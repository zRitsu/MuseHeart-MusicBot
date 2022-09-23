from __future__ import annotations
import datetime
import random
from itertools import cycle
import disnake
import asyncio
import wavelink
from urllib import parse
from .converters import fix_characters, time_format, get_button_style
from .filters import AudioFilter
from ..db import DBModel
from ..others import send_idle_embed, PlayerControls
from .spotify import SpotifyTrack
import traceback
from collections import deque
from typing import Optional, Union, TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..client import BotCore


class LavalinkTrack(wavelink.Track):

    __slots__ = ('extra')

    def __init__(self, *args, **kwargs):
        try:
            args[1]['title'] = fix_characters(args[1]['title'])
        except IndexError:
            pass
        super().__init__(*args, **kwargs)

        if (info:=kwargs.pop("info", None)):
            self.info = info
            self.thumb = info["extra"]["thumb"]
            return

        try:
            self.info["extra"]
        except KeyError:
            self.info["extra"] = {}

        try:
            self.info["extra"]["playlist"] = {
                "name": kwargs["playlist"]["name"],
                "url": kwargs["playlist"]["url"]
            }
        except KeyError:
            pass

        self.info["extra"]["track_loops"] = kwargs.pop('track_loops', 0)
        self.info["extra"]["requester"] = kwargs.pop('requester', '')

        try:
            self.info['sourceName']
        except:
            self.info['sourceName'] = 'LavalinkTrack'

        if self.ytid:
            self.info["extra"]["thumb"] = f"https://img.youtube.com/vi/{self.ytid}/mqdefault.jpg"
        elif "soundcloud.com" in self.uri:
            self.info["extra"]["thumb"] = self.info.get("artworkUrl", "").replace('large.jpg', 't500x500.jpg')
        else:
            self.info["extra"]["thumb"] = self.info.get("artworkUrl", "")

        self.thumb = self.info["extra"]["thumb"]

        if self.info["sourceName"] == "youtube" and "list=" not in self.uri and self.playlist_url:
            try:
                self.uri = f"{self.uri}&list={parse.parse_qs(parse.urlparse(self.playlist_url).query)['list'][0]}"
                self.info["uri"] = self.uri
            except KeyError:
                pass

    def __repr__(self):
        return f"{self.info['sourceName']} - {self.duration if not self.is_stream else 'stream'} - {self.authors_string} - {self.title}"

    @property
    def single_title(self) -> str:
        return self.title

    @property
    def authors_md(self) -> str:
        return f"`{self.author}`"

    @property
    def authors_string(self) -> str:
        return f"{self.author}"

    @property
    def album_name(self) -> str:
        try:
            return self.info["extra"]["album"]["name"]
        except KeyError:
            return ""

    @property
    def album_url(self) -> str:
        try:
            return self.info["extra"]["album"]["url"]
        except KeyError:
            return ""

    @property
    def requester(self) -> int:
        return self.info["extra"]["requester"]

    @property
    def track_loops(self) -> int:
        return self.info["extra"]["track_loops"]

    @property
    def playlist_name(self) -> str:
        try:
            return self.info["extra"]["playlist"]["name"]
        except KeyError:
            return ""

    @property
    def playlist_url(self) -> str:
        try:
            return self.info["extra"]["playlist"]["url"]
        except KeyError:
            return ""


class LavalinkPlayer(wavelink.Player):

    bot: BotCore

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guild: disnake.Guild = kwargs.pop('guild')
        self.text_channel: disnake.TextChannel = kwargs.pop('channel')
        self.message: Optional[disnake.Message] = kwargs.pop('message', None)
        self.static: bool = kwargs.pop('static', False)
        self.skin: str = kwargs.pop("skin", None) or self.bot.default_skin
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
        self.keep_connected: bool = kwargs.pop("keep_connected", False)
        self.update: bool = False
        self.updating: bool = False
        self.auto_update: int = 0
        self.message_updater_task: Optional[asyncio.Task] = self.bot.loop.create_task(self.message_updater())
        self.restrict_mode = kwargs.pop('restrict_mode', False) # limitar apenas para dj's e staff's
        self.ignore_np_once = False  # não invocar player controller em determinadas situações
        self.allowed_mentions = disnake.AllowedMentions(users=False, everyone=False, roles=False)
        self.controller_mode = True  # ativar/desativar modo controller (apenas para uso em skins)
        self.can_process_next = True

        self.initial_hints = [
            "Você pode alterar a skin/aparência do player usando o comando /change_skin (comando vísivel apenas membros"
            " com perm de: gerenciar servidor).",

            "Crie favoritos para ter fácil acesso de usar seus links favoritos aqui dispensando ter que copiar e colar "
            "seus links nos comandos. Experimente usando o comando: /fav add.",
        ]

        player_creator: disnake.Member = kwargs.pop('player_creator', None)

        if player_creator and not player_creator.guild_permissions.manage_channels:
            self.dj.add(player_creator.id)

        self.hints: cycle = []
        self.current_hint = ""
        self.setup_hints()

        self.bot.dispatch("player_create", player=self)

    def __str__(self) -> str:
        return f"Servidor de música atual: {self.node.identifier}"

    def __repr__(self):
        return f"<volume={self.volume} " \
               f"current_position={time_format(self.position) if self.position else 'Idling'} " \
               f"queue={len(self.queue)} loop={self.loop} EQ=\"{self.eq}\" guild=\"{self.guild.name}\" " \
               f"node=\"{self.node.identifier}\" keep_connected=\"{self.keep_connected}\">"

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

    async def connect(self, channel_id: int, self_mute: bool = False, self_deaf: bool = False):
        await super().connect(channel_id, self_mute=self_mute, self_deaf=True)

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

        elif self.bot.intents.message_content and self.controller_mode:
            hints.append("Ao criar uma conversa/thread na mensagem do player, será ativado o modo de song-request "
                        "nela (possibilitando pedir música apenas enviando o nome/link da música na conversa).")

        random.shuffle(hints)
        self.hints = cycle(hints)

    async def members_timeout(self):

        self.can_process_next = False

        if self.keep_connected:
            return

        await asyncio.sleep(self.idle_timeout)
        msg = f"**O player foi desligado por falta de membros no canal" + (f"<#{self.guild.me.voice.channel.id}>"
                                                                         if self.guild.me.voice else '') + "...**"
        self.command_log = msg
        if not self.static and not self.has_thread:
            embed = disnake.Embed(description=msg, color=self.bot.get_color(self.guild.me))
            try:
                await self.text_channel.send(embed=embed, allowed_mentions=self.allowed_mentions)
            except:
                pass

        await self.destroy()

    async def process_next(self, start_position: int = 0):

        if self.locked or self.is_closing or not self.can_process_next:
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

            if not track.id:
                return await self.process_next()

        self.last_track = track

        self.is_previows_music = False

        self.locked = False

        await self.play(track, start=start_position)

    async def process_idle_message(self):

        if not self.static and not self.controller_mode:

            cmds = " | ".join(f"{self.bot.get_slash_command(c).name}" for c in ['play', 'back', 'readd', 'stop'])

            embed = disnake.Embed(
                description=f"**As músicas acabaram... Use um dos comandos abaixo para adicionar músicas ou parar "
                            f"o player.**\n\n`{cmds}`\n\n"
                            f"**Nota:** `O Player será desligado automaticamente` "
                            f"<t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=self.idle_timeout)).timestamp())}:R> "
                            f"`caso nenhum comando seja usado...`",
                color=self.bot.get_color(self.guild.me)
            )
            embed.set_thumbnail(self.guild.me.display_avatar.replace(size=256).url)
            self.message = await self.text_channel.send(embed=embed)
            return

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

        data = self.bot.player_skins[self.skin](self)

        self.updating = True

        if not self.controller_mode:
            self.message = None
            await self.text_channel.send(allowed_mentions=self.allowed_mentions, **data)

        else:

            try:
                self.message_updater_task.cancel()
            except:
                pass

            if data.get("components") is None:  # nenhum controle de botão foi definido na skin (será usado os botões padrões).

                data["components"] = [
                    disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume, style=get_button_style(self.paused)),
                    disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
                    disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
                    disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
                    disnake.ui.Button(emoji="📑", custom_id=PlayerControls.queue),
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
                                label="Adicionar favorito", emoji="⭐",
                                value=PlayerControls.enqueue_fav,
                                description="Adicionar um de seus favoritos na fila."
                            ),
                            disnake.SelectOption(
                                label="Tocar do inicio", emoji="⏪",
                                value=PlayerControls.seek_to_start,
                                description="Voltar o tempo da música atual para o inicio."
                            ),
                            disnake.SelectOption(
                                label="Volume", emoji="🔊",
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
                                label="Nightcore", emoji="🇳",
                                value=PlayerControls.nightcore,
                                description="Ativar/Desativar o efeito nightcore."
                            ),
                            disnake.SelectOption(
                                label="Ativar/Desativar modo restrito", emoji="🔐",
                                value=PlayerControls.restrict_mode,
                                description="Apenas DJ's/Staff's podem usar comandos restritos."
                            ),
                        ]
                    ),
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
                    self.message_updater_task = self.bot.loop.create_task(self.message_updater())
                    return
                except:
                    traceback.print_exc()

            await self.destroy_message()

            try:
                self.message = await self.text_channel.send(allowed_mentions=self.allowed_mentions, **data)
                self.message_updater_task = self.bot.loop.create_task(self.message_updater())
            except:
                traceback.print_exc()
                print(self.text_channel)

        self.updating = False

    async def set_pause(self, pause: bool) -> None:
        await super().set_pause(pause)

    async def destroy_message(self):

        try:
            self.message_updater_task.cancel()
        except:
            pass

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
                    disnake.ui.Button(label="Pedir uma música", emoji="🎶", custom_id=PlayerControls.add_song),
                    disnake.ui.Button(label="Tocar favorito", emoji="⭐", custom_id=PlayerControls.enqueue_fav)

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

        thumb = self.bot.user.display_avatar.replace(size=512, static_format="png").url

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
                    "invite_permissions": self.bot.config["INVITE_PERMISSIONS"],
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
                self.last_track.info["extra"]["track_loops"] -= 1
                self.queue.insert(0, self.last_track)
            elif self.loop == "queue": # or self.keep_connected:
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

    async def destroy(self, *, force: bool = False, inter: disnake.MessageInteraction = None):

        await self.cleanup(inter)

        self.is_closing = True

        try:
            await self.guild.voice_client.disconnect(force=True)
        except:
            pass

        try:
            self.guild.voice_client.cleanup()
        except:
            pass

        await super().destroy(force=force)

        self.bot.dispatch("player_destroy", player=self)

    #######################
    #### Filter Stuffs ####
    #######################

    async def change_node(self, identifier: str = None, force: bool = False):
        await super().change_node(identifier=identifier, force=force)
        await self.node._send(op="filters", **self.filters, guildId=str(self.guild_id))

    async def set_volume(self, vol: int) -> None:

        self.volume = max(min(vol, 1000), 0)
        await self.node._send(op='volume', guildId=str(self.guild_id), volume=self.volume)

    async def seek(self, position: int = 0) -> None:
        await super().seek(position=position)
        self.last_position = position

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
