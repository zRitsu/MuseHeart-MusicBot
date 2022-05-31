import sys
import traceback
from typing import Union, Optional
import disnake
from disnake.ext import commands
from utils.music.converters import perms_translations, time_format


class GenericError(commands.CheckFailure):

    def __init__(self, text: str, *, self_delete: int = None, delete_original: Optional[int] = None):
        self.text = text
        self.self_delete = self_delete
        self.delete_original = delete_original


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


def parse_error(
        ctx: Union[disnake.ApplicationCommandInteraction, commands.Context, disnake.MessageInteraction],
        error: Exception
):

    error_txt = None

    error = getattr(error, 'original', error)

    if isinstance(error, NotDJorStaff):
        error_txt = "**Você deve estar na lista de DJ ou ter a permissão de **Gerenciar canais** " \
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
        error_txt = "**Não há player inicializado no servidor.**"

    elif isinstance(error, MissingSpotifyClient):
        error_txt = "**Não há suporte a links do spotify no momento.**"

    elif isinstance(error, commands.CommandOnCooldown):
        remaing = int(error.retry_after)
        if remaing < 1:
            remaing = 1
        error_txt = "**Você deve aguardar {} para usar esse comando.**".format(time_format(int(remaing) * 1000))

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

    if not error_txt:
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    return error_txt