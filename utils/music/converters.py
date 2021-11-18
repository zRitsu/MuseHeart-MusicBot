import datetime
from fake_useragent import UserAgent
import disnake
import re
import json

URL_REG = re.compile(r'https?://(?:www\.)?.+')
YOUTUBE_VIDEO_REG = re.compile(r"(https?://)?(www\.)?youtube\.(com|nl)/watch\?v=([-\w]+)")
ua = UserAgent().random

async def search_suggestions(inter, query):

    if not query:
        return

    if not inter.author.voice:
        return [query]

    if not query or URL_REG.match(query):
        return [query]

    async with inter.bot.session.get(
            f"http://suggestqueries.google.com/complete/search?client=chrome&ds=yt&q={query}",
            headers={'User-Agent': ua}) as r:
        return json.loads(await r.text())[1][:20]


def queue_tracks(inter, query):

    if not inter.author.voice:
        return

    try:
        inter.player
    except:
        inter.player = inter.bot.music.players.get(inter.guild.id)

    if not inter.player:
        return

    return [track.title for track in inter.player.queue if query.lower() in track.title.lower()][:20]


def queue_playlist(inter, query):

    if not inter.author.voice:
        return

    try:
        inter.player
    except:
        inter.player = inter.bot.music.players.get(inter.guild.id)

    if not inter.player:
        return

    return list(set([track.playlist['name'] for track in inter.player.queue if track.playlist and
                               query.lower() in track.playlist['name'].lower()]))[:20]


def queue_author(inter, query):

    if not query:
        return

    if not inter.author.voice:
        return

    try:
        inter.player
    except:
        inter.player = inter.bot.music.players.get(inter.guild.id)

    if not inter.player:
        return

    return list(set([track.author for track in inter.player.queue if query.lower() in track.author.lower()]))[:20]


def seek_suggestions(inter, query):

    if query:
        return

    try:
        inter.player
    except:
        inter.player = inter.bot.music.players.get(inter.guild.id)

    if not inter.player or not inter.player.current:
        return

    if inter.player.current.is_stream:
        return

    seeks = []

    if inter.player.current.duration >= 90000:
        times = [int(n * 0.5 * 10) for n in range(20)]
    else:
        times = [int(n * 1 * 10) for n in range(20)]

    for p in times:
        percent = percentage(p, inter.player.current.duration)
        seeks.append(f"{time_format(percent)} | {p}%")

    return seeks


def get_button_style(enabled: bool, red=True):
    if enabled:
        if red:
            return disnake.ButtonStyle.red
        return disnake.ButtonStyle.green
    return disnake.ButtonStyle.grey


def fix_characters(text: str, limit: int = 0):
    replaces = [
        ('&quot;', '"'),
        ('&amp;', '&'),
        ('(', '\u0028'),
        (')', '\u0029'),
        ('[', '【'),
        (']', '】'),
        ("  ", " "),
        ("*", '"'),
        ("_", ' '),
        ("{", "\u0028"),
        ("}", "\u0029"),
        ("`", "'")
    ]
    for r in replaces:
        text = text.replace(r[0], r[1])

    if limit:
        text = f"{text[:limit]}..." if len(text) > limit else text

    return text


def time_format(milliseconds):
    m, s = divmod(int(milliseconds / 1000), 60)
    h, m = divmod(m, 60)

    strings = f"{m:02d}:{s:02d}"

    if h:
        strings = f"{h}:{strings}"

    return strings


time_names = ["seconds", "minutes", "hours"]

def string_to_seconds(time):
    try:

        times = reversed(time.split(':'))
        time_dict = {}

        for n, t in enumerate(times):
            time_dict[time_names[n]] = int(t)

        return datetime.timedelta(**time_dict).total_seconds()

    except:
        return


def percentage(part, whole):
  return int((part * whole) / 100.0)


def get_track_index(ctx: disnake.ApplicationCommandInteraction, query: str):
    index = None

    player = ctx.player

    for counter, track in enumerate(player.queue):

        if query.lower() == track.title.lower():
        #if query.lower() in track.title.lower() or \
        #        all(elem in track.title.lower().split() for elem in query.lower().split()):
            index = counter
            break

    return index