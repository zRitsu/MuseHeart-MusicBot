# -*- coding: utf-8 -*-
from os.path import basename

import disnake

from utils.music.converters import fix_characters
from utils.music.models import LavalinkPlayer


class MicroNC:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://media.discordapp.net/attachments/554468640942981147/1050275579766784051/micro_nc.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = False
        player.auto_update = 0
        player.hint_rate = 9
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        embed = disnake.Embed(
            color=player.bot.get_color(player.guild.me),
            description=f"-# 🎶 **⠂[{fix_characters(player.current.title, 30)}]({player.current.uri or player.current.search_uri})** `[{fix_characters(player.current.author, 12)}]`"
        )

        data["embeds"].append(embed)

        if player.current_hint:
            data["embeds"].append(disnake.Embed(color=player.bot.get_color(player.guild.me)).set_footer(text=f"💡 Dica: {player.current_hint}"))

        return data

def load():
    return MicroNC()
