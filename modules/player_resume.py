# -*- coding: utf-8 -*-

# nota: este sistema é totalmente experimental.
import asyncio
import os
import pickle
import shutil
import traceback
from base64 import b64encode, b64decode
from typing import Union

import aiofiles
import disnake
from disnake.ext import commands

import wavelink
from utils.client import BotCore
from utils.music.checks import can_connect, can_send_message
from utils.music.models import LavalinkPlayer, LavalinkTrack, PartialTrack, PartialPlaylist, LavalinkPlaylist
from utils.others import SongRequestPurgeMode


class PlayerSession(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

        if not hasattr(bot, "player_resumed"):
            bot.player_resumed = False

        if not hasattr(bot, "player_resuming"):
            bot.player_resuming = False

        self.resume_task = bot.loop.create_task(self.resume_players())

    @commands.Cog.listener()
    async def on_player_destroy(self, player: LavalinkPlayer):

        try:
            player.queue_updater_task.cancel()
        except:
            pass

        await self.delete_data(player)

    @commands.Cog.listener('on_wavelink_track_end')
    async def track_end(self, node, payload: wavelink.TrackStart):

        if len(payload.player.queue) > 0:
            return

        await self.save_info(payload.player)

    async def queue_updater_task(self, player: LavalinkPlayer):

        while True:
            await asyncio.sleep(self.bot.config["PLAYER_INFO_BACKUP_INTERVAL"])
            await self.save_info(player)

    async def save_info(self, player: LavalinkPlayer):

        if not player.guild.me.voice:
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

        data = {
            "_id": player.guild.id,
            "version": getattr(player, "version", 1),
            "volume": player.volume,
            "nightcore": player.nightcore,
            "position": player.position,
            "voice_channel": player.guild.me.voice.channel.id,
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
            "custom_skin_data": player.custom_skin_data,
            "custom_skin_static_data": player.custom_skin_static_data,
            "uptime": player.uptime,
            "restrict_mode": player.restrict_mode,
            "mini_queue_enabled": player.mini_queue_enabled,
            "listen_along_invite": player.listen_along_invite,
            "current": player.current,
            "queue": player.queue,
            "played": player.played,
            "queue_autoplay": player.queue_autoplay,
            "failed_tracks": player.failed_tracks,
            "prefix_info": player.prefix_info,
            "purge_mode": player.purge_mode,
        }

        try:
            await self.save_session(player, data=data)
        except:
            traceback.print_exc()

    def process_track_cls(self, data: list, playlists: dict = None):

        if not playlists:
            playlists = {}

        tracks = []

        for track in data:

            if track.info["sourceName"] == "spotify":

                if playlist:=track.playlist:

                    try:
                        playlist = playlists[track.playlist_url]
                    except KeyError:
                        playlist_cls = PartialPlaylist(
                            {
                                'loadType': 'PLAYLIST_LOADED',
                                'playlistInfo': {
                                    'name': track.playlist_name,
                                    'selectedTrack': -1
                                },
                                'tracks': []
                            }, url=track.playlist_url
                        )
                        playlists[track.playlist_url] = playlist_cls
                        playlist = playlist_cls

                t = PartialTrack(info=track.info, playlist=playlist)
                t.id = ""

            else:

                if playlist := track.playlist:

                    try:
                        playlist = playlists[track.playlist_url]
                    except KeyError:
                        playlist_cls = LavalinkPlaylist(
                            {
                                'loadType': 'PLAYLIST_LOADED',
                                'playlistInfo': {
                                    'name': track.playlist_name,
                                    'selectedTrack': -1
                                },
                                'tracks': []
                            }, url=track.playlist_url
                        )
                        playlists[track.playlist_url] = playlist_cls
                        playlist = playlist_cls

                t = LavalinkTrack(id_=track.id, info=track.info, playlist=playlist)

            tracks.append(t)

        return tracks, playlists

    async def resume_players(self):

        try:
            if self.bot.player_resuming:
                return

            self.bot.player_resuming = True

            await self.bot.wait_until_ready()

            while not self.bot.bot_ready:
                await asyncio.sleep(3)

            while True:

                node = self.bot.music.get_best_node()

                if not node:
                    try:
                        node = await self.bot.wait_for("wavelink_node_ready", timeout=5)
                    except asyncio.TimeoutError:
                        continue

                break

            hints = self.bot.config["EXTRA_HINTS"].split("||")
        except Exception:
            print(traceback.format_exc())
            self.bot.player_resuming = False
            return

        try:

            data_list = await self.get_player_sessions()

            for data in data_list:

                guild = self.bot.get_guild(data["_id"])

                if not guild:
                    print(f"{self.bot.user} - Player Ignorado: {data['_id']} | Servidor inexistente...")
                    await self.delete_data(data['_id'])
                    continue

                voice_channel = self.bot.get_channel(data["voice_channel"])

                if not voice_channel:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\nO canal de voz não existe...")
                    await self.delete_data(guild.id)
                    continue

                try:
                    can_connect(voice_channel, guild=guild, bot=self.bot)
                except Exception as e:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\n{repr(e)}")
                    await self.delete_data(guild.id)
                    continue

                message = None

                if not data["text_channel_id"]:
                    text_channel = None
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

                if data["purge_mode"] == SongRequestPurgeMode.on_player_start:
                    data["purge_mode"] = SongRequestPurgeMode.no_purge
                    temp_purge_mode = True
                else:
                    temp_purge_mode = False

                try:
                    player: LavalinkPlayer = self.bot.music.get_player(
                        node_id=node.identifier,
                        guild_id=guild.id,
                        cls=LavalinkPlayer,
                        guild=guild,
                        channel=text_channel,
                        message=message or message_without_thread,
                        last_message_id=data["message_id"],
                        skin=data["skin"] if data["skin"] in self.bot.player_skins else "default",
                        skin_static=data["skin_static"] if data["skin_static"] in self.bot.player_static_skins else "default",
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
                        volume=int(data["volume"]),
                        prefix=data["prefix_info"],
                        purge_mode=data["purge_mode"],
                    )
                except Exception:
                    print(f"{self.bot.user} - Falha ao criar player: {guild.name} [{guild.id}]\n{traceback.format_exc()}")
                    # await self.delete_data(guild.id)
                    continue

                try:
                    player.mini_queue_enabled = data["mini_queue_enabled"]
                except:
                    pass

                if temp_purge_mode:
                    player.purge_mode = SongRequestPurgeMode.on_player_start

                player.listen_along_invite = data.pop("listen_along_invite", "")

                player.dj = set(data["dj"])
                player.loop = data["loop"]

                player.nightcore = data.get("nightcore")

                if player.nightcore:
                    await player.set_timescale(pitch=1.2, speed=1.1)

                if data["current"]:
                    data["queue"].insert(0, data["current"])

                if data.get("version", 1) < player.version:

                    tracks, playlists = self.process_track_cls(data["queue"])

                    player.queue.extend(tracks)

                    played_tracks, playlists = self.process_track_cls(data["played"], playlists)

                    player.played.extend(played_tracks)

                    queue_autoplay_tracks, playlists = self.process_track_cls(data.get("queue_autoplay", []))

                    player.queue_autoplay.extend(queue_autoplay_tracks)

                    failed_tracks, playlists = self.process_track_cls(data.get("failed_tracks", []), playlists)

                    player.queue.extend(failed_tracks)

                    playlists.clear()
                    tracks.clear()
                    played_tracks.clear()
                    queue_autoplay_tracks.clear()
                    failed_tracks.clear()

                else:
                    player.queue.extend(data["queue"])
                    player.played.extend(data["played"])
                    player.queue_autoplay.extend(data["queue_autoplay"])
                    player.failed_tracks.extend(data["failed_tracks"])

                await player.connect(voice_channel.id)

                while not guild.me.voice:
                    await asyncio.sleep(1)

                if isinstance(voice_channel, disnake.StageChannel) and \
                        voice_channel.permissions_for(guild.me).mute_members:

                    await asyncio.sleep(3)

                    await guild.me.edit(suppress=False)

                player.set_command_log(
                    text="O player foi restaurado com sucesso!",
                    emoji="🔰"
                )

                try:
                    player.stage_title_event = data["stage_title_event"]
                except:
                    pass

                try:
                    check = any(m for m in player.guild.me.voice.channel.members if not m.bot)
                except:
                    check = None

                if data.get("paused") and check:

                    try:
                        track = player.queue.popleft()
                    except:
                        track = None

                    if track:
                        player.current = track
                        position = int(float(data.get("position", 0)))
                        await player.play(track, start=position if not track.is_stream else 0)
                        player.last_position = position
                        player.last_track = track
                        await player.set_pause(True)
                        await player.invoke_np(rpc_update=True)
                        await player.update_stage_topic()

                    else:
                        await player.process_next()

                else:
                    position = int(float(data.get("position", 0)))
                    await player.process_next(start_position=position)

                try:
                    player.members_timeout_task.cancel()
                except:
                    pass

                player.members_timeout_task = self.bot.loop.create_task(player.members_timeout(check=check, idle_timeout=10))

                print(f"{self.bot.user} - Player Retomado: {guild.name} [{guild.id}]")

        except Exception:
            print(f"{self.bot.user} - Falha Crítica ao retomar players:\n{traceback.format_exc()}")

        self.bot.player_resumed = True

    async def get_player_sessions(self):

        if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            return [pickle.loads(b64decode(d["data"])) for d in await self.bot.pool.mongo_database.query_data(db_name=str(self.bot.user.id), collection="player_sessions_bin")]

        try:
            files = os.listdir(f"./local_database/player_sessions_bin/{self.bot.user.id}")
        except FileNotFoundError:
            return []

        guild_data = []

        for file in files:

            if not file.endswith(".pkl"):
                continue

            guild_id = file[:-4]

            async with aiofiles.open(f'./local_database/player_sessions_bin/{self.bot.user.id}/{guild_id}.pkl', 'rb') as f:
                data = pickle.loads(await f.read())

            if data:
                guild_data.append(data)

        return guild_data

    async def save_session(self, player: LavalinkPlayer, data: dict):

        try:
            player = player.bot.music.players[player.guild.id]
        except:
            try:
                player.queue_updater_task.cancel()
            except:
                pass
            return

        if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            await self.bot.pool.mongo_database.update_data(
                id_=str(player.guild.id),
                data={"data": b64encode(pickle.dumps(data)).decode('utf-8')},
                collection="player_sessions_bin",
                db_name=str(self.bot.user.id)
            )
            return

        if not os.path.isdir(f"./local_database/player_sessions_bin/{self.bot.user.id}"):
            os.makedirs(f"./local_database/player_sessions_bin/{self.bot.user.id}")

        path = f'./local_database/player_sessions_bin/{self.bot.user.id}/{player.guild.id}'

        try:
            async with aiofiles.open(f"{path}.pkl", "wb") as f:
                await f.write(pickle.dumps(data))
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

    async def delete_data(self, player: Union[LavalinkPlayer, int]):

        if not isinstance(player, LavalinkPlayer):

            guild_id = int(player)

            try:
                player = self.bot.music.players[guild_id]
            except KeyError:
                player = None

        else:
            guild_id = player.guild.id

        if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            await self.bot.pool.mongo_database.delete_data(id_=str(guild_id), db_name=str(self.bot.user.id), collection="player_sessions_bin")
            return

        for ext in ('.pkl', '.bak'):
            try:
                os.remove(f'./local_database/player_sessions_bin/{self.bot.user.id}/{guild_id}{ext}')
            except FileNotFoundError:
                continue
            except Exception:
                traceback.print_exc()

    def cog_unload(self):
        try:
            self.resume_task.cancel()
        except:
            pass

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
