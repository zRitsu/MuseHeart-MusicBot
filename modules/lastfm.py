from __future__ import annotations

import asyncio
import datetime
import traceback
from typing import TYPE_CHECKING, Optional

import disnake
import pylast
from disnake.ext import commands

from utils.db import DBModel
from utils.music.models import LavalinkPlayer, LavalinkTrack
from utils.others import CustomContext

if TYPE_CHECKING:
    from utils.client import BotCore


class MyNetWork(pylast.LastFMNetwork):
    last_url: str = ""
    last_duration: int = 0
    last_timestamp: Optional[datetime.datetime] = None


class LastFMView(disnake.ui.View):

    def __init__(self, ctx, url):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.url = url

        btn = disnake.ui.Button(label="Integrar sua conta do last.fm")
        btn.callback = self.ephemeral_callback
        self.add_item(btn)


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

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(hidden=True, name="lastfm", aliases=["scb", "scrobbler", "lfm"])
    async def scrobbler_legacy(self, ctx: CustomContext):

        network = pylast.LastFMNetwork(self.bot.pool.config["LASTFM_KEY"], self.bot.pool.config["LASTFM_SECRET"])

        skg = pylast.SessionKeyGenerator(network)

        url = await self.bot.loop.run_in_executor(None, lambda: skg.get_web_auth_url())

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

        count = 4

        error = None

        session_key = None

        while count > 0:
            try:
                await asyncio.sleep(15)
                session_key = await self.bot.loop.run_in_executor(None, lambda: skg.get_web_auth_session_key(url))
                break
            except pylast.WSError:
                count -= 1
                continue
            except Exception as e:
                error = e
                break

        view.stop()

        for c in view.children:
            c.disabled = True

        if not session_key:

            if error:
                raise error

            await msg.edit(embed=disnake.Embed(
                description="\n### O tempo para linkar sua conta do last.fm expirou!\n\n"
                            "Use o comando novamente caso queira repetir o processo.",
                color=self.bot.get_color(ctx.guild.me)), view=view)

            return

        try:
            data = ctx.global_user_data
        except AttributeError:
            data = await self.bot.get_global_data(ctx.author.id, db_name=DBModel.users)
            ctx.global_user_data = data

        newdata = {"scrobble": True, "sessionkey": session_key}
        data["lastfm"].update(newdata)
        await self.bot.update_global_data(ctx.author.id, data=data, db_name=DBModel.users)

        self.bot.pool.lastfm_sessions[ctx.author.id] = newdata

        embed.description += "\n### Sua conta do [last.fm](<https://www.last.fm/home>) foi conectada com sucesso!"

        await msg.edit(embed=embed, view=view, content=None)

    @commands.Cog.listener("on_voice_state_update")
    async def connect_vc_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):

        if member.bot or not after.channel or before.channel == after.channel:
            return

        try:
            player: LavalinkPlayer = self.bot.music.players[member.guild.id]
        except KeyError:
            return

        try:
            if not player.current or not member.id not in player.last_channel.voice_states:
                return
        except AttributeError:
            return

        try:
            nw: MyNetWork = player.lastfm_networks[member.id]
        except KeyError:
            pass
        else:
            if nw.last_url == player.current.uri and nw.last_timestamp and datetime.datetime.utcnow() < nw.last_timestamp:
                return

        await self.startscrooble(player=player, track=player.last_track, users=[member])

    @commands.Cog.listener('on_wavelink_track_start')
    async def update_np(self, player: LavalinkPlayer):
        await self.startscrooble(player, track=player.last_track, update_np=True)

    @commands.Cog.listener('on_wavelink_track_end')
    async def startscrooble(self, player: LavalinkPlayer, track: LavalinkTrack, reason: str = None, update_np=False, users=None):

        if not track or reason != "FINISHED":
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

        if not users:
            users = player.last_channel.members

        for user in users:

            if user.bot:
                continue

            try:
                if user.voice.self_deaf or user.voice.deaf:
                    continue
            except AttributeError:
                continue

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
                player.lastfm_networks[user.id] = MyNetWork(
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

            if update_np:
                func = nw.update_now_playing
                kw = {}
            else:
                func = nw.scrobble
                kw = {"timestamp": int(disnake.utils.utcnow().timestamp())}

            try:
                await self.bot.loop.run_in_executor(
                    None, lambda: func(
                        artist=artist, title=name, album=album, duration=duration, **kw
                    )
                )
                nw.last_timestamp = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)
            except:
                traceback.print_exc()

def setup(bot):
    if not bot.pool.config["LASTFM_KEY"] or not bot.pool.config["LASTFM_SECRET"]:
        print("⚠️ - Recursos do Last.FM estarão desativados devido a falta de configuração do LASTFM_KEY e LASTFM_SECRET")
        return
    bot.add_cog(LastFmCog(bot))
