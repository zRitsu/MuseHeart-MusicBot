# nota: este sistema é totalmente experimental.
# Será necessário usar um comando para salvar as sessões atuais do player manualmente.

import os.path
import shutil
from disnake.ext import commands
from utils.client import BotCore
import json
import asyncio
from utils.music.spotify import SpotifyTrack
from utils.music.checks import can_connect
from utils.music.models import LavalinkPlayer, LavalinkTrack
from utils.others import CustomContext


class PlayerSession(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        bot.loop.create_task(self.resume_players())
        self.resumed = False

    async def resume_players(self):

        if self.resumed:
            return

        await self.bot.wait_until_ready()

        while True:
            node = self.bot.music.get_best_node()
            if not node:
                await asyncio.sleep(3)
                continue
            break

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
                    can_connect(voice_channel)
                except Exception as e:
                    print(f"{self.bot.user} - Player Ignorado: {guild.name} [{guild.id}]\n{repr(e)}")
                    continue

                text_channel = self.bot.get_channel(data["text_channel"])

                if not text_channel:
                    continue

                message = await text_channel.fetch_message(data["message"])

                player: LavalinkPlayer = self.bot.music.get_player(
                    node_id=node.identifier,
                    guild_id=guild.id,
                    cls=LavalinkPlayer,
                    guild=guild,
                    channel=text_channel,
                    message=message,
                    keep_connected=data["keep_connected"],
                    static=data['static'],
                )

                player.dj = set(data["dj"])
                player.restrict_mode = data["restrict_mode"]
                player.loop = data["loop"]

                if data["volume"] != 100:
                    await player.set_volume(data["volume"])

                for info in data["tracks"]:
                    if info["sourceName"] == "spotify":
                        t = SpotifyTrack(info=info)
                    else:
                        t = LavalinkTrack(id_=info["id"], info=info)
                    del t.info["id"]
                    player.queue.append(t)

                await player.connect(voice_channel.id)

                await player.process_next(start_position=data["position"])

                print(f"{self.bot.user} - Player Retomado: {guild.name} [{guild.id}]")

            shutil.rmtree(f"./.player_sessions/{self.bot.user.id}")

        except FileNotFoundError:
            return

    @commands.max_concurrency(1, commands.BucketType.default)
    @commands.is_owner()
    @commands.command(hidden=True, aliases=["savep"])
    async def saveplayers(self, ctx: CustomContext):

        async with ctx.typing():

            for bot in self.bot.pool.bots:

                if not os.path.isdir(f"./.player_sessions/{bot.user.id}"):
                    os.makedirs(f"./.player_sessions/{bot.user.id}")

                for player in bot.music.players.values():
                    with open(f"./.player_sessions/{bot.user.id}/{player.guild_id}.json", "w") as f:

                        player.current.info["id"] = player.current.id

                        for t in player.queue:
                            t.info["id"] = t.id

                        f.write(
                            json.dumps(
                                {
                                    "volume": player.volume,
                                    "position": player.position,
                                    "voice_channel": player.channel_id,
                                    "dj": list(player.dj),
                                    "static": player.static,
                                    "text_channel": player.text_channel.id,
                                    "keep_connected": player.keep_connected,
                                    "message": player.message.id,
                                    "loop": player.loop,
                                    "restrict_mode": player.restrict_mode,
                                    "tracks": [player.current.info] +
                                              [t.info for t in player.queue]
                                }, indent=4
                            )
                        )

                    await player.destroy(force=True)

        self.resumed = True
        await ctx.send("as sessões dos players foram salvas com sucesso!")

def setup(bot: BotCore):
    bot.add_cog(PlayerSession(bot))
