# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import hmac
import json
import os.path
import re
import struct
import time
import traceback
from hashlib import sha1
from tempfile import gettempdir
from typing import Optional, TYPE_CHECKING, Union
from urllib.parse import urljoin, urlparse, quote, unquote

import aiofiles
from aiohttp import ClientSession, ClientResponseError
from rapidfuzz import fuzz

from utils.music.converters import fix_characters, URL_REG
from utils.music.errors import GenericError
from utils.music.models import LavalinkTrack, LavalinkPlaylist
from utils.music.track_encoder import encode_track

if TYPE_CHECKING:
    from utils.client import BotCore

spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|artist|track)/([a-zA-Z0-9]+)")
spotify_link_regex = re.compile(r"(?i)https?:\/\/spotify\.link\/?(?P<id>[a-zA-Z0-9]+)")
spotify_regex_w_user = re.compile("https://open.spotify.com?.+(album|playlist|artist|track|user)/([a-zA-Z0-9]+)")
spotify_search_regex = re.compile(r"(?i)https://open\.spotify\.com(?:/intl-[^/]+)?/search/([^?#]+)")

spotify_cache_file = os.path.join(gettempdir(), ".spotify_cache.json")


class SpotifyClient:

    PUBLIC_BASE_URL = "https://open.spotify.com/intl-pt"
    PARTNER_API_BASE = "https://api-partner.spotify.com/pathfinder/v1/query"
    SEARCH_OPERATION = "searchDesktop"
    SEARCH_HASH = "fcad5a3e0d5af727fb76966f06971c19cfa2275e6ff7671196753e008611873c"
    RECOMMENDATIONS_OPERATION = "internalLinkRecommenderTrack"
    RECOMMENDATIONS_HASH = "c77098ee9d6ee8ad3eb844938722db60570d040b49f41f5ec6e7be9160a7c86b"
    TRACK_OPERATION = "getTrack"
    TRACK_HASH = "612585ae06ba435ad26369870deaae23b5c8800a256cd8a57e08eddc25a37294"
    SECRET_ARRAY_PATTERN = re.compile(r'"secret":\[(\d+(?:,\d+)+)]')
    SECRET_VERSIONED_PATTERN = re.compile(r'\{secret:(?:"([^"]+)"|\'([^\']+)\'),version:(\d+)\}')
    SCRIPT_SRC_PATTERN = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
    META_TAG_PATTERN = re.compile(r'<meta[^>]+(?:name|property)="([^"]+)"[^>]+content="([^"]*)"', re.IGNORECASE)
    JSON_LD_PATTERN = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.IGNORECASE | re.DOTALL)
    PLAYLIST_CARD_PATTERN = re.compile(
        r'<a[^>]+href="/playlist/([A-Za-z0-9]+)"[^>]*>'
        r'(?:.*?)<img[^>]+src="([^"]+)"[^>]*>'
        r'(?:.*?)<span[^>]*>([^<]+)</span>',
        re.IGNORECASE | re.DOTALL,
    )

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, playlist_extra_page_limit: int = 0):
        self.spotify_cache_file = spotify_cache_file
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://api.spotify.com/v1"
        self.spotify_cache = {}
        self.disabled = False
        self.type = "api" if client_id and client_secret else "visitor"
        self.token_refresh = False
        self.playlist_extra_page_limit = playlist_extra_page_limit

        try:
            with open(self.spotify_cache_file) as f:
                self.spotify_cache = json.load(f)
                self.type = self.spotify_cache.get("type", self.type)
        except FileNotFoundError:
            pass

    async def request(self, path: str, params: dict = None):

        if self.disabled:
            return

        headers = {'Authorization': f'Bearer {await self.get_valid_access_token()}'}

        async with ClientSession() as session:
            async with session.get(f"{self.base_url}/{path}", headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    await self.get_access_token()
                    return await self.request(path=path, params=params)
                elif response.status == 404:
                    raise GenericError("**Não houve resultado para o link informado (confira se o link está correto ou se o conteúdo dele está privado ou se foi deletado).**\n\n"
                                       f"{str(response.url).replace('api.', 'open.').replace('/v1/', '/').replace('s/', '/')}")
                elif response.status == 403:
                    url = str(response.url).replace('api.', 'open.').replace('/v1/', '/').replace('s/', '/')
                    raise GenericError(
                        "**O Spotify bloqueou o acesso a esse conteúdo para minha sessão atual.**\n\n"
                        "`Isso costuma acontecer por restrição regional, conteúdo privado ou limitação temporária da API.`\n\n"
                        f"{url}"
                    )
                elif response.status == 429:
                    self.disabled = True
                    print(f"⚠️ - Spotify: Suporte interno desativado devido a ratelimit (429).")
                    return
                else:
                    try:
                        response.raise_for_status()
                    except ClientResponseError as e:
                        raise GenericError(
                            f"**Falha ao consultar o Spotify:** `{e.status} {e.message or 'HTTP error'}`"
                        ) from e

    @staticmethod
    def _is_spotify_access_blocked(error: Exception) -> bool:
        return isinstance(error, GenericError) and "Spotify bloqueou o acesso" in getattr(error, "text", "")

    @staticmethod
    def _extract_search_term(query: str) -> str:
        if not (match := spotify_search_regex.match(query)):
            return ""

        raw_term = match.group(1).strip("/")

        for suffix in ("tracks", "albums", "artists", "playlists", "shows", "episodes", "profiles"):
            token = f"/{suffix}"
            if raw_term.lower().endswith(token):
                raw_term = raw_term[:-len(token)]
                break

        return unquote(raw_term.replace("/", " ")).strip()

    async def get_track_info(self, track_id: str):
        if self.type == "visitor":
            try:
                result = await self._get_track_info_visitor(track_id)
                if result.get("name"):
                    return result
            except Exception:
                pass
            return await self._get_track_info_public(track_id)
        try:
            return await self.request(path=f'tracks/{track_id}')
        except Exception as e:
            if self._is_spotify_access_blocked(e):
                return await self._get_track_info_public(track_id)
            raise

    async def get_album_info(self, album_id: str):
        if self.type == "visitor":
            return await self._get_album_info_public(album_id)
        try:
            return await self.request(path=f'albums/{album_id}')
        except Exception as e:
            if self._is_spotify_access_blocked(e):
                return await self._get_album_info_public(album_id)
            raise

    async def get_artist_top(self, artist_id: str):
        return await self.request(path=f'artists/{artist_id}/top-tracks')

    async def get_playlist_info(self, playlist_id: str):
        if self.type == "visitor":
            return await self._get_playlist_info_public(playlist_id)

        try:
            result = await self.request(path=f"playlists/{playlist_id}")
        except Exception as e:
            if self._is_spotify_access_blocked(e):
                return await self._get_playlist_info_public(playlist_id)
            raise

        if len(result["tracks"]["items"]) == 100 and self.playlist_extra_page_limit > 0:

            offset = 101
            page_count = 0

            while True:
                try:
                    result_extra = await self.request(path=f"playlists/{playlist_id}/tracks?offset={offset}&limit=100")
                except:
                    traceback.print_exc()
                    break
                else:
                    result["tracks"]["items"].extend(result_extra["items"])
                    if result_extra["next"] and page_count <= self.playlist_extra_page_limit:
                        offset += 100
                        page_count += 1
                        continue
                    break

        return result

    async def get_user_info(self, user_id: str):
        if self.type == "visitor":
            return await self._get_user_info_public(user_id)
        try:
            return await self.request(path=f"users/{user_id}")
        except Exception as e:
            if self._is_spotify_access_blocked(e):
                return await self._get_user_info_public(user_id)
            raise

    async def get_user_playlists(self, user_id: str):
        if self.type == "visitor":
            info = await self._get_user_info_public(user_id)
            return {
                "items": info["items"],
                "total": info["total"],
                "external_urls": {"spotify": info["external_urls"]["spotify"]},
                "id": info["id"],
                "display_name": info["display_name"],
                "images": info["images"],
            }
        try:
            return await self.request(path=f"users/{user_id}/playlists")
        except Exception as e:
            if self._is_spotify_access_blocked(e):
                info = await self._get_user_info_public(user_id)
                return {
                    "items": info["items"],
                    "total": info["total"],
                    "external_urls": {"spotify": info["external_urls"]["spotify"]},
                    "id": info["id"],
                    "display_name": info["display_name"],
                    "images": info["images"],
                }
            raise

    async def get_recommendations(self, seed_tracks: Union[list, str], limit=10):
        if isinstance(seed_tracks, str):
            track_ids = seed_tracks
        else:
            track_ids = ",".join(seed_tracks)

        if self.type == "visitor":
            track_ids = track_ids.split(",")[0]
            return await self._get_recommendations_visitor(track_ids, limit)

        return await self.request(path='recommendations', params={
            'seed_tracks': track_ids, 'limit': limit
        })

    async def track_search(self, query: str, limit: int = 10):
        if self.type == "visitor":
            return await self._track_search_visitor(query=query, limit=limit)

        try:
            return await self.request(path='search', params={
                'q': query, 'type': 'track', 'limit': limit
            })
        except Exception as e:
            if self._is_spotify_access_blocked(e):
                payload = await self._get_visitor_access_token_payload()
                return await self._track_search_visitor(
                    query=query,
                    limit=limit,
                    access_token=payload["accessToken"]
                )
            raise

    async def _post_partner_api(self, operation_name: str, sha256_hash: str, variables: dict, access_token: str = None) -> dict:
        headers = {
            "Authorization": f"Bearer {access_token or await self.get_valid_access_token()}",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Spotify-App-Version": "1.2.80.289.gd6b01cc3",
            "Referer": "https://open.spotify.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/134.0.6998.178 Spotify/1.2.65.255 Safari/537.36"
            ),
        }
        payload = {
            "operationName": operation_name,
            "variables": variables,
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": sha256_hash,
                }
            },
        }

        async with ClientSession(headers=headers) as session:
            async with session.post(self.PARTNER_API_BASE, json=payload) as response:
                if response.status == 401 and not access_token:
                    await self.get_access_token()
                    return await self._post_partner_api(operation_name, sha256_hash, variables)
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", "1") or "1")
                    await asyncio.sleep(max(1, retry_after))
                    return await self._post_partner_api(operation_name, sha256_hash, variables, access_token=access_token)

                data = await response.json(content_type=None)

                if response.status >= 400:
                    response.raise_for_status()

                return data

    @staticmethod
    def _spotify_uri_to_id(uri: str) -> str:
        try:
            return uri.rsplit(":", maxsplit=1)[-1]
        except AttributeError:
            return ""

    @staticmethod
    def _extract_id_from_url(url: str) -> str:
        path_parts = [part for part in urlparse(url).path.split("/") if part]
        return path_parts[-1] if path_parts else ""

    @classmethod
    def _extract_meta_tags(cls, html: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
        pairs = cls.META_TAG_PATTERN.findall(html)
        meta = {}
        for key, value in pairs:
            meta.setdefault(key, value)
        return meta, pairs

    @classmethod
    def _extract_json_ld(cls, html: str) -> dict:
        if not (match := cls.JSON_LD_PATTERN.search(html)):
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _parse_description_parts(description: str) -> list[str]:
        return [part.strip() for part in (description or "").split("·")]

    async def _fetch_public_spotify_page(self, entity_type: str, entity_id: str) -> str:
        async with ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
            async with session.get(f"{self.PUBLIC_BASE_URL}/{entity_type}/{entity_id}") as response:
                response.raise_for_status()
                return await response.text()

    @staticmethod
    def _pick_image_url(images) -> str:
        for image in images or []:
            if isinstance(image, dict) and image.get("url"):
                return image["url"]
        return ""

    @staticmethod
    def _coerce_duration_ms(value) -> int:
        try:
            if value is None:
                return 0
            if isinstance(value, bool):
                return int(value)
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _normalize_partner_track(self, track_data: dict) -> dict:
        album_data = track_data.get("albumOfTrack") or track_data.get("album") or {}
        album_cover = (album_data.get("coverArt") or {}).get("sources") or album_data.get("images") or []
        artist_items = (track_data.get("artists") or {}).get("items") or track_data.get("artists") or []
        track_id = track_data.get("id") or self._spotify_uri_to_id(track_data.get("uri"))
        track_url = (
            ((track_data.get("sharingInfo") or {}).get("shareUrl"))
            or ((track_data.get("external_urls") or {}).get("spotify"))
            or (f"https://open.spotify.com/track/{track_id}" if track_id else "")
        )
        album_id = album_data.get("id") or self._spotify_uri_to_id(album_data.get("uri"))
        album_url = (
            ((album_data.get("sharingInfo") or {}).get("shareUrl"))
            or ((album_data.get("external_urls") or {}).get("spotify"))
            or (f"https://open.spotify.com/album/{album_id}" if album_id else "")
        )

        artists = []

        for artist in artist_items:
            artist_data = (artist.get("profile") and {"name": artist["profile"].get("name")}) or artist
            artist_id = artist.get("id") or self._spotify_uri_to_id(artist.get("uri"))
            artist_url = (
                ((artist.get("sharingInfo") or {}).get("shareUrl"))
                or ((artist.get("external_urls") or {}).get("spotify"))
                or (f"https://open.spotify.com/artist/{artist_id}" if artist_id else "")
            )
            artists.append({
                "name": artist_data.get("name") or "",
                "id": artist_id,
                "external_urls": {"spotify": artist_url},
            })

        return {
            "name": track_data.get("name"),
            "duration_ms": self._coerce_duration_ms(track_data.get("duration") or track_data.get("duration_ms")),
            "id": track_id,
            "uri": track_data.get("uri"),
            "artists": artists,
            "album": {
                "name": album_data.get("name") or "",
                "id": album_id,
                "images": [{"url": self._pick_image_url(album_cover)}] if self._pick_image_url(album_cover) else [],
                "external_urls": {"spotify": album_url},
                "total_tracks": album_data.get("totalTracks") or album_data.get("total_tracks") or 0,
            },
            "external_urls": {"spotify": track_url},
            "external_ids": {},
        }

    async def _get_track_info_visitor(self, track_id: str) -> dict:
        data = await self._post_partner_api(
            operation_name=self.TRACK_OPERATION,
            sha256_hash=self.TRACK_HASH,
            variables={"uri": f"spotify:track:{track_id}"},
        )
        track_data = (((data or {}).get("data") or {}).get("trackUnion")) or {}
        if not track_data:
            raise GenericError("**Não houve resultado para a música do spotify informada...**")
        return self._normalize_partner_track(track_data)

    async def _get_track_info_public(self, track_id: str) -> dict:
        html = await self._fetch_public_spotify_page("track", track_id)
        meta, _pairs = self._extract_meta_tags(html)
        ld_json = self._extract_json_ld(html)
        description_parts = self._parse_description_parts(meta.get("og:description") or ld_json.get("description") or "")
        artist_name = description_parts[0] if description_parts else ""
        album_name = description_parts[1] if len(description_parts) >= 2 else ""
        album_id = self._extract_id_from_url(meta.get("music:album", ""))
        track_url = f"https://open.spotify.com/track/{track_id}"
        album_url = f"https://open.spotify.com/album/{album_id}" if album_id else ""
        artwork_url = meta.get("og:image", "")

        return {
            "name": meta.get("og:title") or ld_json.get("name") or "",
            "duration_ms": self._coerce_duration_ms((float(meta.get("music:duration", "0") or 0) * 1000)),
            "id": track_id,
            "uri": f"spotify:track:{track_id}",
            "artists": [{
                "name": artist_name,
                "id": self._extract_id_from_url(meta.get("music:musician", "")),
                "external_urls": {
                    "spotify": meta.get("music:musician", "")
                }
            }] if artist_name else [],
            "album": {
                "name": album_name,
                "id": album_id,
                "images": [{"url": artwork_url}] if artwork_url else [],
                "external_urls": {"spotify": album_url},
                "total_tracks": 0,
            },
            "artworkUrl": artwork_url,
            "external_urls": {"spotify": track_url},
            "external_ids": {},
            "track_number": int(meta.get("music:album:track", "0") or 0),
            "release_date": meta.get("music:release_date") or ld_json.get("datePublished") or "",
        }

    async def _get_public_track_infos(self, track_ids: list[str]) -> list[dict]:
        semaphore = asyncio.Semaphore(5)

        async def load(track_id: str) -> dict:
            async with semaphore:
                return await self._get_track_info_public(track_id)

        return await asyncio.gather(*(load(track_id) for track_id in track_ids))

    async def _get_album_info_public(self, album_id: str) -> dict:
        html = await self._fetch_public_spotify_page("album", album_id)
        meta, pairs = self._extract_meta_tags(html)
        ld_json = self._extract_json_ld(html)
        description_parts = self._parse_description_parts(meta.get("og:description") or "")
        artist_name = description_parts[0] if description_parts else ""
        track_ids = [self._extract_id_from_url(value) for key, value in pairs if key == "music:song"]
        tracks = await self._get_public_track_infos(track_ids) if track_ids else []
        total_tracks = len(track_ids)

        return {
            "name": meta.get("og:title", "").split(" - Album by ", 1)[0] or ld_json.get("name") or "",
            "id": album_id,
            "uri": f"spotify:album:{album_id}",
            "artists": [{"name": artist_name}] if artist_name else [],
            "images": [{"url": meta.get("og:image", "")}] if meta.get("og:image") else [],
            "external_urls": {"spotify": f"https://open.spotify.com/album/{album_id}"},
            "tracks": {"items": tracks},
            "total_tracks": total_tracks,
            "release_date": meta.get("music:release_date") or ld_json.get("datePublished") or "",
        }

    async def _get_playlist_info_public(self, playlist_id: str) -> dict:
        html = await self._fetch_public_spotify_page("playlist", playlist_id)
        meta, pairs = self._extract_meta_tags(html)
        ld_json = self._extract_json_ld(html)
        description_parts = self._parse_description_parts(meta.get("og:description") or "")
        owner_name = description_parts[1] if len(description_parts) >= 2 else ""
        owner_id = self._extract_id_from_url(meta.get("music:creator", ""))
        track_ids = [self._extract_id_from_url(value) for key, value in pairs if key == "music:song"]
        tracks = await self._get_public_track_infos(track_ids) if track_ids else []

        return {
            "name": meta.get("og:title") or ld_json.get("name") or "",
            "id": playlist_id,
            "uri": f"spotify:playlist:{playlist_id}",
            "images": [{"url": meta.get("og:image", "")}] if meta.get("og:image") else [],
            "external_urls": {"spotify": f"https://open.spotify.com/playlist/{playlist_id}"},
            "owner": {
                "display_name": owner_name,
                "id": owner_id,
                "external_urls": {"spotify": f"https://open.spotify.com/user/{owner_id}" if owner_id else ""},
            },
            "tracks": {"items": [{"track": track} for track in tracks]},
            "description": meta.get("description") or ld_json.get("description") or "",
        }

    async def _get_user_info_public(self, user_id: str) -> dict:
        html = await self._fetch_public_spotify_page("user", user_id)
        meta, _pairs = self._extract_meta_tags(html)
        items = []
        seen_playlist_ids = set()

        for playlist_id, image_url, title in self.PLAYLIST_CARD_PATTERN.findall(html):
            if playlist_id in seen_playlist_ids:
                continue
            seen_playlist_ids.add(playlist_id)
            items.append({
                "name": title.strip(),
                "id": playlist_id,
                "images": [{"url": image_url}] if image_url else [],
                "external_urls": {"spotify": f"https://open.spotify.com/playlist/{playlist_id}"},
                "owner": {
                    "id": user_id,
                    "display_name": meta.get("og:title") or "",
                    "external_urls": {"spotify": f"https://open.spotify.com/user/{user_id}"},
                },
                "tracks": {"total": 0},
            })

        match = re.search(r'(\d+)\s+public playlists', html, flags=re.IGNORECASE)
        total = int(match.group(1)) if match else len(items)

        return {
            "display_name": meta.get("og:title") or "",
            "id": user_id,
            "external_urls": {"spotify": f"https://open.spotify.com/user/{user_id}"},
            "images": [{"url": meta.get("og:image", "")}] if meta.get("og:image") else [],
            "followers": {"total": 0},
            "items": items,
            "total": total,
            "description": meta.get("description") or meta.get("og:description") or "",
        }

    async def _track_search_visitor(self, query: str, limit: int = 10, access_token: str = None) -> dict:
        data = await self._post_partner_api(
            operation_name=self.SEARCH_OPERATION,
            sha256_hash=self.SEARCH_HASH,
            variables={
                "searchTerm": query,
                "offset": 0,
                "limit": limit,
                "numberOfTopResults": 5,
                "includeAudiobooks": True,
                "includeArtistHasConcertsField": False,
                "includePreReleases": True,
                "includeAuthors": False,
            },
            access_token=access_token,
        )

        items = (
            (((data or {}).get("data") or {}).get("searchV2") or {})
            .get("tracksV2", {})
            .get("items", [])
        )
        tracks = []

        for item in items:
            track_data = (((item or {}).get("item") or {}).get("data")) or {}
            if track_data:
                tracks.append(self._normalize_partner_track(track_data))

        return {"tracks": {"items": tracks}, "tracks_data": tracks}

    async def _get_recommendations_visitor(self, seed_track_id: str, limit: int) -> dict:
        data = await self._post_partner_api(
            operation_name=self.RECOMMENDATIONS_OPERATION,
            sha256_hash=self.RECOMMENDATIONS_HASH,
            variables={"uri": f"spotify:track:{seed_track_id}"},
        )

        payload = (data or {}).get("data") or {}
        items = ((payload.get("internalLinkRecommenderTrack") or {}).get("items")) or (
            (payload.get("seoRecommendedTrack") or {}).get("items") or []
        )

        tracks = []

        for item in items[:limit]:
            track_data = (((item or {}).get("content") or {}).get("data")) or ((item or {}).get("data")) or {}
            if track_data and track_data.get("__typename") == "Track":
                tracks.append(self._normalize_partner_track(track_data))

        return {"tracks": tracks}

    @staticmethod
    def _generate_totp(secret: bytes, period: int = 30, digits: int = 6) -> str:
        counter = int(time.time() // period)
        counter_bytes = struct.pack(">Q", counter)
        digest = hmac.new(secret, counter_bytes, sha1).digest()
        offset = digest[-1] & 0x0F
        binary = (
            ((digest[offset] & 0x7F) << 24)
            | ((digest[offset + 1] & 0xFF) << 16)
            | ((digest[offset + 2] & 0xFF) << 8)
            | (digest[offset + 3] & 0xFF)
        )
        otp = binary % (10 ** digits)
        return f"{otp:0{digits}d}"

    @staticmethod
    def _transform_secret_values(secret_values: list[int]) -> bytes:
        transformed_values = [
            value ^ ((index % 33) + 9)
            for index, value in enumerate(secret_values)
        ]
        return "".join(str(value) for value in transformed_values).encode("utf-8")

    async def _request_spotify_web_secret(self, session: ClientSession) -> tuple[bytes, str]:
        homepage_url = "https://open.spotify.com/"

        async with session.get(homepage_url) as response:
            response.raise_for_status()
            html = await response.text()

        script_urls = []

        for script_url in self.SCRIPT_SRC_PATTERN.findall(html):
            if "web-player" in script_url and "vendor" not in script_url:
                script_urls.append(urljoin(homepage_url, script_url))

        if not script_urls:
            raise RuntimeError("Nenhum script do Web Player foi encontrado na pagina do Spotify.")

        for script_url in script_urls:
            async with session.get(script_url) as response:
                response.raise_for_status()
                script_content = await response.text()

            if match := self.SECRET_ARRAY_PATTERN.search(script_content):
                secret_array = [int(value.strip()) for value in match.group(1).split(",")]
                return self._transform_secret_values(secret_array), "7"

            if matches := self.SECRET_VERSIONED_PATTERN.findall(script_content):
                secret_raw_a, secret_raw_b, secret_version = matches[0]
                secret_raw = secret_raw_a or secret_raw_b
                secret_values = [ord(char) for char in secret_raw]
                return self._transform_secret_values(secret_values), secret_version

        raise RuntimeError("Nao foi possivel extrair o secret do Web Player do Spotify.")

    async def _get_visitor_token_via_web_player(self) -> dict:
        headers = {
            "App-Platform": "WebPlayer",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
        }

        async with ClientSession(headers=headers) as session:
            secret, secret_version = await self._request_spotify_web_secret(session)
            totp = self._generate_totp(secret)
            access_token_url = (
                "https://open.spotify.com/api/token"
                f"?reason=transport&productType=web-player&totp={totp}"
                f"&totpServer=unavailable&totpVer={secret_version}"
            )

            async with session.get(access_token_url) as response:
                data = await response.json(content_type=None)

                if response.status >= 400:
                    error = data.get("error") if isinstance(data, dict) else None
                    raise RuntimeError(f"Spotify retornou erro no token guest: {error or response.status}")

                if data.get("error"):
                    raise RuntimeError(f"Spotify retornou erro no token guest: {data['error']}")

                return data

    async def _get_visitor_token_legacy(self) -> dict:
        access_token_url = "https://open.spotify.com/get_access_token?reason=transport&productType=embed"
        headers = {
            "App-Platform": "WebPlayer",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
        }

        async with ClientSession(headers=headers) as session:
            async with session.get(access_token_url) as response:
                data = await response.json(content_type=None)

                if response.status >= 400:
                    error = data.get("error") if isinstance(data, dict) else None
                    raise RuntimeError(f"Spotify retornou erro no endpoint legacy guest: {error or response.status}")

                return data

    async def _get_visitor_access_token_payload(self) -> dict:
        errors = []

        for loader in (self._get_visitor_token_via_web_player, self._get_visitor_token_legacy):
            try:
                return await loader()
            except Exception as exc:
                errors.append(repr(exc))

        raise RuntimeError("Falha ao obter token guest do Spotify. Tentativas: " + " | ".join(errors))

    async def get_access_token(self):

        if self.token_refresh:
            while self.token_refresh:
                await asyncio.sleep(1)
            return

        self.token_refresh = True

        try:
            if self.client_id and self.client_secret:
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
                    print(f"⚠️ - Spotify: Ocorreu um erro ao obter token oficial: {data.get('error_description', data['error'])}")
                    self.client_id = None
                    self.client_secret = None
                    self.type = "visitor"
                    await self.get_access_token()
                    return

                self.spotify_cache = data
                self.type = "api"
                self.spotify_cache["type"] = "api"
                self.spotify_cache["expires_at"] = time.time() + self.spotify_cache["expires_in"]

                print("🎶 - Access token do spotify obtido com sucesso via API Oficial.")

            else:
                data = await self._get_visitor_access_token_payload()
                expires_at = (data.get("accessTokenExpirationTimestampMs", 0) or 0) / 1000

                if not expires_at:
                    expires_at = time.time() + 300

                self.spotify_cache = {
                    "access_token": data["accessToken"],
                    "expires_in": max(0, int(expires_at - time.time())),
                    "expires_at": expires_at,
                    "type": "visitor",
                }
                self.type = "visitor"

                print("🎶 - Access token do spotify obtido com sucesso do tipo: visitante.")

        except Exception as e:
            self.token_refresh = False
            raise e

        self.token_refresh = False

        async with aiofiles.open(self.spotify_cache_file, "w") as f:
            await f.write(json.dumps(self.spotify_cache))

    async def get_valid_access_token(self):
        if not (exp_date := self.spotify_cache.get("expires_at")) or time.time() >= exp_date:
            await self.get_access_token()
        return self.spotify_cache["access_token"]

    async def get_tracks(self, bot: BotCore, requester: int, query: str, search: bool = True, check_title: float = None):

        if spotify_link_regex.match(query):
            async with bot.session.get(query, allow_redirects=False) as r:
                if 'location' not in r.headers:
                    raise GenericError("**Falha ao obter resultado para o link informado...**")
                query = str(r.headers["location"])

        if spotify_search_term := self._extract_search_term(query):
            query = spotify_search_term

        if not (matches := spotify_regex.match(query)) and not self.disabled:

            if URL_REG.match(query) or not search:
                return

            r = await self.track_search(query=query)

            tracks = []

            try:
                tracks_result = r['tracks']['items']
            except KeyError:
                pass
            else:
                for result in tracks_result:

                    trackinfo = {
                        'title': result["name"],
                        'author': result["artists"][0]["name"] or "Unknown Artist",
                        'length': self._coerce_duration_ms(result["duration_ms"]),
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

        if self.disabled:

            if [n for n in bot.music.nodes.values() if "spotify" in n.info.get("sourceManagers", [])]:
                return

            raise GenericError("**O suporte a links do spotify está temporariamente desativado.**")

        url_type, url_id = matches.groups()

        if url_type == "track":

            result = await self.get_track_info(url_id)

            if not result:
                raise GenericError("**Não houve resultados para o link da música informado...**")

            trackinfo = {
                'title': result["name"],
                'author': result["artists"][0]["name"] or "Unknown Artist",
                'length': self._coerce_duration_ms(result["duration_ms"]),
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
                bot.pool.playlist_cache[cache_key] = result

            if not result:
                raise GenericError("**Não houve resultados para o link do álbum informado...**")

            album_tracks = result.get("tracks") or {}

            if isinstance(album_tracks, dict):
                tracks_items = album_tracks.get("items") or []
            else:
                tracks_items = album_tracks or []

            if not tracks_items:
                raise GenericError("**Não houve resultados para o link do álbum informado...**")

            try:
                thumb = tracks_items[0]["album"]["images"][0]["url"]
            except:
                thumb = ""

            if len(tracks_items) < 2:

                track = tracks_items[0]

                trackinfo = {
                    'title': track["name"],
                    'author': track["artists"][0]["name"] or "Unknown Artist",
                    'length': self._coerce_duration_ms(track["duration_ms"]),
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

            for t in tracks_items:
                t["album"] = result

            tracks_data = tracks_items

        elif url_type == "artist":

            cache_key = f"partial:spotify:{url_type}:{url_id}"

            if not (result := bot.pool.playlist_cache.get(cache_key)):
                result = await self.get_artist_top(url_id)
                bot.pool.playlist_cache[cache_key] = result

            if not result or not result.get("tracks"):
                raise GenericError("**Não houve resultados para o link do artista informado...**")

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

            if not result:
                raise GenericError("**Não houve resultados para o link da playlist informada...**")

            data["playlistInfo"]["name"] = result["name"]
            try:
                data["playlistInfo"]["thumb"] = result["images"][0]["url"]
            except (IndexError, KeyError, TypeError):
                data["playlistInfo"]["thumb"] = ""

            playlist_tracks = (result.get("tracks") or {}).get("items") or []

            if not playlist_tracks:
                raise GenericError("**Não houve resultados para o link da playlist informada...**")

            tracks_data = [t["track"] for t in playlist_tracks]

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
                'length': self._coerce_duration_ms(t["duration_ms"]),
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

        return playlist
