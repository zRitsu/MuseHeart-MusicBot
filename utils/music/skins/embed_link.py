from typing import Union
import disnake
import re
from ..models import LavalinkPlayer, YTDLPlayer
from ..converters import time_format


def load(player: Union[LavalinkPlayer, YTDLPlayer]) -> dict:

    txt = ""

    if not player.paused:
        txt += "▶️ **Tocando Agora:** "

    else:
        txt += "⏸️ **Em Pausa:** "

    txt += player.current.uri

    if player.current.is_stream:
        txt += f"\n🔴 **Duração:** `Livestream`\n"
    else:
        txt += f"\n⏰ **Duração:** `{time_format(player.current.duration)}`\n"

    txt += f"✋ **Pedido por:** {player.current.requester.mention}\n" \
           f"🔊 **Volume:** `{player.volume}%`\n"

    if player.current.track_loops:
        txt += f"🔂 **Repetições restantes:** `{player.current.track_loops}\n`"

    elif player.loop:
        if player.loop == 'current':
            txt += '🔂 **Repetição:** `música atual`\n'
        else:
            txt += '🔁 **Repetição:** `fila`\n'

    if queue_size:=len(player.queue):
        txt += f"🎼 **Músicas na fila:** `({queue_size})`\n"

    if player.command_log:

        log = re.sub(r"\[(.+)\]\(.+\)", r"\1", player.command_log) # remover links do command_log p/ evitar gerar mais de uma preview.

        txt += f"```ini\n" \
               f"[Última Interação]:``` " \
               f"{player.command_log_emoji} {log}\n"

    if player.current_hint:
        txt += f"```ini\n[Dica]:``` `{player.current_hint}`"

    return {"content": txt, "embeds": []}
