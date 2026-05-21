"""MIT License

Copyright (c) 2019-2020 PythonistaGuild

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import asyncio
import datetime
import inspect
import json
import logging
import os
import pprint
import re
import traceback
from typing import Any, Callable, Dict, Optional, Union
from urllib.parse import quote

from rapidfuzz import fuzz

from utils.music.youtube_trusted_session_generator import Browser
from .backoff import ExponentialBackoff
from .errors import *
from .player import Player, Track, TrackPlaylist
from .websocket import WebSocket

__log__ = logging.getLogger(__name__)

yt_playlist_regex = re.compile(r"[?&]list=([^&]+)")
yt_video_regex = re.compile(r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[&?]|$)")
spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|artist)/([a-zA-Z0-9]+)")
deezer_regex = re.compile(r"(https?://)?(www\.)?deezer\.com/(?P<countrycode>[a-zA-Z]{2}/)?(?P<type>album|playlist|artist|profile)/(?P<identifier>[0-9]+)")
soundcloud_regex = re.compile(r"https://soundcloud\.com/([^/]+)/sets/([^/]+)")

exclude_tags = ["remix", "edit", "extend", "compilation", "mashup", "mixed"]

class Node:
    """A WaveLink Node instance.

    .. warning::
        You should not create :class:`Node` objects manually. Instead you should use, :func:`Client.initiate_node`.

    Attributes
    ------------
    host: str
        The host address the node is connected to.
    port: int
        The port the node is connected to.
    rest_uri: str
        The rest server address the node is connecte to.
    region: str
        The region provided to the node on connection.
    identifier: str
        The unique indentifier associated with the node.
    """

    def __init__(self, host: str,
                 port: int,
                 shards: int,
                 user_id: int,
                 *,
                 client,
                 session,
                 rest_uri: str,
                 password: str,
                 region: str,
                 identifier: str,
                 shard_id: int = None,
                 secure: bool = False,
                 heartbeat: float = None,
                 user_agent: str = None,
                 auto_reconnect: bool = True,
                 resume_key: Optional[str] = None,
                 dumps: Callable[[Dict[str, Any]], Union[str, bytes]] = json.dumps,
                 version: int = 3,
                 **kwargs
                 ):

        self.host = host
        self.port = port
        self.rest_uri = rest_uri
        self.shards = shards
        self.uid = user_id
        self.password = password
        self.region = region
        self.identifier = identifier
        self.secure = secure
        self.heartbeat = heartbeat
        self.user_agent = user_agent
        self.auto_reconnect = auto_reconnect
        self.resume_key = resume_key or str(os.urandom(8).hex())
        self.version = 0
        self.session_id: Optional[int] = None

        self._dumps = dumps

        self.shard_id = shard_id

        self.players = {}

        self.session = session
        self._websocket = None
        self._client = client

        self.hook = None
        self.available = True
        self.restarting = False

        self.stats = None
        self.info = {}

        self.update_info()

        self.max_retries = kwargs.pop("max_retries", 1)
        self.only_use_native_search_providers = kwargs.pop("only_use_native_search_providers", False)
        self.search_providers = []
        self.partial_providers = []
        self.original_providers = []
        self.native_sources = kwargs.pop("native_sources", set())

        self._closing = False
        self._is_connecting = False

        self._retry_count = 0
        self._retry_dt = datetime.datetime.utcnow()

    def __repr__(self):
        return f'{self.identifier} | {self.region} | (Shard: {self.shard_id})'

    def update_info(self, data: dict = None):
        if not data:
            self.info = {"sourceManagers": [], "plugins": {}}
        else:
            self.info = data
            if (version:=data.get("check_version")):
                self.version = version
            if self.version > 3:
                self.info["plugins"] = {d["name"]: d["version"] for d in self.info["plugins"]}

    @property
    def is_available(self) -> bool:
        """Return whether the Node is available or not."""
        if self.version == 4 and not self.session_id:
            return False

        try:
            ws_connected = self._websocket.is_connected
        except AttributeError:
            ws_connected = False

        return ws_connected and self.available and not self._closing and not self._is_connecting

    def close(self) -> None:
        """Close the node and make it unavailable."""
        self.available = False

    def open(self) -> None:
        """Open the node and make it available."""
        self.available = True

    @property
    def penalty(self) -> float:
        """Returns the load-balancing penalty for this node."""
        if not self.available or not self.stats:
            return 9e30

        return self.stats.penalty.total

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.password,
            "User-Id": str(self.uid),
            "Client-Name": "Wavelink/custom",
        }

    async def connect(self, *args, **kwargs) -> None:

        if self._is_connecting:
            return

        self._is_connecting = True

        backoff = 9
        retries = 1
        exception = None
        max_retries = int(self.max_retries)

        if (info:=kwargs.get("info")):
            self.update_info(info)

        else:
            print(f"📶 - {self._client.bot.user} - Iniciando servidor de música: {self.identifier}")
            while not self._client.bot.is_closed():
                try:
                    async with self._client.bot.session.get(f"{self.rest_uri}/v4/info", timeout=45, headers={'Authorization': self.password}) as r:
                        if r.status == 200:
                            self.info = await r.json()
                            self.version = 4
                        elif r.status != 404:
                            raise Exception(f"❌ - {self._client.bot.user} - [{r.status}]: {await r.text()}"[:300])
                        else:
                            self.version = 3
                            self.info["sourceManagers"] = ["youtube", "soundcloud", "http"]
                            return
                        break
                except Exception as e:
                    if retries >= max_retries:
                        self._is_connecting = False
                        print(
                            f"❌ - {self._client.bot.user} - Falha ao conectar no servidor [{self.identifier}]." +
                            (f"\nCausa: {repr(exception)}" if exception else ""))
                        return
                    exception = e
                    if self.identifier != "LOCAL":
                        print(f'⚠️ - {self._client.bot.user} - Falha ao conectar no servidor [{self.identifier}], '
                              f'nova tentativa [{retries}/{max_retries}] em {backoff} segundos.')
                    backoff += 2
                    retries += 1
                    await asyncio.sleep(backoff)
                    continue

        if not self._websocket:

            self._websocket = WebSocket(node=self,
                                        host=self.host,
                                        port=self.port,
                                        password=self.password,
                                        shard_count=self.shards,
                                        user_id=self.uid,
                                        user_agent=self.user_agent,
                                        secure=self.secure,
                                        dumps=self._dumps,
                                        auto_reconnect=self.auto_reconnect,
                                        **kwargs,
                                        )

        if not self._websocket.is_connected:
            await self._websocket._connect()

        self.available = True
        self._is_connecting = False

        __log__.info(f'NODE | {self.identifier} connected:: {self.__repr__()}')

    async def refresh_potoken(self, sandbox=True, browser_executable_path=None):

        browser = Browser()

        try:
            ytid = self._client.bot.config["POTOKEN_YTID"]
        except:
            ytid = "jNQXAC9IVRw"

        try:
            await browser.start(sandbox=sandbox, browser_executable_path=browser_executable_path, ytid=ytid)
        except Exception as e:
            if not browser.data:
                raise e
            else:
                traceback.print_exc()

        async with self.session.post(url=f"{self.rest_uri}/youtube",
            json={
              "poToken": browser.data["po_token"],
              "visitorData": browser.data["visitor_data"]
            }, headers=self._websocket.headers
        ) as r:
            return f"{r.status}: {await r.text()}"

    async def update_player(self, guild_id: int, data: dict, replace: bool = False):

        player = self._client.bot.music.players[guild_id]

        if not self.session_id:
            try:
                player._new_node_task = player.bot.loop.create_task(player._wait_for_new_node())
                return
            except:
                pass
            raise MissingSessionID(self)

        no_replace: bool = not replace

        no_replace_qs = "true" if no_replace else "false"
        uri: str = f"{self.rest_uri}/v4/sessions/{self.session_id}/players/{guild_id}?noReplace={no_replace_qs}"

        if data.get("filters") == {}:
            try:
                del data["filters"]
            except KeyError:
                pass

        if self.info.get("isNodelink"):
            # nodelink fix

            if not data.get("track"):
                try:
                    data["volume"]
                except KeyError:
                    pass

            if not data.get("filters"):

                try:
                    del data["filters"]
                except KeyError:
                    pass

            try:
                if not data["track"]["pluginInfo"]:
                    del data["track"]["pluginInfo"]
            except KeyError:
                pass
        else:
            try:
                if not data["voice"].get("channelId"):
                    del data["voice"]["channelId"]
            except KeyError:
                pass

            try:
                del data["track"]["pluginInfo"]
            except KeyError:
                pass

        try:
            player.status.update(data)
        except AttributeError:
            player.status = data

        async with self.session.patch(url=uri, json=data, headers=self._websocket.headers) as resp:

            try:
                resp_data = await resp.json()
            except:
                resp_data = await resp.text()

            if resp.status == 200:
                return resp_data

            # Nodelink: worker restarted — player no longer exists in the new session.
            # Re-send voice state and, if a track was active, rebuild the full payload.
            if resp.status == 404 and self.info.get("isNodelink"):
                __log__.warning(
                    f"NODE | {self.identifier} | Player not found (worker restart?). "
                    f"Attempting to recreate player for guild {guild_id}."
                )
                try:
                    return await self._recreate_nodelink_player(player=player, guild_id=guild_id, original_data=data)
                except Exception as rebuild_err:
                    __log__.error(f"NODE | {self.identifier} | Failed to recreate player: {rebuild_err}")
                return

            await asyncio.sleep(1.5)

        if new_node := self._client.get_best_node(ignore_node=self):
            await self.players[guild_id].change_node(new_node.identifier)
            return

        raise WavelinkException(f"{self.identifier}: UpdatePlayer Failed = {resp.status}: {resp_data}" + f"\n\nData info:\n{pprint.pformat(data)}\n")

    async def _recreate_nodelink_player(self, player: Player, guild_id: int, original_data: dict):
        if getattr(player, "_nodelink_recreating", False):
            __log__.warning(
                f"NODE | {self.identifier} | Player recreate already in progress for guild {guild_id}. Skipping duplicate attempt."
            )
            return

        player._nodelink_recreating = True

        try:
            last_error = None

            for attempt, delay in enumerate((0, 0.75, 1.5, 3), start=1):
                if delay:
                    await asyncio.sleep(delay)

                rebuild_payload = {}

                try:
                    rebuild_payload["voice"] = {
                        "sessionId": player._voice_state["sessionId"],
                        "token": player._voice_state["event"]["token"],
                        "endpoint": player._voice_state["event"]["endpoint"],
                        "channelId": str(player.channel_id) if player.channel_id else None,
                    }
                except KeyError:
                    if "voice" in original_data:
                        rebuild_payload["voice"] = dict(original_data["voice"])

                if player.current and player.current_encoded:
                    rebuild_payload.update(
                        {
                            "track": {
                                "encoded": player.current_encoded,
                            },
                            "volume": player.volume,
                            "position": int(player.position),
                            "paused": player.paused,
                        }
                    )
                    if player.filters:
                        rebuild_payload["filters"] = player.filters

                for key, value in original_data.items():
                    rebuild_payload.setdefault(key, value)

                rebuild_uri = f"{self.rest_uri}/v4/sessions/{self.session_id}/players/{guild_id}?noReplace=false"

                async with self.session.patch(url=rebuild_uri, json=rebuild_payload, headers=self._websocket.headers) as rebuild_resp:
                    if rebuild_resp.status == 200:
                        __log__.info(
                            f"NODE | {self.identifier} | Player recreated successfully for guild {guild_id} on attempt {attempt}."
                        )
                        return await rebuild_resp.json()

                    try:
                        rebuild_data = await rebuild_resp.json()
                    except Exception:
                        rebuild_data = await rebuild_resp.text()

                    last_error = f"{rebuild_resp.status} | {rebuild_data}"

                    if rebuild_resp.status not in (404, 409):
                        __log__.error(
                            f"NODE | {self.identifier} | Recreate player failed for guild {guild_id}: {last_error}"
                        )
                        return

                    __log__.warning(
                        f"NODE | {self.identifier} | Recreate player retry {attempt} for guild {guild_id}: {last_error}"
                    )

            __log__.error(
                f"NODE | {self.identifier} | Exhausted recreate retries for guild {guild_id}. Last error: {last_error}"
            )
        finally:
            player._nodelink_recreating = False

    def _require_v4(self):
        if self.version < 4:
            raise WavelinkException(f"{self.identifier}: This endpoint requires a v4-compatible server.")

    def _require_session(self):
        self._require_v4()
        if not self.session_id:
            raise MissingSessionID(self)

    def _player_uri(self, guild_id: int, suffix: str = "") -> str:
        self._require_session()
        base = f"{self.rest_uri}/v4/sessions/{self.session_id}/players/{guild_id}"
        if suffix:
            if not suffix.startswith("/"):
                suffix = f"/{suffix}"
            base += suffix
        return base

    @staticmethod
    def _track_to_encoded(track: Union[Track, str, dict]) -> str:
        if isinstance(track, Track):
            return track.id
        if isinstance(track, str):
            return track
        if isinstance(track, dict):
            encoded = track.get("encoded") or track.get("track")
            if encoded:
                return encoded
        raise TypeError("track must be a Track, encoded track string or payload dict containing 'encoded'.")

    @staticmethod
    def _track_to_payload(track: Union[Track, str, dict], *, user_data: Any = None,
                          audio_track_id: str = None, include_plugin_info: bool = True) -> dict:
        if isinstance(track, Track):
            payload = {"encoded": track.id}
            if include_plugin_info:
                plugin_info = track.info.get("pluginInfo", {})
                if plugin_info:
                    payload["pluginInfo"] = plugin_info
        elif isinstance(track, str):
            payload = {"encoded": track}
        elif isinstance(track, dict):
            payload = dict(track)
        else:
            raise TypeError("track must be a Track, encoded track string or payload dict.")

        if user_data is not None:
            payload["userData"] = user_data

        if audio_track_id is not None:
            payload["audioTrackId"] = audio_track_id

        return payload

    async def _json_request(self, method: str, url: str, *, json_data: dict = None, params: dict = None,
                            expected_status: tuple = (200,), allow_empty: bool = False):
        async with self.session.request(method, url, json=json_data, params=params, headers=self.headers) as resp:
            if resp.status in expected_status:
                if allow_empty or resp.status == 204:
                    return None
                try:
                    return await resp.json()
                except Exception:
                    return await resp.text()

            try:
                resp_data = await resp.json()
            except Exception:
                resp_data = await resp.text()

            raise WavelinkException(
                f"{self.identifier}: {method.upper()} {url} failed = {resp.status}: {resp_data}"
            )

    async def get_tracks(self, query: str, *, retry_on_failure: bool = False, **kwargs) -> Union[list, TrackPlaylist, None]:
        """|coro|

        Search for and return a list of Tracks for the given query.

        Parameters
        ------------
        query: str
            The query to use to search for tracks. If a valid URL is not provided, it's best to default to
            "ytsearch:query", which allows the REST server to search YouTube for Tracks.
        retry_on_failure: bool
            Bool indicating whether the Node should retry upto a maximum of 5 attempts on load failure.
            If this is set to True, the Node will attempt to retrieve tracks with an exponential backoff delay
            between retries. Defaults to True.

        Returns
        ---------
        Union[list, TrackPlaylist, None]:
            A list of or TrackPlaylist instance of :class:`wavelink.player.Track` objects.
            This could be None if no tracks were found.
        """
        backoff = ExponentialBackoff(base=1)

        ytid = None
        playlist_id = None

        if yt_id:=(yt_playlist_regex.search(query)):
            yt_id = yt_id.group(1)
            playlist_id = yt_id
            if yt_id.startswith("RD"):
                cache_key = None
            else:
                cache_key = f"youtube:{yt_id}"
            try:
                ytid = yt_video_regex.search(query).group(1)
            except:
                pass

        elif sp_match:=spotify_regex.match(query):
            url_type, url_id = sp_match.groups()
            cache_key = f"spotify:{url_type}:{url_id}"

        elif dz_match:=deezer_regex.match(query):
            url_type, url_id = dz_match.groups()[-2:]
            cache_key = f"deezer:{url_type}:{url_id}"

        elif sc_match:=soundcloud_regex.match(query):
            user_name, playlist_id = sc_match.groups()
            cache_key = f"soundcloud:{user_name}:{playlist_id}"

        else:
            cache_key = None

        if not (data:=self._client.bot.pool.playlist_cache.get(cache_key)):

            base_uri = f'{self.rest_uri}/v4' if self.version == 4 else self.rest_uri

            for attempt in range(2):

                async with self.session.get(f"{base_uri}/loadtracks?identifier={quote(query)}", headers={'Authorization': self.password}) as resp:

                    if resp.status != 200:

                        if not retry_on_failure:
                            __log__.info(f'REST | {self.identifier} | Status code ({resp.status}) while retrieving tracks. Not retrying.')
                            return

                        retry = backoff.delay()

                        __log__.info(f'REST | {self.identifier} | Status code ({resp.status}) while retrieving tracks. '
                                     f'Attempt {attempt} of 5, retrying in {retry} seconds.')

                        await asyncio.sleep(retry)
                        continue

                    try:
                        data = await resp.json()
                    except Exception as e:
                        raise WavelinkException(f"{self.identifier}: Failed to parse json result. | Error: {repr(e)}")

                    if isinstance(data, list):
                        return data

                    break

        loadtype = data.get('loadType')

        try:
            new_data = data.get('data')
        except KeyError:
            new_data = data

        if not loadtype:
            raise WavelinkException('There was an error while trying to load this track.')

        if loadtype == 'NO_MATCHES':
            __log__.info(f'REST | {self.identifier} | No tracks with query:: <{query}> found.')
            return []

        if loadtype in ('LOAD_FAILED', 'error'):

            if self.version == 4:
                if isinstance(new_data, dict):
                    if 'exception' not in new_data:
                        new_data['exception'] = new_data
                else:
                    new_data = data if isinstance(data, dict) else {}

            exception_data = {}

            if isinstance(new_data, dict):
                exception_data = new_data.get('exception') or new_data

            if not isinstance(exception_data, dict):
                exception_data = {}

            severity = exception_data.get('severity', 'unknown')
            message = exception_data.get('message') or exception_data.get('error') or repr(data)
            error = f"There was an error of severity '{severity}' while loading tracks.\n\n{message}"
            e = TrackLoadError(error=error, node=self, data=new_data)

            if not e.message:
                e.message = exception_data.get('error') or exception_data.get('message') or message

            if ytid:

                if e.message.endswith("The playlist does not exist."):
                    return await self.get_tracks(query=f"https://www.youtube.com/watch?v={ytid}",
                                                 retry_on_failure=retry_on_failure, **kwargs)

                if e.message.endswith("This video cannot be loaded.") and playlist_id:
                    return await self.get_tracks(query=f"https://www.youtube.com/watch?v={ytid}",
                                                 retry_on_failure=retry_on_failure, **kwargs)

            raise e

        try:
            tracks = new_data.get('tracks')
        except AttributeError:
            tracks = new_data

        if loadtype == 'track' and new_data:
            tracks = [new_data]

        if not tracks:
            __log__.info(f'REST | {self.identifier} | No tracks with query:: <{query}> found.')
            raise TrackNotFound(f"{self.identifier}: Track not found... | {query}")

        encoded_name = "track" if self.version == 3 else "encoded"

        if loadtype in ('PLAYLIST_LOADED', 'playlist'):

            try:
                new_data['playlistInfo'] = new_data.pop('info')
            except KeyError:
                pass

            playlist_cls = kwargs.pop('playlist_cls', TrackPlaylist)

            if cache_key:

                if not ytid:
                    self._client.bot.pool.playlist_cache[cache_key] = data

                else:

                    index = None

                    for n, t in enumerate(new_data['tracks']):
                        if t['info']['identifier'] == ytid:
                            index = n

                    if index is None:
                        try:
                            del self._client.bot.pool.playlist_cache[cache_key]
                        except KeyError:
                            pass
                        return await self.get_tracks(query=f"https://www.youtube.com/playlist?list={playlist_id}", retry_on_failure=retry_on_failure, playlist_cls=playlist_cls, **kwargs)

                    self._client.bot.pool.playlist_cache[cache_key] = data

                    if index > 0:
                        new_data['tracks'] = new_data['tracks'][index:] + new_data['tracks'][:index]

            if query.startswith("https://music.youtube.com/"):
                query = query.replace("https://www.youtube.com/", "https://music.youtube.com/")

                try:
                    if new_data["playlistInfo"]["name"].startswith("Album - "):
                        new_data["playlistInfo"]["name"] = new_data["playlistInfo"]["name"][8:]
                        new_data["pluginInfo"]["type"] = "album"
                        new_data["pluginInfo"]["albumName"] = new_data["playlistInfo"]["name"]
                        new_data["pluginInfo"]["albumUrl"] = query
                except KeyError:
                    pass
            return playlist_cls(data=new_data, url=query, encoded_name=encoded_name, pluginInfo=new_data.pop("pluginInfo", {}),
                                **kwargs)

        track_cls = kwargs.pop('track_cls', Track)

        if (check_title:=kwargs.get("check_title")) and len(tracks) > 1:

            tracks_ = [
                track_cls(
                    id_=track[encoded_name], info=track['info'],
                    pluginInfo=track.get("pluginInfo", {}), **kwargs
                ) for track in tracks
            ]

            search = "".join(query.split(":", 1)[1]).strip().lower()

            if tracks_[0].info['sourceName'] in ("youtube", "soundcloud"):

                def chk(t):
                    if t.author.endswith(" - topic") and not t.author.endswith(
                            "Release - topic") and not t.title.startswith(t.author[:-8]):
                        return f"{t.author} - {t.title}".lower()
                    else:
                        return t.title.lower()

                tracks_ = [t for t in tracks_ if fuzz.token_sort_ratio(chk(t), search) >= check_title]

            else:
                tracks_ = [t for t in tracks_ if fuzz.token_sort_ratio(f"{t.author} - {t.title}".lower(), search) >= check_title]

            if not any(tag for tag in exclude_tags if tag in search.lower()):
                return [t for t in tracks_ if not any(tag for tag in exclude_tags if tag in t.title.lower())]

            return tracks_

        return [
            track_cls(id_=track[encoded_name], info=track['info'], pluginInfo=track.get("pluginInfo", {}), **kwargs) for
            track in tracks]

        __log__.warning(f'REST | {self.identifier} | Failure to load tracks after 5 attempts.')

    async def build_track(self, identifier: str) -> Track:
        """|coro|

        Build a track object with a valid track identifier.

        Parameters
        ------------
        identifier: str
            The tracks unique Base64 encoded identifier. This is usually retrieved from various lavalink events.

        Returns
        ---------
        :class:`wavelink.player.Track`
            The track built from a Base64 identifier.

        Raises
        --------
        BuildTrackError
            Decoding and building the track failed.
        """
        async with self.session.get(f'{self.rest_uri}/decodetrack?',
                                    headers={'Authorization': self.password},
                                    params={'track': identifier}) as resp:
            data = await resp.json()

            if not resp.status == 200:
                raise BuildTrackError(f'Failed to build track. Status: {data["status"]}, Error: {data["error"]}.'
                                      f'Check the identifier is correct and try again.')

            track = Track(id_=identifier, info=data)
            return track

    @property
    def lyric_support(self):

        if self.version < 4:
            return

        try:
            return bool(self.info["plugins"]["lyrics"])
        except:
            pass

        try:
            return bool(self.info["plugins"]["java-lyrics-plugin"])
        except:
            pass

        return False

    async def fetch_ytm_lyrics(self, ytid: str):

        if not self.lyric_support:
            raise Exception(f"Lyrics plugin not available on Node: {self.identifier}")

        async with self.session.get(f"{self.rest_uri}/v4/lyrics/{ytid}", headers=self.headers) as r:
            if r.status not in (200, 404):
                r.raise_for_status()
            return await r.json()

    async def update_session(self, *, resuming: bool = None, timeout: int = None):
        self._require_session()
        payload = {}
        if resuming is not None:
            payload["resuming"] = resuming
        if timeout is not None:
            payload["timeout"] = int(timeout)
        if not payload:
            return None
        return await self._json_request(
            "PATCH",
            f"{self.rest_uri}/v4/sessions/{self.session_id}",
            json_data=payload
        )

    async def load_lyrics(self, track: Union[Track, str, dict], *, language: str = None):
        encoded = self._track_to_encoded(track)
        params = {"encodedTrack": encoded}
        if language:
            params["lang"] = language
        return await self._json_request("GET", f"{self.rest_uri}/v4/loadlyrics", params=params)

    async def load_chapters(self, track: Union[Track, str, dict]):
        encoded = self._track_to_encoded(track)
        return await self._json_request(
            "GET",
            f"{self.rest_uri}/v4/loadchapters",
            params={"encodedTrack": encoded}
        )

    async def load_meaning(self, track: Union[Track, str, dict], *, language: str = None):
        encoded = self._track_to_encoded(track)
        params = {"encodedTrack": encoded}
        if language:
            params["lang"] = language
        return await self._json_request("GET", f"{self.rest_uri}/v4/meaning", params=params)

    async def track_stream(self, track: Union[Track, str, dict], *, itag: int = None):
        encoded = self._track_to_encoded(track)
        params = {"encodedTrack": encoded}
        if itag is not None:
            params["itag"] = int(itag)
        return await self._json_request("GET", f"{self.rest_uri}/v4/trackstream", params=params)

    async def load_stream(self, track: Union[Track, str, dict], *, volume: int = 100, position: int = 0,
                          filters: dict = None) -> bytes:
        encoded = self._track_to_encoded(track)
        payload = {
            "encodedTrack": encoded,
            "volume": int(volume),
            "position": int(position),
        }
        if filters is not None:
            payload["filters"] = filters

        async with self.session.post(f"{self.rest_uri}/v4/loadstream", json=payload, headers=self.headers) as resp:
            if resp.status == 200:
                return await resp.read()

            try:
                resp_data = await resp.json()
            except Exception:
                resp_data = await resp.text()

            raise WavelinkException(
                f"{self.identifier}: POST {self.rest_uri}/v4/loadstream failed = {resp.status}: {resp_data}"
            )

    async def subscribe_lyrics(self, guild_id: int, *, skip_track_source: bool = False):
        skip_track_source_qs = "true" if skip_track_source else "false"
        return await self._json_request(
            "POST",
            f"{self._player_uri(guild_id, 'lyrics/subscribe')}?skipTrackSource={skip_track_source_qs}",
            expected_status=(204,),
            allow_empty=True
        )

    async def unsubscribe_lyrics(self, guild_id: int):
        return await self._json_request(
            "DELETE",
            self._player_uri(guild_id, "lyrics/subscribe"),
            expected_status=(204,),
            allow_empty=True
        )

    async def add_mix(self, guild_id: int, track: Union[Track, str, dict], *, volume: float = None,
                      user_data: Any = None, audio_track_id: str = None):
        payload = {"track": self._track_to_payload(track, user_data=user_data, audio_track_id=audio_track_id,
                                                   include_plugin_info=False)}
        if volume is not None:
            payload["volume"] = float(volume)
        return await self._json_request(
            "POST",
            self._player_uri(guild_id, "mix"),
            json_data=payload,
            expected_status=(201,)
        )

    async def get_mixes(self, guild_id: int):
        return await self._json_request("GET", self._player_uri(guild_id, "mix"))

    async def update_mix(self, guild_id: int, mix_id: str, *, volume: float):
        return await self._json_request(
            "PATCH",
            self._player_uri(guild_id, f"mix/{quote(str(mix_id), safe='')}"),
            json_data={"volume": float(volume)},
            expected_status=(204,),
            allow_empty=True
        )

    async def remove_mix(self, guild_id: int, mix_id: str):
        return await self._json_request(
            "DELETE",
            self._player_uri(guild_id, f"mix/{quote(str(mix_id), safe='')}"),
            expected_status=(204,),
            allow_empty=True
        )

    def get_player(self, guild_id: int) -> Optional[Player]:
        """Retrieve a player object associated with the Node.

        Parameters
        ------------
        guild_id: int
            The guild id belonging to the player.

        Returns
        ---------
        Optional[Player]
        """
        return self.players.get(guild_id, None)

    async def on_event(self, event) -> None:
        """Function which dispatches events when triggered on the Node."""
        __log__.info(f'NODE | Event dispatched:: <{str(event)}> ({self.__repr__()})')
        await event.player.hook(event)

        if not self.hook:
            return

        if inspect.iscoroutinefunction(self.hook):
            await self.hook(event)
        else:
            self.hook(event)

    def set_hook(self, func) -> None:
        """Set the Node Event Hook.

        The event hook will be dispatched when an Event occurs.
        Maybe a coroutine.

        Raises
        --------
        WavelinkException
            The hook provided was not a valid callable.
        """
        if not callable(func):
            raise WavelinkException('Node hook must be a callable.')

        self.hook = func

    async def destroy(self, *, force: bool = False) -> None:
        """Destroy the node and all it's players."""
        self._closing = True
        players = self.players.copy()

        for player in players.values():
            await player.destroy(force=force)

        try:
            self._websocket._task.cancel()
        except Exception:
            pass

        del self._client.nodes[self.identifier]

    async def _send(self, **data) -> None:
        __log__.debug(f'NODE | Sending payload:: <{data}> ({self.__repr__()})')
        await self._websocket._send(**data)
