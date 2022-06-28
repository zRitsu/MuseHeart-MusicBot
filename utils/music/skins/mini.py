import datetime
import itertools
from typing import Union
from ..models import LavalinkPlayer, YTDLPlayer
import disnake
from ..converters import time_format, fix_characters, get_button_style
from ...others import PlayerControls


def load(player: Union[LavalinkPlayer, YTDLPlayer]) -> dict:

    data = {
        "content": None,
        "embeds": [],
        "components": []
    }

    embed = disnake.Embed(
        color=player.bot.get_color(player.guild.me),
        description=f"[`{player.current.single_title}`]({player.current.uri})"
    )
    embed_queue = None
    queue_size = len(player.queue)

    if not player.paused:
        embed.set_author(
            name="Tocando Agora:",
            icon_url="https://media.discordapp.net/attachments/480195401543188483/987633257178882108/Equalizer.gif",
        )

    else:
        embed.set_author(
            name="Em Pausa:",
            icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
        )

    if player.static:

        embed.set_image(url=player.current.thumb or "https://media.discordapp.net/attachments/480195401543188483/987830071815471114/musicequalizer.gif")

        if queue_size:

            queue_txt = "\n".join(
                f"`{n + 1}) [{time_format(t.duration) if not t.is_stream else '🔴 Livestream'}]` [`{fix_characters(t.title, 29)}`]({t.uri})"
                for n, t in (enumerate(itertools.islice(player.queue, 15)))
            )

            embed_queue = disnake.Embed(title=f"Músicas na fila: {len(player.queue)}",
                                        color=player.bot.get_color(player.guild.me),
                                        description=f"\n{queue_txt}")

            if not player.nonstop:

                queue_duration = 0

                for t in player.queue:
                    if not t.is_stream:
                        queue_duration += t.duration

                embed_queue.description += f"\n`[⌛ As músicas acabam` <t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=(queue_duration + player.current.duration) - player.position)).timestamp())}:R> `⌛]`"

    else:
        if queue_size:
            embed.description += f" `({queue_size})`"
        embed.set_thumbnail(url=player.current.thumb)
        embed.set_image(url="https://cdn.discordapp.com/attachments/554468640942981147/937918500784197632/rainbow_bar.gif")

    if player.current.is_stream:
        embed.add_field(name="**Duração:**", value="`🔴 Livestream`", inline=True)
    else:
        embed.add_field(name="**Duração:**", value=f"`{time_format(player.current.duration)}`", inline=True)

    embed.add_field(name="**Uploader:**", value=f"{player.current.authors_md}", inline=True)
    embed.add_field(name="**Adc. por:**", value=f"{player.current.requester.mention}", inline=True)

    if player.current.track_loops:
        embed.description += f" `[🔂 {player.current.track_loops}]`"

    elif player.loop:
        if player.loop == 'current':
            embed.description += ' `[🔂 música atual]`'
        else:
            embed.description += ' `[🔁 fila]`'

    if player.command_log:
        embed.add_field(name=f"{player.command_log_emoji} **⠂Última Interação:**", value=f"╚ {player.command_log}")

    if player.current_hint:
        embed.set_footer(text=f"💡 Dica: {player.current_hint}")

    if player.auto_update:
        player.auto_update = 0

    data["embeds"] = [embed_queue, embed] if embed_queue else [embed]

    data["components"].extend(
        [
            disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
            disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
            disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
            disnake.ui.Button(emoji="🎶", custom_id=PlayerControls.add_song),
            disnake.ui.Select(
                placeholder="Mais opções:",
                custom_id="musicplayer_dropdown_inter",
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
    )

    return data
