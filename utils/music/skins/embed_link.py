import datetime
from typing import Union
import re
import disnake
from ..models import LavalinkPlayer, YTDLPlayer
from ..converters import time_format, fix_characters, get_button_style
from ...others import PlayerControls


def load(player: Union[LavalinkPlayer, YTDLPlayer]) -> dict:

    txt = ""

    if player.current.is_stream:
        duration_txt = f"\n> 🔴 **⠂Duração:** `Livestream`"
    else:
        duration_txt = f"\n> ⏰ **⠂Duração:** `{time_format(player.current.duration)}`"

    if player.paused:
        txt += f"> ⏸️ **⠂Em Pausa:** {player.current.uri}{duration_txt}"

    else:
        txt += f"> ▶️ **⠂Tocando Agora:** {player.current.uri}{duration_txt} `[`<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>`]`"

    if not player.static:

        txt += f" {player.current.requester.mention}\n"

    else:

        txt += f"\n> ✋ **⠂Pedido por:** {player.current.requester.mention}\n"

        if player.current.playlist:
            txt += f"> 📑 **⠂Playlist:** `{fix_characters(player.current.playlist['name'])}`\n"

        try:
            txt += f"> *️⃣ **⠂Canal de voz:** {player.guild.me.voice.channel.mention}\n"
        except AttributeError:
            pass

        if player.current.track_loops:
            txt += f"> 🔂 **⠂Repetições restantes:** `{player.current.track_loops}`\n"

        elif player.loop:
            if player.loop == 'current':
                txt += '> 🔂 **⠂Repetição:** `música atual`\n'
            else:
                txt += '> 🔁 **⠂Repetição:** `fila`\n'

        if queue_size:=len(player.queue):
            txt += f"> 🎼 **⠂Músicas na fila:** `{queue_size}`\n"

    if player.command_log:

        log = re.sub(r"\[(.+)]\(.+\)", r"\1", player.command_log.replace("`", "")) # remover links do command_log p/ evitar gerar mais de uma preview.

        txt += f"> {player.command_log_emoji} **⠂Última Interação:** {log}\n"

    if player.current_hint:
        txt += f"> `╔══════💡DICA💡══════╗`\n> `{player.current_hint}`"

    if player.auto_update:
        player.auto_update = 0

    return {
        "content": txt,
        "embeds": [],
        "components": [
            disnake.ui.Button(emoji="⏸️", custom_id=PlayerControls.pause, label="Pausar") if not player.paused else
            disnake.ui.Button(emoji="▶️", custom_id=PlayerControls.resume, label="Retomar", style=disnake.ButtonStyle.red),
            disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back, label="Voltar"),
            disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip, label="Pular"),
            disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop, label="Parar"),
            disnake.ui.Button(emoji="🎶", custom_id=PlayerControls.add_song, label="Adicionar"),
            disnake.ui.Select(
                placeholder="Mais opções:",
                custom_id="musicplayer_dropdown_1",
                min_values=0, max_values=1,
                options=[
                    disnake.SelectOption(
                        label="Tocar do inicio", emoji="⏪",
                        value=PlayerControls.seek_to_start,
                        description="Tocar a música desde o inicio."
                    ),
                    disnake.SelectOption(
                        label="Misturar", emoji="🔀",
                        value=PlayerControls.shuffle,
                        description="Misturar as músicas da fila."
                    ),
                    disnake.SelectOption(
                        label="Readicionar", emoji="<:add_music:588172015760965654>",
                        value=PlayerControls.readd,
                        description="Readicionar as músicas tocadas de volta na fila."
                    ),
                    disnake.SelectOption(
                        label="Músicas na fila", emoji="📑",
                        value=PlayerControls.queue,
                        description="Listar as músicas que estão na fila."
                    ),
                    disnake.SelectOption(
                        label="Player config.", emoji="🛠️",
                        value=PlayerControls.settings,
                        description="Alterar algumas configurações do player."
                    ),
                ]
            ),
        ]
    }
