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
    "SOURCE_REPO": "https://github.com/zRitsu/MuseHeart-MusicBot.git",
    "SUPPORT_SERVER": "",
    "ADDITIONAL_BOT_IDS": "",
    "INVITE_PERMISSIONS": 332892794064,
    "ENABLE_LOGGER": False,
    "KILL_ON_429": True,
    "PREFIXED_POOL_TIMEOUT": 4,
    "ENABLE_COMMANDS_COOLDOWN": True,
    "GIT_DIR": "./.git",

    ################
    ### Database ###
    ################
    "MONGO": "",
    "MONGO_TIMEOUT": 30,
    "SENSITIVE_INFO_WARN": True,

    #########################
    ### Sistema de música ###
    #########################
    "AUTO_DOWNLOAD_LAVALINK_SERVERLIST": False,
    "LAVALINK_SERVER_LIST": "https://gist.githubusercontent.com/zRitsu/c3511e1da0440b94c126769dd40c9d91/raw/lavalink.ini",
    "LAVALINK_RECONNECT_RETRIES": 30,
    "DEFAULT_SKIN": "default",
    "DEFAULT_STATIC_SKIN": "default",
    "DEFAULT_IDLING_SKIN": "default",
    "VOTE_SKIP_AMOUNT": 3,
    "IDLE_TIMEOUT": 180,
    "WAIT_FOR_MEMBERS_TIMEOUT": 180,
    "MAX_USER_FAVS": 10,
    "USER_FAV_MAX_NAME_LENGTH": 35,
    "USER_FAV_MAX_URL_LENGTH": 90,
    "MAX_USER_INTEGRATIONS": 10,
    "EXTRA_HINTS": "",
    "HINT_RATE": 4,
    "IGNORE_SKINS": '',
    "IGNORE_STATIC_SKINS": '',
    "GUILD_DEAFEN_WARN": True,
    "ENABLE_DISCORD_URLS_PLAYBACK": True,
    "PLAYER_INFO_BACKUP_INTERVAL": 45,
    "PLAYER_INFO_BACKUP_INTERVAL_MONGO": 300,
    "PLAYER_SESSIONS_MONGODB": False,
    "QUEUE_MAX_ENTRIES": 0,
    "ENABLE_DEFER_TYPING": True,
    "VOICE_CHANNEL_LATENCY_RECONNECT": 200,
    "PLAYLIST_CACHE_SIZE": 500,
    "PLAYLIST_CACHE_TTL": 1800,
    "USE_YTM_TRACKINFO_SCROBBLE": False,
    "PARTIALTRACK_FIRST": False,

    ##############################################
    ### Sistema de música - Suporte ao spotify ###
    ##############################################
    "SPOTIFY_CLIENT_ID": '',
    "SPOTIFY_CLIENT_SECRET": '',
    "SPOTIFY_PLAYLIST_EXTRA_PAGE_LIMIT": 0,

    ################################################
    ### Sistema de música - RPC (Rich Presence): ###
    ################################################
    "RUN_RPC_SERVER": True,
    "RPC_SERVER": "ws://localhost:$PORT/ws",
    "PORT": None,
    "RPC_PUBLIC_URL": "",
    "ENABLE_RPC_COMMAND": False,
    "ENABLE_RPC_AUTH": False,

    ##################################################
    ### Sistema de música - Local lavalink stuffs: ###
    ##################################################
    "RUN_LOCAL_LAVALINK": False,
    "CONNECT_LOCAL_LAVALINK": True,
    "USE_JABBA": False,
    "LAVALINK_ADDITIONAL_SLEEP": 0,
    "LAVALINK_INITIAL_RAM": 30,
    "LAVALINK_RAM_LIMIT": 120,
    "LAVALINK_CPU_CORES": 2,
    "LAVALINK_FILE_URL": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/Lavalink.jar",
    "SEARCH_PROVIDERS": "scsearch",
    "PREFER_YOUTUBE_NATIVE_PLAYBACK": True,
    "ONLY_USE_NATIVE_SEARCH_PROVIDERS": True,

    ##################################################
    ### Sistema de música - Integração com Last.fm ###
    ##################################################

    "LASTFM_KEY": "",
    "LASTFM_SECRET": "",

    ##########################
    ##### Bot presences: #####
    ##########################
    "LISTENING_PRESENCES": "",
    "WATCHING_PRESENCES": "",
    "PLAYING_PRESENCES": "",
    "STREAMING_PRESENCES": "",
    "CUSTOM_STATUS_PRESENCES": "",

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

    ##############
    ### Tests ####
    ##############
    "USE_YTDL": True,
    "FORCE_USE_DEEZER_CLIENT": False,
    "SILENT_PUBLICBOT_WARNING": False,
    "DBCACHE_SIZE": 1000,
    "DBCACHE_TTL": 300
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
        "WAIT_FOR_MEMBERS_TIMEOUT",
        "VOTE_SKIP_AMOUNT",
        "LAVALINK_ADDITIONAL_SLEEP",
        "LAVALINK_INITIAL_RAM",
        "LAVALINK_RAM_LIMIT",
        "LAVALINK_CPU_CORES",
        "USER_FAV_MAX_NAME_LENGTH",
        "USER_FAV_MAX_URL_LENGTH",
        "MAX_USER_INTEGRATIONS",
        "PRESENCE_INTERVAL",
        "HINT_RATE",
        "MONGO_TIMEOUT",
        "INVITE_PERMISSIONS",
        "PREFIXED_POOL_TIMEOUT",
        "PLAYER_INFO_BACKUP_INTERVAL",
        "PLAYER_INFO_BACKUP_INTERVAL_MONGO",
        "LAVALINK_RECONNECT_RETRIES",
        "QUEUE_MAX_ENTRIES",
        "VOICE_CHANNEL_LATENCY_RECONNECT",
        "DBCACHE_SIZE",
        "DBCACHE_TTL",
        "PLAYLIST_CACHE_SIZE",
        "PLAYLIST_CACHE_TTL",
        "SPOTIFY_PLAYLIST_EXTRA_PAGE_LIMIT",
    ]:
        try:
            new_value = int(CONFIG[i])
        except ValueError as e:
            raise Exception(f"Você usou uma configuração inválida! {i}: {CONFIG[i]}\n{repr(e)}")

        CONFIG[i] = new_value

    # converter strings que requer valor bool/nulo.
    for i in [
        "AUTO_SYNC_COMMANDS",
        "INTERACTION_COMMAND_ONLY",
        "RUN_LOCAL_LAVALINK",
        "USE_JABBA",
        "CONNECT_LOCAL_LAVALINK",
        "COMMAND_LOG",
        "RUN_RPC_SERVER",
        "ENABLE_RPC_COMMAND",
        "ENABLE_RPC_AUTH",
        "AUTO_DOWNLOAD_LAVALINK_SERVERLIST",
        "ENABLE_LOGGER",
        "GUILD_DEAFEN_WARN",
        "ENABLE_DISCORD_URLS_PLAYBACK",
        "PLAYER_SESSIONS_MONGODB",
        "SENSITIVE_INFO_WARN",
        "ENABLE_DEFER_TYPING",
        "ENABLE_COMMANDS_COOLDOWN",

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

        "USE_YTDL",
        "PREFER_YOUTUBE_NATIVE_PLAYBACK",
        "ONLY_USE_NATIVE_SEARCH_PROVIDERS",
        "USE_YTM_TRACKINFO_SCROBBLE",
        "PARTIALTRACK_FIRST",
        "FORCE_USE_DEEZER_CLIENT",
        "SILENT_PUBLICBOT_WARNING",
    ]:
        if CONFIG[i] in (True, False, None):
            continue

        try:
            new_value = bools[CONFIG[i]]
        except KeyError as e:
            raise Exception(f"Você usou uma configuração inválida! {i}: {CONFIG[i]}\n{repr(e)}")

        CONFIG[i] = new_value

    CONFIG["RPC_SERVER"] = CONFIG["RPC_SERVER"].replace("$PORT", CONFIG.get("PORT") or environ.get("PORT", "80"))

    if CONFIG["IDLE_TIMEOUT"] < 60:
        CONFIG["IDLE_TIMEOUT"] = 60

    if CONFIG["WAIT_FOR_MEMBERS_TIMEOUT"] < 60:
        CONFIG["WAIT_FOR_MEMBERS_TIMEOUT"] = 60

    if CONFIG["PRESENCE_INTERVAL"] < 300:
        CONFIG["PRESENCE_INTERVAL"] = 300

    if CONFIG["IDLE_TIMEOUT"] < 10:
        CONFIG["IDLE_TIMEOUT"] = 10

    if CONFIG["PLAYER_INFO_BACKUP_INTERVAL"] < 30:
        CONFIG["PLAYER_INFO_BACKUP_INTERVAL"] = 30

    if CONFIG["PLAYER_INFO_BACKUP_INTERVAL_MONGO"] < 120:
        CONFIG["PLAYER_INFO_BACKUP_INTERVAL_MONGO"] = 120

    if CONFIG["LAVALINK_RECONNECT_RETRIES"] < 5:
        CONFIG["LAVALINK_RECONNECT_RETRIES"] = 0

    return CONFIG
