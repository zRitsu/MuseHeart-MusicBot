# nota: este sistema é totalmente experimental.
# Será necessário usar um comando para salvar as sessões atuais do player manualmente.

import os.path
import shutil
import traceback
import disnake
from disnake.ext import commands
from utils.client import BotCore
import json
import asyncio
from utils.music.checks import can_connect, ensure_bot_instance
from utils.music.models import LavalinkPlayer, LavalinkTrack, PartialTrack, PartialPlaylist, LavalinkPlaylist
from utils.others import CustomContext


class PlayerSession(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.resumed = False
        self.resume_task = bot.loop.create_task(self.resume_players())

    async def resume_players(self):

        if self.resumed:
            return

        await self.bot.wait_until_ready()

        node = self.bot.music.get_best_node() or await self.bot.wait_for("wavelink_node_ready")

        try:

            for f in os.listdir(f"./.player_sessions/{self.bot.user.id}"):

                if not f.endswith(".json"):
                    continue

                with open(f"./.player_sessions/{self.bot.user.id}/{f}") as fp:
                    data = json.load(fp)

                guild = self.bot.get_guild(int(f[:-5]))

                if not guild:
                    print(f"{self.bot.user} - Player Ignorado: {f[:-5]} | Servidor inexistente...")
                    continue

                voice_channel = self.bot.get_channel(data["voice_channel"])

                if not voice_channel:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\nO canal de voz não existe...")
                    continue

                try:
                    can_connect(voice_channel, guild=guild, bot=self.bot)
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

                if data["volume"] != 100:
                    await player.set_volume(data["volume"])

                playlists = {}

                for info in data["tracks"]:

                    if info["sourceName"] == "spotify":

                        if playlist:=info.pop("playlist", None):

                            try:
                                playlist = playlists[playlist["url"]]
                            except KeyError:
                                playlist = PartialPlaylist(
                                    {
                                        'loadType': 'PLAYLIST_LOADED',
                                        'playlistInfo': {
                                            'name': playlist["name"],
                                            'selectedTrack': -1
                                        },
                                        'tracks': []
                                    }, url = playlist["url"]
                                )

                        t = PartialTrack(info=info, playlist=playlist)

                    else:

                        if playlist := info.pop("playlist", None):

                            try:
                                playlist = playlists[playlist["url"]]
                            except KeyError:
                                playlist = LavalinkPlaylist(
                                    {
                                        'loadType': 'PLAYLIST_LOADED',
                                        'playlistInfo': {
                                            'name': playlist["name"],
                                            'selectedTrack': -1
                                        },
                                        'tracks': []
                                    }, url=playlist["url"]
                                )

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

            shutil.rmtree(f"./.player_sessions/{self.bot.user.id}")

        except FileNotFoundError:
            return

        except Exception:
            print(f"{self.bot.user} - Falha Crítica ao retomar players:\n{traceback.format_exc()}")


    @commands.max_concurrency(1, commands.BucketType.default)
    @commands.is_owner()
    @ensure_bot_instance(return_first=True)
    @commands.command(hidden=True, aliases=["savep"])
    async def saveplayers(self, ctx: CustomContext, *args):

        saved_players = 0
        ignored_players = 0

        reset_ids  = any(a in args for a in ("--reset", "--resetids", "-reset", "-resetids"))

        async with ctx.typing():

            for bot in self.bot.pool.bots:

                if not os.path.isdir(f"./.player_sessions/{bot.user.id}"):
                    os.makedirs(f"./.player_sessions/{bot.user.id}")

                for player in bot.music.players.values():

                    tracks = []
                    played = []

                    if player.current:
                        player.current.info["id"] = player.current.id if not reset_ids else ""
                        if player.current.playlist:
                            player.current.info["playlist"] = {"name": player.current.playlist.name, "url": player.current.playlist.url}
                        tracks.append(player.current.info)

                    for t in player.queue:
                        t.info["id"] = t.id if not reset_ids else ""
                        if t.playlist:
                            t.info["playlist"] = {"name": t.playlist.name, "url": t.playlist.url}
                        tracks.append(t.info)

                    for t in player.played:
                        t.info["id"] = t.id if not reset_ids else ""
                        if t.playlist:
                            t.info["playlist"] = {"name": t.playlist.name, "url": t.playlist.url}
                        played.append(t.info)

                    if not tracks and not played:
                        await player.destroy(force=True)
                        ignored_players += 1
                        continue

                    data = json.dumps(
                        {
                            "volume": player.volume,
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
                            "skin": player.skin,
                            "skin_static": player.skin_static,
                            "restrict_mode": player.restrict_mode,
                            "mini_queue_enabled": player.mini_queue_enabled,
                            "tracks": tracks
                        }, indent=4
                    )

                    with open(f"./.player_sessions/{bot.user.id}/{player.guild_id}.json", "w") as f:
                        f.write(data)

                    txt = "O player foi desligado para uma rápida manutenção/reinicialização e será restaurado logo."

                    if player.static:
                        player.set_command_log(text=txt, emoji="🛠️")
                    else:
                        self.bot.loop.create_task(
                            player.text_channel.send(
                                embed=disnake.Embed(
                                    color=self.bot.get_color(player.guild.me),
                                    description=f"🛠️ **⠂{txt}**"
                                )
                            )
                        )

                    await player.destroy(force=True)
                    saved_players += 1

        txt = ""

        if saved_players:
            txt += f"**Players salvos: {saved_players}**\n"
        if ignored_players:
            txt += f"**Players ignorados: {ignored_players}**\n"

        if not txt:
            txt = "**Nenhum player ativo no momento...**"

        self.resumed = True
        await ctx.send(embed=disnake.Embed(color=self.bot.get_color(ctx.guild.me), description=txt))

    def cog_unload(self):
        try:
            self.resume_task.cancel()
        except:
            pass

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
