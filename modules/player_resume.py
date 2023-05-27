# -*- coding: utf-8 -*-

# nota: este sistema é totalmente experimental.
import asyncio
import json
import os
import traceback

import aiosqlite
import disnake
from disnake.ext import commands

import wavelink
from utils.client import BotCore
from utils.music.checks import can_connect, can_send_message
from utils.music.models import LavalinkPlayer, LavalinkTrack, PartialTrack, PartialPlaylist, LavalinkPlaylist


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
            text_channel = str(player.text_channel.id)
            message = None

        data = {
            "_id": str(player.guild.id),
            "volume": str(player.volume),
            "nightcore": player.nightcore,
            "position": str(player.position),
            "voice_channel": str(player.guild.me.voice.channel.id),
            "dj": list(player.dj),
            "player_creator": str(player.player_creator) if player.player_creator else None,
            "static": player.static,
            "paused": player.paused,
            "text_channel": text_channel,
            "keep_connected": player.keep_connected,
            "message": message,
            "played": played,
            "loop": player.loop,
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
            "tracks": tracks
        }

        try:
            await self.save_session(player, data=data)
        except:
            traceback.print_exc()

    async def resume_players(self):

        if self.bot.player_resuming:
            return

        self.bot.player_resuming = True

        await self.bot.wait_until_ready()

        await asyncio.sleep(5)

        node = self.bot.music.get_best_node() or await self.bot.wait_for("wavelink_node_ready")

        while not self.bot.bot_ready:
            await asyncio.sleep(2)

        hints = self.bot.config["EXTRA_HINTS"].split("||")

        try:

            data_list = await self.get_player_sessions()

            for data in data_list:

                guild = self.bot.get_guild(int(data["_id"]))

                if not guild:
                    print(f"{self.bot.user} - Player Ignorado: {data['_id']} | Servidor inexistente...")
                    await self.delete_data(guild.id)
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
                except disnake.NotFound:
                    text_channel = None

                if not text_channel:

                    message = False

                    if data["text_channel"] != str(voice_channel.id) and data['static']:
                        data['static'] = False

                    text_channel = voice_channel

                try:
                    can_send_message(text_channel, self.bot.user)
                except Exception:
                    print(f"{self.bot.user} - Player Ignorado (falta de permissão) [Canal: {text_channel.name} | ID: {text_channel.id}] - [ {guild.name} - {guild.id} ]")
                    await self.delete_data(guild.id)
                    continue

                try:
                    creator = int(data["player_creator"])
                except:
                    creator = None

                message_without_thread = None

                if message is None:

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
                    player: LavalinkPlayer = self.bot.music.get_player(
                        node_id=node.identifier,
                        guild_id=guild.id,
                        cls=LavalinkPlayer,
                        guild=guild,
                        channel=text_channel,
                        message=message or message_without_thread,
                        skin=data["skin"],
                        skin_static=data["skin_static"],
                        player_creator=creator,
                        keep_connected=data["keep_connected"],
                        static=data['static'],
                        custom_skin_data=data.get("custom_skin_data", {}),
                        custom_skin_static_data=data.get("custom_skin_static_data", {}),
                        extra_hints=hints,
                        uptime=data.get("uptime"),
                        stage_title_template=data.get("stage_title_template"),
                        restrict_mode=data["restrict_mode"],
                        volume=int(data["volume"])
                    )
                except Exception:
                    print(f"{self.bot.user} - Falha ao criar player: {guild.name} [{guild.id}]\n{traceback.format_exc()}")
                    await self.delete_data(guild.id)
                    continue

                try:
                    player.mini_queue_enabled = data["mini_queue_enabled"]
                except:
                    pass

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

                playlists = {}

                for info in data["tracks"]:

                    if info["sourceName"] == "spotify":

                        if playlist:=info.pop("playlist", None):

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
                                    }, url = playlist["url"]
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
                    player.queue.append(t)

                playlists.clear()

                for info in data["played"]:
                    if info["sourceName"] == "spotify":
                        t = PartialTrack(info=info)
                    else:
                        t = LavalinkTrack(id_=info["id"], info=info)
                    del t.info["id"]
                    player.played.append(t)

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

                if data.get("paused"):

                    try:
                        track = player.queue.popleft()
                    except:
                        track = None

                    if track:
                        await player.play(track, start=int(data["position"]))
                        await player.set_pause(True)
                        player.current = track
                        player.last_track = track
                        await player.invoke_np(rpc_update=True)

                    else:
                        await player.process_next()

                else:
                    await player.process_next(start_position=int(float(data["position"])))

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
            except ValueError:
                try:
                    player.conn.close()
                except:
                    pass
                player.conn_cursor = None
                await self.save_session(player, data)
                return

            await player.conn_cursor.execute('INSERT INTO dados (json_data) VALUES (?)', (json_str,))

        await player.conn.commit()

    async def delete_data(self, player: LavalinkPlayer):

        if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            await self.bot.pool.mongo_database.delete_data(id_=str(player.guild_id), db_name=str(self.bot.user.id), collection="player_sessions")
            return

        try:
            await player.conn.close()
        except:
            pass

        try:
            os.remove(f'./local_database/player_sessions/{self.bot.user.id}/{player.guild_id}.db')
        except FileNotFoundError:
            return

    def cog_unload(self):
        try:
            self.resume_task.cancel()
        except:
            pass

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
