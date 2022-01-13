from __future__ import annotations
import pprint
import disnake
import asyncio
import wavelink
from urllib import parse
from .converters import fix_characters, time_format, get_button_style
from .filters import AudioFilter
from .interactions import PlayerInteractions
from .spotify import SpotifyTrack
import traceback
from collections import deque
from typing import Optional, Union, TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..client import BotCore


class WavelinkVoiceClient(disnake.VoiceClient):

    # Esta classe é apenas um tapa-buraco pra versão 2.x do dpy ou outro fork atualizado.

    def __call__(self, client: BotCore, channel: disnake.VoiceChannel):
        self.client = client
        self.channel: disnake.VoiceChannel = channel
        return self

    def __init__(self, client: BotCore, channel: Union[disnake.VoiceChannel, disnake.StageChannel],
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


class LavalinkPlayer(wavelink.Player):

    bot: BotCore

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
        self.vc: Optional[WavelinkVoiceClient] = None
        self.votes = set()
        self.view: Optional[disnake.ui.View] = None
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
        self.last_track: Optional[LavalinkTrack] = None
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
        self.current: Optional[LavalinkTrack, SpotifyTrack] = None
        self.view: Optional[disnake.ui.View] = None
        self.seek_time = None
        self.exiting = False
        self.skin = self.cog.bot.player_skins[kwargs.pop("skin", self.cog.bot.default_skin)]
        self.has_thread: bool = False
        self.nonstop = False
        self.ws_client = None


    def __str__(self) -> str:
        return f"Lavalink Player | Server: {self.node.identifier}"


    async def members_timeout(self):

        await asyncio.sleep(self.idle_timeout)
        msg = f"O player foi desligado por falta de membros no canal <#{self.guild.me.voice.channel.id if self.guild.me.voice else ''}>..."
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

        self.bot.loop.create_task(self.process_rpc(self.guild.me.voice.channel))

        self.view = PlayerInteractions(self.bot)

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

        msg = "**O player foi desligado por inatividade...**"

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

    async def cleanup(self):

        vc = self.bot.get_channel(self.channel_id)

        self.bot.loop.create_task(self.process_rpc(vc, close=True))

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

    async def process_rpc(
            self,
            voice_channel: Optional[disnake.VoiceChannel, disnake.StageChannel] = None,
            close=False,
            users: List[disnake.Member] = None
    ):

        if not voice_channel:
            voice_channel = self.bot.get_channel(self.channel_id)
            if not voice_channel:
                return

        try:
            thumb = self.bot.user.avatar.with_format("png").url
        except AttributeError:
            thumb = self.bot.user.default_avatar.with_format("png").url

        if close:

            stats = {
                "op": "close",
                "bot_id": self.bot.user.id,
                "thumb": thumb,
                "users": [u.id for u in users or voice_channel.members]
            }

            try:
                await self.bot.ws_client.send(stats)
            except Exception:
                traceback.print_exc()
            return

        if self.exiting:
            return

        stats = {
            "op": "update",
            "track": None,
            "bot_id": self.bot.user.id,
            "users": [m.id for m in (users or voice_channel.members) if not m.bot],
            "thumb": thumb,
            "info": {
                "channel": {
                    "name": voice_channel.name,
                    "id": voice_channel.id
                },
                "guild": {
                    "name": voice_channel.guild.name,
                    "id": voice_channel.guild.id,
                    "vc_url": f"http://discordapp.com/channels/{self.guild_id}/{self.channel_id}"
                }
            }
        }

        try:
            stats["info"]["guild"]["icon"] = self.guild.icon.with_static_format("png").url
        except AttributeError:
            pass

        if not self.current:

            stats.update(
                {
                    "op": "idle",
                    "bot_id": self.bot.user.id,
                    "public": (await self.bot.application_info()).bot_public
                }
            )

        else:

            track: Optional[LavalinkTrack, SpotifyTrack] = self.current

            stats["thumb"] = track.thumb

            stats["track"] = {
                "title": track.title,
                "url": track.uri,
                "author": track.author,
                "duration": track.duration,
                "stream": track.is_stream,
                "position": self.position,
                "paused": self.is_paused,
                "loop": self.current.track_loops or self.loop,
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

        await self.bot.ws_client.send(stats)

    async def track_end(self):

        self.votes.clear()

        self.locked = True

        try:
            self.updating_message.cancel()
        except:
            pass

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

        self.locked = False

    async def process_next(self):

        if self.locked:
            return

        try:
            track = self.queue.popleft()
        except Exception:
            self.last_track = None
            self.idle_task = self.bot.loop.create_task(self.idling_mode())
            return

        if not track:
            return

        try:
            self.idle_task.cancel()
            self.idle_task = None
        except:
            pass

        if isinstance(track, SpotifyTrack):

            self.locked = True

            await track.resolve(self.node)

            self.locked = False

            if not track.id:
                return await self.process_next()

        self.last_track = track

        await self.play(track)

        self.bot.loop.create_task(self.process_rpc())

        self.is_previows_music = False

        self.locked = False

    async def connect(self, channel_id: int, self_deaf: bool = False):

        self.channel_id = channel_id

        channel = self.bot.get_channel(channel_id)

        if not self.vc:
            self.vc = WavelinkVoiceClient(self.bot, channel, self)

        if not self.guild.me.voice:
            await channel.connect(cls=self.vc, reconnect=True)

        elif self.guild.me.voice.channel.id != channel_id:
            await self.vc.move_to(channel)

        await super().connect(channel_id, self_deaf)

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
        await super().change_node(identifier=identifier)
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


def music_mode(bot: BotCore):
    return wavelink.Client(bot=bot)