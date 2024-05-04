# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from utils.music.converters import fix_characters
from utils.music.errors import GenericError
from utils.music.models import PartialTrack, PartialPlaylist

if TYPE_CHECKING:
    from utils.client import BotCore

deezer_regex = re.compile(r"(https?://)?(www\.)?deezer\.com/(?P<countrycode>[a-zA-Z]{2}/)?(?P<type>track|album|playlist|artist|profile)/(?P<identifier>[0-9]+)")

async def process_deezer(bot: BotCore, requester: int, query: str):

    if not bot.pool.config["FORCE_USE_DEEZER_CLIENT"] and [n for n in bot.music.nodes.values() if "deezer" in n.info.get("sourceManagers", [])]:
        return

    if query.startswith("https://deezer.page.link/"):
        async with bot.session.get(query, allow_redirects=False) as r:
            if 'location' not in r.headers:
                raise GenericError("**Falha ao obter resultado para o link informado...**")
            query = str(r.headers["location"])

    if not (matches := deezer_regex.match(query)):
        return

    url_type, url_id = matches.groups()[-2:]

    if url_type == "track":

        result = await bot.loop.run_in_executor(None, lambda: bot.pool.deezer.get_track(int(url_id)))

        t = PartialTrack(
            uri=result.link,
            author=result.artist.name,
            title=result.title,
            thumb=f"https://e-cdns-images.dzcdn.net/images/cover/{result.md5_image}/500x500-000000-80-0-0.jpg",
            duration=result.duration * 1000,
            source_name="deezer",
            identifier=url_id,
            requester=requester
        )

        t.info["isrc"] = result.isrc
        t.info["extra"]["authors_md"] = f"[`{fix_characters(result.artist.name)}`]({result.artist.link})"
        t.info["extra"]["artist_id"] = result.artist.id

        if result.album.title != result.title:
            t.info["extra"]["album"] = {
                "name": result.album.title,
                "url": result.album.link
            }

        return [t]

    data = {
        'loadType': 'PLAYLIST_LOADED',
        'playlistInfo': {'name': ''},
        'sourceName': "deezer",
        'tracks_data': [],
        'is_album': False,
        "thumb": ""
    }

    if url_type == "album":

        result = await bot.loop.run_in_executor(None, lambda: bot.pool.deezer.get_album(int(url_id)))

        if len(result.tracks) > 1:
            data["playlistInfo"]["is_album"] = True
            tracks_data = result.tracks

        else:
            result_track = result.tracks[0]

            t = PartialTrack(
                uri=result_track.link,
                author=result_track.artist.name,
                title=result_track.title,
                thumb=f"https://e-cdns-images.dzcdn.net/images/cover/{result.md5_image}/500x500-000000-80-0-0.jpg",
                duration=result_track.duration * 1000,
                source_name="deezer",
                identifier=result_track.id,
                requester=requester
            )

            t.info["isrc"] = result_track.isrc
            t.info["extra"]["authors_md"] = f"[`{fix_characters(result_track.artist.name)}`]({result_track.artist.link})"
            t.info["extra"]["artist_id"] = result.artist.id

            if result.name != result_track.title:
                t.info["extra"]["album"] = {
                    "name": result.title,
                    "url": result.link
                }

            return [t]

    elif url_type == "artist":

        result = await bot.loop.run_in_executor(None, lambda: bot.pool.deezer.get_artist(int(url_id)))
        data["playlistInfo"]["name"] = f"As mais tocadas de: {result.name}"
        tracks_data = result.tracks

    elif url_type == "playlist":
        result = await bot.loop.run_in_executor(None, lambda: bot.pool.deezer.get_playlist(int(url_id)))
        data["playlistInfo"]["name"] = result.title
        data["playlistInfo"]["thumb"] = result.picture_big
        tracks_data = result.tracks

    else:
        raise GenericError(f"**Link do deezer não reconhecido/suportado:**\n{query}")

    if not tracks_data:
        raise GenericError("**Não houve resultados no link do spotify informado...**")

    data["playlistInfo"]["selectedTrack"] = -1
    data["playlistInfo"]["type"] = url_type

    playlist = PartialPlaylist(data, url=query)

    for t in tracks_data:

        track = PartialTrack(
            uri=t.link,
            author=t.artist.name,
            title=t.title,
            thumb=f"https://e-cdns-images.dzcdn.net/images/cover/{t.md5_image}/500x500-000000-80-0-0.jpg",
            duration=t.duration * 1000,
            source_name="deezer",
            identifier=url_id,
            requester=requester
        )

        track.info["isrc"] = t.isrc
        track.info["extra"]["authors_md"] = f"[`{fix_characters(t.artist.name)}`]({t.artist.link})"
        track.info["extra"]["artist_id"] = t.artist.id

        if t.album.title != t.title:
            track.info["extra"]["album"] = {
                "name": t.album.title,
                "url": t.album.link
            }

        playlist.tracks.append(track)

    return playlist
