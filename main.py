import disnake
from disnake.ext import commands
import os
from dotenv import load_dotenv
from keep_alive import keep_alive
from json import load
from utils.music.local_lavalink import run_lavalink
from utils.client import BotCore

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

if os.getenv('KEEP_ALIVE') != "false":
    keep_alive()

intents = disnake.Intents.default()
intents.members = True
intents.presences = True

mongo_key = os.environ.get("MONGO")

if not mongo_key:
    print("Token do mongoDB não configurado! será usado o arquivo database.json.")


bot = BotCore(
    command_prefix=commands.when_mentioned_or(os.environ.get('DEFAULT_PREFIX'), '!!!'),
    case_insensitive=True,
    intents=intents,
    test_guilds=[],
    sync_commands=False,
    sync_commands_on_cog_unload=False,
    config=config,
    db_name="botdiscord",
    mongo=mongo_key
)


@bot.event
async def on_ready():
    print(f'{bot.user} [{bot.user.id}] Online.')


bot.load_modules()

bot.run(os.environ['TOKEN'])
