from __future__ import annotations
import asyncio
import datetime
import json
import logging
import os
import traceback
from configparser import ConfigParser
from importlib import import_module
from subprocess import check_output
from typing import Optional, Union, List

import aiohttp
import requests
from disnake.ext import commands
import disnake

from config_loader import load_config
from web_app import WSClient, start
from utils.music.checks import check_pool_bots
from utils.music.errors import GenericError
from utils.music.local_lavalink import run_lavalink
from utils.music.models import music_mode
from utils.music.spotify import spotify_client
from asyncspotify import Client
from utils.owner_panel import PanelView
from utils.db import MongoDatabase, LocalDatabase, guild_prefix, DBModel, global_db_models
from asyncspotify import Client as SpotifyClient
from utils.others import CustomContext

class BotPool:

    bots: List[BotCore] = []
    killing_state = False

    def __init__(self):
        self.playlist_cache = {}
        self.mongo_database: Optional[MongoDatabase] = None
        self.local_database: Optional[LocalDatabase] = None
        self.ws_client: Optional[WSClient] = None
        self.spotify: Optional[Client] = None
        self.config = {}
        self.commit = ""
        self.remote_git_url = ""
        self.max_counter: int = 0
        self.message_ids: set = set()
        self.db_cache_cleanup_task = None
        self.bot_mentions = set()

    @property
    def database(self) -> Union[LocalDatabase, MongoDatabase]:

        if self.config["MONGO"]:
            return self.mongo_database

        return self.local_database

    async def start_bot(self, bot: BotCore):
        try:
            await bot.start(bot.http.token)
        except disnake.HTTPException as e:

            if e.status == 429 or "429 Too Many Requests" in str(e):

                if not self.config["KILL_ON_429"]:

                    if self.killing_state == "ratelimit":
                        return

                    self.killing_state = "ratelimit"
                    print("Aplicação com ratelimit do discord!")
                    return

                if self.killing_state is True:
                    return

                print(
                    "Aplicação com ratelimit do discord!\n"
                    "Finalizando/Reiniciando o processo em 5 segundos..."
                )

                self.killing_state = True

                await asyncio.sleep(5)

                await asyncio.create_subprocess_shell("kill 1")

                return

            traceback.print_exc()
            bot.pool.bots.remove(bot)

        except Exception:
            traceback.print_exc()
            bot.pool.bots.remove(bot)

    async def run_bots(self, bots: List[BotCore]):
        await asyncio.wait(
            [asyncio.create_task(self.start_bot(bot)) for bot in bots]
        )

    def load_playlist_cache(self):

        try:
            with open(f"./playlist_cache.json") as file:
                self.playlist_cache = json.load(file)
        except FileNotFoundError:
            return

    async def connect_spotify(self):

        if not self.spotify:
            return

        await self.spotify.authorize()

    async def db_cache_cleanup(self):

        while True:

            await asyncio.sleep(self.config["MONGO_CACHE_CLEANUP_INTERVAL"])

            try:
                self.database.data_cache.clear()
            except AttributeError:
                return
            except:
                continue

    async def connect_rpc_ws(self):

        if not self.config["RUN_RPC_SERVER"] and (
                not self.config["RPC_SERVER"] or self.config["RPC_SERVER"] == "ws://localhost:80/ws"):
            pass
        else:
            await self.ws_client.ws_loop()

    def setup(self):

        self.config = load_config()

        if not self.config["DEFAULT_PREFIX"]:
            self.config["DEFAULT_PREFIX"] = "!!"

        if self.config['ENABLE_LOGGER']:

            if not os.path.isdir("./.logs"):
                os.makedirs("./.logs")

            logger = logging.getLogger()
            logger.setLevel(logging.DEBUG)
            handler = logging.FileHandler(filename='./.logs/disnake.log', encoding='utf-8', mode='w')
            handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
            logger.addHandler(handler)

        LAVALINK_SERVERS = {}

        if self.config["AUTO_DOWNLOAD_LAVALINK_SERVERLIST"]:
            ini_file = "auto_lavalink.ini"
            print("Baixando lista de servidores lavalink (arquivo: lavalink.ini)")
            r = requests.get(self.config["LAVALINK_SERVER_LIST"], allow_redirects=True)
            with open("auto_lavalink.ini", 'wb') as f:
                f.write(r.content)
            r.close()
        else:
            ini_file = "lavalink.ini"

        for key, value in self.config.items():

            if key.lower().startswith("lavalink_node_"):
                try:
                    LAVALINK_SERVERS[key] = json.loads(value)
                except Exception as e:
                    print(f"Falha ao adicionar node: {key}, erro: {repr(e)}")

        config = ConfigParser()
        try:
            config.read(ini_file)
        except FileNotFoundError:
            pass
        except Exception:
            traceback.print_exc()
        else:
            for key, value in {section: dict(config.items(section)) for section in config.sections()}.items():
                value["identifier"] = key.replace(" ", "_")
                value["secure"] = value.get("secure") == "true"
                value["search"] = value.get("search") != "false"
                LAVALINK_SERVERS[key] = value

        if start_local := (self.config['RUN_LOCAL_LAVALINK'] is True or not LAVALINK_SERVERS):
            pass
        else:
            start_local = False

        intents = disnake.Intents(**{i[:-7].lower(): v for i, v in self.config.items() if i.lower().endswith("_intent")})
        intents.members = True
        intents.guilds = True

        mongo_key = self.config.get("MONGO")

        if mongo_key:
            self.mongo_database = MongoDatabase(mongo_key)
        else:
            print(f"O token/link do mongoDB não foi configurado...\nSerá usado um arquivo json para database.\n{'-' * 30}")

        self.local_database = LocalDatabase()

        try:
            self.commit = check_output(['git', 'rev-parse', 'HEAD']).decode('ascii').strip()
            print(f"Commit ver: {self.commit}\n{'-' * 30}")
        except:
            self.commit = None

        try:
            self.remote_git_url = check_output(['git', 'remote', '-v']).decode(
                'ascii').strip().split("\n")[0][7:].replace(".git", "").replace(" (fetch)", "")
        except:
            self.remote_git_url = ""

        prefix = guild_prefix if intents.message_content else commands.when_mentioned

        self.load_playlist_cache()

        self.ws_client = WSClient(self.config["RPC_SERVER"], pool=self)

        self.spotify = spotify_client(self.config)

        def load_bot(bot_name: str, token: str):

            if self.config["GLOBAL_PREFIX"]:
                try:
                    token = token.split()[0]
                except:
                    pass
                default_prefix = self.config["DEFAULT_PREFIX"]
            else:
                try:
                    token, default_prefix = token.split()
                except:
                    default_prefix = None

            if not token:
                print(f"{bot_name} Ignorado (token não informado)...")
                return

            try:
                test_guilds = list([int(i) for i in self.config[f"TEST_GUILDS_{bot_name}"].split("||")])
            except:
                test_guilds = None

            bot = BotCore(
                command_prefix=prefix,
                case_insensitive=True,
                intents=intents,
                identifier=bot_name,
                test_guilds=test_guilds,
                command_sync_flags=commands.CommandSyncFlags.none(),
                embed_color=self.config["EMBED_COLOR"],
                default_prefix=default_prefix,
                pool=self,
                number=int(self.max_counter)
            )

            bot.http.token = token

            bot.load_extension("jishaku")

            jsk = bot.get_command("jsk")
            jsk.hidden = True

            if bot.config['INTERACTION_COMMAND_ONLY']:

                @bot.check
                async def check_commands(ctx: CustomContext):

                    if not (await bot.is_owner(ctx.author)):
                        raise GenericError("**Os comandos de texto estão desativados!\n"
                                           "Use os comandos de barra /**", self_delete=True, delete_original=15)

                    return True

            if bot.config["GLOBAL_PREFIX"]:

                @bot.listen("on_command")
                async def message_id_cleanup(ctx: CustomContext):

                    id_ = f"{ctx.guild.id}-{ctx.channel.id}-{ctx.message.id}"

                    if id_ not in ctx.bot.pool.message_ids:
                        return

                    await asyncio.sleep(ctx.bot.config["PREFIXED_POOL_TIMEOUT"])

                    try:
                        ctx.bot.pool.message_ids.remove(id_)
                    except:
                        pass

            @bot.application_command_check(slash_commands=True, message_commands=True, user_commands=True)
            async def check(inter: disnake.ApplicationCommandInteraction):

                kwargs = {}

                try:
                    kwargs["only_voiced"] = inter.application_command.extras["only_voiced"]
                except KeyError:
                    pass

                try:
                    kwargs["check_player"] = inter.application_command.extras["check_player"]
                except KeyError:
                    pass

                try:
                    kwargs["return_first"] = inter.application_command.extras["return_first"]
                except KeyError:
                    pass

                if not kwargs:
                    kwargs["return_first"] = True

                await check_pool_bots(inter, **kwargs)

                return True

            @bot.listen()
            async def on_ready():

                if not bot.bot_ready:

                    if not bot.config["INTERACTION_BOTS"] or str(bot.user.id) in bot.config["INTERACTION_BOTS"]:

                        self._command_sync_flags = commands.CommandSyncFlags.all()

                        bot.load_modules()

                        if bot.config["AUTO_SYNC_COMMANDS"]:
                            await bot.sync_app_commands(force=True)

                    else:

                        self._command_sync_flags = commands.CommandSyncFlags.none()

                        if self.config["INTERACTION_BOTS"] and self.config["GLOBAL_PREFIX"] and self.config["ADD_REGISTER_COMMAND"]:

                            @bot.slash_command(
                                name=disnake.Localized("register_commands",data={disnake.Locale.pt_BR: "registrar_comandos"}),
                                description="Use este comando caso meus outros comandos de barra (/) não estejam disponíveis..."
                            )
                            async def register_commands(
                                    inter: disnake.AppCmdInter,
                            ):
                                interaction_invites = ""

                                for b in self.bots:

                                    try:
                                        if str(b.user.id) not in self.config["INTERACTION_BOTS"]:
                                            continue
                                    except:
                                        continue

                                    interaction_invites += f"[`{disnake.utils.escape_markdown(str(b.user.name))}`]({disnake.utils.oauth_url(b.user.id, scopes=['applications.commands'])}) "

                                embed = disnake.Embed(
                                    description="**Atenção!** Todos os meus comandos de barra (/) funcionam através da aplicação "
                                                f"com um dos nomes abaixo:**\n{interaction_invites}\n\n"
                                                "**Caso os comandos da aplicação acima não sejam exibidos ao digitar barra (/), "
                                                "clique no nome acima para integrar os comandos de barra no seu "
                                                "servidor.",
                                    color=bot.get_color()
                                )

                                if not inter.author.guild_permissions.manage_guild:
                                    embed.description += "\n\n**Nota:** Será necessário ter a permissão de **Gerenciar " \
                                                         "Servidor** para integrar os comandos no servidor atual."

                                await inter.send(embed=embed, ephemeral=True)

                        if bot.config["AUTO_SYNC_COMMANDS"]:
                            await bot.sync_app_commands(force=True)

                        bot.load_modules()

                    if not bot.appinfo:
                        bot.loop.create_task(bot.update_appinfo())

                    music_cog = bot.get_cog("Music")

                    if music_cog:
                        bot.loop.create_task(music_cog.process_nodes(data=LAVALINK_SERVERS, start_local=start_local))

                    bot.add_view(PanelView(bot))

                    self.bot_mentions.update((f"<@!{bot.user.id}>", f"<@{bot.user.id}>"))

                    bot.sync_command_cooldowns()

                    bot.bot_ready = True

                print(f'{bot.user} - [{bot.user.id}] Online.')

            self.bots.append(bot)

        main_token = self.config.get("TOKEN")

        if main_token:
            load_bot("Main Bot", main_token)

        for k, v in self.config.items():

            if not k.lower().startswith("token_bot_"):
                continue

            bot_name = k[10:] or f"Bot_{self.max_counter}"

            load_bot(bot_name, v)

        if not self.bots:
            os.system('cls' if os.name == 'nt' else 'clear')
            raise Exception(
                "O token do bot não foi configurado devidamente!\n"
                "Confira se o token foi configurado na ENV/ENVIRONMENT/SECRETS ou no arquivo .env\n"
                "Caso ainda tenha dúvidas, entre no servidor de suporte: https://discord.gg/R7BPG8fZTr"
            )

        if start_local:
            run_lavalink(
                lavalink_file_url=self.config['LAVALINK_FILE_URL'],
                lavalink_initial_ram=self.config['LAVALINK_INITIAL_RAM'],
                lavalink_ram_limit=self.config['LAVALINK_RAM_LIMIT'],
                lavalink_additional_sleep=int(self.config['LAVALINK_ADDITIONAL_SLEEP']),
            )

        loop = asyncio.get_event_loop()

        self.database.start_task(loop)
        self.db_cache_cleanup_task = loop.create_task(self.db_cache_cleanup())

        if self.config["RUN_RPC_SERVER"]:

            for bot in self.bots:
                loop.create_task(self.start_bot(bot))

            loop.create_task(self.connect_rpc_ws())
            loop.create_task(self.connect_spotify())

            start(self.bots)

        else:

            loop.create_task(self.connect_rpc_ws())
            loop.create_task(self.connect_spotify())
            loop.run_until_complete(
                self.run_bots(self.bots)
            )


class BotCore(commands.Bot):

    def __init__(self, *args, **kwargs):
        self.session: Optional[aiohttp.ClientError] = None
        self.pool: BotPool = kwargs.pop('pool')
        self.config = self.pool.config
        self.default_prefix = kwargs.pop("default_prefix", "!!")
        self.spotify: Optional[SpotifyClient] = self.pool.spotify
        self.session = aiohttp.ClientSession()
        self.ws_client = self.pool.ws_client
        self.color = kwargs.pop("embed_color", None)
        self.identifier = kwargs.pop("identifier", "")
        self.appinfo: Optional[disnake.AppInfo] = None
        self.bot_ready = False
        self.player_skins = {}
        self.player_static_skins = {}
        self.default_skin = self.config.get("DEFAULT_SKIN", "default")
        self.default_static_skin = self.config.get("DEFAULT_STATIC_SKIN", "default")
        self.default_controllerless_skin = self.config.get("DEFAULT_CONTROLLERLESS_SKIN", "default")
        self.default_idling_skin = self.config.get("DEFAULT_IDLING_SKIN", "default")
        self.load_skins()
        self.uptime = disnake.utils.utcnow()
        self.env_owner_ids = set()
        self.dm_cooldown = commands.CooldownMapping.from_cooldown(rate=2, per=30, type=commands.BucketType.member)
        self.number = kwargs.pop("number", 0)
        super().__init__(*args, **kwargs)
        self.music = music_mode(self)

        for i in self.config["OWNER_IDS"].split("||"):

            if not i:
                continue

            try:
                self.env_owner_ids.add(int(i))
            except ValueError:
                print(f"Owner_ID inválido: {i}")

    def load_skins(self):

        for skin in os.listdir("./utils/music/skins/normal_player"):
            if not skin.endswith(".py"):
                continue
            try:
                skin_file = import_module(f"utils.music.skins.normal_player.{skin[:-3]}")
                if not hasattr(skin_file, "load"):
                    print(f"Skin ignorada: {skin} | Função load() não configurada/encontrada...")
                    continue
                self.player_skins[skin[:-3]] = skin_file.load()
            except Exception:
                print(f"Falha ao carregar skin [normal_player]: {traceback.format_exc()}")
        if self.default_skin not in self.player_skins:
            self.default_skin = "default"

        for skin in os.listdir("./utils/music/skins/static_player"):
            if not skin.endswith(".py"):
                continue
            try:
                skin_file = import_module(f"utils.music.skins.static_player.{skin[:-3]}")
                if not hasattr(skin_file, "load"):
                    print(f"Skin ignorada: {skin} | Função load() não configurada/encontrada...")
                    continue
                self.player_static_skins[skin[:-3]] = skin_file.load()
            except Exception:
                print(f"Falha ao carregar skin [static_player]: {traceback.format_exc()}")
        if self.default_static_skin not in self.player_static_skins:
            self.default_static_skin = "default"

    async def get_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.get_data(
            id_=id_, db_name=db_name, collection=str(self.user.id)
        )

    async def update_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.update_data(
            id_=id_, data=data, db_name=db_name, collection=str(self.user.id)
        )

    async def get_global_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.get_data(
            id_=id_, db_name=db_name, collection="global", default_model=global_db_models
        )

    async def update_global_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.update_data(
            id_=id_, data=data, db_name=db_name, collection="global", default_model=global_db_models
        )

    def check_skin(self, skin: str):

        if skin is None or skin not in self.player_skins:
            return self.default_skin

        return skin

    def check_static_skin(self, skin: str):

        if skin is None or skin not in self.player_static_skins:
            return self.default_static_skin

        return skin

    async def is_owner(self, user: Union[disnake.User, disnake.Member]) -> bool:

        if user.id in self.env_owner_ids:
            return True

        return await super().is_owner(user)

    async def sync_app_commands(self, force=False):

        if not self.command_sync_flags.sync_commands and not force:
            return

        self._command_sync_flags = commands.CommandSyncFlags.all()
        await self._sync_application_commands()
        self._command_sync_flags = commands.CommandSyncFlags.none()

    def sync_command_cooldowns(self):

        for b in self.pool.bots:

            if not b.bot_ready or b == self:
                continue

            for cmd in b.commands:
                if cmd.extras.get("exclusive_cooldown"): continue
                self.get_command(cmd.name)._buckets = cmd._buckets

            for cmd in b.slash_commands:
                c = self.get_slash_command(cmd.name)
                if not c: continue
                if c.extras.get("exclusive_cooldown"): continue
                c._buckets = cmd._buckets

            for cmd in b.user_commands:
                c = self.get_user_command(cmd.name)
                if not c: continue
                if c.extras.get("exclusive_cooldown"): continue
                c._buckets = cmd._buckets

            for cmd in b.message_commands:
                c = self.get_message_command(cmd.name)
                if not c: continue
                if c.extras.get("exclusive_cooldown"): continue
                c._buckets = cmd._buckets

    async def can_send_message(self, message: disnake.Message):

        if not message.channel.permissions_for(message.guild.me).send_messages:

            print(f"Can't send message in: {message.channel.name} [{message.channel.id}] (Missing permissions)")

            bucket = self.dm_cooldown.get_bucket(message)
            retry_after = bucket.update_rate_limit()

            if retry_after:
                return

            try:
                await message.author.send(f"Não tenho permissão para enviar mensagens no canal {message.channel.mention}...")
            except disnake.HTTPException:
                pass

        return True

    async def on_message(self, message: disnake.Message):

        if not self.bot_ready:
            return

        if not message.guild:
            return

        if isinstance(message.channel, disnake.StageChannel):
            pass

        elif message.author.bot:
            return

        elif message.content in (f"<@{self.user.id}>",  f"<@!{self.user.id}>"):

            if message.author.bot:
                return

            if not await self.can_send_message(message):
                return

            embed = disnake.Embed(color=self.get_color(message.guild.me))

            kwargs = {}

            if not (await self.is_owner(message.author)):

                prefix = (await self.get_prefix(message))

                if not isinstance(prefix, str):
                    prefix = prefix[-1]

                embed.description = f"**Olá {message.author.mention}.\n\n" \
                                    f"Para ver todos os meus comandos use: /**"

                bot_count = 0

                if not self.command_sync_flags.sync_commands and self.config["INTERACTION_BOTS"]:

                    interaction_invites = []

                    for b in self.pool.bots:

                        if str(b.user.id) not in self.config["INTERACTION_BOTS"]:
                            continue

                        try:
                            if b.appinfo.bot_public and b.user not in message.guild.members:
                                bot_count += 1
                        except AttributeError:
                            pass

                        interaction_invites.append(f"[`{disnake.utils.escape_markdown(str(b.user.name))}`]({disnake.utils.oauth_url(b.user.id, scopes=['applications.commands'])}) ")

                    if interaction_invites:
                        embed.description += f"\n\nMeus comandos de barra (/) funcionam através " \
                                             f"das seguintes aplicações abaixo:\n" \
                                             f"{' **|** '.join(interaction_invites)}\n\n" \
                                             f"Caso os comandos da aplicação acima não sejam exibidos ao digitar " \
                                             f"barra (/), clique no nome acima para integrar os comandos de barra no " \
                                             f"seu servidor."

                if not self.config["INTERACTION_COMMAND_ONLY"]:
                    embed.description += f"\n\nTambém tenho comandos de texto por prefixo.\n" \
                                        f"Para ver todos os meus comandos de texto use **{prefix}help**\n"

                if bot_count:

                    kwargs = {
                        "components": [
                            disnake.ui.Button(
                                custom_id="bot_invite",
                                label="Precisa de mais bots de música? Clique aqui."
                            )
                        ]
                    }

            else:

                embed.title = "PAINEL DE CONTROLE."
                embed.set_footer(text="Clique em uma tarefa que deseja executar.")
                kwargs = {"view": PanelView(self)}

            await message.reply(embed=embed, **kwargs)
            return

        ctx: CustomContext = await self.get_context(message, cls=CustomContext)

        self.dispatch("song_request", ctx, message)

        if not ctx.valid:
            return

        if not await self.can_send_message(message):
            return

        try:
            kwargs = {
                "only_voiced": ctx.command.pool_only_voiced,
                "check_player": ctx.command.pool_check_player,
                "return_first": ctx.command.pool_return_first,
            }
        except AttributeError:
            kwargs = {"return_first": True}

        try:
            await check_pool_bots(ctx, **kwargs)
        except Exception as e:
            self.dispatch("command_error", ctx, e)
            return

        await self.invoke(ctx)

    def check_bot_forum_post(
            self,
            channel: Union[disnake.ForumChannel, disnake.TextChannel, disnake.VoiceChannel, disnake.Thread],
            raise_error=False,
    ):

        try:
            if isinstance(channel.parent, disnake.ForumChannel):

                if channel.owner_id in (bot.user.id for bot in self.pool.bots if bot.bot_ready):

                    if raise_error is False:
                        return False

                    raise GenericError("**Você não pode usar comandos prefixed na postagem atual...**\n"
                                       "`Use comando de barra (/) aqui.`", self_delete=True)
        except AttributeError:
            pass

        return True

    def get_color(self, me: Optional[disnake.Member] = None):

        if not me:
            return self.color or 0x2F3136

        if self.color:
            return self.color

        if me.color.value == 0:
            return 0x2F3136

        return me.color

    async def update_appinfo(self):

        self.appinfo = (await self.application_info())

        try:
            self.owner = self.appinfo.team.members[0]
        except AttributeError:
            self.owner = self.appinfo.owner

    async def on_application_command_autocomplete(self, inter: disnake.ApplicationCommandInteraction):

        if not self.bot_ready or not inter.guild_id:
            return

        await super().on_application_command_autocomplete(inter)

    async def on_application_command(self, inter: disnake.ApplicationCommandInteraction):

        if not inter.guild_id:
            await inter.send("Meus comandos não podem ser usados no DM.\n"
                             "Use em algum servidor que estou presente.")
            return

        if not self.bot_ready:
            await inter.send("Ainda estou inicializando...\nPor favor aguarde mais um pouco...", ephemeral=True)
            return

        if self.config["COMMAND_LOG"] and inter.guild:
            try:
                print(f"cmd log: [user: {inter.author} - {inter.author.id}] - [guild: {inter.guild.name} - {inter.guild.id}]"
                      f" - [cmd: {inter.data.name}] {datetime.datetime.utcnow().strftime('%d/%m/%Y - %H:%M:%S')} (UTC) - {inter.filled_options}\n" + ("-" * 15))
            except:
                traceback.print_exc()

        await super().on_application_command(inter)

    def load_modules(self):

        modules_dir = "modules"

        load_status = {
            "reloaded": [],
            "loaded": []
        }

        bot_name = self.user or self.identifier

        for item in os.walk(modules_dir):
            files = filter(lambda f: f.endswith('.py'), item[-1])
            for file in files:
                filename, _ = os.path.splitext(file)
                module_filename = os.path.join(modules_dir, filename).replace('\\', '.').replace('/', '.')
                try:
                    self.reload_extension(module_filename)
                    print(f"{'=' * 48}\n[OK] {bot_name} - {filename}.py Recarregado.")
                    load_status["reloaded"].append(f"{filename}.py")
                except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
                    try:
                        self.load_extension(module_filename)
                        print(f"{'=' * 48}\n[OK] {bot_name} - {filename}.py Carregado.")
                        load_status["loaded"].append(f"{filename}.py")
                    except Exception as e:
                        print(f"{'=' * 48}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename}")
                        raise e
                except Exception as e:
                    print(f"{'=' * 48}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename}")
                    raise e

        print(f"{'=' * 48}")

        if not self.config["ENABLE_DISCORD_URLS_PLAYBACK"]:
            self.remove_slash_command("play_nusic_file")

        for c in self.slash_commands:
            if (desc:=len(c.description)) > 100:
                raise Exception(f"A descrição do comando {c.name} excedeu a quantidade de caracteres permitido "
                                f"no discord (100), quantidade atual: {desc}")

        return load_status
