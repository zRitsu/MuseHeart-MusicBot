import asyncio
from subprocess import check_output
import disnake
from os import path
from utils.music.local_lavalink import run_lavalink
from utils.client import BotCore
from utils.db import MongoDatabase, LocalDatabase, guild_prefix
from utils.music.spotify import spotify_client
from web_app import run_app
from config_loader import load_config

CONFIGS = load_config()

if not CONFIGS["DEFAULT_PREFIX"]:
    CONFIGS["DEFAULT_PREFIX"] = "!!!"


if CONFIGS['START_LOCAL_LAVALINK'] == "true":
    run_lavalink(
        lavalink_file_url=CONFIGS['LAVALINK_FILE_URL'],
        lavalink_initial_ram=CONFIGS['LAVALINK_INITIAL_RAM'],
        lavalink_ram_limit=CONFIGS['LAVALINK_RAM_LIMIT'],
        lavalink_additional_sleep=int(CONFIGS['LAVALINK_ADDITIONAL_SLEEP']),
    )

intents = disnake.Intents.all()

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


def load_bot(bot_name: str, token: str, main=False):
    try:
        token, default_prefix = token.split()
    except:
        default_prefix = CONFIGS["DEFAULT_PREFIX"]

    bot = BotCore(
        command_prefix=guild_prefix,
        case_insensitive=True,
        intents=intents,
        # test_guilds=[],
        sync_commands=True,
        sync_commands_debug=True,
        config=CONFIGS,
        color=CONFIGS["EMBED_COLOR"],
        commit=commit,
        spotify=spotify,
        remote_git_url=remote_git_url,
        default_prefix=default_prefix,
    )

    bot.token = token

    bot.load_extension('jishaku')
    bot.get_command("jsk").hidden = True
    bot.load_modules(bot_name)

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

            bot.db = MongoDatabase(bot=bot, token=mongo_key, name=str(bot.user.id)) if mongo_key \
                else LocalDatabase(bot, rename_db=main and path.isfile("./database.json"))

            bot.loop.create_task(bot.ws_client.ws_loop())

            bot.bot_ready = True

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


run_app()

loop = asyncio.get_event_loop()

loop.run_until_complete(start_bots())