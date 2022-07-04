from typing import Union
from ..models import LavalinkPlayer, YTDLPlayer
import disnake
from ..converters import fix_characters, time_format
import itertools


def load(player: Union[LavalinkPlayer, YTDLPlayer]) -> dict:

    data = {
        "content": None,
        "embeds": []
    }

    embed = disnake.Embed(color=player.bot.get_color(player.guild.me), description="")

    if not player.static:
        embed_top = disnake.Embed(
            color=player.bot.get_color(player.guild.me),
            description=f"> [**{player.current.title}**]({player.current.uri})"
        )
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif"
        )

        embed_top.set_image(
            url="https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif"
        )

        embed_top.set_thumbnail(url=player.current.thumb)

    else:
        embed.description = f"[**{player.current.title}**]({player.current.uri})\n\n"
        embed.set_image(url=player.current.thumb.replace("mqdefault.jpg", "hqdefault.jpg"))
        embed_top = None

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
          f"💠 **⠂Uploader**: `{player.current.author}`\n" \
          f"🎧 **⠂Pedido por:** {player.current.requester.mention}\n" \
          f"🔊 **⠂Volume:** `{player.volume}%`"

    txt += "\n"

    if player.restrict_mode:
        txt += "🔒 **⠂Modo restrito: `ativado`\n"

    if player.command_log:
        txt += f"{player.command_log_emoji} **⠂Última Interação:** {player.command_log}\n"

    if len(player.queue):

        if player.static:

            data["content"] = "**Músicas na fila:**\n```ini\n" + \
                              "\n".join(f"{n+1}) [{time_format(t.duration) if not t.is_stream else '🔴 stream'}] - {fix_characters(t.title, 45)}" for n, t in enumerate(
                                  itertools.islice(player.queue, 30)))

            if (qsize := len(player.queue)) > 30:
                data["content"] += f"\n\nE mais [{qsize}] músicas(s)."

            data["content"] += "```"

        else:
            txt += "```ldif\nPróximas Músicas:```" + "\n".join(
                f"`{n + 1}) [{time_format(t.duration) if t.duration else '🔴 Livestream'}]` "
                f"[`{fix_characters(t.title, 31)}`]({t.uri})" for n, t in enumerate(itertools.islice(player.queue, 3))
            )

            if (qsize := len(player.queue)) > 3:
                txt += f"\n`╚══════ E mais {qsize - 3} música(s) ══════╝`"

    embed.description += txt

    if player.current_hint:
        embed.set_footer(text=f"💡 Dica: {player.current_hint}")

    data["embeds"] = [embed_top, embed] if embed_top else [embed]

    return data
