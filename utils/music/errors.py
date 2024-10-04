# -*- coding: utf-8 -*-
import os
import traceback
from typing import Union, Optional

import disnake
from disnake.ext import commands
from disnake.utils import escape_mentions
from pymongo.errors import ServerSelectionTimeoutError

from utils.music.converters import time_format, perms_translations
from wavelink import WavelinkException, TrackNotFound, MissingSessionID


class PoolException(commands.CheckFailure):
    pass

class ArgumentParsingError(commands.CommandError):
    def __init__(self, message):
        super().__init__(escape_mentions(message))

class GenericError(commands.CheckFailure):

    def __init__(self, text: str, *, self_delete: int = None, delete_original: Optional[int] = None, components: list = None, error: str = None):
        self.text = text
        self.self_delete = self_delete
        self.delete_original = delete_original
        self.components = components
        self.error = error

    def __repr__(self):
        return disnake.utils.escape_markdown(self.text)

    def __str__(self):
        return disnake.utils.escape_markdown(self.text)


class EmptyFavIntegration(commands.CheckFailure):
    pass

class MissingSpotifyClient(commands.CheckFailure):
    pass


class NoPlayer(commands.CheckFailure):
    pass


class NoVoice(commands.CheckFailure):
    pass


class MissingVoicePerms(commands.CheckFailure):

    def __init__(self, voice_channel: Union[disnake.VoiceChannel, disnake.StageChannel]):
        self.voice_channel = voice_channel


class DiffVoiceChannel(commands.CheckFailure):
    pass


class NoSource(commands.CheckFailure):
    pass


class NotDJorStaff(commands.CheckFailure):
    pass


class NotRequester(commands.CheckFailure):
    pass


class YoutubeSourceDisabled(commands.CheckFailure):
    pass


def parse_error(
        ctx: Union[disnake.ApplicationCommandInteraction, commands.Context, disnake.MessageInteraction],
        error: Exception
):

    error_txt = None

    kill_process = False

    mention_author = False

    components = []

    send_error = False

    error = getattr(error, 'original', error)

    if isinstance(error, NotDJorStaff):
        error_txt = "**Você deve estar na lista de DJ ou ter a permissão de **Mover Membros** " \
                    "para usar este comando.**"

    elif isinstance(error, MissingVoicePerms):
        error_txt = f"**Não tenho permissão para conectar/falar no canal:** {error.voice_channel.mention}"

    elif isinstance(error, commands.NotOwner):
        error_txt = "**Apenas meu(s) desenvolvedor(es) pode(m) usar esse comando.**"

    elif isinstance(error, commands.BotMissingPermissions):
        error_txt = "Não tenho as seguintes permissões para executar esse comando: ```\n{}```" \
            .format(", ".join(perms_translations.get(perm, perm) for perm in error.missing_permissions))

    elif isinstance(error, commands.MissingPermissions):
        error_txt = "Você não possui as seguintes permissões para executar esse comando: ```\n{}```" \
            .format(", ".join(perms_translations.get(perm, perm) for perm in error.missing_permissions))

    elif isinstance(error, GenericError):
        error_txt = error.text
        components = error.components
        if error.text:
            send_error = True

    elif isinstance(error, NotRequester):
        error_txt = "**Você deve ter pedido a música atual ou estar na lista de DJ ou ter a permissão de " \
                    "**Gerenciar canais** para pular músicas.**"

    elif isinstance(error, DiffVoiceChannel):
        error_txt = "**Você deve estar no meu canal de voz atual para usar esse comando.**"

    elif isinstance(error, NoSource):
        error_txt = "**Não há músicas no player atualmente.**"

    elif isinstance(error, NoVoice):
        error_txt = "**Você deve entrar em um canal de voz para usar esse comando.**"

    elif isinstance(error, NoPlayer):
        try:
            error_txt = f"**Não há player ativo no canal {ctx.author.voice.channel.mention}.**"
        except AttributeError:
            error_txt = "**Não há player inicializado no servidor.**"

    elif isinstance(error, (commands.UserInputError, commands.MissingRequiredArgument)) and ctx.command.usage:

        error_txt = "### Você usou o comando de forma incorreta.\n"

        if ctx.command.usage:

            prefix = ctx.prefix if str(ctx.me.id) not in ctx.prefix else f"@{ctx.me.display_name} "

            error_txt += f'📘 **⠂Como Usar:** ```\n{ctx.command.usage.replace("{prefix}", prefix).replace("{cmd}", ctx.command.name).replace("{parent}", ctx.command.full_parent_name)}```\n' \
                        f"⚠️ **⠂Notas sobre o uso dos argumentos no comando:** ```\n" \
                        f"[] = Obrigatório | <> = Opcional```\n"

    elif isinstance(error, MissingSpotifyClient):
        error_txt = "**Não há suporte a links do spotify no momento.**"

    elif isinstance(error, commands.NoPrivateMessage):
        error_txt = "Esse comando não pode ser executado em mensagens privadas."

    elif isinstance(error, MissingSessionID):
        error_txt = f"**O servidor de música {error.node.identifier} está desconectado, por favor aguarde alguns segundos e tente novamente.**"

    elif isinstance(error, commands.CommandOnCooldown):
        remaing = int(error.retry_after)
        if remaing < 1:
            remaing = 1
        error_txt = "**Você deve aguardar {} para usar esse comando.**".format(time_format(int(remaing) * 1000, use_names=True))

    elif isinstance(error, EmptyFavIntegration):

        if isinstance(ctx, disnake.MessageInteraction):
            error_txt = "**Você não possui favorito/integração**\n\n" \
                        "`Caso queira, você pode adicionar um favorito ou integração para usar esse " \
                        "esse botão da próxima vez. Pra isso você pode clicar em um dos botões abaixo.`"
        else:
            error_txt = "**Você usou o comando sem incluir um nome ou link de uma músisca ou vídeo e você não possui " \
                        "favoritos ou integrações para usar esse comando dessa forma diretamente...**\n\n" \
                        "`Caso queira, você pode adicionar um favorito ou integração para usar esse " \
                        "comando sem incluir um nome ou link. Pra isso você pode clicar em um dos botões abaixo.`"

        mention_author = True

        components = [
            disnake.ui.Button(label="Abrir o gerenciador de favoritos e integrações",
                              custom_id="musicplayer_fav_manager", emoji="⭐"),
        ]

    elif isinstance(error, commands.MaxConcurrencyReached):
        txt = f"{error.number} vezes " if error.number > 1 else ''
        txt = {
            commands.BucketType.member: f"você já usou esse comando {txt}no servidor",
            commands.BucketType.guild: f"esse comando já foi usado {txt}no servidor",
            commands.BucketType.user: f"você já usou esse comando {txt}",
            commands.BucketType.channel: f"esse comando já foi usado {txt}no canal atual",
            commands.BucketType.category: f"esse comando já foi usado {txt}na categoria do canal atual",
            commands.BucketType.role: f"esse comando já foi usado {txt}por um membro que possui o cargo permitido",
            commands.BucketType.default: f"esse comando já foi usado {txt}por alguém"
        }

        error_txt = f"{ctx.author.mention} **{txt[error.per]} e ainda não teve seu{'s' if error.number > 1 else ''} " \
                    f"uso{'s' if error.number > 1 else ''} finalizado{'s' if error.number > 1 else ''}!**"

    elif isinstance(error, TrackNotFound):
        error_txt = "**Não houve resultados para sua busca...**"

    elif isinstance(error, YoutubeSourceDisabled):
        error_txt = "O suporte a links/buscas do youtube está desativado devido a medidas reforçadas do próprio youtube " \
                     "que impede o funcionamento nativo de links do yt. Caso queira conferir a postagem do youtube sobre isso você pode [clicar aqui](<https://support.google.com/youtube/thread/269521462/enforcement-on-third-party-apps?hl=en>)."

    if isinstance(error, ServerSelectionTimeoutError) and os.environ.get("REPL_SLUG"):
        error_txt = "Foi detectado um erro de dns na repl.it que me impede de conectar com minha database " \
                    "do mongo/atlas. irei reiniciar e em breve estarei disponível novamente..."
        kill_process = True

    elif isinstance(error, WavelinkException):
        if "Unknown file format" in (wave_error := str(error)):
            error_txt = "**Não há suporte para o link especificado...**"
        elif "No supported audio format" in wave_error:
            error_txt = "**Não há suporte para o link informado.**"
        elif "This video is not available" in wave_error:
            error_txt = "**Este vídeo está indisponível ou privado...**"
        elif "This playlist type is unviewable" in wave_error:
            error_txt = "**Oo link da playlist contém um parâmetro/id não suportado...**"
        elif "The playlist does not exist" in wave_error:
            error_txt = "**A playlist não existe (ou está privada).**"
        elif "not made this video available in your country" in wave_error.lower() or \
                "who has blocked it in your country on copyright grounds" in wave_error.lower():
            error_txt = "**O conteúdo deste link não está disponível na região no qual estou funcionando...**"

    full_error_txt = ""

    if not error_txt:
        full_error_txt = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        print(full_error_txt)
    elif send_error:
        full_error_txt = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    return error_txt, full_error_txt, kill_process, components, mention_author
