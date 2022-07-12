import datetime
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

    embed = disnake.Embed(color=player.bot.get_color(player.guild.me))

    if not player.static:

        duration = "`🔴 Livestream`" if player.current.is_stream else \
            time_format(player.current.duration)

        embed.description = f"**Tocando Agora:** [`{player.current.title}`]({player.current.uri})\n" \
                            f"**Duração:** `{duration}` ┃ **Uploader:** `{fix_characters(player.current.author, 18)}`\n" \
                            f"**Pedido por:** {player.current.requester.mention}"

        if player.current.playlist:
            embed.description += f" ┃ **Playlist:** [`{player.current.playlist['name']}`]({player.current.playlist['url']})"

        embed.set_thumbnail(url=player.current.thumb)

        if player.current_hint:
            embed.set_image(url="https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif")
            embed.set_footer(text=f"💡 Dica: {player.current_hint}")

        data["embeds"] = [embed]

        if player.controller_mode:
            player.hint_rate = 9
            player.controller_mode = False

    else:

        embed_queue = None
        position_txt = ""
        vc_txt = ""

        if not player.paused:
            embed.set_author(
                name="Tocando Agora:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/895862881105616947/music_equalizer.gif"
            )

            if not player.current.is_stream:
                position_txt = f"\n> ⏲️ **⠂Termina:** " f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>"

        else:
            embed.set_author(
                name="Em Pausa:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        if player.current_hint:
            embed.set_footer(text=f"💡 Dica: {player.current_hint}")
        else:
            embed.set_footer(
                text=str(player),
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/907119505971486810/speaker-loud-speaker.gif"
            )

        queue_text_size = 31
        queue_img = "https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif"
        playlist_text_size = 13

        duration = "> 🔴 **⠂Duração:** `Livestream`" if player.current.is_stream else \
            f"> ⏰ **⠂Duração:** `{time_format(player.current.duration)}`"

        txt = f"[`{player.current.single_title}`]({player.current.uri})\n\n" \
              f"{duration}\n" \
              f"> 💠 **⠂Por:** {player.current.authors_md}\n" \
              f"> ✋ **⠂Pedido por:** {player.current.requester.mention}\n" \
              f"> 🔊 **⠂Volume:** `{player.volume}%`"

        if player.current.track_loops:
            txt += f"\n> 🔂 **⠂Repetições restante:** `{player.current.track_loops}`"

        if player.loop:
            if player.loop == 'current':
                e = '🔂'; m = 'Música atual'
            else:
                e = '🔁'; m = 'Fila'
            txt += f"\n> {e} **⠂Modo de repetição:** `{m}`"

        if player.nightcore:
            txt += f"\n> 🇳 **⠂Efeito nightcore:** `ativado`"

        if player.current.album:
            txt += f"\n> 💽 **⠂Álbum:** [`{fix_characters(player.current.album['name'], limit=playlist_text_size)}`]({player.current.album['url']})"

        if player.current.playlist:
            txt += f"\n> 📑 **⠂Playlist:** [`{fix_characters(player.current.playlist['name'], limit=playlist_text_size)}`]({player.current.playlist['url']})"

        if player.nonstop:
            txt += "\n> ♾️ **⠂Modo interrupto:** `Ativado`"

        if player.restrict_mode:
            txt += f"\n> 🔒 **⠂Modo restrito:** `Ativado`"

        txt += f"{vc_txt}{position_txt}\n"

        if player.command_log:
            txt += f"```ini\n [Última Interação]```**┕ {player.command_log_emoji} ⠂**{player.command_log}\n"

        if len(player.queue):

            queue_txt = "\n".join(
                f"`{n + 1}) [{time_format(t.duration) if not t.is_stream else '🔴 Livestream'}]` [`{fix_characters(t.title, queue_text_size)}`]({t.uri})"
                for n, t in (enumerate(itertools.islice(player.queue, 15)))
            )

            embed_queue = disnake.Embed(title=f"Músicas na fila: {len(player.queue)}", color=player.bot.get_color(player.guild.me),
                                        description=f"\n{queue_txt}")

            if not player.nonstop:

                queue_duration = 0

                for t in player.queue:
                    if not t.is_stream:
                        queue_duration += t.duration

                embed_queue.description += f"\n`[⌛ As músicas acabam` <t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=(queue_duration + player.current.duration) - player.position)).timestamp())}:R> `⌛]`"

            embed_queue.set_image(url=queue_img)

        embed.description = txt
        embed.set_image(url="https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif")
        embed.set_thumbnail(url=player.current.thumb)

        if player.auto_update:
            player.auto_update = 0

        if not player.controller_mode:
            player.controller_mode = True

        data["embeds"] = [embed_queue, embed] if embed_queue else [embed]

    return data
