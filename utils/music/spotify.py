import disnake
from disnake.ext import commands
import re
import os
from .converters import fix_characters
from wavelink import Node
import traceback
from .errors import MissingSpotifyClient
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Optional


spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|track)/([a-zA-Z0-9]+)")


def fix_spotify_data(data: dict):
    try:
        return data["track"]
    except KeyError:
        data = {"track": data}
        return data


class SpotifyPlaylist:

    def __init__(self, data: dict, requester: disnake.Member, *, playlist):
        self.data = data

        self.tracks = [
            SpotifyTrack(
                uri=i['track']['external_urls']['spotify'],
                authors=i['track']["artists"],
                title=i['track']['name'],
                thumb=i['track']['album']['images'][0]['url'],
                duration=i['track']['duration_ms'],
                requester=requester,
                playlist=playlist
            ) for i in data['tracks'] if i.get('track')]


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
            self.info = track.info
            self.id = track.id
        except IndexError:
            return
        except Exception:
            traceback.print_exc()


async def process_spotify(bot: commands.bot, requester: disnake.Member, query: str):
    if not (matches := spotify_regex.match(query)):
        return

    if not bot.spotify:
        raise MissingSpotifyClient()

    url_type, url_id = matches.groups()

    if url_type == "track":
        t = bot.spotify.track(url_id)

        album = {
                "name": t['album']["name"],
                "url": t['album']['external_urls']['spotify'],
            }

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

    else: # playlist
        result = bot.spotify.playlist(playlist_id=url_id)
        data["playlistInfo"]["name"] = result['name']
        data["tracks"] = result['tracks']['items']

    playlist = {"name": result['name'], "url": query}

    if data["tracks"]:
        return SpotifyPlaylist(data, requester=requester, playlist=playlist)


def spotify_client() -> Optional[spotipy.Spotify]:
    try:
        return spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=os.environ['SPOTIFY_CLIENT_ID'],
                client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
            )
        )
    except Exception as e:
        print(
            f"A APIKEY do spotify não foi configurada devidamente nas variáveis da host (ou no arquivo .env), "
            f"verifique e tente novamente caso queira o suporte a músicas do spotify (Erro: {repr(e)}).\n{'-'*30}")
        return