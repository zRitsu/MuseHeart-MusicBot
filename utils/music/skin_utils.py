from __future__ import annotations

import json
import random
from typing import Optional, TYPE_CHECKING

import disnake

from utils.music.converters import fix_characters, time_format

if TYPE_CHECKING:
    from utils.others import CustomContext
    from utils.music.models import LavalinkPlayer

def skin_converter(data: str, ctx: CustomContext = None, player: Optional[LavalinkPlayer] = None) -> dict:

    if player:

        requester = player.guild.get_member(player.current.requester)

        data = data. \
            replace('{track.title_25}', fix_characters(player.current.title, 25)). \
            replace('{track.title_42}', fix_characters(player.current.title, 42)). \
            replace('{track.title_58}', fix_characters(player.current.title, 58)). \
            replace('{track.title}', player.current.title). \
            replace('{track.url}', player.current.uri). \
            replace('{track.author}', str(player.current.author)). \
            replace('{track.duration}', time_format(player.current.duration)). \
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
            replace('{guild.color}', str(player.bot.get_color(player.guild.me).value)). \
            replace('{guild.icon}', player.guild.icon.with_static_format("png").url if player.guild.icon else ""). \
            replace('{guild.name}', player.guild.name). \
            replace('{guild.id}', str(player.guild.id))

    else:

        track_title = 'Sekai - Burn Me Down [NCS Release]'

        data = data.\
            replace('{track.title_25}', fix_characters(track_title, 25)). \
            replace('{track.title_42}', fix_characters(track_title, 42)). \
            replace('{track.title_58}', fix_characters(track_title, 58)). \
            replace('{track.title}', track_title). \
            replace('{track.url}', 'https://youtu.be/B6DmYzyjjMU'). \
            replace('{track.author}', "NoCopyrightSounds"). \
            replace('{track.duration}', '3:35'). \
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
            replace('{guild.color}', str(ctx.bot.get_color(ctx.guild.me).value)). \
            replace('{guild.icon}', ctx.guild.icon.with_static_format("png").url if ctx.guild.icon else ""). \
            replace('{guild.name}', ctx.guild.name). \
            replace('{guild.id}', str(ctx.guild.id))

    data = json.loads(data)

    if embeds := data.get("embeds"):
        for d in embeds:
            try:
                d["color"] = int(d["color"])
            except:
                try:
                    d["color"] = int(d["color"], 16)
                except KeyError:
                    continue

        data["embeds"] = [disnake.Embed.from_dict(e) for e in data.get("embeds")]

    return data
