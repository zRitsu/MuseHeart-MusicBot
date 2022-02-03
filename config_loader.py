import json
from json import load
from dotenv import dotenv_values
from os import environ


bools = {
    "true": True,
    "false": False,
    "none": None
}


def load_config():

    #############################################################################################
    #####
    #####  Nota:
    #####  As configs abaixo serve apenas como modelo, caso esteja na repl.it/heroku etc
    #####  altere elas criando uma secret/env colocando o value/key conforme os itens abaixo,
    #####  caso seja outra host, use o arquivo .env ou config.json e modifique de acordo com
    #####  os valores exibidos no modelo abaixo.
    #####
    #############################################################################################

    CONFIGS = {
        "VOTE_SKIP_AMOUNT": 3, # quantidade de votos necessários para o comando de voteskip.
        "DEFAULT_PREFIX": "!!!", # prefixo padrão do bot.
        "DEFAULT_SKIN": "default", # skin padrão do player (você pode copiar a skin padrão e deixa-la com outro nome e editar o arquivo a seu gosto, ela não será afetada por minhas alterações em updates).
        "AUTO_SYNC_COMMANDS": True, # Sincronizar comandos automaticamente ao ligar o bot.
        "IDLE_TIMEOUT": 180, # Tempo em segundos pro bot aguardar por novas músicas no modo de espera.
        "RPC_SERVER": "ws://localhost:8080/ws", # Link do servidor RPC (pra status do membro), caso não tenha será usado localmente.
        "EMBED_COLOR": None, # cor da embed do player (caso não tenha será usado a cor do cargo do bot).
        "MAX_USER_FAVS": 10, # limiite de favoritos por membro (0 ou menor que isso = sem limites)
        "SPOTIFY_CLIENT_ID": '', # Necessário para o suporte ao spotify.
        "SPOTIFY_CLIENT_SECRET": '', # Necessário para o suporte ao spotify.
        "SOURCE_REPO": "https://github.com/zRitsu/disnake-LL-music-bot.git", # Link do github pra ser usado em comandos como o de update,
        "HIDE_SOURCE_OWNER": False,  # Ocultar link do meu repositório no comando /about. Caso altere isso, por favor considere de alguma forma fornecer crédito. :(

        #############################
        ### Local lavalink stuffs ###
        #############################

        "START_LOCAL_LAVALINK": True, # Iniciar um servidor lavalink localmente (Nota, requer uma vps/host com 512mb no mínimo, caso desative ignore todos os itens abaixo mas você terá que adicionar um servidor lavalink externo).
        "LAVALINK_ADDITIONAL_SLEEP": 0, # Tempo adicional pra aguardar o servidor lavalink iniciar (atualmente não é muito necessário e talvez em breve irei retirar).
        "LAVALINK_INITIAL_RAM": 30, # Quantidade de ram inicial pra ser usado no processo do servidor lavalink.
        "LAVALINK_RAM_LIMIT": 120, # Limite de ram pra ser usado no processo do servidor lavalink.
        "LAVALINK_CPU_CORES": 2, # Quantidade de cpu cores pra ser usado no servidor lavalink.
        "LAVALINK_FILE_URL": "https://github.com/zRitsu/LL-binaries/releases/download/0.0.1/Lavalink.jar" # link pra baixar o arquivo Lavalink.jar
    }

    for cfg in list(CONFIGS) + ["TOKEN", "MONGO"]:
        try:
            CONFIGS[cfg] = environ[cfg]
        except KeyError:
            continue

    for env in environ:
        if env.lower().startswith("token_bot_") or env.lower().startswith("lavalink_node_"):
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
        "LAVALINK_CPU_CORES"
    ]:
        CONFIGS[i] = int(CONFIGS[i])

    # converter strings que requer valor bool/nulo.
    for i in [
        "AUTO_SYNC_COMMANDS",
        "EMBED_COLOR",
        "HIDE_SOURCE_OWNER",
        "START_LOCAL_LAVALINK"

    ]:
        if CONFIGS[i] in (True, False, None):
            continue

        CONFIGS[i] = bools[CONFIGS[i]]

    if CONFIGS["IDLE_TIMEOUT"] < 30:
        CONFIGS["IDLE_TIMEOUT"] = 30

    return CONFIGS
