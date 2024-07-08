# -*- coding: utf-8 -*-
from os.path import basename

import disnake

from utils.music.converters import fix_characters, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class MicroController:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://i.ibb.co/R0SsBxq/micro-controller.png"

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
            description=f"-# [`{fix_characters(player.current.single_title, 32)}`]({player.current.uri or player.current.search_uri}) "
                        f"[`{fix_characters(player.current.author, 12)}`] "
        )

        if not player.current.autoplay:
            embed.description += f"<@{player.current.requester}>"
        else:
            try:
                embed.description += f"[`[Recomendada]`]({player.current.info['extra']['related']['uri']})"
            except:
                embed.description += "`[Recomendada]`"

        embed.set_author(
            name="Tocando Agora:",
            icon_url=music_source_image(player.current.info["sourceName"])
        )

        if player.command_log:
            embed.description += f"\n\n{player.command_log_emoji} ⠂**Última Interação:** {player.command_log}"

        if player.current_hint:
            embed_hint = disnake.Embed(colour=embed_color)
            embed_hint.set_footer(text=f"💡 Dica: {player.current_hint}")
            data["embeds"].append(embed_hint)

        data["embeds"].append(embed)

        data["components"] = [
            disnake.ui.Button(emoji="⏯️", label="Retomar" if player.paused else "Pausar", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(emoji="⏮️", label="Voltar", custom_id=PlayerControls.back),
            disnake.ui.Button(emoji="⏹️", label="Parar", custom_id=PlayerControls.stop, style=disnake.ButtonStyle.red),
            disnake.ui.Button(emoji="⏭️", label="Pular", custom_id=PlayerControls.skip),
            disnake.ui.Button(emoji="<:music_queue:703761160679194734>", label="Fila", custom_id=PlayerControls.queue,disabled=not (player.queue or player.queue_autoplay)),
            disnake.ui.Button(emoji="💗", label="Adicionar nos seus favoritos", custom_id=PlayerControls.add_favorite),
            disnake.ui.Button(emoji="⭐", label="Tocar favorito", custom_id=PlayerControls.enqueue_fav),
        ]

        return data

def load():
    return MicroController()
