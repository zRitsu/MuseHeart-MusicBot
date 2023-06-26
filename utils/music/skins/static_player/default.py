# -*- coding: utf-8 -*-
import datetime
import itertools

import disnake

from utils.music.converters import fix_characters, time_format, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class DefaultStaticSkin:
    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = "default_static"
        self.preview = "https://cdn.discordapp.com/attachments/554468640942981147/1047187412666810448/default_static_skin.png"

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

        embed = disnake.Embed(color=player.bot.get_color(player.guild.me))
        embed_queue = None
        vc_txt = ""

        if not player.paused:
            emoji = "▶️"
            embed.set_author(
                name="Tocando Agora:",
                icon_url=music_source_image(player.current.info["sourceName"])
            )

        else:
            emoji = "⏸️"
            embed.set_author(
                name="Em Pausa:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        if player.current_hint:
            embed.set_footer(text=f"💡 Dica: {player.current_hint}")
        elif player.node.identifier != "LOCAL":
            embed.set_footer(
                text=str(player),
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/907119505971486810/speaker-loud-speaker.gif"
            )

        queue_img = ""

        try:
            vc_txt = f"\n> *️⃣ **⠂Canal de voz:** {player.guild.me.voice.channel.mention}"
        except AttributeError:
            pass

        duration = "> 🔴 **⠂Duração:** `Livestream`" if player.current.is_stream else \
            (f"> ⏰ **⠂Duração:** `{time_format(player.current.duration)} [`" +
            f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>`]`"
            if not player.paused else '')

        txt = f"[`{player.current.single_title}`]({player.current.uri or player.current.search_uri})\n\n" \
              f"{duration}\n" \
              f"> 💠 **⠂Por:** {player.current.authors_md}\n" \
              f"> ✋ **⠂Pedido por:** <@{player.current.requester}>\n" \
              f"> 🔊 **⠂Volume:** `{player.volume}%`"

        if player.current.track_loops:
            txt += f"\n> 🔂 **⠂Repetições restante:** `{player.current.track_loops}`"

        if player.loop:
            if player.loop == 'current':
                e = '🔂'; m = 'Música atual'
            else:
                e = '🔁'; m = 'Fila'
            txt += f"\n> {e} **⠂Modo de repetição:** `{m}`"

        if player.nightcore:
            txt += f"\n> 🇳 **⠂Efeito nightcore:** `ativado`"

        if player.current.album_name:
            txt += f"\n> 💽 **⠂Álbum:** [`{fix_characters(player.current.album_name, limit=20)}`]({player.current.album_url})"

        if player.current.playlist_name:
            txt += f"\n> 📑 **⠂Playlist:** [`{fix_characters(player.current.playlist_name, limit=20)}`]({player.current.playlist_url})"

        if player.keep_connected:
            txt += "\n> ♾️ **⠂Modo 24/7:** `Ativado`"

        elif player.restrict_mode:
            txt += f"\n> 🔒 **⠂Modo restrito:** `Ativado`"

        txt += f"{vc_txt}\n"

        if player.command_log:
            txt += f"```ansi\n [34;1mÚltima Interação[0m```**┕ {player.command_log_emoji} ⠂**{player.command_log}\n"

        if qlenght:=len(player.queue):

            queue_txt = "\n".join(
                f"`{(n + 1):02}) [{time_format(t.duration) if not t.is_stream else '🔴 Livestream'}]` [`{fix_characters(t.title, 33)}`]({t.uri})"
                for n, t in (enumerate(itertools.islice(player.queue, 20)))
            )

            embed_queue = disnake.Embed(title=f"Músicas na fila: {qlenght}", color=player.bot.get_color(player.guild.me),
                                        description=f"\n{queue_txt}")

            if not player.loop and not player.keep_connected and not player.paused and not player.current.is_stream:

                queue_duration = 0

                for t in player.queue:
                    if not t.is_stream:
                        queue_duration += t.duration

                embed_queue.description += f"\n`[⌛ As músicas acabam` <t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=(queue_duration + (player.current.duration if not player.current.is_stream else 0)) - player.position)).timestamp())}:R> `⌛]`"

            embed_queue.set_image(url=queue_img)

        embed.description = txt

        embed.set_image(url=player.current.thumb or "https://media.discordapp.net/attachments/480195401543188483/987830071815471114/musicequalizer.gif")

        data["embeds"] = [embed_queue, embed] if embed_queue else [embed]

        data["components"] = [
            disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
            disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
            disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
            disnake.ui.Button(emoji="<:music_queue:703761160679194734>", custom_id=PlayerControls.queue),
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
                        label="Adicionar favorito", emoji="⭐",
                        value=PlayerControls.enqueue_fav,
                        description="Adicionar um de seus favoritos na fila."
                    ),
                    disnake.SelectOption(
                        label="Tocar do inicio", emoji="⏪",
                        value=PlayerControls.seek_to_start,
                        description="Voltar o tempo da música atual para o inicio."
                    ),
                    disnake.SelectOption(
                        label="Volume", emoji="🔊",
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
                        label="Nightcore", emoji="🇳",
                        value=PlayerControls.nightcore,
                        description="Ativar/Desativar o efeito nightcore."
                    ),
                    disnake.SelectOption(
                        label="Ativar/Desativar modo restrito", emoji="🔐",
                        value=PlayerControls.restrict_mode,
                        description="Apenas DJ's/Staff's podem usar comandos restritos."
                    ),
                ]
            ),
        ]

        if not player.static and not player.has_thread:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Song-Request Thread", emoji="💬",
                    value=PlayerControls.song_request_thread,
                    description="Criar uma thread/conversa temporária para pedir músicas usando apenas o nome/link."
                )
            )

        try:
            if isinstance(player.text_channel.parent, disnake.ForumChannel):
                data["content"] = f"{emoji} {player.current.title[:50]}"
        except:
            pass

        return data

def load():
    return DefaultStaticSkin()
