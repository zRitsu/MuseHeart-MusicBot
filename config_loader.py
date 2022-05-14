from json import load
from dotenv import dotenv_values
from os import environ


bools = {
    "true": True,
    "false": False,
    "none": None
}


def load_config():

    CONFIGS = {
        "VOTE_SKIP_AMOUNT": 3,
        "DEFAULT_PREFIX": "!!!",
        "DEFAULT_SKIN": "default",
        "AUTO_SYNC_COMMANDS": True,
        "OWNER_IDS": "",
        "INTENTS": "",
        "DISABLE_INTENTS": "",
        "IDLE_TIMEOUT": 180,
        "COMMAND_LOG": False,
        "RUN_RPC_SERVER": True,
        "RPC_SERVER": "ws://localhost:$PORT/ws",
        "EMBED_COLOR": None,
        "MAX_USER_FAVS": 10,
        "USER_FAV_MAX_NAME_LENGTH": 35,
        "USER_FAV_MAX_URL_LENGTH": 90,
        "BOT_ADD_REMOVE_LOG": '',
        "ERROR_REPORT_WEBHOOK": '',
        "PLAYER_MESSAGE_UPDATE_INTERVAL": 15,
        "SPOTIFY_CLIENT_ID": '',
        "SPOTIFY_CLIENT_SECRET": '',
        "INTERACTION_COMMAND_ONLY": False,
        "PRESENCE_INTERVAL": 900,
        "SOURCE_REPO": "https://github.com/zRitsu/disnake-LL-music-bot.git",
        "HIDE_SOURCE_OWNER": False,
        "SUPPORT_SERVER": "",
        "YTDLMODE": False,

        ##########################
        ##### Bot presences: #####
        ##########################

        "LISTENING_PRESENCES": "",
        "WATCHING_PRESENCES": "",
        "PLAYING_PRESENCES": "",

        ##############################
        ### Local lavalink stuffs: ###
        ##############################

        "START_LOCAL_LAVALINK": True,
        "LAVALINK_ADDITIONAL_SLEEP": 0,
        "LAVALINK_INITIAL_RAM": 30,
        "LAVALINK_RAM_LIMIT": 120,
        "LAVALINK_CPU_CORES": 2,
        "LAVALINK_FILE_URL": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/Lavalink.jar"
    }

    for cfg in list(CONFIGS) + ["TOKEN", "MONGO"]:
        try:
            CONFIGS[cfg] = environ[cfg]
        except KeyError:
            continue

    for env in environ:
        if env.lower().startswith("token_bot_") or \
                env.lower().startswith("lavalink_node_") or \
                env.lower().startswith("test_guilds_"):
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

    if CONFIGS["EMBED_COLOR"] is False:
        CONFIGS["EMBED_COLOR"] = None


    # converter strings que requer número int.
    for i in [
        "MAX_USER_FAVS",
        "IDLE_TIMEOUT",
        "VOTE_SKIP_AMOUNT",
        "LAVALINK_ADDITIONAL_SLEEP",
        "LAVALINK_INITIAL_RAM",
        "LAVALINK_RAM_LIMIT",
        "LAVALINK_CPU_CORES",
        "USER_FAV_MAX_NAME_LENGTH",
        "USER_FAV_MAX_URL_LENGTH",
        "PLAYER_MESSAGE_UPDATE_INTERVAL",
        "PRESENCE_INTERVAL"
    ]:
        try:
            CONFIGS[i] = int(CONFIGS[i])
        except ValueError:
            raise Exception(f"Você usou uma configuração inválida! {i}: {CONFIGS[i]}")


    # converter strings que requer valor bool/nulo.
    for i in [
        "AUTO_SYNC_COMMANDS",
        "EMBED_COLOR",
        "HIDE_SOURCE_OWNER",
        "INTERACTION_COMMAND_ONLY",
        "START_LOCAL_LAVALINK",
        "COMMAND_LOG",
        "YTDLMODE"

    ]:
        if CONFIGS[i] in (True, False, None):
            continue

        try:
            CONFIGS[i] = bools[CONFIGS[i]]
        except KeyError:
            raise Exception(f"Você usou uma configuração inválida! {i}: {CONFIGS[i]}")

    CONFIGS["RPC_SERVER"] = CONFIGS["RPC_SERVER"].replace("$PORT", environ.get("PORT", "8080"))

    if CONFIGS["PRESENCE_INTERVAL"] < 300:
        CONFIGS["PRESENCE_INTERVAL"] = 300

    if CONFIGS["IDLE_TIMEOUT"] < 30:
        CONFIGS["IDLE_TIMEOUT"] = 30

    if 10 < CONFIGS["PLAYER_MESSAGE_UPDATE_INTERVAL"] < 45:
        CONFIGS["PLAYER_MESSAGE_UPDATE_INTERVAL"] = 15

    return CONFIGS
