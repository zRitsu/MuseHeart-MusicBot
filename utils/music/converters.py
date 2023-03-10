from __future__ import annotations
import datetime
from typing import Union, TYPE_CHECKING
import disnake
import re
import json
from user_agent import generate_user_agent

if TYPE_CHECKING:
    pass

URL_REG = re.compile('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
YOUTUBE_VIDEO_REG = re.compile(r"(https?://)?(www\.)?youtube\.(com|nl)/watch\?v=([-\w]+)")

replaces = [
    ('&quot;', '"'),
    ('&amp;', '&'),
    ('(', '\u0028'),
    (')', '\u0029'),
    ('[', '【'),
    (']', '】'),
    ("  ", " "),
    ("*", '"'),
    ("_", ' '),
    ("{", "\u0028"),
    ("}", "\u0029"),
    ("`", "'")
]

u_agent = generate_user_agent()


async def google_search(bot, query: str, *, max_entries: int = 20) -> list:

    async with bot.session.get(
            f"http://suggestqueries.google.com/complete/search?client=chrome&ds=yt&q={query}",
            headers={'User-Agent': u_agent}) as r:
        return json.loads(await r.text())[1][:max_entries]


def get_button_style(enabled: bool, red=True):
    if enabled:
        if red:
            return disnake.ButtonStyle.red
        return disnake.ButtonStyle.green
    return disnake.ButtonStyle.grey


def fix_characters(text: str, limit: int = 0):
    for r in replaces:
        text = text.replace(r[0], r[1])

    if limit:
        text = f"{text[:limit]}..." if len(text) > limit else text

    return text


def time_format(milliseconds: Union[int, float], use_names: bool = False) -> str:
    minutes, seconds = divmod(int(milliseconds / 1000), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    if use_names:

        times = []

        for time_, name in (
                (days, "dia"),
                (hours, "hora"),
                (minutes, "minuto"),
                (seconds, "segundo")
        ):
            if not time_:
                continue

            times.append(f"{time_} {name}" + ("s" if time_ > 1 else ""))

        try:
            last_time = times.pop()
        except IndexError:
            last_time = None
            times = ["1 segundo"]

        strings = ", ".join(t for t in times)

        if last_time:
            strings += f" e {last_time}" if strings else last_time

    else:

        strings = f"{minutes:02d}:{seconds:02d}"

        if hours:
            strings = f"{hours}:{strings}"

        if days:
            strings = (f"{days} dias" if days > 1 else f"{days} dia") + (f", {strings}" if strings != "00:00" else "")

    return strings


time_names = ["seconds", "minutes", "hours"]


def string_to_seconds(time):
    try:

        times = reversed(time.split(':'))
        time_dict = {}

        for n, t in enumerate(times):
            time_dict[time_names[n]] = int(t)

        return datetime.timedelta(**time_dict).total_seconds()

    except:
        return


def percentage(part, whole):
    return int((part * whole) / 100.0)


perms_translations = {
    "add_reactions": "Adicionar Reações",
    "administrator": "Administrador",
    "attach_files": "Anexar Arquivos",
    "ban_members": "Banir Membros",
    "change_nickname": "Alterar apelido",
    "connect": "Conectar em canal de voz",
    "create_instant_invite": "Criar convite instantâneo",
    "create_private_threads": "Criar Tópicos Privado",
    "create_public_threads": "Criar Tópicos Públicos",
    "deafen_members": "Ensurdecer membros",
    "embed_links": "Embutir links",
    "kick_members": "Expulsar Membros",
    "manage_channels": "Gerenciar Canais",
    "manage_emojis_and_stickers": "Gerenciar Emojis e Figurinhas",
    "manage_events": "Gerenciar Eventos",
    "manage_guild": "Gerenciar Servidor",
    "manage_messages": "Gerenciar Mensagens",
    "manage_nicknames": "Gerenciar Apelidos",
    "manage_roles": "Gerenciar Cargos",
    "manage_threads": "Gerenciar Tópicos",
    "manage_webhooks": "Gerenciar Webhooks",
    "mention_everyone": "Marcar @everyone e @here",
    "moderate_members": "Moderar membros",
    "move_members": "Mover membros",
    "mute_members": "Silenciar membros",
    "priority_speaker": "Prioridade para falar",
    "read_message_history": "Mostrar histórico de mensagens",
    "request_to_speak": "Pedir para falar",
    "send_messages": "Enviar mensagem",
    "send_messages_in_threads": "Enviar mensagem em tópicos",
    "send_tts_messages": "Enviar mensagens de texto-a-voz",
    "speak": "Falar em canal de voz",
    "stream": "Transmitir",
    "use_application_commands": "Usar comandos de aplicações/bots",
    "use_embedded_activities": "Usar atividades ",
    "use_external_emojis": "Usar Emojis Externos",
    "use_external_stickers": "Usar Figurinhas Externas",
    "use_voice_activation": "Usar detecção de voz automática",
    "view_audit_log": "Visualizar registro de auditória",
    "view_channel": "Ver canal",
    "view_guild_insights": "Ver análises do servidor"
}


