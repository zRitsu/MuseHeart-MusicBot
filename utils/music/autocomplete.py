from __future__ import annotations
import disnake
from utils.client import BotCore
from utils.db import DBModel
from utils.music.checks import check_pool_bots
from utils.music.converters import google_search, percentage, time_format


async def search_suggestions(inter, query: str):
    if not query:
        return []

    if not inter.author.voice:
        return []

    return await google_search(inter.bot, query)


def queue_tracks(inter, query: str):
    if not inter.author.voice:
        return

    check_pool_bots(inter, check_player=True)

    try:
        bot = inter.music_bot
    except AttributeError:
        bot = inter.bot

    try:
        player = bot.music.players[inter.guild.id]
    except KeyError:
        return

    return [f"{track.title}"[:100] for n, track in enumerate(player.queue) if query.lower() in track.title.lower()][:20]


def queue_playlist(inter, query: str):
    if not inter.author.voice:
        return

    check_pool_bots(inter, check_player=True)

    try:
        bot = inter.music_bot
    except AttributeError:
        return

    try:
        player = bot.music.players[inter.guild.id]
    except KeyError:
        return

    return list(set([track.playlist_name for track in player.queue if track.playlist_name and
                     query.lower() in track.playlist_name.lower()]))[:20]


async def fav_list(inter, query: str, *, prefix=""):
    return sorted([f"{prefix}{favname}" for favname in
                   (await inter.bot.get_global_data(inter.author.id, db_name=DBModel.users))["fav_links"]
                   if not query or query.lower() in favname.lower()][:20])


async def pin_list(inter, query: str, *, prefix=""):
    return sorted([f"{prefix}{pinname}" for pinname in
                   (await inter.bot.get_data(inter.guild.id, db_name=DBModel.guilds))["player_controller"]["fav_links"]
                   if not query or query.lower() in pinname.lower()][:20])


async def fav_add_autocomplete(inter, query: str):
    favs: list = await fav_list(inter, query, prefix="> fav: ")

    if not inter.author.voice or not query or (favs_size := len(favs)) >= 20:
        return favs[:20]

    return await google_search(inter.bot, query, max_entries=20 - favs_size) + favs


def queue_author(inter, query):
    if not query:
        return

    if not inter.author.voice:
        return

    check_pool_bots(inter, check_player=True)

    try:
        bot = inter.music_bot
    except AttributeError:
        return

    player = bot.music.players[inter.guild.id]

    return list(set([track.author for track in player.queue if query.lower() in track.author.lower()]))[:20]


def seek_suggestions(inter, query):
    if query:
        return

    check_pool_bots(inter, check_player=True)

    try:
        bot = inter.music_bot
    except:
        return

    player = bot.music.players[inter.guild.id]

    if not player.current or player.current.is_stream:
        return

    seeks = []

    if player.current.duration >= 90000:
        times = [int(n * 0.5 * 10) for n in range(20)]
    else:
        times = [int(n * 1 * 10) for n in range(20)]

    for p in times:
        percent = percentage(p, player.current.duration)
        seeks.append(f"{time_format(percent)} | {p}%")

    return seeks


def queue_track_index(inter: disnake.AppCmdInter, bot: BotCore, query: str, check_all: bool = False):

    player = bot.music.players[inter.guild.id]

    query_split = query.lower().split()

    tracklist = []

    for counter, track in enumerate(player.queue):

        track_title = track.title.lower().split()

        q_found = 0

        for q in query_split:
            for t in track_title:
                if q in t:
                    q_found += 1
                    track_title.remove(t)
                    break

        if q_found == len(query_split):

            tracklist.append((counter, track,))
            if not check_all:
                break

    return tracklist
