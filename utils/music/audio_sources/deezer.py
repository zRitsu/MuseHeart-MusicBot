# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs

from aiohttp import ClientError, ClientSession, ClientTimeout
from cachetools import TTLCache
from rapidfuzz import fuzz

from utils.music.converters import fix_characters, URL_REG
from utils.music.errors import GenericError
from utils.music.models import LavalinkTrack, LavalinkPlaylist
from utils.music.track_encoder import encode_track


deezer_regex = re.compile(
    r"(?i)^https?://(?:www\.)?deezer\.com/"
    r"(?:(?P<countrycode>[a-z]{2})/)?"
    r"(?P<type>track|album|playlist|artist|profile)/"
    r"(?P<identifier>[0-9]+)(?:[/?#].*)?$"
)

DEEzer_SHORT_HOSTS = {"deezer.page.link", "link.deezer.com"}


class DeezerClient:

    base_url = "https://api.deezer.com"

    def __init__(self, cache: Optional[TTLCache] = None):
        self.cache = cache if cache is not None else TTLCache(maxsize=700, ttl=86400)
        self.timeout = ClientTimeout(total=25, connect=8)
        self._request_semaphore = asyncio.Semaphore(8)

    async def request(self, path: str, params: dict = None):
        """Request the public Deezer API and normalize API/network errors."""
        url = f"{self.base_url}/{path.lstrip('/')}"

        async with self._request_semaphore:
            try:
                async with ClientSession(timeout=self.timeout) as session:
                    async with session.get(url, params=params) as response:
                        payload = await response.json(content_type=None)

                        if response.status != 200:
                            raise GenericError(
                                f"**A API do Deezer respondeu com HTTP {response.status}. Tente novamente mais tarde.**"
                            )

            except GenericError:
                raise
            except (ClientError, asyncio.TimeoutError, ValueError) as exc:
                raise GenericError(f"**Não foi possível acessar o Deezer: {exc}**") from exc

        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            message = error.get("message", "erro desconhecido") if isinstance(error, dict) else str(error)
            raise GenericError(f"**O Deezer não conseguiu fornecer esse conteúdo: {message}.**")

        return payload

    async def get_track_info(self, track_id):
        return await self.request(f"track/{track_id}")

    async def get_album_info(self, album_id):
        return await self.request(f"album/{album_id}")

    async def get_artist_top(self, artist_id, limit=50):
        return await self.request(f"artist/{artist_id}/top", params={"limit": limit})

    async def get_playlist_info(self, playlist_id):
        return await self.request(f"playlist/{playlist_id}")

    async def get_user_playlists(self, user_id: int):
        result = await self.request(f"user/{user_id}/playlists")
        return result.get("data", [])

    async def get_user_info(self, user_id: int):
        return await self.request(f"user/{user_id}")

    async def get_artist_radio_info(self, artist_id):
        result = await self.request(f"artist/{artist_id}/radio")
        return result.get("data", [])

    async def track_search(self, query):
        return await self.request("search", params={"q": query, "limit": 25})

    async def _resolve_short_url(self, url: str) -> str:
        parsed = urlparse(url)

        if parsed.netloc.lower() not in DEEzer_SHORT_HOSTS:
            return url

        try:
            async with ClientSession(timeout=self.timeout) as session:
                async with session.get(url, allow_redirects=True) as response:
                    final_url = str(response.url)

                    if not deezer_regex.match(final_url):
                        raise GenericError(
                            "**Não foi possível identificar o conteúdo desse link curto do Deezer.**"
                        )

                    return final_url

        except GenericError:
            raise
        except (ClientError, asyncio.TimeoutError) as exc:
            raise GenericError(f"**Falha ao abrir o link curto do Deezer: {exc}**") from exc

    def _cache_get(self, key):
        return self.cache.get(key)

    async def _cached_request(self, key: str, callback):
        result = self._cache_get(key)

        if result is not None:
            return result

        result = await callback()

        if result is not None:
            self.cache[key] = result

        return result

    @staticmethod
    def _artists(data: dict) -> list:
        artists = data.get("contributors") or [data.get("artist") or {}]
        return [artist for artist in artists if artist and artist.get("name")]

    def _make_track(self, data: dict, requester: int, playlist=None):

        artist = data.get("artist") or {}
        album = data.get("album") or {}
        artists = self._artists(data)

        title = data.get("title") or data.get("title_short") or "Faixa desconhecida"
        duration = data.get("duration") or 0

        trackinfo = {
            "title": title,
            "author": artist.get("name") or (
                artists[0].get("name") if artists else "Unknown Artist"
            ),
            "length": int(duration * 1000),
            "identifier": str(data.get("id", "")),
            "isStream": False,
            "uri": data.get("link") or "",
            "sourceName": "deezer",
            "position": 0,
            "artworkUrl": (
                album.get("cover_xl")
                or album.get("cover_big")
                or album.get("cover_medium")
                or ""
            ),
            "isrc": data.get("isrc"),
        }

        track = LavalinkTrack(
            id_=encode_track(trackinfo)[1],
            info=trackinfo,
            requester=requester,
            playlist=playlist,
        )

        track.info["extra"]["authors"] = [
            artist["name"] for artist in artists
        ]

        track.info["extra"]["authors_md"] = ", ".join(
            f"[`{fix_characters(a['name'])}`](https://www.deezer.com/artist/{a['id']})"
            for a in artists if a.get("id")
        )

        if artist.get("id"):
            track.info["extra"]["artist_id"] = artist["id"]

        if album.get("title") and album.get("title") != title:
            track.info["extra"]["album"] = {
                "name": album["title"],
                "url": album.get("link") or (
                    f"https://www.deezer.com/album/{album.get('id', '')}"
                ),
            }

        return track

    async def _get_all_pages(self, first_page: dict, max_pages: int = 20) -> list:
        """Collect paginated Deezer results without following arbitrary URLs."""

        items = list(first_page.get("data") or [])
        next_url = first_page.get("next")
        pages = 1

        while next_url and pages < max_pages:

            parsed = urlparse(next_url)

            if parsed.netloc not in {"api.deezer.com", "www.deezer.com"}:
                break

            path = parsed.path.removeprefix("/")
            params = {
                key: values[-1]
                for key, values in parse_qs(parsed.query).items()
            }

            page = await self.request(path, params=params)
            page_items = page.get("data") or []

            if not page_items:
                break

            items.extend(page_items)
            next_url = page.get("next")
            pages += 1

        return items

    async def get_tracks(
        self,
        requester: int,
        url: str,
        search: bool = True,
        check_title: float = None
    ):

        original_url = url
        url = await self._resolve_short_url(url)
        matches = deezer_regex.match(url)

        # Pesquisa textual: a integração principal com LavaSrc/dzsearch
        # é feita pelo módulo de música. Este cliente é o fallback da API.

        if not matches:

            if URL_REG.match(url) or not search:
                return None

            result = await self.track_search(url)
            tracks = []

            for item in result.get("data", []):

                track = self._make_track(item, requester)

                if check_title is not None:

                    comparison = (
                        f"{track.authors_string} - {track.single_title}"
                    ).lower()

                    if fuzz.token_sort_ratio(
                        url.lower(), comparison
                    ) < check_title:
                        continue

                tracks.append(track)

            return tracks or None

        url_type = matches.group("type").lower()
        url_id = matches.group("identifier")

        if url_type == "profile":
            raise GenericError(
                "**Links de perfil do Deezer não são reproduzíveis diretamente. "
                "Envie o link de uma playlist.**"
            )

        if url_type == "track":

            result = await self.get_track_info(url_id)

            return [
                self._make_track(result, requester)
            ]

        cache_key = f"partial:deezer:{url_type}:{url_id}"

        if url_type == "album":

            result = await self._cached_request(
                cache_key,
                lambda: self.get_album_info(url_id)
            )

            tracks_page = result.get("tracks") or {}
            tracks_data = await self._get_all_pages(tracks_page)

            if not tracks_data:
                raise GenericError(
                    "**Esse álbum do Deezer não contém faixas disponíveis.**"
                )

            if len(tracks_data) == 1:

                return [
                    self._make_track(
                        await self.get_track_info(tracks_data[0]["id"]),
                        requester
                    )
                ]

            playlist_name = result.get("title") or "Álbum do Deezer"
            playlist_url = result.get("link") or url
            is_album = True

            thumbnail = (
                result.get("cover_xl")
                or result.get("cover_big")
                or ""
            )

        elif url_type == "artist":

            result = await self._cached_request(
                cache_key,
                lambda: self.get_artist_top(url_id)
            )

            tracks_data = result.get("data") or []

            if not tracks_data:
                raise GenericError(
                    "**Não foram encontradas faixas populares para esse artista.**"
                )

            artist_name = (
                tracks_data[0].get("artist", {}).get("name", "Artista")
            )

            playlist_name = f"As mais tocadas de: {artist_name}"
            playlist_url = url
            is_album = False
            thumbnail = ""

        elif url_type == "playlist":

            result = await self._cached_request(
                cache_key,
                lambda: self.get_playlist_info(url_id)
            )

            tracks_page = result.get("tracks") or {}
            tracks_data = await self._get_all_pages(tracks_page)

            if not tracks_data:
                raise GenericError(
                    "**Essa playlist do Deezer não contém faixas disponíveis.**"
                )

            playlist_name = result.get("title") or "Playlist do Deezer"
            playlist_url = result.get("link") or url
            is_album = False

            thumbnail = (
                result.get("picture_xl")
                or result.get("picture_big")
                or ""
            )

        else:
            raise GenericError(
                f"**Link do Deezer não reconhecido/suportado:**\n{original_url}"
            )

        playlist_data = {
            "loadType": "PLAYLIST_LOADED",
            "playlistInfo": {
                "name": playlist_name,
                "selectedTrack": -1,
                "type": url_type,
                "url": playlist_url,
                "thumb": thumbnail,
                "is_album": is_album,
            },
            "sourceName": "deezer",
            "tracks_data": [],
            "thumb": thumbnail,
        }

        playlist = LavalinkPlaylist(
            playlist_data,
            url=playlist_url
        )

        playlist_info = None if is_album else playlist

        for item in tracks_data:

            if not item or not item.get("id"):
                continue

            # Alguns endpoints retornam objetos resumidos.
            # Completa os dados essenciais quando necessário.

            if not item.get("album") or not item.get("link"):
                item = await self.get_track_info(item["id"])

            playlist.tracks.append(
                self._make_track(
                    item,
                    requester,
                    playlist_info
                )
            )

        if not playlist.tracks:
            raise GenericError(
                "**Não foi possível carregar nenhuma faixa desse conteúdo do Deezer.**"
            )

        return playlist
