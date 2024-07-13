# -*- coding: utf-8 -*-
import datetime
from os.path import basename

import disnake

from utils.music.converters import fix_characters, time_format, get_button_style, music_source_image
from utils.music.models import LavalinkPlayer
from utils.others import PlayerControls


class DefaultStaticSkin:
    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = basename(__file__)[:-3] + "_static"
        self.preview = "https://i.ibb.co/fDzTqtV/default-static-skin.png"

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

        queue_img = ""

        current_time = disnake.utils.utcnow() - datetime.timedelta(milliseconds=player.position)

        duration = f"> -# 🔴 **⠂Yayın:** <t:{int(current_time.timestamp())}:R>\n" if player.current.is_stream else \
            (f"> -# ⏰ **⠂Süre:** `{time_format(player.current.duration)} [`<t:{int(current_time.timestamp())}:R>`]`\n"
            if not player.paused else '')

        txt = f"-# [`{player.current.single_title}`]({player.current.uri or player.current.search_uri})\n\n" \
              f"{duration}" \
              f"> -# 💠 **⠂Yayıncı:** {player.current.authors_md}"

        if not player.current.autoplay:
            txt += f"\n> -# ✋ **⠂Talep eden::** <@{player.current.requester}>"
        else:
            try:
                mode = f" [`Öneri`]({player.current.info['extra']['related']['uri']})"
            except:
                mode = "`Öneri`"
            txt += f"\n> -# 👍 **⠂Şununla eklendi::** {mode}"

        try:
            vc_txt = f"\n> -# *️⃣ **⠂Ses kanalı:** {player.guild.me.voice.channel.mention}"
        except AttributeError:
            pass

        if player.current.track_loops:
            txt += f"\n> -# 🔂 **⠂Kalan tekrarlar:** `{player.current.track_loops}`"

        if player.loop:
            if player.loop == 'current':
                e = '🔂'; m = 'Güncel müzik'
            else:
                e = '🔁'; m = 'Dosya'
            txt += f"\n> -# {e} **⠂Tekrar modu:** `{m}`"

        if player.current.album_name:
            txt += f"\n> -# 💽 **⠂Álbüm:** [`{fix_characters(player.current.album_name, limit=20)}`]({player.current.album_url})"

        if player.current.playlist_name:
            txt += f"\n> -# 📑 **⠂Çalma listesi:** [`{fix_characters(player.current.playlist_name, limit=20)}`]({player.current.playlist_url})"

        if player.keep_connected:
            txt += "\n> -# ♾️ **⠂7/24 modu:** `Aktif`"

        txt += f"{vc_txt}\n"

        if player.command_log:
            txt += f"```ansi\n [34;1mSon Etkileşim:[0m```**┕ {player.command_log_emoji} ⠂**{player.command_log}\n"

        if qlenght:=len(player.queue):

            queue_txt = ""

            has_stream = False

            current_time += datetime.timedelta(milliseconds=player.current.duration)

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

                    queue_txt += f"-# `┌ {n+1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                           f"-# `└ ⏲️ {duration}`" + (f" - `Temsilciler: {t.track_loops}`" if t.track_loops else "") + \
                           f" **|** `✋` <@{t.requester}>\n"

                else:
                    duration = f"<t:{int((current_time + datetime.timedelta(milliseconds=queue_duration)).timestamp())}:R>"

                    queue_txt += f"-# `┌ {n+1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                           f"-# `└ ⏲️` {duration}" + (f" - `Temsilciler: {t.track_loops}`" if t.track_loops else "") + \
                           f" **|** `✋` <@{t.requester}>\n"

            embed_queue = disnake.Embed(title=f"Músicas na fila: {qlenght}", color=player.bot.get_color(player.guild.me),
                                        description=f"\n{queue_txt}")

            if not has_stream and not player.loop and not player.keep_connected and not player.paused and not player.current.is_stream:
                embed_queue.description += f"\n`[ ⌛ Şarkılar bitiyor` <t:{int((current_time + datetime.timedelta(milliseconds=queue_duration + player.current.duration)).timestamp())}:R> `⌛ ]`"

            embed_queue.set_image(url=queue_img)

        elif len(player.queue_autoplay):

            queue_txt = ""

            has_stream = False

            current_time += datetime.timedelta(milliseconds=player.current.duration)

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

                    queue_txt += f"-# `┌ {n+1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                           f"-# `└ ⏲️ {duration}`" + (f" - `Temsilciler: {t.track_loops}`" if t.track_loops else "") + \
                           f" **|** `👍⠂Tavsiye edilen`\n"

                else:
                    duration = f"<t:{int((current_time + datetime.timedelta(milliseconds=queue_duration)).timestamp())}:R>"

                    queue_txt += f"-# `┌ {n+1})` [`{fix_characters(t.title, limit=34)}`]({t.uri})\n" \
                           f"-# `└ ⏲️` {duration}" + (f" - `Temsilciler: {t.track_loops}`" if t.track_loops else "") + \
                           f" **|** `👍⠂Tavsiye edilen`\n"

            embed_queue = disnake.Embed(title="Önerilen gelecek şarkılar:", color=player.bot.get_color(player.guild.me),
                                        description=f"\n{queue_txt}")

            embed_queue.set_image(url=queue_img)

        embed.description = txt

        embed.set_image(url=player.current.thumb or "https://media.discordapp.net/attachments/480195401543188483/987830071815471114/musicequalizer.gif")

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
                        description="Geçerli şarkının temposunu başlangıca döndür."
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
                        description="Readicionar as músicas tocadas de volta na fila."
                    ),
                    disnake.SelectOption(
                        label="Repetição", emoji="🔁",
                        value=PlayerControls.loop_mode,
                        description="Şarkı/sıra tekrarını etkinleştirin/devre dışı bırakın."
                    ),
                    disnake.SelectOption(
                        label=("Devre dışı bırakıldı" if player.nightcore else "Etkinleştirildi") + " nightcore efekti", emoji="🇳",
                        value=PlayerControls.nightcore,
                        description="Efeito que aumenta velocidade e tom da música."
                    ),
                    disnake.SelectOption(
                        label=("Devre dışı bırakıldı" if player.autoplay else "Etkinleştirildi") + " otomatik oynatma", emoji="🔄",
                        value=PlayerControls.autoplay,
                        description="Sıra boşaldığında😨 otomatik müzik ekleme sistemi."
                    ),
                    disnake.SelectOption(
                        label= ("Devre dışı bırakıldı" if player.restrict_mode else "Etkinleştirildi") + " kısıtlı mod", emoji="🔐",
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
    return DefaultStaticSkin()
