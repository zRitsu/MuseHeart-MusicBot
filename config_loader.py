# -*- coding: utf-8 -*-
from json import load
from os import environ

import disnake
from dotenv import dotenv_values

bools = {
    "true": True,
    "false": False,
    "none": None
}

DEFAULT_CONFIG = {
    "DEFAULT_PREFIX": "!!",
    "AUTO_SYNC_COMMANDS": True,
    "OWNER_IDS": "",
    "COMMAND_LOG": False,
    "EMBED_COLOR": None,
    "BOT_ADD_REMOVE_LOG": '',
    "ERROR_REPORT_WEBHOOK": '',
    "AUTO_ERROR_REPORT_WEBHOOK": '',
    "INTERACTION_COMMAND_ONLY": False,
    "PRESENCE_INTERVAL": 900,
    "SOURCE_REPO": "https://github.com/zRitsu/disnake-LL-music-bot.git",
    "SUPPORT_SERVER": "",
    "ADDITIONAL_BOT_IDS": "",
    "INVITE_PERMISSIONS": 332892794064,
    "ENABLE_LOGGER": False,
    "INTERACTION_BOTS": "",
    "INTERACTION_BOTS_CONTROLLER": "",
    "KILL_ON_429": True,
    "PREFIXED_POOL_TIMEOUT": 4,

    ################
    ### Database ###
    ################
    "MONGO": "",
    "MONGO_CACHE_CLEANUP_INTERVAL": 300,
    "SENSITIVE_INFO_WARN": True,

    #########################
    ### Sistema de música ###
    #########################
    "AUTO_DOWNLOAD_LAVALINK_SERVERLIST": False,
    "LAVALINK_SERVER_LIST": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/lavalink.ini",
    "DEFAULT_SKIN": "default",
    "DEFAULT_STATIC_SKIN": "default",
    "DEFAULT_IDLING_SKIN": "default",
    "VOTE_SKIP_AMOUNT": 3,
    "IDLE_TIMEOUT": 180,
    "MAX_USER_FAVS": 10,
    "USER_FAV_MAX_NAME_LENGTH": 35,
    "USER_FAV_MAX_URL_LENGTH": 90,
    "EXTRA_HINTS": "",
    "HINT_RATE": 4,
    "IGNORE_SKINS": '',
    "IGNORE_STATIC_SKINS": '',
    "GUILD_DEAFEN_WARN": True,
    "ADD_REGISTER_COMMAND": False,
    "ENABLE_DISCORD_URLS_PLAYBACK": True,
    "PLAYER_INFO_BACKUP_INTERVAL": 45,
    "PLAYER_SESSIONS_MONGODB": False,

    ##############################################
    ### Sistema de música - Suporte ao spotify ###
    ##############################################
    "SPOTIFY_CLIENT_ID": '',
    "SPOTIFY_CLIENT_SECRET": '',
    "SEARCH_PROVIDER": "ytsearch",

    ################################################
    ### Sistema de música - RPC (Rich Presence): ###
    ################################################
    "RUN_RPC_SERVER": True,
    "RPC_SERVER": "ws://localhost:$PORT/ws",
    "RPC_PUBLIC_URL": "",
    "ENABLE_RPC_COMMAND": False,
    "ENABLE_RPC_AUTH": False,

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
    "STREAMING_PRESENCES": "",

    ###############
    ### Intents ###
    ###############
    "BANS_INTENT": False,
    "DM_MESSAGES_INTENT": False,
    "DM_REACTIONS_INTENT": False,
    "DM_TYPING_INTENT": False,
    "GUILD_MESSAGES_INTENT": True,
    "GUILD_REACTIONS_INTENT": False,
    "GUILD_SCHEDULED_EVENTS_INTENT": False,
    "GUILD_TYPING_INTENT": False,
    "EMOJIS_AND_STICKERS_INTENT": True,
    "GUILDS_INTENT": True,
    "INTEGRATIONS_INTENT": True,
    "INVITES_INTENT": True,
    "VOICE_STATES_INTENT": True,
    "WEBHOOKS_INTENT": False,

    ##########################
    ### Privileged Intents ###
    ##########################
    "MEMBERS_INTENT": False,
    "PRESENCES_INTENT": False,
    "MESSAGE_CONTENT_INTENT": True,
}


def load_config():

    CONFIG = dict(DEFAULT_CONFIG)

    for cfg in list(CONFIG) + ["TOKEN", "MONGO"]:
        try:
            CONFIG[cfg] = environ[cfg]
        except KeyError:
            continue

    for env in environ:
        if env.lower().startswith(("token_bot_", "test_guilds_", "lavalink_node_")):
            CONFIG[env] = environ[env]

    try:
        with open("config.json") as f:
            CONFIG.update(load(f))
    except FileNotFoundError:
        pass

    try:
        CONFIG.update(dotenv_values())
    except:
        pass

    try:
        CONFIG["EMBED_COLOR"] = disnake.Color(int(CONFIG["EMBED_COLOR"], 16))
    except:
        CONFIG["EMBED_COLOR"] = None

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
        "INVITE_PERMISSIONS",
        "MONGO_CACHE_CLEANUP_INTERVAL",
        "PREFIXED_POOL_TIMEOUT",
        "PLAYER_INFO_BACKUP_INTERVAL"
    ]:
        try:
            CONFIG[i] = int(CONFIG[i])
        except ValueError:
            raise Exception(f"Você usou uma configuração inválida! {i}: {CONFIG[i]}")

    # converter strings que requer valor bool/nulo.
    for i in [
        "AUTO_SYNC_COMMANDS",
        "INTERACTION_COMMAND_ONLY",
        "RUN_LOCAL_LAVALINK",
        "COMMAND_LOG",
        "RUN_RPC_SERVER",
        "ENABLE_RPC_COMMAND",
        "ENABLE_RPC_AUTH",
        "AUTO_DOWNLOAD_LAVALINK_SERVERLIST",
        "ENABLE_LOGGER",
        "GUILD_DEAFEN_WARN",
        "ADD_REGISTER_COMMAND",
        "ENABLE_DISCORD_URLS_PLAYBACK",
        "PLAYER_SESSIONS_MONGODB",
        "SENSITIVE_INFO_WARN",

        "BANS_INTENT",
        "DM_MESSAGES_INTENT",
        "DM_REACTIONS_INTENT",
        "DM_TYPING_INTENT",
        "GUILD_MESSAGES_INTENT",
        "GUILD_REACTIONS_INTENT",
        "GUILD_SCHEDULED_EVENTS_INTENT",
        "GUILD_TYPING_INTENT",
        "EMOJIS_AND_STICKERS_INTENT",
        "GUILDS_INTENT",
        "INTEGRATIONS_INTENT",
        "INVITES_INTENT",
        "VOICE_STATES_INTENT",
        "WEBHOOKS_INTENT",

        "MEMBERS_INTENT",
        "PRESENCES_INTENT",
        "MESSAGE_CONTENT_INTENT",
    ]:
        if CONFIG[i] in (True, False, None):
            continue

        try:
            CONFIG[i] = bools[CONFIG[i]]
        except KeyError:
            raise Exception(f"Você usou uma configuração inválida! {i}: {CONFIG[i]}")

    CONFIG["RPC_SERVER"] = CONFIG["RPC_SERVER"].replace("$PORT", environ.get("PORT", "80"))

    if CONFIG["PRESENCE_INTERVAL"] < 300:
        CONFIG["PRESENCE_INTERVAL"] = 300

    if CONFIG["MONGO_CACHE_CLEANUP_INTERVAL"] < 30:
        CONFIG["MONGO_CACHE_CLEANUP_INTERVAL"] = 30

    if CONFIG["IDLE_TIMEOUT"] < 30:
        CONFIG["IDLE_TIMEOUT"] = 30

    if CONFIG["PLAYER_INFO_BACKUP_INTERVAL"] < 30:
        CONFIG["PLAYER_INFO_BACKUP_INTERVAL"] = 30

    return CONFIG
