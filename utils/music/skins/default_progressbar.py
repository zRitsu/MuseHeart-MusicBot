from datetime import timedelta
from ..models import LavalinkPlayer
import disnake
from ..converters import fix_characters, time_format
import itertools
from ...others import ProgressBar


def load(player: LavalinkPlayer) -> dict:

    data = {
        "content": None,
        "embeds": []
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
        duration = "```ansi\n🔴 [31;1m Livestream[0m```"
    else:

        progress = ProgressBar(
            player.position,
            player.current.duration,
            bar_count=8 if not player.static else 17
        )

        duration = f"```ansi\n[34;1m[{time_format(player.position)}] {('='*progress.start)}[0m🔴️[36;1m{'-'*progress.end} " \
                   f"[{time_format(player.current.duration)}][0m```\n"

    vc_txt = ""

    if player.static:
        queue_size = 20
        queue_text_size = 33
        queue_img = ""
        playlist_text_size = 20

        try:
            vc_txt = f"\n> *️⃣ **⠂Canal de voz:** [`{player.guild.me.voice.channel.name}`](http://discordapp.com/channels/{player.guild.id}/{player.guild.me.voice.channel.id})"
        except AttributeError:
            pass

    else:
        queue_size = 3
        queue_text_size = 30
        queue_img = "https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif"
        playlist_text_size = 13

    txt = f"[`{player.current.single_title}`]({player.current.uri})\n\n" \
          f"> 💠 **⠂Por:** {player.current.authors_md}\n" \
          f"> ✋ **⠂Pedido por:** <@{player.current.requester}>\n" \
          f"> 🔊 **⠂Volume:** `{player.volume}%`"

    if player.current.track_loops:
        txt += f"\n> 🔂 **⠂Repetições restante:** `{player.current.track_loops}`"

    if player.loop:
        if player.loop == 'current':
            e = '🔂'
            m = 'Música atual'
        else:
            e = '🔁'
            m = 'Fila'
        txt += f"\n> {e} **⠂Modo de repetição:** `{m}`"

    if player.nightcore:
        txt += f"\n> 🇳 **⠂Efeito nightcore:** `ativado`"

    if player.current.album_name:
        txt += f"\n> 💽 **⠂Álbum:** [`{fix_characters(player.current.album_name, limit=playlist_text_size)}`]({player.current.album_url})"

    if player.current.playlist_name:
        txt += f"\n> 📑 **⠂Playlist:** [`{fix_characters(player.current.playlist_name, limit=playlist_text_size)}`]({player.current.playlist_url})"

    if player.keep_connected:
        txt += "\n> ♾️ **⠂Modo 24/7:** `Ativado`"

    elif player.restrict_mode:
        txt += f"\n> 🔒 **⠂Modo restrito:** `Ativado`"

    if player.ping:
        txt += f"\n> 📶 **⠂Latência:** `{player.ping}ms`"

    txt += f"{vc_txt}\n"

    if player.command_log:
        txt += f"> {player.command_log_emoji} **⠂Última Interação:** {player.command_log}\n"

    txt += duration

    if len(player.queue):

        queue_txt = "\n".join(
            f"`{(n + 1):02}) [{time_format(t.duration) if not t.is_stream else '🔴 Livestream'}]` [`{fix_characters(t.title, queue_text_size)}`]({t.uri})"
            for n, t in (enumerate(itertools.islice(player.queue, queue_size)))
        )

        embed_queue = disnake.Embed(title=f"Músicas na fila: {len(player.queue)}", color=player.bot.get_color(player.guild.me),
                                    description=f"\n{queue_txt}")

        if not player.loop and not player.keep_connected:

            queue_duration = 0

            for t in player.queue:
                if not t.is_stream:
                    queue_duration += t.duration

            embed_queue.description += f"\n`[⌛ As músicas acabam` <t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=(queue_duration + (player.current.duration if not player.current.is_stream else 0)) - player.position)).timestamp())}:R> `⌛]`"

        embed_queue.set_image(url=queue_img)

    embed.description = txt

    if player.static:
        embed.set_image(url=player.current.thumb)
    else:
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif")
        embed.set_thumbnail(url=player.current.thumb)

    data["embeds"] = [embed_queue, embed] if embed_queue else [embed]

    if not player.auto_update:
        player.auto_update = 15 # tempo em segundos para atualizar

    return data
