import datetime
from typing import Union
import re
import disnake
from ..models import LavalinkPlayer, YTDLPlayer
from ..converters import time_format


def load(player: Union[LavalinkPlayer, YTDLPlayer]) -> dict:

    txt = ""

    if player.current.is_stream:
        duration_txt = f"\n🔴 **Duração:** `Livestream`"
    else:
        duration_txt = f"\n⏰ **Duração:** `{time_format(player.current.duration)}`"

    if player.paused:
        txt += f"⏸️ **Em Pausa:** {player.current.uri}{duration_txt}"

    else:
        txt += f"▶️ **Tocando Agora:** {player.current.uri}{duration_txt} `[`<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>`]`"

    if not player.static:

        txt += f" {player.current.requester.mention}\n"

    else:

        txt += f"\n✋ **Pedido por:** {player.current.requester.mention}\n" \
               f"🔊 **Volume:** `{player.volume}%`\n"

        try:
            txt += f"*️⃣ **Canal de voz:** {player.guild.me.voice.channel.mention}\n"
        except AttributeError:
            pass

        if player.current.track_loops:
            txt += f"🔂 **Repetições restantes:** `{player.current.track_loops}`\n"

        elif player.loop:
            if player.loop == 'current':
                txt += '🔂 **Repetição:** `música atual`\n'
            else:
                txt += '🔁 **Repetição:** `fila`\n'

        if queue_size:=len(player.queue):
            txt += f"🎼 **Músicas na fila:** `{queue_size}`\n"

    if player.command_log:

        log = re.sub(r"\[(.+)]\(.+\)", r"\1", player.command_log.replace("`", "")) # remover links do command_log p/ evitar gerar mais de uma preview.

        txt += f"`[=================]`\n{player.command_log_emoji} **Última Interação:** {log}\n"

    if player.current_hint:
        txt += f"`[=================]`\n`💡 Dica: {player.current_hint}`"

    if player.auto_update:
        player.auto_update = 0

    return {"content": txt, "embeds": []}
