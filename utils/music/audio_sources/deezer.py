# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from aiohttp import ClientSession
from cachetools import TTLCache
from rapidfuzz import fuzz

from utils.music.converters import fix_characters, URL_REG
from utils.music.errors import GenericError
from utils.music.models import LavalinkTrack, LavalinkPlaylist
from utils.music.track_encoder import encode_track

deezer_regex = re.compile(r"(https?://)?(www\.)?deezer\.com/(?P<countrycode>[a-zA-Z]{2}/)?(?P<type>track|album|playlist|artist|profile)/(?P<identifier>[0-9]+)")


class DeezerClient:

    base_url = "https://api.deezer.com"
    
    def __init__(self, cache: Optional[TTLCache] = None):
        self.cache = cache or TTLCache(maxsize=700, ttl=86400)

    async def request(self, path: str, params: dict = None):

        async with ClientSession() as session:
            async with session.get(f"{self.base_url}/{path}", params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    response.raise_for_status()

    async def get_track_info(self, track_id):
        return await self.request(path=f"track/{track_id}")

    async def get_album_info(self, album_id):
        return await self.request(path=f"album/{album_id}")

    async def get_artist_top(self, artist_id, limit=50):
        return await self.request(path=f"artist/{artist_id}/top?limit={limit}")

    async def get_playlist_info(self, playlist_id):
        return await self.request(path=f"playlist/{playlist_id}")

    async def get_user_playlists(self, user_id: int):
        return (await self.request(path=f'user/{user_id}/playlists'))['data']

    async def get_user_info(self, user_id: int):
        return await self.request(path=f"user/{user_id}")

    async def get_artist_radio_info(self, artist_id):
        return (await self.request(path=f"artist/{artist_id}/radio"))['data']

    async def track_search(self, query):
        return await self.request(path="search", params={'q': quote(query)})

    async def get_tracks(self, requester: int, url: str, search: bool = True, check_title: float = None):

        if not (matches := deezer_regex.match(url)):

            if URL_REG.match(url) or not search:
                return

            r = await self.track_search(query=url)

            try:
                tracks_result = r['data']
            except KeyError:
                return
            else:
                tracks = []

                for result in tracks_result:

                    trackinfo = {
                        'title': result['title'],
                        'author': result['artist']['name'],
                        'length': int(result['duration'] * 1000),
                        'identifier': str(result['id']),
                        'isStream': False,
                        'uri': result['link'],
                        'sourceName': 'deezer',
                        'position': 0,
                        'artworkUrl': result['album']['cover_big'],
                        'isrc': result.get('isrc'),
                    }

                    t = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester)

                    artists = result.get('contributors') or [result['artist']]

                    t.info["extra"]["authors"] = [a['name'] for a in artists]

                    if check_title and fuzz.token_sort_ratio(url.lower(), f"{t.authors_string} - {t.single_title}".lower()) < check_title:
                        continue

                    t.info["extra"]["authors_md"] = ", ".join(
                        f"[`{fix_characters(a['name'])}`](https://www.deezer.com/artist/{a['id']})" for a in
                        artists)
                    t.info["extra"]["artist_id"] = result['artist']['id']

                    if result['title'] != result['album']['title']:
                        t.info["extra"]["album"] = {
                            "name": result['album']['title'],
                            "url": result['album']['tracklist'].replace("https://api.", "https://")
                        }

                    tracks.append(t)

                return tracks

        if url.startswith("https://deezer.page.link/"):
            async with ClientSession() as session:
                async with session.get(url, allow_redirects=False) as r:
                    if 'location' not in r.headers:
                        raise GenericError("**Falha ao obter resultado para o link informado...**")
                    url = str(r.headers["location"])

        url_type, url_id = matches.groups()[-2:]

        if url_type == "track":

            result = await self.get_track_info(url_id)

            trackinfo = {
                'title': result['title'],
                'author': result['artist']['name'],
                'length': int(result['duration'] * 1000),
                'identifier': str(result['id']),
                'isStream': False,
                'uri': result['link'],
                'sourceName': 'deezer',
                'position': 0,
                'artworkUrl': result['album']['cover_big'],
                'isrc': result.get('isrc'),
            }

            t = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester)

            artists = result.get('contributors') or [result['artist']]

            t.info["extra"]["authors"] = [a['name'] for a in artists]
            t.info["extra"]["authors_md"] = ", ".join(f"[`{fix_characters(a['name'])}`](https://www.deezer.com/artist/{a['id']})" for a in artists)
            t.info["extra"]["artist_id"] = result['artist']['id']

            if result['title'] != result['album']['title']:
                t.info["extra"]["album"] = {
                    "name": result['album']['title'],
                    "url": result['album']['tracklist'].replace("https://api.", "https://")
                }

            return [t]

        data = {
            'loadType': 'PLAYLIST_LOADED',
            'playlistInfo': {'name': ''},
            'sourceName': "deezer",
            'tracks_data': [],
            "thumb": ""
        }

        if url_type == "album":

            cache_key = f"partial:deezer:{url_type}:{url_id}"

            if not (result:=self.cache.get(cache_key)):
                result = await self.get_album_info(url_id)
                self.cache[cache_key] = result

            if len(result['tracks']['data']) > 1:
                data["playlistInfo"].update(
                    {
                        "name":result['title'],
                        "url": result['link'],
                        "is_album": True
                    }
                )
                tracks_data = result['tracks']['data']

            else:
                result_track = result['tracks']['data'][0]

                trackinfo = {
                    'title': result['title'],
                    'author': result['artist']['name'],
                    'length': int(result['duration'] * 1000),
                    'identifier': str(result['id']),
                    'isStream': False,
                    'uri': result['link'],
                    'sourceName': 'deezer',
                    'position': 0,
                    'artworkUrl': result['album']['cover_big'],
                    'isrc': result.get('isrc'),
                }

                t = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester)

                artists = result_track.get('contributors') or [result_track['artist']]

                t.info["extra"]["authors"] = [a['name'] for a in artists]
                t.info["extra"]["authors_md"] = ", ".join(f"[`{fix_characters(a['name'])}`](https://www.deezer.com/artist/{a['id']})" for a in artists)
                t.info["extra"]["artist_id"] = result['artist']['id']

                if result['title'] != result_track['title']:
                    result_track.info["extra"]["album"] = {
                        "name": result['title'],
                        "url": result['tracklist'].replace("https://api.", "https://")
                    }

                return [t]

        elif url_type == "artist":

            cache_key = f"partial:deezer:{url_type}:{url_id}"

            if not (result:=self.cache.get(cache_key)):
                result = await self.get_artist_top(url_id)
                self.cache[cache_key] = result

            url_id = int(url_id)

            for a in result['data']:

                if url_id == a['artist']['id']:
                    data["playlistInfo"]["name"] = f"As mais tocadas de: {a['artist']['name']}"
                    break

                artist = None

                for c in a['contributors']:
                    if c['id'] == url_id:
                        artist = f"As mais tocadas de: {c['name']}"
                        break

                if artist:
                    data["playlistInfo"]["name"] = artist
                    break

            tracks_data = result['data']

        elif url_type == "playlist":

            cache_key = f"partial:deezer:{url_type}:{url_id}"

            if not (result := self.cache.get(cache_key)):
                result = await self.get_playlist_info(url_id)
                self.cache[cache_key] = result

            data["playlistInfo"]["name"] = result["title"]
            data["playlistInfo"]["thumb"] = result["picture_big"]
            tracks_data = result["tracks"]["data"]

        else:
            raise GenericError(f"**Link do deezer não reconhecido/suportado:**\n{url}")

        if not tracks_data:
            raise GenericError("**Não houve resultados no link do deezer informado...**")

        data["playlistInfo"]["selectedTrack"] = -1
        data["playlistInfo"]["type"] = url_type

        playlist = LavalinkPlaylist(data, url=url)

        playlist_info = playlist if url_type != "album" else None

        for t in tracks_data:

            trackinfo = {
                'title': result['title'],
                'author': result['artist']['name'],
                'length': int(result['duration'] * 1000),
                'identifier': str(result['id']),
                'isStream': False,
                'uri': result['link'],
                'sourceName': 'deezer',
                'position': 0,
                'artworkUrl': result['album']['cover_big'],
                'isrc': result.get('isrc'),
            }

            track = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester, playlist=playlist_info)

            artists = t.get('contributors') or [t['artist']]

            track.info["extra"]["authors"] = [a['name'] for a in artists]
            track.info["extra"]["authors_md"] = ", ".join(f"[`{fix_characters(a['name'])}`](https://www.deezer.com/artist/{a['id']})" for a in artists)
            track.info["extra"]["artist_id"] = t['artist']['id']

            if t['title'] != t['album']['title']:
                track.info["extra"]["album"] = {
                    "name": t['album']['title'],
                    "url": t['album']['tracklist'].replace("https://api.", "https://")
                }

            playlist.tracks.append(track)

        return playlist
