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

try:
    if os.environ["IS_SOURCE"]: # impedir o uso do botão run na replit direto da source pra fork.
        raise Exception("Este código não pode ser executado a partir do botão \"run\".")
except KeyError:
    pass

load_dotenv()

try:
    with open('config.json', encoding='utf-8') as f:
        config = load(f)
except FileNotFoundError:
    config = {}

yt_dlp_mode = os.environ.get("YOUTUBEDL")

if yt_dlp_mode is True or yt_dlp_mode == "true":
    config["youtubedl"] = True

ad_link = os.environ.get("LINK")

if ad_link is False or ad_link == "false":
    config["link"] = ""

if not config.get('youtubedl') and config['lavalink']['local']['start_local_lavalink']:
    run_lavalink(
        lavalink_file_url=config['lavalink']['local']['lavalink_file_url'],
        lavalink_ram_limit=config['lavalink']['local']['lavalink_ram_limit'],
        lavalink_additional_sleep=config['lavalink']['local']['lavalink_additional_sleep'],
    )

intents = disnake.Intents.default()
intents.members = True
intents.presences = True

mongo_key = os.environ.get("MONGO")

if not mongo_key:
    print(f"Token do mongoDB não configurado! será usado um arquivo json para database.\n{'-'*30}")

bots = []

def load_bot(token: str):

    bot = BotCore(
        command_prefix=commands.when_mentioned,
        case_insensitive=True,
        intents=intents,
        test_guilds=[],
        sync_commands=False,
        sync_commands_on_cog_unload=False,
        config=config,
        db_name="botdiscord",
        color=os.environ.get("EMBED_COLOR")
    )

    bot.token = token

    @bot.listen()
    async def on_ready():
        print(f'{bot.user} [{bot.user.id}] Online.')

        if not bot.bot_ready:
            bot.load_modules()
            mongo = mongo_key
            bot.db = Database(token=mongo, name=str(bot.user.id)) if mongo else LocalDatabase(bot)
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
