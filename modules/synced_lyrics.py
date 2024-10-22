# Nota: Code incompleto e mal-otimizado (provavelmetne não será finalizado).
# Há possibilidade de ocorrer ratelimit do discord no ip da hospedagem devido a constante edição de mensagem (429: too many requests).

from __future__ import annotations
import asyncio
import itertools
import os
import pickle
from urllib.parse import quote

import regex as re
import traceback
from typing import TYPE_CHECKING, List, Union

import disnake
import pylrc
import syncedlyrics
from disnake.ext import commands

from utils.music.checks import has_source, check_voice, is_dj
from utils.music.converters import time_format, fix_characters, music_source_image, get_button_style
from utils.music.errors import GenericError
from utils.music.interactions import EmbedPaginatorInteraction
from utils.music.models import LavalinkPlayer, LavalinkTrack, PartialTrack
from utils.others import CustomContext, ProgressBar, PlayerControls, pool_command

if TYPE_CHECKING:
    from utils.client import BotCore

cache_data_file = "./local_database/.lyric_cache_data"

to_remove = (
    "lyric", "official", "video", "extended",
)


def remove_characters(text: str):

    for t in text.split():
        try:
            re.search(r'\p{L}|\p{N}', t)
        except:
            print(f"palavra: {t}")
            traceback.print_exc()

    return " ".join(t for t in text.split() if t == "-" or re.search(r'\p{L}|\p{N}', t)).strip()

class LiveLyrics(commands.Cog):
    emoji = "🎶"
    name = "Música"
    desc_prefix = f"[{emoji} {name}] | "

    footer_text = "Letras sincronizadas - beta/experimental"

    def __init__(self, bot: BotCore):
        self.bot = bot

    def lyric_id_save_cache_data(self):
        with open(cache_data_file, 'wb') as f:
            pickle.dump(self.bot.pool.lyric_data_cache, f)

    @commands.is_owner()
    @commands.command(hidden=True, aliases=["ccl"])
    async def clearcachely(self, ctx: CustomContext):
        self.bot.pool.lyric_data_cache.clear()
        try:
            os.remove(cache_data_file)
        except FileNotFoundError:
            pass
        await ctx.send("Cache de lyrics limpo!")

    async def fetch_lavalink_lyrics(self, query, ytm_id: str = None, duration: int = None):

        try:
            node = [n for n in self.bot.music.nodes.values() if n.lyric_support][0]
        except IndexError:
            return

        try:
            node_search = [n for n in self.bot.music.nodes.values() if "youtube" in n.info["sourceManagers"]][0]
        except IndexError:
            return

        if not ytm_id:

            cache_key = f"ytmid_search:{query}"

            if (ytm_id := self.bot.pool.lyric_data_cache.get(cache_key)) is None:

                print(f"Requisitando lyric (ytm id): {query}")

                async with node_search.session.get(f"{node_search.rest_uri}/v4/lyrics/search/{quote(query)}&source=youtube", headers=node_search.headers) as r:
                    if r.status != 200:
                        print(f"fetch lyrics failed: {r.status} - {await r.text()}")
                        return
                    data = await r.json()

                if not data:
                    self.bot.pool.lyric_data_cache[cache_key] = {}
                    return

                ytm_id = data[0]["videoId"]

                self.bot.pool.lyric_data_cache[cache_key] = ytm_id

        cache_key = f"lavalyric:{ytm_id}"

        if (lyric_data := self.bot.pool.lyric_data_cache.get(cache_key)) is None:
            print(f"Requisitando lyric (lavalyrics): {query}")
            try:
                lyric_data = await node.fetch_ytm_lyrics(ytm_id)
            except Exception as e:
                print(repr(e))
                self.bot.pool.lyric_data_cache[cache_key] = {}
                return

            lyric_data = {} if lyric_data.get("lines") is None else lyric_data

            self.bot.pool.lyric_data_cache[cache_key] = lyric_data

        try:
            if duration:
                last_timestamp = lyric_data["lines"][-1]["range"]["end"]
                if not (last_timestamp - 20000) < duration < (last_timestamp + 20000):
                    return {}
        except KeyError:
            pass

        return lyric_data

    async def fetch_lib_lyrics(self, query: str, duration = None):

        save = False

        cache_key = f"lyquery:{query.lower()}"

        if (data := self.bot.pool.lyric_data_cache.get(cache_key)) is None:
            print(f"Requisitando lyric (lrc): {query}")
            try:
                lrc: str = await self.bot.loop.run_in_executor(None, lambda: syncedlyrics.search(query, synced_only=True)) #, providers=["Musixmatch", "Lrclib", "NetEase", "Megalobiz"]))
            except Exception:
                traceback.print_exc()
                lrc = ""

            save = True

        else:
            lrc = data

        if not lrc:
            self.bot.pool.lyric_data_cache[cache_key] = {}
            if save:
                self.lyric_id_save_cache_data()
            return

        try:
            lrc: List[pylrc.parser.LyricLine] = pylrc.parse(''.join([f"{l}\n" for l in lrc.split("\n")]))

            if duration and not ((lrc[-1].time * 1000) - 20000) < duration < (lrc[-1].time * 1000) + 20000:
                self.bot.pool.lyric_data_cache[cache_key] = {}
                if save:
                    self.lyric_id_save_cache_data()
                return

            lines = []

            time_start = 0

            for n, d in enumerate(lrc):

                if ":" in d.text:
                    continue

                if time_start:
                    start = time_start
                    time_start = 0
                else:
                    start = d.time * 1000

                try:
                    end = lrc[n + 1].time * 1000
                except IndexError:
                    end = start + 7000

                text = d.text.strip() or "♪"

                if (end - start) < 3000:
                    try:
                        lines[n - 1]["range"]["end"] = end
                        if text != "♪":
                            lines[n - 1]["line"] += f". {text}"
                        time_start = start
                        continue
                    except IndexError:
                        pass

                lines.append({"line": text, "range": {"start": start, "end": end}})

            first_line = lines[0]

            if first_line["range"]["start"] > 5000 and first_line["line"] != "♪":
                lines.insert(0, {"line": "♪", "range": {"start": 0, "end": first_line["range"]["start"]}})
            else:
                lines[0]["range"]["start"] = 0

            data = {"lines": lines}

        except Exception:
            traceback.print_exc()
            data = {}

        if save:
            self.lyric_id_save_cache_data()

        return data

    async def fetch_lyrics(self, query: str, ytm_id: str = None, duration: int = None, lavalink_first=False):

        query = remove_characters(query.lower())

        if lavalink_first:
            data = await self.fetch_lavalink_lyrics(query=query, ytm_id=ytm_id, duration=duration) or await self.fetch_lib_lyrics(query, duration=duration)
        else:
            data = await self.fetch_lib_lyrics(query, duration=duration) or await self.fetch_lavalink_lyrics(query=query, ytm_id=ytm_id, duration=duration)

        return data

    lly_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)
    lly_cd = commands.CooldownMapping.from_cooldown(1, 7, commands.BucketType.member)

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(name="livelyrics", aliases=["lly", "syncedlyrics"], cooldown=lly_cd, max_concurrency=lly_mc, only_voiced=True,
                  description="Ativar/Desativar o sistema de letras sincronizadas (experimental).")
    async def live_lyrics_legacy(self, ctx: CustomContext):
        await self.live_lyrics.callback(self=self, inter=ctx)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(cooldown=lly_cd, max_concurrency=lly_mc, extras={"only_voiced": True},
                            description=f"{desc_prefix}Ativar/Desativar o sistema de letras sincronizadas (experimental).")
    async def live_lyrics(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        cog = bot.get_cog("Music")

        if cog:
            ephemeral = await cog.is_request_channel(inter, ignore_thread=True)
        else:
            ephemeral = True

        await inter.response.defer(ephemeral=ephemeral)

        if player.live_lyrics_enabled:
            self.lyriccancel(player)
            player.live_lyrics_enabled = False
            player.has_lyrics = False
            txt = f"{inter.author.mention} desativou o sistema de letras sincronizadas."
            emoji = "❌"
            txt_msg = f"{emoji} **⠂{txt}**"
            player.set_command_log(emoji=emoji, text=txt)
            if player.controller_mode:
                await player.invoke_np(force=True)
            await self.update_no_controller_msg(player)

        else:
            player.live_lyrics_enabled = True
            self.lyricupdater(player)
            txt = f"{inter.author.mention} ativou o sistema de letras sincronizadas."
            emoji = "🎤"
            txt_msg = (f"{emoji} **⠂{txt}**\n-# Nota: Esse sistema ainda está em fase de testes, sujeito a ocorrer a alguns erros "
                       f"como:\n"
                       f"-# * Letras indisponíveis em algumas músicas.\n"
                       f"-# * Problemas de sincronização.\n"
                       f"-# * Letras que não correspondem com a música. {player.controller_link}")
            player.set_command_log(emoji=emoji, text=txt)

        embed = disnake.Embed(description=txt_msg, color=self.bot.get_color(player.guild.me))

        try:
            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Bot selecionado: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
        except AttributeError:
            pass

        if isinstance(inter, CustomContext):
            await inter.send(embed=embed)
        else:
            await inter.edit_original_message(embed=embed)

    ly_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)
    ly_cd = commands.CooldownMapping.from_cooldown(2, 12, commands.BucketType.member)

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(name="lyrics", aliases=["ly", "letras"], cooldown=ly_cd, max_concurrency=ly_mc, only_voiced=True,
                  description="Exibir letras da música que está tocando atualmente.")
    async def lyrics_legacy(self, ctx: CustomContext):

        await self.lyrics.callback(self=self, inter=ctx)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(description=f"{desc_prefix}Exibir letras da música que está tocando atualmente.",
                            max_concurrency=ly_mc, cooldown=ly_cd, extras={"only_voiced": True})
    async def lyrics(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        cog = self.bot.get_cog("Music")

        if cog:
            ephemeral = await cog.is_request_channel(inter, ignore_thread=True)
        else:
            ephemeral = True

        await inter.response.defer(ephemeral=ephemeral)

        lrc = await self.fetch_lyrics(*self.parse_lyric_query(player.current), duration=player.current.duration)

        if not lrc:
            raise GenericError(f"**Não houve resultados para a música:**\n-# [{player.current.single_title} - {player.current.authors_string}]({player.current.uri})")

        embeds = []

        max_page = len(lrc["lines"]) > 20

        color = self.bot.get_color(player.guild.me)

        for data in disnake.utils.as_chunks(lrc["lines"], 20):

            if player.current.info["sourceName"] == "youtube":
                ly_lines = "\n".join(f'[`{time_format(l["range"]["start"])}]` [{l["line"]}]({player.current.uri + "&t=" + str(int(l["range"]["start"]/1000)) + "s"})' for l in data)

            elif player.current.info["sourceName"] == "soundcloud":
                ly_lines = "\n".join(f'[`{(tf:=time_format(l["range"]["start"]))}`] [{l["line"]}]({player.current.uri + "#t=" + tf})' for l in data)

            else:
                ly_lines = "\n".join(f'[{time_format(l["range"]["start"])}] `{l["line"]}`' for l in data)

            embed = disnake.Embed(
                color=color,
                description=f"## Letra da música:\n"
                            f"### [`{player.current.single_title}`]({player.current.uri})\n"
                            f"### Por: {player.current.authors_md}\n{ly_lines}"
            )

            embed.set_thumbnail(player.current.thumb)
            embed.set_footer(text="Comando em fase de testes.", icon_url="https://i.ibb.co/dkWYt88/pngegg.png")

            embeds.append(embed)

        if max_page:
            view = EmbedPaginatorInteraction(inter.author, embeds)
        else:
            view = None

        if isinstance(inter, CustomContext):
            msg = await inter.send(embed=embeds[0], view=view)
        else:
            msg = await inter.edit_original_message(embed=embeds[0], view=view)

        if view:
            await view.wait()

            for c in view.children:
                c.disabled = True

            if view.inter:
                await view.inter.response.edit_message(view=view)
            elif isinstance(inter, CustomContext):
                await msg.edit(view=view)
            else:
                await inter.edit_original_message(view=view)


    @commands.is_owner()
    @commands.command(hidden=True)
    async def clearlyrics(self, ctx: CustomContext):
        count = 0
        async with ctx.typing():
            for b in self.bot.pool.get_all_bots():
                for p in b.music.players.values():
                    try:
                        del p.current.info["extra"]["lyrics"]
                        count += 1
                    except:
                        pass

                    for t in p.queue + p.played:
                        try:
                            del t.info["extra"]["lyrics"]
                            count += 1
                        except:
                            pass

            if count:
                self.lyric_id_save_cache_data()
                await ctx.send(f"{count} letras deletada(s)")
            else:
                await ctx.send("Não há músicas com letras em cache...")

    @commands.Cog.listener('on_wavelink_track_end')
    async def lyric_end(self, player: LavalinkPlayer, reason: str = None, *args, **kwargs):

        if not player.live_lyrics_enabled:
            return

        self.lyriccancel(player)

        if reason == "REPLACED":
            await self.update_no_controller_msg(player)
            return

        await self.update_no_controller_msg(player)

    @commands.Cog.listener("on_player_destroy")
    async def lyric_destroy(self, player: LavalinkPlayer, *args, **kwargs):

        if not player.live_lyrics_enabled:
            return

        self.lyriccancel(player)
        await self.update_no_controller_msg(player)

    async def update_no_controller_msg(self, player: LavalinkPlayer):

        if player.controller_mode:
            return

        data = {"embeds": None, "components": None}

        try:
            data.update(player.np_original_data)
        except AttributeError:
            return

        player.np_original_data.clear()

        try:
            await player.message.edit(**data)
        except:
            pass

    @commands.Cog.listener('on_player_seek')
    @commands.Cog.listener('on_wavelink_track_start')
    @commands.Cog.listener('on_player_resume')
    async def lyric_start(self, player: LavalinkPlayer, *args, **kwargs):

        if not player.live_lyrics_enabled:
            return

        self.lyricupdater(player)


    @commands.Cog.listener('on_player_pause')
    async def lyric_pause(self, player: LavalinkPlayer):

        if not player.live_lyrics_enabled:
            return

        self.lyriccancel(player)

        if not player.controller_mode:
            return

        player.start_message_updater_task()

    async def send_lyric_message(self, player: LavalinkPlayer, embed: disnake.Embed, view=None, components=None):

        kwargs = {
            "embed": embed,
            "view": view,
        }

        if components:
            kwargs["components"] = components

        if not player.controller_mode:
            player.current = player.last_track
            data = player.bot.pool.player_skins[player.skin].load(player)
            data["content"] = ""
            try:
                await player.message.edit(**data)
            except:
                pass
            player.current = None

        elif player.message:

            perms = player.message.channel.permissions_for(player.message.guild.me)

            if not perms.send_messages and not perms.read_messages:
                return

            player.text_channel = player.message.channel

            await player.text_channel.edit(**kwargs)

    def parse_lyric_query(self, track: Union[LavalinkTrack, PartialTrack]):

        if track.uri.startswith("https://www.youtube.com/"):
            if track.author.endswith(" - topic") and not track.author.endswith(
                    "Release - topic") and not track.title.startswith(track.author[:-8]):
                return f"{track.author} - {track.title}".lower(), track.ytid
            else:
                title = f"{track.title.lower()}".strip()
        else:
            title = f"{track.single_title} - {track.authors_string}".lower()

        for w in to_remove:
            title = title.replace(w, "")
            
        return title.strip(), None

    def lyriccancel(self, player: LavalinkPlayer):
        try:
            player.lyric_task.cancel()
        except:
            pass

    def lyricupdater(self, player: LavalinkPlayer):

        if not player.live_lyrics_enabled:
            return

        self.lyriccancel(player)
        player.lyric_task = player.bot.loop.create_task(self.lyric_task(player, player.current))

    async def lyric_task(self, player: LavalinkPlayer, track: LavalinkTrack):

        if not player.live_lyrics_enabled:
            return

        if player.auto_pause:
            return

        await asyncio.sleep(1)

        try:
            try:
                player: LavalinkPlayer = player.bot.music.players[player.guild_id]
            except KeyError:
                return

            if not player.current or not player.text_channel or "nightcore" in player.current.title.lower():
                return

            perms = player.text_channel.permissions_for(player.text_channel.guild.me)

            if not perms.read_messages or not perms.send_messages:
                return

            if player.current.is_stream or not (15000 < player.current.duration < 480000) or (player.current.duration - player.position) < 3000:
                lyrics_data = {}
            else:
                lyrics_data = await self.fetch_lyrics(*self.parse_lyric_query(player.current), duration=player.current.duration)

            if not lyrics_data or not (lineinfos := lyrics_data.get("lines")):
                return

            if lineinfos[-1]['range']['end'] > player.current.duration:
                lineinfos[-1]['range']['end'] = player.current.duration

            txt_info = f"-# 👤 **⠂Uploader:** {player.current.authors_md}\n"

            if not player.current.autoplay:
                txt_info += f"-# ✋ **⠂Pedido por:** <@{player.current.requester}>\n"
            else:
                try:
                    mode = f" [`Recomendação`]({player.current.info['extra']['related']['uri']})"
                except:
                    mode = "`Recomendação`"
                txt_info += f"-# 👍 **⠂Adicionado via:** {mode}\n"

            if player.current.album_name:
                txt_info += f"-# 💽 **⠂Álbum:** [`{fix_characters(player.current.album_name, limit=20)}`]({player.current.album_url})\n"

            if player.current.playlist_name:
                txt_info += f"-# 📑 **⠂Playlist:** [`{fix_characters(player.current.playlist_name, limit=20)}`]({player.current.playlist_url})\n"

            kwargs = {}

            if not player.controller_mode or (player.message and not player.message.components):

                if not player.controller_mode:
                    try:
                        player.np_original_data = {"content": player.message.content, "embeds": player.message.embeds}
                    except AttributeError:
                        pass

                kwargs["components"] = [
                    disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume,
                                      style=get_button_style(player.paused)),
                    disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
                    disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
                    disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
                    disnake.ui.Button(emoji="<:music_queue:703761160679194734>", custom_id=PlayerControls.queue,
                                      disabled=not (player.queue or player.queue_autoplay)),
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
                                label=("Desativar" if player.nightcore else "Ativar") + " o efeito nightcore",
                                emoji="🇳",
                                value=PlayerControls.nightcore,
                                description="Efeito que aumenta velocidade e tom da música."
                            ),
                            disnake.SelectOption(
                                label=("Desativar" if player.autoplay else "Ativar") + " a reprodução automática",
                                emoji="🔄",
                                value=PlayerControls.autoplay,
                                description="Sistema de adição de música automática quando a fila estiver vazia."
                            ),
                            disnake.SelectOption(
                                label=("Desativar" if player.restrict_mode else "Ativar") + " o modo restrito",
                                emoji="🔐",
                                value=PlayerControls.restrict_mode,
                                description="Apenas DJ's/Staff's podem usar comandos restritos."
                            ),
                        ]
                    ),
                ]

                if player.static:
                    if (queue := player.queue or player.queue_autoplay):
                        kwargs["components"].append(
                            disnake.ui.Select(
                                placeholder="Próximas músicas:",
                                custom_id="musicplayer_queue_dropdown",
                                min_values=0, max_values=1,
                                options=[
                                    disnake.SelectOption(
                                        label=f"{n + 1}. {fix_characters(t.author, 18)}",
                                        description=fix_characters(t.title, 47),
                                        value=t.title[:100]
                                    ) for n, t in enumerate(itertools.islice(queue, 25))
                                ]
                            )
                        )

            try:
                player.message_updater_task.cancel()
            except:
                pass

            player.has_lyrics = True

            player.update = False

            for n, line in enumerate(lineinfos):

                try:
                    player = self.bot.music.players[player.guild_id]
                except KeyError:
                    return

                if not player.current or not player.live_lyrics_enabled:
                    return

                if line['range']['end'] < player.position:
                    continue

                sleep_time = (line['range']['end'] - player.position) / 1000

                txt = f"[`{player.current.title}`](<{player.current.uri}>)"

                progress = ProgressBar(
                    player.position,
                    player.current.duration,
                    bar_count=12 if isinstance(player.text_channel, disnake.Thread) else 22
                )

                if player.current.info["sourceName"] == "youtube" and "&t=" not in player.current.uri:
                    track_url = player.current.uri + f"&t={int(player.position / 1000)}"
                elif player.current.info["extra"].get("ytmid"):
                    track_url = f'https://music.youtube.com/watch?v={player.current.ytid or player.current.info["extra"]["ytmid"]}&t={int(player.position / 1000)}s'
                else:
                    track_url = player.current.uri

                txt += f"\n\n[`[{time_format(player.position)}]`](<{track_url}>) "
                if progress.start:
                    txt += f"[`{('━' * progress.start)}`](<{track_url}>)"
                if progress.end:
                    txt += f"`{'━' * progress.end}`"
                txt += f" `[{time_format(player.current.duration)}]`\n"

                player.lyric_embed = disnake.Embed(
                    description=f"{txt}\n{txt_info}\n",
                    color=self.bot.get_color(player.guild.me),
                ).set_footer(
                    text=self.footer_text, icon_url="https://i.ibb.co/dkWYt88/pngegg.png")

                if player.static:
                    player.lyric_embed.set_image(player.current.thumb)
                else:
                    player.lyric_embed.set_thumbnail(player.current.thumb)

                if player.current.info["sourceName"] == "youtube" and "&t=" not in player.current.uri:

                    if n != 0:
                        try:
                            t = lineinfos[n - 1]
                            player.lyric_embed.description += f'> [`{t["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`](<{player.current.uri}&t={int(t["range"]["start"] / 1000)}s>)\n'
                        except:
                            pass

                    player.lyric_embed.description += '> ## ' + ("🎶" if line[
                                                                          "line"] == "♪" else "🎤") + f' ⠂[`{line["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`](<{player.current.uri}&t={int(line["range"]["start"] / 1000)}s>)\n'

                    try:
                        t = lineinfos[n + 1]
                        player.lyric_embed.description += f'> [`{t["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`](<{player.current.uri}&t={int(t["range"]["start"] / 1000)}s>)\n'
                    except:
                        pass

                elif player.current.ytid:

                    if n != 0:
                        try:
                            t = lineinfos[n - 1]
                            player.lyric_embed.description += f'> [`{t["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`](<https://music.youtube.com/watch?v={player.current.ytid or player.current.ytid}&t={int(t["range"]["start"] / 1000)}s>)\n'
                        except:
                            pass

                    player.lyric_embed.description += '> ## ' + ("🎶" if line["line"] == "♪" else "🎤") + f' ⠂[`{line["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`](<https://music.youtube.com/watch?v={player.current.ytid or player.current.ytid}&t={int(line["range"]["start"] / 1000)}s>)\n'

                    try:
                        t = lineinfos[n + 1]
                        player.lyric_embed.description += f'> [`{t["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`](<https://music.youtube.com/watch?v={player.current.ytid or player.current.ytid}&t={int(t["range"]["start"] / 1000)}s>)\n'
                    except:
                        pass

                else:

                    if n != 0:
                        try:
                            t = lineinfos[n - 1]
                            player.lyric_embed.description += f'> `{t["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`\n'
                        except:
                            pass

                    player.lyric_embed.description += '> ## ' + ("🎶" if line["line"] == "♪" else "🎤") + f' ⠂`{line["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`\n'

                    try:
                        t = lineinfos[n + 1]
                        player.lyric_embed.description += f'> `{t["line"].replace("♪", " 🎵 🎶 🎵 🎶 🎵 🎶 ")}`\n'
                    except:
                        pass

                player.lyric_embed.set_author(name="⠂Tocando agora:",
                                              icon_url=music_source_image(player.current.info["sourceName"]))

                if player.controller_mode:

                    txt = ""

                    try:
                        if player.static and isinstance(player.text_channel.parent, disnake.ForumChannel):
                            txt = f"`{'🎤' if not player.paused else '⏸️'} {fix_characters(player.current.title, 50)} - by: {player.current.author}`\n\n"
                    except:
                        pass

                    try:
                        await player.message.edit(content=txt, embed=player.lyric_embed, **kwargs)
                    except:
                        if not player.static:
                            player.message = await player.text_channel.send(embed=player.lyric_embed, **kwargs)
                else:

                    if player.command_log:
                        player.lyric_embed.description += f"\n{player.command_log_emoji} ⠂**Última Interação:**\n-# {player.command_log}"

                    if player.current_hint:
                        player.lyric_embed.description += f"\n-# `💡 Dica: {player.current_hint}`"

                    try:
                        await player.message.edit(content=None, embed=player.lyric_embed, **kwargs)
                    except:
                        player.message = await player.text_channel.send(txt, embed=player.lyric_embed)

                await asyncio.sleep(sleep_time if sleep_time > 0 else 1)

            if player.position > (player.current.duration - 10000):
                return

            player.has_lyrics = False

            if player.controller_mode:
                await player.invoke_np()
            else:
                await self.update_no_controller_msg(player=player)

        except Exception:
            traceback.print_exc()

    def cog_unload(self) -> None:
        for p in self.bot.music.players.values():
            self.lyriccancel(p)

    def cog_load(self) -> None:
        for p in self.bot.music.players.values():
            self.lyricupdater(p)


def setup(bot: BotCore):
    bot.add_cog(LiveLyrics(bot))
