# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import os
import re
from typing import Optional
from urllib.parse import urlparse

from aiohttp import (
    ClientError,
    ClientSession,
    ClientTimeout,
    ContentTypeError,
)
from cachetools import TTLCache
from rapidfuzz import fuzz

from utils.music.converters import fix_characters, URL_REG
from utils.music.errors import GenericError
from utils.music.models import LavalinkTrack, LavalinkPlaylist
from utils.music.track_encoder import encode_track


# Amazon Music:
# https://music.amazon.com/tracks/ID
# https://music.amazon.com/albums/ID
# https://music.amazon.com/artists/ID/name
# https://music.amazon.com/playlists/ID
# https://music.amazon.com/user-playlists/ID

amazonmusic_regex = re.compile(
    r"(?i)^https?://(?:www\.)?music\.amazon\.[a-z.]+/"
    r"(?P<type>tracks|albums|artists|playlists|user-playlists)/"
    r"(?P<identifier>[a-z0-9_-]+)"
    r"(?:/[^?#]*)?(?:[?#].*)?$"
)


AMAZON_ENDPOINTS = {
    "tracks": "songs",
    "albums": "albums",
    "artists": "artists",
    "playlists": "playlists",
    "user-playlists": "community-playlists",
}


class AmazonMusicClient:

    def __init__(
        self,
        cache: Optional[TTLCache] = None,
        base_url: Optional[str] = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("AMAZON_MUSIC_API_URL")
            or "http://localhost:3000"
        ).rstrip("/")

        self.cache = (
            cache
            if cache is not None
            else TTLCache(maxsize=700, ttl=3600)
        )

        self.timeout = ClientTimeout(total=35, connect=10)
        self._request_semaphore = asyncio.Semaphore(5)

    # ---------------------------------------------------------
    # HTTP
    # ---------------------------------------------------------

    async def request(
        self,
        path: str,
        params: Optional[dict] = None,
    ):
        url = f"{self.base_url}/{path.lstrip('/')}"

        async with self._request_semaphore:

            try:
                async with ClientSession(
                    timeout=self.timeout
                ) as session:

                    async with session.get(
                        url,
                        params=params,
                    ) as response:

                        try:
                            payload = await response.json(
                                content_type=None
                            )
                        except (
                            ValueError,
                            ContentTypeError,
                        ) as exc:
                            raise GenericError(
                                "**A API do Amazon Music retornou "
                                "uma resposta inválida.**"
                            ) from exc

                        if response.status == 429:
                            raise GenericError(
                                "**A API do Amazon Music está limitando "
                                "as requisições. Tente novamente em instantes.**"
                            )

                        if response.status == 404:
                            raise GenericError(
                                "**O conteúdo solicitado não foi encontrado "
                                "no Amazon Music.**"
                            )

                        if response.status != 200:
                            raise GenericError(
                                f"**A API do Amazon Music respondeu com "
                                f"HTTP {response.status}.**"
                            )

            except GenericError:
                raise

            except (
                ClientError,
                asyncio.TimeoutError,
                OSError,
            ) as exc:
                raise GenericError(
                    "**Não foi possível acessar a API do Amazon Music. "
                    "Verifique a disponibilidade do serviço e tente novamente.**"
                ) from exc

        if not isinstance(payload, dict):
            raise GenericError(
                "**A API do Amazon Music retornou dados em formato inválido.**"
            )

        if not payload.get("success"):
            message = payload.get(
                "message",
                "Não foi possível obter os dados solicitados.",
            )

            raise GenericError(
                f"**Amazon Music:** {message}"
            )

        return payload.get("data")

    # ---------------------------------------------------------
    # API endpoints
    # ---------------------------------------------------------

    async def search_songs(
        self,
        query: str,
        page: int = 1,
        limit: int = 10,
    ):
        return await self.request(
            "api/search/songs",
            params={
                "query": query,
                "page": page,
                "limit": min(max(limit, 1), 10),
            },
        )

    async def get_song_by_url(self, url: str):
        return await self.request(
            "api/songs",
            params={"url": url},
        )

    async def get_album_by_url(self, url: str):
        return await self.request(
            "api/albums",
            params={"url": url},
        )

    async def get_artist_by_url(self, url: str):
        return await self.request(
            "api/artists",
            params={"url": url},
        )

    async def get_playlist_by_url(self, url: str):
        return await self.request(
            "api/playlists",
            params={"url": url},
        )

    async def get_community_playlist_by_url(self, url: str):
        return await self.request(
            "api/community-playlists",
            params={"url": url},
        )

    # ---------------------------------------------------------
    # Cache
    # ---------------------------------------------------------

    async def _cached_request(
        self,
        key: str,
        callback,
    ):
        result = self.cache.get(key)

        if result is not None:
            return result

        result = await callback()

        if result is not None:
            self.cache[key] = result

        return result

    # ---------------------------------------------------------
    # Track conversion
    # ---------------------------------------------------------

    @staticmethod
    def _make_track(
        data: dict,
        requester: int,
        playlist=None,
    ) -> LavalinkTrack:

        artist = data.get("artist") or {}
        album = data.get("album") or {}

        title = (
            data.get("title")
            or data.get("name")
            or "Faixa desconhecida"
        )

        artist_name = (
            artist.get("name")
            or data.get("artistName")
            or "Unknown Artist"
        )

        try:
            duration = int(float(data.get("duration") or 0) * 1000)
        except (TypeError, ValueError):
            duration = 0

        identifier = str(data.get("id") or "")

        track_url = (
            data.get("url")
            or (
                f"https://music.amazon.com/tracks/{identifier}"
                if identifier
                else ""
            )
        )

        artwork = (
            data.get("image")
            or album.get("image")
            or ""
        )

        trackinfo = {
            "title": title,
            "author": artist_name,
            "length": duration,
            "identifier": identifier,
            "isStream": False,
            "uri": track_url,
            "sourceName": "amazonmusic",
            "position": 0,
            "artworkUrl": artwork,
            "isrc": data.get("isrc"),
        }

        track = LavalinkTrack(
            id_=encode_track(trackinfo)[1],
            info=trackinfo,
            requester=requester,
            playlist=playlist,
        )

        track.info["extra"]["authors"] = [artist_name]

        artist_url = (
            artist.get("url")
            or (
                f"https://music.amazon.com/artists/{artist.get('id')}"
                if artist.get("id")
                else ""
            )
        )

        if artist_url:
            track.info["extra"]["authors_md"] = (
                f"[`{fix_characters(artist_name)}`]({artist_url})"
            )
        else:
            track.info["extra"]["authors_md"] = (
                f"`{fix_characters(artist_name)}`"
            )

        if artist.get("id"):
            track.info["extra"]["artist_id"] = artist["id"]

        album_name = album.get("name")
        album_url = album.get("url")

        if album_name and album_name != title:
            track.info["extra"]["album"] = {
                "name": album_name,
                "url": album_url or "",
            }

        return track

    # ---------------------------------------------------------
    # Playlist conversion
    # ---------------------------------------------------------

    def _make_playlist(
        self,
        data: dict,
        requester: int,
        url: str,
        playlist_type: str,
    ):

        songs = data.get("songs") or data.get("topSongs") or []

        if not songs:
            raise GenericError(
                "**Não foram encontradas faixas disponíveis "
                "nesse conteúdo do Amazon Music.**"
            )

        playlist_name = (
            data.get("name")
            or data.get("title")
            or "Playlist do Amazon Music"
        )

        thumbnail = data.get("image") or ""

        playlist_data = {
            "loadType": "PLAYLIST_LOADED",
            "playlistInfo": {
                "name": playlist_name,
                "selectedTrack": -1,
                "type": playlist_type,
                "url": data.get("url") or url,
                "thumb": thumbnail,
                "is_album": playlist_type == "album",
            },
            "sourceName": "amazonmusic",
            "tracks": [],
            "thumb": thumbnail,
        }

        playlist_url = data.get("url") or url

        playlist = LavalinkPlaylist(
            playlist_data,
            url=playlist_url,
        )

        # Álbuns são tratados como álbuns, não como playlists comuns.
        track_playlist = (
            None
            if playlist_type == "album"
            else playlist
        )

        for item in songs:

            if not isinstance(item, dict):
                continue

            if not item.get("id"):
                continue

            playlist.tracks.append(
                self._make_track(
                    item,
                    requester,
                    track_playlist,
                )
            )

        if not playlist.tracks:
            raise GenericError(
                "**Não foi possível carregar nenhuma faixa "
                "desse conteúdo do Amazon Music.**"
            )

        return playlist

    # ---------------------------------------------------------
    # Main resolver
    # ---------------------------------------------------------

    async def get_tracks(
        self,
        requester: int,
        url: str,
        search: bool = True,
        check_title: float = None,
    ):

        original_url = url.strip()
        matches = amazonmusic_regex.match(original_url)

        # -----------------------------------------------------
        # Text search
        # -----------------------------------------------------

        if not matches:

            parsed = urlparse(original_url)

            # Não tenta pesquisar URLs de outras fontes.
            if URL_REG.match(original_url):
                return None

            # Evita enviar links Amazon não reconhecidos
            # para a pesquisa textual.
            if parsed.hostname and (
                "amazon." in parsed.hostname.lower()
            ):
                raise GenericError(
                    "**Link do Amazon Music não reconhecido "
                    "ou não suportado.**"
                )

            if not search or len(original_url) < 2:
                return None

            result = await self.search_songs(original_url)

            if not isinstance(result, list):
                return None

            tracks = []

            for item in result:

                if not isinstance(item, dict):
                    continue

                track = self._make_track(
                    item,
                    requester,
                )

                if check_title is not None:

                    comparison = (
                        f"{track.authors_string} - "
                        f"{track.single_title}"
                    ).lower()

                    if fuzz.token_sort_ratio(
                        original_url.lower(),
                        comparison,
                    ) < check_title:
                        continue

                tracks.append(track)

            return tracks or None

        # -----------------------------------------------------
        # URL resolution
        # -----------------------------------------------------

        url_type = matches.group("type").lower()

        endpoint = AMAZON_ENDPOINTS.get(url_type)

        if not endpoint:
            raise GenericError(
                "**Tipo de conteúdo do Amazon Music não suportado.**"
            )

        cache_key = (
            f"partial:amazonmusic:{url_type}:"
            f"{matches.group('identifier')}"
        )

        async def fetch_content():
            if url_type == "tracks":
                return await self.get_song_by_url(original_url)

            if url_type == "albums":
                return await self.get_album_by_url(original_url)

            if url_type == "artists":
                return await self.get_artist_by_url(original_url)

            if url_type == "playlists":
                return await self.get_playlist_by_url(original_url)

            if url_type == "user-playlists":
                return await self.get_community_playlist_by_url(
                    original_url
                )

            return None

        result = await self._cached_request(
            cache_key,
            fetch_content,
        )

        if not isinstance(result, dict):
            raise GenericError(
                "**A API do Amazon Music não retornou os dados "
                "esperados para esse conteúdo.**"
            )

        # -----------------------------------------------------
        # Single track
        # -----------------------------------------------------

        if url_type == "tracks":

            return [
                self._make_track(
                    result,
                    requester,
                )
            ]

        # -----------------------------------------------------
        # Album
        # -----------------------------------------------------

        if url_type == "albums":

            return self._make_playlist(
                result,
                requester,
                original_url,
                "album",
            )

        # -----------------------------------------------------
        # Artist
        # -----------------------------------------------------

        if url_type == "artists":

            return self._make_playlist(
                result,
                requester,
                original_url,
                "artist",
            )

        # -----------------------------------------------------
        # Playlist
        # -----------------------------------------------------

        if url_type == "playlists":

            return self._make_playlist(
                result,
                requester,
                original_url,
                "playlist",
            )

        # -----------------------------------------------------
        # Community playlist
        # -----------------------------------------------------

        if url_type == "user-playlists":

            return self._make_playlist(
                result,
                requester,
                original_url,
                "community_playlist",
            )

        raise GenericError(
            f"**Não foi possível resolver esse link do Amazon Music:**\n"
            f"{original_url}"
        )
