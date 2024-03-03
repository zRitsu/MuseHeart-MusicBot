# -*- coding: utf-8 -*-
from __future__ import annotations

import itertools
from copy import deepcopy
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
        replace('{track.duration}', time_format(track_duration) if track_duration else "🔴 Ao vivo"). \
        replace('{track.number}', str(track_number))


def replaces(
    txt: str, info: dict, ctx: disnake.MessageInteraction, player: LavalinkPlayer, queue_text: str, track: dict,
        guild: disnake.Guild
):

    if player:

        try:
            if not player.current.autoplay:
                requester = guild.get_member(player.current.requester)
                requester_global_name = requester.global_name
                requester_display_name = requester.display_name
                requester_mention = requester.mention
                requester_avatar = requester.display_avatar.replace(static_format="png", size=512).url
            else:
                requester_global_name = "Recomendação"
                requester_display_name = "Recomendação"
                requester_mention = "Recomendação"
                requester_avatar = guild.me.display_avatar.replace(static_format="png", size=512).url
        except:
            requester_global_name = "Desconhecido..."
            requester_display_name = "Desconhecido..."
            requester_mention = f"<@{player.current.requester}>"
            requester_avatar = "https://i.ibb.co/LNpG5TM/unknown.png"

        txt = track_title_format(
            track_title=player.current.title,
            track_author=player.current.author,
            track_url=player.current.uri,
            track_duration=player.current.duration if not player.current.is_stream else 0,
            data=txt
        ). \
            replace('{track.thumb}', player.current.thumb). \
            replace('{playlist.name}', player.current.playlist_name or "Sem playlist"). \
            replace('{playlist.url}', player.current.playlist_url or player.controller_link). \
            replace('{player.loop.mode}', 'Desativado' if not player.loop else 'Música atual' if player.loop == "current" else "Fila"). \
            replace('{player.queue.size}', str(len(player.queue or player.queue_autoplay))). \
            replace('{player.volume}', str(player.volume)). \
            replace('{player.autoplay}', "Ativado" if player.autoplay else "Desativado"). \
            replace('{player.nightcore}', "Ativado" if player.nightcore else "Desativado"). \
            replace('{player.hint}', player.current_hint). \
            replace('{player.log.text}', player.command_log or "Sem registro."). \
            replace('{player.log.emoji}', player.command_log_emoji or ""). \
            replace('{requester.global_name}', requester_global_name). \
            replace('{requester.display_name}', requester_display_name). \
            replace('{requester.mention}', requester_mention). \
            replace('{requester.avatar}', requester_avatar). \
            replace('{guild.color}', hex(guild.me.color.value)[2:]). \
            replace('{guild.icon}', guild.icon.with_static_format("png").url if guild.icon else ""). \
            replace('{guild.name}', guild.name). \
            replace('{guild.id}', str(guild.id)). \
            replace('{queue_format}', queue_text or "Fila vazia...")

    else:

        queue_max_entries = info.pop("queue_max_entries", 3) or 3

        c = ctx.bot.get_color(guild.me)

        try:
            color = c.value
        except AttributeError:
            color = c

        txt = track_title_format(
            track_title=track['title'],
            track_author=track['author'],
            track_url=track['url'],
            track_duration=track['duration'],
            data=txt
        ). \
            replace('{track.thumb}', "https://img.youtube.com/vi/2vFA0HL9kTk/mqdefault.jpg"). \
            replace('{playlist.name}', "🎵 DV 🎶"). \
            replace('{playlist.url}', "https://www.youtube.com/playlist?list=PLKlXSJdWVVAD3iztmL2vFVrwA81sRkV7n"). \
            replace('{player.loop.mode}', "Música Atual"). \
            replace('{player.queue.size}', f"{queue_max_entries}"). \
            replace('{player.volume}', "100"). \
            replace('{player.autoplay}', "Ativado"). \
            replace('{player.nightcore}', "Ativado"). \
            replace('{player.log.emoji}', "⏭️"). \
            replace('{player.log.text}', f"{ctx.author} pulou a música."). \
            replace('{requester.global_name}', ctx.author.global_name). \
            replace('{requester.display_name}', ctx.author.display_name). \
            replace('{requester.mention}', ctx.author.mention). \
            replace('{requester.avatar}', ctx.author.display_avatar.with_static_format("png").url). \
            replace('{guild.color}', hex(color)[2:]). \
            replace('{guild.icon}', guild.icon.with_static_format("png").url if guild.icon else ""). \
            replace('{guild.name}', guild.name). \
            replace('{guild.id}', str(guild.id)). \
            replace('{queue_format}', queue_text or "(Sem músicas).")

    return txt


def skin_converter(info: dict, guild: disnake.Guild, ctx: Union[CustomContext, disnake.ModalInteraction] = None, player: Optional[LavalinkPlayer] = None) -> dict:

    info = deepcopy(info)

    try:
        if len(str(info["queue_max_entries"])) > 2:
            info["queue_max_entries"] = 7
    except:
        pass

    queue_max_entries = info.pop("queue_max_entries", 7)
    if len(str(queue_max_entries)) > 2:
        queue_max_entries = 7

    track = {}
    queue_format = info.pop("queue_format", "")

    controller_enabled = info.pop("controller_enabled", True)

    if not isinstance(queue_format, str):
        queue_text = ""
    elif player:
        player.controller_mode = controller_enabled
        queue_text = "\n".join(track_title_format(
            track_title=t.title,
            track_author=t.author,
            track_url=t.uri,
            track_duration=t.duration,
            data=queue_format,
            track_number=n + 1
        ) for n, t in enumerate(itertools.islice(player.queue or player.queue_autoplay, queue_max_entries)))
    else:
        track = {
            'title': 'Sekai - Burn Me Down [NCS Release]',
            'author': "NoCopyrightSounds",
            'url': "https://www.youtube.com/watch?v=2vFA0HL9kTk",
            'duration': 215000
        }
        queue_text = "\n".join(track_title_format(
            track_title=t['title'],
            track_author=t['author'],
            track_url=t['url'],
            track_duration=t['duration'],
            data=queue_format,
            track_number=n + 1
        ) for n, t in enumerate([track] * queue_max_entries))

    try:
        if info["content"]:
            info["content"] = replaces(info["content"], info=info, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
    except KeyError:
        pass

    if embeds := info.get("embeds"):

        for d in embeds:
            try:
                d["description"] = replaces(d["description"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            try:
                d["footer"]["text"] = replaces(d["footer"]["text"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            try:
                d["footer"]["icon_url"] = replaces(d["footer"]["icon_url"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            try:
                d["author"]["name"] = replaces(d["author"]["name"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            try:
                d["author"]["url"] = replaces(d["author"]["url"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            try:
                d["author"]["icon_url"] = replaces(d["author"]["icon_url"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            try:
                d["image"]["url"] = replaces(d["image"]["url"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            try:
                d["thumbnail"]["url"] = replaces(d["thumbnail"]["url"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
            except KeyError:
                pass

            for n, f in enumerate(d.get("fields", [])):
                f["name"] = replaces(f["name"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)
                f["value"] = replaces(f["value"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild)

            try:
                d["color"] = int(replaces(d["color"], info=d, ctx=ctx, player=player, queue_text=queue_text, track=track, guild=guild), 16)
            except (KeyError, AttributeError):
                pass

        info["embeds"] = [disnake.Embed.from_dict(e) for e in embeds]

    return info
