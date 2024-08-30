# -*- coding: utf-8 -*-
import itertools
from os.path import basename

import disnake

from utils.music.converters import fix_characters, time_format, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class ClassicStaticSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3] + "_static"
        self.preview = "https://media.discordapp.net/attachments/554468640942981147/1047187412343853146/classic_static_skin.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = True
        player.auto_update = 0
        player.hint_rate = player.bot.config["HINT_RATE"]
        player.static = True

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        embed = disnake.Embed(color=player.bot.get_color(player.guild.me), description="")

        queue_txt = ""

        embed.description = f"[**{player.current.title}**]({player.current.uri or player.current.search_uri})\n\n"
        embed.set_image(url=player.current.thumb)
        embed_top = None

        if not player.paused:
            (embed_top or embed).set_author(
                name="Tocando Agora:",
                icon_url=music_source_image(player.current.info["sourceName"])
            )
        else:
            (embed_top or embed).set_author(
                name="Em Pausa:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        if player.current.is_stream:
            duration = "🔴 **⠂Livestream**"
        else:
            duration = f"⏰ **⠂Duração:** `{time_format(player.current.duration)}`"

        txt = f"{duration}\n" \
              f"💠 **⠂Uploader:** `{player.current.author}`\n"

        if not player.current.autoplay:
            f"🎧 **⠂Pedido por:** <@{player.current.requester}>\n"
        else:
            try:
                mode = f" [`Recomendação`]({player.current.info['extra']['related']['uri']})"
            except:
                mode = "`Recomendação`"
            txt += f"👍 **⠂Adicionado via:** {mode}\n"

        if player.current.playlist_name:
            txt += f"📑 **⠂Playlist:** [`{fix_characters(player.current.playlist_name, limit=20)}`]({player.current.playlist_url})\n"

        if qsize := len(player.queue):

            data["content"] = "**Músicas na fila:**\n```ansi\n" + \
                              "\n".join(f"[0;33m{(n+1):02}[0m [0;34m[{time_format(t.duration) if not t.is_stream else '🔴 stream'}][0m [0;36m{fix_characters(t.title, 45)}[0m" for n, t in enumerate(
                                  itertools.islice(player.queue, 15)))

            if qsize > 15:
                data["content"] += f"\n\n[0;37mE mais[0m [0;35m{qsize}[0m [0;37mmúsicas{'s'[:qsize^1]}.[0m"

            data["content"] += "```"

        elif len(player.queue_autoplay):

            data["content"] = "**Próximas músicas recomendadas:**\n```ansi\n" + \
                              "\n".join(f"[0;33m{(n+1):02}[0m [0;34m[{time_format(t.duration) if not t.is_stream else '🔴 stream'}][0m [0;36m{fix_characters(t.title, 45)}[0m" for n, t in enumerate(
                                  itertools.islice(player.queue_autoplay, 15))) + "```"

        if player.command_log:
            txt += f"{player.command_log_emoji} **⠂Última Interação:** {player.command_log}\n"

        embed.description += txt + queue_txt

        if player.current_hint:
            embed.set_footer(text=f"💡 Dica: {player.current_hint}")
        else:
            embed.set_footer(
                text=str(player),
                icon_url="https://i.ibb.co/QXtk5VB/neon-circle.gif"
            )

        data["embeds"] = [embed_top, embed] if embed_top else [embed]

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

        if (queue:=player.queue or player.queue_autoplay):
            data["components"].append(
                disnake.ui.Select(
                    placeholder="Próximas músicas:",
                    custom_id="musicplayer_queue_dropdown",
                    min_values=0, max_values=1,
                    options=[
                        disnake.SelectOption(
                            label=f"{n+1}. {fix_characters(t.author, 18)}",
                            description=fix_characters(t.title, 47),
                            value=f"{n:02d}.{t.title[:96]}"
                        ) for n, t in enumerate(itertools.islice(queue, 25))
                    ]
                )
            )

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
    return ClassicStaticSkin()
