from __future__ import annotations

import itertools
import json
import random
from typing import Optional, TYPE_CHECKING, Union

import disnake

from utils.music.converters import fix_characters, time_format

if TYPE_CHECKING:
    from utils.others import CustomContext
    from utils.music.models import LavalinkPlayer

def track_title_format(
        track_title: str,
        track_author: str,
        track_url: str,
        track_duration: Union[int, float],
        data: str,
        track_number: int = 0
):

    return data. \
        replace('{track.title_25}', fix_characters(track_title, 25)). \
        replace('{track.title_42}', fix_characters(track_title, 42)). \
        replace('{track.title_58}', fix_characters(track_title, 58)). \
        replace('{track.title}', track_title). \
        replace('{track.url}', track_url). \
        replace('{track.author}', track_author). \
        replace('{track.duration}', time_format(track_duration)). \
        replace('{track.number}', str(track_number))


def skin_converter(data: str, ctx: CustomContext = None, player: Optional[LavalinkPlayer] = None) -> dict:

    info = json.loads(data)

    if player:

        requester = player.guild.get_member(player.current.requester)

        queue_max_entries = info.pop("queue_max_entries", 3) or 3

        queue_text = ""

        if (queue_format:=info.pop("queue_format", "")):
            queue_text = "\n".join(track_title_format(
                track_title=t.title,
                track_author=t.author,
                track_url=t.uri,
                track_duration=t.duration,
                data=queue_format,
                track_number=n+1
            ) for n, t in enumerate(itertools.islice(player.queue, queue_max_entries)))

        data = track_title_format(
            track_title=player.current.title,
            track_author=player.current.author,
            track_url=player.current.uri,
            track_duration=player.current.duration,
            data=data
        ). \
            replace('{track.thumb}', player.current.thumb). \
            replace('{playlist.name}', player.current.playlist_name or "Nenhuma"). \
            replace('{playlist.url}', player.current.playlist_url). \
            replace('{player.loop.mode}', 'Desativado' if not player.loop else 'Música atual' if player.loop == "current" else "Fila"). \
            replace('{player.queue.size}', str(len(player.queue))). \
            replace('{player.volume}', str(player.volume)). \
            replace('{player.log.text}', player.command_log or "Sem registro."). \
            replace('{player.log.emoji}', player.command_log_emoji or ""). \
            replace('{requester.mention}', f'<@{player.current.requester}>'). \
            replace('{requester.avatar}', requester.display_avatar.with_static_format("png").url). \
            replace('{requester.tag}', f"{requester.display_name}#{requester.discriminator}"). \
            replace('{guild.color}', hex(player.bot.get_color(player.guild.me).value)[2:]). \
            replace('{guild.icon}', player.guild.icon.with_static_format("png").url if player.guild.icon else ""). \
            replace('{guild.name}', player.guild.name). \
            replace('{guild.id}', str(player.guild.id)). \
            replace('{queue_format}', queue_text or "Sem músicas.")

    else:

        queue_max_entries = info.pop("queue_max_entries", 3) or 3

        queue_text = ""

        track = {
            'title': 'Sekai - Burn Me Down [NCS Release]',
            'author': "NoCopyrightSounds",
            'url': "https://youtu.be/B6DmYzyjjMU",
            'duration': 215000
        }

        if (queue_format:=info.pop("queue_format", "")):
            queue_text = "\n".join(track_title_format(
                track_title=t['title'],
                track_author=t['author'],
                track_url=t['url'],
                track_duration=t['duration'],
                data=queue_format,
                track_number=n+1
            ) for n, t in enumerate([track] * queue_max_entries))

        data = track_title_format(
            track_title=track['title'],
            track_author=track['author'],
            track_url=track['url'],
            track_duration=track['duration'],
            data=data
        ). \
            replace('{track.thumb}', "https://img.youtube.com/vi/2vFA0HL9kTk/mqdefault.jpg"). \
            replace('{playlist.name}', "🎵 DV 🎶"). \
            replace('{playlist.url}', "https://www.youtube.com/playlist?list=PLKlXSJdWVVAD3iztmL2vFVrwA81sRkV7n"). \
            replace('{player.loop.mode}', "Música Atual"). \
            replace('{player.queue.size}', "6"). \
            replace('{player.volume}', "100"). \
            replace('{player.log.emoji}', "⏭️"). \
            replace('{player.log.text}', f"{random.choice(ctx.guild.members)} pulou a música."). \
            replace('{requester.mention}', ctx.author.mention). \
            replace('{requester.avatar}', ctx.author.display_avatar.with_static_format("png").url). \
            replace('{requester.tag}', f"{ctx.author.display_name}#{ctx.author.discriminator}"). \
            replace('{guild.color}', hex(ctx.bot.get_color(ctx.guild.me).value)[2:]). \
            replace('{guild.icon}', ctx.guild.icon.with_static_format("png").url if ctx.guild.icon else ""). \
            replace('{guild.name}', ctx.guild.name). \
            replace('{guild.id}', str(ctx.guild.id)). \
            replace('{queue_format}', queue_text or "Sem músicas.")

    data = json.loads(data, strict=False)

    for d in ("queue_format", "queue_max_entries", "player_features"):
        try:
            del data[d]
        except KeyError:
            continue

    if embeds := data.get("embeds"):
        for d in embeds:
            try:
                d["color"] = int(d["color"], 16)
            except KeyError:
                continue

        data["embeds"] = [disnake.Embed.from_dict(e) for e in embeds]

    return data
