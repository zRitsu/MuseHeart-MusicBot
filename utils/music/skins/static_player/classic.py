from utils.music.models import LavalinkPlayer
import disnake
from utils.music.converters import fix_characters, time_format
import itertools


class ClassicStaticSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = "classic_static"
        self.preview = "https://media.discordapp.net/attachments/554468640942981147/1047187412343853146/classic_static_skin.png"

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        embed = disnake.Embed(color=player.bot.get_color(player.guild.me), description="")

        queue_txt = ""

        embed.description = f"[**{player.current.title}**]({player.current.uri})\n\n"
        embed.set_image(url=player.current.thumb)
        embed_top = None
        player.mini_queue_feature = False
        player.mini_queue_enabled = True

        if not player.paused:
            (embed_top or embed).set_author(
                name="Tocando Agora:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/895862881105616947/music_equalizer.gif"
            )
        else:
            (embed_top or embed).set_author(
                name="Em Pausa:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        if player.current.is_stream:
            duration = "🔴 **⠂Livestream**"
        else:
            duration = f"⏰ **⠂Duração:** `{time_format(player.current.duration)}`"

        txt = f"{duration}\n" \
              f"💠 **⠂Uploader:** `{player.current.author}`\n" \
              f"🎧 **⠂Pedido por:** <@{player.current.requester}>\n" \

        if player.current.playlist_name:
            txt += f"📑 **⠂Playlist:** [`{fix_characters(player.current.playlist_name, limit=20)}`]({player.current.playlist_url})\n"

        txt += f"🔊 **⠂Volume:** `{player.volume}%`\n"

        if player.restrict_mode:
            txt += "🔒 **⠂Modo restrito:** `ativado`\n"

        if qsize := len(player.queue):

            data["content"] = "**Músicas na fila:**\n```ansi\n" + \
                              "\n".join(f"[0;33m{(n+1):02}[0m [0;34m[{time_format(t.duration) if not t.is_stream else '🔴 stream'}][0m [0;36m{fix_characters(t.title, 45)}[0m" for n, t in enumerate(
                                  itertools.islice(player.queue, 15)))

            if qsize > 15:
                data["content"] += f"\n\n[0;37mE mais[0m [0;35m{qsize}[0m [0;37mmúsicas(s).[0m"

            data["content"] += "```"

        if player.command_log:
            txt += f"{player.command_log_emoji} **⠂Última Interação:** {player.command_log}\n"

        embed.description += txt + queue_txt

        if player.current_hint:
            embed.set_footer(text=f"💡 Dica: {player.current_hint}")

        data["embeds"] = [embed_top, embed] if embed_top else [embed]

        return data

def load():
    return ClassicStaticSkin()
