from __future__ import annotations

import datetime
import pprint

import disnake
import asyncio
import wavelink
from yt_dlp import YoutubeDL
from functools import partial
from .converters import fix_characters, time_format, get_button_style, URL_REG
from .filters import AudioFilter
from .interactions import PlayerInteractions
from .spotify import SpotifyTrack
import itertools
import traceback
from collections import deque
from .errors import GenericError
from typing import Optional, Union, TYPE_CHECKING
if TYPE_CHECKING:
    from ..client import BotCore



YDL_OPTIONS = {
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'retries': 5,
    'extract_flat': True,
    'cachedir': False,
    'extractor_args': {
        'youtube': {
            'skip': [
                'hls',
                'dash'
            ],
            'player_skip': [
                'js',
                'configs',
                'webpage'
            ]
        },
        'youtubetab': ['webpage']
    }
}


filters = {
    'nightcore': 'aresample=48000,asetrate=48000*1.25'
}


class WavelinkVoiceClient(disnake.VoiceClient):

    # Esta classe é apenas um tapa-buraco pra versão 2.x do dpy ou outro fork atualizado.

    def __call__(self, client: disnake.Client, channel: disnake.VoiceChannel):
        self.client: disnake.Client = client
        self.channel: disnake.VoiceChannel = channel
        return self

    def __init__(self, client: disnake.Client, channel: Union[disnake.VoiceChannel, disnake.StageChannel],
                 player: wavelink.Player):
        self.bot = client
        self.channel = channel
        self.wavelink: wavelink.Client = self.bot.music
        self.player = player

    async def on_voice_server_update(self, data):
        lavalink_data = {
            't': 'VOICE_SERVER_UPDATE',
            'd': data
        }

        await self.wavelink.update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        lavalink_data = {
            't': 'VOICE_STATE_UPDATE',
            'd': data
        }

        await self.wavelink.update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        await self.guild.change_voice_state(channel=self.channel)
        self._connected = True

    async def disconnect(self, *, force: bool) -> None:
        if not force and not self.player.is_connected:
            return

        await self.channel.guild.change_voice_state(channel=None)

        self.player.channel_id = None
        self.cleanup()


class LavalinkTrack(wavelink.Track):

    def __init__(self, *args, **kwargs):
        self.requester = kwargs.pop('requester')
        self.playlist = kwargs.pop('playlist', None)
        self.repeats = kwargs.pop('repeats', 0)
        args[1]['title'] = fix_characters(args[1]['title'])
        super().__init__(*args, **kwargs)
        if self.ytid:
            self.thumb = f"https://img.youtube.com/vi/{self.ytid}/mqdefault.jpg"
        elif "soundcloud.com" in self.uri:
            self.thumb = self.info.get("artworkUrl", "").replace('large.jpg', 't500x500.jpg')
        else:
            self.thumb = self.info.get("artworkUrl", "")


class YTDLPlaylist:

    def __init__(self, data: dict, playlist: dict):
        self.data = data

        self.tracks = [
            YTDLTrack(
                data=i,
                playlist=playlist
            ) for i in data['tracks'] if i.get('duration')]


class YTDLSource(disnake.PCMVolumeTransformer):

    def __init__(self, source):
        super().__init__(source)

    @classmethod
    async def source(cls, url, *, ffmpeg_opts):
        return cls(disnake.FFmpegPCMAudio(url, **ffmpeg_opts))



class YTDLTrack:

    def __init__(self, *args, **kwargs):

        data = kwargs.pop('data', {}) or args[1]

        self.author = fix_characters(data.get('uploader', ''))
        self.id = data.pop('source', '')
        self.title = f"{fix_characters(data.get('title', ''))}"
        self.uri = data.get('webpage_url') or data.get('url')
        self.duration = data.get('duration', 0) * 1000
        self.is_stream = False
        self.info = data
        self.requester = kwargs.pop('requester', '')
        self.playlist = kwargs.pop('playlist', {})
        self.repeats = kwargs.pop('repeats', 0)

        if (data.get("ie_key") or data.get('extractor_key')) == "Youtube":
            self.thumb = f"https://img.youtube.com/vi/{data['id']}/mqdefault.jpg"
        else:
            self.thumb = data.get('thumbnail', '')


class BasePlayer:

    bot: BotCore
    volume: int
    node: wavelink.node
    vc: disnake.VoiceProtocol
    music_core: str

    def __init__(self, *args, **kwargs):

        try:
            super().__init__(*args, **kwargs)
        except:
            pass

        self.requester = kwargs.pop('requester')
        self.guild: disnake.Guild = kwargs.pop('guild')
        self.text_channel: disnake.TextChannel = kwargs.pop('channel')
        self.dj = [] if self.requester.guild_permissions.manage_channels else [self.requester]
        self.message: Optional[disnake.Message] = kwargs.pop('message', None)
        self.static = kwargs.pop('static', False)
        self.cog = kwargs.pop('cog')
        self.filters = {}
        self.queue = deque()
        self.played = deque(maxlen=20)
        self.nightcore = False
        self.loop = False
        self.last_track: Optional[LavalinkTrack, YTDLTrack] = None
        self.locked = False
        self.idle = None
        self.idle_timeout = 180  # aguardar 3 minutos para adicionar novas músicas
        self.is_previows_music = False
        self.updating_message = None
        self.command_log = ""
        self.last_embed = None
        self.interaction_cooldown = False
        self.votes = set()
        self.msg_ad = self.cog.bot.config.get("link")
        self.view: Optional[disnake.ui.View] = None
        self.current: Optional[LavalinkTrack, SpotifyTrack, YTDLTrack] = None
        self.paused = False
        self.view: Optional[disnake.ui.View] = None

    async def idling_mode(self):

        try:
            self.view.stop()
        except:
            pass

        self.view = PlayerInteractions(self.bot)

        if self.bot.tests:
            self.bot.loop.create_task(self.bot.tests.tests_start(self))

        controls = {
            "⏮️": ["back"],
            "⏹️": ["stop"],
        }

        for button, control in controls.items():
            try:
                style = control[1]
            except IndexError:
                style = disnake.ButtonStyle.grey
            self.view.add_item(disnake.ui.Button(emoji=button, custom_id=f"musicplayer_{control[0]}", style=style))

        embed = disnake.Embed(
            description=f"**Não há músicas na fila. Adicione uma música ou use um dos botões abaixo\n\n"
                        f"[O Player será desligado em: {time_format(self.idle_timeout * 1000)}]**",
            color=self.guild.me.colour
        )

        if self.static or self.text_channel.last_message_id == self.message.id:
            await self.message.edit(embed=embed, content=None, view=self.view)
        else:
            self.message = await self.text_channel.send(embed=embed, view=self.view)

        await asyncio.sleep(self.idle_timeout)
        embed = disnake.Embed(description="**O player foi desligado por inatividade...**",
                              color=disnake.Colour.dark_gold())
        self.bot.loop.create_task(self.text_channel.send(embed=embed, delete_after=15 if self.static else None))
        self.bot.loop.create_task(self.destroy())
        return

    async def invoke_np(self, force=False, interaction=None):

        if not self.current:
            return

        embed = disnake.Embed(color=self.guild.me.color)
        embed_queue = None

        if not self.paused:
            embed.set_author(
                name="Tocando Agora:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/895862881105616947/music_equalizer.gif"
            )
        else:
            embed.set_author(
                name="Em Pausa:",
                icon_url="https://cdn.discordapp.com/attachments/480195401543188483/896013933197013002/pause.png"
            )

        embed.set_footer(
            text=f"Modo do player: {self.music_core}",
            icon_url="https://cdn.discordapp.com/attachments/480195401543188483/907119505971486810/speaker-loud-speaker.gif"
        )

        if self.current.is_stream:
            duration = "🔴 **⠂Livestream**"
        else:
            duration = f"⏰ **⠂Duração:** `{time_format(self.current.duration)}`"

        txt = f"[**{self.current.title}**]({self.current.uri})\n\n" \
              f"> {duration}\n" \
              f"> 💠 **⠂Uploader**: `{self.current.author}`\n" \
              f"> 🎧 **⠂Pedido por:** {self.current.requester.mention}\n" \
              f"> 🔊 **⠂Volume:** `{self.volume}%`"

        if self.current.repeats:
            txt += f"\n> 🔂 **⠂Repetições restantes:** `{self.current.repeats}`"

        if self.current.playlist:
            txt += f"\n> 📑 **⠂Playlist:** [`{fix_characters(self.current.playlist['name'], limit=17)}`]({self.current.playlist['url']})"

        txt += "\n"

        if self.command_log:
            txt += f"```ldif\nUltima Interação:```{self.command_log}\n"

        if len(self.queue):

            char_limit = 26 if not self.static else 33

            queue_txt = "\n".join(
                f"`{n + 1}) [{time_format(t.duration) if t.duration else '🔴 Livestream'}]` [`{fix_characters(t.title, char_limit)}`]({t.uri})"
                for n, t
                in (enumerate(itertools.islice(self.queue, (20 if self.static else 3))))
            )

            if not self.static:

                txt += f"```ldif\nPróximas Músicas:``` {queue_txt}"

                if (qsize := len(self.queue)) > 3:
                    txt += f"\n\n`E mais {qsize - 3}" + (f" |` {self.msg_ad}" if self.msg_ad else " músicas`")
                else:
                    txt += f"\n\n{self.msg_ad}" if self.msg_ad else ""

            else:

                embed_queue = disnake.Embed(title=f"Músicas na fila:", color=self.guild.me.color,
                                            description=f"\n{queue_txt}")
                if (qsize := len(self.queue)) > 20:
                    embed_queue.description += f"\n\nE mais **{qsize - 20}** músicas."
                txt += f"\n{self.msg_ad}" if self.msg_ad else ""

        else:
            txt += f"\n{self.msg_ad}" if self.msg_ad else ""

        embed.description = txt

        if self.static:
            embed.set_image(url=self.current.thumb)
        else:
            embed.set_image(
                url="https://cdn.discordapp.com/attachments/480195401543188483/795080813678559273/rainbow_bar2.gif")
            embed.set_thumbnail(url=self.current.thumb)

        if self.bot.tests:
            self.bot.loop.create_task(self.bot.tests.tests_start(self))

        embeds = [embed_queue, embed] if embed_queue else [embed]

        try:
            if self.message and embeds == self.last_embed and (self.static or self.is_last_message()):
                try:
                    await interaction.response.defer()
                except:
                    pass
                self.cancel_message_task_update()
                return
        except:
            pass

        try:
            self.view.stop()
        except:
            pass

        self.view = PlayerInteractions(self.bot)

        controls = {
            "⏯️": ["playpause", get_button_style(self.paused)],
            "⏮️": ["back"],
            "⏭️": ["skip"],
            "🔀": ["shuffle"],
            "🇳": ["nightcore", get_button_style(self.nightcore, red=False)],
            "⏹️": ["stop"],
            ("🔂" if self.loop == "current" else "🔁"): [
                "loop_mode", disnake.ButtonStyle.grey
                if not self.loop else disnake.ButtonStyle.blurple
                if self.loop == "current"
                else disnake.ButtonStyle.green
            ],
            "🔊": ["volume"],
            "📑": ['queue'],
            "ℹ️": ["help"]
        }

        for button, control in controls.items():
            try:
                style = control[1]
            except IndexError:
                style = disnake.ButtonStyle.grey
            self.view.add_item(disnake.ui.Button(emoji=button, custom_id=f"musicplayer_{control[0]}", style=style))

        if self.message and (self.static or not force or self.is_last_message()):
            try:
                if interaction and not interaction.response.is_done():
                    await interaction.response.edit_message(embeds=embeds, view=self.view)
                else:
                    try:
                        await interaction.response.defer()
                    except:
                        pass
                    try:
                        await self.message.edit(embeds=embeds, view=self.view)
                    except:
                        if not self.bot.get_channel(self.text_channel.id):
                            await self.destroy(force=True)  # canal não existe mais no servidor...
                self.cancel_message_task_update()
                return
            except:
                traceback.print_exc()
                pass

        await self.destroy_message(destroy_view=False)

        self.last_embed = embeds

        self.message = await self.text_channel.send(embeds=embeds, view=self.view)

        self.cancel_message_task_update()

    async def destroy_message(self, destroy_view=True):

        if destroy_view:

            try:
                self.view.stop()
            except:
                pass

            self.view = None
        if not self.static:
            try:
                await self.message.delete()
            except:
                pass

        self.last_embed = None

        self.message = None

    def is_last_message(self):

        try:
            return self.text_channel.last_message_id == self.message.id
        except AttributeError:
            return

    def cancel_message_task_update(self):

        try:
            self.updating_message.cancel()
        except:
            pass
        self.updating_message = None

    async def update_message_task(self, interaction=None, force=False):

        if not interaction and not force:
            await asyncio.sleep(5)

        try:
            await self.invoke_np(interaction=interaction)
        except:
            traceback.print_exc()

    async def update_message(self, interaction: disnake.Interaction = None, force=False):

        if self.updating_message:

            if interaction and not interaction.response.is_done():
                await interaction.response.defer()
            return

        self.updating_message = self.bot.loop.create_task(
            self.update_message_task(interaction=interaction, force=force))

    async def process_next(self):

        if self.locked:
            return False

        try:
            track = self.queue.popleft()
        except Exception:
            self.idle = self.bot.loop.create_task(self.idling_mode())
            return False

        if not track:
            return False

        try:
            self.idle.cancel()
        except:
            pass

        if isinstance(track, SpotifyTrack):

            self.locked = True

            await track.resolve(self.node)

            self.locked = False

            if not track.info.get('ie_key') and not track.id:
                return await self.process_next()

        self.last_track = track

        return track

    async def cleanup(self):

        try:
            self.idle.cancel()
        except:
            pass

        if self.static:
            try:
                await self.cog.send_idle_embed(self.message, self.command_log)
            except:
                pass

        try:
            await self.destroy_message()
        except:
            pass

        if self.bot.tests:
            self.current = None
            await self.bot.tests.tests_start(self, close=True)

    async def track_end(self):

        self.votes.clear()

        self.locked = True

        await asyncio.sleep(0.5)

        if self.last_track:

            if self.loop == "queue":
                if self.is_previows_music:
                    self.queue.insert(1, self.last_track)
                    self.is_previows_music = False
                else:
                    self.queue.append(self.last_track)
            elif self.loop == "current":
                self.queue.appendleft(self.last_track)
            elif self.is_previows_music:
                self.queue.insert(1, self.last_track)
                self.is_previows_music = False
            elif self.last_track.repeats:
                self.last_track.repeats -= 1
                self.queue.insert(0, self.last_track)
            else:
                self.played.append(self.last_track)

        elif self.is_previows_music:
            self.is_previows_music = False

        try:
            self.updating_message.cancel()
        except:
            pass

        self.locked = False


class YTDLPlayer(BasePlayer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current = None
        self.channel_id = kwargs.pop('channel_id', None)
        self.bot: BotCore = kwargs.pop('bot')
        self.event = asyncio.Event()
        self.exiting = False
        self.locked = False
        self.vc: Optional[disnake.VoiceClient] = None
        self.volume = 100
        self.start_time: Optional[datetime.datetime] = disnake.utils.utcnow()
        self.music_core = "YT-DLP (Experimental)"

    @property
    def position(self):

        try:
            return (disnake.utils.utcnow() - self.start_time).total_seconds() * 1000
        except:
            return 0

    async def set_pause(self, pause: bool):

        if pause:
            self.vc.pause()
            self.paused = True
        else:
            self.vc.resume()
            self.paused = False

    async def update_filters(self):
        # quebra-galho
        self.nightcore = False
        self.queue.appendleft(self.current)
        self.last_track = None
        self.current = None
        await self.stop()

    async def set_timescale(self, *args, **kwargs):
        # quebra-galho
        self.nightcore = True
        self.queue.appendleft(self.current)
        self.last_track = None
        self.current = None
        await self.stop()

    async def set_volume(self, vol: int):

        if self.vc and self.vc.source:
            self.vc.source.volume  = vol / 100
        self.volume = vol

    async def connect(self, channel_id: int, self_deaf: bool = False):

        self.channel_id = channel_id

        if not self.vc:
            if not self.guild.me.voice:
                await self.bot.get_channel(channel_id).connect()
            self.vc = self.guild.voice_client
            return

        channel = self.bot.get_channel(channel_id)

        if self.guild.me.voice and self.guild.me.voice.channel.id != channel_id:
            await self.vc.move_to(channel)
        else:
            await channel.connect(cls=self.vc, reconnect=True)
        self.vc = self.guild.voice_client

    async def seek(self, position: int):
        # não implementado ainda...
        raise GenericError("O sistema de avançar/voltar música ainda não foi implementado para o modo: YoutubeDL.")

    @property
    def is_connected(self)  -> bool:
        return self.vc is not None

    @property
    def is_paused(self) -> bool:
        return self.is_connected and self.vc.is_paused()

    async def destroy(self, force=True):

        self.exiting = True

        try:
            if self.guild.me.voice:
                await self.guild.voice_client.disconnect(force=force)
            elif self.guild.me.voice_client:
                self.guild.me.voice_client.cleanup()
        except AttributeError:
            pass

        await self.cleanup()

        try:
            del self.bot.music.players[self.guild.id]
        except:
            pass

    async def renew_url(self, track: Union[YTDLTrack, SpotifyTrack]) -> Union[YTDLTrack, SpotifyTrack]:

        url = track.info['url'] if isinstance(track, SpotifyTrack) else track.uri

        to_run = partial(self.bot.ytdl.extract_info, url=url, download=False)
        info = await self.bot.loop.run_in_executor(None, to_run)

        track.id = info['formats'][0]['url']
        return track

    async def process_track(self):

        self.event.clear()

        if self.exiting:
            return

        track: YTDLTrack = await super().process_next()

        if track is False or self.locked:
            return

        await self.bot.wait_until_ready()

        self.locked = True

        if not track.id:

            try:
                track = await self.renew_url(track)
            except Exception as e:
                traceback.print_exc()
                try:
                    await self.text_channel.send(embed=disnake.Embed(
                        description=f"**Ocorreu um erro durante a reprodução da música:\n[{self.current['title']}]({self.current['webpage_url']})** ```css\n{e}\n```",
                        color=disnake.Colour.red()))
                except:
                    pass
                await asyncio.sleep(6)
                self.locked = False
                await self.process_next()
                return

        self.current = track
        self.last_track = track

        FFMPEG_OPTIONS = {
            'before_options': '-nostdin'
                              ' -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }

        if self.nightcore:
            FFMPEG_OPTIONS['options'] += (f" -af \"{filters['nightcore']}\"")

        source = await YTDLSource.source(track.id, ffmpeg_opts=FFMPEG_OPTIONS)
        source.volume = self.volume / 100

        self.vc.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.event.set))

        self.start_time = disnake.utils.utcnow()

        try:
            await self.invoke_np()
        except:
            traceback.print_exc()

        self.locked = False

        self.command_log = ""

        await self.event.wait()

        source.cleanup()

        self.current = None

        await self.track_end()

        await self.process_next()

    async def stop(self):
        self.vc.stop()

    async def process_next(self):
        self.bot.loop.create_task(self.process_track())

    # temp workaround for spotify
    @property
    def node(self):
        return self

    async def get_tracks(self, query: str):
        return await self.bot.music.get_tracks(query)


class LavalinkPlayer(BasePlayer, wavelink.Player):

    def __init__(self, *args, **kwargs):
        super(LavalinkPlayer, self).__init__(*args, **kwargs)
        self.queue = deque()
        self.played = deque(maxlen=20)
        self.nightcore = False
        self.loop = False
        self.last_track: Optional[LavalinkTrack] = None
        self.locked = False
        self.idle = None
        self.idle_timeout = 180  # aguardar 3 minutos para adicionar novas músicas
        self.is_previows_music = False
        self.updating_message = None
        self.command_log = ""
        self.last_embed = None
        self.interaction_cooldown = False
        self.vc = WavelinkVoiceClient(self.bot, self.requester.voice.channel, self)
        self.votes = set()
        self.msg_ad = self.bot.config.get("link")
        self.view: Optional[disnake.ui.View] = None
        self.music_core = "Lavalink"

    async def process_next(self):

        track = await super().process_next()

        if track is False:
            return

        await self.play(track)

        self.locked = False

    async def connect(self, channel_id: int, self_deaf: bool = False):

        if not self.vc:
            if not self.guild.me.voice:
                await super().connect(channel_id, self_deaf)
            return

        self.channel_id = channel_id

        channel = self.bot.get_channel(channel_id)

        await super().connect(channel_id, self_deaf)

        if self.guild.me.voice and self.guild.me.voice.channel.id != channel_id:
            await self.vc.move_to(channel)
        else:
            await channel.connect(cls=self.vc, reconnect=True)

    async def destroy(self, *, force: bool = False):

        try:
            await self.vc.disconnect(force=True)
        except:
            pass

        await self.cleanup()

        await super().destroy(force=force)


    #######################
    #### Filter Stuffs ####
    #######################

    async def change_node(self, identifier: str = None):
        await super().change_node()
        await self.node._send(op="filters", **self.filters, guildId=str(self.guild_id))

    async def set_volume(self, vol: int) -> None:

        self.volume = max(min(vol, 1000), 0)
        await self.node._send(op='volume', guildId=str(self.guild_id), volume=self.volume)


    async def set_distortion(self, sin_offset: float = 0, sin_scale: float = 1.0, cos_offset: float = 0,
                             cos_scale: float = 1.0, tan_offset: float = 0, tan_scale: float = 1.0,
                             offset: float = 0, scale: float = 1.0, enabled: bool = True):

        if enabled:
            return await self.set_filter(
                AudioFilter.distortion(sin_offset, sin_scale, cos_offset, cos_scale, tan_offset, tan_scale, offset,
                                       scale))

        try:
            del self.filters['distortion']
        except KeyError:
            pass

        await self.update_filters()

    async def set_timescale(self, speed: float = 1.0, pitch: float = 1.0, rate: float = 1.0, enabled: bool = True):
        if enabled:
            return await self.set_filter(AudioFilter.timescale(speed=speed, pitch=pitch, rate=rate))

        try:
            del self.filters['timescale']
        except KeyError:
            pass

        await self.update_filters()

    async def set_karaoke(self, level: float = 1.0, mono_level: float = 1.0, filter_band: float = 220.0,
                          filter_width: float = 100.0, enabled: bool = True):
        if enabled:
            return await self.set_filter(
                AudioFilter.karaoke(level=level, mono_level=mono_level, filter_band=filter_band,
                                    filter_width=filter_width))

        try:
            del self.filters['karaoke']
        except KeyError:
            pass

        await self.update_filters()

    async def set_tremolo(self, frequency: float = 2.0, depth: float = 0.0, enabled: bool = True):
        if enabled:
            return await self.set_filter(AudioFilter.tremolo(frequency=frequency, depth=depth))

        try:
            del self.filters['tremolo']
        except KeyError:
            pass

        await self.update_filters()

    async def set_vibrato(self, frequency: float = 2.0, depth: float = 0.0, enabled: bool = True):
        if enabled:
            return await self.set_filter(AudioFilter.vibrato(frequency=frequency, depth=depth))

        try:
            del self.filters['vibrato']
        except KeyError:
            pass

        await self.update_filters()

    async def set_rotation(self, sample_rate: int = 5, enabled: bool = True):
        if enabled:
            return await self.set_filter(AudioFilter.rotation(sample_rate=sample_rate))

        try:
            del self.filters['rotation']
        except KeyError:
            pass

        await self.update_filters()

    async def set_lowpass(self, smoothing: float = 20.0, enabled: bool = True):
        if enabled:
            return await self.set_filter(AudioFilter.low_pass(smoothing=smoothing))

        try:
            del self.filters['lowpass']
        except KeyError:
            pass

        await self.update_filters()

    async def set_channelmix(self, left_to_left: float = 1.0, left_to_right: float = 0, right_to_left: float = 0,
                             right_to_right: float = 1.0, enabled: bool = True):
        if enabled:
            return await self.set_filter(
                AudioFilter.channel_mix(left_to_left=left_to_left, left_to_right=left_to_right,
                                        right_to_left=right_to_left, right_to_right=right_to_right))

        try:
            del self.filters['channelmix']
        except KeyError:
            pass

        await self.update_filters()

    async def set_eq(self, equalizer: wavelink.Equalizer):

        await self.set_filter(AudioFilter.equalizer(bands=equalizer.eq))
        self._equalizer = equalizer

    async def update_filters(self):
        await self.node._send(op="filters", **self.filters, guildId=str(self.guild_id))

    async def set_filter(self, filter_type: AudioFilter):

        self.filters.update(filter_type.filter)
        await self.update_filters()

        return filter_type


class YTDLManager:

    def __init__(self, *, bot: BotCore):
        bot.ytdl = YoutubeDL(YDL_OPTIONS)
        self.bot = bot
        self.players = {}
        self.identifier = "YoutubeDL"

    def get_player(self, guild_id: int, *args, **kwargs):

        try:
            player = self.players[guild_id]
        except KeyError:
            pass
        else:
            return player

        kwargs['bot'] = self.bot

        player = YTDLPlayer(*args, **kwargs)
        self.players[guild_id] = player
        return player

    #testes
    def get_best_node(self):
        return self

    async def get_tracks(self, query: str):

        to_run = partial(self.bot.ytdl.extract_info, url=query, download=False)
        info = await self.bot.loop.run_in_executor(None, to_run)

        try:

            data = {
                'loadType': 'PLAYLIST_LOADED',
                'playlistInfo': {'name': '', 'selectedTrack': -1},
                'tracks': []
            }

            data["playlistInfo"]["name"] = info.pop('title')
            data["tracks"] = info["entries"]

            playlist = {"name": data["playlistInfo"]["name"], "url": info.pop('webpage_url', query)}

            info['url'] = query
            return YTDLPlaylist(data, playlist=playlist)
        except KeyError:
            entries = [info]

        if query.startswith(("ytsearch:", "scsearch:")):
            entries = entries[:1]

        tracks = []

        for t in entries:

            if not t.get('duration'):
                continue

            tracks.append(
                YTDLTrack(data=t)
            )

        return tracks


def music_mode(bot: BotCore):

    if bot.config.get("youtubedl"):
        return YTDLManager(bot=bot)
    else:
        return wavelink.Client(bot=bot)