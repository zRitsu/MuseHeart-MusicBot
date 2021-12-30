from __future__ import annotations

import datetime
import json
import pprint

import disnake
import asyncio
import wavelink
from urllib import parse
from yt_dlp import YoutubeDL
from functools import partial
from .converters import fix_characters, time_format, get_button_style
from .filters import AudioFilter
from .interactions import PlayerInteractions
from .spotify import SpotifyTrack
import traceback
from collections import deque
from typing import Optional, Union, TYPE_CHECKING
if TYPE_CHECKING:
    from ..client import BotCore


audioformats = ["mp3", "ogg", "m4a", "webm", "mp4"]

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'retries': 5,
    'extract_flat': 'in_playlist',
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

    __slots__ = ('requester', 'playlist', 'track_loops', 'album')

    def __init__(self, *args, **kwargs):
        self.requester = kwargs.pop('requester')
        self.playlist = kwargs.pop('playlist', None)
        self.track_loops = kwargs.pop('track_loops', 0)
        self.album = {}
        args[1]['title'] = fix_characters(args[1]['title'])
        super().__init__(*args, **kwargs)

        if self.ytid:
            self.thumb = f"https://img.youtube.com/vi/{self.ytid}/mqdefault.jpg"
        elif "soundcloud.com" in self.uri:
            self.thumb = self.info.get("artworkUrl", "").replace('large.jpg', 't500x500.jpg')
        else:
            self.thumb = self.info.get("artworkUrl", "")

        if self.info.get("class") == "YoutubeAudioTrack" and self.playlist:
            self.uri = f"{self.uri}&list={parse.parse_qs(parse.urlparse(self.playlist['url']).query)['list'][0]}"


class YTDLPlaylist:

    __slots__ = ('data', 'tracks')

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

    __slots__ = ('author', 'id', 'title', 'uri', 'duration', 'is_stream', 'info',
                 'requester', 'playlist', 'album', 'track_loops', 'thumb')

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
        self.album = {}
        self.track_loops = kwargs.pop('track_loops', 0)

        if (data.get("ie_key") or data.get('extractor_key')) == "Youtube":
            self.thumb = f"https://img.youtube.com/vi/{data['id']}/mqdefault.jpg"
        else:
            self.thumb = data.get('thumbnail', '')

class BasePlayer:

    bot: BotCore
    volume: int
    node: wavelink.Node
    vc: disnake.VoiceProtocol
    paused: bool
    position: int
    is_paused: bool

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
        self.request_channel: bool = kwargs.pop("request_channel", False)
        self.cog = kwargs.pop('cog')
        self.filters = {}
        self.queue = deque()
        self.played = deque(maxlen=20)
        self.nightcore = False
        self.loop = False
        self.last_track: Union[LavalinkTrack, YTDLTrack] = None
        self.locked = False
        self.idle_task = None
        self.members_timeout_task = None
        self.idle_timeout = self.cog.bot.config["IDLE_TIMEOUT"]
        self.is_previows_music = False
        self.updating_message = None
        self.command_log = ""
        self.last_data = None
        self.interaction_cooldown = False
        self.votes = set()
        self.view: Optional[disnake.ui.View] = None
        self.current: Union[LavalinkTrack, SpotifyTrack, YTDLTrack] = None
        self.view: Optional[disnake.ui.View] = None
        self.seek_time = None
        self.exiting = False
        self.skin = self.cog.bot.player_skins[kwargs.pop("skin", self.cog.bot.default_skin)]
        self.has_thread: bool = False
        self.nonstop = False


    async def members_timeout(self):

        await asyncio.sleep(self.idle_timeout)
        msg = f"O player foi desligado por falta de membros no canal <#{self.vc.channel.id if self.vc else ''}>..."
        if self.static:
            self.command_log = msg
        else:
            embed = disnake.Embed(description=msg, color=self.bot.get_color(self.guild.me))
            self.bot.loop.create_task(self.text_channel.send(embed=embed))
        await self.destroy()

    async def idling_mode(self):

        try:
            self.view.stop()
        except:
            pass

        self.view = PlayerInteractions(self.bot)

        self.bot.loop.create_task(self.process_rpc(self.vc.channel))

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
            color=self.bot.get_color(self.guild.me)
        )

        if self.has_thread or self.static or self.text_channel.last_message_id == self.message.id:
            await self.message.edit(embed=embed, content=None, view=self.view)
        else:
            try:
                await self.message.delete()
            except:
                pass
            self.message = await self.text_channel.send(embed=embed, view=self.view)

        await asyncio.sleep(self.idle_timeout)

        msg =  "**O player foi desligado por inatividade...**"

        if self.static:
            self.command_log = msg
        else:
            embed = disnake.Embed(description=msg, color=self.bot.get_color(self.guild.me))
            self.bot.loop.create_task(self.text_channel.send(embed=embed))

        self.bot.loop.create_task(self.destroy())

    async def invoke_np(self, force=False, interaction=None):

        if not self.current:
            return

        data = self.skin(self)

        try:
            if self.message and data == self.last_data and (self.has_thread or self.static or self.is_last_message()):
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

        if self.message and (self.has_thread or self.static or not force or self.is_last_message()):
            try:
                if interaction and not interaction.response.is_done():
                    await interaction.response.edit_message(view=self.view, **data)
                else:
                    try:
                        await interaction.response.defer()
                    except:
                        pass
                    try:
                        await self.message.edit(view=self.view, **data)
                    except:
                        if not self.bot.get_channel(self.text_channel.id):
                            await self.destroy(force=True)  # canal não existe mais no servidor...
                self.cancel_message_task_update()
                return
            except:
                traceback.print_exc()
                pass

        await self.destroy_message(destroy_view=False)

        self.last_data = data

        self.message = await self.text_channel.send(view=self.view, **data)

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

        self.last_data = None

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

        self.bot.loop.create_task(self.process_rpc(self.vc.channel))

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
            self.last_track = None
            self.idle_task = self.bot.loop.create_task(self.idling_mode())
            return False

        if not track:
            return False

        try:
            self.idle_task.cancel()
            self.idle_task = None
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
            self.idle_task.cancel()
        except:
            pass

        try:
            self.members_timeout_task.cancel()
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

        self.queue.clear()
        self.played.clear()

        self.bot.loop.create_task(self.process_rpc(self.vc.channel, close=True))

    async def process_rpc(
            self,
            voice_channel: Union[disnake.VoiceChannel, disnake.StageChannel],
            close = False,
            user: disnake.Member = None
    ):

        if close:

            data = {
                "op": "close",
                "bot_id": self.bot.user.id,
                "public": True
            }

            if user:
                try:
                    data["user"] = user.id
                    self.bot.ws_users[user.id]["ws"].write_message(json.dumps(data))
                    return
                except KeyError:
                    return

            for m in voice_channel.members:

                if m.bot:
                    continue

                try:
                    user_ws = self.bot.ws_users[m.id]["ws"]
                except KeyError:
                    continue

                data["user"] = m.id

                try:
                    user_ws.write_message(json.dumps(data))
                except Exception:
                    traceback.print_exc()

        if self.exiting:
            return

        vc_members = [m for m in voice_channel.members if not m.bot and (not m.voice.deaf or not m.voice.self_deaf)]

        stats = {
            "op": "update",
            "track": None,
            "bot_id": self.bot.user.id,
            "public": True,
            "info": {
                "members": len(vc_members),
                "channel": {
                    "name": voice_channel.name,
                    "id": voice_channel.id
                },
                "guild": {
                    "name": voice_channel.guild.name,
                    "id": voice_channel.guild.id
                }
            }
        }

        try:
            stats["thumb"] = self.bot.user.avatar.with_format("png").url
        except AttributeError:
            stats["thumb"] = self.bot.user.default_avatar.with_format("png").url

        if not self.current:

            stats.update(
                {
                    "op": "idle",
                    "bot_id": self.bot.user.id,
                    "public": True,
                }
            )

        else:

            track: Optional[LavalinkTrack, YTDLTrack, SpotifyTrack] = self.current

            stats["thumb"] = track.thumb

            stats["track"] = {
                "title": track.title,
                "url": track.uri,
                "author": track.author,
                "duration": track.duration,
                "stream": track.is_stream,
                "position": self.position,
                "paused": self.is_paused,
                "loop": self.current.track_loops or self.loop
            }

            if track.playlist:
                stats["track"].update(
                    {
                        "playlist_name": track.playlist['name'],
                        "playlist_url": track.playlist['url'],
                    }
                )

            if track.album:
                stats["track"].update(
                    {
                        "album_name": track.album['name'],
                        "album_url": track.album['url'],
                    }
                )

        if user:
            stats["user"] = user.id
            self.bot.ws_users[user.id]["ws"].write_message(json.dumps(stats))

        else:
            for m in vc_members:
                try:
                    if stats == self.bot.ws_users[m.id]["last"]:
                        continue
                    stats["user"] = m.id
                    self.bot.ws_users[m.id]["ws"].write_message(json.dumps(stats))
                    self.bot.ws_users[m.id]["last"] = stats
                except KeyError:
                    pass

    async def track_end(self):

        self.votes.clear()

        self.locked = True

        await asyncio.sleep(0.5)

        if self.last_track:

            if self.loop == "current":
                self.queue.appendleft(self.last_track)
            elif self.is_previows_music:
                self.queue.insert(1, self.last_track)
                self.is_previows_music = False
            elif self.last_track.track_loops:
                self.last_track.track_loops -= 1
                self.queue.insert(0, self.last_track)
            elif self.loop == "queue" or self.nonstop:
                if self.is_previows_music:
                    self.queue.insert(1, self.last_track)
                    self.is_previows_music = False
                else:
                    self.queue.append(self.last_track)
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
        self.locked = False
        self.vc: Optional[disnake.VoiceClient] = None
        self.volume = 100
        self.start_time: Optional[datetime.datetime] = disnake.utils.utcnow()

    def __str__(self) -> str:
        return "YT-DLP Player (Experimental)"

    @property
    def position(self):

        try:
            return (disnake.utils.utcnow() - self.start_time).total_seconds() * 1000
        except:
            return 0

    @property
    def paused(self):
        return self.vc.is_paused()

    async def set_pause(self, pause: bool):

        if pause:
            self.vc.pause()
        else:
            self.vc.resume()

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
        elif not self.guild.voice_client:
            await channel.connect(cls=self.vc, reconnect=True)
        self.vc = self.guild.voice_client

    async def seek(self, position: int):
        self.queue.appendleft(self.current)
        self.last_track = None
        self.current = None
        self.seek_time = time_format(position)
        await self.stop()

    @property
    def is_connected(self)  -> bool:
        return self.vc is not None

    @property
    def is_paused(self) -> bool:
        return self.is_connected and self.vc.is_paused()

    async def destroy(self, force=True):

        self.exiting = True

        try:
            await self.guild.voice_client.disconnect(force=True)
        except AttributeError:
            pass

        try:
            self.vc.cleanup()
        except:
            pass

        await self.cleanup()

        try:
            del self.bot.music.players[self.guild.id]
        except KeyError:
            pass

    async def renew_url(self, track: Union[YTDLTrack, SpotifyTrack]) -> Union[YTDLTrack, SpotifyTrack]:

        url = track.info['url'] if isinstance(track, SpotifyTrack) else track.uri

        to_run = partial(self.bot.ytdl.extract_info, url=url, download=False)
        info = await self.bot.loop.run_in_executor(None, to_run)

        track.id = [f for f in info["formats"] if f["ext"] in audioformats][0]["url"]
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

        if self.seek_time:
            FFMPEG_OPTIONS['options'] += f' -ss {self.seek_time}'
            self.seek_time = None

        if self.nightcore:
            FFMPEG_OPTIONS['options'] += f" -af \"{filters['nightcore']}\""

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

        self.is_previows_music = False

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
        self.is_previows_music = False
        self.updating_message = None
        self.command_log = ""
        self.last_embed = None
        self.interaction_cooldown = False
        self.vc = WavelinkVoiceClient(self.bot, self.requester.voice.channel, self)
        self.votes = set()
        self.view: Optional[disnake.ui.View] = None

    def __str__(self) -> str:
        return f"Lavalink Player | Server: {self.node.identifier}"

    async def process_next(self):

        track = await super().process_next()

        if track is False:
            return

        await self.play(track)

        self.is_previows_music = False

        self.locked = False

    async def connect(self, channel_id: int, self_deaf: bool = False):

        if not self.vc:
            if not self.guild.me.voice:
                await super().connect(channel_id, self_deaf)
            return

        self.channel_id = channel_id

        channel = self.bot.get_channel(channel_id)

        await super().connect(channel_id, self_deaf)

        if self.guild.me.voice:
            if self.guild.me.voice.channel.id != channel_id:
                await self.vc.move_to(channel)
        else:
            await channel.connect(cls=self.vc, reconnect=True)

    async def destroy(self, *, force: bool = False):

        await self.cleanup()

        try:
            await self.vc.disconnect(force=True)
        except:
            pass

        try:
            self.vc.cleanup()
        except:
            pass

        self.exiting = True

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
        self.search = True

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

        if info.get('_type') == "playlist" and not info.get('extractor', '').endswith('search'):

            try:
                selected = int(parse.parse_qs(parse.urlparse(query).query)['index'][0]) #-1
            except:
                selected = -1

            data = {
                'loadType': 'PLAYLIST_LOADED',
                'playlistInfo': {'name': '', 'selectedTrack': selected},
                'tracks': []
            }

            data["playlistInfo"]["name"] = info.pop('title')
            data["tracks"] = info["entries"]

            playlist = {"name": data["playlistInfo"]["name"], "url": info.pop('webpage_url', query)}

            info['url'] = query
            return YTDLPlaylist(data, playlist=playlist)

        try:
            entries = info['entries']
        except:
            entries = [info]

        tracks = []

        for t in entries:

            if not t.get('duration'):
                continue

            tracks.append(
                YTDLTrack(data=t)
            )

        return tracks


def music_mode(bot: BotCore):

    if bot.config.get("YOUTUBEDL") == "true":
        return YTDLManager(bot=bot)
    else:
        return wavelink.Client(bot=bot)