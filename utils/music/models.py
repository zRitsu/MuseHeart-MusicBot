from __future__ import annotations
import datetime
import os
import random
from functools import partial
from itertools import cycle
import disnake
import ctypes.util
import asyncio
import wavelink
from urllib import parse
from .converters import fix_characters, time_format, get_button_style
from .filters import AudioFilter
from ..others import send_idle_embed, PlayerControls
from .spotify import SpotifyTrack
import traceback
from collections import deque
from typing import Optional, Union, TYPE_CHECKING, List
from yt_dlp import YoutubeDL, utils as ytdlp_utils

if TYPE_CHECKING:
    from ..client import BotCore


class LavalinkTrack(wavelink.Track):
    __slots__ = ('requester', 'playlist', 'track_loops', 'album', 'single_title', 'authors_md', 'authors_string')

    def __init__(self, *args, **kwargs):
        self.requester = kwargs.pop('requester')
        self.playlist = kwargs.pop('playlist', None)
        self.track_loops = kwargs.pop('track_loops', 0)
        self.album = {}
        args[1]['title'] = fix_characters(args[1]['title'])
        super().__init__(*args, **kwargs)
        self.single_title = self.title
        self.authors_md = f"`{self.author}`"
        self.authors_string = self.author

        if self.ytid:
            self.thumb = f"https://img.youtube.com/vi/{self.ytid}/mqdefault.jpg"
        elif "soundcloud.com" in self.uri:
            self.thumb = self.info.get("artworkUrl", "").replace('large.jpg', 't500x500.jpg')
        else:
            self.thumb = self.info.get("artworkUrl", "")

        if self.info.get("sourceName") == "youtube" and self.playlist:
            try:
                self.uri = f"{self.uri}&list={parse.parse_qs(parse.urlparse(self.playlist['url']).query)['list'][0]}"
            except KeyError:
                pass


class YTDLTrack:
    __slots__ = ('author', 'id', 'title', 'uri', 'duration', 'is_stream', 'info',
                 'requester', 'playlist', 'album', 'track_loops', 'thumb', 'single_title',
                 'authors_md', 'authors_string')

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
        self.playlist = kwargs.pop('playlist', None)
        self.album = {}
        self.track_loops = kwargs.pop('track_loops', 0)

        self.single_title = self.title
        self.authors_md = f"`{self.author}`"
        self.authors_string = self.author

        if (data.get("ie_key") or data.get('extractor_key')) == "Youtube":
            self.info["class"] = "YoutubeAudioTrack"
            self.thumb = f"https://img.youtube.com/vi/{data['id']}/mqdefault.jpg"
            if self.playlist:
                try:
                    self.uri = f"{self.uri}&list={parse.parse_qs(parse.urlparse(self.playlist['url']).query)['list'][0]}"
                except KeyError:
                    pass
        else:
            self.info["class"] = data.pop("extractor_key", "")
            self.thumb = data.get('thumbnail', '')


class YTDLPlaylist:

    __slots__ = ('data', 'tracks')

    def __init__(self, data: dict, playlist: dict):
        self.data = data

        self.tracks = [
            YTDLTrack(
                data=i,
                playlist=playlist
            ) for i in data['tracks'] if i.get('duration')]


class BasePlayer:
    volume: int
    node: wavelink.Node
    paused: bool
    position: int
    is_paused: bool
    channel_id: Optional[int]
    current: Union[LavalinkTrack, YTDLTrack, SpotifyTrack]

    def __init__(self, *args, **kwargs):

        self.bot: BotCore = kwargs.pop('bot', None)

        try:
            super().__init__(*args, **kwargs)
        except:
            pass
        self.guild: disnake.Guild = kwargs.pop('guild')
        self.text_channel: disnake.TextChannel = kwargs.pop('channel')
        self.message: Optional[disnake.Message] = kwargs.pop('message', None)
        self.static: bool = kwargs.pop('static', False)
        self.request_channel: bool = kwargs.pop("request_channel", False)
        self.skin = self.bot.player_skins[kwargs.pop("skin", None) or self.bot.default_skin]
        self.queue: deque = deque()
        self.played: deque = deque(maxlen=20)
        self.nightcore: bool = False
        self.loop = False
        self.last_track: Optional[LavalinkTrack] = None
        self.locked: bool = False
        self.is_previows_music: bool = False
        self.interaction_cooldown: bool = False
        self.votes: set = set()
        self.dj: set = set()
        self.filters: dict = {}
        self.idle_task: Optional[asyncio.Task] = None
        self.members_timeout_task: Optional[asyncio.Task] = None
        self.idle_timeout = self.bot.config["IDLE_TIMEOUT"]
        self.hint_rate = self.bot.config["HINT_RATE"]
        self.command_log: str = ""
        self.command_log_emoji: str = ""
        self.is_closing: bool = False
        self.last_message_id: Optional[int] = None
        self.nonstop: bool = False
        self.update: bool = False
        self.updating: bool = False
        self.auto_update: int = 0
        self.message_updater_task: Optional[asyncio.Task] = self.bot.loop.create_task(self.message_updater())
        self.restrict_mode = kwargs.pop('restrict_mode', False) # limitar apenas para dj's e staff's
        self.ignore_np_once = False  # não invocar player controller em determinadas situações
        self.allowed_mentions = disnake.AllowedMentions(users=False, everyone=False, roles=False)
        self.controller_mode = True  # ativar/desativar modo controller (apenas para uso em skins)

        self.initial_hints = [
            "Você pode usar o botão [🎶] para pedir músicas ou adicionar um link de música/playlist/favorito na fila.",

            "Você pode alterar a skin/aparência do player usando o comando /change_skin (comando vísivel apenas membros"
            " com perm de: gerenciar servidor).",

            "Crie favoritos para ter fácil acesso de usar seus links favoritos aqui dispensando ter que copiar e colar "
            "seus links nos comandos. Experimente usando o comando: /fav add.",
        ]

        requester: disnake.Member = kwargs.pop('requester')

        if not requester.guild_permissions.manage_channels:
            self.dj.add(requester)

        self.hints: cycle = []
        self.current_hint = ""
        self.setup_hints()

        self.bot.dispatch("player_create", player=self)

    def __repr__(self):
        return f"<volume={self.volume} " \
               f"current_position={time_format(self.position) if self.position else 'Idling'} " \
               f"queue={len(self.queue)} loop={self.loop} EQ=\"{self.eq}\" guild=\"{self.guild.name}\" " \
               f"node=\"{self.node.identifier}\" 24/7=\"{self.nonstop}\">"

    @property
    def has_thread(self):
        return self.message and self.message.thread

    @property
    def controller_link(self):
        try:
            if self.controller_mode:
                return f" [`💠`]({self.message.jump_url})"
        except AttributeError:
            pass
        return ""

    def process_hint(self):
        if random.choice([x for x in range(self.hint_rate)]) == 0:
            self.current_hint = next(self.hints)
        else:
            self.current_hint = ""

    def setup_hints(self):

        hints = list(self.initial_hints)

        if self.static:
            hints.append("Você pode fixar músicas/playlists na mensagem do player quando tiver no modo de espera/oscioso "
                         "para qualquer membro poder usá-las de forma facilitada. Para isso use o comando: /pin add "
                         "(comando vísivel apenas membros com perm de: gerenciar servidor)")

        elif self.bot.intents.message_content:
            hints.append("Ao criar uma conversa/thread na mensagem do player, será ativado o modo de song-request "
                         "nela (possibilitando pedir música apenas enviando o nome/link da música na conversa).")

        random.shuffle(hints)
        self.hints = cycle(hints)

    async def members_timeout(self):

        await asyncio.sleep(self.idle_timeout)
        msg = f"O player foi desligado por falta de membros no canal" + (f"<#{self.guild.me.voice.channel.id}>"
                                                                         if self.guild.me.voice else '') + "..."
        self.command_log = msg
        if not self.static and not self.has_thread:
            embed = disnake.Embed(description=msg, color=self.bot.get_color(self.guild.me))
            try:
                await self.text_channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
            except:
                pass

        await self.destroy()

    async def process_next(self):

        if self.locked or self.is_closing:
            return

        if not self.is_connected:
            self.bot.loop.create_task(self.destroy(force=True))
            return

        try:
            self.idle_task.cancel()
            self.idle_task = None
        except:
            pass

        try:
            track = self.queue.popleft()
        except Exception:
            self.last_track = None
            self.idle_task = self.bot.loop.create_task(self.idling_mode())
            return

        if not track:
            return

        if isinstance(track, SpotifyTrack):

            self.locked = True

            await track.resolve(self.node)

            self.locked = False

            if not track.id and isinstance(self, LavalinkPlayer):
                return await self.process_next()

        self.last_track = track

        self.is_previows_music = False

        self.locked = False

        return track


    async def process_idle_message(self):

        if not self.static and not self.controller_mode:

            cmds = " | ".join(f"/{self.bot.get_slash_command(c).name}" for c in ['play', 'back', 'readd', 'stop'])

            embed = disnake.Embed(
                description=f"**As músicas acabaram... Use um dos comandos abaixo para adicionar músicas ou parar "
                            f"o player.**\n\n`{cmds}`\n\n"
                            f"**Nota:** `O Player será desligado automaticamente` "
                            f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=self.idle_timeout)).timestamp())}:R> "
                            f"`caso nenhum comando seja usado...`",
                color=self.bot.get_color(self.guild.me)
            )
            self.message = await self.text_channel.send(embed=embed)
            return

        controller_opts = []

        if (played := len(self.played)) or self.last_track:
            controller_opts.append(
                disnake.SelectOption(
                    emoji="⏮️", value=PlayerControls.back, label="Voltar",
                    description=f"Ouvir novamente: {self.played[-1].title[:31]}"
                )
            )

        if played > 1:
            controller_opts.append(
                disnake.SelectOption(
                    emoji="↪️", value=PlayerControls.readd, label="Tocar novamente",
                    description=f"Tocar todas as músicas novamente ({played})"
                )
            )

        controller_opts.extend([
            disnake.SelectOption(
                emoji="🛑", value=PlayerControls.stop, label="Finalizar",
                description=f"Finalizar o player e me desconectar do canal."
            ),
            disnake.SelectOption(
                emoji="🎶", value=PlayerControls.add_song, label="Adicionar",
                description=f"Tocar nova música/playlist/favorito."
            ),
        ])

        components = [
            disnake.ui.Select(
                placeholder="Executar uma ação:", options=controller_opts,
                custom_id="musicplayer_dropdown_idle", min_values=0, max_values=1
            )
        ]

        guild_data = await self.bot.db.get_data(self.guild.id, db_name="guilds")

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
            description=f"**Não há músicas na fila... Adicione uma música ou use uma das opções abaixo.\n\n"
                        f"Nota:** `O Player será desligado automaticamente` "
                        f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=self.idle_timeout)).timestamp())}:R> "
                        f"`caso nenhuma ação seja executada...`",
            color=self.bot.get_color(self.guild.me)
        )

        try:
            if self.has_thread or self.static or self.text_channel.last_message_id == self.message.id:
                await self.message.edit(embed=embed, content=None, components=components, allowed_mentions=self.allowed_mentions)
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
            self.message = await self.text_channel.send(embed=embed, components=components, allowed_mentions=self.allowed_mentions)


    async def idling_mode(self):

        self.bot.loop.create_task(self.process_rpc(self.guild.me.voice.channel))

        await self.process_idle_message()

        await asyncio.sleep(self.idle_timeout)

        msg = "💤 **⠂O player foi desligado por inatividade...**"

        if self.static or self.has_thread:
            self.command_log = msg
        else:
            embed = disnake.Embed(description=msg, color=self.bot.get_color(self.guild.me))
            self.bot.loop.create_task(self.text_channel.send(embed=embed, delete_after=120, allowed_mentions=self.allowed_mentions))

        self.bot.loop.create_task(self.destroy())

    def set_command_log(self, text="", emoji=""):
        self.command_log = text
        self.command_log_emoji = emoji

    async def invoke_np(self, force=False, interaction=None, rpc_update=False):

        if not self.current or self.updating:
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
            return

        if rpc_update:
            self.bot.loop.create_task(self.process_rpc())

        data = self.skin(self)

        self.updating = True

        if not self.controller_mode:
            self.message = None
            await self.text_channel.send(allowed_mentions=self.allowed_mentions, **data)

        else:

            if data.get("components") is None:  # nenhum controle de botão foi definido na skin (será usado os botões padrões).

                data["components"] = [
                    disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume,
                                      style=get_button_style(self.paused)),
                    disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
                    disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
                    disnake.ui.Button(emoji="🔀", custom_id=PlayerControls.shuffle),
                    disnake.ui.Button(emoji="🎶", custom_id=PlayerControls.add_song),
                    disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
                    disnake.ui.Button(emoji="📑", custom_id=PlayerControls.queue),
                    disnake.ui.Button(emoji="🛠️", custom_id=PlayerControls.settings),
                    disnake.ui.Button(emoji="<:help:947781412017279016>", custom_id=PlayerControls.help_button,
                                      label="menu de ajuda")
                ]


            if self.message and (self.ignore_np_once or self.has_thread or self.static or not force or self.is_last_message()):

                self.ignore_np_once = False

                try:
                    if interaction and not interaction.response.is_done():
                        await interaction.response.edit_message(allowed_mentions=self.allowed_mentions, **data)
                    else:
                        try:
                            await interaction.response.defer()
                        except:
                            pass
                        try:
                            await self.message.edit(allowed_mentions=self.allowed_mentions, **data)
                        except:
                            if not self.bot.get_channel(self.text_channel.id):
                                await self.destroy(force=True)  # canal não existe mais no servidor...
                                return

                    self.updating = False
                    return
                except:
                    traceback.print_exc()

            await self.destroy_message()

            try:
                self.message = await self.text_channel.send(allowed_mentions=self.allowed_mentions, **data)
            except:
                traceback.print_exc()


        self.updating = False

    async def set_pause(self, pause: bool) -> None:
        await super().set_pause(pause)

    async def destroy_message(self):

        if not self.static:
            try:
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

            if not self.controller_mode:
                pass

            elif self.auto_update:

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
            self.bot.loop.create_task(self.process_rpc())

        if force or (interaction and not interaction.response.is_done()):
            self.update = False
            if self.controller_mode:
                await self.invoke_np(interaction=interaction)

        else:
            self.update = True

    async def cleanup(self, inter: disnake.MessageInteraction = None):

        self.queue.clear()
        self.played.clear()

        vc = self.bot.get_channel(self.channel_id)

        self.bot.loop.create_task(self.process_rpc(vc, close=True))

        try:
            self.idle_task.cancel()
            self.idle_task = None
        except:
            pass

        try:
            self.message_updater_task.cancel()
        except:
            pass

        if self.static:
            try:
                await send_idle_embed(inter or self.message, self.command_log, bot=self.bot)
            except:
                pass

        elif self.has_thread:

            try:
                await self.message.edit(
                    embed=disnake.Embed(
                        description=self.command_log,
                        color=self.bot.get_color(self.guild.me)
                    ), view=None, allowed_mentions=self.allowed_mentions
                )
                channel: disnake.Thread = self.bot.get_channel(self.message.id)
                await channel.edit(archived=True, locked=True)
            except Exception:
                print(f"Falha ao arquivar thread do servidor: {self.guild.name}\n{traceback.format_exc()}")

        elif inter:

            await inter.response.edit_message(
                content=None,
                embed=disnake.Embed(
                    description=f"🛑 ⠂{self.command_log}",
                    color=self.bot.get_color(self.guild.me)),
                components=[
                    disnake.ui.Button(label="Pedir uma música", emoji="🎶", custom_id=PlayerControls.add_song)
                ]
            )

        else:

            await self.destroy_message()

        try:
            self.members_timeout_task.cancel()
        except:
            pass

    async def process_rpc(
            self,
            voice_channel: Union[disnake.VoiceChannel, disnake.StageChannel] = None,
            close=False,
            users: List[int] = None
    ):

        if not voice_channel:
            try:
                voice_channel = self.bot.get_channel(self.channel_id) or self.guild.voice_client.channel
            except AttributeError:
                return #TODO: Investigar possível bug ao mover o bot de canal pelo discord.
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
                "bot_name": str(self.bot.user),
                "thumb": thumb,
                "users": [u for u in (users or voice_channel.voice_states) if u != self.bot.user.id]
            }

            try:
                await self.bot.ws_client.send(stats)
            except Exception:
                traceback.print_exc()
            return

        if self.is_closing:
            return

        stats = {
            "op": "update",
            "track": None,
            "bot_id": self.bot.user.id,
            "bot_name": str(self.bot.user),
            "users": [m for m in (users or voice_channel.voice_states) if m != self.bot.user.id],
            "thumb": thumb,
            "info": {
                "channel": {
                    "name": voice_channel.name,
                    "id": voice_channel.id
                },
                "guild": {
                    "name": voice_channel.guild.name,
                    "id": voice_channel.guild.id,
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
                    "bot_name": str(self.bot.user),
                    "public": (await self.bot.application_info()).bot_public
                }
            )

        else:

            track: Union[LavalinkTrack, SpotifyTrack] = self.current

            stats["track"] = {
                "thumb": track.thumb,
                "title": track.single_title,
                "url": track.uri,
                "author": track.authors_string,
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


class YTDLManager:

    def __init__(self, *, bot: BotCore):

        ytdlp_utils.bug_reports_message = lambda: ''

        if os.name != "nt":
            disnake.opus.load_opus(ctypes.util.find_library("opus"))

        self.bot = bot
        self.players = {}
        self.nodes = {} # test
        self.identifier = "YoutubeDL"
        self.search = True
        self.audioformats = ["mp3", "ogg", "m4a", "webm", "mp4", "unknown_video"]
        self.ytdl = YoutubeDL(
            {
                'format': 'webm[abr>0]/bestaudio/best',
                'noplaylist': True,
                'nocheckcertificate': True,
                'ignoreerrors': False,
                'logtostderr': False,
                'quiet': True,
                'no_warnings': True,
                'retries': 5,
                'extract_flat': 'in_playlist',
                # 'cachedir': False,
                'skip_download': True,
                'default_search': 'auto',
                'source_address': '0.0.0.0',
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
        )

    def get_player(self, guild_id: int, *args, **kwargs):

        try:
            player = self.players[guild_id]
        except KeyError:
            pass
        else:
            return player

        player = YTDLPlayer(node=self, *args, **kwargs)
        self.players[guild_id] = player
        return player

    #testes
    def get_best_node(self):
        return self

    #testes
    def get_node(self, *args, **kwargs):
        return self

    async def renew_url(self, track: Union[YTDLTrack, SpotifyTrack]) -> Union[YTDLTrack, SpotifyTrack]:

        try:
            url = track.info['url']
        except KeyError:
            url = track.info['webpage_url']

        to_run = partial(self.ytdl.extract_info, url=url, download=False)
        info = await self.bot.loop.run_in_executor(None, to_run)

        track.id = [f for f in info["formats"] if f["ext"] in self.audioformats][0]["url"]
        return track

    async def get_tracks(self, query: str):

        to_run = partial(self.ytdl.extract_info, url=query, download=False, process=False)
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


class YTDLPlayer(BasePlayer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current = None
        self.channel_id = kwargs.pop('channel_id', None)
        self.bot: BotCore = kwargs.pop('bot')
        self.event = asyncio.Event()
        self.locked = False
        self.volume = 100
        self.start_time: Optional[datetime.datetime] = disnake.utils.utcnow()
        self.seek_time = None
        self.is_stopping = False
        self.node = kwargs.pop('node')
        self.is_closing = False
        self.filters_dict = {
            'nightcore': 'aresample=48000,asetrate=48000*1.20'
        }

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
        return self.guild.voice_client.is_paused()

    async def set_pause(self, pause: bool):

        if pause:
            self.guild.voice_client.pause()
        else:
            self.guild.voice_client.resume()

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

        if self.guild.voice_client and self.guild.voice_client.source:
            self.guild.voice_client.source.volume = vol / 100
        self.volume = vol

    async def connect(self, channel_id: int, self_deaf: bool = False):

        channel: disnake.VoiceChannel = self.bot.get_channel(channel_id)

        self.channel_id = channel_id

        if not self.guild.me.voice:
            await channel.connect()
            return

        if self.guild.me.voice.channel.id != channel_id:
            await self.guild.voice_client.move_to(channel)

    async def seek(self, position: int):
        self.queue.appendleft(self.current)
        self.last_track = None
        self.current = None
        self.seek_time = time_format(position)
        await self.stop()

    @property
    def is_connected(self) -> bool:
        return self.guild.voice_client is not None

    @property
    def is_paused(self) -> bool:
        return self.is_connected and self.guild.voice_client.is_paused()

    async def destroy(self, force=True, inter: disnake.MessageInteraction = None):

        self.is_closing = True

        try:
            self.guild.voice_client.source.cleanup()
        except:
            pass

        try:
            await self.guild.voice_client.disconnect(force=True)
        except AttributeError:
            pass

        await self.cleanup(inter=inter)

        try:
            del self.bot.music.players[self.guild.id]
        except KeyError:
            pass

    async def process_track(self):

        self.event.clear()

        if self.is_closing:
            return

        track: YTDLTrack = await super().process_next()

        if not track or self.locked:
            return

        await self.bot.wait_until_ready()

        self.locked = True

        if not track.id:

            try:
                track = await self.node.renew_url(track)
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
                              ' -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10'
            ,
            'options': '-vn -loglevel panic'
        }

        if self.seek_time:
            FFMPEG_OPTIONS['options'] += f' -ss {self.seek_time}'
            self.seek_time = None

        if self.nightcore:
            FFMPEG_OPTIONS['options'] += f" -af \"{self.filters_dict['nightcore']}\""

        source = await disnake.FFmpegOpusAudio.from_probe(track.id, **FFMPEG_OPTIONS)
        source.volume = self.volume / 100

        self.guild.voice_client.play(source, after=self.next)

        self.start_time = disnake.utils.utcnow()

        try:
            await self.invoke_np(rpc_update=True)
        except:
            traceback.print_exc()

        self.locked = False

        self.is_previows_music = False

        await self.event.wait()

        if self.is_stopping:
            self.is_stopping = False
        else:
            self.set_command_log()

        self.current = None

        await self.track_end()

        await self.process_next()

    def next(self, error=None):

        if error:
            print(f"Erro na reprodução: {self.guild.id} - {error}")

        self.event.set()

    async def stop(self):
        self.is_stopping = True
        self.guild.voice_client.stop()

    async def process_next(self):
        self.bot.loop.create_task(self.process_track())

    async def get_tracks(self, query: str):
        return await self.bot.music.get_tracks(query)


class LavalinkPlayer(BasePlayer, wavelink.Player):
    bot: BotCore

    def __init__(self, *args, **kwargs):
        super(LavalinkPlayer, self).__init__(*args, **kwargs)

    def __str__(self) -> str:
        return f"Lavalink Player | Server: {self.node.identifier}"

    async def process_next(self):

        track: LavalinkTrack = await super().process_next()

        if not track:
            return

        await self.play(track)

    async def destroy(self, *, force: bool = False, inter: disnake.MessageInteraction = None):

        await self.cleanup(inter)

        self.is_closing = True

        await super().destroy(force=force)

        self.bot.dispatch("player_destroy", player=self)

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
    if bot.config.get("YTDLMODE"):
        return YTDLManager(bot=bot)
    else:
        return wavelink.Client(bot=bot)
