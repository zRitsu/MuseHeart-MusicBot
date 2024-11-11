# -*- coding: utf-8 -*-

# nota: este sistema é totalmente experimental.
import asyncio
import os
import pickle
import shutil
import traceback
import zlib
from base64 import b64decode, b64encode
from typing import Union

import aiofiles
import disnake
from disnake.ext import commands

from utils.client import BotCore
from utils.db import DBModel
from utils.music.checks import can_connect, can_send_message
from utils.music.filters import AudioFilter
from utils.music.models import LavalinkPlayer
from utils.others import send_idle_embed, CustomContext


class PlayerSession(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

        if not hasattr(bot, "player_resumed"):
            bot.player_resumed = False

        if not hasattr(bot, "player_resuming"):
            bot.player_resuming = False

        if not hasattr(bot, 'players_resumed'):
            bot.players_resumed ={}

        self.resume_task = bot.loop.create_task(self.resume_players())

    @commands.Cog.listener()
    async def on_player_destroy(self, player: LavalinkPlayer):

        try:
            player.queue_updater_task.cancel()
        except:
            pass

        await self.delete_data(player)

    @commands.Cog.listener('on_wavelink_track_end')
    async def track_end(self, player: LavalinkPlayer, *args, **kwargs):

        if len(player.queue) > 0:
            return

        await self.save_info(player)

    @commands.is_owner()
    @commands.command(hidden=True, description="Salvar informações dos players na database instantaneamente.", aliases=["svplayers"])
    async def saveplayers(self, ctx: CustomContext):

        await ctx.defer()

        player_count = 0

        for bot in self.bot.pool.get_all_bots():
            for player in bot.music.players.values():
                try:
                    await player.process_save_queue()
                    player_count += 1
                except:
                    continue

        txt = f"As informações dos players atuais foram salvos com sucesso ({player_count})!" if player_count else "Não há player ativo..."
        await ctx.send(txt)

    async def queue_updater_task(self, player: LavalinkPlayer):

        while True:

            if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
                await asyncio.sleep(self.bot.config["PLAYER_INFO_BACKUP_INTERVAL_MONGO"])
            else:
                await asyncio.sleep(self.bot.config["PLAYER_INFO_BACKUP_INTERVAL"])

            try:
                await self.save_info(player)
            except:
                traceback.print_exc()

    async def save_info(self, player: LavalinkPlayer):

        if not player.guild.me.voice or player.is_closing:
            return

        try:
            message_id = player.message.id
        except:
            message_id = None

        try:
            text_channel_id = player.text_channel.id
        except:
            text_channel_id = None
            message_id = None

        tracks = []
        played = []
        autoqueue = []
        failed_tracks = []

        if player.current:
            player.current.info["id"] = player.current.id
            if player.current.playlist_name:
                player.current.info["playlist"] = {"name": player.current.playlist_name, "url": player.current.playlist_url}
                try:
                    player.current.info["playlist"]["thumb"] = player.current.playlist.thumb
                except:
                    pass
            tracks.append(player.current.info)

        for t in player.queue:
            t.info["id"] = t.id
            if t.playlist:
                t.info["playlist"] = {"name": t.playlist_name, "url": t.playlist_url}
            tracks.append(t.info)

        for t in player.played:
            t.info["id"] = t.id
            if t.playlist:
                t.info["playlist"] = {"name": t.playlist_name, "url": t.playlist_url}
            played.append(t.info)

        for t in player.queue_autoplay:
            t.info["id"] = t.id
            autoqueue.append(t.info)

        for t in player.failed_tracks:
            t.info["id"] = t.id
            if t.playlist:
                t.info["playlist"] = {"name": t.playlist_name, "url": t.playlist_url}
            failed_tracks.append(t.info)

        try:
            vc_id = player.guild.me.voice.channel.id
        except AttributeError:
            vc_id = player.last_channel.id

        data = {
            "_id": player.guild.id,
            "version": getattr(player, "version", 1),
            "volume": player.volume,
            "nightcore": player.nightcore,
            "position": player.position,
            "voice_channel": vc_id,
            "dj": player.dj,
            "player_creator": player.player_creator,
            "static": player.static,
            "paused": player.paused and not player.auto_pause,
            "text_channel_id": text_channel_id,
            "message_id": message_id,
            "keep_connected": player.keep_connected,
            "loop": player.loop,
            "autoplay": player.autoplay,
            "stage_title_event": player.stage_title_event,
            "stage_title_template": player.stage_title_template,
            "skin": player.skin,
            "skin_static": player.skin_static,
            "custom_skin_data": {},
            "custom_skin_static_data": {},
            "uptime": player.uptime,
            "restrict_mode": player.restrict_mode,
            "mini_queue_enabled": player.mini_queue_enabled,
            "listen_along_invite": player.listen_along_invite,
            "queue": tracks,
            "played": played,
            "queue_autoplay": autoqueue,
            "failed_tracks": failed_tracks,
            "prefix_info": player.prefix_info,
            "voice_state": player._voice_state,
            "time": disnake.utils.utcnow(),
            "lastfm_artists": player.lastfm_artists,
            "start_timestamp": player.start_timestamp
        }

        try:
            data["last_voice_channel_id"] = player._last_channel_id
        except AttributeError:
            player._last_channel_id = vc_id
            data["last_voice_channel_id"] = vc_id

        try:
            data["live_lyrics_status"] = player.live_lyrics_enabled
        except AttributeError:
            pass

        try:
            data["command_log_list"] = player.command_log_list
        except AttributeError:
            pass

        if player.static:
            if player.skin_static.startswith("> custom_skin: "):
                custom_skin = player.skin_static[15:]
                data["custom_skin_static_data"] = {custom_skin: player.custom_skin_static_data[custom_skin]}

        elif player.skin.startswith("> custom_skin: "):
            custom_skin = player.skin[15:]
            data["custom_skin_data"] = {custom_skin: player.custom_skin_data[custom_skin]}

        try:
            await self.save_session(player, data=data)
        except:
            traceback.print_exc()

    async def resume_players(self):

        try:
            if self.bot.player_resuming:
                return

            self.bot.player_resuming = True

            await self.bot.wait_until_ready()

            while not self.bot.bot_ready:
                await asyncio.sleep(3)

        except Exception:
            print(traceback.format_exc())
            self.bot.player_resuming = False
            return

        try:

            mongo_sessions = await self.get_player_sessions_mongo()
            local_sessions = await self.get_player_sessions_local()

            data_list = {}

            if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
                for d in local_sessions:
                    data_list[d["_id"]] = d
                    print(f"{self.bot.user} - Migrando dados de sessões do server: {d['_id']} | DB Local -> Mongo")
                    await self.save_session_mongo(d["_id"], d)
                    self.delete_data_local(d["_id"])
                for d in mongo_sessions:
                    data_list[d["_id"]] = d

            else:
                for d in mongo_sessions:
                    data_list[d["_id"]] = d
                    print(f"{self.bot.user} - Migrando dados de sessões do server: {d['_id']} | Mongo -> DB Local")
                    await self.save_session_local(d["_id"], d)
                    if self.bot.config["MONGO"]:
                        await self.delete_data_mongo(d["_id"])
                for d in local_sessions:
                    data_list[d["_id"]] = d

            mongo_sessions.clear()
            local_sessions.clear()

            hints = self.bot.config["EXTRA_HINTS"].split("||")

            for data in data_list.values():

                try:
                    self.bot.players_resumed[data['_id']]
                except KeyError:
                    self.bot.players_resumed[data['_id']] = self.bot.loop.create_task(self.resume_player(data, hints=hints))
                    await asyncio.sleep(1)

        except Exception:
            print(f"{self.bot.user} - Falha ao retomar player {data['_id']}:\n{traceback.format_exc()}")

        self.bot.player_resumed = True

    async def update_player(
            self,
            player: LavalinkPlayer,
            voice_channel: Union[disnake.VoiceChannel, disnake.StageChannel],
            pause: bool,
            position: int,
            has_members = None
    ):

        if not player.current:
            try:
                player.current = player.queue.popleft()
            except:
                pass

            if not player.current and player.autoplay:
                try:
                    player.current = await player.get_autoqueue_tracks()
                    position = 0
                except:
                    traceback.print_exc()

        data = {
            "volume": player.volume,
            "filters": player.filters,
        }

        await player.connect(voice_channel.id)
        await self.voice_check(voice_channel, position)

        try:
            track_id = player.current.id
        except:
            track_id = None

        if track_id and has_members:
            data.update(
                {
                    "encodedTrack": track_id,
                    "position": position,
                    "paused": pause,
                }
            )
            await player.node.update_player(player.guild.id, data=data)
        else:
            await player.node.update_player(player.guild.id, data=data)
            if player.current:
                player.queue.appendleft(player.current)
            await player.process_next(start_position=position)

    async def voice_check(self, voice_channel: Union[disnake.VoiceChannel, disnake.StageChannel], position: int = 0):

        wait_counter = 30

        guild = voice_channel.guild

        while wait_counter > 1:
            if not guild.me.voice:
                wait_counter -= 1
                await asyncio.sleep(1)
                continue
            try:
                player = self.bot.music.players[voice_channel.guild.id]
                player._last_channel = voice_channel
                if player.node.version > 3:
                    player.last_position = position
            except KeyError:
                pass
            break

        if not wait_counter:
            print(f"{self.bot.user} - {guild.name}: Player ignorado devido a demora para conectar no canal de voz.")
            return

        if isinstance(voice_channel, disnake.StageChannel) and \
                voice_channel.permissions_for(guild.me).mute_members:

            while not guild.me.voice:
                await asyncio.sleep(1)

            await asyncio.sleep(3)

            try:
                await guild.me.edit(suppress=False)
            except Exception as e:
                print(f"{self.bot.user} - Falha ao falar no palco do servidor {guild.name}. Erro: {repr(e)}")

    async def resume_player(self, data: dict, hints: list = None):

        if hints is None:
            hints = []

        voice_channel = self.bot.get_channel(data["voice_channel"])

        try:
            guild = self.bot.get_guild(data["_id"])

            db_date = data.get("time")

            if not db_date or (not guild and ((disnake.utils.utcnow() - db_date)).total_seconds() > 172800):
                print(f"{self.bot.user} - Limpando informações do player: {data['_id']}")
                await self.delete_data(data["_id"])
                return

            if not guild:
                print(f"{self.bot.user} - Player Ignorado: {data['_id']} | Servidor inexistente...")
                return

            try:
                player = self.bot.music.players[int(data["_id"])]
                started = True
            except KeyError:
                message = None
                started = False

                guild_data = await self.bot.get_data(guild.id, db_name=DBModel.guilds)

                text_channel = None

                if guild_data['player_controller']["channel"]:
                    try:
                        text_channel = self.bot.get_channel(int(guild_data['player_controller']["channel"])) or await self.bot.fetch_channel(
                            int(guild_data['player_controller']["channel"]))
                    except:
                        pass
                    else:
                        data["message_id"] = int(guild_data['player_controller']['message_id'])

                if not text_channel:

                    if not data["text_channel_id"]:
                        pass
                    elif not isinstance(data["text_channel_id"], disnake.Thread):
                        text_channel = self.bot.get_channel(data["text_channel_id"])
                    else:
                        try:
                            text_channel = self.bot.get_channel(int(data["text_channel_id"])) or \
                                       await self.bot.fetch_channel(int(data["text_channel_id"]))
                        except (disnake.NotFound, TypeError):
                            text_channel = None
                            data["message_id"] = None

                if not text_channel:
                    data['static'] = False
                    text_channel = voice_channel
                    data["message_id"] = None

                if text_channel:
                    try:
                        can_send_message(text_channel, self.bot.user)
                    except Exception:
                        print(f"{self.bot.user} - Controller Ignorado (falta de permissão) [Canal: {text_channel.name} | ID: {text_channel.id}] - [ {guild.name} - {guild.id} ]")
                        text_channel = None
                    else:
                        if data["message_id"]:
                            try:
                                message = await text_channel.fetch_message(data["message_id"])
                            except (disnake.NotFound, disnake.Forbidden):
                                pass

                message_without_thread = None

                if text_channel and not message and text_channel.permissions_for(guild.me).read_message_history:
                    try:
                        async for msg in text_channel.history(limit=100):

                            if msg.author.id != self.bot.user.id:
                                continue

                            if msg.reference:
                                continue

                            if msg.thread:
                                message = msg
                                break

                            if message_without_thread:
                                continue

                            message_without_thread = msg

                    except Exception as e:
                        print(f"{self.bot.user} - Falha ao obter mensagem: {repr(e)}\n"
                              f"channel_id: {text_channel.id} | message_id {data['message']}")

                if not voice_channel or not voice_channel.permissions_for(guild.me).connect:
                    if data["voice_channel"] != (vc:=data.get("last_voice_channel_id", data["voice_channel"])):
                        voice_channel=vc
                        try:
                            del data["voice_state"]
                        except:
                            pass

                if not voice_channel:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\nO canal de voz não existe...")
                    try:
                        msg = "Player finalizado pois o canal de voz não existe ou foi deletado."
                        if not data["skin_static"]:
                            await text_channel.send(embed=disnake.Embed(description=msg, color=self.bot.get_color(guild.me)))
                        else:
                            if isinstance(text_channel, disnake.ForumChannel):
                                cog = self.bot.get_cog("Music")
                                if cog:
                                    await cog.reset_controller_db(guild.id, guild_data)
                                print(f"{self.bot.user} - Controller resetado por config de canal inválido.\n"
                                      f"Server: {guild.name} [{guild.id}] | channel: {text_channel.name} [{text_channel.id}] {type(text_channel)}")
                                return
                            await send_idle_embed(text_channel, bot=self.bot, text=msg)
                    except Exception:
                        traceback.print_exc()
                    if (disnake.utils.utcnow() - data.get("time", disnake.utils.utcnow())).total_seconds() > 172800:
                        await self.delete_data(guild.id)
                    return

                try:
                    can_connect(voice_channel, guild=guild, bot=self.bot)
                except Exception as e:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\n{repr(e)}")
                    try:
                        msg = f"O player foi finalizado devido a falta da permissão de conectar no canal {voice_channel.mention}."
                        if not data["skin_static"]:
                            await text_channel.send(embed=disnake.Embed(description=msg, color=self.bot.get_color(guild.me)))
                        else:
                            await send_idle_embed(text_channel, bot=self.bot, text=msg)
                    except Exception:
                        traceback.print_exc()
                    return

                while True:

                    node = self.bot.music.get_best_node()

                    if not node:
                        try:
                            node = await self.bot.wait_for("wavelink_node_ready", timeout=5)
                        except asyncio.TimeoutError:
                            continue

                    break

                try:
                    player: LavalinkPlayer = self.bot.music.get_player(
                        node_id=node.identifier,
                        guild_id=guild.id,
                        cls=LavalinkPlayer,
                        guild=guild,
                        channel=text_channel,
                        message=message or message_without_thread,
                        last_message_id=data["message_id"],
                        skin=data["skin"],
                        skin_static=data["skin_static"],
                        player_creator=data["player_creator"],
                        keep_connected=data.get("keep_connected"),
                        autoplay=data.get("autoplay", False),
                        static=data['static'],
                        custom_skin_data=data.get("custom_skin_data", {}),
                        custom_skin_static_data=data.get("custom_skin_static_data", {}),
                        extra_hints=hints,
                        uptime=data.get("uptime"),
                        stage_title_template=data.get("stage_title_template"),
                        restrict_mode=data["restrict_mode"],
                        prefix=data["prefix_info"],
                        session_resuming=True,
                    )
                except Exception:
                    print(f"{self.bot.user} - Falha ao criar player: {guild.name} [{guild.id}]\n{traceback.format_exc()}")
                    if not data.get("autoplay") and (disnake.utils.utcnow() - data.get("time", disnake.utils.utcnow())).total_seconds() > 172800:
                        await self.delete_data(guild.id)
                    return

                try:
                    player._voice_state = data["voice_state"]
                except KeyError:
                    pass

                player.live_lyrics_enabled = data.get("live_lyrics_status", False)

                if start_timestamp:=data.get("start_timestamp"):
                    player.start_timestamp = start_timestamp

                try:
                    player.mini_queue_enabled = data["mini_queue_enabled"]
                except:
                    pass

                player.lastfm_artists = data.get("lastfm_artists")

                player.stage_title_event = data.get("stage_title_event", False)

                player.listen_along_invite = data.pop("listen_along_invite", "")

                player.command_log_list.extend(data.pop("command_log_list", []))

                player.dj = set(data["dj"])
                player.loop = data["loop"]

                player.volume = int(data["volume"])

                if player.volume != 100 and player.node.version == 3:
                    player.filters["volume"] = max(min(player.volume, 1000), 0)

                player.nightcore = data.get("nightcore")

                if player.nightcore:
                    player.filters.update(AudioFilter.timescale(pitch=1.2, speed=1.1).filter)

                if node.version == 3:

                    if player.filters:
                        await player.update_filters()

                    await player.connect(voice_channel.id)

                    await self.voice_check(voice_channel)

            tracks, playlists = self.bot.pool.process_track_cls(data["queue"])

            player.queue.extend(tracks)

            played_tracks, playlists = self.bot.pool.process_track_cls(data["played"], playlists)

            player.played.extend(played_tracks)

            queue_autoplay_tracks, playlists = self.bot.pool.process_track_cls(data.get("queue_autoplay", []))

            player.queue_autoplay.extend(queue_autoplay_tracks)

            failed_tracks, playlists = self.bot.pool.process_track_cls(data.get("failed_tracks", []), playlists)

            player.queue.extend(failed_tracks)

            if player.controller_mode is False:
                try:
                    await player.message.delete()
                    player.message = None
                except:
                    pass

            if started:
                player.set_command_log(
                    text="Os dados do player foram restaurados com sucessos!",
                    emoji="🔰"
                )
                player.update = True

            else:
                if player.keep_connected and not player.queue and not player.queue_autoplay:
                    if player.failed_tracks:
                        player.queue.extend(reversed(player.failed_tracks))
                        player.failed_tracks.clear()
                    if not player.queue:
                        player.queue.extend(player.played)
                        player.played.clear()

                player.set_command_log(
                    text="O player foi restaurado com sucesso!",
                    emoji="🔰"
                )

                player._last_channel = voice_channel

                try:
                    check = any(m for m in voice_channel.members if not m.bot or not (m.voice.deaf or m.voice.self_deaf))
                except:
                    check = None

                if not check:
                    player.auto_pause = True

                try:

                    pause = data.get("paused") and check

                    start_position = int(float(data.get("position", 0))) if player.queue else 0

                    if player.node.version > 3:
                        await self.update_player(
                            player=player, voice_channel=voice_channel, pause=pause, position=start_position, has_members=check
                        )
                        await player.invoke_np()
                    else:
                        await player.process_next(start_position=start_position)
                        if pause:
                            await player.set_pause(True)
                            if not check:
                                player.start_members_timeout(check=False)

                    player._session_resuming = False
                except Exception:
                    print(f"{self.bot.user} - Falha na reprodução da música ao retomar player do servidor {guild.name} [{guild.id}]:\n{traceback.format_exc()}")
                    return

            print(f"▶️ - {self.bot.user} - Player Retomado: {guild.name} [{guild.id}] - Server: {player.node.identifier}")

        except Exception:
            print(f"{self.bot.user} - Falha Crítica ao retomar players:\n{traceback.format_exc()}")

    async def get_player_sessions_mongo(self):

        if not self.bot.config["MONGO"]:
            return []

        guild_data = []

        for d in (await self.bot.pool.mongo_database.query_data(db_name=str(self.bot.user.id), collection="player_sessions")):

            try:
                data = d["data"]
            except KeyError:
                await self.delete_data(int(d["_id"]))
                continue
            data = b64decode(data)
            try:
                data = zlib.decompress(data)
            except zlib.error:
                pass
            guild_data.append(pickle.loads(data))

        return guild_data

    async def get_player_sessions_local(self):

        guild_data = []

        try:
            files = os.listdir(f"./local_database/player_sessions/{self.bot.user.id}")
        except FileNotFoundError:
            return guild_data

        for file_content in files:

            if not file_content.endswith(".pkl"):
                continue

            guild_id = file_content[:-4]

            async with aiofiles.open(f'./local_database/player_sessions/{self.bot.user.id}/{guild_id}.pkl', 'rb') as f:
                file_content = await f.read()
                try:
                    file_content = zlib.decompress(file_content)
                except zlib.error:
                    pass
                data = pickle.loads(file_content)

            if data:
                guild_data.append(data)

        return guild_data

    async def save_session_mongo(self, id_: Union[int, str], data: dict):
        await self.bot.pool.mongo_database.update_data(
            id_=str(id_),
            data={"data": b64encode(zlib.compress(pickle.dumps(data))).decode('utf-8')},
            collection="player_sessions",
            db_name=str(self.bot.user.id)
        )

    async def save_session_local(self, id_: Union[int, str], data: dict):

        if not os.path.isdir(f"./local_database/player_sessions/{self.bot.user.id}"):
            os.makedirs(f"./local_database/player_sessions/{self.bot.user.id}")

        path = f'./local_database/player_sessions/{self.bot.user.id}/{id_}'

        try:
            async with aiofiles.open(f"{path}.pkl", "wb") as f:
                await f.write(zlib.compress(pickle.dumps(data)))
        except Exception:
            traceback.print_exc()
            try:
                os.rename(f"{path}.bak", f"{path}.pkl")
            except:
                pass
            return

        try:
            shutil.copy(f'{path}.pkl', f'{path}.bak')
        except FileNotFoundError:
            pass
        except Exception:
            traceback.print_exc()

    async def save_session(self, player: LavalinkPlayer, data: dict):

        try:
            player = player.bot.music.players[player.guild.id]
        except:
            try:
                player.queue_updater_task.cancel()
            except:
                pass
            return

        try:
            if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
                await self.save_session_mongo(player.guild.id, data)
            else:
                await self.save_session_local(player.guild.id, data)

        except asyncio.CancelledError as e:
            print(f"❌ - {self.bot.user} - Salvamento cancelado: {repr(e)}")

    async def delete_data_mongo(self, id_: Union[LavalinkPlayer, int]):
        await self.bot.pool.mongo_database.delete_data(id_=str(id_), db_name=str(self.bot.user.id),
                                                       collection="player_sessions")

    def delete_data_local(self, id_: Union[LavalinkPlayer, int]):
        for ext in ('.pkl', '.bak'):
            try:
                os.remove(f'./local_database/player_sessions/{self.bot.user.id}/{id_}{ext}')
            except FileNotFoundError:
                continue
            except Exception:
                traceback.print_exc()

    async def delete_data(self, player: Union[LavalinkPlayer, int]):

        try:
            guild_id = player.guild.id
        except AttributeError:
            guild_id = int(player)

        if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            await self.delete_data_mongo(guild_id)
        else:
            self.delete_data_local(guild_id)

    def cog_unload(self):
        try:
            self.resume_task.cancel()
        except:
            pass

        for guild_id in list(self.bot.players_resumed):
            try:
                self.bot.players_resumed[guild_id].cancel()
            except:
                pass
            try:
                del self.bot.players_resumed[guild_id]
            except KeyError:
                continue

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
