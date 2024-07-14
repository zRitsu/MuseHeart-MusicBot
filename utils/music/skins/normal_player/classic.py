# -*- coding: utf-8 -*-
import itertools
from os.path import basename

import disnake

from utils.music.converters import fix_characters, time_format, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class ClassicSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://i.ibb.co/893S3dJ/image.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = True
        player.controller_mode = True
        player.auto_update = 0
        player.hint_rate = player.bot.config["HINT_RATE"]
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        color = player.bot.get_color(player.guild.me)

        embed = disnake.Embed(color=color, description="")

        queue_txt = ""

        bar = "https://i.ibb.co/fVgyxLZ/output-onlinegiftools.gif"

        embed_top = disnake.Embed(
            color=color,
            description=f"### [{player.current.title}]({player.current.uri or player.current.search_uri})"
        )
        embed.set_image(url=bar)

        embed_top.set_image(url=bar)

        embed_top.set_thumbnail(url=player.current.thumb)

        if not player.paused:
            (embed_top or embed).set_author(
                name="Şimdi çalıyor:",
                icon_url=music_source_image(player.current.info["sourceName"])
            )
        else:
            (embed_top or embed).set_author(
                name="Duraklatıldı:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        if player.current.is_stream:
            duration = "🔴 **⠂ `Canlı yayın`"
        else:
            duration = f"⏰ **⠂** `{time_format(player.current.duration)}`"

        txt = f"{duration}\n" \
              f"👤 **⠂** `{player.current.author}`\n"

        if not player.current.autoplay:
            txt += f"🎧 **⠂** <@{player.current.requester}>\n"
        else:
            try:
                mode = f" [`Recomendada`]({player.current.info['extra']['related']['uri']})"
            except:
                mode = "`Recomendada`"
            txt += f"> 👍 **⠂** {mode}\n"

        if player.current.playlist_name:
            txt += f"📑 **⠂** [`{fix_characters(player.current.playlist_name, limit=19)}`]({player.current.playlist_url})\n"

        if qsize := len(player.queue):

            if not player.mini_queue_enabled:
                txt += f"🎶 **⠂** `{qsize} müzik{'ler'[:qsize^1]} ve sıra`\n"
            else:
                queue_txt += "```ansi\n[0;33mGelecek Şarkılar:[0m```" + "\n".join(
                    f"`{(n + 1):02}) [{time_format(t.duration) if t.duration else '🔴 Canlı yayın'}]` "
                    f"[`{fix_characters(t.title, 29)}`]({t.uri})" for n, t in
                    enumerate(itertools.islice(player.queue, 3))
                )

                if qsize > 3:
                    queue_txt += f"\n`╚══════ Sıradaki {(t:=qsize - 3)} müzik{'ler'[:t^1]} ══════╝`"

        elif len(player.queue_autoplay):
            queue_txt += "```ansi\n[0;33mGelecek Şarkılar:[0m```" + "\n".join(
                f"`👍⠂{(n + 1):02}) [{time_format(t.duration) if t.duration else '🔴 Canlı yayın'}]` "
                f"[`{fix_characters(t.title, 29)}`]({t.uri})" for n, t in
                enumerate(itertools.islice(player.queue_autoplay, 3))
            )

        if player.command_log:
            txt += f"{player.command_log_emoji} **⠂Son Etkileşim:** {player.command_log}\n"

        embed.description += txt + queue_txt

        if player.current_hint:
            embed.set_footer(text=f"💡 Not: {player.current_hint}")
        else:
            embed.set_footer(
                text=str(player),
                icon_url="https://i.ibb.co/LxXWyjG/3dgifmaker97684.gif"
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
                        label="Müzik ekle", emoji="<:add_music:588172015760965654>",
                        value=PlayerControls.add_song,
                        description="Sıraya bir şarkı/çalma listesi ekleyin."
                    ),
                    disnake.SelectOption(
                        label="Sıraya favori ekle", emoji="⭐",
                        value=PlayerControls.enqueue_fav,
                        description="Favorilerinizden birini sıraya ekleyin."
                    ),
                    disnake.SelectOption(
                        label="Favorilerinize ekleyin", emoji="💗",
                        value=PlayerControls.add_favorite,
                        description="Mevcut şarkıyı favorilerinize ekleyin."
                    ),
                    disnake.SelectOption(
                        label="Baştan itibaren oyna", emoji="⏪",
                        value=PlayerControls.seek_to_start,
                        description="Geçerli şarkının temposunu başlangıca döndürür."
                    ),
                    disnake.SelectOption(
                        label=f"Ses: {player.volume}%", emoji="🔊",
                        value=PlayerControls.volume,
                        description="Ses seviyesini ayarlayın."
                    ),
                    disnake.SelectOption(
                        label="Karıştır", emoji="🔀",
                        value=PlayerControls.shuffle,
                        description="Sıradaki şarkıları karıştırın."
                    ),
                    disnake.SelectOption(
                        label="Yeniden Ekle", emoji="🎶",
                        value=PlayerControls.readd,
                        description="Çalınan şarkıları tekrar sıraya ekleyin."
                    ),
                    disnake.SelectOption(
                        label="Tekrar", emoji="🔁",
                        value=PlayerControls.loop_mode,
                        description="Şarkı/sıra tekrarını etkinleştirme/devre dışı bırakma."
                    ),
                    disnake.SelectOption(
                        label=("Devre dışı bırakmak" if player.nightcore else "Etkinleştir") + " nightcore efekti", emoji="🇳",
                        value=PlayerControls.nightcore,
                        description="Müziğin hızını ve tonunu artıran efekt."
                    ),
                    disnake.SelectOption(
                        label=("Devre dışı bırakmak" if player.autoplay else "Etkinleştir") + " otomatik oynatma", emoji="🔄",
                        value=PlayerControls.autoplay,
                        description="Sıra boşaldığında otomatik müzik ekleme sistemi."
                    ),
                    disnake.SelectOption(
                        label= ("Devre dışı bırakmak" if player.restrict_mode else "Etkinleştir") + " kısıtlı mod", emoji="🔐",
                        value=PlayerControls.restrict_mode,
                        description="Yalnızca DJ'ler/Personel kısıtlı komutları kullanabilir."
                    ),
                ]
            ),
        ]

        if player.current.ytid and player.node.lyric_support:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label= "Şarkı sözlerini görüntüle", emoji="📃",
                    value=PlayerControls.lyrics,
                    description="Mevcut şarkının sözlerini al."
                )
            )


        if player.mini_queue_feature:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Mini fila oynatıcısı", emoji="<:music_queue:703761160679194734>",
                    value=PlayerControls.miniqueue,
                    description="Oynatıcı mini kuyruğunu etkinleştirin/devre dışı bırakın."
                )
            )

        if isinstance(player.last_channel, disnake.VoiceChannel):
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Otomatik durum", emoji="📢",
                    value=PlayerControls.set_voice_status,
                    description="Otomatik ses kanalı durumunu yapılandırın."
                )
            )

        if not player.static and not player.has_thread:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Şarkı İsteği Konusu", emoji="💬",
                    value=PlayerControls.song_request_thread,
                    description="Yalnızca adı/bağlantıyı kullanarak şarkı istemek için geçici bir konu/konuşma oluşturun."
                )
            )

        return data

def load():
    return ClassicSkin()
