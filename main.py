import json
import os.path
import traceback
import disnake
import requests
from disnake.ext import commands
import asyncio
from subprocess import check_output
from os import path
from utils.music.errors import GenericError
from utils.music.local_lavalink import run_lavalink
from utils.client import BotCore
from utils.db import MongoDatabase, LocalDatabase, guild_prefix
from utils.music.spotify import spotify_client
from utils.owner_panel import PanelView
from web_app import start
from config_loader import load_config
from configparser import ConfigParser
import logging

CONFIGS = load_config()

if not CONFIGS["DEFAULT_PREFIX"]:
    CONFIGS["DEFAULT_PREFIX"] = "!!!"

if CONFIGS['ENABLE_LOGGER']:

    if not path.isdir("./.logs"):
        os.makedirs("./.logs")

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(filename='./.logs/disnake.log', encoding='utf-8', mode='w')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    logger.addHandler(handler)

LAVALINK_SERVERS = {}


if CONFIGS["AUTO_DOWNLOAD_LAVALINK_SERVERLIST"]:
    print("Baixando lista de servidores lavalink (arquivo: lavalink.ini)")
    r = requests.get(CONFIGS["LAVALINK_SERVER_LIST"], allow_redirects=True)
    with open("lavalink.ini", 'wb') as f:
        f.write(r.content)
    r.close()

for key, value in CONFIGS.items():

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

if start_local := (CONFIGS['RUN_LOCAL_LAVALINK'] is True or not LAVALINK_SERVERS):
    run_lavalink(
        lavalink_file_url=CONFIGS['LAVALINK_FILE_URL'],
        lavalink_initial_ram=CONFIGS['LAVALINK_INITIAL_RAM'],
        lavalink_ram_limit=CONFIGS['LAVALINK_RAM_LIMIT'],
        lavalink_additional_sleep=int(CONFIGS['LAVALINK_ADDITIONAL_SLEEP']),
    )

intents = disnake.Intents(**{i[:-7].lower(): v for i, v in CONFIGS.items() if i.lower().endswith("_intent")})

mongo_key = CONFIGS.get("MONGO")

if not mongo_key:
    print(f"Token do mongoDB não configurado! será usado um arquivo json para database.\n{'-' * 30}")

spotify = spotify_client(CONFIGS)

try:
    commit = check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    print(f"Commit ver: {commit}\n{'-' * 30}")
except:
    commit = None

try:
    remote_git_url = check_output(['git', 'remote', '-v']).decode(
        'ascii').strip().split("\n")[0][7:].replace(".git (fetch)", "")
except:
    remote_git_url = ""

bots = []

prefix = guild_prefix if intents.message_content else commands.when_mentioned


def load_bot(bot_name: str, token: str, main=False):
    try:
        token, default_prefix = token.split()
    except:
        default_prefix = CONFIGS["DEFAULT_PREFIX"]

    try:
        test_guilds = list([int(i) for i in CONFIGS[f"TEST_GUILDS_{bot_name}"].split("||")])
    except:
        test_guilds = None

    bot = BotCore(
        command_prefix=prefix,
        case_insensitive=True,
        intents=intents,
        test_guilds=test_guilds,
        sync_commands=CONFIGS["AUTO_SYNC_COMMANDS"] is True,
        sync_commands_debug=True,
        config=CONFIGS,
        color=CONFIGS["EMBED_COLOR"],
        commit=commit,
        spotify=spotify,
        remote_git_url=remote_git_url,
        default_prefix=default_prefix,
    )

    bot.token = token

    bot.load_modules(bot_name)

    if bot.config['INTERACTION_COMMAND_ONLY']:

        @bot.check
        async def check_commands(ctx: commands.Context):

            if not (await bot.is_owner(ctx.author)):
                raise GenericError("**Os comandos de texto estão desativados!\n"
                                   "Use os comandos de barra /**")

            return True


    @bot.listen()
    async def on_ready():

        if not bot.bot_ready:

            if not bot.owner:
                botowner = (await bot.application_info())
                try:
                    bot.owner = botowner.team.members[0]
                except AttributeError:
                    bot.owner = botowner.owner

            bot.db = MongoDatabase(bot=bot, token=mongo_key, name=str(bot.user.id)) if mongo_key \
                else LocalDatabase(bot, rename_db=main and path.isfile("./database.json"))

            music_cog = bot.get_cog("Music")

            if music_cog:
                bot.loop.create_task(music_cog.process_nodes(data=LAVALINK_SERVERS, start_local=start_local))

            if spotify:
                try:
                    await bot.spotify.authorize()
                except Exception:
                    traceback.print_exc()

            bot.add_view(PanelView(bot))

            if not CONFIGS["RUN_RPC_SERVER"] and (not CONFIGS["RPC_SERVER"] or CONFIGS["RPC_SERVER"] == "ws://localhost:8080/ws"):
                pass
            else:
                bot.loop.create_task(bot.ws_client.ws_loop())

            bot.bot_ready = True

        print(f'{bot.user} - [{bot.user.id}] Online.')

    bots.append(bot)


main_token = CONFIGS.get("TOKEN")

if main_token:
    load_bot("Main Bot", main_token, main=True)

for k, v in CONFIGS.items():

    if not k.lower().startswith("token_bot_"):
        continue

    bot_name = k[10:] or "Sec. Bot"

    load_bot(bot_name, v)

if not bots:
    raise Exception("O token do bot não foi configurado devidamente!")


async def start_bots():
    await asyncio.wait(
        [asyncio.create_task(bot.start(bot.token)) for bot in bots]
    )


loop = asyncio.get_event_loop()

if CONFIGS["RUN_RPC_SERVER"]:

    for bot in bots:
        loop.create_task(bot.start(bot.token))

    start(bots)

else:

    loop.run_until_complete(start_bots())
