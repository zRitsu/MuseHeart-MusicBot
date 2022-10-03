from __future__ import annotations
import asyncio
import datetime
import json
import logging
import subprocess
from configparser import ConfigParser
from importlib import import_module
from subprocess import check_output
import aiohttp
import requests
from disnake.ext import commands
import disnake
from typing import Optional, Union, List
from config_loader import load_config
from web_app import WSClient, start
from .music.errors import GenericError
from .music.local_lavalink import run_lavalink
from .music.models import music_mode
from .music.spotify import spotify_client
from asyncspotify import Client
from .owner_panel import PanelView
from utils.db import MongoDatabase, LocalDatabase, guild_prefix, DBModel, global_db_models
from asyncspotify import Client as SpotifyClient
from utils.others import sync_message, CustomContext
import os
import traceback


async def start_bot(bot: BotCore):
    try:
        await bot.start(bot.token)
    except:
        traceback.print_exc()
    del bot.token


async def run_bots(bots: List[BotCore]):
    await asyncio.wait(
        [asyncio.create_task(start_bot(bot)) for bot in bots]
    )

class BotPool:

    bots: List[BotCore] = []

    def __init__(self):
        self.playlist_cache = {}
        self.database: Union[MongoDatabase, LocalDatabase] = None
        self.ws_client: Optional[WSClient] = None
        self.spotify: Optional[Client] = None
        self.lavalink_process: Optional[subprocess.Popen] = None
        self.config = {}
        self.commit = ""
        self.remote_git_url = ""

    def load_playlist_cache(self):

        try:
            with open(f"./playlist_cache.json") as file:
                self.playlist_cache = json.load(file)
        except FileNotFoundError:
            return

    async def connect_spotify(self):

        if not self.spotify:
            return

        await self.bots[0].wait_until_ready()  # método temporário para contornar um problema de inicialização
        await self.spotify.authorize()

    async def connect_rpc_ws(self):

        if not self.config["RUN_RPC_SERVER"] and (
                not self.config["RPC_SERVER"] or self.config["RPC_SERVER"] == "ws://localhost:8080/ws"):
            pass
        else:
            await self.ws_client.ws_loop()

    def setup(self):

        self.config = load_config()

        if not self.config["DEFAULT_PREFIX"]:
            self.config["DEFAULT_PREFIX"] = "!!!"

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
            print("Baixando lista de servidores lavalink (arquivo: lavalink.ini)")
            r = requests.get(self.config["LAVALINK_SERVER_LIST"], allow_redirects=True)
            with open("lavalink.ini", 'wb') as f:
                f.write(r.content)
            r.close()

        for key, value in self.config.items():

            if key.lower().startswith("lavalink_node_"):
                try:
                    LAVALINK_SERVERS[key] = json.loads(value)
                except Exception as e:
                    print(f"Falha ao adicionar node: {key}, erro: {repr(e)}")

        config = ConfigParser()
        try:
            config.read('lavalink.ini')
        except FileNotFoundError:
            pass
        except Exception as e:
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

        mongo_key = self.config.get("MONGO")

        if not mongo_key:
            print(f"O token/link do mongoDB não foi configurado...\nSerá usado um arquivo json para database.\n{'-' * 30}")
            self.database = LocalDatabase()
        else:
            self.database = MongoDatabase(token=mongo_key)

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

        try:
            os.makedirs("./local_dbs/user_playlists")
        except:
            pass

        self.load_playlist_cache()

        self.ws_client = WSClient(self.config["RPC_SERVER"], pool=self)

        self.spotify = spotify_client(self.config)

        def load_bot(bot_name: str, token: str):

            try:
                token, default_prefix = token.split()
            except:
                default_prefix = self.config["DEFAULT_PREFIX"]

            try:
                test_guilds = list([int(i) for i in self.config[f"TEST_GUILDS_{bot_name}"].split("||")])
            except:
                test_guilds = None

            bot = BotCore(
                command_prefix=prefix,
                case_insensitive=True,
                intents=intents,
                test_guilds=test_guilds,
                sync_commands=False,
                sync_commands_debug=True,
                embed_color=self.config["EMBED_COLOR"],
                default_prefix=default_prefix,
                pool=self
            )

            bot.token = token

            bot.load_extension("jishaku")
            bot.get_command("jsk").hidden = True

            @bot.check
            async def forum_check(ctx: CustomContext):

                bot.check_bot_forum_post(ctx.channel, raise_error=True)
                return True

            if bot.config['INTERACTION_COMMAND_ONLY']:

                @bot.check
                async def check_commands(ctx: CustomContext):

                    if not (await bot.is_owner(ctx.author)):
                        raise GenericError("**Os comandos de texto estão desativados!\n"
                                           "Use os comandos de barra /**", self_delete=True, delete_original=True)

                    return True


            @bot.listen()
            async def on_ready():

                if not bot.bot_ready:

                    if bot.config["AUTO_SYNC_COMMANDS"]:

                        if not bot.config["INTERACTION_BOTS"] or str(bot.user.id) in bot.config["INTERACTION_BOTS"]:
                            self._sync_commands = True
                            bot.load_modules(bot_name)
                            await bot.sync_app_commands()
                        else:
                            self._sync_commands = False
                            await bot.sync_app_commands()
                            bot.load_modules(bot_name)

                    if not bot.owner:
                        botowner = (await bot.application_info())
                        try:
                            bot.owner = botowner.team.members[0]
                        except AttributeError:
                            bot.owner = botowner.owner
                        bot.public = botowner.bot_public

                    music_cog = bot.get_cog("Music")

                    if music_cog:
                        bot.loop.create_task(music_cog.process_nodes(data=LAVALINK_SERVERS, start_local=start_local))

                    bot.add_view(PanelView(bot))

                    bot.bot_ready = True

                print(f'{bot.user} - [{bot.user.id}] Online.')

            self.bots.append(bot)

        main_token = self.config.get("TOKEN")

        if main_token:
            load_bot("Main Bot", main_token)

        for k, v in self.config.items():

            if not k.lower().startswith("token_bot_"):
                continue

            bot_name = k[10:] or "Sec. Bot"

            load_bot(bot_name, v)

        if not self.bots:
            raise Exception("O token do bot não foi configurado devidamente!")

        if start_local:
            self.lavalink_process = run_lavalink(
                lavalink_file_url=self.config['LAVALINK_FILE_URL'],
                lavalink_initial_ram=self.config['LAVALINK_INITIAL_RAM'],
                lavalink_ram_limit=self.config['LAVALINK_RAM_LIMIT'],
                lavalink_additional_sleep=int(self.config['LAVALINK_ADDITIONAL_SLEEP']),
            )

        loop = asyncio.get_event_loop()

        self.database.start_task(loop)

        if self.config["RUN_RPC_SERVER"]:

            for bot in self.bots:
                loop.create_task(start_bot(bot))

            loop.create_task(self.connect_rpc_ws())
            loop.create_task(self.connect_spotify())

            start(self.bots)

        else:

            loop.create_task(self.connect_rpc_ws())
            loop.create_task(self.connect_spotify())
            loop.run_until_complete(
                run_bots(self.bots)
            )


class BotCore(commands.Bot):

    def __init__(self, *args, **kwargs):
        self.session: Optional[aiohttp.ClientError] = None
        self.pool: BotPool = kwargs.pop('pool')
        self.config = self.pool.config
        self.default_prefix = kwargs.pop("default_prefix", "!!!")
        self.spotify: Optional[SpotifyClient] = self.pool.spotify
        self.session = aiohttp.ClientSession()
        self.ws_client = self.pool.ws_client
        self.color = kwargs.pop("embed_color", None)
        self.bot_ready = False
        self.player_skins = {}
        self.default_skin = self.config.get("DEFAULT_SKIN", "default")
        self.load_skins()
        self.uptime = disnake.utils.utcnow()
        self.env_owner_ids = set()
        self.dm_cooldown = commands.CooldownMapping.from_cooldown(rate=2, per=30, type=commands.BucketType.member)
        super().__init__(*args, **kwargs)
        self.music = music_mode(self)
        self.public = None

        for i in self.config["OWNER_IDS"].split("||"):

            if not i:
                continue

            try:
                self.env_owner_ids.add(int(i))
            except ValueError:
                print(f"Owner_ID inválido: {i}")

    def load_skins(self):

        for skin in os.listdir("./utils/music/skins"):

            if not skin.endswith(".py"):
                continue

            try:
                skin_file = import_module(f"utils.music.skins.{skin[:-3]}")

                if not hasattr(skin_file, "load"):
                    print(f"Skin ignorada: {skin} | Função load() não configurada/encontrada...")
                    continue

                self.player_skins[skin[:-3]] = skin_file.load

            except Exception:
                print(f"Falha ao carregar skin: {traceback.format_exc()}")

        if self.default_skin not in self.player_skins:
            self.default_skin = "default"

    async def get_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.get_data(id_=id_, db_name=db_name, collection=str(self.user.id))

    async def update_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.update_data(id_=id_, data=data, db_name=db_name, collection=str(self.user.id))

    async def get_global_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.get_data(
            id_=id_, db_name=db_name, collection="global", default_model=global_db_models
        )

    async def update_global_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.update_data(
            id_=id_, data=data, db_name=db_name, collection="global", default_model=global_db_models
        )

    def check_skin(self, skin: str):

        if skin is None or skin == "default" or skin not in self.player_skins:
            return self.default_skin

        return skin

    async def is_owner(self, user: Union[disnake.User, disnake.Member]) -> bool:

        if user.id in self.env_owner_ids:
            return True

        return await super().is_owner(user)

    async def sync_app_commands(self):

        if not self._sync_commands:
            return

        self._sync_commands = True
        await self._sync_application_commands()
        self._sync_commands = False

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

        if message.is_system():
            return

        if message.content in (f"<@{self.user.id}>",  f"<@!{self.user.id}>"):

            if message.author.bot:
                return

            if not await self.can_send_message(message):
                return

            embed = disnake.Embed(color=self.get_color(message.guild.me))

            if not (await self.is_owner(message.author)):

                prefix = (await self.get_prefix(message))[-1]

                embed.description = f"**Olá {message.author.mention}.\n" \
                                    f"Para ver todos os meus comandos use: /**"

                if message.author.guild_permissions.administrator:
                    embed.description += f"\n\n{sync_message(self)}"

                if not self.config["INTERACTION_COMMAND_ONLY"]:
                    embed.description += f"\n\nTambém tenho comandos de texto por prefixo.\n" \
                                        f"Para ver todos os meus comandos de texto use **{prefix}help**\n"

                if not self._sync_commands and self.config["INTERACTION_BOTS"]:

                    interaction_invites = ""

                    for b in self.pool.bots:

                        if str(b.user.id) not in self.config["INTERACTION_BOTS"]:
                            continue

                        interaction_invites += f"[`{disnake.utils.escape_markdown(str(b.user)).replace(' ', '_')}`]({disnake.utils.oauth_url(b.user.id, scopes=['applications.commands'])}) "

                    if interaction_invites:
                        embed.description += f"Caso os comandos de barra (/) não apareçam, você terá que integrar um dos " \
                                             f"seguintes bots no servidor: {interaction_invites}"

                view = None

            else:

                embed.title = "PAINEL DE CONTROLE."
                embed.set_footer(text="Clique em uma tarefa que deseja executar.")
                view = PanelView(self)

            await message.reply(embed=embed, view=view)
            return

        ctx: CustomContext = await self.get_context(message, cls=CustomContext)

        self.dispatch("song_request", ctx, message)

        if message.author.bot:
            return

        if not ctx.valid:
            return

        if not await self.can_send_message(message):
            return

        await self.invoke(ctx)

    def check_bot_forum_post(
            self,
            channel: Union[disnake.ForumChannel, disnake.TextChannel, disnake.VoiceChannel, disnake.Thread],
            raise_error=False,
    ):

        try:
            if isinstance(channel.parent, disnake.ForumChannel):
                if self.intents.members and channel.owner.bot:

                    if raise_error is False:
                        return False

                    raise GenericError("**Você não pode usar comandos prefixed em postagens de bots.**\n"
                                       "`Use comando de barra (/) aqui.`", self_delete=True)

                if channel.owner_id in (bot.user.id for bot in self.pool.bots):

                    if raise_error is False:
                        return False

                    raise GenericError("**Você não pode usar comandos prefixed na postagem atual...**\n"
                                       "`Use comando de barra (/) aqui.`", self_delete=True)
        except AttributeError:
            pass

        return True

    def get_color(self, me: disnake.Member):

        if self.color:
            return self.color

        if me.color.value == 0:
            return 0x2F3136

        return me.color

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
            print(f"cmd log: [user: {inter.author} - {inter.author.id}] - [guild: {inter.guild.name} - {inter.guild.id}]"
                  f" - [cmd: {inter.data.name}] "
                  f"{datetime.datetime.utcnow().strftime('%d/%m/%Y - %H:%M:%S')} (UTC)\n" + ("-"*15))

        await super().on_application_command(inter)

    def load_modules(self, bot_name: str = None):

        modules_dir = "modules"

        load_status = {
            "reloaded": [],
            "loaded": []
        }

        if not bot_name:
            bot_name = self.user

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

        for c in self.slash_commands:
            if (desc:=len(c.description)) > 100:
                raise Exception(f"A descrição do comando {c.name} excedeu a quantidade de caracteres permitido "
                                f"no discord (100), quantidade atual: {desc}")

        return load_status