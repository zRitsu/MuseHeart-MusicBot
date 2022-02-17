from ..models import LavalinkPlayer
import disnake
from ..converters import fix_characters, time_format
import itertools
from ...others import ProgressBar


def load(player: LavalinkPlayer) -> dict:

    data = {
        "content": None,
        "embeds": None
    }

    embed = disnake.Embed(color=player.bot.get_color(player.guild.me))
    embed_queue = None

    if not player.paused:
        embed.set_author(
            name="Tocando Agora:",
            icon_url="https://cdn.discordapp.com/attachments/480195401543188483/895862881105616947/music_equalizer.gif"
        )
    else:
        embed.set_author(
            name="Em Pausa:",
            icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
        )

    embed.set_footer(
        text=str(player),
        icon_url="https://cdn.discordapp.com/attachments/480195401543188483/907119505971486810/speaker-loud-speaker.gif"
    )

    if player.current.is_stream:
        duration = "```ini\n🔴 [Livestream]```"
    else:

        progress = ProgressBar(
            player.position,
            player.current.duration,
            bar_count=20 if  (player.static and player.current.info.get("sourceName") == "youtube") else 10
        )

        duration = f"```ini\n[{time_format(player.position)}] {('='*progress.start)}🔴️{'='*progress.end} " \
                   f"[{time_format(player.current.duration)}]```\n"

    vc_txt = ""

    if player.static:
        queue_size = 20
        queue_text_size = 33
        queue_img = ""
        playlist_text_size = 17
        uploader_text_size = 22

        try:
            vc_txt = f"\n> *️⃣ **⠂Canal de voz:** [`{player.guild.me.voice.channel.name}`](http://discordapp.com/channels/{player.guild.id}/{player.guild.me.voice.channel.id})"
        except AttributeError:
            pass

    else:
        queue_size = 3
        queue_text_size = 31
        queue_img = "https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif"
        playlist_text_size = 11
        uploader_text_size = 17


    txt = f"[`{player.current.title}`]({player.current.uri})\n\n" \
          f"> 💠 **⠂Por:** `{fix_characters(player.current.author, uploader_text_size)}`\n" \
          f"> ✋ **⠂Pedido por:** {player.current.requester.mention}\n" \
          f"> 🔊 **⠂Volume:** `{player.volume}%`"

    if player.current.track_loops:
        txt += f"\n> 🔂 **⠂Repetições restantes:** `{player.current.track_loops}`"

    if player.nightcore:
        txt += f"\n> 🇳 **⠂Efeito nightcore:** `ativado`"

    if player.current.playlist:
        txt += f"\n> 📑 **⠂Playlist:** [`{fix_characters(player.current.playlist['name'], limit=playlist_text_size)}`]({player.current.playlist['url']})"

    if player.nonstop:
        txt += "\n> ♾️ **⠂Modo interrupto:** `Ativado`"

    txt += f"{vc_txt}\n"

    if player.command_log:
        txt += f"> ✅ **⠂Última Interação:** {player.command_log}\n"

    txt += duration

    if len(player.queue):

        queue_txt = "\n".join(
            f"`{n + 1}) [{time_format(t.duration) if t.duration else '🔴 Livestream'}]` [`{fix_characters(t.title, queue_text_size)}`]({t.uri})"
            for n, t in (enumerate(itertools.islice(player.queue, queue_size)))
        )

        embed_queue = disnake.Embed(title=f"Músicas na fila: {len(player.queue)}", color=player.bot.get_color(player.guild.me),
                                    description=f"\n{queue_txt}")
        embed_queue.set_image(url=queue_img)

    embed.description = txt

    if player.static:
        embed.set_image(url=player.current.thumb)
    else:
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif")
        embed.set_thumbnail(url=player.current.thumb)

    data["embeds"] = [embed_queue, embed] if embed_queue else [embed]

    return data
