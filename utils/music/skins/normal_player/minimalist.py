# -*- coding: utf-8 -*-
from os.path import basename

from utils.music.converters import fix_characters, time_format
from utils.music.models import LavalinkPlayer


class Minimalist:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://i.ibb.co/ynN9F4V/minimalist.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = False
        player.auto_update = 0
        player.hint_rate = 9
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        duration = "🔴 Livestream" if player.current.is_stream else \
            time_format(player.current.duration)

        data = {
            "embeds": [],
            "content": f"-# ▶️`⠂Tocando:` [`{fix_characters(player.current.title, 42)}`](<{player.current.uri or player.current.search_uri}>) `[{fix_characters(player.current.author, 20)}] {duration}`"
        }

        if player.current_hint:
            data["content"] += f"\n-# 💡`⠂Dica: {player.current_hint}`"

        return data

def load():
    return Minimalist()
