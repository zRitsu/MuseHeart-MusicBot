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

class MySessionKeyGenerator(pylast.SessionKeyGenerator):

    def get_web_auth_session_key(self, url, token: str = ""):
        session_key, _username = self.get_web_auth_session_key_username(url, token)
        return session_key, _username


class LastFMView(disnake.ui.View):

    def __init__(self, ctx, session_key: str):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.interaction: Optional[disnake.MessageInteraction] = None
        self.session_key = ""
        self.username = ""
        self.auth_url = None
        self.skg = None
        self.network = None
        self.clear_session = False
        self.check_loop = None
        self.error = None
        self.cooldown = commands.CooldownMapping.from_cooldown(1, 15, commands.BucketType.user)

        if session_key:
            btn = disnake.ui.Button(label="Revincular conta do last.fm")
            btn.callback = self.send_authurl_callback
            self.add_item(btn)

            btn2 = disnake.ui.Button(label="Desvincular conta do last.fm", style=disnake.ButtonStyle.red)
            btn2.callback = self.disconnect_account
            self.add_item(btn2)

        else:
            btn = disnake.ui.Button(label="Vincular conta do last.fm")
            btn.callback = self.send_authurl_callback
            self.add_item(btn)

    async def check_session_loop(self):

        count = 8

        while count > 0:
            try:
                await asyncio.sleep(15)
                self.session_key, self.username = await self.ctx.bot.loop.run_in_executor(None, lambda: self.skg.get_web_auth_session_key(self.auth_url))
                self.stop()
                return
            except pylast.WSError:
                count -= 1
                continue
            except Exception as e:
                self.error = e
                self.stop()
                return

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.send("Você não pode usar esse botão", ephemeral=True)
            return False
        return True

    async def disconnect_account(self, interaction: disnake.MessageInteraction):
        self.clear_session = True
        self.session_key = ""
        self.interaction = interaction
        self.stop()

    async def send_authurl_callback(self, interaction: disnake.MessageInteraction):

        if bucket := self.cooldown.get_bucket(interaction):  # type: ignore
            if retry_after := bucket.update_rate_limit():
                await interaction.send(f"você terá que aguardar {retry_after} segundo{'s'[:retry_after^1]} para gerar um novo link de acesso.", ephemeral=True)
                return

        if not self.skg:
            self.network = pylast.LastFMNetwork(self.ctx.bot.pool.config["LASTFM_KEY"], self.ctx.bot.pool.config["LASTFM_SECRET"])
            self.skg = MySessionKeyGenerator(self.network)

        self.check_loop = self.ctx.bot.loop.create_task(self.check_session_loop())
        self.auth_url = await self.ctx.bot.loop.run_in_executor(None, lambda: self.skg.get_web_auth_url())

        await interaction.send(f"### [Clique aqui](<{self.auth_url}>) para integrar sua conta do last.fm\n\n"
                               f"`Nota: O link expira em` <t:{int((disnake.utils.utcnow() + datetime.timedelta(minutes=2)).timestamp())}:R>"
                               "`. caso já tenha autorizado a aplicação você deve aguardar até 15 segundos para a mensagem acima atualizar.`",
                               ephemeral=True)

class LastFmCog(commands.Cog):

    emoji = "🎧"
    name = "LastFM"
    desc_prefix = f"[{emoji} {name}] | "

    def __init__(self, bot: BotCore):
        self.bot = bot

        if not hasattr(bot.pool, "lastfm_sessions"):
            bot.pool.lastfm_sessions = {}

    lastfm_cd = commands.CooldownMapping.from_cooldown(1, 13, commands.BucketType.member)
    lastfm_mc = commands.MaxConcurrency(1, per=commands.BucketType.user, wait=False)

    @commands.command(hidden=True, name="lastfm", aliases=["lastfmconnect", "lfm"],
                      description="Conectar sua conta do last.fm.",
                      cooldown=lastfm_cd, max_concurrency=lastfm_mc)
    async def lastfmconnect_legacy(self, ctx: CustomContext):
        await self.lastfmconnect.callback(self=self, inter=ctx)


    @commands.slash_command(hidden=True, name="lastfm",
                      description=f"{desc_prefix}Conectar sua conta do last.fm",
                      cooldown=lastfm_cd, max_concurrency=lastfm_mc)
    async def lastfmconnect(self, inter: disnake.AppCmdInter):

        cog = self.bot.get_cog("Music")

        if cog:
            await inter.response.defer(ephemeral=await cog.is_request_channel(inter, ignore_thread=True))
        else:
            await inter.response.defer(ephemeral=True)

        try:
            data = inter.global_user_data
        except AttributeError:
            data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            try:
                inter.global_user_data = data
            except:
                pass

        embed = disnake.Embed(
            description="**Vincule (ou crie) uma conta no [last.fm](<https://www.last.fm/home>) para registrar "
                        "todas as músicas que você ouvir por aqui no seu perfil do last.fm para obter sugestões de "
                        "músicas/artistas/álbuns e ter uma estatística geral das músicas que você ouviu alem de ter "
                        "acesso a uma comunidade incrível da plataforma.**",
            color=self.bot.get_color()
        ).set_thumbnail(url="https://www.last.fm/static/images/lastfm_avatar_twitter.52a5d69a85ac.png")

        if username:=data["lastfm"]["username"]:
            embed.add_field(name="\u200b", value=f"**Conta vinculada atual:** [**{username}**](<https://www.last.fm/user/{username}>)")

        current_session_key = data["lastfm"]["sessionkey"]

        view = LastFMView(inter, session_key=current_session_key)

        if isinstance(inter, CustomContext):
            msg = await inter.send(embed=embed, view=view)
            inter.store_message = msg
        else:
            msg = None
            await inter.edit_original_message(embed=embed, view=view)

        await view.wait()

        for c in view.children:
            c.disabled = True

        if not view.session_key and not view.clear_session:

            if view.error:
                raise view.error

            embed.set_footer(text="O tempo para linkar sua conta do last.fm expirou! Use o comando novamente caso queira repetir o processo.")

            if msg:
                await msg.edit(embed=embed, view=view)
            else:
                await inter.edit_original_message(embed=embed, view=view)

            return

        newdata = {"scrobble": True, "sessionkey": view.session_key, "username": view.username}
        data["lastfm"].update(newdata)
        await self.bot.update_global_data(inter.author.id, data=data, db_name=DBModel.users)

        self.bot.pool.lastfm_sessions[inter.author.id] = newdata

        if view.session_key:
            embed.clear_fields()
            embed.description += f"\n### A conta [{view.username}](<https://www.last.fm/user/{view.username}>) foi " + \
                                 "vinculada com sucesso!\n\n`Agora ao ouvir suas músicas no canal de voz elas serão registradas " \
                                "na sua conta do last.fm`"
        else:
            embed.description += "\n### Você desconectou sua conta do [last.fm](<https://www.last.fm/home>)."

        if view.interaction:
            await view.interaction.response.edit_message(embed=embed, view=view, content=None)
        elif msg:
            await msg.edit(embed=embed, view=view, content=None)
        else:
            await inter.edit_original_message(embed=embed, view=view, content=None)

    @commands.Cog.listener("on_voice_state_update")
    async def connect_vc_update(self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState):

        if member.bot or not after.channel or before.channel == after.channel:
            return

        try:
            player: LavalinkPlayer = self.bot.music.players[member.guild.id]
        except KeyError:
            return

        if player.last_channel != after.channel:
            return

        try:
            if not player.current or member not in player.last_channel.members:
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

        if not track:
            return

        if reason != "FINISHED" and not update_np:
            return

        counter = 3

        while counter > 0:
            if not player.guild.me.voice:
                await asyncio.sleep(2)
                continue
            break

        if not player.guild.me.voice:
            return

        if track.is_stream or track.info["sourceName"] in ("local", "http"):
            return

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

        for user in users or player.last_channel.members:

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
                network = player.lastfm_networks[user.id]
            except KeyError:
                network = MyNetWork(
                    self.bot.pool.config["LASTFM_KEY"],
                    self.bot.pool.config["LASTFM_SECRET"],
                    session_key=fminfo["sessionkey"]
                )
                network.disable_caching()
                player.lastfm_networks[user.id] = network

            if update_np:
                func = network.update_now_playing
                kw = {}
            else:
                func = network.scrobble
                kw = {"timestamp": int(disnake.utils.utcnow().timestamp())}

            try:
                await self.bot.loop.run_in_executor(
                    None, lambda: func(
                        artist=artist, title=name, album=album, duration=duration, **kw
                    )
                )
                network.last_timestamp = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)
            except pylast.WSError as e:
                if "Invalid session key" in e.details:
                    user_data = await self.bot.get_global_data(user.id, db_name=DBModel.users)
                    user_data["lastfm"]["sessionkey"] = ""
                    await self.bot.update_global_data(user.id, user_data, db_name=DBModel.users)
                    try:
                        del self.bot.pool.lastfm_sessions[user.id]
                    except KeyError:
                        pass
                    try:
                        del player.lastfm_networks[user.id]
                    except KeyError:
                        pass
                else:
                    traceback.print_exc()
            except Exception:
                traceback.print_exc()

def setup(bot):
    if not bot.pool.config["LASTFM_KEY"] or not bot.pool.config["LASTFM_SECRET"]:
        print("⚠️ - Recursos do Last.FM estarão desativados devido a falta de configuração do LASTFM_KEY e LASTFM_SECRET")
        return
    bot.add_cog(LastFmCog(bot))
