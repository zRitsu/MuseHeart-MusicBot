# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import datetime
import gc
import json
import logging
import os
import pickle
import subprocess
import traceback
import zlib
from configparser import ConfigParser
from importlib import import_module
from subprocess import check_output
from typing import Optional, Union, List

import aiofiles
import aiohttp
import disnake
import requests
import spotipy
from disnake.ext import commands
from disnake.http import Route
from dotenv import dotenv_values
from user_agent import generate_user_agent

from config_loader import load_config
from utils.db import MongoDatabase, LocalDatabase, get_prefix, DBModel, global_db_models
from utils.music.checks import check_pool_bots
from utils.music.errors import GenericError
from utils.music.local_lavalink import run_lavalink
from utils.music.models import music_mode, LavalinkPlayer, PartialTrack, LavalinkPlaylist, LavalinkTrack, \
    PartialPlaylist
from utils.music.spotify import spotify_client
from utils.others import CustomContext, token_regex, sort_dict_recursively
from utils.owner_panel import PanelView
from web_app import WSClient, start


class BotPool:

    bots: List[BotCore] = []
    killing_state = False
    command_sync_config = commands.CommandSyncFlags(
                    allow_command_deletion=True,
                    sync_commands=True,
                    sync_commands_debug=True,
                    sync_global_commands=True,
                    sync_guild_commands=True
                )

    add_fav_embed_cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=15,
                                                                         type=commands.BucketType.user)

    enqueue_track_embed_cooldown = commands.CooldownMapping.from_cooldown(rate=2, per=9,
                                                                               type=commands.BucketType.user)

    enqueue_playlist_embed_cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=14,
                                                                                  type=commands.BucketType.user)

    def __init__(self):
        self.playlist_cache = {}
        self.user_prefix_cache = {}
        self.guild_prefix_cache = {}
        self.mongo_database: Optional[MongoDatabase] = None
        self.local_database: Optional[LocalDatabase] = None
        self.ws_client: Optional[WSClient] = None
        self.spotify: Optional[spotipy.Spotify] = None
        self.lavalink_instance: Optional[subprocess.Popen] = None
        self.config = {}
        self.emoji_data = {}
        self.commit = ""
        self.remote_git_url = ""
        self.max_counter: int = 0
        self.message_ids: set = set()
        self.bot_mentions = set()
        self.single_bot = True
        self.rpc_token_cache: dict = {}
        self.failed_bots: dict = {}
        self.controller_bot: Optional[BotCore] = None
        self.current_useragent = self.reset_useragent()
        self.processing_gc: bool = False

    def reset_useragent(self):
        self.current_useragent = generate_user_agent()


    @property
    def database(self) -> Union[LocalDatabase, MongoDatabase]:

        if self.config["MONGO"]:
            return self.mongo_database

        return self.local_database

    async def start_lavalink(self, loop=None):

        if self.lavalink_instance:
            try:
                self.lavalink_instance.kill()
            except:
                traceback.print_exc()

        if not loop:
            loop = asyncio.get_event_loop()

        try:
            self.lavalink_instance = await loop.run_in_executor(
                None, lambda: run_lavalink(
                    lavalink_file_url=self.config['LAVALINK_FILE_URL'],
                    lavalink_initial_ram=self.config['LAVALINK_INITIAL_RAM'],
                    lavalink_ram_limit=self.config['LAVALINK_RAM_LIMIT'],
                    lavalink_additional_sleep=int(self.config['LAVALINK_ADDITIONAL_SLEEP']),
                    use_jabba=self.config["USE_JABBA"]
                )
            )
        except Exception:
            traceback.print_exc()

    async def start_bot(self, bot: BotCore):

        e = None

        try:
            await bot.start(bot.http.token)
        except disnake.HTTPException as error:

            if error.status == 429 or "429 Too Many Requests" in str(e):

                if not self.config["KILL_ON_429"]:

                    if self.killing_state == "ratelimit":
                        return

                    self.killing_state = "ratelimit"
                    print("Aplicação com ratelimit do discord!")
                    await asyncio.sleep(10)
                    raise e

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

            e = error

        except Exception as error:
            e = error

        if e:

            if isinstance(e, disnake.PrivilegedIntentsRequired):
                e = "Você não ativou as Privileged Intents na sua aplicação<br>" \
                    "Acesse o discord developer portal:<br>" \
                    "https://discord.com/developers/applications/<br>" \
                    "e clique na sua aplicação e depois clique no menu \"bot\"<br>" \
                    "e em seguida ative todas as intents.<br>" \
                    "Print de exemplo: https://i.imgur.com/a9c1DHT.png<br>" \
                    "Após corrigir, reinicie a aplicação."

                print(("=" * 30) + f"\nFalha ao iniciar o bot configurado no: {bot.identifier}\n" + e.replace('<br>', '\n') + "\n" + ("=" * 30))

            elif isinstance(e, disnake.LoginFailure) and "Improper token" in str(e):
                e = "Foi utilizado um token inválido.<br>" \
                    "Revise se o token informado está correto<br>" \
                    "ou se o token foi resetado<br>" \
                    "ou copiado do local correto ( ex: https://i.imgur.com/k894c1q.png )<br>" \
                    "Após corrigir, reinicie a aplicação."

                print(("=" * 30) + f"\nFalha ao iniciar o bot configurado no: {bot.identifier}\n" + e.replace('<br>', '\n') + "\n" + ( "=" * 30))

            else:
                traceback.print_tb(e.__traceback__)
                e = repr(e)
            self.failed_bots[bot.identifier] = e
            self.bots.remove(bot)

    async def run_bots(self, bots: List[BotCore]):
        await asyncio.wait(
            [asyncio.create_task(self.start_bot(bot)) for bot in bots]
        )

    async def load_playlist_cache(self):

        try:
            async with aiofiles.open(f"./.playlist_cache.pkl", 'rb') as file:
                data = pickle.loads(zlib.decompress(await file.read()))
        except FileNotFoundError:
            return

        for url, track_data in data.items():
            self.playlist_cache[url] = self.process_track_cls(track_data)

    def process_track_cls(self, data: list, playlists: dict = None):

        if not playlists:
            playlists = {}

        tracks = []

        for info in data:

            if info["sourceName"] == "spotify":

                if playlist := info.pop("playlist", None):

                    try:
                        playlist = playlists[playlist["url"]]
                    except KeyError:
                        playlist_cls = PartialPlaylist(
                            {
                                'loadType': 'PLAYLIST_LOADED',
                                'playlistInfo': {
                                    'name': playlist["name"],
                                    'selectedTrack': -1
                                },
                                'tracks': []
                            }, url=playlist["url"]
                        )
                        playlists[playlist["url"]] = playlist_cls
                        playlist = playlist_cls

                t = PartialTrack(info=info, playlist=playlist)

            else:

                if playlist := info.pop("playlist", None):

                    try:
                        playlist = playlists[playlist["url"]]
                    except KeyError:
                        playlist_cls = LavalinkPlaylist(
                            {
                                'loadType': 'PLAYLIST_LOADED',
                                'playlistInfo': {
                                    'name': playlist["name"],
                                    'selectedTrack': -1
                                },
                                'tracks': []
                            }, url=playlist["url"]
                        )
                        playlists[playlist["url"]] = playlist_cls
                        playlist = playlist_cls

                t = LavalinkTrack(id_=info.get("id", ""), info=info, playlist=playlist, requester=info["extra"]["requester"])

            tracks.append(t)

        return tracks, playlists

    async def connect_rpc_ws(self):

        if not self.config["RUN_RPC_SERVER"] and (
                not self.config["RPC_SERVER"] or self.config["RPC_SERVER"].replace("$PORT", port := os.environ.get("PORT", "80")) == f"ws://localhost:{port}/ws"):
            pass
        else:
            await self.ws_client.ws_loop()

    def load_cfg(self):

        self.config = load_config()

        try:
            with open("emojis.json") as f:
                self.emoji_data = json.load(f)
        except FileNotFoundError:
            pass
        except:
            traceback.print_exc()

        if not self.config["DEFAULT_PREFIX"]:
            self.config["DEFAULT_PREFIX"] = "!!"

    def setup(self):

        self.load_cfg()

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
            print(f"Baixando lista de servidores lavalink (arquivo: {ini_file})")
            r = requests.get(self.config["LAVALINK_SERVER_LIST"], allow_redirects=False)
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
                value["port"] = value["port"].replace("{SERVER_PORT}", os.environ.get("SERVER_PORT") or "8090")
                value["search"] = value.get("search") != "false"
                value["retry_403"] = value.get("retry_403") == "true"
                value["search_providers"] = value.get("search_providers", "").strip().split() or [self.config["DEFAULT_SEARCH_PROVIDER"]] + [s for s in ("ytsearch", "scsearch") if s != self.config["DEFAULT_SEARCH_PROVIDER"]]
                LAVALINK_SERVERS[key] = value

        start_local = None

        if os.environ.get("HOSTNAME", "").lower() == "squarecloud.app" and self.config.get("SQUARECLOUD_LAVALINK_AUTO_CONFIG", "").lower() != "false":
            for f in ("squarecloud.config", "squarecloud.app"):
                try:
                    square_cfg = dotenv_values(f"./{f}")
                except:
                    continue
                else:
                    try:
                        start_local = int(square_cfg["MEMORY"]) >= 490
                    except KeyError:
                        pass
                    else:
                        self.config["AUTO_DOWNLOAD_LAVALINK_SERVERLIST"] = not start_local
                        self.config['USE_YTDL'] = int(square_cfg["MEMORY"]) >= 512
                        self.config['USE_JABBA'] = False
                        if not square_cfg.get("SUBDOMAIN"):
                            self.config["RUN_RPC_SERVER"] = False
                        print("Usando a configuração automática na squarecloud\n"
                              f"Lavalink local: {start_local}\n"
                              f"YTDL: {self.config['USE_YTDL']}\n"
                              f"Memória: {square_cfg['MEMORY']}\n"
                              f"Run RPC Server: {self.config['RUN_RPC_SERVER']}\n"
                              f"Usando JABBA: {self.config['USE_JABBA']}")
                    break

        if start_local is None:

            if start_local := (self.config['RUN_LOCAL_LAVALINK'] is True or not LAVALINK_SERVERS):
                pass
            else:
                start_local = False

        intents = disnake.Intents(**{i[:-7].lower(): v for i, v in self.config.items() if i.lower().endswith("_intent")})
        intents.members = True
        intents.guilds = True

        mongo_key = self.config.get("MONGO")

        if mongo_key:
            self.mongo_database = MongoDatabase(mongo_key, timeout=self.config["MONGO_TIMEOUT"])
            print("Database em uso: MongoDB")
        else:
            print("Database em uso: TinyMongo | Nota: Os arquivos da database serão salvos localmente na pasta: local_database")

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
            self.remote_git_url = self.config["SOURCE_REPO"]

        prefix = get_prefix if intents.message_content else commands.when_mentioned

        self.ws_client = WSClient(self.config["RPC_SERVER"], pool=self)

        self.spotify: Optional[spotipy.Spotify] = spotify_client(self.config)

        all_tokens = {}

        for k, v in dict(os.environ, **self.config).items():

            if not isinstance(v, str):
                continue

            if not (tokens := token_regex.findall(v)):
                continue

            if len(tokens) > 1:
                counter = 1
                for t in tokens:

                    if t in all_tokens.values():
                        continue

                    all_tokens[f"{k}_{counter}"] = t
                    counter += 1

            elif (token := tokens.pop()) not in all_tokens.values():
                all_tokens[k] = token

        if self.config["INTERACTION_BOTS"]:
            interaction_bot_reg = None
        else:
            try:
                interaction_bot_reg = sorted(list(all_tokens), key=lambda i: i)[0]
            except:
                interaction_bot_reg = None

        def load_bot(bot_name: str, token: str):

            try:
                token = token.split().pop()
            except:
                pass

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
                default_prefix=self.config["DEFAULT_PREFIX"],
                pool=self,
                number=int(self.max_counter)
            )

            bot.http.token = token

            os.environ.update(
                {
                    "JISHAKU_HIDE": "true",
                    "JISHAKU_NO_DM_TRACEBACK": "true",
                    "JISHAKU_NO_UNDERSCORE": "true",
                }
            )

            bot.load_extension("jishaku")

            if bot.config['INTERACTION_COMMAND_ONLY']:

                @bot.check
                async def check_commands(ctx: CustomContext):

                    if not (await bot.is_owner(ctx.author)):
                        raise GenericError("**Os comandos de texto estão desativados!\n"
                                           "Use os comandos de barra /**", self_delete=True, delete_original=15)

                    return True

            if not bot.pool.single_bot:

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

            @bot.listen("on_resumed")
            async def clear_gc():

                if self.processing_gc:
                    return

                self.processing_gc = True
                await asyncio.sleep(2)
                gc.collect()
                self.processing_gc = False

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

            if self.config["COMMAND_LOG"]:

                @bot.listen("on_command")
                async def command_log(ctx: CustomContext):

                    if (await bot.is_owner(ctx.author)):
                        return

                    print(
                        f"cmd (prefix) log: [user: {ctx.author} - {ctx.author.id}] - [guild: {ctx.guild.name} - {ctx.guild.id}]"
                        f" - [cmd: {ctx.message.content}] {datetime.datetime.utcnow().strftime('%d/%m/%Y - %H:%M:%S')} (UTC)\n" + ("-" * 15)
                    )

            @bot.listen()
            async def on_ready():

                if not bot.bot_ready:

                    if bot.initializing:
                        return

                    bot.initializing = True

                    if str(bot.user.id) in bot.config["INTERACTION_BOTS_CONTROLLER"]:
                        self.bots.remove(bot)

                    try:
                        if str(bot.user.id) in bot.config["INTERACTION_BOTS"] or \
                                str(bot.user.id) in bot.config["INTERACTION_BOTS_CONTROLLER"] or \
                                interaction_bot_reg == bot.identifier:

                            bot.interaction_id = bot.user.id
                            self.controller_bot = bot

                            bot.load_modules()

                            if bot.config["AUTO_SYNC_COMMANDS"]:
                                await bot.sync_app_commands(force=True)

                        else:

                            self._command_sync_flags = commands.CommandSyncFlags.none()

                            if self.config["INTERACTION_BOTS"] and self.config["ADD_REGISTER_COMMAND"]:

                                @bot.slash_command(
                                    name=disnake.Localized("register_commands",data={disnake.Locale.pt_BR: "registrar_comandos"}),
                                    description="Use este comando caso meus outros comandos de barra (/) não estejam disponíveis..."
                                )
                                async def register_commands(
                                        inter: disnake.AppCmdInter,
                                ):
                                    interaction_invites = ""

                                    for b in self.bots:

                                        if not b.interaction_id:
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

                        music_cog = bot.get_cog("Music")

                        if music_cog:
                            bot.loop.create_task(music_cog.process_nodes(data=LAVALINK_SERVERS, start_local=self.config["CONNECT_LOCAL_LAVALINK"] and start_local))

                        bot.add_view(PanelView(bot))

                        self.bot_mentions.update((f"<@!{bot.user.id}>", f"<@{bot.user.id}>"))

                        bot.sync_command_cooldowns()

                    except Exception:
                        traceback.print_exc()

                    await bot.update_appinfo()

                    bot.bot_ready = True

                print(f'{bot.user} - [{bot.user.id}] Online.')

            self.bots.append(bot)

        if len(all_tokens) > 1:
            self.single_bot = False

        for k, v in all_tokens.items():
            load_bot(k, v)

        message = ""

        if not self.bots:

            os.system('cls' if os.name == 'nt' else 'clear')

            message = "O token do bot não foi configurado devidamente!\n\n"

            if os.environ.get("REPL_SLUG"):
                message += f"Confira se o token foi adicionado nas secrets da replit"

                print(message + ": Guia de como configurar: https://gist.github.com/zRitsu/70737984cbe163f890dae05a80a3ddbe#2---com-o-projeto-j%C3%A1-criado-prossiga-as-etapas-abaixo")

                message += f'. <a href="https://gist.github.com/zRitsu/70737984cbe163f890dae05a80a3ddbe#2---com-o-projeto-j%C3%A1-criado-prossiga-as-etapas-abaixo" target="_blank">Clique aqui</a> para ver o guia de como configurar.'

            else:
                message += "Confira se o token foi configurado na ENV/ENVIRONMENT ou no arquivo .env"

                print(message)

        loop = asyncio.get_event_loop()

        loop.create_task(self.load_playlist_cache())

        if start_local:
            loop.create_task(self.start_lavalink(loop=loop))

        if self.config["RUN_RPC_SERVER"]:

            if not message:

                for bot in self.bots:
                    loop.create_task(self.start_bot(bot))

                loop.create_task(self.connect_rpc_ws())

            try:
                start(self, message=message)
            except KeyboardInterrupt:
                return

        elif message:
            raise Exception(message)

        else:

            loop.create_task(self.connect_rpc_ws())
            try:
                loop.run_until_complete(
                    self.run_bots(self.bots)
                )
            except KeyboardInterrupt:
                return


class BotCore(commands.AutoShardedBot):

    def __init__(self, *args, **kwargs):
        self.session: Optional[aiohttp.ClientError] = None
        self.pool: BotPool = kwargs.pop('pool')
        self.default_prefix = kwargs.pop("default_prefix", "!!")
        self.spotify: Optional[spotipy.Spotify] = self.pool.spotify
        self.session = aiohttp.ClientSession()
        self.color = kwargs.pop("embed_color", None)
        self.identifier = kwargs.pop("identifier", "")
        self.appinfo: Optional[disnake.AppInfo] = None
        self.bot_ready = False
        self.initializing = False
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
        self.interaction_id: Optional[int] = None

        for i in self.config["OWNER_IDS"].split("||"):

            if not i:
                continue

            try:
                self.env_owner_ids.add(int(i))
            except ValueError:
                print(f"Owner_ID inválido: {i}")

    async def edit_voice_channel_status(
            self, status: Optional[str], *, channel_id: int, reason: Optional[str] = None
    ):
        # Obtido do discord.py: https://github.com/Rapptz/discord.py/blob/9ce733321b445db245924bfd21fedf20a01a570b/discord/http.py#L1166
        r = Route('PUT', '/channels/{channel_id}/voice-status', channel_id=channel_id)
        payload = {'status': status}
        return await self.http.request(r, reason=reason, json=payload)

    def load_skins(self):

        for skin in os.listdir("./utils/music/skins/normal_player"):
            if not skin.endswith(".py"):
                continue

            skin = skin[:-3]

            if skin in self.config["IGNORE_SKINS"].split() and skin != "default":
                print(f"{self.user} | Skin {skin}.py ignorada")
                continue

            try:
                skin_file = import_module(f"utils.music.skins.normal_player.{skin}")
                if not hasattr(skin_file, "load"):
                    print(f"Skin ignorada: {skin}.py | Função load() não configurada/encontrada...")
                    continue
                self.player_skins[skin] = skin_file.load()
            except Exception:
                print(f"Falha ao carregar skin [normal_player]: {traceback.format_exc()}")
        if self.default_skin not in self.player_skins:
            self.default_skin = "default"

        for skin in os.listdir("./utils/music/skins/static_player"):
            if not skin.endswith(".py"):
                continue

            skin = skin[:-3]

            if skin in self.config["IGNORE_STATIC_SKINS"].split() and skin != "default":
                print(f"{self.user} | Skin {skin}.py ignorada")
                continue

            try:
                skin_file = import_module(f"utils.music.skins.static_player.{skin}")
                if not hasattr(skin_file, "load"):
                    print(f"Skin ignorada: {skin}.py | Função load() não configurada/encontrada...")
                    continue
                self.player_static_skins[skin] = skin_file.load()
            except Exception:
                print(f"Falha ao carregar skin [static_player]: {traceback.format_exc()}")
        if self.default_static_skin not in self.player_static_skins:
            self.default_static_skin = "default"

    @property
    def config(self):
        return self.pool.config

    @property
    def emoji_data(self):
        return self.pool.emoji_data

    @property
    def ws_client(self):
        return self.pool.ws_client

    async def get_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.get_data(
            id_=id_, db_name=db_name, collection=str(self.user.id)
        )

    async def update_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users]):
        return await self.pool.database.update_data(
            id_=id_, data=data, db_name=db_name, collection=str(self.user.id)
        )

    async def get_global_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users]):

        data = await self.pool.database.get_data(
            id_=id_, db_name=db_name, collection="global", default_model=global_db_models
        )

        if db_name == DBModel.users:
            try:
                self.pool.rpc_token_cache[int(id_)] = data["token"]
            except KeyError:
                pass

        return data

    async def update_global_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users]):

        if db_name == DBModel.users:
            try:
                self.pool.rpc_token_cache[int(id_)] = data["token"]
            except KeyError:
                pass

        return await self.pool.database.update_data(
            id_=id_, data=data, db_name=db_name, collection="global", default_model=global_db_models
        )

    def check_skin(self, skin: str):

        if skin is None:
            return self.default_skin

        if skin.startswith("> custom_skin: "):
            return skin

        if skin not in self.player_skins:
            return self.default_skin

        return skin

    def check_static_skin(self, skin: str):

        if skin is None:
            return self.default_static_skin

        if skin.startswith("> custom_skin: "):
            return skin

        if skin is None or skin not in self.player_static_skins:
            return self.default_static_skin

        return skin

    async def is_owner(self, user: Union[disnake.User, disnake.Member]) -> bool:

        if user.id in self.env_owner_ids:
            return True

        return await super().is_owner(user)

    async def sync_app_commands(self, force=False):

        await self.wait_until_ready()

        if not self.command_sync_flags.sync_commands and not force:
            return

        current_cmds = sorted([sort_dict_recursively(cmd.body.to_dict()) for cmd in self.application_commands], key=lambda k: k["name"])

        try:
            with open(f"./.app_commands_sync_data/{self.user.id}.pkl", "rb") as f:
                synced_cmds = pickle.load(f)
        except FileNotFoundError:
            synced_cmds = None

        if current_cmds == synced_cmds:
            if current_cmds:
                print(f"{self.user} - Os comandos já estão sincronizados.")
            return

        self._command_sync_flags = self.pool.command_sync_config
        await self._sync_application_commands()
        self._command_sync_flags = commands.CommandSyncFlags.none()

        try:
            if not os.path.isdir("./.app_commands_sync_data/"):
                os.makedirs("./.app_commands_sync_data/")

            with open(f"./.app_commands_sync_data/{self.user.id}.pkl", "wb") as f:
                pickle.dump(current_cmds, f)
        except:
            traceback.print_exc()

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
                c.body.dm_permission = False
                if c.extras.get("exclusive_cooldown"): continue
                c._buckets = cmd._buckets

            for cmd in b.user_commands:
                c = self.get_user_command(cmd.name)
                if not c: continue
                c.body.dm_permission = False
                if c.extras.get("exclusive_cooldown"): continue
                c._buckets = cmd._buckets

            for cmd in b.message_commands:
                c = self.get_message_command(cmd.name)
                if not c: continue
                c.body.dm_permission = False
                if c.extras.get("exclusive_cooldown"): continue
                c._buckets = cmd._buckets

    async def can_send_message(self, message: disnake.Message):

        if isinstance(message.channel, disnake.Thread):
            perm_check = message.channel.parent.permissions_for(message.guild.me).send_messages_in_threads
        else:
            perm_check = message.channel.permissions_for(message.guild.me).send_messages

        if not perm_check:
            print(f"Can't send message in: {message.channel.name} [{message.channel.id}] (Missing permissions)")
            return

        return True

    async def on_message(self, message: disnake.Message):

        if not self.bot_ready or not self.appinfo or self.is_closed():
            return

        if not message.guild:
            return

        try:
            player: LavalinkPlayer = self.music.players[message.guild.id]
            if player.text_channel == message.channel and not message.flags.ephemeral:
                player.last_message_id = message.id
        except (KeyError, AttributeError):
            pass

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

            prefix = (await self.get_prefix(message))

            if not isinstance(prefix, str):
                prefix = prefix[-1]

            embed.description = f"**Olá {message.author.mention}.**"

            if not self.config["INTERACTION_COMMAND_ONLY"]:
                embed.description += f"\n\nMeu prefixo no servidor é: **{prefix}** `(minha menção também funciona como prefixo).`\n"\
                                    f"Pra ver todos os meus comandos use **{prefix}help**"

            bot_count = 0

            if not self.command_sync_flags.sync_commands and self.config["INTERACTION_BOTS"]:

                interaction_invites = []

                for b in self.pool.bots:

                    if not b.interaction_id:
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

                else:
                    embed.description += "\n\n**Pra ver todos os meus comandos use: /**"

            else:
                embed.description += "\n\n**Pra ver todos os meus comandos use: /**"

            if bot_count:

                if message.author.guild and message.author.guild_permissions.manage_guild:
                    embed.description += "\n\n`Caso precise de mais bots de música neste servidor ou queira adicionar bots " \
                                         "de música em outro servidor, clique no botão abaixo.`"

                kwargs = {
                    "components": [
                        disnake.ui.Button(
                            custom_id="bot_invite",
                            label="Me adicione no seu servidor."
                        )
                    ]
                }

            else:
                kwargs = {
                    "components": [
                        disnake.ui.Button(
                            label="Me adicione no seu servidor.",
                            url=disnake.utils.oauth_url(self.user.id, permissions=disnake.Permissions(self.config['INVITE_PERMISSIONS']), scopes=('bot', 'applications.commands'))
                        )
                    ]
                }

            if message.channel.permissions_for(message.guild.me).read_message_history:
                await message.reply(embed=embed, fail_if_not_exists=False, **kwargs)
            else:
                await message.channel.send(message.author.mention, embed=embed, **kwargs)
            return

        ctx: CustomContext = await self.get_context(message, cls=CustomContext)

        try:
            ctx.player = self.music.players[message.guild.id]
        except:
            pass

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
            return self.color or 0x2b2d31

        if self.color:
            return self.color

        if me.color.value == 0:
            return 0x2b2d31

        return me.color

    async def update_appinfo(self):

        await self.wait_until_ready()

        self.appinfo = await self.application_info()

        try:
            self.owner = self.appinfo.team.owner
            owners =self.appinfo.team.members
        except AttributeError:
            self.owner = self.appinfo.owner
            owners = [self.appinfo.owner]

        if self.appinfo.bot_public and not self.config.get("SILENT_PUBLICBOT_WARNING"):

            def check_member(u: disnake.User, g: disnake.Guild):
                member = g.get_member(u.id)
                return member and member.guild_permissions.manage_guild

            guilds = set()
            for guild in self.guilds:
                if not [dev for dev in owners if check_member(dev, guild)]:
                    guilds.add(guild)

            warn_msg = f"Atenção: O bot [{self.user}] (ID: {self.user.id}) foi configurado no portal do desenvolvedor " \
                  "como bot público\n" \
                  "lembrando que se caso o bot seja divulgado pra ser adicionado publicamente o mesmo terá que " \
                  "estar sob as condições da licença GPL-2: " \
                  "https://github.com/zRitsu/MuseHeart-MusicBot/blob/main/LICENSE\n" \
                  "Caso não queira seguir as condições da licença no seu bot, você pode deixar o bot privado desmarcando a " \
                  f"opção public bot acessando o link: https://discord.com/developers/applications/{self.user.id}/bot"

            if guilds:
                warn_msg += "\n\nAtualmente o bot se encontra em servidores no qual o dono do bot (ou membro da equipe) não "\
                            f"estão ou que não possuem permissão de gerenciar servidor pra adicionar o próprio bot " \
                             f"[{self.user}] nos servidores abaixo:\n\n" + "\n".join(f"{g.name} [ID: {g.id}]" for g in list(guilds)[:10])

                if (gcount:=len(guilds)) > 10:
                    warn_msg += F"\ne em mais {gcount-10} servidor(es)."

            print(("="*50) + f"\n{warn_msg}\n" + ("="*50))

    async def on_application_command_autocomplete(self, inter: disnake.ApplicationCommandInteraction):

        if not self.bot_ready or self.is_closed():
            return []

        if not inter.guild_id:
            return []

        await super().on_application_command_autocomplete(inter)

    async def on_application_command(self, inter: disnake.ApplicationCommandInteraction):

        if not inter.guild_id:
            await inter.send("Meus comandos não podem ser usados no DM.\n"
                             "Use em algum servidor que estou presente.")
            return

        if not self.bot_ready or self.is_closed():
            await inter.send("Ainda estou inicializando...\nPor favor aguarde mais um pouco...", ephemeral=True)
            return

        if self.config["COMMAND_LOG"] and inter.guild and not (await self.is_owner(inter.author)):
            try:
                print(f"cmd log: [user: {inter.author} - {inter.author.id}] - [guild: {inter.guild.name} - {inter.guild.id}]"
                      f" - [cmd: {inter.data.name}] {datetime.datetime.utcnow().strftime('%d/%m/%Y - %H:%M:%S')} (UTC) - {inter.filled_options}\n" + ("-" * 15))
            except:
                traceback.print_exc()

        if str(self.user.id) in self.config["INTERACTION_BOTS_CONTROLLER"]:

            available_bot = False

            for bot in self.pool.bots:
                if bot.appinfo and (bot.appinfo.bot_public or await bot.is_owner(inter.author)) and bot.get_guild(inter.guild_id):
                    available_bot = True
                    break

            if not available_bot:
                await inter.send("**Não há bots disponíveis no servidor, Adicione pelo menos um clicando no botão abaixo.**",
                                 ephemeral=True, components=[disnake.ui.Button(custom_id="bot_invite", label="Adicionar bots")])
                return

        await super().on_application_command(inter)

    def load_modules(self, module_list: list = None):

        modules_dir = "modules"

        load_status = {
            "reloaded": [],
            "loaded": []
        }

        bot_name = self.user or self.identifier

        for item in os.walk(modules_dir):
            files = filter(lambda f: f.endswith('.py'), item[-1])
            for file in files:
                if module_list and file not in module_list:
                    continue
                filename, _ = os.path.splitext(file)
                module_filename = os.path.join(modules_dir, filename).replace('\\', '.').replace('/', '.')
                try:
                    self.reload_extension(module_filename)
                    if self.pool.controller_bot == self and not self.bot_ready:
                        print(f"{'=' * 48}\n[OK] {bot_name} - {filename}.py Recarregado.")
                    load_status["reloaded"].append(f"{filename}.py")
                except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
                    try:
                        self.load_extension(module_filename)
                        if self.pool.controller_bot == self and not self.bot_ready:
                            print(f"{'=' * 48}\n[OK] {bot_name} - {filename}.py Carregado.")
                        load_status["loaded"].append(f"{filename}.py")
                    except Exception as e:
                        if self.pool.controller_bot == self and not self.bot_ready:
                            print(f"{'=' * 48}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename}")
                            raise e
                        return load_status
                except Exception as e:
                    if self.pool.controller_bot == self and not self.bot_ready:
                        print(f"{'=' * 48}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename}")
                        raise e
                    return load_status

        if self.pool.controller_bot == self and not self.bot_ready:
            print(f"{'=' * 48}")

        if not self.config["ENABLE_DISCORD_URLS_PLAYBACK"]:
            self.remove_slash_command("play_music_file")

        for c in self.slash_commands:
            if (desc:=len(c.description)) > 100:
                raise Exception(f"A descrição do comando {c.name} excedeu a quantidade de caracteres permitido "
                                f"no discord (100), quantidade atual: {desc}")

        return load_status