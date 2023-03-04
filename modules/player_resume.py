# nota: este sistema é totalmente experimental.
import asyncio
import traceback

import disnake
from disnake.ext import commands

import wavelink
from utils.client import BotCore
from utils.music.checks import can_connect
from utils.music.models import LavalinkPlayer, LavalinkTrack, PartialTrack, PartialPlaylist, LavalinkPlaylist
from utils.others import CustomContext


class PlayerSession(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

        if not hasattr(bot, "player_resumed"):
            bot.player_resumed = False

        self.resume_task = bot.loop.create_task(self.resume_players())

    @commands.Cog.listener()
    async def on_player_destroy(self, player: LavalinkPlayer):
        await self.bot.pool.database.delete_data(
            str(player.guild.id),
            collection="player_sessions",
            db_name=str(player.bot.user.id)
        )

    @commands.Cog.listener('on_wavelink_track_end')
    async def track_end(self, node, payload: wavelink.TrackStart):

        if len(payload.player.queue) > 0:
            return

        await self.save_info(payload.player)

    @commands.Cog.listener('on_wavelink_track_start')
    async def track_start(self, node, payload: wavelink.TrackStart):

        try:
            payload.player.queue_updater_task.cancel()
        except:
            pass

        payload.player.queue_updater_task = self.bot.loop.create_task(self.queue_updater_task(payload.player))

    async def queue_updater_task(self, player: LavalinkPlayer):

        while True:
            await self.save_info(player)
            await asyncio.sleep(30)

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

        data = {
            "_id": str(player.guild.id),
            "volume": player.volume,
            "nightcore": player.nightcore,
            "position": player.position,
            "voice_channel": player.channel_id,
            "dj": list(player.dj),
            "player_creator": player.player_creator,
            "static": player.static,
            "paused": player.paused,
            "text_channel": player.text_channel.id,
            "keep_connected": player.keep_connected,
            "message": player.message.id if player.message else None,
            "played": played,
            "loop": player.loop,
            "stage_title_event": player.stage_title_event,
            "skin": player.skin,
            "skin_static": player.skin_static,
            "restrict_mode": player.restrict_mode,
            "mini_queue_enabled": player.mini_queue_enabled,
            "tracks": tracks
        }

        bot_id = str(player.bot.user.id)

        try:
            await self.bot.pool.database.update_data(
                str(player.guild.id),
                data=data,
                collection="player_sessions",
                db_name=bot_id,
                default_model={bot_id: {}}
            )
        except:
            traceback.print_exc()

    async def resume_players(self):

        if self.bot.player_resumed:
            return

        await self.bot.wait_until_ready()

        node = self.bot.music.get_best_node() or await self.bot.wait_for("wavelink_node_ready")

        hints = self.bot.config["EXTRA_HINTS"].split("||")

        try:

            for data in await self.bot.pool.database.query_data(db_name=str(self.bot.user.id), collection="player_sessions"):

                guild = self.bot.get_guild(int(data["_id"]))

                if not guild:
                    print(f"{self.bot.user} - Player Ignorado: {data['_id']} | Servidor inexistente...")
                    continue

                voice_channel = self.bot.get_channel(data["voice_channel"])

                if not voice_channel:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\nO canal de voz não existe...")
                    continue

                try:
                    can_connect(voice_channel, guild=guild)
                except Exception as e:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\n{repr(e)}")
                    continue

                text_channel = self.bot.get_channel(data["text_channel"])

                if not text_channel:
                    continue

                try:
                    creator = data["player_creator"]
                except KeyError:
                    creator = None

                try:
                    message = await text_channel.fetch_message(data["message"])
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
                        extra_hints=hints,
                    )
                except Exception:
                    print(f"{self.bot.user} - Falha ao criar player: {guild.name} [{guild.id}]\n{traceback.format_exc()}")
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

                if data["volume"] != 100:
                    await player.set_volume(data["volume"])

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

                await player.process_next(start_position=data["position"])

                if data.get("paused"):
                    await asyncio.sleep(1.5)
                    if player.current:
                        await player.set_pause(True)

                print(f"{self.bot.user} - Player Retomado: {guild.name} [{guild.id}]")

        except Exception:
            print(f"{self.bot.user} - Falha Crítica ao retomar players:\n{traceback.format_exc()}")



    def cog_unload(self):
        try:
            self.resume_task.cancel()
        except:
            pass

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
