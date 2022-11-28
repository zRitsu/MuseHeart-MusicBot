import re
import disnake
from yt_dlp import YoutubeDL, list_extractors
from utils.music.errors import GenericError
from utils.music.models import PartialTrack

extractors = list_extractors()

exclude_extractors = ["youtube", "soundcloud", "deezer", "applemusic", "twitch"]

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'retries': 5,
    'extract_flat': "in_playlist",
    'cachedir': False,
    'extractor_args': {
        'youtube': {
            'skip': [
                'hls',
                'dash'
            ],
            'player_skip': [
                'js',
                'configs',
                'webpage'
            ]
        },
        'youtubetab': ['webpage']
    }
}

class YTDLTools:

    def __init__(self, bot):
        self.bot = bot

    def extract_info(self, url: str):

        with YoutubeDL(YTDL_OPTS) as ytdl:
            return ytdl.extract_info(url=url, download=False)

    async def get_track_info(self, url: str, user: disnake.Member):

        for e in extractors:

            if not e._VALID_URL:
                continue

            if not (matches := re.compile(e._VALID_URL).match(url)):
                continue

            if not matches.groups():
                continue

            if any(ee in type(e).__name__.lower() for ee in exclude_extractors):
                continue

            if e.age_limit > 17 and e.ie_key() != "Twitter":
                raise GenericError("**Este link contém conteúdo para maiores de 18 anos!**")

            data = await self.bot.loop.run_in_executor(None, self.extract_info, url)

            try:
                if data["_type"] == "playlist":
                    raise GenericError("**No momento não há suporte para playlists com o link fornecido...**")
            except KeyError:
                pass

            try:
                entrie = data["entries"][0]
            except KeyError:
                entrie = data

            try:
                if entrie["age_limit"] > 17:
                    raise GenericError("**Este link contém conteúdo para maiores de 18 anos!**")
            except KeyError:
                pass

            t = PartialTrack(
                uri=entrie.get("webpage_url") or url,
                title=entrie["title"],
                author=entrie["uploader"],
                thumb=entrie["thumbnail"],
                duration=entrie["duration"] * 1000,
                requester=user.id,
                source_name=entrie["extractor"],
            )

            t.info.update({
                "search_uri": entrie["url"],
                "authors": entrie["uploader"]
            })

            return [t]
