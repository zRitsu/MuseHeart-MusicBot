from yt_dlp import YoutubeDL

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

    async def get_track_info(self, url: str):
        return await self.bot.loop.run_in_executor(None, self.extract_info, url)
