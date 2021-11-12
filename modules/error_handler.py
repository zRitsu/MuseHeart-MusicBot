import disnake
import traceback
from utils.music.converters import time_format
from utils.music.errors import *
from utils.music.interactions import send_message
import sys

perms_translations = {
	"create_instant_invite": "Criar convite instantâneo",
	"kick_members": "Expulsar membros",
	"ban_members": "Banir membros",
	"administrator": "Administrador",
	"manage_channels": "Gerenciar canais",
	"manage_guild": "Gerenciar servidor",
	"add_reactions": "Adicionar reações",
	"view_audit_log": "Ver o registro de auditoria",
	"priority_speaker": "Voz prioritária",
	"stream": "Transmitir em canais de voz",
	"read_messages": "Ler mensagens",
	"send_messages": "Enviar mensagens",
	"send_tts_messages": "Enviar mensagens em TTS",
	"manage_messages": "Gerenciar mensagens",
	"embed_links": "Inserir links",
	"attach_files": "Anexar arquivos",
	"read_message_history": "Ver histórico de mensagens",
	"mention_everyone": "Mencionar todos",
	"external_emojis": "Usar emojis externos",
	"view_guild_insights": "Ver informação do servidor",
	"connect": "Conectar",
	"speak": "Falar",
	"mute_members": "Silenciar membros",
	"deafen_members": "Ensurdecer membros",
	"move_members": "Mover membros",
	"use_voice_activation": "Usar detecção de voz",
	"change_nickname": "Mudar apelido",
	"manage_nicknames": "Gerenciar apelidos",
	"manage_roles": "Gerenciar cargos",
	"manage_webhooks": "Gerenciar webhooks",
	"manage_emojis": "Gerenciar emojis",
	"use_slash_commands": "Usar comandos de barra",
}


class ErrorHandler(commands.Cog):
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener('on_user_command_error')
    @commands.Cog.listener('on_message_command_error')
    @commands.Cog.listener('on_slash_command_error')
    async def on_interaction_command_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception):

        embed = disnake.Embed(color=disnake.Colour.red())

        error_txt = None

        error = getattr(error, 'original', error)

        if isinstance(error, NotDJorStaff):
            error_txt = "**Você deve estar na lista de DJ ou ter a permissão de **Gerenciar canais** " \
                        "para usar este comando.**"

        elif isinstance(error, commands.NotOwner):
            error_txt = "**Apenas meu(s) desenvolvedor(es) pode(m) usar este comando.**"

        elif isinstance(error, commands.BotMissingPermissions):
            error_txt = "Não tenho as seguintes permissões para executar este comando: ```\n{}```"\
                .format(", ".join(perms_translations.get(perm, perm) for perm in error.missing_permissions))

        elif isinstance(error, commands.MissingPermissions):
            error_txt = "Você não possui as seguintes permissões para executar este comando: ```\n{}```"\
                .format(", ".join(perms_translations.get(perm, perm) for perm in error.missing_permissions))

        elif isinstance(error, GenericError):
            error_txt = error.text

        elif isinstance(error, NotRequester):
            error_txt = "**Você deve ter pedido a música atual ou estar na lista de DJ ou ter a permissão de " \
                        "**Gerenciar canais** para pular músicas.**"

        elif isinstance(error, DiffVoiceChannel):
            error_txt = "**Você deve estar no meu canal de voz atual para usar este comando.**"

        elif isinstance(error, NoSource):
            error_txt = "**Não há músicas no player atualmente.**"

        elif isinstance(error, NoVoice):
            error_txt = "**Você deve estar em um canal de voz para usar este comando.**"

        elif isinstance(error, NoPlayer):
            error_txt = "**Não há player inicializado no servidor.**"

        elif isinstance(error, MissingSpotifyClient):
            error_txt = "**Não há suporte a links do spotify no momento.**"

        elif isinstance(error, commands.CommandOnCooldown):
            remaing = int(error.retry_after)
            if remaing < 1:
                remaing = 1
            error_txt = "**Você deve aguardar {} para usar este comando.**".format(time_format(int(remaing) * 1000))

        elif isinstance(error, commands.MaxConcurrencyReached):
            txt = f"{error.number} vezes " if error.number > 1 else ''
            txt = {
                commands.BucketType.member: f"você já usou esse comando {txt}neste servidor",
                commands.BucketType.guild: f"esse comando já foi usado {txt}neste servidor",
                commands.BucketType.user: f"você já usou esse comando {txt}",
                commands.BucketType.channel: f"esse comando já foi usado {txt}neste atual",
                commands.BucketType.category: f"esse comando já foi usado {txt}na categoria do canal atual",
                commands.BucketType.role: f"esse comando já foi usado {txt}por um membro que possui o cargo permitido",
                commands.BucketType.default: f"esse comando já foi usado {txt}por alguém"
            }

            error_txt = f"{inter.author.mention} **{txt[error.per]} e ainda não teve seu{'s' if error.number > 1 else ''} " \
                        f"uso{'s' if error.number > 1 else ''} finalizado{'s' if error.number > 1 else ''}!**"

        if error_txt:
            embed.description = error_txt
            return await send_message(inter, embed=embed)

        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if isinstance(error, commands.CommandNotFound):
            return

        embed.description = f"**Ocorreu um erro no comando:**\n" \
                            f"```py\n{str(repr(error))[:2020].replace(self.bot.http.token, 'mytoken')}```"

        await send_message(inter, embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(ErrorHandler(bot))