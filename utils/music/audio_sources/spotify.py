# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import re
import time
import traceback
from typing import Optional, TYPE_CHECKING, Union
from urllib.parse import quote

import aiofiles
from aiohttp import ClientSession

from utils.music.converters import fix_characters
from utils.music.errors import MissingSpotifyClient, GenericError
from utils.music.models import PartialPlaylist, PartialTrack

if TYPE_CHECKING:
    from utils.client import BotCore

spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|artist|track)/([a-zA-Z0-9]+)")
spotify_link_regex = re.compile(r"(?i)https?:\/\/spotify\.link\/?(?P<id>[a-zA-Z0-9]+)")
spotify_regex_w_user = re.compile("https://open.spotify.com?.+(album|playlist|artist|track|user)/([a-zA-Z0-9]+)")


class SpotifyClient:

    def __init__(self, client_id: str, client_secret: str):

        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.spotify.com/v1"
        self.disabled = ""

        try:
            with open(".spotify_cache.json") as f:
                self.spotify_cache = json.load(f)
        except FileNotFoundError:
            self.spotify_cache = {
                "access_token": "",
                "expires_at": 0,
                "expires_in": 0
            }

    async def request(self, path: str, params: dict = None):

        if self.disabled:
            raise GenericError(f"**O suporte ao spotify foi temporariamente desativado.** ```py\n{self.disabled}```")

        headers = {'Authorization': f'Bearer {await self.get_valid_access_token()}'}

        async with ClientSession() as session:
            async with session.get(f"{self.base_url}/{path}", headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    response.raise_for_status()

    async def get_track_info(self, track_id: str):
        return await self.request(path=f'tracks/{track_id}')

    async def get_album_info(self, album_id: str):
        return await self.request(path=f'albums/{album_id}')

    async def get_artist_top(self, artist_id: str):
        return await self.request(path=f'artists/{artist_id}/top-tracks')

    async def get_playlist_info(self, playlist_id: str):
        return await self.request(path=f"playlists/{playlist_id}")

    async def get_user_info(self, user_id: str):
        return await self.request(path=f"users/{user_id}")

    async def get_user_playlists(self, user_id: str):
        return await self.request(path=f"users/{user_id}/playlists")

    async def get_recommendations(self, seed_tracks: Union[list, str], limit=10):
        if isinstance(seed_tracks, str):
            track_ids = seed_tracks
        else:
            track_ids = ",".join(seed_tracks)

        return await self.request(path='recommendations', params={
            'seed_tracks': track_ids, 'limit': limit
        })

    async def get_access_token(self):

        if self.disabled:
            raise GenericError(f"**O suporte ao spotify foi temporariamente desativado.** ```py{self.disabled}```")

        token_url = 'https://accounts.spotify.com/api/token'

        headers = {
            'Authorization': 'Basic ' + base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        }

        data = {
            'grant_type': 'client_credentials'
        }

        async with ClientSession() as session:
            async with session.post(token_url, headers=headers, data=data) as response:
                data = await response.json()

                if data.get("error"):
                    self.disabled = data
                    raise GenericError(f"**Ocorreu um erro ao obter token do spotify** ```py\n"
                                       f"{data}```")

                self.spotify_cache = data

                self.spotify_cache["expires_at"] = time.time() + self.spotify_cache["expires_in"]
                async with aiofiles.open(".spotify_cache.json", "w") as f:
                    await f.write(json.dumps(self.spotify_cache))

    async def get_valid_access_token(self):
        if time.time() >= self.spotify_cache["expires_at"]:
            await self.get_access_token()
        return self.spotify_cache["access_token"]


async def process_spotify(bot: BotCore, requester: int, query: str):

    if bot.spotify.disabled:
        bot.pool.spotify = None
        return

    if spotify_link_regex.match(query):
        async with bot.session.get(query, allow_redirects=False) as r:
            if 'location' not in r.headers:
                raise GenericError("**Falha ao obter resultado para o link informado...**")
            query = str(r.headers["location"])

    if not (matches := spotify_regex.match(query)):
        return

    if not bot.spotify:
        if [n for n in bot.music.nodes.values() if "spotify" in n.info.get("sourceManagers", [])]:
            return
        raise MissingSpotifyClient()

    url_type, url_id = matches.groups()

    if url_type == "track":

        result = await bot.spotify.get_track_info(url_id)

        t = PartialTrack(
            uri=result["external_urls"]["spotify"],
            author=result["artists"][0]["name"] or "Unknown Artist",
            title=result["name"],
            thumb=result["album"]["images"][0]["url"],
            duration=result["duration_ms"],
            source_name="spotify",
            identifier=result["id"],
            requester=requester
        )

        try:
            t.info["isrc"] = result["external_ids"]["isrc"]
        except KeyError:
            pass

        t.info["extra"]["authors"] = [fix_characters(i['name']) for i in result['artists'] if f"feat. {i['name'].lower()}"
                                      not in result['name'].lower()]

        t.info["extra"]["authors_md"] = ", ".join(f"[`{a['name']}`]({a['external_urls']['spotify']})" for a in result["artists"])

        try:
            if result["album"]["name"] != result["name"]:
                t.info["extra"]["album"] = {
                    "name": result["album"]["name"],
                    "url": result["album"]["external_urls"]["spotify"]
                }
        except (AttributeError, KeyError):
            pass

        return [t]

    data = {
        'loadType': 'PLAYLIST_LOADED',
        'playlistInfo': {'name': ''},
        'sourceName': "spotify",
        'tracks_data': [],
        'is_album': False,
        "thumb": ""
    }

    if url_type == "album":

        result = await bot.spotify.get_album_info(url_id)

        try:
            thumb = result["tracks"][0]["album"]["images"][0]["url"]
        except:
            thumb = ""

        if len(result["tracks"]) < 2:

            track = result["tracks"][0]

            t = PartialTrack(
                uri=track["external_urls"]["spotify"],
                author=track["artists"][0]["name"] or "Unknown Artist",
                title=track["name"],
                thumb=thumb,
                duration=track["duration_ms"],
                source_name="spotify",
                identifier=track["id"],
                requester=requester
            )

            try:
                t.info["isrc"] = track["external_ids"]["isrc"]
            except KeyError:
                pass

            t.info["extra"]["authors"] = [fix_characters(i['name']) for i in track['artists'] if
                                          f"feat. {i['name'].lower()}"
                                          not in track['name'].lower()]

            t.info["extra"]["authors_md"] = ", ".join(
                f"[`{a['name']}`]({a['external_urls']['spotify']})" for a in track["artists"])

            try:
                t.info["extra"]["album"] = {
                    "name": result["name"],
                    "url": result["external_urls"]["spotify"]
                }
            except (AttributeError, KeyError):
                pass

            return [t]

        data["playlistInfo"]["name"] = result["name"]
        data["playlistInfo"]["is_album"] = True

        for t in result["tracks"]["items"]:
            t["album"] = result

        tracks_data = result["tracks"]["items"]

    elif url_type == "artist":

        result = await bot.spotify.get_artist_top(url_id)

        try:
            data["playlistInfo"]["name"] = "As mais tocadas de: " + \
                                           [a["name"] for a in result["tracks"][0]["artists"] if a["id"] == url_id][0]
        except IndexError:
            data["playlistInfo"]["name"] = "As mais tocadas de: " + result["tracks"][0]["artists"][0]["name"]
        tracks_data = result["tracks"]

    elif url_type == "playlist":
        result = await bot.spotify.get_playlist_info(url_id)
        data["playlistInfo"]["name"] = result["name"]
        data["playlistInfo"]["thumb"] = result["images"][0]["url"]
        tracks_data = [t["track"] for t in result["tracks"]["items"]]

    else:
        raise GenericError(f"**Link do spotify não reconhecido/suportado:**\n{query}")

    if not tracks_data:
        raise GenericError("**Não houve resultados no link do spotify informado...**")

    data["playlistInfo"]["selectedTrack"] = -1
    data["playlistInfo"]["type"] = url_type

    playlist = PartialPlaylist(data, url=query)

    playlist_info = playlist if url_type != "album" else None

    for t in tracks_data:

        if not t:
            continue

        try:
            thumb = t["album"]["images"][0]["url"]
        except (IndexError, KeyError):
            thumb = ""

        track = PartialTrack(
            uri=t["external_urls"].get("spotify", f"https://www.youtube.com/results?search_query={quote(t['name'])}"),
            author=t["artists"][0]["name"] or "Unknown Artist",
            title=t["name"],
            thumb=thumb,
            duration=t["duration_ms"],
            source_name="spotify",
            identifier=t["id"],
            playlist=playlist_info,
            requester=requester
        )

        try:
            track.info["isrc"] = t["external_ids"]["isrc"]
        except KeyError:
            pass

        try:
            track.info["extra"]["album"] = {
                "name": t["album"]["name"],
                "url": t["album"]["external_urls"]["spotify"]
            }
        except (AttributeError, KeyError):
            pass

        if t["artists"][0]["name"]:
            track.info["extra"]["authors"] = [fix_characters(i['name']) for i in t['artists'] if f"feat. {i['name'].lower()}" not in t['name'].lower()]
            track.info["extra"]["authors_md"] = ", ".join(f"[`{fix_characters(a['name'])}`](<" + a['external_urls'].get('spotify', f'https://www.youtube.com/results?search_query={quote(t["name"])}') + ">)" for a in t['artists'])
        else:
            track.info["extra"]["authors"] = ["Unknown Artist"]
            track.info["extra"]["authors_md"] = "`Unknown Artist`"

        playlist.tracks.append(track)

    return playlist


def spotify_client(config: dict) -> Optional[SpotifyClient]:
    if not config['SPOTIFY_CLIENT_ID']:
        print(
            f"[IGNORADO] - Spotify Support: SPOTIFY_CLIENT_ID não foi configurado na ENV da host (ou no arquivo .env)."
            f"\n{'-' * 30}")
        return

    if not config['SPOTIFY_CLIENT_SECRET']:
        print(
            F"[IGNORADO] - Spotify Support: SPOTIFY_CLIENT_SECRET não foi configurado nas ENV da host "
            F"(ou no arquivo .env).\n{'-' * 30}")
        return

    try:
        return SpotifyClient(client_id=config['SPOTIFY_CLIENT_ID'], client_secret=config['SPOTIFY_CLIENT_SECRET'])

    except KeyError as e:
        print(
            f"A APIKEY do spotify não foi configurada devidamente na ENV da host (ou no arquivo .env), "
            f"verifique e tente novamente caso queira o suporte a músicas do spotify (Erro: {repr(e)}).\n{'-' * 30}")
        return

    except Exception as e:
        print(f"Ocorreu um erro na configuração do spotify:\n{traceback.format_exc()}).\n{'-' * 30}")
        return
