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

    def __init__(self, *, uri, title, authors, thumb, duration, requester, playlist = None, album=None, track_loops=0):
        self.author = fix_characters(authors[0].name)
        self.authors = [fix_characters(i.name) for i in authors]
        self.authors_md = ", ".join(f"[`{a.name}`]({a.link})" for a in authors)
        self.authors_string = ", ".join(a.name for a in authors)
        self.id = ""
        self.single_title = fix_characters(title)
        self.title = f"{self.author} - {self.single_title}"
        self.thumb = thumb
        self.uri = uri
        self.duration = duration
        self.is_stream = False
        self.info = {}
        self.requester = requester
        self.playlist = playlist or {}
        self.album = {"name": album.name, "url": album.link} if album else {}
        self.track_loops = track_loops

    async def resolve(self, node: Node):

        if self.id:
            return

        try:
            track = (await node.get_tracks(f"ytsearch:{self.title}"))
            try:
                track = track[0]
            except:
                track = track.tracks[0]
            track.info["sourceName"] = "spotify"
            self.info = track.info
            self.id = track.id
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
            album=result.album,
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

        data["playlistInfo"]["name"] = "As mais tocadas de: " + [a["name"] for a in result[0].artists if a.id == url_id][0]
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
    try:
        return Client(
            ClientCredentialsFlow(
                client_id=config['SPOTIFY_CLIENT_ID'],
                client_secret=config["SPOTIFY_CLIENT_SECRET"]
            )
        )

    except Exception as e:
        print(
            f"A APIKEY do spotify não foi configurada devidamente nas variáveis da host (ou no arquivo .env), "
            f"verifique e tente novamente caso queira o suporte a músicas do spotify (Erro: {repr(e)}).\n{'-'*30}")
        return