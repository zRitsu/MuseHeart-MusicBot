# -*- coding: utf-8 -*-
import datetime
import re
from os.path import basename

import disnake

from utils.music.converters import time_format, fix_characters, get_button_style
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class EmbedLinkSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://media.discordapp.net/attachments/554468640942981147/1101330475164893244/Discord_N1QhBDXtar.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = True
        player.auto_update = 0
        player.hint_rate = player.bot.config["HINT_RATE"]
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        txt = ""

        if player.current_hint:
            txt += f"> -# `💡` **⠂Dica:** `{player.current_hint}`"

        if player.current.is_stream:
            duration_txt = f"\n> -# `🔴` **⠂Duração:** `Livestream`"
        else:
            duration_txt = f"\n> -# `⏰` **⠂Duração:** `{time_format(player.current.duration)}`"

        title = f"`{fix_characters(player.current.title)}`" if not player.current.uri else f"[`{fix_characters(player.current.title, 40)}`]({player.current.uri})"

        if player.paused:
            txt += f"\n> -# ⏸️ **⠂Em Pausa:** {title}{duration_txt}"

        else:
            txt += f"\n> -# ▶️ **⠂Tocando Agora:** {title}{duration_txt}"
            if not player.current.is_stream:
                txt += f" `[`<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>`]`" \
                if not player.paused else ''

        if q:=len(player.queue):
            txt += f" `[Na fila: {q}]`"

        if not player.current.autoplay:
            txt += f" <@{player.current.requester}>\n"
        else:
            try:
                txt += f" [`[Música Recomendada]`](<{player.current.info['extra']['related']['uri']}>)"
            except:
                txt += " `[Música Recomendada]`"

        if player.command_log:

            log = re.sub(r"\[(.+)]\(.+\)", r"\1", player.command_log.replace("`", "")) # remover links do command_log p/ evitar gerar mais de uma preview.

            txt += f"> -# {player.command_log_emoji} **⠂Última Interação:** {log}\n"

        data["content"] = txt

        data["components"] = [
            disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
            disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
            disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
            disnake.ui.Button(emoji="<:music_queue:703761160679194734>", custom_id=PlayerControls.queue, disabled=not (player.queue or player.queue_autoplay)),
            disnake.ui.Select(
                placeholder="Mais opções:",
                custom_id="musicplayer_dropdown_inter",
                min_values=0, max_values=1,
                options=[
                    disnake.SelectOption(
                        label="Adicionar música", emoji="<:add_music:588172015760965654>",
                        value=PlayerControls.add_song,
                        description="Adicionar uma música/playlist na fila."
                    ),
                    disnake.SelectOption(
                        label="Adicionar favorito na fila", emoji="⭐",
                        value=PlayerControls.enqueue_fav,
                        description="Adicionar um de seus favoritos na fila."
                    ),
                    disnake.SelectOption(
                        label="Adicionar nos seus favoritos", emoji="💗",
                        value=PlayerControls.add_favorite,
                        description="Adicionar a música atual nos seus favoritos."
                    ),
                    disnake.SelectOption(
                        label="Tocar do inicio", emoji="⏪",
                        value=PlayerControls.seek_to_start,
                        description="Voltar o tempo da música atual para o inicio."
                    ),
                    disnake.SelectOption(
                        label=f"Volume: {player.volume}%", emoji="🔊",
                        value=PlayerControls.volume,
                        description="Ajustar volume."
                    ),
                    disnake.SelectOption(
                        label="Misturar", emoji="🔀",
                        value=PlayerControls.shuffle,
                        description="Misturar as músicas da fila."
                    ),
                    disnake.SelectOption(
                        label="Readicionar", emoji="🎶",
                        value=PlayerControls.readd,
                        description="Readicionar as músicas tocadas de volta na fila."
                    ),
                    disnake.SelectOption(
                        label="Repetição", emoji="🔁",
                        value=PlayerControls.loop_mode,
                        description="Ativar/Desativar repetição da música/fila."
                    ),
                    disnake.SelectOption(
                        label=("Desativar" if player.nightcore else "Ativar") + " o efeito nightcore", emoji="🇳",
                        value=PlayerControls.nightcore,
                        description="Efeito que aumenta velocidade e tom da música."
                    ),
                    disnake.SelectOption(
                        label=("Desativar" if player.autoplay else "Ativar") + " a reprodução automática", emoji="🔄",
                        value=PlayerControls.autoplay,
                        description="Sistema de adição de música automática quando a fila estiver vazia."
                    ),
                    disnake.SelectOption(
                        label="Last.fm scrobble", emoji="<:Lastfm:1278883704097341541>",
                        value=PlayerControls.lastfm_scrobble,
                        description="Ativar/desativar o scrobble/registro de músicas na sua conta do last.fm."
                    ),
                    disnake.SelectOption(
                        label= ("Desativar" if player.restrict_mode else "Ativar") + " o modo restrito", emoji="🔐",
                        value=PlayerControls.restrict_mode,
                        description="Apenas DJ's/Staff's podem usar comandos restritos."
                    ),
                ]
            ),
        ]

        if player.current.ytid and player.node.lyric_support:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label= "Visualizar letras", emoji="📃",
                    value=PlayerControls.lyrics,
                    description="Obter letra da música atual."
                )
            )


        if isinstance(player.last_channel, disnake.VoiceChannel):
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Status automático", emoji="📢",
                    value=PlayerControls.set_voice_status,
                    description="Configurar o status automático do canal de voz."
                )
            )

        if not player.static and not player.has_thread:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Song-Request Thread", emoji="💬",
                    value=PlayerControls.song_request_thread,
                    description="Criar uma thread/conversa temporária para pedir músicas usando apenas o nome/link."
                )
            )

        return data

def load():
    return EmbedLinkSkin()