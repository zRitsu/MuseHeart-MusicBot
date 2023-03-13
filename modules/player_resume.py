# nota: este sistema é totalmente experimental.
import asyncio
import json
import os
import shutil
import traceback

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

        self.resume_task = bot.loop.create_task(self.resume_players())

    @commands.Cog.listener()
    async def on_player_destroy(self, player: LavalinkPlayer):

        try:
            player.queue_updater_task.cancel()
        except:
            pass

        await self.database().delete_data(
            id_=str(player.guild.id),
            collection="player_sessions",
            db_name=str(player.bot.user.id)
        )

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
            "text_channel": str(player.text_channel.id),
            "keep_connected": player.keep_connected,
            "message": str(player.message.id) if player.message else None,
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
            "tracks": tracks
        }

        bot_id = str(player.bot.user.id)

        try:
            await self.database().update_data(
                id_=str(player.guild.id),
                data=data,
                collection="player_sessions",
                db_name=bot_id
            )
        except:
            traceback.print_exc()

    def database(self):
        if self.bot.config["PLAYER_SESSIONS_MONGODB"] and self.bot.config["MONGO"]:
            return self.bot.pool.mongo_database
        return self.bot.pool.local_database

    async def resume_players(self):

        if self.bot.player_resumed:
            return

        await self.bot.wait_until_ready()

        node = self.bot.music.get_best_node() or await self.bot.wait_for("wavelink_node_ready")

        hints = self.bot.config["EXTRA_HINTS"].split("||")

        try:

            data_list = []

            try:
                for f in os.listdir(f"./.player_sessions/{self.bot.user.id}"):

                    if not f.endswith(".json"):
                        continue

                    try:
                        with open(f"./.player_sessions/{self.bot.user.id}/{f}") as fp:
                            json_data = json.load(fp)
                    except Exception:
                        traceback.print_exc()
                        continue

                    json_data.update({"_id": f[:-5]})
                    data_list.append(json_data)
                shutil.rmtree(f"./.player_sessions/{self.bot.user.id}")
            except:
                pass

            database = self.database()

            if not data_list:
                data_list = await database.query_data(db_name=str(self.bot.user.id), collection="player_sessions")

            for data in data_list:

                guild = self.bot.get_guild(int(data["_id"]))

                if not guild:
                    print(f"{self.bot.user} - Player Ignorado: {data['_id']} | Servidor inexistente...")
                    await database.delete_data(data['_id'], str(self.bot.user.id), collection="player_sessions")
                    continue

                voice_channel = self.bot.get_channel(int(data["voice_channel"]))

                if not voice_channel:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\nO canal de voz não existe...")
                    await database.delete_data(data['_id'], str(self.bot.user.id), collection="player_sessions")
                    continue

                try:
                    can_connect(voice_channel, guild=guild)
                except Exception as e:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\n{repr(e)}")
                    await database.delete_data(data['_id'], str(self.bot.user.id), collection="player_sessions")
                    continue

                text_channel = self.bot.get_channel(int(data["text_channel"]))

                if not text_channel:

                    if data["text_channel"] != str(voice_channel.id) and data['static']:
                        data['static'] = False

                    text_channel = voice_channel

                try:
                    can_send_message(text_channel, self.bot.user)
                except Exception:
                    print(f"{self.bot.user} - Player Ignorado (falta de permissão) [Canal: {text_channel.name} | ID: {text_channel.id}] - [ {guild.name} - {guild.id} ]")
                    await database.delete_data(data['_id'], str(self.bot.user.id), collection="player_sessions")
                    continue

                try:
                    creator = int(data["player_creator"])
                except:
                    creator = None

                try:
                    message = await text_channel.fetch_message(int(data["message"]))
                except:
                    message = None

                try:
                    player: LavalinkPlayer = self.bot.music.get_player(
                        node_id=node.identifier,
                        guild_id=guild.id,
                        cls=LavalinkPlayer,
                        guild=guild,
                        channel=text_channel,
                        message=message,
                        skin=data["skin"],
                        skin_static=data["skin_static"],
                        player_creator=creator,
                        keep_connected=data["keep_connected"],
                        static=data['static'],
                        custom_skin_data=data.get("custom_skin_data", {}),
                        custom_skin_static_data=data.get("custom_skin_static_data", {}),
                        extra_hints=hints,
                        uptime=data.get("uptime"),
                        stage_title_template=data.get("stage_title_template")
                    )
                except Exception:
                    print(f"{self.bot.user} - Falha ao criar player: {guild.name} [{guild.id}]\n{traceback.format_exc()}")
                    await database.delete_data(data['_id'], str(self.bot.user.id), collection="player_sessions")
                    continue

                try:
                    player.mini_queue_enabled = data["mini_queue_enabled"]
                except:
                    pass

                player.dj = set(data["dj"])
                player.restrict_mode = data["restrict_mode"]
                player.loop = data["loop"]

                try:
                    player.stage_title_event = data["stage_title_event"]
                except:
                    pass

                if (vol:=int(data["volume"])) != 100:
                    await player.set_volume(vol)

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

                if isinstance(voice_channel, disnake.StageChannel):

                    while not guild.me.voice:
                        await asyncio.sleep(1)

                    if voice_channel.permissions_for(guild.me).mute_members:
                        await asyncio.sleep(1.5)
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
                        player.paused = True
                        player.last_position = float(data["position"])
                        player.current = track
                        await player.invoke_np(rpc_update=True)

                    else:
                        await player.process_next()

                else:
                    await player.process_next(start_position=float(data["position"]))

                print(f"{self.bot.user} - Player Retomado: {guild.name} [{guild.id}]")

        except Exception:
            print(f"{self.bot.user} - Falha Crítica ao retomar players:\n{traceback.format_exc()}")

        self.bot.player_resumed = True

    def cog_unload(self):
        try:
            self.resume_task.cancel()
        except:
            pass

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
