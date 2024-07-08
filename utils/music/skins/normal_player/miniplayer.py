# -*- coding: utf-8 -*-
from os.path import basename

import disnake

from utils.music.converters import fix_characters, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class MiniPlayer:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://i.ibb.co/R6668sT/image.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = True
        player.auto_update = 0
        player.hint_rate = player.bot.config["HINT_RATE"]
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": [],
        }

        embed_color = player.bot.get_color(player.guild.me)

        embed = disnake.Embed(
            color=embed_color,
            description=f"-# [{fix_characters(player.current.single_title, 48)}]({player.current.uri or player.current.search_uri})\n"
                        f"-# **Uploader:** `{fix_characters(player.current.author, 17)}`\n"
        )

        if player.current.thumb:
            embed.set_thumbnail(url=player.current.thumb)

        if not player.current.autoplay:
            embed.description += f"-# **Pedido por:** <@{player.current.requester}>\n"
        else:
            try:
                embed.description += f"-# **Adicionado via:** [`[Recomendação]`]({player.current.info['extra']['related']['uri']})\n"
            except:
                embed.description += "-# **Adicionado via:** `[Recomendação]`\n"

        embed.set_author(
            name="Tocando Agora:",
            icon_url=music_source_image(player.current.info["sourceName"])
        )

        if player.command_log:
            embed.description += f"-# {player.command_log_emoji} ⠂**Última Interação:** {player.command_log}"

        if player.current_hint:
            embed_hint = disnake.Embed(colour=embed_color)
            embed_hint.set_footer(text=f"💡 Dica: {player.current_hint}")
            data["embeds"].append(embed_hint)

        data["embeds"].append(embed)

        data["components"] = [
            disnake.ui.Button(emoji="<:playpause:1000648043529519144>", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(emoji="<:backward:938437126532517928>", custom_id=PlayerControls.back),
            disnake.ui.Button(emoji="<:stop:923282526322184212>", custom_id=PlayerControls.stop, style=disnake.ButtonStyle.red),
            disnake.ui.Button(emoji="<:skip:955164528595857488>", custom_id=PlayerControls.skip),
            disnake.ui.Button(emoji="🤍", custom_id=PlayerControls.add_favorite),
        ]

        return data

def load():
    return MiniPlayer()
