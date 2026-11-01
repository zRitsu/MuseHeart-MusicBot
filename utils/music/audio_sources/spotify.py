# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import json
import os.path
import random
import re
import time
from tempfile import gettempdir
from typing import Optional, TYPE_CHECKING, Union
from urllib.parse import quote

import aiofiles
from aiohttp import ClientSession, ClientTimeout
from rapidfuzz import fuzz

from utils.music.converters import fix_characters, URL_REG
from utils.music.errors import GenericError
from utils.music.models import LavalinkTrack, LavalinkPlaylist
from utils.music.track_encoder import encode_track

if TYPE_CHECKING:
    from utils.client import BotCore

spotify_regex = re.compile(r"(?i)^https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?(album|playlist|artist|track)/([a-zA-Z0-9]+)(?:[/?#].*)?$")
spotify_link_regex = re.compile(r"(?i)https?:\/\/spotify\.link\/?(?P<id>[a-zA-Z0-9]+)")
spotify_regex_w_user = re.compile(r"(?i)^https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?(album|playlist|artist|track|user)/([a-zA-Z0-9]+)(?:[/?#].*)?$")

spotify_cache_file = os.path.join(gettempdir(), ".spotify_cache.json")


class SpotifyClient:

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, playlist_extra_page_limit: int = 0):
        # SlugYZeon/LavaSrc podem resolver links Spotify diretamente no Lavalink.
        # As credenciais da API oficial ficam opcionais e são usadas apenas como fallback.
        self.client_id = client_id or None
        self.client_secret = client_secret or None
        self.api_available = bool(self.client_id and self.client_secret)
        self.base_url = "https://api.spotify.com/v1"
        self.spotify_cache = {}
        self.disabled = False
        self.type = "api"
        self.token_refresh = False
        self._token_lock = asyncio.Lock()
        self.playlist_extra_page_limit = max(0, int(playlist_extra_page_limit or 0))
        self.timeout = ClientTimeout(total=30, connect=10)

        try:
            with open(spotify_cache_file, encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict):
                self.spotify_cache = cached
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.spotify_cache = {}

    def _token_is_valid(self) -> bool:
        return bool(
            self.spotify_cache.get("access_token")
            and self.spotify_cache.get("expires_at", 0) > time.time() + 60
        )

    async def request(self, path: str, params: dict = None):
        if self.disabled:
            return None

        # A 401 pode ocorrer se o token for revogado antes da expiração prevista.
        for auth_attempt in range(2):
            token = await self.get_valid_access_token()
            headers = {"Authorization": f"Bearer {token}"}
            async with ClientSession(timeout=self.timeout) as session:
                for attempt in range(3):
                    async with session.get(f"{self.base_url}/{path.lstrip('/')}", headers=headers, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        if response.status == 401:
                            if auth_attempt == 0:
                                self.spotify_cache = {}
                                await self.get_access_token(force=True)
                                break
                            raise GenericError("**O Spotify recusou a autenticação. Confira CLIENT_ID e CLIENT_SECRET.**")
                        if response.status == 404:
                            raise GenericError(
                                "**Não houve resultado para o link informado (confira se o link está correto, "
                                "se o conteúdo está privado ou se foi deletado).**"
                            )
                        if response.status == 429:
                            retry_after = response.headers.get("Retry-After", "1")
                            try:
                                delay = max(1.0, float(retry_after))
                            except (TypeError, ValueError):
                                delay = 2.0
                            if attempt < 2:
                                await asyncio.sleep(min(delay, 30))
                                continue
                            raise GenericError("**O Spotify está limitando temporariamente as requisições. Tente novamente em instantes.**")
                        response.raise_for_status()
                else:
                    return None
        return None

    async def get_track_info(self, track_id: str):
        return await self.request(path=f'tracks/{track_id}')

    async def get_album_info(self, album_id: str):
        return await self.request(path=f'albums/{album_id}')

    async def get_artist_top(self, artist_id: str):
        return await self.request(path=f'artists/{artist_id}/top-tracks')

    async def get_playlist_info(self, playlist_id: str):
        result = await self.request(path=f"playlists/{playlist_id}")
        if not result:
            return result

        tracks = result.get("tracks") or {}
        items = tracks.get("items") or []
        offset = len(items)
        page_count = 0

        while tracks.get("next") and page_count < self.playlist_extra_page_limit:
            page = await self.request(
                path=f"playlists/{playlist_id}/tracks",
                params={"offset": offset, "limit": 100},
            )
            if not page:
                break
            page_items = page.get("items") or []
            if not page_items:
                break
            items.extend(page_items)
            offset += len(page_items)
            tracks["next"] = page.get("next")
            page_count += 1

        return result

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

    async def track_search(self, query: str):
        return await self.request(path='search', params = {
        'q': quote(query), 'type': 'track', 'limit': 10
        })

    async def get_access_token(self, force: bool = False):
        if not self.api_available:
            raise GenericError("**A API oficial do Spotify não está configurada; configure CLIENT_ID e CLIENT_SECRET ou utilize um nó Lavalink com SlugYZeon/LavaSrc.**")

        async with self._token_lock:
            if not force and self._token_is_valid():
                return self.spotify_cache["access_token"]

            token_url = "https://accounts.spotify.com/api/token"
            credentials = f"{self.client_id}:{self.client_secret}".encode("utf-8")
            headers = {
                "Authorization": "Basic " + base64.b64encode(credentials).decode("ascii"),
                "Content-Type": "application/x-www-form-urlencoded",
            }

            async with ClientSession(timeout=self.timeout) as session:
                async with session.post(token_url, headers=headers, data={"grant_type": "client_credentials"}) as response:
                    payload = await response.json(content_type=None)
                    if response.status != 200:
                        description = payload.get("error_description") or payload.get("error") or f"HTTP {response.status}"
                        raise GenericError(f"**Não foi possível autenticar no Spotify: {description}**")

            access_token = payload.get("access_token")
            expires_in = payload.get("expires_in")
            if not access_token or not isinstance(expires_in, (int, float)):
                raise GenericError("**O Spotify retornou um token inválido ou incompleto.**")

            self.spotify_cache = {
                "access_token": access_token,
                "token_type": payload.get("token_type", "Bearer"),
                "expires_in": expires_in,
                "expires_at": time.time() + expires_in,
                "type": "api",
            }
            self.type = "api"
            self.token_refresh = False
            try:
                async with aiofiles.open(spotify_cache_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(self.spotify_cache))
            except OSError as exc:
                # A falha ao persistir cache não deve impedir o uso do token em memória.
                print(f"⚠️ - Spotify: não foi possível salvar o cache do token: {exc}")

            print("🎶 - Access token do Spotify obtido com sucesso via API oficial.")
            return access_token

    async def get_valid_access_token(self):
        if not self._token_is_valid():
            await self.get_access_token()
        return self.spotify_cache["access_token"]

    async def _load_from_lavalink_plugin(self, bot: BotCore, requester: int, identifier: str):
        """Resolve Spotify URLs/queries através dos plugins instalados no Lavalink.

        SlugYZeon documenta URLs Spotify diretas e o prefixo spsearch:. LavaSrc
        também pode resolver URLs diretamente. O resultado já vem como Track/Playlist
        do Wavelink, evitando reconstruir e re-encodar faixas no Python.
        """
        nodes = list(getattr(getattr(bot, "music", None), "nodes", {}).values())
        if not nodes:
            return None

        for node in nodes:
            try:
                result = await node.get_tracks(
                    identifier,
                    track_cls=LavalinkTrack,
                    playlist_cls=LavalinkPlaylist,
                    requester=requester,
                )
                if result:
                    return result
            except Exception as exc:
                # Um nó sem o plugin/fonte Spotify não deve impedir o fallback.
                print(f"⚠️ - Spotify: resolução via Lavalink falhou em {getattr(node, 'identifier', 'node')}: {exc}")
        return None

    async def get_tracks(self, bot: BotCore, requester: int, query: str, search: bool = True, check_title: float = None):

        if spotify_link_regex.match(query):
            async with bot.session.get(query, allow_redirects=False) as r:
                if 'location' not in r.headers:
                    raise GenericError("**Falha ao obter resultado para o link informado...**")
                query = str(r.headers["location"])

        matches = spotify_regex.match(query)
        is_spotify_url = bool(matches)

        # Preferência: SlugYZeon/LavaSrc no Lavalink. Para pesquisa textual,
        # SlugYZeon documenta o prefixo spsearch:. Mantemos API oficial como fallback.
        if is_spotify_url:
            plugin_result = await self._load_from_lavalink_plugin(bot, requester, query)
            if plugin_result:
                return plugin_result
        elif search and not URL_REG.match(query):
            plugin_result = await self._load_from_lavalink_plugin(bot, requester, f"spsearch:{query}")
            if plugin_result:
                if check_title and isinstance(plugin_result, list):
                    plugin_result = [t for t in plugin_result if fuzz.token_sort_ratio(
                        query.lower(), f"{getattr(t, 'author', '')} - {getattr(t, 'title', '')}".lower()
                    ) >= check_title]
                if plugin_result:
                    return plugin_result

        if not (matches := spotify_regex.match(query)) and not self.disabled and self.api_available:

            if URL_REG.match(query) or not search:
                return

            r = await self.track_search(query=query)

            tracks = []

            try:
                tracks_result = (r or {}).get('tracks', {}).get('items', [])
            except (AttributeError, TypeError):
                tracks_result = []
            else:
                for result in tracks_result:

                    trackinfo = {
                        'title': result["name"],
                        'author': result["artists"][0]["name"] or "Unknown Artist",
                        'length': result["duration_ms"],
                        'identifier': result["id"],
                        'isStream': False,
                        'uri': result["external_urls"]["spotify"],
                        'sourceName': 'spotify',
                        'position': 0,
                        'artworkUrl': result["album"]["images"][0]["url"],
                    }

                    try:
                        trackinfo["isrc"] = result["external_ids"]["isrc"]
                    except KeyError:
                        pass

                    t = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester)

                    t.info["extra"]["authors"] = [fix_characters(i['name']) for i in result['artists'] if f"feat. {i['name'].lower()}"
                                                  not in result['name'].lower()]

                    if check_title and fuzz.token_sort_ratio(query.lower(), f"{t.authors_string} - {t.single_title}".lower()) < check_title:
                        continue

                    try:
                        t.info["isrc"] = result["external_ids"]["isrc"]
                    except KeyError:
                        pass

                    t.info["extra"]["authors_md"] = ", ".join(f"[`{a['name']}`]({a['external_urls']['spotify']})" for a in result["artists"])

                    try:
                        if result["album"]["name"] != result["name"]:
                            t.info["extra"]["album"] = {
                                "name": result["album"]["name"],
                                "url": result["album"]["external_urls"]["spotify"]
                            }
                    except (AttributeError, KeyError):
                        pass

                    tracks.append(t)

                return tracks

            return

        if not self.api_available or self.disabled:
            raise GenericError(
                "**Não foi possível resolver esse conteúdo do Spotify.** Verifique se o SlugYZeon/LavaSrc está ativo no Lavalink; "
                "como fallback, configure CLIENT_ID e CLIENT_SECRET da API oficial."
            )

        url_type, url_id = matches.groups()

        if url_type == "track":

            result = await self.get_track_info(url_id)

            trackinfo = {
                'title': result["name"],
                'author': result["artists"][0]["name"] or "Unknown Artist",
                'length': result["duration_ms"],
                'identifier': result["id"],
                'isStream': False,
                'uri': result["external_urls"]["spotify"],
                'sourceName': 'spotify',
                'position': 0,
                'artworkUrl': result["album"]["images"][0]["url"],
            }

            try:
                trackinfo["isrc"] = result["external_ids"]["isrc"]
            except KeyError:
                pass

            t = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester)

            t.info["extra"]["authors"] = [fix_characters(i['name']) for i in result['artists'] if f"feat. {i['name'].lower()}"
                                          not in result['name'].lower()]

            t.info["extra"]["authors_md"] = ", ".join(f"[`{a['name']}`]({a['external_urls']['spotify']})" for a in result["artists"])

            try:
                if result["album"]["name"] != result["name"] or result["album"]["total_tracks"] > 1:
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

            cache_key = f"partial:spotify:{url_type}:{url_id}"

            if not (result := bot.pool.playlist_cache.get(cache_key)):
                result = await self.get_album_info(url_id)
                if result is None:
                    raise GenericError("**Não foi possível obter os dados do álbum no Spotify.**")
                bot.pool.playlist_cache[cache_key] = result

            try:
                thumb = result["tracks"][0]["album"]["images"][0]["url"]
            except:
                thumb = ""

            if result["tracks"] is None:
                raise GenericError("**Não houve resultados para o link do álbum informado...**")

            if len(result["tracks"]) < 2:

                track = result["tracks"][0]

                trackinfo = {
                    'title': track["name"],
                    'author': track["artists"][0]["name"] or "Unknown Artist",
                    'length': track["duration_ms"],
                    'identifier': track["id"],
                    'isStream': False,
                    'uri': track["external_urls"]["spotify"],
                    'sourceName': 'spotify',
                    'position': 0,
                    'artworkUrl': track["album"]["images"][0]["url"],
                }

                try:
                    trackinfo["isrc"] = track["external_ids"]["isrc"]
                except KeyError:
                    pass

                t = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester)

                t.info["extra"]["authors"] = [fix_characters(i['name']) for i in track['artists'] if
                                              f"feat. {i['name'].lower()}"
                                              not in track['name'].lower()]

                t.info["extra"]["authors_md"] = ", ".join(
                    f"[`{a['name']}`]({a['external_urls']['spotify']})" for a in track["artists"])

                try:
                    if result["name"] != track["name"] or result["total_tracks"] > 1:
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

            cache_key = f"partial:spotify:{url_type}:{url_id}"

            if not (result := bot.pool.playlist_cache.get(cache_key)):
                result = await self.get_artist_top(url_id)
                bot.pool.playlist_cache[cache_key] = result

            try:
                data["playlistInfo"]["name"] = "As mais tocadas de: " + \
                                               [a["name"] for a in result["tracks"][0]["artists"] if a["id"] == url_id][0]
            except IndexError:
                data["playlistInfo"]["name"] = "As mais tocadas de: " + result["tracks"][0]["artists"][0]["name"]
            tracks_data = result["tracks"]

        elif url_type == "playlist":

            cache_key = f"partial:spotify:{url_type}:{url_id}"

            if not (result := bot.pool.playlist_cache.get(cache_key)):
                result = await self.get_playlist_info(url_id)
                bot.pool.playlist_cache[cache_key] = result

            data["playlistInfo"]["name"] = result["name"]
            data["playlistInfo"]["thumb"] = result["images"][0]["url"]

            if result["tracks"]["items"] is None:
                raise GenericError("**Não houve resultados para o link da playlist informada...**")

            tracks_data = [t["track"] for t in result["tracks"]["items"]]

        else:
            raise GenericError(f"**Link do spotify não reconhecido/suportado:**\n{query}")

        if not tracks_data:
            raise GenericError("**Não houve resultados para o link do spotify informado...**")

        data["playlistInfo"]["selectedTrack"] = -1
        data["playlistInfo"]["type"] = url_type

        playlist = LavalinkPlaylist(data, url=query)

        playlist_info = playlist if url_type != "album" else None

        for t in tracks_data:

            if not t:
                continue

            try:
                thumb = t["album"]["images"][0]["url"]
            except (IndexError, KeyError):
                thumb = ""

            trackinfo = {
                'title': t["name"],
                'author': t["artists"][0]["name"] or "Unknown Artist",
                'length': t["duration_ms"],
                'identifier': t["id"],
                'isStream': False,
                'uri': t["external_urls"].get("spotify", f"https://www.youtube.com/results?search_query={quote(t['name'])}"),
                'sourceName': 'spotify',
                'position': 0,
                'artworkUrl': thumb,
            }

            try:
                trackinfo["isrc"] = t["external_ids"]["isrc"]
            except KeyError:
                pass

            track = LavalinkTrack(id_=encode_track(trackinfo)[1], info=trackinfo, requester=requester, playlist=playlist_info)

            try:
                if t["album"]["name"] != t["name"] or t["album"]["total_tracks"] > 1:
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
