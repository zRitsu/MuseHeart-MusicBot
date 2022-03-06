from __future__ import annotations
import disnake
import re
from .converters import fix_characters
from wavelink import Node
import traceback
from .errors import MissingSpotifyClient
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from utils.client import BotCore


spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|artist|track)/([a-zA-Z0-9]+)")

def process_album_info(track: dict):
    try:
        return {
            "name": track['album']["name"],
            "url": track['album']['external_urls']['spotify']
        }
    except KeyError:
        return {}

def fix_spotify_data(data: dict):
    try:
        data = data["track"]
    except KeyError:
        data = {"track": data}
        return data


class SpotifyPlaylist:

    def __init__(self, data: dict, requester: disnake.Member, *, playlist):
        self.data = data

        self.tracks = []

        for i in data['tracks']:

            try:
                track = i['track']
            except KeyError:
                track = i

            self.tracks.append(
                SpotifyTrack(
                    uri=track['external_urls']['spotify'],
                    authors=track["artists"],
                    title=track['name'],
                    thumb=track['album']['images'][0]['url'],
                    duration=track['duration_ms'],
                    requester=requester,
                    playlist=playlist,
                    album=process_album_info(track)
                )
            )


class SpotifyTrack:

    def __init__(self, *, uri, title, authors, thumb, duration, requester, playlist = None, album=None, track_loops=0):
        self.author = fix_characters(authors[0]['name'])
        self.authors = [fix_characters(i['name']) for i in authors]
        self.id = ""
        self.title = f"{fix_characters(title)}"
        self.thumb = thumb
        self.uri = uri
        self.duration = duration
        self.is_stream = False
        self.info = {}
        self.requester = requester
        self.playlist = playlist or {}
        self.album = album or {}
        self.track_loops = track_loops

        self.title += ' - ' + ', '.join(a for a in self.authors if not a in self.title)

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


async def process_spotify(bot: BotCore, requester: disnake.Member, query: str, *, hide_playlist=False):
    if not (matches := spotify_regex.match(query)):
        return

    if not bot.spotify:
        raise MissingSpotifyClient()

    url_type, url_id = matches.groups()

    if url_type == "track":
        t = bot.spotify.track(url_id)

        album = process_album_info(t)

        return [SpotifyTrack(
            uri=t['external_urls']['spotify'],
            authors=t["artists"],
            title=t['name'],
            thumb=t['album']['images'][0]['url'],
            duration=t['duration_ms'],
            album=album,
            requester=requester
        )]

    data = {
        'loadType': 'PLAYLIST_LOADED',
        'playlistInfo': {'name': '', 'selectedTrack': -1},
        'tracks': []
    }

    if url_type == "album":
        result = bot.spotify.album(url_id)
        data["playlistInfo"]["name"] = result['name']
        for t in result['tracks']['items']:
            t['album'] = {'images': [{'url': result['images'][0]['url']}]}
        data["tracks"] = [fix_spotify_data(i) for i in result['tracks']['items']]

    else:

        if url_type == "artist":
            result = bot.spotify.artist_top_tracks(url_id)
            data["playlistInfo"]["name"] = "As mais tocadas de: " + [a["name"] for a in result["tracks"][0]["artists"] if a["id"] == url_id][0]
            data["tracks"] = result["tracks"]
            result["name"] = data["playlistInfo"]["name"]

        else: # playlist
            result = bot.spotify.playlist(playlist_id=url_id)
            data["playlistInfo"]["name"] = result['name']
            data["tracks"] = result['tracks']['items']

    playlist = {"name": result['name'], "url": query} if not hide_playlist else {}

    if data["tracks"]:
        return SpotifyPlaylist(data, requester=requester, playlist=playlist)


def spotify_client(config: dict) -> Optional[spotipy.Spotify]:
    try:
        return spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=config['SPOTIFY_CLIENT_ID'],
                client_secret=config["SPOTIFY_CLIENT_SECRET"]
            )
        )
    except Exception as e:
        print(
            f"A APIKEY do spotify não foi configurada devidamente nas variáveis da host (ou no arquivo .env), "
            f"verifique e tente novamente caso queira o suporte a músicas do spotify (Erro: {repr(e)}).\n{'-'*30}")
        return