import datetime
import itertools
import re
import disnake
from utils.music.models import LavalinkPlayer
from utils.music.converters import time_format, fix_characters


class EmbedLinkStaticSkin:
    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = "embed_link_static"
        self.preview = "https://cdn.discordapp.com/attachments/554468640942981147/1047187413325324319/embed_link_static_skin.png"

    def load(self, player: LavalinkPlayer) -> dict:

        txt = ""

        if player.current_hint:
            txt += f"> `💡 Dica: {player.current_hint}`\n> \n"

        if player.current.is_stream:
            duration_txt = f"\n> 🔴 **⠂Duração:** `Livestream`"
        else:
            duration_txt = f"\n> ⏰ **⠂Duração:** `{time_format(player.current.duration)}`"

        if player.paused:
            txt += f"> ⏸️ **⠂Em Pausa:** {player.current.uri}{duration_txt}"

        else:
            txt += f"> ▶️ **⠂Tocando Agora:** {player.current.uri}{duration_txt}"
            if not player.current.is_stream:
                txt += f" `[`<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>`]`"

        txt += f"\n> ✋ **⠂Pedido por:** <@{player.current.requester}>\n"

        if player.current.playlist_name:
            txt += f"> 📑 **⠂Playlist:** `{fix_characters(player.current.playlist_name)}`\n"

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

        if player.command_log:

            log = re.sub(r"\[(.+)]\(.+\)", r"\1", player.command_log.replace("`", "")) # remover links do command_log p/ evitar gerar mais de uma preview.

            txt += f"> {player.command_log_emoji} **⠂Última Interação:** {log}\n"

        if qsize := len(player.queue):

            qtext = "**Músicas na fila:**\n```ansi\n" + \
                              "\n".join(
                                  f"[0;33m{(n + 1):02}[0m [0;34m[{time_format(t.duration) if not t.is_stream else '🔴 stream'}][0m [0;36m{fix_characters(t.title, 45)}[0m"
                                  for n, t in enumerate(
                                      itertools.islice(player.queue, 4)))

            if qsize  > 4:
                qtext += f"\n╚═ [0;37mE mais[0m [0;35m{qsize}[0m [0;37mmúsicas(s).[0m"

            txt = qtext + "```\n" + txt

        if player.auto_update:
            player.auto_update = 0

        return {
            "content": txt,
            "embeds": [],
        }

def load():
    return EmbedLinkStaticSkin()
