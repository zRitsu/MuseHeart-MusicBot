# -*- coding: utf-8 -*-

# nota: este sistema é totalmente experimental.
import asyncio
import json
import os
import traceback
from typing import Union

import aiosqlite
import disnake
from disnake.ext import commands

import wavelink
from utils.client import BotCore
from utils.db import DBModel
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

        tracks = []
        played = []
        autoqueue = []
        failed_tracks = []

        if player.current:
            player.current.info["id"] = player.current.id
            if player.current.playlist_name:
                player.current.info["playlist"] = {"name": player.current.playlist_name, "url": player.current.playlist_url}
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

        if player.skin.startswith("> custom_skin: "):

            custom_skin = player.skin[15:]

            if player.static:
                custom_skin_data = {}
                custom_skin_static_data = {custom_skin: player.custom_skin_static_data[custom_skin]}

            else:
                custom_skin_data = {custom_skin: player.custom_skin_data[custom_skin]}
                custom_skin_static_data = {}

        else:
            custom_skin_data = {}
            custom_skin_static_data = {}

        try:
            text_channel = str(player.message.channel.id)
            message = str(player.message.id)
        except:
            text_channel = str(player.text_channel.id) if player.text_channel else None
            message = None

        try:
            prefix = player.prefix_info
        except AttributeError:
            prefix = ""

        try:
            purge_mode = player.purge_mode
        except AttributeError:
            purge_mode = SongRequestPurgeMode.on_message

        data = {
            "_id": str(player.guild.id),
            "volume": str(player.volume),
            "nightcore": player.nightcore,
            "position": str(player.position),
            "voice_channel": str(player.guild.me.voice.channel.id),
            "dj": list(player.dj),
            "player_creator": str(player.player_creator) if player.player_creator else None,
            "static": player.static,
            "paused": player.paused and not player.auto_pause,
            "text_channel": text_channel,
            "keep_connected": player.keep_connected,
            "message": message,
            "loop": player.loop,
            "autoplay": player.autoplay,
            "stage_title_event": player.stage_title_event,
            "stage_title_template": player.stage_title_template,
            "skin": player.skin,
            "skin_static": player.skin_static,
            "custom_skin_data": custom_skin_data,
            "custom_skin_static_data": custom_skin_static_data,
            "uptime": player.uptime,
            "restrict_mode": player.restrict_mode,
            "mini_queue_enabled": player.mini_queue_enabled,
            "listen_along_invite": player.listen_along_invite,
            "tracks": tracks,
            "played": played,
            "queue_autoplay": autoqueue,
            "failed_tracks": failed_tracks,
            "prefix_info": prefix,
            "purge_mode": purge_mode,
        }

        try:
            await self.save_session(player, data=data)
        except:
            traceback.print_exc()

    def process_track_cls(self, data: list, playlists: dict = None):

        if not playlists:
            playlists = {}

        tracks = []

        for info in data:

            if info["sourceName"] == "spotify":

                if playlist := info.pop("playlist", None):

                    try:
                        playlist = playlists[playlist["url"]]
                    except KeyError:
                        playlist_cls = PartialPlaylist(
                            {
                                'loadType': 'PLAYLIST_LOADED',
                                'playlistInfo': {
                                    'name': playlist["name"],
                                    'selectedTrack': -1
                                },
                                'tracks': []
                            }, url=playlist["url"]
                        )
                        playlists[playlist["url"]] = playlist_cls
                        playlist = playlist_cls

                t = PartialTrack(info=info, playlist=playlist)

            else:

                if playlist := info.pop("playlist", None):

                    try:
                        playlist = playlists[playlist["url"]]
                    except KeyError:
                        playlist_cls = LavalinkPlaylist(
                            {
                                'loadType': 'PLAYLIST_LOADED',
                                'playlistInfo': {
                                    'name': playlist["name"],
                                    'selectedTrack': -1
                                },
                                'tracks': []
                            }, url=playlist["url"]
                        )
                        playlists[playlist["url"]] = playlist_cls
                        playlist = playlist_cls

                t = LavalinkTrack(id_=info["id"], info=info, playlist=playlist)

            del t.info["id"]
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
            traceback.print_exc()
            self.bot.player_resuming = False
            return

        try:

            data_list = await self.get_player_sessions()

            for data in data_list:

                guild = self.bot.get_guild(int(data["_id"]))

                if not guild:
                    print(f"{self.bot.user} - Player Ignorado: {data['_id']} | Servidor inexistente...")
                    await self.delete_data(data['_id'])
                    continue

                voice_channel = self.bot.get_channel(int(data["voice_channel"]))

                message = None

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

                try:
                    text_channel = self.bot.get_channel(int(data["text_channel"])) or \
                               await self.bot.fetch_channel(int(data["text_channel"]))
                except (disnake.NotFound, TypeError):
                    text_channel = None

                if not text_channel:

                    message = False

                    if data["text_channel"] != str(voice_channel.id) and data['static']:
                        data['static'] = False

                    text_channel = voice_channel

                if text_channel:
                    try:
                        can_send_message(text_channel, self.bot.user)
                    except Exception:
                        print(f"{self.bot.user} - Controller Ignorado (falta de permissão) [Canal: {text_channel.name} | ID: {text_channel.id}] - [ {guild.name} - {guild.id} ]")
                        text_channel = None

                try:
                    creator = int(data["player_creator"])
                except:
                    creator = None

                message_without_thread = None

                if message is None and text_channel:

                    try:
                        message = await text_channel.fetch_message(int(data["message"]))
                    except:
                        if not text_channel.permissions_for(guild.me).read_message_history:
                            print(f"{self.bot.user} - Não foi possível obter a mensagem e não tem permissão para "
                                  f"ler o histórico de mensagens. O player controller será reenviado.\n"
                                  f"Servidor: {guild} [{guild.id}]\n"
                                  f"Canal: {text_channel.name} [{text_channel.id}]")
                        else:
                            try:
                                async for msg in text_channel.history(limit=100):

                                    if not message:
                                        continue

                                    if message.author.id != self.bot.user.id:
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

                try:
                    last_message_id = message.id
                except AttributeError:
                    last_message_id = None

                if not (prefix:=data.get("prefix_info")):
                    global_data = await self.bot.get_global_data(guild.id, db_name=DBModel.guilds)
                    prefix = global_data["prefix"] or self.bot.default_prefix

                purge_mode = data.get("purge_mode", SongRequestPurgeMode.on_message)

                if purge_mode == SongRequestPurgeMode.on_player_start:
                    purge_mode = SongRequestPurgeMode.no_purge
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
                        last_message_id=last_message_id,
                        skin=data["skin"],
                        skin_static=data["skin_static"],
                        player_creator=creator,
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
                        prefix=prefix,
                        purge_mode=purge_mode,
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

                try:
                    player.stage_title_event = data["stage_title_event"]
                except:
                    pass

                player.nightcore = data.get("nightcore")

                if player.nightcore:
                    await player.set_timescale(pitch=1.2, speed=1.1)

                tracks, playlists = self.process_track_cls(data["tracks"])

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
                        await player.play(track, start=int(data["position"]))
                        player.last_track = track
                        await player.set_pause(True)
                        await player.invoke_np(rpc_update=True)

                    else:
                        await player.process_next()

                else:
                    await player.process_next(start_position=int(float(data["position"])))

                try:
                    player.members_timeout_task.cancel()
                except:
                    pass

                if not check:
                    await player.members_timeout(check=check, force=True)
                else:
                    player.members_timeout_task = self.bot.loop.create_task(player.members_timeout(check=check))

                print(f"{self.bot.user} - Player Retomado: {guild.name} [{guild.id}]")

        except Exception:
            print(f"{self.bot.user} - Falha Crítica ao retomar players:\n{traceback.format_exc()}")

        self.bot.player_resumed = True

    async def get_player_sessions(self):

        if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            return await self.bot.pool.mongo_database.query_data(db_name=str(self.bot.user.id), collection="player_sessions")

        try:
            files = os.listdir(f"./local_database/player_sessions/{self.bot.user.id}")
        except FileNotFoundError:
            return []

        guild_data = []

        for file in files:

            guild_id = file[:-3]

            conn = await aiosqlite.connect(f'./local_database/player_sessions/{self.bot.user.id}/{guild_id}.db')
            c = await conn.cursor()

            await c.execute('SELECT json_data FROM dados')
            data = await c.fetchone()

            await conn.close()

            if data:
                guild_data.append(json.loads(data[0]))

        return guild_data

    async def check_session(self, player: LavalinkPlayer):

        try:
            player.conn_cursor
        except AttributeError:
            try:
                conn = await aiosqlite.connect(f'./local_database/player_sessions/{self.bot.user.id}/{player.guild.id}.db')
            except aiosqlite.OperationalError:
                os.makedirs(f"./local_database/player_sessions/{self.bot.user.id}/")
                conn = await aiosqlite.connect(f'./local_database/player_sessions/{self.bot.user.id}/{player.guild.id}.db')
            player.conn = conn
            player.conn_cursor = await conn.cursor()

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
                data=data,
                collection="player_sessions",
                db_name=str(self.bot.user.id)
            )
            return

        await self.check_session(player)

        json_str = json.dumps(data)

        try:
            await player.conn_cursor.execute('UPDATE dados SET json_data = ? WHERE id = ?', (json_str, 1))
        except:
            try:
                await player.conn_cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dados (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        json_data TEXT
                    )
                ''')
            except (ValueError, AttributeError):
                try:
                    player.conn.close()
                except:
                    pass
                player.conn_cursor = None
                await self.save_session(player, data)
                return

            await player.conn_cursor.execute('INSERT INTO dados (json_data) VALUES (?)', (json_str,))

        await player.conn.commit()

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
            await self.bot.pool.mongo_database.delete_data(id_=str(guild_id), db_name=str(self.bot.user.id), collection="player_sessions")
            return

        try:
            await player.conn.close()
        except:
            pass

        try:
            os.remove(f'./local_database/player_sessions/{self.bot.user.id}/{guild_id}.db')
        except FileNotFoundError:
            return

    def cog_unload(self):
        try:
            self.resume_task.cancel()
        except:
            pass

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
