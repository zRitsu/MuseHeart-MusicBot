from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime
from typing import TYPE_CHECKING

import disnake
import pylast
from disnake.ext import commands

from utils.db import DBModel
from utils.music.models import LavalinkPlayer, LavalinkTrack
from utils.others import CustomContext

if TYPE_CHECKING:
    from utils.client import BotCore


class LastFMView(disnake.ui.View):

    def __init__(self, ctx, url):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.url = url

        btn = disnake.ui.Button(label="Integrar sua conta do last.fm")
        btn.callback = self.ephemeral_callback
        self.add_item(btn)

    async def on_timeout(self) -> None:
        for c in self.children:
            c.disabled = True

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.send("Você não pode usar esse botão", ephemeral=True)
            return False

        return True

    async def ephemeral_callback(self, interaction: disnake.MessageInteraction):
        await interaction.send(f"### [Clique aqui](<{self.url}>) para integrar sua conta do last.fm", ephemeral=True)

class LastFmCog(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

        if not hasattr(bot.pool, "lastfm_sessions"):
            bot.pool.lastfm_sessions = {}

        if not self.bot.pool.skg:
            self.bot.pool.skg = pylast.SessionKeyGenerator(
                pylast.LastFMNetwork(self.bot.pool.config["LASTFM_KEY"], self.bot.pool.config["LASTFM_SECRET"])
            )

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(hidden=True, name="lastfm", aliases=["scb", "scrobbler", "lfm"])
    async def scrobbler_legacy(self, ctx: CustomContext):

        url = await self.bot.loop.run_in_executor(None, lambda: self.bot.pool.skg.get_web_auth_url())

        embed = disnake.Embed(
            description="Integre sua conta do [last.fm](<https://www.last.fm/home>) para registrar todas as músicas "
                        "que você ouvir por aqui para obter sugestões de artistas, músicas e etc pelo site do last.fm."
                        "\n\n`Nota: Você tem apenas 1 minuto para efetuar esse processo (e aguarde até essa mensagem "
                        "ser atualizada).`",
            color=self.bot.get_color(ctx.guild.me)
        ).set_thumbnail(url="https://www.last.fm/static/images/lastfm_avatar_twitter.52a5d69a85ac.png")

        view = LastFMView(ctx, url)

        msg = await ctx.send(embed=embed, view=view)

        ctx.store_message = msg

        await view.wait()

        try:
            session_key = await self.bot.loop.run_in_executor(None, lambda: self.bot.pool.skg.get_web_auth_session_key(url))
        except pylast.WSError as e:
            if "This token has not been authorized" in e.status:
                await msg.edit(embed=disnake.Embed(
                    description="### O tempo para linkar sua conta do last.fm expirou!\n\n"
                                "Use o comando novamente caso queira repetir o processo.",
                    color=self.bot.get_color(ctx.guild.me)))
                return
            raise e

        try:
            data = ctx.global_user_data
        except AttributeError:
            data = await self.bot.get_global_data(ctx.author.id, db_name=DBModel.users)
            ctx.global_user_data = data

        newdata = {"scrobble": True, "sessionkey": session_key}
        data["lastfm"].update(newdata)
        await self.bot.update_global_data(ctx.author.id, data=data, db_name=DBModel.users)

        self.bot.pool.lastfm_sessions[ctx.author.id] = newdata

        embed.description = "### Sua conta do [last.fm](<https://www.last.fm/home>) foi conectada com sucesso!"

        await msg.edit(embed=embed, view=view, content=None)

    @commands.Cog.listener('on_wavelink_track_end')
    async def startscrooble(self, player: LavalinkPlayer, track: LavalinkTrack, reason: str = None):

        if reason != "FINISHED" or not track:
            return

        counter = 3

        while counter > 0:
            if not player.last_channel:
                await asyncio.sleep(2)
                continue
            break

        if not player.last_channel:
            return

        if track.is_stream or track.info["sourceName"] in ("local", "http"):
            return

        for user in player.last_channel.members:

            try:
                fminfo = self.bot.pool.lastfm_sessions[user.id]
            except KeyError:
                user_data = await self.bot.get_global_data(user.id, db_name=DBModel.users)
                fminfo = user_data["lastfm"]
                self.bot.pool.lastfm_sessions[user.id] = fminfo

            if fminfo["scrobble"] is False or not fminfo["sessionkey"]:
                continue

            try:
                player.lastfm_networks[user.id]
            except KeyError:
                player.lastfm_networks[user.id] = pylast.LastFMNetwork(
                    self.bot.pool.config["LASTFM_KEY"],
                    self.bot.pool.config["LASTFM_SECRET"],
                    session_key=fminfo["sessionkey"]
                )

        if track.info["sourceName"] in ("youtube", "soundcloud"):

            if track.ytid:
                if track.author.endswith(" - topic") and not track.author.endswith("Release - topic") and not track.title.startswith(track.author[:-8]):
                    name = track.title
                    artist = track.author[:-8]
                else:
                    try:
                        artist, name = track.title.split(" - ", maxsplit=1)
                    except ValueError:
                        name = track.title
                        artist = track.author
            else:
                name = track.single_title
                artist = track.author

            artist = artist.split(",")[0]

        else:
            artist = track.author.split(",")[0]
            name = track.single_title

        duration = int(track.duration / 1000)
        album = track.album_name

        for nw in player.lastfm_networks.values():

            try:
                await self.bot.loop.run_in_executor(
                    None, lambda: nw.scrobble(
                        artist=artist, title=name, timestamp=int(time.mktime(datetime.now().timetuple())),
                        album=album, duration=duration
                    )
                )
            except:
                traceback.print_exc()

def setup(bot):
    if not bot.pool.config["LASTFM_KEY"] or not bot.pool.config["LASTFM_SECRET"]:
        print("⚠️ - Recursos do Last.FM estarão desativados devido a falta de configuração do LASTFM_KEY e LASTFM_SECRET")
        return
    bot.add_cog(LastFmCog(bot))
