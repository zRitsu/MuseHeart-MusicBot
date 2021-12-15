import asyncio
import disnake
from disnake.ext import commands
import os
from dotenv import load_dotenv
from json import load
from utils.music.local_lavalink import run_lavalink
from utils.client import BotCore
from utils.db import Database, LocalDatabase
from web_app import run_app

CONFIGS = {
    "VOTE_SKIP_AMOUNT": "3",
    "DEFAULT_PREFIX": "!!!",
    "LINK": "[`Crie seu próprio bot de música`](https://www.youtube.com/watch?v=zTXF4QA05Ic)",
    "YOUTUBEDL": "true",

    # Local lavalink stuffs
    "START_LOCAL_LAVALINK": "true",
    "LAVALINK_ADDITIONAL_SLEEP": "0",
    "LAVALINK_RAM_LIMIT": "120",
    "LAVALINK_CPU_CORES": "2",
    "LAVALINK_FILE_URL": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/Lavalink.jar"
}

load_dotenv()

for cfg in CONFIGS:
    try:
        CONFIGS[cfg] = os.environ[cfg]
    except KeyError:
        continue

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

bots = []

def load_bot(token: str):

    try:
        token, prefix = token.split()[:2]
        prefix = commands.when_mentioned_or(prefix)
    except:
        if token == os.environ["TOKEN"]:
            prefix = commands.when_mentioned_or(os.environ.get("DEFAULT_PREFIX", "!!!"))
        else:
            prefix = commands.when_mentioned

    bot = BotCore(
        command_prefix=prefix,
        case_insensitive=True,
        intents=intents,
        #test_guilds=[],
        sync_commands=False,
        config=CONFIGS,
        color=os.environ.get("EMBED_COLOR")
    )

    bot.token = token

    @bot.listen()
    async def on_ready():
        print(f'{bot.user} [{bot.user.id}] Online.')

        if not bot.bot_ready:
            bot.load_modules()
            mongo = mongo_key

            bot.db = Database(token=mongo, name=str(bot.user.id)) if mongo \
                else LocalDatabase(bot, rename_db=token == os.environ["TOKEN"] and os.path.isfile("./database.json"))
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

loop.run_until_complete(start_bots())
