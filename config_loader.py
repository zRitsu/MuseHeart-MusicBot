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
        "DEFAULT_PREFIX": "!!!",
        "AUTO_SYNC_COMMANDS": True,
        "OWNER_IDS": "",
        "INTENTS": "",
        "DISABLE_INTENTS": "",
        "COMMAND_LOG": False,
        "EMBED_COLOR": None,
        "BOT_ADD_REMOVE_LOG": '',
        "ERROR_REPORT_WEBHOOK": '',
        "INTERACTION_COMMAND_ONLY": False,
        "PRESENCE_INTERVAL": 900,
        "SOURCE_REPO": "https://github.com/zRitsu/disnake-LL-music-bot.git",
        "HIDE_SOURCE_OWNER": False,
        "SUPPORT_SERVER": "",
        "ADDITIONAL_BOT_IDS": "",
        "INVITE_PERMISSIONS": 397287680080,

        #########################
        ### Sistema de música ###
        #########################
        "DEFAULT_SKIN": "default",
        "VOTE_SKIP_AMOUNT": 3,
        "IDLE_TIMEOUT": 180,
        "RUN_RPC_SERVER": True,
        "RPC_SERVER": "ws://localhost:$PORT/ws",
        "MAX_USER_FAVS": 10,
        "USER_FAV_MAX_NAME_LENGTH": 35,
        "USER_FAV_MAX_URL_LENGTH": 90,
        "HINT_RATE": 4,
        "PLAYER_MESSAGE_UPDATE_INTERVAL": 15,
        "YTDLMODE": False,
        "IGNORE_SKINS": '',

        ##############################################
        ### Sistema de música - Suporte ao spotify ###
        ##############################################
        "SPOTIFY_CLIENT_ID": '',
        "SPOTIFY_CLIENT_SECRET": '',

        ##################################################
        ### Sistema de música - Local lavalink stuffs: ###
        ##################################################
        "RUN_LOCAL_LAVALINK": False,
        "LAVALINK_ADDITIONAL_SLEEP": 0,
        "LAVALINK_INITIAL_RAM": 30,
        "LAVALINK_RAM_LIMIT": 120,
        "LAVALINK_CPU_CORES": 2,
        "LAVALINK_FILE_URL": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/Lavalink.jar",

        ##########################
        ##### Bot presences: #####
        ##########################
        "LISTENING_PRESENCES": "",
        "WATCHING_PRESENCES": "",
        "PLAYING_PRESENCES": "",
    }

    for cfg in list(CONFIGS) + ["TOKEN", "MONGO"]:
        try:
            CONFIGS[cfg] = environ[cfg]
        except KeyError:
            continue

    for env in environ:
        if env.lower().startswith(("token_bot_", "test_guilds_", "lavalink_node_")):
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
        "PRESENCE_INTERVAL",
        "HINT_RATE",
        "INVITE_PERMISSIONS"
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
        "RUN_LOCAL_LAVALINK",
        "COMMAND_LOG",
        "RUN_RPC_SERVER",
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
