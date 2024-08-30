# -*- coding: utf-8 -*-
import datetime
import itertools
from os.path import basename

import disnake

from utils.music.converters import time_format, fix_characters, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class MiniStaticSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3] + "_static"
        self.preview = "https://i.ibb.co/F3NTnPc/mini-static-skin.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = True
        player.auto_update = 0
        player.hint_rate = player.bot.config["HINT_RATE"]
        player.static = True

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": [],
        }

        embed_color = player.bot.get_color(player.guild.me)

        embed = disnake.Embed(
            color=embed_color,
            description=f"-# [`{player.current.single_title}`]({player.current.uri or player.current.search_uri})"
        )
        embed_queue = None
        queue_size = len(player.queue)

        if not player.paused:
            embed.set_author(
                name="Tocando Agora:",
                icon_url=music_source_image(player.current.info["sourceName"]),
            )

        else:
            embed.set_author(
                name="Em Pausa:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        if player.current.track_loops:
            embed.description += f" `[🔂 {player.current.track_loops}]`"

        elif player.loop:
            if player.loop == 'current':
                embed.description += ' `[🔂 música atual]`'
            else:
                embed.description += ' `[🔁 fila]`'

        if not player.current.autoplay:
            embed.description += f" `[`<@{player.current.requester}>`]`"
        else:
            try:
                embed.description += f" [`[Recomendada]`]({player.current.info['extra']['related']['uri']})"
            except:
                embed.description += "` [Recomendada]`"

        duration = "🔴 Livestream" if player.current.is_stream else \
            time_format(player.current.duration)

        embed.add_field(name="⏰ **⠂Duração:**", value=f"```ansi\n[34;1m{duration}[0m\n```")
        embed.add_field(name="💠 **⠂Uploader/Artista:**",
                        value=f"```ansi\n[34;1m{fix_characters(player.current.author, 18)}[0m\n```")

        if player.command_log:
            embed.add_field(name=f"{player.command_log_emoji} **⠂Última Interação:**",
                            value=f"{player.command_log}", inline=False)

        embed.set_image(url=player.current.thumb or "https://media.discordapp.net/attachments/480195401543188483/987830071815471114/musicequalizer.gif")

        if queue_size:

            queue_txt = ""

            has_stream = False

            current_time = disnake.utils.utcnow() - datetime.timedelta(milliseconds=player.position) + datetime.timedelta(milliseconds=player.current.duration)

            queue_duration = 0

            for n, t in enumerate(player.queue):

                if t.is_stream:
                    has_stream = True

                elif n != 0:
                    queue_duration += t.duration

                if n > 7:
                    if has_stream:
                        break
                    continue

                if has_stream:
                    duration = time_format(t.duration) if not t.is_stream else '🔴 Ao vivo'

                    queue_txt += f"`┌ {n + 1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                                 f"`└ ⏲️ {duration}`" + (f" - `Repetições: {t.track_loops}`" if t.track_loops else "") + \
                                 f" **|** `✋` <@{t.requester}>\n"

                else:
                    duration = f"<t:{int((current_time + datetime.timedelta(milliseconds=queue_duration)).timestamp())}:R>"

                    queue_txt += f"-# `┌ {n + 1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                                 f"-# `└ ⏲️` {duration}" + (f" - `Repetições: {t.track_loops}`" if t.track_loops else "") + \
                                 f" **|** `✋` <@{t.requester}>\n"

            embed_queue = disnake.Embed(title=f"Músicas na fila: {queue_size}",
                                        color=player.bot.get_color(player.guild.me),
                                        description=f"\n{queue_txt}")

            if not has_stream and not player.loop and not player.keep_connected and not player.paused and not player.current.is_stream:
                embed_queue.description += f"\n-# `[ ⌛ As músicas acabam` <t:{int((current_time + datetime.timedelta(milliseconds=queue_duration + player.current.duration)).timestamp())}:R> `⌛ ]`"

        elif player.queue_autoplay:

            queue_txt = ""

            has_stream = False

            current_time = disnake.utils.utcnow() - datetime.timedelta(milliseconds=player.position) + datetime.timedelta(milliseconds=player.current.duration)

            queue_duration = 0

            for n, t in enumerate(player.queue_autoplay):

                if t.is_stream:
                    has_stream = True

                elif n != 0:
                    queue_duration += t.duration

                if n > 7:
                    if has_stream:
                        break
                    continue

                if has_stream:
                    duration = time_format(t.duration) if not t.is_stream else '🔴 Ao vivo'

                    queue_txt += f"`┌ {n + 1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                                 f"`└ ⏲️ {duration}`" + (f" - `Repetições: {t.track_loops}`" if t.track_loops else "") + \
                                 f" **|** `👍⠂Recomendada`\n"

                else:
                    duration = f"<t:{int((current_time + datetime.timedelta(milliseconds=queue_duration)).timestamp())}:R>"

                    queue_txt += f"-# `┌ {n + 1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                                 f"-# `└ ⏲️` {duration}" + (f" - `Repetições: {t.track_loops}`" if t.track_loops else "") + \
                                 f" **|** `👍⠂Recomendada`\n"

            embed_queue = disnake.Embed(title="Próximas músicas recomendadas:",
                                        color=player.bot.get_color(player.guild.me),
                                        description=f"\n{queue_txt}")

        if player.current_hint:
            embed.set_footer(text=f"💡 Dica: {player.current_hint}")

        data["embeds"] = [embed_queue, embed] if embed_queue else [embed]

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
                        label=("Desativar" if player.restrict_mode else "Ativar") + " o modo restrito", emoji="🔐",
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
    return MiniStaticSkin()
