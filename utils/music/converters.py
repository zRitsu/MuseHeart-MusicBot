# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime
import json
import re
import traceback
from typing import Union, TYPE_CHECKING

import disnake

if TYPE_CHECKING:
    pass

URL_REG = re.compile('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
YOUTUBE_VIDEO_REG = re.compile(r"(https?://)?(www\.|music\.)?youtube\.(com|nl)/watch\?v=([-\w]+)")

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


async def google_search(bot, query: str, *, max_entries: int = 20) -> list:

    try:
        async with bot.session.get(
                "https://suggestqueries.google.com/complete/search",
                headers={'User-Agent': bot.pool.current_useragent} if bot.pool.current_useragent else None,
                params={
                    'client': 'youtube',
                    'q': query,
                    'ds': 'yt',
                    'hl': 'en'
                }
        ) as r:

            text = await r.text()
            json_text = text[text.find("(") + 1:text.rfind(")")]
            return [result[0] for result in json.loads(json_text)[1][:max_entries]]
    except:
        traceback.print_exc()
        return []


def get_button_style(enabled: bool, red=True):
    if enabled:
        if red:
            return disnake.ButtonStyle.red
        return disnake.ButtonStyle.green
    return disnake.ButtonStyle.grey


def fix_characters(text: str, limit: int = 0):
    for r in replaces:
        old, new = r
        text = text.replace(old, new)

    if limit:
        text = f"{text[:limit]}..." if len(text) > limit else text

    return text


def time_format(milliseconds: Union[int, float], use_names: bool = False) -> str:
    minutes, seconds = divmod(int(milliseconds / 1000), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    if use_names:

        times = []

        for time_, name in (
                (days, "Gün"),
                (hours, "Saat"),
                (minutes, "Dakika"),
                (seconds, "Saniye")
        ):
            if not time_:
                continue

            times.append(f"{time_} {name}" + ("s" if time_ > 1 else ""))

        try:
            last_time = times.pop()
        except IndexError:
            last_time = None
            times = ["1 Saniye"]

        strings = ", ".join(t for t in times)

        if last_time:
            strings += f" e {last_time}" if strings else last_time

    else:

        strings = f"{minutes:02d}:{seconds:02d}"

        if hours:
            strings = f"{hours}:{strings}"

        if days:
            strings = (f"{days} Günler" if days > 1 else f"{days} Gün") + (f", {strings}" if strings != "00:00" else "")

    return strings


time_names = ["seconds", "minutes", "hours"]


def string_to_seconds(time):
    try:

        times = reversed([i for i in time.replace(" ", ":").split(':') if i.isdigit()])
        time_dict = {}

        for n, t in enumerate(times):
            time_dict[time_names[n]] = int(t)

        return datetime.timedelta(**time_dict).total_seconds()

    except:
        return


def percentage(part, whole):
    return int((part * whole) / 100.0)

sources = {
    "deezer": "https://i.ibb.co/Wz7kJYy/deezer.png",
    "soundcloud": "https://i.ibb.co/CV6NB6w/soundcloud.png",
    "spotify": "https://i.ibb.co/3SWMXj8/spotify.png",
    "youtube": "https://i.ibb.co/LvX7dQL/yt.png",
    "applemusic": "https://i.ibb.co/Dr4hbS5/applemusic.png",
    "twitch": "https://cdn3.iconfinder.com/data/icons/popular-services-brands-vol-2/512/twitch-512.png",
    "jiosaavn": "https://i.ibb.co/Bfh8dW2/jiosaavn.png",
    "tidal": "https://i.ibb.co/JkBbrXh/tidal.png",
    "youtubemusic": "https://i.ibb.co/WtCC2pg/Youtube-music-icon.png",
}

def music_source_image(sourcename):
    return sources.get(
        sourcename,
        "https://cdn.discordapp.com/attachments/480195401543188483/895862881105616947/music_equalizer.gif"
    )


perms_translations = {
    "add_reactions": "Tepkiler ekleyin",
    "administrator": "Yönetici",
    "attach_files": "Dosya ekleme",
    "ban_members": "Yasaklı Üyeler",
    "change_nickname": "Soyadınızı değiştirin",
    "connect": "Bir ses kanalına bağlanın",
    "create_instant_invite": "Anında davetiye oluşturun",
    "create_private_threads": "Özel Konular Oluşturun",
    "create_public_threads": "Genel Konular Oluşturun",
    "deafen_members": "Sağır edici uzuvlar",
    "embed_links": "Bağlantıları ekle",
    "kick_members": "Üyelerin İhraç Edilmesi",
    "manage_channels": "Kanalları Yönet",
    "manage_emojis_and_stickers": "Emojileri ve Çıkartmaları Yönetme",
    "manage_events": "Etkinlikleri Yönet",
    "manage_guild": "Sunucu Yönetme",
    "manage_messages": "Mesajları Yönet",
    "manage_nicknames": "Takma adları yönetme",
    "manage_roles": "İşlerin yönetilmesi",
    "manage_threads": "Konuları Yönet",
    "manage_webhooks": "Web Kancalarını Yönetme",
    "mention_everyone": "@everyone ve @here işaretle",
    "moderate_members": "Ilımlı üyeler",
    "move_members": "Üyeleri taşıyın",
    "mute_members": "Üyelerin susturulması",
    "priority_speaker": "Konuşmaya öncelik verme",
    "read_message_history": "Mesaj geçmişini göster",
    "read_messages": "Mesajları okuyun",
    "request_to_speak": "Konuşmak isteyin",
    "send_messages": "Bir mesaj gönderin",
    "send_messages_in_threads": "Konu başlıklarında mesaj gönderme",
    "send_tts_messages": "Metinden sese mesaj gönderme",
    "speak": "Bir ses kanalında konuşma",
    "stream": "İletim",
    "use_application_commands": "Uygulama/bot komutlarını kullanma",
    "use_embedded_activities": "Faaliyetleri kullanın ",
    "use_external_emojis": "Harici Emojileri Kullanın",
    "use_external_stickers": "Harici çıkartmalar kullanın",
    "use_voice_activation": "Otomatik ses algılamayı kullanın",
    "view_audit_log": "Denetim günlüğünü görüntüle",
    "view_channel": "Kanalı izle",
    "view_guild_insights": "Sunucu analizlerini görüntüleyin"
}
