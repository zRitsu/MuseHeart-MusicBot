from functools import partial
from yt_dlp import YoutubeDL

YDL_OPTIONS = {
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
        self.ytdl = YoutubeDL(YDL_OPTIONS)

    async def extract_info(self, url: str):

        to_run = partial(self.ytdl.extract_info, url=url, download=False)
        info = await self.bot.loop.run_in_executor(None, to_run)
        return info