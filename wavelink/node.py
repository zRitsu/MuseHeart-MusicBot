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
import re
import traceback
from typing import Any, Callable, Dict, Optional, Union, List
from urllib.parse import quote

from utils.music.youtube_trusted_session_generator import Browser
from .backoff import ExponentialBackoff
from .errors import *
from .player import Player, Track, TrackPlaylist
from .websocket import WebSocket

__log__ = logging.getLogger(__name__)

yt_playlist_regex = re.compile(r"[?&]list=([^&]+)")
spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|artist)/([a-zA-Z0-9]+)")
deezer_regex = re.compile(r"(https?://)?(www\.)?deezer\.com/(?P<countrycode>[a-zA-Z]{2}/)?(?P<type>album|playlist|artist|profile)/(?P<identifier>[0-9]+)")
soundcloud_regex = re.compile(r"https://soundcloud\.com/([^/]+)/sets/([^/]+)")


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
        self.info = {"sourceManagers": []}
        self.plugin_names: Optional[List] = None
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
            self.version = info["check_version"]
            self.info = info

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

        if self.version < 4:
            self.plugin_names = set()
        else:
            self.plugin_names = set([p["name"] for p in self.info["plugins"]])

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

        if not self.session_id:
            try:
                player = self._client.bot.music.players[guild_id]
                player._new_node_task = player.bot.loop.create_task(player._wait_for_new_node())
                return
            except:
                pass
            raise MissingSessionID(self)

        no_replace: bool = not replace

        uri: str = f"{self.rest_uri}/v4/sessions/{self.session_id}/players/{guild_id}?noReplace={no_replace}"

        retries = 3

        while retries > 0:

            async with self.session.patch(url=uri, json=data, headers=self._websocket.headers) as resp:

                try:
                    resp_data = await resp.json()
                except:
                    resp_data = await resp.text()

                if resp.status == 200:
                    return resp_data

                retries -= 1

                await asyncio.sleep(1.5)

        if new_node := self._client.get_best_node(ignore_node=self):
            await self.players[guild_id].change_node(new_node.identifier)
            return

        raise WavelinkException(f"{self.identifier}: UpdatePlayer Failed = {resp.status}: {resp_data}")

    async def get_tracks(self, query: str, *, retry_on_failure: bool = True, **kwargs) -> Union[list, TrackPlaylist, None]:
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

        if yt_id:=(yt_playlist_regex.search(query)):
            cache_key = f"youtube:{yt_id.group(1)}"

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

                    if resp.status != 200 and retry_on_failure:
                        retry = backoff.delay()

                        __log__.info(f'REST | {self.identifier} | Status code ({resp.status}) while retrieving tracks. '
                                     f'Attempt {attempt} of 5, retrying in {retry} seconds.')

                        await asyncio.sleep(retry)
                        continue

                    elif not resp.status == 200 and not retry_on_failure:
                        __log__.info(f'REST | {self.identifier} | Status code ({resp.status}) while retrieving tracks. Not retrying.')
                        return

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
                new_data['exception'] = new_data

            try:
                error = f"There was an error of severity '{new_data['exception']['severity']}' while loading tracks.\n\n{new_data['exception']['message']}"
            except KeyError:
                error = f"There was an error of severity '{new_data['exception']['severity']}:\n{new_data['exception']['error']}"
            e = TrackLoadError(error=error, node=self, data=new_data)
            if not e.message:
                e.message = new_data['exception']['error']
            raise e

        try:
            tracks = new_data.get('tracks')
        except AttributeError:
            tracks = new_data

        if loadtype == 'track':
            tracks = [new_data]

        if not tracks:
            __log__.info(f'REST | {self.identifier} | No tracks with query:: <{query}> found.')
            raise TrackNotFound(f"{self.identifier}: Track not found... | {query}")

        encoded_name = "track" if self.version == 3 else "encoded"

        if loadtype in ('PLAYLIST_LOADED', 'playlist'):

            if cache_key:
                self._client.bot.pool.playlist_cache[cache_key] = data

            try:
                new_data['playlistInfo'] = new_data.pop('info')
            except KeyError:
                pass

            playlist_cls = kwargs.pop('playlist_cls', TrackPlaylist)
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

        return "lyrics" in self.plugin_names

    async def fetch_ytm_lyrics(self, ytid: str):

        if not self.lyric_support:
            raise Exception(f"Lyrics plugin not available on Node: {self.identifier}")

        async with self.session.get(f"{self.rest_uri}/v4/lyrics/{ytid}", headers=self.headers) as r:
            if r.status not in (200, 404):
                r.raise_for_status()
            return await r.json()

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
