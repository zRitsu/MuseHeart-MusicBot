import disnake
import asyncio
import wavelink
from typing import Union, Optional
from collections import deque
from .converters import fix_characters, time_format, get_button_style
from .filters import AudioFilter
from .interactions import PlayerInteractions
from .spotify import SpotifyTrack
import itertools
import traceback


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
        self.wavelink: wavelink.Client = self.bot.wavelink
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


class CustomTrack(wavelink.Track):

    def __init__(self, *args, **kwargs):
        self.requester = kwargs.pop('requester')
        self.playlist = kwargs.pop('playlist', None)
        args[1]['title'] = fix_characters(args[1]['title'])
        super().__init__(*args, **kwargs)
        if self.ytid:
            self.thumb = f"https://img.youtube.com/vi/{self.ytid}/mqdefault.jpg"
        elif "soundcloud.com" in self.uri:
            self.thumb = self.info.get("artworkUrl", "").replace('large.jpg', 't500x500.jpg')
        else:
            self.thumb = self.info.get("artworkUrl", "")


class CustomPlayer(wavelink.Player):

    def __init__(self, *args, **kwargs):

        requester = kwargs.pop('requester')

        self.guild = kwargs.pop('guild')
        self.text_channel: disnake.TextChannel = kwargs.pop('channel')
        self.dj = [] if requester.guild_permissions.manage_channels else [requester]
        self.message: Optional[disnake.Message] = kwargs.pop('message', None)
        self.static = kwargs.pop('static', False)
        self.cog = kwargs.pop('cog')
        self.filters = {}
        super().__init__(*args, **kwargs)
        self.queue = deque()
        self.played = deque(maxlen=20)
        self.nightcore = False
        self.loop = False
        self.last_track: Optional[CustomTrack] = None
        self.locked = False
        self.idle = None
        self.idle_timeout = 180  # aguardar 3 minutos para adicionar novas músicas
        self.is_previows_music = False
        self.updating_message = None
        self.command_log = ""
        self.last_embed = None
        self.interaction_cooldown = False
        self.vc = WavelinkVoiceClient(self.bot, requester.voice.channel, self)
        self.votes = set()
        self.msg_ad = self.bot.config.get("link")

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
            self.idle.cancel()
        except:
            pass

        if self.static:
            await self.cog.send_idle_embed(self.message, self.command_log)

        try:
            await self.destroy_message()
        except:
            pass

        if self.vc:
            try:
                await self.vc.disconnect(force=True)
            except:
                pass

        if self.bot.tests:
            self.current = None
            self.bot.loop.create_task(self.bot.tests.tests_start(self))

        await super().destroy()

    async def idling_mode(self):

        self.view.stop()

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

    async def process_next(self):

        if self.locked:
            return

        try:
            track = self.queue.popleft()
        except:
            self.idle = self.bot.loop.create_task(self.idling_mode())
            return

        if not track:
            return

        try:
            self.idle.cancel()
        except:
            pass

        self.locked = True

        if isinstance(track, SpotifyTrack):

            await track.resolve(self.node)

            if not track.id:
                return await self.process_next()

        self.last_track = track

        await self.play(track)

        self.locked = False

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

        if self.current.is_stream:
            duration = "🔴 **⠂Livestream**"
        else:
            duration = f"⏰ **⠂Duração:** `{time_format(self.current.duration)}`"

        txt = f"[**{self.current.title}**]({self.current.uri})\n\n" \
              f"> {duration}\n" \
              f"> 💠 **⠂Uploader**: `{self.current.author}`\n" \
              f"> 🎧 **⠂Pedido por:** {self.current.requester.mention}\n" \
              f"> 🔊 **⠂Volume:** `{self.volume}%`"

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

                embed_queue = disnake.Embed(title=f"Músicas na fila:", color=self.guild.me.color, description=f"\n{queue_txt}")
                if (qsize := len(self.queue)) > 20:
                    embed_queue.description += f"\n\nE mais **{qsize - 20}** músicas."
                txt += f"\n{self.msg_ad}" if self.msg_ad else ""

        else:
            txt += f"\n{self.msg_ad}" if self.msg_ad else ""

        embed.description = txt

        if self.static:
            embed.set_image(url=self.current.thumb)
        else:
            embed.set_image(url="https://cdn.discordapp.com/attachments/480195401543188483/795080813678559273/rainbow_bar2.gif")
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
                "loop", disnake.ButtonStyle.grey
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
                        await self.message.edit(embeds=embeds, view=self.view)
                    except:
                        pass
                return
            except:
                traceback.print_exc()
                pass

        await self.destroy_message(destroy_view=False)

        self.last_embed = embeds

        self.message = await self.text_channel.send(embeds=embeds, view=self.view)


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

    async def update_message_task(self, interaction=None, force=False):

        if not interaction and not force:
            await asyncio.sleep(5)

        try:
            await self.invoke_np(interaction=interaction)
        except:
            traceback.print_exc()

        self.updating_message = None

    async def update_message(self, interaction: disnake.Interaction=None, force=False):

        if self.updating_message:

            if interaction and not interaction.response.is_done():
                await interaction.response.defer()
            return

        self.updating_message = self.bot.loop.create_task(self.update_message_task(interaction=interaction, force=force))

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