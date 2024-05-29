import hashlib
import pprint
import time

from aiohttp import ClientSession


class LastFmException(Exception):
    def __init__(self, data: dict):
        self.code = data["error"]
        self.message = data["message"]


def generate_api_sig(params, api_secret):
    sig = ''.join(f"{key}{params[key]}" for key in sorted(params))
    sig += api_secret
    return hashlib.md5(sig.encode('utf-8')).hexdigest()


async def request_lastfm(params):
    params["format"] = "json"
    async with ClientSession() as session:
        async with session.get("http://ws.audioscrobbler.com/2.0/", params=params) as response:
            if (data:=await response.json()).get('error'):
                raise LastFmException(data)
            return data


async def post_lastfm(params):
    params["format"] = "json"
    async with ClientSession() as session:
        async with session.post("http://ws.audioscrobbler.com/2.0/", params=params) as response:
            if (data:=await response.json()).get('error'):
                raise LastFmException(data)
            return data


async def lastfm_get_token(apikey: str):
    data = await request_lastfm(
        params={
            'method': 'auth.getToken',
            'api_key': apikey,
            'format': 'json',
        }
    )
    return data['token']


async def lastfm_get_session_key(api_key: str, api_secret: str, token: str):
    params = {
        'method': 'auth.getSession',
        'api_key': api_key,
        'token': token,
    }
    params['api_sig'] = generate_api_sig(params, api_secret=api_secret)
    return await request_lastfm(params=params)


async def lastfm_track_scrobble(artist: str, track: str, album: str, duration: int, session_key: str, api_key: str,
                                api_secret: str):
    params = {
        "method": "track.scrobble",
        "artist[0]": artist,
        "timestamp[0]": str(int(time.time() - 30)),
        "track[0]": track,
        "api_key": api_key,
        "sk": session_key,
    }
    if album:
        params["album"] = album
    if duration:
        params["duration"] = str(duration)

    params['api_sig'] = generate_api_sig(params, api_secret)

    return await post_lastfm(params)


async def lastfm_update_nowplaying(artist: str, track: str, album: str, duration: int, session_key: str, api_key: str,
                                   api_secret: str):

    params = {
        "method": "track.updateNowPlaying",
        "artist": artist,
        "track": track,
        "timestamp": str(int(time.time() - 30)),
        "api_key": api_key,
        "sk": session_key,
    }

    if album:
        params["album"] = album
    if duration:
        params["duration"] = str(duration)

    params['api_sig'] = generate_api_sig(params, api_secret)

    return await post_lastfm(params)


async def lastfm_track_love(track: str, artist: str, session_key: str, api_key: str, api_secret: str):
    params = {
        'method': 'track.love',
        'track': track,
        'artist': artist,
        'api_key': api_key,
        'sk': session_key,
    }
    params['api_sig'] = generate_api_sig(params, api_secret)
    await post_lastfm(params)


async def lastfm_track_unlove(track: str, artist: str, session_key: str, api_key: str, api_secret: str):
    params = {
        'method': 'track.unlove',
        'track': track,
        'artist': artist,
        'api_key': api_key,
        'sk': session_key,
    }
    params['api_sig'] = generate_api_sig(params, api_secret)
    await post_lastfm(params)


async def lastfm_get_similar_track(track: str, artist: str, session_key: str, api_key: str, mbid: str = None):
    params = {
        'method': 'track.getSimilar',
        'api_key': api_key,
        'autocorrect[0|1]': True,
        'sk': session_key,
    }
    params.update({'mbid': mbid}) if mbid else {'track': track, 'artist': artist}
    return (await request_lastfm(params))['lfm']['similartracks']


async def lastfm_user_info(session_key: str, api_key: str):
    return (await request_lastfm(
        params = {
            'method': 'user.getInfo',
            'api_key': api_key,
            'sk': session_key,
        }))['user']

