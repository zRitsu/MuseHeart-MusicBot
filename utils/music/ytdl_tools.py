# -*- coding: utf-8 -*-
import asyncio
import re

import disnake
import yt_dlp

from utils.music.errors import GenericError
from utils.music.models import PartialTrack

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
                'dash',
                'translated_subs'
            ],
            'player_skip': [
                'js',
                'configs',
                'webpage'
            ],
            'player_client': ['android_creator'],
            'max_comments': [0],
        },
        'youtubetab': {
            "skip": ["webpage"]
        }
    }
}

class YTDLTools:

    extractors = [
        {
            "name": type(e).__name__.lower(),
            "ie_key": e.ie_key(),
            "regex": e._VALID_URL,
            "age_limit": e.age_limit
        } for e in yt_dlp.list_extractors() if e._VALID_URL
    ]

    def extract_info(self, url: str):

        with yt_dlp.YoutubeDL(YTDL_OPTS) as ytdl:
            return ytdl.extract_info(url=url, download=False)

    async def get_track_info(self, url: str, user: disnake.Member = None, loop = None):

        for e in self.extractors:

            if not (matches := re.compile(e['regex']).match(url)) or not matches.groups():
                continue

            if any(ee in e["name"] for ee in exclude_extractors):
                continue

            if e["age_limit"] > 17 and e["ie_key"] != "Twitter":
                raise GenericError("**Este link contém conteúdo para maiores de 18 anos!**")

            if not loop:
                loop = asyncio.get_event_loop()

            data = await loop.run_in_executor(None, self.extract_info, url)

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

if __name__ == "__main__":

    ydl = YTDLTools()
    url = "https://www.youtube.com/channel/UC9AiU8Srqw7iPu3UcR9IJ8g"
    for e in ydl.extractors:

        if e['ie_key'] == "Generic":
            continue

        a = re.compile(e['regex']).match(url)
        if a:
            print(e['ie_key'], e['name'])
