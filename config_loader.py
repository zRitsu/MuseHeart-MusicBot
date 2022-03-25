from json import load
from dotenv import dotenv_values
from os import environ


bools = {
    "true": True,
    "false": False,
    "none": None
}


def load_config():

    ###############################################################################################
    #####                                                                                     #####
    #####  Nota:                                                                              #####
    #####  As configs abaixo serve apenas como modelo, caso esteja na repl.it/heroku etc      #####
    #####  altere elas criando uma secret/env colocando o value/key conforme os itens abaixo, #####
    #####  caso seja outra host, use o arquivo .env ou config.json e modifique de acordo com  #####
    #####  os valores exibidos no modelo abaixo.                                              #####
    #####                                                                                     #####
    ###############################################################################################

    CONFIGS = {
        "VOTE_SKIP_AMOUNT": 3, # quantidade de votos necessários para o comando de voteskip.
        "DEFAULT_PREFIX": "!!!", # prefixo padrão do bot.
        "DEFAULT_SKIN": "default", # skin padrão do player (você pode copiar a skin padrão e deixa-la com outro nome e editar o arquivo a seu gosto, ela não será afetada por minhas alterações em updates).
        "AUTO_SYNC_COMMANDS": True, # Sincronizar comandos automaticamente ao ligar o bot.
        "OWNER_IDS": "", # ID de usuário pra lista de owner/dono do bot, caso use mais de 1 id separe por || (Qualquer id que for colocado na lista vai permitir o membro ter acesso total ao bot, tome cuidado!).
        "IDLE_TIMEOUT": 180, # Tempo em segundos pro bot aguardar por novas músicas no modo de espera.
        "COMMAND_LOG": False, # Ativar/Desativar log de comandos.
        "RPC_SERVER": "ws://localhost:8080/ws", # Link do servidor RPC (pra status do membro), caso não tenha será usado localmente.
        "EMBED_COLOR": None, # cor da embed do player (caso não tenha será usado a cor do cargo do bot).
        "MAX_USER_FAVS": 10, # limiite de favoritos por membro (0 ou menor que isso = sem limites)
        "USER_FAV_MAX_NAME_LENGTH": 35,  # limite de caracteres no nome de playlists.
        "USER_FAV_MAX_URL_LENGTH": 90, # limite de caracteres no link de playlists.
        "BOT_ADD_REMOVE_LOG": '', # Link do webhook para envio de logs quando o bot for adicionado/removido de um server.
        "ERROR_REPORT_WEBHOOK": '', # Link do webhook para envio dos reports de erros.
        "PLAYER_MESSAGE_UPDATE_INTERVAL": 15, # Intervalo para atualizar a mensagem do player controller. (min = 10 e max = 45)
        "SPOTIFY_CLIENT_ID": '', # Necessário para o suporte ao spotify.
        "SPOTIFY_CLIENT_SECRET": '', # Necessário para o suporte ao spotify.
        "INTERACTION_COMMAND_ONLY": False, # Não permitir o uso dos comandos de texto com prefixo.
        "PRESENCE_INTERVAL": 900, # Tempo em segundos para alterar a presence do bot.
        "SOURCE_REPO": "https://github.com/zRitsu/disnake-LL-music-bot.git", # Link do github pra ser usado em comandos como o de update.
        "HIDE_SOURCE_OWNER": False,  # Ocultar link do meu repositório no comando /about. Caso altere isso, por favor considere de alguma forma fornecer crédito. :(
        "SUPPORT_SERVER": "", # invite do servidor de suporte (exibido no comando about e nos erros dos comandos).

        #############################################################################################
        ##### Bot presences:                                                                    #####
        ##### Status pra exibir no bot, caso queira mais de 1 pra tipo específico separe com || #####
        #####                                                                                   #####
        ##### Placeholders:                                                                     #####
        ##### {users} -> quantidade de usuários.                                                #####
        ##### {guilds} -> quantidade de servidores.                                             #####
        ##### {playing} -> quantidade de players ativos.                                        #####
        ##### {uptime} -> uptime do bot.                                                        #####
        #############################################################################################

        "LISTENING_PRESENCES": "",
        "WATCHING_PRESENCES": "",
        "PLAYING_PRESENCES": "",

        ##############################
        ### Local lavalink stuffs: ###
        ##############################

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
        "COMMAND_LOG"

    ]:
        if CONFIGS[i] in (True, False, None):
            continue

        try:
            CONFIGS[i] = bools[CONFIGS[i]]
        except KeyError:
            raise Exception(f"Você usou uma configuração inválida! {i}: {CONFIGS[i]}")

    if CONFIGS["PRESENCE_INTERVAL"] < 300:
        CONFIGS["PRESENCE_INTERVAL"] = 300

    if CONFIGS["IDLE_TIMEOUT"] < 30:
        CONFIGS["IDLE_TIMEOUT"] = 30

    if 10 < CONFIGS["PLAYER_MESSAGE_UPDATE_INTERVAL"] < 45:
        CONFIGS["PLAYER_MESSAGE_UPDATE_INTERVAL"] = 15

    return CONFIGS
