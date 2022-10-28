from __future__ import annotations
import re
from .converters import fix_characters
from .errors import MissingSpotifyClient, GenericError
from asyncspotify import Client, ClientCredentialsFlow
from typing import Optional, TYPE_CHECKING

from .models import PartialPlaylist, PartialTrack

if TYPE_CHECKING:
    from utils.client import BotCore

spotify_regex = re.compile("https://open.spotify.com?.+(album|playlist|artist|track)/([a-zA-Z0-9]+)")


def query_spotify_track(func, url_id: str):
    return func(url_id)


async def process_spotify(bot: BotCore, requester: int, query: str, *, hide_playlist=False):

    if not (matches := spotify_regex.match(query)):
        return

    if not bot.spotify:
        raise MissingSpotifyClient()

    url_type, url_id = matches.groups()

    if url_type == "track":
        result = await bot.spotify.get_track(url_id)

        t = PartialTrack(
            uri=result.link,
            author=result.artists[0].name,
            title=result.name,
            thumb=result.album.images[1].url,
            duration=result.duration.total_seconds() * 1000,
            source_name="spotify",
            requester=requester
        )

        t.info["extra"]["authors"] = [fix_characters(i.name) for i in result.artists]

        t.info["extra"]["authors_md"] = ", ".join(f"[`{a.name}`]({a.link})" for a in result.artists)

        try:
            if result.album.name != result.name:
                t.info["extra"]["album"] = {
                    "name": result.album.name,
                    "url": result.album.uri
                }
        except (AttributeError, KeyError):
            pass

        return [t]

    data = {
        'loadType': 'PLAYLIST_LOADED',
        'playlistInfo': {'name': '', 'url': query},
        'sourceName': "spotify",
        'tracks': []
    }

    if url_type == "album":

        result = await bot.spotify.get_album(url_id)

        if len(result.tracks) < 2:
            track = result.tracks[0]

            return [PartialTrack(
                uri=track.link,
                author=track.artists[0].name,
                title=track.name,
                thumb=result.images[1].url,
                duration=track.duration.total_seconds() * 1000,
                requester=requester
            )]

        data["playlistInfo"]["name"] = result.name

        for t in result.tracks:
            t.album = result

        tracks = result.tracks

    elif url_type == "artist":

        result = await bot.spotify.get_artist_top_tracks(url_id)

        data["playlistInfo"]["name"] = "As mais tocadas de: " + \
                                       [a["name"] for a in result[0].artists if a.id == url_id][0]
        tracks = result

    elif url_type == "playlist":

        result = await bot.spotify.get_playlist(url_id)

        if hide_playlist:
            data["playlistInfo"].clear()
        else:
            data["playlistInfo"]["name"] = result.name

        tracks = result.tracks

    else:
        raise GenericError(f"**Link do spotify não reconhecido/suportado:**\n{query}")

    if not tracks:
        raise GenericError(f"**Não houve resultados no link do spotify informado...**")

    for t in tracks:

        track = PartialTrack(
            uri=t.link,
            author=t.artists[0].name,
            title=t.name,
            thumb=t.album.images[1].url,
            duration=t.duration.total_seconds() * 1000,
            source_name="spotify",
            requester=requester
        )

        try:
            track.info["extra"]["album"] = {
                "name": t.album.name,
                "url": t.album.uri
            }
        except (AttributeError, KeyError):
            pass

        track.info["extra"]["playlist"] = data["playlistInfo"]

        track.info["extra"]["authors"] = [fix_characters(i.name) for i in t.artists]

        track.info["extra"]["authors_md"] = ", ".join(f"[`{a.name}`]({a.link})" for a in t.artists)

        data["tracks"].append(track)

    data["playlistInfo"]["selectedTrack"] = -1

    return PartialPlaylist(data)


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
