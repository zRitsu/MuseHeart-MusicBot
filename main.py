import asyncio
import json
import subprocess

import disnake
from disnake.ext import commands
import os
from dotenv import load_dotenv
from utils.music.local_lavalink import run_lavalink
from utils.client import BotCore
from utils.db import Database, LocalDatabase
from web_app import run_app, run_ws_client

CONFIGS = {
    "VOTE_SKIP_AMOUNT": "3",
    "DEFAULT_PREFIX": "!!!",
    "YOUTUBEDL": "false",
    "DEFAULT_SKIN": "default",
    "IDLE_TIMEOUT": "180",
    "RPC_SERVER": "http://localhost:8080/ws",

    # Local lavalink stuffs
    "START_LOCAL_LAVALINK": "true",
    "LAVALINK_ADDITIONAL_SLEEP": "0",
    "LAVALINK_RAM_LIMIT": "120",
    "LAVALINK_CPU_CORES": "2",
    "LAVALINK_FILE_URL": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/Lavalink.jar"
}

try:
    with open("config.json") as f:
        CONFIGS.update(json.load(f))
except FileNotFoundError:
    pass

load_dotenv()

for cfg in CONFIGS:
    try:
        CONFIGS[cfg] = os.environ[cfg]
    except KeyError:
        continue

CONFIGS["IDLE_TIMEOUT"] = int(CONFIGS["IDLE_TIMEOUT"])

if CONFIGS["IDLE_TIMEOUT"] < 30:
    CONFIGS["IDLE_TIMEOUT"] = 30

if CONFIGS.get('YOUTUBEDL') != "true" and CONFIGS['START_LOCAL_LAVALINK'] == "true":
    run_lavalink(
        lavalink_file_url=CONFIGS['LAVALINK_FILE_URL'],
        lavalink_ram_limit=CONFIGS['LAVALINK_RAM_LIMIT'],
        lavalink_additional_sleep=int(CONFIGS['LAVALINK_ADDITIONAL_SLEEP']),
    )

intents = disnake.Intents.default()
intents.members = True
intents.presences = True

mongo_key = os.environ.get("MONGO")

if not mongo_key:
    print(f"Token do mongoDB não configurado! será usado um arquivo json para database.\n{'-'*30}")

try:
    commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    print(f"Commit ver: {commit}\n{'-'*30}")
except:
    commit = None

print(f"Modo do player: {'Lavalink' if CONFIGS['YOUTUBEDL'] != 'true' else 'YT-DLP'}\n{'-'*30}")

bots = []

def load_bot(token: str):

    try:
        token, default_prefix = token.split()[:2]
        prefix = commands.when_mentioned_or(default_prefix)
    except:
        if token == os.environ["TOKEN"]:
            default_prefix = os.environ.get("DEFAULT_PREFIX", "!!!")
            prefix = commands.when_mentioned_or(default_prefix)
        else:
            prefix = commands.when_mentioned
            default_prefix = None

    bot = BotCore(
        command_prefix=prefix,
        case_insensitive=True,
        intents=intents,
        #test_guilds=[],
        sync_commands=False,
        config=CONFIGS,
        color=os.environ.get("EMBED_COLOR"),
        commit=commit,
        default_prefix=default_prefix,
    )

    bot.token = token

    bot.load_extension('jishaku')
    bot.get_command("jsk").hidden = True

    @bot.listen()
    async def on_ready():
        print(f'{bot.user} [{bot.user.id}] Online.')

        if not bot.bot_ready:

            if not bot.owner:
                botowner = (await bot.application_info())
                try:
                    bot.owner = botowner.team.members[0]
                except AttributeError:
                    bot.owner = botowner.owner

            bot.load_modules()
            mongo = mongo_key

            bot.db = Database(token=mongo, name=str(bot.user.id)) if mongo \
                else LocalDatabase(bot, rename_db=token == os.environ["TOKEN"] and os.path.isfile("./database.json"))

            if bot.ws_client and bot.ws_client.is_connected:
                await bot.ws_client.send({"user_id": bot.user.id, "bot": True})

            bot.bot_ready = True

    bots.append(bot)

for t in [os.environ["TOKEN"]] + [v for k, v in os.environ.items() if k.lower().startswith("token_bot_")]:
    load_bot(t)

async def start_bots():

    await asyncio.wait(
        [asyncio.create_task(bot.start(bot.token)) for bot in bots]
    )

if os.getenv('KEEP_ALIVE') != "false":
    run_app(bots)

loop = asyncio.get_event_loop()

loop.create_task(run_ws_client(CONFIGS["RPC_SERVER"], bots))

loop.run_until_complete(start_bots())
