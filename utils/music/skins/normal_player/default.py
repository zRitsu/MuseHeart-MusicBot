# -*- coding: utf-8 -*-
import datetime
import itertools
from os.path import basename

import disnake

from utils.music.converters import fix_characters, time_format, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class DefaultSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3]
        self.preview = "https://i.ibb.co/4PkWyqb/image.png"

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

        embed = disnake.Embed(color=color)
        embed_queue = None
        vc_txt = ""

        if not player.paused:
            embed.set_author(
                name="Şimdi çalıyor:",
                icon_url=music_source_image(player.current.info["sourceName"])
            )

        else:
            embed.set_author(
                name="Duraklatıldı:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        if player.current_hint:
            embed.set_footer(text=f"💡 Not: {player.current_hint}")
        else:
            embed.set_footer(
                text=str(player),
                icon_url="https://i.ibb.co/LxXWyjG/3dgifmaker97684.gif"
            )

        player.mini_queue_feature = True

        duration = "> -# 🔴 **⠂** `Canlı yayın`\n" if player.current.is_stream else \
            (f"> -# ⏰ **⠂** `{time_format(player.current.duration)} [`" +
            f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>`]`\n"
            if not player.paused else '')

        txt = f"-# [`{player.current.single_title}`]({player.current.uri or player.current.search_uri})\n\n" \
              f"{duration}" \
              f"> -# 👤 **⠂** {player.current.authors_md}"

        if not player.current.autoplay:
            txt += f"\n> -# ✋ **⠂** <@{player.current.requester}>"
        else:
            try:
                mode = f" [`Tavsiye edilen`]({player.current.info['extra']['related']['uri']})"
            except:
                mode = "`Tavsiye edilen`"
            txt += f"\n> -# 👍 **⠂** {mode}"

        if player.current.track_loops:
            txt += f"\n> -# 🔂 **⠂** `Sıradaki Müzikler: {player.current.track_loops}`"

        if player.loop:
            if player.loop == 'current':
                e = '🔂'; m = 'Güncel müzik'
            else:
                e = '🔁'; m = 'Fila'
            txt += f"\n> -# {e} **⠂** `Liste: {m}`"

        if player.current.album_name:
            txt += f"\n> -# 💽 **⠂** [`{fix_characters(player.current.album_name, limit=36)}`]({player.current.album_url})"

        if player.current.playlist_name:
            txt += f"\n> -# 📑 **⠂** [`{fix_characters(player.current.playlist_name, limit=36)}`]({player.current.playlist_url})"

        if (qlenght:=len(player.queue)) and not player.mini_queue_enabled:
            txt += f"\n> -# 🎶 **⠂** `{qlenght} müzik{'ler'[:qlenght^1]} ve sıra`"

        if player.keep_connected:
            txt += "\n> -# ♾️ **⠂** `7/24 modu etkinleştirildi`"

        txt += f"{vc_txt}\n"

        bar = "https://i.ibb.co/VCKrSqz/output-onlinegiftools-1.gif"

        if player.command_log:
            txt += f"```ansi\n [34;1mSon Etkileşim:[0m```**┕ {player.command_log_emoji} ⠂**{player.command_log}\n"

        if player.mini_queue_enabled:

            if len(player.queue):

                queue_txt = "\n".join(
                    f"-# `{(n + 1):02}) [{time_format(t.duration) if not t.is_stream else '🔴 Canlı yayın'}]` [`{fix_characters(t.title, 21)}`]({t.uri})"
                    for n, t in (enumerate(itertools.islice(player.queue, 3)))
                )

                embed_queue = disnake.Embed(title=f"Sıradaki şarkılar: {qlenght}", color=color,
                                            description=f"\n{queue_txt}")

                if not player.loop and not player.keep_connected and not player.paused:

                    queue_duration = 0

                    for t in player.queue:
                        if not t.is_stream:
                            queue_duration += t.duration

                    embed_queue.description += f"\n-# `[⌛ Şarkılar bitiyor` <t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=(queue_duration + (player.current.duration if not player.current.is_stream else 0)) - player.position)).timestamp())}:R> `⌛]`"

                embed_queue.set_image(url=bar)

            elif len(player.queue_autoplay):
                queue_txt = "\n".join(
                    f"-# `👍⠂{(n + 1):02}) [{time_format(t.duration) if not t.is_stream else '🔴 Canlı yayın'}]` [`{fix_characters(t.title, 20)}`]({t.uri})"
                    for n, t in (enumerate(itertools.islice(player.queue_autoplay, 3)))
                )
                embed_queue = disnake.Embed(title="Önerilen gelecek şarkılar:", color=color,
                                            description=f"\n{queue_txt}")
                embed_queue.set_image(url=bar)

        embed.description = txt
        embed.set_image(url=bar)
        embed.set_thumbnail(url=player.current.thumb)

        data["embeds"] = [embed_queue, embed] if embed_queue else [embed]

        data["components"] = [
            disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
            disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
            disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
            disnake.ui.Button(emoji="<:music_queue:703761160679194734>", custom_id=PlayerControls.queue, disabled=not (player.queue or player.queue_autoplay)),
            disnake.ui.Select(
                placeholder="Daha fazla seçenek:",
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
                        description="Sesi ayarla."
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
                        label=("Devre dışı bırakıldı" if player.nightcore else "Etkinleştirildi") + " nightcore efekti", emoji="🇳",
                        value=PlayerControls.nightcore,
                        description="Müziğin hızını ve tonunu artıran efekt."
                    ),
                    disnake.SelectOption(
                        label=("Devre dışı bırakıldı" if player.autoplay else "Etkinleştirildi") + " otomatik oynatma", emoji="🔄",
                        value=PlayerControls.autoplay,
                        description="Sıra boşaldığında otomatik müzik ekleme sistemi."
                    ),
                    disnake.SelectOption(
                        label= ("Devre dışı bırakıldı" if player.restrict_mode else "Etkinleştirildi") + " kısıtlı mod", emoji="🔐",
                        value=PlayerControls.restrict_mode,
                        description="Yalnızca DJ'ler/Personeller kısıtlı komutları kullanabilir."
                    ),
                ]
            ),
        ]

        if player.current.ytid and player.node.lyric_support:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label= "Şarkı sözlerini görüntüle", emoji="📃",
                    value=PlayerControls.lyrics,
                    description="Geçerli şarkının sözlerini alın."
                )
            )


        if player.mini_queue_feature:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Mini fila oynatıcısı", emoji="<:music_queue:703761160679194734>",
                    value=PlayerControls.miniqueue,
                    description="Oyuncu mini kuyruğunu etkinleştirme/devre dışı bırakma."
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
    return DefaultSkin()
