import hashlib
import os
import pickle
import time

from aiohttp import ClientSession
from cachetools import TTLCache

cache_file = "./.lastfm_cache"

class LastFmException(Exception):
    def __init__(self, data: dict):
        self.code = data["error"]
        self.message = data["message"]
        
class LastFM:
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.cache: TTLCache = self.scrobble_load_cache()

    def scrobble_load_cache(self):

        cache = TTLCache(maxsize=10000, ttl=600)

        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                try:
                    cache.update(pickle.load(f))
                except EOFError:
                    pass

        return cache

    def scrobble_save_cache(self):
        with open(cache_file, 'wb') as f:
            pickle.dump(self.cache, f)

    def generate_api_sig(self, params: dict):
        sig = ''.join(f"{key}{params[key]}" for key in sorted(params))
        sig += self.api_secret
        return hashlib.md5(sig.encode('utf-8')).hexdigest()
    
    async def request_lastfm(self, params: dict):
        params["format"] = "json"
        async with ClientSession() as session:
            async with session.get("http://ws.audioscrobbler.com/2.0/", params=params) as response:
                if (data:=await response.json()).get('error'):
                    raise LastFmException(data)
                return data
    
    async def post_lastfm(self, params: dict):
        params["format"] = "json"
        async with ClientSession() as session:
            async with session.post("http://ws.audioscrobbler.com/2.0/", params=params) as response:
                if (data:=await response.json()).get('error'):
                    raise LastFmException(data)
                return data
    
    async def get_token(self):
        data = await self.request_lastfm(
            params={
                'method': 'auth.getToken',
                'api_key': self.api_key,
                'format': 'json',
            }
        )
        return data['token']
    
    async def get_session_key(self, token: str):
        params = {
            'method': 'auth.getSession',
            'api_key': self.api_key,
            'token': token,
        }
        params['api_sig'] = self.generate_api_sig(params)
        return await self.request_lastfm(params=params)
    
    async def track_scrobble(self, artist: str, track: str, album: str, duration: int, session_key: str, chosen_by_user: bool = True):

        params = {
            "method": "track.scrobble",
            "artist[0]": artist,
            "timestamp[0]": str(int(time.time() - 30)),
            "track[0]": track,
            "api_key": self.api_key,
            "sk": session_key,
        }

        if chosen_by_user is False:
            params["chosenByUser[0]"] = "0"

        if album:
            params["album"] = album

        if duration:
            params["duration"] = str(duration)

        params['api_sig'] = self.generate_api_sig(params)

        return await self.post_lastfm(params)
    
    async def update_nowplaying(self, artist: str, track: str, album: str, duration: int, session_key: str):
    
        params = {
            "method": "track.updateNowPlaying",
            "artist": artist,
            "track": track,
            "timestamp": str(int(time.time() - 30)),
            "api_key": self.api_key,
            "sk": session_key,
        }
    
        if album:
            params["album"] = album
        if duration:
            params["duration"] = str(duration)
    
        params['api_sig'] = self.generate_api_sig(params)
    
        return await self.post_lastfm(params)

    async def search_track(self, track: str, artist: str = None, limit: int = 30):
        params = {
            'method': 'track.search',
            'track': track,
            'api_key': self.api_key,
            'limit': limit
        }
        if artist:
            params['artist'] = artist
        return (await self.request_lastfm(params))['results']['trackmatches']['track']
    
    async def track_love(self, track: str, artist: str, session_key: str):
        params = {
            'method': 'track.love',
            'track': track,
            'artist': artist,
            'api_key': self.api_key,
            'sk': session_key,
        }
        params['api_sig'] = self.generate_api_sig(params)
        await self.post_lastfm(params)
    
    async def track_unlove(self, track: str, artist: str, session_key: str):
        params = {
            'method': 'track.unlove',
            'track': track,
            'artist': artist,
            'api_key': self.api_key,
            'sk': session_key,
        }
        params['api_sig'] = self.generate_api_sig(params)
        await self.post_lastfm(params)

    async def get_track_info(self, track: str, artist: str = None, mbid: str = None, username: str = None):
        params = {
            'method': 'track.getInfo',
            'api_key': self.api_key,
            'autocorrect': 1,
        }
        if mbid:
            params['mbid'] = mbid
        else:
            params['track'] = track
            if artist:
                params['artist'] = artist

        if username:
            params["username"] = username

        return (await self.request_lastfm(params))
    
    async def get_similar_tracks(self, track: str, artist: str = None, mbid: str = None):
        params = {
            'method': 'track.getSimilar',
            'api_key': self.api_key,
            'autocorrect': 1,
        }
        if mbid:
            params['mbid'] = mbid
        else:
            params['track'] = track
            if artist:
                params['artist'] = artist
    
        return (await self.request_lastfm(params))['similartracks']['track']

    async def get_artist_toptracks(self, artist: str, limit=20):
        return (await self.request_lastfm(
            {
                'method': 'artist.gettoptracks',
                'api_key': self.api_key,
                'artist': artist,
                'limit': limit,
            }
        ))['toptracks']['track']

    async def get_similar_artists(self, artist: str, mbid: str = None):
        params = {
            'method': 'artist.getSimilar',
            'api_key': self.api_key,
            'autocorrect': 1,
        }
        if mbid:
            params['mbid'] = mbid
        else:
            params['artist'] = artist
    
        return (await self.request_lastfm(params))['similarartists']['artist']
    
    async def user_info(self, session_key: str):
        return (await self.request_lastfm(
            params = {
                'method': 'user.getInfo',
                'api_key': self.api_key,
                'sk': session_key,
            }))['user']
    
    async def user_recent_tracks(self, user: str, limit: int = 50):
        return (await self.request_lastfm(
            params = {
                'method': 'user.getRecentTracks',
                'user': user,
                'limit': limit,
                'api_key': self.api_key,
            }))['recenttracks']

    async def user_top_tracks(self, user: str, limit: int = 50):
        return (await self.request_lastfm(
            params = {
                'method': 'user.getTopTracks',
                'user': user,
                'limit': limit,
                'api_key': self.api_key,
            }))['toptracks']['track']

    async def user_top_artists(self, user: str, limit: int = 50):
        return (await self.request_lastfm(
            params = {
                'method': 'user.getTopArtists',
                'user': user,
                'limit': limit,
                'api_key': self.api_key,
            }))['topartists']['artist']

    async def user_top_albums(self, user: str, limit: int = 50):
        return (await self.request_lastfm(
            params = {
                'method': 'user.getTopAlbums',
                'user': user,
                'limit': limit,
                'api_key': self.api_key,
            }))['topalbums']['album']

    async def user_top_tags(self, user: str):
        return (await self.request_lastfm(
            params = {
                'method': 'user.getTopTags',
                'user': user,
                'api_key': self.api_key,
            }))['toptags']['tag']
