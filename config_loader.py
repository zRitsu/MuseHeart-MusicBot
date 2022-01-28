import json
from json import load
from dotenv import dotenv_values
from os import environ

def load_config():

    CONFIGS = {
        "VOTE_SKIP_AMOUNT": "3",
        "DEFAULT_PREFIX": "!!!",
        "DEFAULT_SKIN": "default",
        "IDLE_TIMEOUT": "180",
        "RPC_SERVER": "ws://localhost:8080/ws",
        "EMBED_COLOR": None,
        "SPOTIFY_CLIENT_ID": None,
        "SPOTIFY_CLIENT_SECRET": None,
        "SOURCE_REPO": "https://github.com/zRitsu/disnake-LL-music-bot.git",

        # Local lavalink stuffs
        "START_LOCAL_LAVALINK": "true",
        "LAVALINK_ADDITIONAL_SLEEP": "0",
        "LAVALINK_INITIAL_RAM": "30",
        "LAVALINK_RAM_LIMIT": "120",
        "LAVALINK_CPU_CORES": "2",
        "LAVALINK_FILE_URL": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/Lavalink.jar"
    }

    for cfg in list(CONFIGS) + ["TOKEN", "MONGO"]:
        try:
            CONFIGS[cfg] = environ[cfg]
        except KeyError:
            continue

    for env in environ:
        if env.lower().startswith("token_bot_"):
            CONFIGS[env] = environ[env]

    try:
        with open("config.json") as f:
            CONFIGS.update(load(f))
    except FileNotFoundError:
        pass

    try:
        CONFIGS.update(dotenv_values())
    except:
        pass

    CONFIGS["IDLE_TIMEOUT"] = int(CONFIGS["IDLE_TIMEOUT"])

    if CONFIGS["EMBED_COLOR"] in ["false", "none"]:
        CONFIGS["EMBED_COLOR"] = None

    if CONFIGS["IDLE_TIMEOUT"] < 30:
        CONFIGS["IDLE_TIMEOUT"] = 30

    return CONFIGS
