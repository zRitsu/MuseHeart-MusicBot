# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import datetime
import itertools
import pprint
import random
import re
import traceback
import uuid
from collections import deque
from contextlib import suppress
from itertools import cycle
from time import time
from typing import Optional, Union, TYPE_CHECKING, List
from urllib import parse
from urllib.parse import quote

import disnake
from rapidfuzz import fuzz

import wavelink
from utils.db import DBModel
from utils.music.checks import can_connect
from utils.music.converters import fix_characters, time_format, get_button_style
from utils.music.errors import GenericError, PoolException
from utils.music.filters import AudioFilter
from utils.music.skin_utils import skin_converter
from utils.others import music_source_emoji, send_idle_embed, PlayerControls, song_request_buttons
from wavelink import TrackStart, TrackEnd

if TYPE_CHECKING:
    from utils.client import BotCore

exclude_tags = ["remix", "edit", "extend", "compilation", "mashup", "mixed"]
exclude_tags_2 = ["extend", "compilation", "mashup", "nightcore", "8d", "mixed"]
emoji_pattern = re.compile('<a?:.+?:\d+?>')

thread_archive_time = {
    60: 30,
    24: 720,
    2880: 720,
    10080: 2880,
}

providers_dict = {
    "youtube": "ytmsearch",
    "soundcloud": "scsearch",
    "applemusic": "amsearch",
    "deezer": "dzsearch",
    "spotify": "spsearch",
    "tidal": "tdsearch",
}

native_sources = {"http", "youtube", "soundcloud", "tts", "reddit", "ocremix", "tiktok", "mixcloud", "soundgasm", "flowerytts", "vimeo", "twitch", "bandcamp", "local"}


def get_start_pos(player, track, extra_milliseconds=0):
    if not track.is_stream:
        difference = (((disnake.utils.utcnow() + datetime.timedelta(milliseconds=int(extra_milliseconds))).timestamp() * 1000)) - player.last_update
        position = player.last_position + difference
        if 0 < position < track.duration:
            return min(position, track.duration)
    return 0


class PartialPlaylist:
    __slots__ = ('data', 'url', 'tracks')

    def __init__(self, data: dict, url: str):
        self.data = data
        self.url = url
        self.tracks = []

    @property
    def name(self):
        try:
            return self.data["playlistInfo"]["name"]
        except KeyError:
            return

    @property
    def uri(self) -> str:
        return self.url

    @property
    def thumb(self):
        try:
            return self.data["playlistInfo"]["thumb"]
        except KeyError:
            pass
        try:
            return self.tracks[0].thumb
        except:
            return ""


class PartialTrack:
    __slots__ = ('id', 'source_name', 'info', 'playlist', 'unique_id', 'ytid')

    def __init__(self, *, uri: str = "", title: str = "", author="", thumb: str = "", duration: int = 0,
                 requester: int = 0, track_loops: int = 0, source_name: str = "", autoplay: bool = False,
                 identifier: str = "", info: dict = None, playlist: PartialPlaylist = None):

        self.info = info or {
            "author": fix_characters(author)[:97],
            "identifier": identifier,
            "title": title[:97],
            "uri": uri,
            "length": duration,
            "isStream": False,
            "isSeekable": True,
            "sourceName": source_name,
            "is_partial": True,
            "extra": {
                "requester": requester,
                "track_loops": track_loops,
                "thumb": thumb,
                "autoplay": autoplay
            }
        }

        self.id = None
        self.ytid = ""
        self.unique_id = str(uuid.uuid4().hex)[:10]
        self.playlist: Optional[PartialPlaylist] = playlist

    def __repr__(self):
        return f"{self.info['sourceName']} - {self.duration} - {self.authors_string} - {self.title}"

    @property
    def thumb(self) -> str:
        try:
            return self.info["extra"]["thumb"] or self.info["artworkUrl"]
        except KeyError:
            try:
                return self.info["artworkUrl"]
            except KeyError:
                return ""

    @property
    def uri(self) -> str:
        return self.info["uri"]

    @property
    def url(self) -> str:
        return self.uri

    @property
    def search_uri(self):
        return f"https://www.youtube.com/results?search_query={quote(self.title)}"

    @property
    def title(self) -> str:
        return f"{self.author} - {self.single_title}"

    @property
    def name(self) -> str:
        return self.title

    @property
    def identifier(self) -> str:
        try:
            return self.info["identifier"]
        except KeyError:
            try:
                return self.info["extra"]["original_id"]
            except KeyError:
                return ""

    @property
    def single_title(self) -> str:
        return self.info["title"]

    @property
    def author(self) -> str:
        return self.info["author"] or "Artista Desconhecido"

    @property
    def authors_string(self) -> str:
        try:
            return ", ".join(self.info["extra"]["authors"])
        except KeyError:
            return self.author

    @property
    def authors_md(self) -> str:
        try:
            return self.info["extra"]["authors_md"]
        except KeyError:
            return f"`{self.author}`"

    @property
    def authors(self) -> List[str]:
        try:
            return self.info["extra"]["authors"]
        except KeyError:
            return [self.author]

    @property
    def lyrics(self) -> str:

        try:
            return self.info["extra"]["lyrics"]
        except KeyError:
            return ""

    @property
    def requester(self) -> int:
        return self.info["extra"]["requester"]

    @property
    def autoplay(self) -> bool:
        try:
            return self.info["extra"]["autoplay"]
        except KeyError:
            return False

    @property
    def track_loops(self) -> int:
        return self.info["extra"]["track_loops"]

    @property
    def is_stream(self) -> bool:
        return self.info["isStream"]

    @property
    def duration(self) -> int:
        return self.info["length"]

    @property
    def album_name(self) -> str:
        try:
            return self.info["extra"]["album"]["name"]
        except KeyError:
            try:
                self.info["pluginInfo"]["albumName"]
            except KeyError:
                return ""

    @property
    def album_url(self) -> str:
        try:
            return self.info["extra"]["album"]["url"]
        except KeyError:
            try:
                self.info["pluginInfo"]["albumUrl"]
            except KeyError:
                return ""

    @property
    def playlist_name(self) -> str:
        try:
            return self.playlist.name[:97]
        except AttributeError:
            return ""

    @property
    def playlist_url(self) -> str:
        try:
            return self.playlist.url
        except AttributeError:
            return ""


class LavalinkPlaylist:
    __slots__ = ('data', 'url', 'tracks')

    def __init__(self, data: dict, **kwargs):
        self.data = data
        self.url = kwargs.pop("url")

        try:
            self.data["playlistInfo"]["thumb"] = kwargs["pluginInfo"]["artworkUrl"]
        except KeyError:
            pass

        try:
            self.data["playlistInfo"]["type"] = kwargs["pluginInfo"]["type"]
        except KeyError:
            pass

        encoded_name = kwargs.pop("encoded_name", "track")

        try:
            if self.data['tracks'][0]['info'].get("sourceName") == "youtube":
                try:
                    self.url = f"https://www.youtube.com/playlist?list={parse.parse_qs(parse.urlparse(self.url).query)['list'][0]}"
                except KeyError:
                    pass
        except IndexError:
            pass
        pluginInfo = kwargs.pop("pluginInfo", {})
        thumb = None
        try:
            playlist = self if pluginInfo["type"] == "playlist" else None
            if pluginInfo["type"] == "album":
                thumb = self.thumb
        except KeyError:
            playlist = self
        self.tracks = [LavalinkTrack(
            id_=track[encoded_name], info=track['info'], pluginInfo=track.get("pluginInfo") or pluginInfo, thumb=thumb, playlist=playlist, **kwargs) for track in data['tracks']]

    @property
    def uri(self):
        return self.url

    @property
    def name(self):
        return self.data["playlistInfo"]["name"]

    @property
    def thumb(self):
        try:
            return self.data["playlistInfo"]["thumb"]
        except KeyError:
            pass
        try:
            return self.tracks[0].thumb
        except:
            return ""


class LavalinkTrack(wavelink.Track):
    __slots__ = ('extra', 'playlist', 'unique_id')

    def __init__(self, *args, **kwargs):
        try:
            args[1]['title'] = fix_characters(args[1]['title'])[:97]
        except IndexError:
            pass
        super().__init__(*args, **kwargs)
        self.title = fix_characters(self.title)
        self.info["title"] = self.title
        self.unique_id = str(uuid.uuid4().hex)[:10]

        try:
            self.info['sourceName']
        except:
            self.info['sourceName'] = 'LavalinkTrack'

        try:
            if (albumname:=fix_characters(self.info["pluginInfo"]["albumName"])) == self.title:
                del self.info["pluginInfo"]["albumName"]
                del self.info["pluginInfo"]["albumUrl"]
            else:
                self.info["pluginInfo"]["albumName"] = albumname
        except (AttributeError, KeyError):
            pass

        try:
            self.info["extra"]
        except KeyError:
            self.info["extra"] = {
                "track_loops": kwargs.pop('track_loops', 0),
                "requester": kwargs.pop('requester', ''),
                "autoplay": kwargs.pop("autoplay", '')
            }

        self.playlist: Optional[LavalinkPlaylist] = kwargs.pop(
            "playlist", None)

        if self.info["sourceName"] == "youtube":
            self.info["artworkUrl"] = f"https://img.youtube.com/vi/{self.ytid}/mqdefault.jpg"
            if "list=" not in self.uri:
                try:
                    self.info['uri'] = f"{self.uri}&list={parse.parse_qs(parse.urlparse(self.playlist_url or self.album_url).query)['list'][0]}"
                except KeyError:
                    pass

        elif self.info["sourceName"] == "soundcloud":

            self.info["artworkUrl"] = self.info.get("artworkUrl", "").replace('-large.', '-t500x500.').replace('-original.', '-t500x500.')

            if "?in=" not in self.uri:
                try:
                    self.info['uri'] = f"{self.uri}?in=" + self.playlist_url.split("soundcloud.com/")[1]
                except:
                    pass

        elif thumb:=kwargs.get("thumb"):
            self.info["artworkUrl"] = thumb

    def __repr__(self):
        return f"{self.info['sourceName']} - {self.duration if not self.is_stream else 'stream'} - {self.authors_string} - {self.title}"

    @property
    def thumb(self) -> str:
        return self.info["artworkUrl"] or ""

    @property
    def name(self) -> str:
        return self.title

    @property
    def single_title(self) -> str:
        return self.title

    @property
    def url(self) -> str:
        return self.info["uri"]

    @property
    def search_uri(self):
        return f"https://www.youtube.com/results?search_query={quote(self.title)}"

    @property
    def authors_md(self) -> str:
        try:
            if self.info['pluginInfo']['artistUrl']:
                return f"[`{self.author}`](<{self.info['pluginInfo']['artistUrl']}>)"
        except KeyError:
            pass
        return f"`{self.author}`"

    @property
    def authors(self) -> str:
        return f"{self.author}"

    @property
    def authors_string(self) -> str:
        return f"{self.author}"

    @property
    def album_name(self) -> str:
        try:
            return self.info["extra"]["album"]["name"]
        except KeyError:
            try:
                return self.info["pluginInfo"]["albumName"]
            except KeyError:
                return ""

    @property
    def album_url(self) -> str:
        try:
            return self.info["extra"]["album"]["url"]
        except KeyError:
            try:
                return self.info["pluginInfo"]["albumUrl"]
            except KeyError:
                return ""

    @property
    def lyrics(self) -> str:
        try:
            return self.info["extra"]["lyrics"]
        except KeyError:
            return ""

    @property
    def requester(self) -> int:
        return self.info["extra"]["requester"]

    @property
    def autoplay(self) -> bool:
        try:
            return self.info["extra"]["autoplay"]
        except KeyError:
            return False

    @property
    def track_loops(self) -> int:
        return self.info["extra"]["track_loops"]

    @property
    def playlist_name(self) -> str:
        try:
            return self.playlist.name[:97]
        except AttributeError:
            return ""

    @property
    def playlist_url(self) -> str:
        try:
            return self.playlist.url
        except AttributeError:
            return ""


class LavalinkPlayer(wavelink.Player):
    bot: BotCore

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.version = 1.1
        self.volume = 100
        self.guild: disnake.Guild = kwargs.pop('guild')
        self.text_channel: Union[disnake.TextChannel,
        disnake.VoiceChannel, disnake.Thread] = kwargs.pop('channel')
        self.message: Optional[disnake.Message] = kwargs.pop('message', None)
        self.static: bool = kwargs.pop('static', False)
        self.skin: str = kwargs.pop("skin", None) or self.bot.pool.default_skin
        self.skin_static: str = kwargs.pop("skin_static", None) or self.bot.pool.default_static_skin
        self.custom_skin_data = kwargs.pop("custom_skin_data", {})
        self.custom_skin_static_data = kwargs.pop("custom_skin_static_data", {})
        self.queue: deque = deque()
        self.played: deque = deque(maxlen=20)
        self.queue_autoplay: deque = deque(maxlen=30)
        self.failed_tracks: deque = deque(maxlen=30)
        self.autoplay: bool = kwargs.pop("autoplay", False)
        self.nightcore: bool = False
        self.loop = False
        self.last_track: Optional[LavalinkTrack] = None
        self.locked: bool = False
        self.is_previows_music: bool = False
        self.interaction_cooldown: bool = False
        self.votes: set = set()
        self.dj: set = set()
        self.player_creator: Optional[int] = kwargs.pop('player_creator', None)
        self.filters: dict = {}
        self.idle_task: Optional[asyncio.Task] = None
        self.hook_event_task = {}
        self.members_timeout_task: Optional[asyncio.Task] = None
        self.reconnect_voice_channel_task: Optional[asyncio.Task] = None
        self.idle_endtime: Optional[datetime.datetime] = None
        self.idle_start_timestamp: Optional[int] = None
        self.hint_rate = self.bot.config["HINT_RATE"]
        self.command_log: str = ""
        self.command_log_emoji: str = ""
        self.is_closing: bool = False
        self.last_message_id: Optional[int] = kwargs.pop("last_message_id", None)
        self.keep_connected: bool = kwargs.pop("keep_connected", False)
        self.update: bool = False
        self.updating: bool = False
        self.auto_update: int = 0
        self.listen_along_invite = kwargs.pop("listen_along_invite", "")
        self.message_updater_task: Optional[asyncio.Task] = None
        # limitar apenas para dj's e staff's
        self.restrict_mode = kwargs.pop('restrict_mode', False)
        self.ignore_np_once = False  # não invocar player controller em determinadas situações
        self.allowed_mentions = disnake.AllowedMentions(users=False, everyone=False, roles=False)
        self.uptime = kwargs.pop("uptime", None) or int(disnake.utils.utcnow().timestamp())
        # ativar/desativar modo controller (apenas para uso em skins)
        self.controller_mode = True
        self.mini_queue_feature = False
        self.mini_queue_enabled = False
        self.is_resuming = False
        self.is_purging = False
        self.auto_pause = False
        self._session_resuming = kwargs.pop("session_resuming", False)
        self._last_channel: Optional[disnake.VoiceChannel] = None
        self._last_channel_id: Optional[int] = None
        self._rpc_update_task: Optional[asyncio.Task] = None
        self._new_node_task: Optional[asyncio.Task] = None
        self._queue_updater_task: Optional[asyncio.Task] = None
        self.auto_skip_track_task: Optional[asyncio.Task] = None
        self.track_load_task: Optional[asyncio.Task] = None
        self.native_yt: bool = True
        self.stage_title_event = False
        self.stage_title_template: str = kwargs.pop("stage_title_template", None) or "Tocando: {track.title} | {track.author}"
        self.last_stage_title = ""

        self.channel_purged = False

        self.temp_embed: Optional[disnake.Embed] = None
        self.prefix_info = kwargs.pop("prefix", "")

        self.start_time = disnake.utils.utcnow()
        self.start_timestamp = self.start_time.timestamp()

        self.lastfm_artists = []

        self.initial_hints = [
            f"É possível alterar a skin/aparência do player usando o comando /change_skin ou {self.prefix_info}skin "
            f"(Apenas membros com permissão de gerenciar servidor podem usar esse comando).",

            "Dê uma nova cara para o player de música no servidor criando skins personalizadas. Experimente usando "
            f"o comando /custom_skin ou {self.prefix_info}customskin (Apenas membros com permissão de administrador "
            "podem usar esse comando).",

            "É possível definir o status automático no canal de voz com informações sobre "
            "a música que está sendo tocada no momento. Experimente usando o comando /set_voice_status ou "
            f"{self.prefix_info}stageannounce (Apenas membros com permissão de gerenciar servidor podem usar esse recurso)."
        ]

        self.retry_setup_hints = False

        hint_platforms = []

        if self.bot.config["USE_YTDL"]:
            hint_platforms.append("youtube, soundcloud")

        if (self.bot.spotify and not self.bot.spotify.disabled) or "spotify" in self.node.info["sourceManagers"]:
            hint_platforms.append("spotify")

        hint_platforms.append("deezer")

        if self.bot.config["LASTFM_KEY"] and self.bot.config["LASTFM_SECRET"]:
            self.initial_hints.append(
                f"Você pode vincular uma conta do last.fm para registrar as músicas que você ouvir por aqui na sua "
                f"lista de músicas tocadas. Experimente usando o comando /lastfm ou {self.prefix_info}lastfm."
            )

        if hint_platforms:
            self.initial_hints.append(
                "Você pode adicionar/integrar link de perfis/canais do " + " e ".join(hint_platforms) + " para tocar "
                f"playlists pública que tem no canal/perfil via comando {self.prefix_info}play (sem incluir "
                "nome/link) ou no comando /play (via preenchimento automático da busca). Experimente usando o "
                f"comando /fav_manager ou {self.prefix_info}favmanager selecionando a opção \"integrações\"."
            )

        try:
            self.initial_hints.extend(kwargs.pop("extra_hints"))
        except:
            pass

        self.lastfm_users = {}

        self.hints: cycle = []
        self.current_hint: str = ""
        self.last_data: dict = {}
        self.check_skins()
        self.setup_features()
        self.setup_hints()

        self.bot.dispatch("player_create", player=self)

    def __str__(self) -> str:
        return f"Servidor de música atual: {self.node.identifier} (v{self.node.version})"

    def __repr__(self):
        return f"<volume={self.volume} " \
               f"current_position={time_format(self.position) if self.position else 'Idling'} " \
               f"queue={len(self.queue)} loop={self.loop} EQ=\"{self.eq}\" guild=\"{self.guild.name}\" " \
               f"node=\"{self.node.identifier}\" keep_connected=\"{self.keep_connected}\">"

    @property
    def has_thread(self):
        try:
            if isinstance(self.message.channel.parent, disnake.ForumChannel):
                return
        except AttributeError:
            pass

        return self.message and self.message.thread  # and not (self.message.thread.locked or self.message.thread.archived)

    @property
    def controller_link(self):
        if self.controller_mode:
            try:
                return f" [`🎛️`](<{self.message.jump_url}>)"
            except AttributeError:
                try:
                    return f" [`#️⃣`](<{self.text_channel.jump_url}>)"
                except AttributeError:
                    pass
        return ""

    @property
    def position(self):

        if not self.current:
            return 0

        if not self.is_playing:
            return 0

        if self.paused and not self.auto_pause:
            return min(self.last_position, self.current.duration)

        difference = (time() * 1000) - self.last_update
        position = self.last_position + difference

        if position > self.current.duration:
            return 0

        return min(position, self.current.duration)

    async def update_state(self, state: dict) -> None:
        state = state['state']

        if not self.auto_pause:
            self.last_position = state.get('position') or 0

        self.last_update = time() * 1000
        self.position_timestamp = state.get('time', 0)
        self.ping = state.get('ping', None)

    async def report_error(self, embed: disnake.Embed, track: Union[LavalinkTrack, PartialTrack]):

        cog = self.bot.get_cog("Music")

        if cog and cog.error_report_queue:

            embed.description += f"\n**Fonte:** `{track.info['sourceName']}`" \
                                 f"\n**Servidor:** `{disnake.utils.escape_markdown(self.guild.name)} [{self.guild.id}]`"

            try:
                embed.description += f"\n**Canal:** `{disnake.utils.escape_markdown(self.guild.me.voice.channel.name)} [{self.guild.me.voice.channel.id}]`\n"
            except:
                pass

            embed.description += f"**Data:** <t:{int(disnake.utils.utcnow().timestamp())}:F>"

            if self.guild.icon:
                embed.set_thumbnail(url=self.guild.icon.with_format("png").url)

            await cog.error_report_queue.put({"embed": embed})

    async def reconnect_voice_channel(self):

        channel_check_retries = 0

        while True:

            try:
                self.bot.music.players[self.guild_id]
            except KeyError:
                return

            try:
                vc = self.bot.get_channel(self.last_channel.id)
            except AttributeError:
                vc = None

            if not vc:

                if channel_check_retries < 3:
                    channel_check_retries += 1
                    await asyncio.sleep(3 * channel_check_retries)
                    continue

                msg = "O canal de voz foi excluido..."

                if self.static:
                    self.set_command_log(msg)
                    await self.destroy()
                    return

                else:
                    if self.text_channel:
                        try:
                            self.bot.loop.create_task(self.text_channel.send(embed=disnake.Embed(
                                description=msg,
                                color=self.bot.get_color(self.guild.me)), delete_after=7))
                        except:
                            traceback.print_exc()
                    await self.destroy()
                    return

            if self.guild.me.voice:
                if isinstance(vc, disnake.StageChannel) \
                        and self.guild.me not in vc.speakers \
                        and vc.permissions_for(self.guild.me).mute_members:
                    try:
                        await self.guild.me.edit(suppress=False)
                    except Exception:
                        traceback.print_exc()
                return

            if self.is_closing:
                return

            if not self._new_node_task:

                try:
                    can_connect(vc, self.guild, bot=self.bot)
                except (GenericError, PoolException) as e:
                    self.set_command_log(f"Ocorreu uma falha ao reconectar o player no canal de voz: {e}.")
                    self.update = True
                except Exception as e:
                    self.set_command_log(f"Ocorreu uma falha ao reconectar o player no canal de voz: {repr(e)}.")
                    self.update = True
                else:
                    if (ping := round(self.bot.latency * 1000)) > 250:
                        voice_msg = f"Reconectei no canal de voz devido a um possível problema de instabilidade ne conexão (ping: {ping}ms)."
                    elif self.keep_connected:
                        voice_msg = f"Notei uma tentativa de me desconectarem do canal <#{vc.id}>."
                    else:
                        voice_msg = None

                    if not voice_msg:
                        self.set_command_log(text=f"O plater foi finalizado por perca de conexão no canal <#{vc.id}>.",
                                             emoji="⚠️")
                        await self.destroy()
                        return

                    try:
                        await self.connect(vc.id)
                        self.set_command_log(
                            text=f"{voice_msg}\nCaso realmente queira me desconectar, use o comando/botão: **stop**.",
                            emoji="⚠️")
                        self.update = True
                        await asyncio.sleep(5)
                        continue
                    except Exception:
                        traceback.print_exc()

            await asyncio.sleep(30)

    async def hook(self, event) -> None:

        """if self.is_closing:
            return

        event_name = str(event)

        if self.hook_event_task.get(event_name):
            return

        self.hook_event_task[event_name] = self.bot.loop.create_task(self.hook_events(event))"""
        await self.hook_events(event)

    async def hook_events(self, event):

        await self.bot.wait_until_ready()

        if isinstance(event, wavelink.TrackEnd):

            if event.node.identifier != self.node.identifier:
                return

            self.bot.dispatch("wavelink_track_end", player=self, track=self.last_track, reason=event.reason)

            if self.locked:
                return

            if event.reason == "FINISHED":
                self.set_command_log()

            elif event.reason == "STOPPED":

                if len(self.queue) == 0:
                    return

                self.ignore_np_once = True

            else:
                return

            try:
                self.message_updater_task.cancel()
            except:
                pass

            await self.track_end()

            self.update = False

            await self.process_next()

            return

        if isinstance(event, wavelink.TrackStart):

            if event.node.identifier != self.node.identifier:
                return

            self.bot.dispatch("wavelink_track_start", player=self)

            if self.text_channel:

                if isinstance(self.text_channel, disnake.Thread):
                    send_message_perm = self.text_channel.parent.permissions_for(self.guild.me).send_messages_in_threads
                else:
                    send_message_perm = self.text_channel.permissions_for(self.guild.me).send_messages

                if not send_message_perm:
                    self.text_channel = None

            if not self.guild.me.voice:
                try:
                    await self.bot.wait_for(
                        "voice_state_update", check=lambda m, b, a: m == self.guild.me and m.voice, timeout=7
                    )
                except asyncio.TimeoutError:
                    self.update = True
                    return

            try:
                await self.process_save_queue()
            except:
                traceback.print_exc()

            await asyncio.sleep(2)
            await self.update_stage_topic()
            return

        if isinstance(event, wavelink.TrackException):

            track = self.current or self.last_track
            node_info = f"`{event.node.identifier}`" if event.node.identifier == self.node.identifier else f"`{self.node.identifier} | {event.node.identifier}`"
            embed = disnake.Embed(
                description=f"**Falha ao reproduzir música:\n[{track.title}]({track.uri or track.search_uri})** ```java\n{event.message}```\n"
                            f"**Causa:** ```java\n{event.cause[:200]}```\n"
                            f"**Nível:** `{event.severity}`\n"
                            f"**Servidor de música:** {node_info}",
                color=disnake.Colour.red())

            error_format = pprint.pformat(event.data)

            async def send_report():

                print(("-" * 50) + f"\nErro ao reproduzir a música: {track.uri or track.search_uri}\n"
                                   f"Servidor: {self.node.identifier}\n"
                                   f"{error_format}\n" + ("-" * 50))

                await self.report_error(embed, track)

            if event.node.identifier != self.node.identifier:
                await send_report()
                return

            if self.locked:
                self.set_command_log(
                    text=f"A reprodução da música falhou (tentando tocar novamente): [`{fix_characters(track.title, 15)}`](<{track.uri or track.search_uri}>). **Causa:** `{event.cause[:50]}`")
                self.update = True
                await send_report()
                return

            self.locked = True

            self.current = None

            youtube_exception = False
            video_not_available = False

            cooldown = 10

            if event.cause.startswith((
                    "java.net.SocketTimeoutException: Read timed out",
                    "java.net.SocketException: Network is unreachable",
            )) \
                or (video_not_available:=event.cause.startswith((
                "com.sedmelluq.discord.lavaplayer.tools.FriendlyException: This video is not available",
                "com.sedmelluq.discord.lavaplayer.tools.FriendlyException: YouTube WebM streams are currently not supported.",
                "java.lang.IllegalStateException: Connection pool shut down",
            )) or event.message in ("Video returned by YouTube isn't what was requested", "The video returned is not what was requested.")):
                await send_report()

                self.current = None
                self.queue.appendleft(track)

                if video_not_available:

                    with suppress(IndexError, ValueError):
                        self.node.search_providers.remove("ytsearch")
                        self.node.search_providers.remove("ytmsearch")
                        self.node.partial_providers.remove("ytsearch:\"{isrc}\"")
                        self.node.partial_providers.remove("ytsearch:\"{title} - {author}\"")
                        self.node.partial_providers.remove("ytmsearch:\"{isrc}\"")
                        self.node.partial_providers.remove("ytmsearch:\"{title} - {author}\"")

                    self.native_yt = False

                    if track.info["sourceName"] == "youtube":
                        txt = f"Devido a restrições do youtube no servidor `{self.node.identifier}`. Durante a sessão atual " \
                                 "será feito uma tentativa de obter a mesma música em outras plataformas de música usando o nome " \
                                 "das músicas do youtube que estão na fila (talvez a música tocada seja diferente do esperado " \
                                 "ou até mesmo ignoradas caso não retorne resultados)."

                        try:
                            await self.text_channel.send(embed=disnake.Embed(description=txt, color=self.bot.get_color(self.guild.me)), delete_after=60)
                        except:
                            self.set_command_log(text=txt, emoji="⚠️")
                    await asyncio.sleep(3)
                    self.locked = False
                    await self.process_next(start_position=self.position)
                    self.hook_event_task[str(event)] = None

                else:
                    await asyncio.sleep(10)
                    self.current = track
                    await self.play(track=track, start=self.position)
                return

            if (youtube_exception := (event.error == "This IP address has been blocked by YouTube (429)" or
                #event.message == "Video returned by YouTube isn't what was requested" or
                event.cause.startswith(("java.lang.RuntimeException: Not success status code: 403",
                    "com.sedmelluq.discord.lavaplayer.tools.FriendlyException: Sign in to confirm you’re not a bot",
                    "java.io.IOException: Invalid status code for video page response: 400"))
            ) or event.cause == "com.sedmelluq.discord.lavaplayer.tools.FriendlyException: This video is unavailable"):

                if youtube_exception and self.node.retry_403:

                    if not hasattr(self, 'retries_403'):
                        self.retries_403 = {"last_time": None, 'counter': 0}

                    if not self.retries_403["last_time"] or ((disnake.utils.utcnow() - self.retries_403["last_time"]).total_seconds() > self.bot.pool.config.get("ERROR_403_RETRIES", 7)):
                        self.retries_403 = {"last_time": disnake.utils.utcnow(), 'counter': 0}
                        if self.auto_pause:
                            self.update = True
                        else:
                            await self.play(track, start=get_start_pos(self, track, self.bot.pool.config.get("ERROR_403_ADDITIONAL_MILLISECONDS", 430)))
                            await asyncio.sleep(3)
                        self.locked = False
                        self.update = True
                        self.hook_event_task[str(event)] = None
                        return

                    elif self.retries_403["counter"] < 3:
                        self.retries_403["counter"] += 1
                        await asyncio.sleep(3)
                        self.retries_403["last_time"] = disnake.utils.utcnow()

                        if self.is_closing:
                            return

                        self.locked = False
                        self.hook_event_task[str(event)] = None
                        self.set_command_log(
                            text=f'Ocorreu o erro 403 do youtube na reprodução da música atual. Tentativa {self.retries_403["counter"]}/5...')
                        if not self.auto_pause:
                            self.update = True
                        else:
                            await self.play(track, start=get_start_pos(self, track, self.bot.pool.config.get("ERROR_403_ADDITIONAL_MILLISECONDS", 430)))
                            self.update = True
                        await send_report()
                        return

                    self.queue.append(track)

                self.retries_403 = {"last_time": None, 'counter': 0}

                if youtube_exception:

                    with suppress(IndexError, ValueError):
                        self.node.search_providers.remove("ytsearch")
                        self.node.search_providers.remove("ytmsearch")
                        self.node.partial_providers.remove("ytsearch:\"{isrc}\"")
                        self.node.partial_providers.remove("ytsearch:\"{title} - {author}\"")
                        self.node.partial_providers.remove("ytmsearch:\"{isrc}\"")
                        self.node.partial_providers.remove("ytmsearch:\"{title} - {author}\"")

                    self.current = None
                    self.queue.appendleft(track)
                    self.locked = False
                    self.hook_event_task[str(event)] = None

                    if track.info["sourceName"] == "youtube":

                        try:
                            new_node = [n for n in self.bot.music.nodes.values() if n.is_available and "ytsearch" in n.search_providers][0]
                        except:
                            new_node = None

                        if new_node:
                            self.native_yt = True
                            txt = f"Devido a restrições do youtube no servidor `{self.node.identifier} o player foi movido para o servidor `{new_node.identifier}`."
                            if self.controller_mode:
                                self.set_command_log(txt, emoji="⚠️")
                            elif self.text_channel:
                                try:
                                    await self.text_channel.send(embed=disnake.Embed(description=f"-# `⚠️ -` {txt}", color=self.bot.get_color(self.guild.me)), delete_after=10)
                                except:
                                    traceback.print_exc()
                            await asyncio.sleep(5)
                            await self.change_node(new_node.identifier)
                            await self.process_next(start_position=self.position)
                            await send_report()
                            return

                        self.native_yt = False

                        txt = f"Devido a restrições do youtube no servidor `{self.node.identifier}`. Durante a sessão atual " \
                              "será feito uma tentativa de obter a mesma música em outras plataformas de música usando o nome " \
                              "das músicas do youtube que estão na fila (talvez a música tocada seja diferente do esperado " \
                              "ou até mesmo ignoradas caso não retorne resultados)."
                        try:
                            await self.text_channel.send(embed=disnake.Embed(
                                description=txt, color=self.bot.get_color(self.guild.me)
                            ), delete_after=30)
                        except:
                            self.set_command_log(text=txt, emoji="⚠️")
                    await asyncio.sleep(5)
                    await self.process_next(start_position=self.position)
                    await send_report()
                    return

            await send_report()

            start_position = 0

            if event.cause.startswith((
                    "java.lang.IllegalStateException: Failed to get media URL: 2000: An error occurred while decoding track token",
                    "java.lang.RuntimeException: Not success status code: 204",
                    "java.net.SocketTimeoutException: Connect timed out",
                    "java.lang.IllegalArgumentException: Invalid bitrate",
                    "java.io.EOFException",
                    "java.net.UnknownHostException:",
                    "java.lang.IllegalStateException: Error from decoder",
                    "java.lang.IllegalStateException: Current position is beyond this element",
                    "com.sedmelluq.discord.lavaplayer.tools.io.PersistentHttpStream$PersistentHttpException: Not success status code: 403",
            )):

                if not hasattr(self, 'retries_general_errors'):
                    self.retries_general_errors = {'counter': 6, 'last_node': self.node.identifier,
                                                   "last_time": disnake.utils.utcnow()}

                embed = None

                self.queue.appendleft(track)

                if self.retries_general_errors["counter"] < 1 and self.node.identifier == self.retries_general_errors["last_node"] and (disnake.utils.utcnow() - self.retries_general_errors["last_time"]).total_seconds() < 180:

                    try:
                        self._new_node_task.cancel()
                    except:
                        pass
                    self._new_node_task = self.bot.loop.create_task(
                        self._wait_for_new_node(ignore_node=self.node))
                    return

                self.retries_general_errors["last_time"] = disnake.utils.utcnow()

                if self.retries_general_errors['last_node'] == self.node.identifier:
                    self.retries_general_errors['counter'] -= 1
                else:
                    self.retries_general_errors = {'counter': 6, 'last_node': self.node.identifier,
                                                   "last_time": disnake.utils.utcnow()}

                start_position = get_start_pos(self, track)

                cooldown = 4

            elif event.cause == "java.lang.InterruptedException":
                embed = None
                self.queue.appendleft(track)
                try:
                    self._new_node_task.cancel()
                except:
                    pass
                self._new_node_task = self.bot.loop.create_task(self._wait_for_new_node())
                return

            elif not track.track_loops:
                self.failed_tracks.append(track)

            elif self.keep_connected and not track.autoplay and len(self.queue) > 15:
                self.queue.append(track)

            if event.cause == "com.github.topi314.lavasrc.mirror.TrackNotFoundException: Playlist is empty":
                embed = disnake.Embed(
                    description=f"`Ignorando a música` [`{track.title}`](<{track.url}>)`. Pois não houve resultados em outras plataformas de música.`",
                    color=self.bot.get_color(self.guild.me)
                ).set_thumbnail(track.thumb)

            if isinstance(self.text_channel, disnake.Thread):
                send_message_perm = self.text_channel.parent.permissions_for(self.guild.me).send_messages_in_threads
            else:
                send_message_perm = self.text_channel.permissions_for(self.guild.me).send_messages

            if embed and self.text_channel and send_message_perm:
                await self.text_channel.send(embed=embed, delete_after=10)

            await asyncio.sleep(cooldown)

            self.locked = False
            self.hook_event_task[str(event)] = None
            await self.process_next(start_position=start_position)
            return

        if isinstance(event, wavelink.WebsocketClosed):

            if event.code == 1000:
                return

            if not self.guild.me:
                await self.destroy(force=True)
                return

            try:
                vc = self.last_channel or self.guild.me.voice.channel
            except AttributeError:
                vc = None

            if event.code == 4014 and self.guild.me.voice:
                pass
            else:
                print(
                    ("-" * 15) +
                    f"\nErro no canal de voz!"
                    f"\nBot: {self.bot.user} [{self.bot.user.id}] | " + (
                        "Online" if self.bot.is_ready() else "Offline") +
                    f"\nGuild: {self.guild.name} [{self.guild.id}]"
                    f"\nCanal: {vc.name} [{vc.id}]"
                    f"\nServer: {self.node.identifier} | code: {event.code} | reason: {event.reason}\n" +
                    ("-" * 15)
                )

            if self.is_closing:
                return

            if event.code in (
                    4000,  # internal error
                    1006,
                    1001,
                    4016,  # Connection started elsewhere
                    4005,  # Already authenticated.
            ):
                try:
                    vc_id = self.guild.me.voice.channel.id
                except AttributeError:
                    vc_id = self.last_channel.id

                await asyncio.sleep(3)

                if self.is_closing:
                    return

                await self.connect(vc_id)
                return

            if event.code in (
                    4014,
                    4006,  # Session is no longer valid.
            ):
                await asyncio.sleep(5)
                try:
                    self.bot.music.players[self.guild_id]
                except KeyError:
                    return
                if self.guild and self.guild.me.voice or self.is_closing:
                    return

                try:
                    vc_id = self.guild.me.voice.channel.id
                except AttributeError:
                    vc_id = self.last_channel.id

                await self.connect(vc_id)
                return

        if isinstance(event, wavelink.TrackStuck):

            try:
                self.message_updater_task.cancel()
            except:
                pass

            await self.track_end()

            self.update = False

            try:
                self.set_command_log(text=f"A música [{fix_characters(self.current.single_title, 25)}](<{self.current.uri}>) travou.", emoji="⚠️")
            except:
                pass

            await self.process_next()

            return

        print(f"Unknown Wavelink event: {repr(event)}")

    async def channel_cleanup(self):

        try:
            parent = self.text_channel.parent
        except AttributeError:
            pass
        else:
            if isinstance(parent, disnake.ForumChannel) and self.text_channel.owner_id == self.bot.user.id and \
                    self.text_channel.message_count > 1:
                try:
                    await self.text_channel.purge(
                        check=lambda m: m.channel.id != m.id and (not m.pinned or not m.is_system()))
                except:
                    pass
                self.channel_purged = True
                return

        try:
            self.last_message_id = int(self.last_message_id)
        except TypeError:
            self.channel_purged = True
            return

        if self.last_message_id != self.text_channel.last_message_id:

            def check_current_message(m: disnake.Message):
                try:
                    return m.id == self.message.id
                except AttributeError:
                    return True

            if isinstance(self.text_channel, disnake.Thread):
                check = (lambda m: m.id != self.last_message_id and not not m.pinned and check_current_message(m) and (
                            not m.is_system() or m.type != disnake.MessageType.channel_name_change))
            else:
                check = (lambda m: m.id != self.last_message_id and not m.pinned and check_current_message(m))

            try:
                await self.text_channel.purge(check=check)
            except:
                print(f"Falha ao limpar mensagens do canal {self.text_channel} [ID: {self.text_channel.id}]:\n"
                      f"{traceback.format_exc()}")
                pass

        self.channel_purged = True

    async def connect(self, channel_id: int, self_mute: bool = False, self_deaf: bool = False):
        await super().connect(channel_id, self_mute=self_mute, self_deaf=True)
        self._last_channel = self.bot.get_channel(channel_id)
        self._last_channel_id = channel_id

    @property
    def last_channel(self):
        try:
            return self.guild.me.voice.channel
        except AttributeError:
            return self._last_channel

    def process_hint(self):

        if random.choice([x for x in range(self.hint_rate)]) == 0:
            self.current_hint = next(self.hints)
        else:
            self.current_hint = ""

    def setup_features(self):

        try:
            (self.bot.player_static_skins[self.skin_static]
             if self.static else self.bot.player_skins[self.skin]).setup_features(self)
        except:
            # linha temporária para resolver possíveis problemas com skins custom criadas por usuarios antes desse commit.
            self.auto_update = 0
            self.controller_mode = True

    def setup_hints(self):

        hints = list(self.initial_hints)

        if self.static:
            hints.append("É possível fixar músicas/playlists na mensagem do player quando tiver no modo de "
                         "espera/oscioso para permitir os membros ouvi-las de forma pública. Pra isso use o "
                         f"comando /fav_manager ou {self.prefix_info}favmanager (apenas membros com permissão "
                         "de gerenciar servidor podem usar esse recurso).")

        elif self.bot.intents.message_content and self.controller_mode:
            hints.append("Ao criar uma conversa/thread na mensagem do player, será ativado o modo de song-request "
                         "nela (possibilitando pedir música apenas enviando o nome/link da música na conversa).")

        if len(self.bot.pool.get_guild_bots(self.guild.id)) > 1:

            bots_in_guild = 0
            bots_outside_guild = 0

            for b in self.bot.pool.get_guild_bots(self.guild.id):

                if b == self.bot:
                    continue

                try:
                    self.bot.user.id
                except AttributeError:
                    self.retry_setup_hints = True
                    continue

                if b.get_guild(self.guild.id):
                    bots_in_guild += 1
                else:
                    bots_outside_guild += 1

            if bots_in_guild:
                hints.append(
                    "Caso algum membro queira me usar em outro canal de voz sem precisar aguardar me "
                    f"desconectarem ou me interromperem do canal atual, há mais {bots_in_guild} bot{'s'[:bots_in_guild^1]} no servidor que "
                    f"funciona{'m'[:bots_in_guild^1]} com o meu sistema/comandos (usando o mesmo prefixo/comandos de barra). "
                    f"Experimente entrar em um canal de voz diferente do meu atual e use o comando "
                    f"{self.prefix_info}play ou /play."
                )

            elif bots_outside_guild:
                hints.append(
                    "Caso algum membro queira me usar em outro canal de voz sem precisar aguardar me "
                    f"desconectarem ou me interromperem do canal atual. Dá para adicionar mais {bots_outside_guild} bot{'s'[:bots_outside_guild^1]} "
                    f"extras no servidor atual que funciona(m) com o mesmo sistema/comandos (usando o mesmo "
                    f"prefixo/comandos de barra). Use o comando {self.prefix_info}invite ou /invite para adicioná-los."
                )

        if self.controller_mode:
            hints.append(
                "Ao clicar nesse emoji 🎛️ das mensagens de alguns comandos você será redirecionado para o player-controller."
            )

        random.shuffle(hints)
        self.hints = cycle(hints)

    def check_skins(self):
        if self.skin.startswith("> custom_skin: "):
            if self.skin[15:] not in  self.custom_skin_data:
                self.skin = self.bot.pool.default_skin
        elif self.skin not in self.bot.pool.player_skins:
            self.skin = self.bot.pool.default_skin

        if self.skin_static.startswith("> custom_skin: "):
            if self.skin_static[15:] not in  self.custom_skin_static_data:
                self.skin_static = self.bot.pool.default_static_skin
        elif self.skin_static not in self.bot.pool.player_static_skins:
            self.skin_static = self.bot.pool.default_static_skin

    async def members_timeout(self, check: bool, force: bool = False, idle_timeout = None):

        if check:

            try:
                self.auto_skip_track_task.cancel()
            except:
                pass
            self.auto_skip_track_task = None

            if self.current and self.auto_pause:

                self.auto_pause = False

                try:
                    self.set_command_log(emoji="🔋", text="O modo **[economia de recursos]** foi desativado.")
                    await self.resolve_track(self.current)
                    if self.current.id:
                        if self.current.info["sourceName"] == "youtube" and not self.native_yt:
                            stream = self.current.is_stream
                            self.queue.appendleft(self.current)
                            self.current = None
                            await self.process_next(start_position=0 if stream else self.position)
                        else:
                            await self.play(self.current, start=0 if self.current.is_stream else self.position)
                            await asyncio.sleep(1.5)
                            await self.invoke_np(rpc_update=True)
                            await self.update_stage_topic()
                    else:
                        await self.process_next()
                except Exception:
                    traceback.print_exc()
            else:
                self.auto_pause = False
            return

        if not force:

            try:
                vc = self.guild.me.voice.channel
            except AttributeError:
                vc = self.last_channel

            if [m for m in vc.members if not m.bot and not (m.voice.deaf or m.voice.self_deaf)]:
                try:
                    self.auto_skip_track_task.cancel()
                except:
                    pass
                return

            if self.auto_pause:
                return

            if not idle_timeout:
                idle_timeout = self.bot.config["WAIT_FOR_MEMBERS_TIMEOUT"]

            await asyncio.sleep(idle_timeout)

            if [m for m in vc.members if not m.bot and not (m.voice.deaf or m.voice.self_deaf)]:
                try:
                    self.auto_skip_track_task.cancel()
                except:
                    pass
                return

        if self.keep_connected:

            if self.paused or self.auto_pause:
                return

            self.auto_pause = True
            track = self.current
            if self.is_playing:
                await self.stop()
            self.current = track
            try:
                self.auto_skip_track_task.cancel()
            except:
                pass
            self.set_command_log(
                emoji="🪫",
                text="O player está no modo **[economia de recursos]** (esse modo será desativado automaticamente quando "
                     f"um membro entrar no canal <#{self.channel_id}>)."
            )
            self.update = True
            self.start_auto_skip()
            await self.update_stage_topic()

        else:

            if self.is_closing:
                return

            msg = "**O player foi desligado por falta de membros no canal" + (f" <#{self.guild.me.voice.channel.id}>"
                                                                               if self.guild.me.voice else '') + "...**"
            self.command_log = msg
            if not self.static and not self.has_thread:
                embed = disnake.Embed(
                    description=msg, color=self.bot.get_color(self.guild.me))
                try:
                    await self.text_channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
                except:
                    pass

            await self.destroy()

    async def get_autoqueue_tracks(self):

        try:
            return self.queue_autoplay.popleft()
        except:
            pass

        if self.locked:
            return

        tracks_search = []

        for t in reversed(self.failed_tracks + self.played):

            if len(tracks_search) > 4:
                break

            tracks_search.insert(0, t)

        if current_track := self.current or self.last_track:
            tracks_search.insert(0, current_track)

        track = None
        tracks = []
        tracks_ytsearch = []

        exception = None

        if tracks_search:

            self.locked = True

            for track_data in tracks_search:

                if track_data.info["sourceName"] == "spotify" and "spotify" not in self.node.info["sourceManagers"] and self.bot.spotify:
                    track_ids = list(set(t.identifier for t in tracks_search if t.info["sourceName"] == "spotify"))[:5]

                    result = None

                    for i in range(3):
                        try:
                            result = await self.bot.spotify.get_recommendations(track_ids, limit=100)
                            break
                        except Exception as e:
                            self.set_command_log(emoji="⚠️", text=f"Falha ao obter músicas recomendadas do spotify, tentativa {i+1} de 3.")
                            self.update = True
                            traceback.print_exc()
                            exception = e
                            await asyncio.sleep(5)

                    if result:

                        tracks = []

                        for t in result["tracks"]:

                            try:
                                thumb = t["album"]["images"][0]["url"]
                            except (IndexError,KeyError):
                                thumb = ""

                            partial_track = PartialTrack(
                                    uri=t["external_urls"]["spotify"],
                                    author=t["artists"][0]["name"] or "Unknown Artist",
                                    title=t["name"],
                                    thumb=thumb,
                                    duration=t["duration_ms"],
                                    source_name="spotify",
                                    identifier=t["id"],
                                    requester=self.bot.user.id,
                                    autoplay=True,
                                )

                            partial_track.info["extra"]["authors"] = [fix_characters(i['name']) for i in t['artists'] if
                                                          f"feat. {i['name'].lower()}"
                                                          not in t['name'].lower()]

                            partial_track.info["extra"]["authors_md"] = ", ".join(
                                f"[`{a['name']}`]({a['external_urls']['spotify']})" for a in t["artists"])

                            try:
                                if t["album"]["name"] != t["name"]:
                                    partial_track.info["extra"]["album"] = {
                                        "name": t["album"]["name"],
                                        "url": t["album"]["external_urls"]["spotify"]
                                    }
                            except (AttributeError, KeyError):
                                pass

                            tracks.append(partial_track)

                elif track_data.info["sourceName"] == "deezer" and (self.bot.pool.config["FORCE_USE_DEEZER_CLIENT"] or "deezer" not in self.node.info["sourceManagers"]) and (artist_id:=track_data.info["extra"].get("artist_id")):

                    try:
                        try:
                            result = await self.bot.deezer.get_artist_radio_info(artist_id)
                        except Exception:
                            traceback.print_exc()
                            result = None

                        if result:

                            tracks = []

                            for n, t in enumerate(result):

                                partial_track = PartialTrack(
                                    uri=f"https://www.deezer.com/track/{t['id']}",
                                    author=t['artist']['name'],
                                    title=t['title'],
                                    thumb=t['album']['cover_big'],
                                    duration=t['duration'] * 1000,
                                    source_name="deezer",
                                    identifier=t['id'],
                                    requester=self.bot.user.id,
                                    autoplay=True,
                                )

                                partial_track.info["isrc"] = t.get('isrc')
                                artists = t.get('contributors') or [t['artist']]

                                partial_track.info["extra"]["authors"] = [a['name'] for a in artists]
                                partial_track.info["extra"]["authors_md"] = ", ".join(f"[`{fix_characters(a['name'])}`](https://www.deezer.com/artist/{a['id']})" for a in artists)
                                partial_track.info["extra"]["artist_id"] = t['artist']['id']

                                if t['title'] != t['album']['title']:
                                    partial_track.info["extra"]["album"] = {
                                        "name": t['album']['title'],
                                        "url": t['album']['tracklist']
                                    }

                                tracks.append(partial_track)
                    except Exception:
                        traceback.print_exc()

                elif track_data.info["sourceName"] == "soundcloud":
                    try:
                        info = await self.bot.loop.run_in_executor(None, lambda: self.bot.pool.ytdl.extract_info(f"{track_data.uri}/recommended",
                                                                                                            download=False))
                    except AttributeError:
                        pass

                    else:
                        tracks = [PartialTrack(
                            uri=i["url"],
                            title=i["title"],
                            requester=self.bot.user.id,
                            source_name="soundcloud",
                            identifier=i["id"],
                            autoplay=True,
                        ) for i in info['entries']]

                if not tracks:

                    if self.bot.last_fm and not self.lastfm_artists:

                        if track_data.ytid:
                            if track_data.author.endswith(" - topic") and not track_data.author.endswith(
                                    "Release - topic") and not track_data.title.startswith(track_data.author[:-8]):
                                artist = track_data.author[:-8]
                            else:
                                try:
                                    artist = track_data.title.split(" - ", maxsplit=1)[0]
                                except ValueError:
                                    artist = track_data.author
                        else:
                            artist = track_data.author

                        try:
                            self.lastfm_artists = [a['name'] for a in
                                                   await self.bot.last_fm.get_similar_artists(artist) if a['name'].lower() not in track_data.author.lower()]
                            self.lastfm_artists.insert(0, track_data.author)
                        except:
                            traceback.print_exc()

                    try:
                        author = self.lastfm_artists.pop(0)
                    except:
                        author = track_data.author
                        
                    if track_data.info["sourceName"] == "youtube" and self.native_yt:

                        queries = [f"https://www.youtube.com/watch?v={track_data.ytid}&list=RD{track_data.ytid}"]

                        if p_dict:=providers_dict.get(track_data.info["sourceName"]):
                            providers = [p_dict] + [p for p in self.node.search_providers if p != p_dict]
                        else:
                            providers = self.node.search_providers

                        queries.extend([f"{sp}:{author.split(',')[0]}" for sp in providers])

                    elif track_data.info["sourceName"] == "spotify" and "spotfy" in self.node.info["sourceManagers"]:
                        queries = ["sprec:seed_tracks=" + ",".join(list(set(t.identifier for t in tracks_search if t.info["sourceName"] == "spotify"))[:5])]

                    else:
                        if p_dict:=providers_dict.get(track_data.info["sourceName"]):
                            providers = [p_dict] + [p for p in self.node.search_providers if p != p_dict]
                        else:
                            providers = self.node.search_providers

                        queries = [f"{sp}:{author.split(',')[0]}" for sp in providers]

                    for query in queries:

                        if query.startswith("jssearch"):
                            continue

                        try:
                            tracks = await self.node.get_tracks(
                                query, track_cls=LavalinkTrack, playlist_cls=LavalinkPlaylist, autoplay=True,
                                requester=self.bot.user.id
                            )
                        except Exception as e:
                            if [err for err in ("Could not find tracks from mix", "Could not read mix page") if err in str(e)] and self.native_yt:
                                try:
                                    tracks_ytsearch = await self.node.get_tracks(
                                        f"{query}:\"{track_data.author}\"",
                                        track_cls=LavalinkTrack, playlist_cls=LavalinkPlaylist, autoplay=True,
                                        requester=self.bot.user.id)
                                    break
                                except Exception as e:
                                    exception = e
                                    continue
                            else:
                                print(traceback.format_exc())
                                exception = e
                                await asyncio.sleep(1.5)
                                continue

                        try:
                            tracks = tracks.tracks
                        except:
                            pass

                        if not tracks:
                            continue

                        break

                    if not [i in track_data.title.lower() for i in exclude_tags_2]:
                        final_tracks = []
                        for t in tracks:
                            if not any((i in t.title.lower()) for i in exclude_tags_2) and not track_data.uri.startswith(t.uri):
                                final_tracks.append(t)
                        tracks = final_tracks or tracks

                track = track_data

            if not tracks:
                try:
                    tracks_ytsearch = tracks_ytsearch.tracks
                except AttributeError:
                    pass
                tracks = tracks_ytsearch
                tracks.reverse()

            if not tracks:
                self.locked = False

                if exception:
                    if isinstance(exception, wavelink.TrackLoadError):
                        error_msg = f"**Causa:** ```java\n{exception.cause}```\n" \
                                    f"**Mensagem:** `\n{exception.message}`\n" \
                                    f"**Nível:** `{exception.severity}`\n" \
                                    f"**Servidor de música:** `{self.node.identifier}`"
                    else:
                        error_msg = f"**Detalhes:** ```py\n{repr(exception)}```"
                else:
                    error_msg = "Não houve resultados relacionados as músicas tocadas..."

                try:
                    embed = disnake.Embed(
                        description=f"**Falha ao obter dados do autoplay:**\n"
                                    f"{error_msg}",
                        color=disnake.Colour.red())
                    await self.text_channel.send(embed=embed, delete_after=10)
                except:
                    traceback.print_exc()
                await asyncio.sleep(7)
                return

        try:
            tracks = tracks.tracks
        except AttributeError:
            pass

        try:
            tracks = [t for t in tracks if not [u for u in tracks_search if t.uri.startswith(u.uri)]]
        except:
            pass

        if track:

            info = {
                "title": track.title,
                "uri": track.uri
            }

            tracks_final = []

            for t in tracks:

                if t.is_stream:
                    continue

                #if t.duration < 90000:
                #    continue

                if track.ytid and track.ytid == t.ytid:
                    continue

                if not isinstance(t, PartialTrack):
                    t.info["extra"].update({"autoplay": True, "requester": self.bot.user.id})
                    t.playlist = None

                t.info["extra"]["related"] = info
                tracks_final.append(t)

            tracks.clear()
            self.queue_autoplay.extend(tracks_final)

        self.locked = False

        try:
            return self.queue_autoplay.popleft()
        except:
            try:
                return self.played.popleft()
            except:
                return None

    def start_auto_skip(self):
        try:
            self.auto_skip_track_task.cancel()
        except:
            pass
        self.auto_skip_track_task = self.bot.loop.create_task(self.auto_skip_track())

    async def process_next(self, start_position: Union[int, float] = 0, inter: disnake.MessageInteraction = None,
                           force_np=False):

        if self.locked or self.is_closing:
            return

        if not self.node or not self.node.is_available:
            try:
                self._new_node_task.cancel()
            except:
                pass
            self._new_node_task = self.bot.loop.create_task(self._wait_for_new_node())
            return

        try:
            self.track_load_task.cancel()
        except:
            pass
        self.track_load_task = self.bot.loop.create_task(self._process_next(start_position=start_position, inter=inter,
                                                                            force_np=force_np))

    async def _process_next(self, start_position: Union[int, float] = 0, inter: disnake.MessageInteraction = None,
                           force_np=False):

        await self.bot.wait_until_ready()

        if not self.is_connected:
            return

        if not self.guild.me.voice:
            if self.last_channel:
                await self.connect(self.last_channel.id)
            else:
                return

        if not self.channel_purged and self.static and self.text_channel:
            data = await self.bot.get_data(self.guild_id, db_name=DBModel.guilds)
            if data["player_controller"]["channel"] == str(self.text_channel.id):
                await self.channel_cleanup()
            else:
                self.channel_purged = True

        try:
            self.idle_task.cancel()
        except:
            pass

        if not self.controller_mode and self.idle_task:
            await self.message.delete()

        self.idle_task = None

        try:
            track = self.queue.popleft()

        except:

            try:

                track = None

                if self.autoplay or self.keep_connected:
                    try:
                        track = await self.get_autoqueue_tracks()
                    except:
                        traceback.print_exc()
                        self.locked = False
                        await asyncio.sleep(60)
                        if not self.current and (self.autoplay or self.keep_connected):
                            await self.process_next()
                        return

                if not track:
                    await self.stop()
                    now = disnake.utils.utcnow()
                    self.idle_start_timestamp = int(now.timestamp())
                    self.idle_endtime = now + datetime.timedelta(seconds=self.bot.config["IDLE_TIMEOUT"])
                    self.last_track = None
                    self.idle_task = self.bot.loop.create_task(self.idling_mode())
                    self.bot.dispatch("player_queue_end", player=self)
                    return

            except Exception:
                traceback.print_exc()
                track = None

        if not track:
            await self.process_next()
            return

        self.locked = True

        encoded_track = None

        if not self.auto_pause:

            if track.info["sourceName"] not in self.node.info["sourceManagers"] and not isinstance(track, PartialTrack):
                track.id = ""

            if isinstance(track, PartialTrack):

                if not track.id:
                    try:
                        await self.resolve_track(track)
                    except Exception as e:
                        try:
                            await self.text_channel.send(
                                embed=disnake.Embed(
                                    description=f"Houve um problema ao tentar processar a música [{track.title}]({track.uri})... "
                                                f"```py\n{repr(e)}```",
                                    color=self.bot.get_color()
                                )
                            )
                        except:
                            traceback.print_exc()

                        self.locked = False

                        await self.process_next()
                        return

                    if not track.id:
                        try:
                            await self.text_channel.send(
                                embed=disnake.Embed(
                                    description=f"A música [{track.title}]({track.uri}) não está disponível...\n"
                                                f"Pulando para a próxima música...",
                                    color=self.bot.get_color()
                                ), delete_after=10
                            )
                        except:
                            traceback.print_exc()

                        await asyncio.sleep(10)

                        self.locked = False

                        await self.process_next()
                        return

            partial_data = self.bot.pool.partial_track_cache.get(track.id)

            if not self.native_yt or not self.node.prefer_youtube_native_playback:

                if track.info["sourceName"] == "youtube" or (partial_data and partial_data[0].info["sourceName"] == "youtube"):

                    if (track.is_stream or track.duration > 480000):
                        if not self.native_yt:
                            self.played.append(track)
                            self.locked = False
                            await self.process_next()
                            return

                        try:
                            encoded_track = partial_data[0].id
                        except:
                            pass

                    else:
                        tracks = []

                        exceptions = ""

                        if not partial_data:

                            for provider in self.node.search_providers:

                                if provider in ("ytsearch", "ytmsearch"):
                                    continue

                                if track.author.endswith(" - topic"):
                                    query = f"{provider}:{track.title} - {track.author[:-8]}"
                                else:
                                    query = f"{provider}:{track.title}"

                                tracks = self.bot.pool.partial_track_cache.get(query)

                                if not tracks:

                                    try:
                                        tracks = await self.node.get_tracks(
                                            query, track_cls=LavalinkTrack, playlist_cls=LavalinkPlaylist
                                        )
                                    except:
                                        exceptions += f"{traceback.format_exc()}\n"
                                        await asyncio.sleep(1)
                                        continue

                                    try:
                                        tracks = tracks.tracks
                                    except AttributeError:
                                        pass

                                    self.bot.pool.partial_track_cache[query] = tracks

                                if not [i in track.title.lower() for i in exclude_tags]:
                                    final_result = []
                                    for t in tracks:
                                        if not any((i in t.title.lower()) for i in exclude_tags):
                                            final_result.append(t)
                                            break
                                    tracks = final_result or tracks

                                min_duration = track.duration - 7000
                                max_duration = track.duration + 7000

                                final_result = []

                                for t in tracks:
                                    if t.is_stream or not min_duration < t.duration < max_duration and fuzz.token_sort_ratio(t.title, track.title) < 75:
                                        continue
                                    final_result.append(t)

                                if not final_result:
                                    continue

                                tracks = final_result
                                break

                        else:
                            tracks = partial_data

                        if not tracks:

                            if not self.native_yt:

                                if exceptions:
                                    print(exceptions)
                                self.played.append(track)
                                self.set_command_log(emoji="⚠️", text=f"A música [`{track.title[:15]}`](<{track.uri}>) será pulada devido a falta de resultado "
                                                                      "em outras plataformas de música.")
                                await asyncio.sleep(3)
                                self.locked = False
                                await self.process_next()
                                return

                        else:
                            alt_track = tracks[0]
                            encoded_track = alt_track.id
                            self.bot.pool.partial_track_cache[f'youtube:{track.ytid}'] = [alt_track]
                            self.set_command_log(
                                emoji="▶️",
                                text=f"Tocando música obtida via metadados: [`{fix_characters(alt_track.title, 20)}`](<{alt_track.uri}>) `| Por: {fix_characters(alt_track.author, 15)}`"
                            )

            elif not track.id:

                await self.resolve_track(track)

                if not track.id:
                    try:
                        await self.text_channel.send(
                            embed=disnake.Embed(
                                description=f"A música [{track.title}]({track.uri}) não está disponível...\n"
                                            "Pulando para a próxima música...",
                                color=self.bot.get_color()
                            ), delete_after=10
                        )
                    except:
                        traceback.print_exc()

                    await asyncio.sleep(10)

                    self.locked = False

                    await self.process_next()
                    return

        self.last_track = track

        self.is_previows_music = False

        self.locked = False

        if track.is_stream:
            start_position = 0

        self.current = track
        self.last_update = 0
        self.last_position = start_position
        self.position_timestamp = 0
        self.paused = False

        self.process_hint()

        self.start_time = disnake.utils.utcnow()
        self.start_timestamp = self.start_time.timestamp()

        if self.auto_pause:
            self.last_update = time() * 1000
            self.current = track
            self.start_auto_skip()
            self.bot.loop.create_task(self.node.on_event(TrackStart({"track": track, "player": self,"node": self.node})))
            self.set_command_log(
                emoji="🪫",
                text="O player está no modo **[economia de recursos]** (esse modo será desativado automaticamente quando "
                     f"um membro entrar no canal <#{self.channel_id}>)."
            )
        else:
            await self.play(track, start=start_position, temp_id=encoded_track)

        # TODO: rever essa parte caso adicione função de ativar track loops em músicas da fila
        if self.loop != "current" or force_np or (not self.controller_mode and self.current.track_loops == 0):

            if start_position:
                await asyncio.sleep(1)

            await self.invoke_np(
                interaction=inter,
                force=True if (self.static or not self.loop or not self.is_last_message()) else False,
                rpc_update=True
            )

    async def process_idle_message(self):

        controller_opts = [
            disnake.SelectOption(
                emoji="<:add_music:588172015760965654>", value=PlayerControls.add_song, label="Adicionar música",
                description=f"Tocar nova música/playlist."
            ),
            disnake.SelectOption(
                emoji="⭐", value=PlayerControls.enqueue_fav, label="Adicionar favorito",
                description=f"Adicionar favorito na fila."
            ),
        ]

        if (played := len(self.played)) or self.last_track:

            try:
                play_txt = self.played[-1].title
            except:
                play_txt = self.last_track.title

            controller_opts.extend(
                [
                    disnake.SelectOption(
                        emoji="⏮️", value=PlayerControls.back, label="Voltar",
                        description=f"Ouvir novamente: {play_txt[:31]}"
                    ),
                    disnake.SelectOption(
                        label="Ativar a reprodução automática", emoji="🔄",
                        value=PlayerControls.autoplay,
                        description=f"Tocar música relacionadas a: {play_txt[:19]}"
                    ),
                ]
            )

        if played > 1:
            controller_opts.append(
                disnake.SelectOption(
                    emoji="↪️", value=PlayerControls.readd, label="Tocar novamente",
                    description=f"Tocar todas as músicas novamente ({played})"
                )
            )

        controller_opts.append(
            disnake.SelectOption(
                emoji="🛑", value=PlayerControls.stop, label="Finalizar",
                description=f"Finalizar o player e me desconectar do canal."
            ),
        )

        components = [
            disnake.ui.Select(
                placeholder="Executar uma ação:", options=controller_opts,
                custom_id="musicplayer_dropdown_idle", min_values=0, max_values=1
            )
        ]

        guild_data = await self.bot.get_data(self.guild.id, db_name=DBModel.guilds)

        opts = [disnake.SelectOption(label=k, value=k, description=v['description']) for k, v in
                guild_data["player_controller"]["fav_links"].items()]

        if opts:
            components.append(
                disnake.ui.Select(
                    placeholder="Tocar música/playlist do servidor.",
                    options=opts, custom_id="player_guild_pin"
                )
            )

        embed = disnake.Embed(
            description="**Não há músicas na fila... Adicione uma música ou use uma das opções abaixo.**",
            color=self.bot.get_color(self.guild.me)
        )

        embed.set_thumbnail(url=self.bot.user.display_avatar.replace(size=512, static_format="png").url)

        if not self.keep_connected:
            embed.description += "\n\n**Nota:** `O Player será desligado automaticamente` " \
                        f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=self.bot.config['IDLE_TIMEOUT'])).timestamp())}:R> " \
                        f"`caso nenhuma ação seja executada...`"

        kwargs = {
            "embed": embed,
            "content": None,
            "components": components,
            "allowed_mentions": self.allowed_mentions
        }

        try:
            if isinstance(self.text_channel.parent, disnake.ForumChannel) and self.static:
                kwargs["content"] = "💤 Aguardando por novas músicas..."
        except:
            pass

        try:
            if self.has_thread or self.static or self.text_channel.last_message_id == self.message.id:
                try:
                    await self.message.edit(**kwargs)
                except:
                    traceback.print_exc()
                    if self.text_channel and not self.static:
                        self.message = await self.text_channel.send(**kwargs)
                send_message = False
            else:
                send_message = True
        except AttributeError:
            send_message = True

        if send_message:
            try:
                await self.message.delete()
            except:
                pass
            self.message = await self.text_channel.send(**kwargs)

    async def idling_mode(self):

        try:
            vc = self.guild.me.voice.channel
        except AttributeError:
            vc = self.last_channel

        try:
            await self.process_rpc(vc)
        except:
            traceback.print_exc()

        try:
            await self.process_idle_message()
        except:
            traceback.print_exc()

        try:
            await self.update_stage_topic()
        except:
            pass

        if self.keep_connected:
            return

        await asyncio.sleep(self.bot.config["IDLE_TIMEOUT"])

        msg = "💤 **⠂O player foi desligado por inatividade...**"

        try:
            if self.static or self.has_thread:
                self.command_log = msg
            else:
                if self.text_channel:
                    embed = disnake.Embed(
                        description=msg, color=self.bot.get_color(self.guild.me))
                    self.bot.loop.create_task(self.text_channel.send(
                        embed=embed, delete_after=120, allowed_mentions=self.allowed_mentions))
        except:
            traceback.print_exc()

        await self.destroy()

    def set_command_log(self, text="", emoji=""):
        self.command_log = text
        self.command_log_emoji = emoji

    async def update_stage_topic(self, reconnect=True, clear=False):

        if not self.guild.me.voice:
            if reconnect:
                await self.connect(self.last_channel.id)
            return

        if not self.stage_title_event:
            return

        if clear:
            if isinstance(self.guild.me.voice.channel, disnake.VoiceChannel) and self.last_stage_title:
                await self.bot.edit_voice_channel_status(status=None, channel_id=self.guild.me.voice.channel.id)
            return

        msg = None

        if self.current:

            requester = self.guild.get_member(self.current.requester)

            if requester:
                requester_name = str(requester.display_name)
            else:
                requester_name = "Membro desconhecido"

            if not self.current.is_stream and (not self.auto_pause or not self.paused):
                if isinstance(self.guild.me.voice.channel, disnake.StageChannel):
                    timestamp = str(self.current.duration)
                else:
                    timestamp = f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=self.current.duration - self.position)).timestamp())}:R>"
            else:
                timestamp = ("pausado" if (self.paused) else "🔴") + (f" <t:{int(disnake.utils.utcnow().timestamp())}:R>") if not self.current.is_stream else ""

            msg = self.stage_title_template \
                .replace("{track.title}", self.current.single_title) \
                .replace("{track.author}", self.current.authors_string) \
                .replace("{track.duration}",
                         time_format(self.current.duration) if not self.current.is_stream else "Livestream") \
                .replace("{track.source}", self.current.info.get("sourceName", "desconhecido")) \
                .replace("{track.playlist}", self.current.playlist_name or "Sem playlist") \
                .replace("{requester.name}", requester_name) \
                .replace("{requester.id}", str(self.current.requester)) \
                .replace("{track.timestamp}", timestamp)

        if isinstance(self.guild.me.voice.channel, disnake.StageChannel):

            if not self.guild.me.guild_permissions.manage_guild:
                return

            if msg is not None:
                msg = msg.replace("{track.emoji}", "♪")

                if len(msg) > 110:
                    msg = msg[:107] + "..."

            if not msg:
                msg = "Status: Aguardando por novas músicas."
            else:
                emojis = emoji_pattern.findall(msg)
                for emoji in emojis:
                    msg = msg.replace(emoji, '')

            if not self.guild.me.voice.channel.instance:
                func = self.guild.me.voice.channel.create_instance
            elif msg == self.last_stage_title:
                return
            else:
                func = self.guild.me.voice.channel.instance.edit

            await func(topic=msg)

        else:  # voicechannel

            if msg is not None:

                msg = msg.replace("{track.emoji}", music_source_emoji(self.current.info["sourceName"]))

                if len(msg) > 496:
                    msg = msg[:496] + "..."

            if msg == self.last_stage_title:
                return

            try:
                await self.bot.edit_voice_channel_status(status=msg, channel_id=self.guild.me.voice.channel.id)
            except Exception as e:
                if isinstance(e, disnake.Forbidden):
                    self.stage_title_event = False
                    self.set_command_log(emoji="❌", text="O status automático foi desativado devido a falta de permissão pra alterar status.")
                    self.update = True
                print(traceback.format_exc())

        self.last_stage_title = msg

    def start_message_updater_task(self):
        try:
            self.message_updater_task.cancel()
        except AttributeError:
            pass
        self.message_updater_task = self.bot.loop.create_task(self.message_updater())

    async def invoke_np(self, force=False, interaction=None, rpc_update=False):

        if not self.text_channel:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
            return

        if not self.current:
            if not force:
                try:
                    if not interaction.response.is_done():
                        await interaction.response.defer()
                except:
                    pass
            else:
                await self.process_idle_message()
            return

        if self.updating and not force:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
            return

        if rpc_update:

            try:
                await self.process_rpc()
            except:
                traceback.print_exc()

        if self.retry_setup_hints:
            self.setup_hints()
            self.retry_setup_hints = False

        try:
            if self.static:
                if self.skin_static.startswith("> custom_skin: "):
                    data = skin_converter(self.custom_skin_static_data[self.skin_static[15:]], player=self, guild=self.guild)
                else:
                    data = self.bot.pool.player_static_skins[self.skin_static].load(self)

            else:
                if self.skin.startswith("> custom_skin: "):
                    data = skin_converter(self.custom_skin_data[self.skin[15:]], player=self, guild=self.guild)
                else:
                    data = self.bot.pool.player_skins[self.skin].load(self)
        except OverflowError:
            await self.process_next()
            return

        if data == self.last_data:

            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
            return

        self.last_data = data

        try:
            if self.static and isinstance(self.text_channel.parent, disnake.ForumChannel):
                data["content"] = f"`{'▶️' if not self.paused else '⏸️'} {fix_characters(self.current.title, 50)}` |\n\n" + (data.get("content") or "")
        except:
            pass

        if not self.controller_mode:

            if self.temp_embed:
                data["embeds"].insert(0, self.temp_embed)
                self.temp_embed = None

            self.updating = True

            if self.keep_connected:
                if not self.is_last_message():
                    await self.destroy_message()
                elif self.text_channel:
                    if not self.text_channel.permissions_for(self.guild.me).send_messages:
                        self.text_channel = None
                        self.message = None
                    else:
                        try:
                            await self.message.edit(allowed_mentions=self.allowed_mentions, **data)
                        except disnake.Forbidden:
                            self.message = None
                            self.text_channel = None
                        except:
                            self.message = await self.text_channel.send(allowed_mentions=self.allowed_mentions, **data)

            else:
                try:
                    self.message_updater_task.cancel()
                except:
                    pass
                self.message = await self.text_channel.send(allowed_mentions=self.allowed_mentions, **data)

            self.updating = False

        else:

            # nenhum controle de botão foi definido na skin (será usado os botões padrões).
            if data.get("components") is None:

                # Aviso: Não modifique os components abaixo, prefira copiar uma das skins da pasta utils -> music -> skins
                # e deixá-la com outro nome (sem acentos, espaços, caracteres especiais) e modifique-as a seu gosto.
                # Caso queira deixar uma skin customizada por padrão adicione/modifique a config DEFAULT_SKIN="tuaskin"

                data["components"] = [
                    disnake.ui.Button(
                        emoji="⏯️", custom_id=PlayerControls.pause_resume, style=get_button_style(self.paused)),
                    disnake.ui.Button(
                        emoji="⏮️", custom_id=PlayerControls.back),
                    disnake.ui.Button(
                        emoji="⏹️", custom_id=PlayerControls.stop),
                    disnake.ui.Button(
                        emoji="⏭️", custom_id=PlayerControls.skip),
                    disnake.ui.Button(
                        emoji="<:music_queue:703761160679194734>", custom_id=PlayerControls.queue,
                        disabled=not (self.queue or self.queue_autoplay)),
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
                                label=f"Volume: {self.volume}%", emoji="🔊",
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
                                label=("Desativar" if self.nightcore else "Ativar") + " o efeito nightcore", emoji="🇳",
                                value=PlayerControls.nightcore,
                                description="Efeito que aumenta velocidade e tom da música."
                            ),
                            disnake.SelectOption(
                                label=("Desativar" if self.autoplay else "Ativar") + " a reprodução automática",
                                emoji="🔄",
                                value=PlayerControls.autoplay,
                                description="Sistema de reprodução de música automática quando a fila tiver vazia."
                            ),
                            disnake.SelectOption(
                                label="Last.fm scrobble", emoji="<:Lastfm:1278883704097341541>",
                                value=PlayerControls.lastfm_scrobble,
                                description="Ativar/desativar o scrobble/registro de músicas na sua conta do last.fm."
                            ),
                            disnake.SelectOption(
                                label=("Desativar" if self.restrict_mode else "Ativar") + " o modo restrito",
                                emoji="🔐",
                                value=PlayerControls.restrict_mode,
                                description="Apenas DJ's/Staff's podem usar comandos restritos."
                            ),
                        ]
                    ),
                ]

                if self.static:
                    if (queue := self.queue or self.queue_autoplay):
                        data["components"].append(
                            disnake.ui.Select(
                                placeholder="Próximas músicas:",
                                custom_id="musicplayer_queue_dropdown",
                                min_values=0, max_values=1,
                                options=[
                                    disnake.SelectOption(
                                        label=f"{n + 1}. {fix_characters(t.author, 18)}",
                                        description=fix_characters(t.title, 47),
                                        value=f"{n:02d}.{t.title[:96]}"
                                    ) for n, t in enumerate(itertools.islice(queue, 25))
                                ]
                            )
                        )

                if self.current.ytid and self.node.lyric_support:
                    data["components"][5].options.append(
                        disnake.SelectOption(
                            label="Visualizar letras", emoji="📃",
                            value=PlayerControls.lyrics,
                            description="Obter letra da música atual."
                        )
                    )

                if self.mini_queue_feature:
                    data["components"][5].options.append(
                        disnake.SelectOption(
                            label="Mini-fila do player", emoji="<:music_queue:703761160679194734>",
                            value=PlayerControls.miniqueue,
                            description="Ativar/Desativar a mini-fila do player."
                        )
                    )

                if isinstance(self.last_channel, disnake.VoiceChannel):
                    data["components"][5].options.append(
                        disnake.SelectOption(
                            label="Status automático", emoji="📢",
                            value=PlayerControls.set_voice_status,
                            description="Configurar o status automático do canal de voz."
                        )
                    )

                if not self.static and not self.has_thread:
                    data["components"][5].options.append(
                        disnake.SelectOption(
                            label="Song-Request Thread", emoji="💬",
                            value=PlayerControls.song_request_thread,
                            description="Criar uma thread/conversa temporária para pedir músicas usando apenas o nome/link."
                        )
                    )

            self.updating = True

            if interaction:
                try:
                    if interaction.response.is_done():
                        await interaction.message.edit(allowed_mentions=self.allowed_mentions, **data)
                    else:
                        await interaction.response.edit_message(allowed_mentions=self.allowed_mentions,
                                                                **data)
                    self.updating = False
                except:
                    traceback.print_exc()
                else:
                    self.start_message_updater_task()
                return

            else:

                if self.message and (
                        self.ignore_np_once or self.has_thread or self.static or not force or self.is_last_message()):

                    self.ignore_np_once = False

                    try:

                        try:
                            await self.message.edit(allowed_mentions=self.allowed_mentions, **data)
                            await asyncio.sleep(0.5)
                        except asyncio.CancelledError:
                            traceback.print_exc()
                            return
                        except:
                            traceback.print_exc()
                            self.text_channel = self.bot.get_channel(self.text_channel.id)

                            if not self.text_channel:
                                self.message = None
                                return

                            if isinstance(self.text_channel, disnake.Thread):

                                if not self.text_channel.parent.permissions_for(
                                        self.guild.me).send_messages_in_threads or not self.text_channel.permissions_for(
                                        self.guild.me).read_messages:
                                    return

                                if self.text_channel.locked:

                                    if not self.text_channel.parent.permissions_for(self.guild.me).manage_threads:
                                        self.text_channel = None
                                        self.message = None
                                        return
                                    else:
                                        await self.text_channel.edit(archived=False, locked=False)

                                elif self.text_channel.archived:

                                    if self.text_channel.owner_id == self.bot.user.id:
                                        await self.text_channel.edit(archived=False)
                                    else:
                                        await self.text_channel.send("Desarquivando o tópico.", delete_after=2)

                                #elif ((
                                #              self.text_channel.archive_timestamp - disnake.utils.utcnow()).total_seconds() / 60) < (
                                #thread_archive_time[self.text_channel.auto_archive_duration]):
                                #    await self.text_channel.send("Evitando o tópico auto-arquivar...", delete_after=2)

                            elif not self.text_channel.permissions_for(
                                    self.guild.me).send_messages or not self.text_channel.permissions_for(
                                    self.guild.me).read_messages:
                                return

                        self.start_message_updater_task()
                        self.updating = False
                        return
                    except Exception as e:
                        self.updating = False
                        traceback.print_exc()
                        if self.static or self.has_thread:
                            self.set_command_log(
                                f"{(interaction.author.mention + ' ') if interaction else ''}houve um erro na interação: {repr(e)}",
                                "⚠️")
                            self.update = True
                            return

            await self.destroy_message()

            if not self.message:

                try:
                    self.message = await self.text_channel.send(allowed_mentions=self.allowed_mentions,
                                                                **data)
                except:
                    traceback.print_exc()
                else:
                    if self.static:
                        await self.channel_cleanup()
                        data = await self.bot.get_data(self.guild_id, db_name=DBModel.guilds)
                        data['player_controller']['channel'] = str(self.text_channel.id)
                        data['player_controller']['message_id'] = str(self.message.id)
                        await self.bot.update_data(self.guild_id, data, db_name=DBModel.guilds)

            self.start_message_updater_task()

        self.updating = False

    async def set_pause(self, pause: bool) -> None:
        await super().set_pause(pause)
        self.start_timestamp = (disnake.utils.utcnow() - datetime.timedelta(milliseconds=self.position)).timestamp()
        self.bot.dispatch("player_pause" if pause else "player_resume", player=self)

    async def destroy_message(self):

        try:
            self.message_updater_task.cancel()
        except:
            pass

        if self.static:
            return

        try:
            if self.guild.me:
                await self.message.delete()
        except:
            pass

        self.message = None

    def is_last_message(self):

        try:
            return self.last_message_id == self.message.id
        except AttributeError:
            return

    async def message_updater(self):

        while True:

            if not self.text_channel or not self.controller_mode:
                pass

            elif self.auto_update and not self.current.is_stream:

                await asyncio.sleep(self.auto_update)

                try:
                    await self.invoke_np()
                except:
                    traceback.print_exc()

                continue

            elif self.update:

                try:
                    await self.invoke_np()
                except:
                    traceback.print_exc()

                self.update = False

                await asyncio.sleep(5)

            await asyncio.sleep(10)

    async def update_message(self, interaction: disnake.Interaction = None, force=False, rpc_update=False):

        if rpc_update:
            await self.process_rpc()

        if force or (interaction and not interaction.response.is_done()):
            if self.controller_mode or interaction:
                await self.invoke_np(interaction=interaction)

        else:
            self.update = True

    async def cleanup(self, inter: disnake.MessageInteraction = None):

        self.queue.clear()
        self.played.clear()

        try:
            self.reconnect_voice_channel_task.cancel()
        except:
            pass

        try:
            self.members_timeout_task.cancel()
        except:
            pass

        try:
            self.auto_skip_track_task.cancel()
        except:
            pass

        try:
            self._queue_updater_task.cancel()
        except:
            pass

        try:
            self.hook_event_task.cancel()
        except:
            pass

        try:
            vc = self.guild.voice_client.channel
        except:
            vc = self.last_channel

        try:
            await self.process_rpc(vc, close=True)
        except:
            traceback.print_exc()

        if self.guild.me:

            self.bot.loop.create_task(self.update_stage_topic(reconnect=False, clear=True))

            if self.static:

                try:
                    await send_idle_embed(inter or self.message, self.command_log, bot=self.bot)
                except:
                    traceback.print_exc()
                    pass

                #await self.channel_cleanup()

            else:

                try:
                    if self.has_thread:

                        try:
                            if inter.message.id == self.message.id:
                                func = inter.response.edit_message
                            else:
                                func = self.message.edit
                        except AttributeError:
                            try:
                                func = self.message.edit
                            except AttributeError:
                                func = None

                        if func:
                            try:
                                await func(
                                    embed=disnake.Embed(
                                        description=self.command_log,
                                        color=self.bot.get_color(self.guild.me)
                                    ), allowed_mentions=self.allowed_mentions,
                                    components=song_request_buttons
                                )
                                channel: disnake.Thread = self.bot.get_channel(self.message.id)

                                if channel.parent.permissions_for(self.guild.me).send_messages_in_threads:
                                    try:
                                        await channel.send(
                                            embed=disnake.Embed(
                                                color=self.bot.get_color(self.guild.me),
                                                description="**A sessão de pedido de música da conversa atual foi encerrada.**",
                                            )
                                        )
                                    except:
                                        pass

                                if channel.owner.id == self.bot.user.id or channel.parent.permissions_for(
                                        self.guild.me).manage_threads:
                                    kwargs = {"archived": True, "locked": True}
                                else:
                                    kwargs = {}

                                await channel.edit(**kwargs)
                            except Exception:
                                print(
                                    f"Falha ao arquivar thread do servidor: {self.guild.name}\n{traceback.format_exc()}")

                    elif inter:

                        await inter.response.edit_message(
                            content=None,
                            embed=disnake.Embed(
                                description=f"🛑 ⠂{self.command_log}",
                                color=self.bot.get_color(self.guild.me)),
                            view=None
                        )

                    elif self.controller_mode is True:
                        await self.destroy_message()

                except Exception:
                    traceback.print_exc()

        try:
            self.message_updater_task.cancel()
        except:
            pass
        self.message_updater_task = None

        try:
            self._new_node_task.cancel()
        except:
            pass
        self._new_node_task = None

        try:
            self.idle_task.cancel()
        except:
            pass
        self.idle_task = None

    async def auto_skip_track(self):

        if not self.controller_mode or not self.current:
            return

        try:

            try:
                if self.current.is_stream:
                    return
            except AttributeError:
                pass

            retries = 5

            sleep_time = None

            while retries > 0:

                try:
                    sleep_time = (self.current.duration - self.position) / 1000
                    break
                except AttributeError:
                    await asyncio.sleep(5)
                    retries -= 1
                    continue

            await asyncio.sleep(sleep_time or (self.current.duration / 1000))
            self.current = None
            self.last_update = 0
            self.bot.loop.create_task(self.node.on_event(TrackEnd({"track": self.current, "player": self, "node": self.node, "reason": "FINISHED"})))
            return

        except asyncio.CancelledError:
            return

        except Exception:
            traceback.print_exc()
            return

    async def resolve_track(self, track: PartialTrack):

        if track.id:
            return

        check_duration = True

        try:

            exceptions = []
            selected_track = None

            if track.info["sourceName"] == "http":
                tracks = []
                search_queries = [track.uri or track.search_uri]
            else:
                tracks = self.bot.pool.partial_track_cache.get(f'{track.info["sourceName"]}:{track.author}-{track.single_title}') or []
                search_queries = []

            if not tracks:

                if not search_queries:

                    if track.info["sourceName"] in self.node.info.get("sourceManagers", []) and (not self.node.only_use_native_search_providers or track.info["sourceName"] in native_sources):
                        search_queries = [track.uri]
                    else:
                        search_queries = []
                        for sp in self.node.partial_providers:
                            if "{isrc}" in sp:
                                if isrc := track.info.get('isrc'):
                                    search_queries.append(sp.replace("{isrc}", isrc))
                                continue
                            search_queries.append(sp.replace("{title}", track.single_title).replace("{author}", ", ".join(track.authors)))

                for query in search_queries:

                    try:
                        tracks = (await self.node.get_tracks(query, track_cls=LavalinkTrack,
                                                             playlist_cls=LavalinkPlaylist))
                    except Exception as e:
                        if track.info["sourceName"] == "youtube" and any(e in str(e) for e in (
                            "This video is not available",
                            "YouTube WebM streams are currently not supported.",
                            "Video returned by YouTube isn't what was requested",
                            "The video returned is not what was requested.",
                        )
                               ):
                            cog = self.bot.get_cog("Music")
                            cog.remove_provider(self.node.search_providers, ["ytsearch", "ytmsearch"])
                            cog.remove_provider(self.node.partial_providers, ["ytsearch:\"{isrc}\"",
                                                                              "ytsearch:\"{title} - {author}\"",
                                                                              "ytmsearch:\"{isrc}\"",
                                                                              "ytmsearch:\"{title} - {author}\"",
                                                                              ])
                            self.native_yt = False
                            await self.resolve_track(track)
                            return
                        exceptions.append(e)
                        continue

                    try:
                        tracks = tracks.tracks
                    except AttributeError:
                        pass

                    self.bot.pool.partial_track_cache[f'{track.info["sourceName"]}:{track.author}-{track.single_title}'] = tracks

                    try:
                        if tracks[0].info["sourceName"] == "bandcamp":
                            check_duration = False
                    except:
                        pass

                    has_exclude_tags = any(tag for tag in exclude_tags if tag.lower() in track.title.lower())

                    for t in tracks:

                        if t.is_stream or fuzz.token_sort_ratio(t.title, track.title) < 80:
                            continue

                        if not has_exclude_tags and any(tag for tag in exclude_tags if tag.lower() in t.title.lower()):
                            continue

                        if check_duration and ((t.duration - 10000) < track.duration < (t.duration + 10000)):
                            selected_track = t
                            break

                    if not tracks:
                        continue

                    break

            if not tracks:
                if exceptions:
                    print("Falha ao resolver PartialTrack:\n" + "\n".join(repr(e) for e in exceptions))
                return

            if not selected_track:
                selected_track = tracks[0]

            track.id = selected_track.id
            track.info["length"] = selected_track.duration
            track.info["sourceNameOrig"] = selected_track.info["sourceName"]
            if not track.info["author"]:
                track.info["author"] = selected_track.author
            if not track.duration:
                track.info["duration"] = selected_track.duration
            if not track.thumb:
                track.info["artworkUrl"] = selected_track.thumb

        except Exception as e:
            traceback.print_exc()
            embed = disnake.Embed(
                description=f"**Falha ao obter informação de PartialTrack:\n[{track.title}]({track.uri or track.search_uri})** ```py\n{repr(e)}```\n"
                            f"**Servidor de música:** `{self.node.identifier}`",
                color=disnake.Colour.red())
            await self.report_error(embed, track)
            return

        return

    async def _wait_for_new_node(self, txt: str = None, ignore_node: wavelink.Node = None):

        if self.node.is_available:
            return

        self.locked = True

        try:
            self.auto_skip_track_task.cancel()
        except:
            pass

        try:

            original_identifier = str(self.node.identifier)

            self.set_command_log(
                txt or "Não há servidores de música disponível. Irei fazer algumas tentativas de conectar em um novo servidor de música.",
                emoji="⏰"
            )
            self.update = True

            while True:

                node = self.bot.music.get_best_node(ignore_node=ignore_node)

                if not node:
                    await asyncio.sleep(5)
                    continue

                self.native_yt = True

                try:
                    self.node.players[self.guild_id]
                except KeyError:
                    return

                try:
                    if node == self.node and self.guild.me.voice and self._voice_state:
                        await self._dispatch_voice_update()
                    else:
                        await self.change_node(node.identifier)
                except:
                    await asyncio.sleep(5)
                    continue

                if not self.guild.me.voice:
                    try:
                        can_connect(self.last_channel, self.guild, bot=self.bot)
                    except Exception as e:
                        print(traceback.format_exc())
                        self.set_command_log(f"O player foi finalizado devido ao erro: {e}")
                        await self.destroy()
                        return
                    await self.connect(self.last_channel.id)

                self.locked = False

                if self.current:
                    self.queue.appendleft(self.current)
                    start_position = self.position
                    self.current = None
                else:
                    start_position = 0

                await self.process_next(start_position=start_position)

                try:
                    if not self.auto_pause:
                        if original_identifier != node.identifier:
                            txt = f"O player foi movido para o servidor de música **{node.identifier}**."
                        else:
                            txt = f"O player foi reconectado no servidor de músca **{self.node.identifier}**"
                        self.set_command_log(emoji="📶", text=txt)
                        self.update = True
                except:
                    print(traceback.format_exc())
                self._new_node_task = None
                return
        except Exception:
            traceback.print_exc()

    async def _send_rpc_data(self, users: List[int], stats: dict):

        for u in users:

            stats["user"] = u

            data = await self.bot.get_global_data(id_=u, db_name=DBModel.users)

            if self.bot.config["ENABLE_RPC_AUTH"] and not data["token"]:
                continue

            stats.update(
                {"token": data["token"], "lastfm_user": data["lastfm"]["username"]}
            )

            try:
                await self.bot.ws_client.send(stats)
            except Exception:
                print(traceback.format_exc())

    async def process_rpc(
            self,
            voice_channel: Union[disnake.VoiceChannel, disnake.StageChannel] = None,
            close=False,
            users: List[int] = None,
            wait: bool = False
    ):
        try:
            if not voice_channel and not close:

                try:
                    voice_channel = self.bot.get_channel(self.channel_id) or self.bot.get_channel(
                        self.guild.voice_client.channel.id)
                except AttributeError:
                    voice_channel = self.last_channel

            if not users:
                try:
                    users = voice_channel.voice_states
                except AttributeError:
                    # TODO: Investigar possível bug ao mover o bot de canal pelo discord.
                    return

            thumb = self.bot.user.display_avatar.replace(
                size=512, static_format="png").url

            users = [u for u in users if u != self.bot.user.id]

            if close:

                stats = {
                    "op": "close",
                    "bot_id": self.bot.user.id,
                    "bot_name": str(self.bot.user),
                    "thumb": thumb,
                    "auth_enabled": self.bot.config["ENABLE_RPC_AUTH"]
                }

                if wait:
                    await self._send_rpc_data(users, stats)
                else:
                    try:
                        self._rpc_update_task.cancel()
                    except:
                        pass
                    self._rpc_update_task = self.bot.loop.create_task(self._send_rpc_data(users, stats))
                return

            if self.is_closing:
                return

            stats = {
                "op": "update",
                "track": None,
                "bot_id": self.bot.user.id,
                "bot_name": str(self.bot.user),
                "thumb": thumb,
                "guild": self.guild.name,
                "auth_enabled": self.bot.config["ENABLE_RPC_AUTH"],
                "listen_along_invite": self.listen_along_invite
            }

            if not self.current:

                try:
                    bot_public = self.bot.appinfo.bot_public
                except AttributeError:
                    bot_public = False

                stats.update(
                    {
                        "op": "idle",
                        "bot_id": self.bot.user.id,
                        "invite_permissions": self.bot.config["INVITE_PERMISSIONS"],
                        "bot_name": str(self.bot.user),
                        "public": bot_public,
                        "support_server": self.bot.config["SUPPORT_SERVER"],
                    }
                )

                try:
                    stats["idle_endtime"] = int(self.idle_endtime.timestamp())
                    stats["idle_starttime"] = self.idle_start_timestamp
                except:
                    pass

            else:

                track: Union[LavalinkTrack, PartialTrack] = self.current

                stats["track"] = {
                    "source": track.info["sourceName"],
                    "thumb": track.thumb if len(track.thumb) < 257 else "",
                    "title": track.single_title,
                    "url": track.uri,
                    "author": track.authors_string,
                    "stream": track.is_stream,
                    "position": self.position,
                    "paused": self.is_paused,
                    "requester_id": track.requester,
                    "loop": self.current.track_loops or self.loop,
                    "queue": len(self.queue),
                    "247": self.keep_connected,
                    "autoplay": self.current.autoplay,
                }

                stats["start_time"] = self.start_timestamp

                if self.current.is_stream:
                    stats["track"]["duration"] = int(self.start_time.timestamp())
                else:
                    stats["track"]["duration"] = track.duration

                if track.playlist_name:
                    stats["track"].update(
                        {
                            "playlist_name": track.playlist_name,
                            "playlist_url": track.playlist_url,
                        }
                    )

                if track.album_name:
                    stats["track"].update(
                        {
                            "album_name": track.album_name,
                            "album_url": track.album_url,
                        }
                    )

            if wait:
                await self._send_rpc_data(users, stats)
            else:

                try:
                    self._rpc_update_task.cancel()
                except:
                    pass

                self._rpc_update_task = self.bot.loop.create_task(self._send_rpc_data(users, stats))

        except Exception:
            traceback.print_exc()

    async def process_save_queue(self, create_task=True):

        if self._session_resuming:
            await asyncio.sleep(10)
            self._session_resuming = False
            return

        if self._queue_updater_task and self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            return

        cog = self.bot.get_cog("PlayerSession")

        if not cog:
            return

        try:
            self._queue_updater_task.cancel()
        except:
            pass

        await cog.save_info(self)

        if create_task:
            self._queue_updater_task = self.bot.loop.create_task(cog.queue_updater_task(self))

    async def track_end(self, ignore_track_loop=False):

        self.votes.clear()

        self.locked = True

        await asyncio.sleep(0.5)

        if self.last_track:

            if not self.last_track.is_stream and self.last_track.duration < 60000:
                await asyncio.sleep(7)

            if self.loop == "current":
                self.queue.appendleft(self.last_track)
            elif self.is_previows_music:
                self.queue.insert(1, self.last_track)
                self.is_previows_music = False
            elif self.last_track.track_loops and not ignore_track_loop:
                self.last_track.info["extra"]["track_loops"] -= 1
                self.queue.insert(0, self.last_track)
            elif self.loop == "queue": # or self.keep_connected:
                if self.is_previows_music:
                    self.queue.insert(1, self.last_track)
                    self.is_previows_music = False
                else:
                    self.queue.append(self.last_track)
            elif not self.last_track.autoplay:
                self.played.append(self.last_track)

        elif self.is_previows_music:
            self.is_previows_music = False

        self.locked = False

    async def destroy(self, *, force: bool = False, inter: disnake.MessageInteraction = None):
        self.bot.loop.create_task(self.process_destroy(force=force, inter=inter))

    async def process_destroy(self, force: bool = False, inter: disnake.MessageInteraction = None):

        if self.is_closing:
            return

        self.is_closing = True

        await self.cleanup(inter)

        try:
            channel = self.guild.voice_client.channel
        except AttributeError:
            channel = self.last_channel

        if isinstance(channel,
                      disnake.StageChannel) and self.stage_title_event and self.guild.me and self.guild.me.guild_permissions.manage_channels:

            if channel.instance:
                try:
                    await channel.instance.delete()
                except Exception:
                    traceback.print_exc()

        await super().destroy(force=force, guild=self.guild)

        self.bot.dispatch("player_destroy", player=self)

    #######################
    #### Filter Stuffs ####
    #######################

    async def seek(self, position: int = 0) -> None:
        self.last_position = position
        await super().seek(position=position)
        self.start_timestamp = (disnake.utils.utcnow() - datetime.timedelta(milliseconds=self.position)).timestamp()
        self.bot.dispatch("player_seek", player=self, position=position)

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
        if self.node.version == 3:
            await self.node._send(op="filters", **self.filters, guildId=str(self.guild_id))
        else:
            await self.node.update_player(guild_id=self.guild_id, data={"filters": self.filters})

    async def set_filter(self, filter_type: AudioFilter):

        self.filters.update(filter_type.filter)
        await self.update_filters()

        return filter_type


def music_mode(bot: BotCore):
    return wavelink.Client(bot=bot)
