# -*- coding: utf-8 -*-
from os.path import basename

import disnake

from utils.music.converters import fix_characters, time_format
from utils.music.models import LavalinkPlayer


class LiteSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://i.ibb.co/h2r9Y5p/lite.png"

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

        embed = disnake.Embed(color=player.bot.get_color(player.guild.me))

        duration = "`🔴 Livestream`" if player.current.is_stream else \
            time_format(player.current.duration)

        embed.description = f"> -# ▶️ **┃**[`{fix_characters(player.current.title, 45)}`]({player.current.uri or player.current.search_uri})\n" \
                            f"> -# ℹ️ **┃**`{duration}`┃`{fix_characters(player.current.author, 18)}`┃"

        if not player.current.autoplay:
            embed.description += f"<@{player.current.requester}>"
        else:
            try:
                embed.description = f"[`[Recomendada]`]({player.current.info['extra']['related']['uri']})"
            except:
                embed.description = "`[Recomendada]`"

        if player.current.playlist_name:
            embed.description += f"\n> -# 🎼 **┃ Playlist:** [`{player.current.playlist_name}`]({player.current.playlist_url})"

        embed.set_thumbnail(player.current.thumb)

        data["embeds"].append(embed)

        if player.current_hint:
            data["embeds"].append(disnake.Embed(color=player.bot.get_color(player.guild.me)).set_footer(text=f"💡 Dica: {player.current_hint}"))

        return data

def load():
    return LiteSkin()
