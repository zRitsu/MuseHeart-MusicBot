from __future__ import annotations
import disnake
import re
from .converters import fix_characters
from wavelink import Node
import traceback
from .errors import MissingSpotifyClient, GenericError
from asyncspotify import Client, ClientCredentialsFlow
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.client import BotCore

spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|artist|track)/([a-zA-Z0-9]+)")


class SpotifyPlaylist:

    def __init__(self, data: dict, requester: disnake.Member, *, playlist):
        self.data = data

        self.tracks = [
            SpotifyTrack(
                uri=track.link,
                authors=track.artists,
                title=track.name,
                thumb=track.album.images[0].url,
                duration=track.duration.total_seconds() * 1000,
                requester=requester,
                playlist=playlist,
                album=track.album
            ) for track in data['tracks']
        ]


class SpotifyTrack:

    def __init__(self, *, uri, title, authors, thumb, duration,
                 requester, playlist=None, album=None, track_loops=0, info: dict = None):

        self.info = info or {
            "author": fix_characters(authors[0].name),
            "id": "",
            "title": title,
            "uri": uri,
            "length": duration,
            "isStream": False,
            "isSeekable": True,
            "sourceName": "spotify",
            "extra": {
                "authors": [fix_characters(i.name) for i in authors],
                "authors_md": ", ".join(f"[`{a.name}`]({a.link})" for a in authors),
                "authors_string": ", ".join(a.name for a in authors),
                "single_title": fix_characters(title),
                "thumb": thumb
            }
        }

        self.author = self.info["author"]
        self.authors = self.info["extra"]["authors"]
        self.authors_md = self.info["extra"]["authors_md"]
        self.authors_string = self.info["extra"]["authors_string"]
        self.id = self.info["id"]
        self.single_title = self.info["extra"]["single_title"]
        self.title = f"{self.author} - {self.single_title}"
        self.uri = self.info["uri"]
        self.duration = self.info["length"]
        self.is_stream = self.info["isStream"]
        self.requester = requester
        self.track_loops = track_loops
        self.thumb = self.info["extra"]["thumb"]

        if album:
            self.info["extra"]["album"] = {
                "name": album.name,
                "url": album.link
            }

        if playlist:
            self.info["extra"]["playlist"] = {
                "name": playlist["name"],
                "url": playlist["url"]
            }

    @property
    def album_name(self) -> str:
        try:
            return self.info["extra"]["album"]["name"]
        except KeyError:
            return ""

    @property
    def album_url(self) -> str:
        try:
            return self.info["extra"]["album"]["url"]
        except KeyError:
            return ""

    @property
    def playlist_name(self) -> str:
        try:
            return self.info["extra"]["playlist"]["name"]
        except KeyError:
            return ""

    @property
    def playlist_url(self) -> str:
        try:
            return self.info["extra"]["playlist"]["url"]
        except KeyError:
            return ""

    async def resolve(self, node: Node):

        if self.id:
            return

        try:
            tracks = (await node.get_tracks(f"ytsearch:{self.title}"))
            try:
                tracks = tracks.tracks
            except AttributeError:
                pass

            selected_track = None

            for t in tracks:

                if t.is_stream:
                    continue

                if (t.duration - 10000) < self.duration < (t.duration + 10000):
                    selected_track = t
                    break

            if not selected_track:
                selected_track = tracks[0]

            selected_track.info["sourceName"] = "spotify"
            self.id = selected_track.id

        except IndexError:
            return
        except Exception:
            traceback.print_exc()


def query_spotify_track(func, url_id: str):
    return func(url_id)


async def process_spotify(bot: BotCore, requester: disnake.Member, query: str, *, hide_playlist=False):
    if not (matches := spotify_regex.match(query)):
        return

    if not bot.spotify:
        raise MissingSpotifyClient()

    url_type, url_id = matches.groups()

    if url_type == "track":
        result = await bot.spotify.get_track(url_id)

        return [SpotifyTrack(
            uri=result.link,
            authors=result.artists,
            title=result.name,
            thumb=result.album.images[0].url,
            duration=result.duration.total_seconds() * 1000,
            album=result.album if result.album.name != result.name else None,
            requester=requester
        )]

    data = {
        'loadType': 'PLAYLIST_LOADED',
        'playlistInfo': {'name': '', 'selectedTrack': -1},
        'tracks': []
    }

    if url_type == "album":

        result = await bot.spotify.get_album(url_id)

        if len(result.tracks) < 2:
            track = result.tracks[0]

            return [SpotifyTrack(
                uri=track.link,
                authors=track.artists,
                title=track.name,
                thumb=result.images[0].url,
                duration=track.duration.total_seconds() * 1000,
                requester=requester
            )]

        data["playlistInfo"]["name"] = result.name

        for t in result.tracks:
            t.album = result

        data["tracks"] = result.tracks

    elif url_type == "artist":

        result = await bot.spotify.get_artist_top_tracks(url_id)

        data["playlistInfo"]["name"] = "As mais tocadas de: " + \
                                       [a["name"] for a in result[0].artists if a.id == url_id][0]
        data["tracks"] = result

    elif url_type == "playlist":

        result = await bot.spotify.get_playlist(url_id)

        data["playlistInfo"]["name"] = result.name
        data["tracks"] = result.tracks

    else:
        raise GenericError(f"**Link do spotify não reconhecido/suportado:**\n{query}")

    playlist = {"name": result.name, "url": query} if not hide_playlist else {}

    if data["tracks"]:
        return SpotifyPlaylist(data, requester=requester, playlist=playlist)


def spotify_client(config: dict) -> Optional[Client]:
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
        return Client(
            ClientCredentialsFlow(
                client_id=config['SPOTIFY_CLIENT_ID'],
                client_secret=config["SPOTIFY_CLIENT_SECRET"]
            )
        )

    except Exception as e:
        print(
            f"A APIKEY do spotify não foi configurada devidamente na ENV da host (ou no arquivo .env), "
            f"verifique e tente novamente caso queira o suporte a músicas do spotify (Erro: {repr(e)}).\n{'-' * 30}")
        return
