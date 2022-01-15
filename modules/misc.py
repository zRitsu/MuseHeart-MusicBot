import asyncio
import datetime
from typing import Optional
import disnake
from disnake.ext import commands
from utils.client import BotCore
import psutil
import humanize
from itertools import cycle
from random import shuffle
from os import getpid, environ
import platform


class Misc(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.source_owner: Optional[disnake.User] = None
        self.activities = None
        self.task = self.bot.loop.create_task(self.presences())

    def placeholders(self, text: str):

        if not text:
            return ""

        return text \
            .replace("{users}", str(len([m for m in self.bot.users if not m.bot]))) \
            .replace("{playing}", str(len(self.bot.music.players))) \
            .replace("{guilds}", str(len(self.bot.guilds))) \
            .replace("{uptime}", str(datetime.timedelta(seconds=(disnake.utils.utcnow() - self.bot.uptime)
                                                        .total_seconds())).split('.')[0])


    async def presences(self):

        if not self.activities:

            activities = []

            for i in environ.get("LISTENING_PRESENCES", "").split("||"):
                activities.append({"name":i, "type": "listening"})

            for i in environ.get("WATCHING_PRESENCES", "").split("||"):
                activities.append({"name": i, "type": "watching"})

            for i in environ.get("PLAYING_PRESENCES", "").split("||"):
                activities.append({"name": i, "type": "playing"})

            shuffle(activities)

            self.activities = cycle(activities)

        while True:

            await self.bot.wait_until_ready()

            activity_data = next(self.activities)

            if activity_data["type"] == "listening":
                activity = disnake.Activity(type=disnake.ActivityType.listening, name=self.placeholders(activity_data["name"]))

            elif activity_data["type"] == "watching":
                activity = disnake.Activity(type=disnake.ActivityType.watching, name=self.placeholders(activity_data["name"]))

            else:
                activity = disnake.Game(name=self.placeholders(activity_data["name"]))

            await self.bot.change_presence(activity=activity)

            await asyncio.sleep(300)


    @commands.slash_command(description="Exibir informações sobre mim.")
    async def about(self, inter: disnake.ApplicationCommandInteraction):

        if not self.source_owner:
            self.source_owner = await self.bot.get_or_fetch_user(815907450090946571)

        ram_usage = humanize.naturalsize(psutil.Process(getpid()).memory_info().rss)

        embed = disnake.Embed(
            description=f"**Sobre mim:**\n\n"
                        f"> **Estou em:** `{len(self.bot.guilds)} servidor(es)`\n"
                        f"> **Players ativos:** `{len(self.bot.music.players)}`\n"
                        f"> **Tipo de player usado:** `Lavalink`\n"
                        f"> **Commit atual:** [`{self.bot.commit}`]({self.bot.remote_git_url}/commit/{self.bot.commit})\n"
                        f"> **Versão do Disnake:** `{disnake.__version__}`\n"
                        f"> **Versão do python:** `{platform.python_version()}`\n"
                        f"> **Latencia:** `{round(self.bot.latency * 1000)}ms`\n"
                        f"> **Uso de RAM:** `{ram_usage}`\n"
                        f"> **Uptime:** `{str((datetime.timedelta(seconds=(disnake.utils.utcnow() - self.bot.uptime).total_seconds()))).split('.')[0]}`\n",
            color=self.bot.get_color(inter.guild.me)
        )

        try:
            embed.set_thumbnail(url=self.bot.user.avatar.with_static_format("png").url)
        except AttributeError:
            pass

        if self.bot.default_prefix:
            embed.description += f"> **Prefixo:** {self.bot.default_prefix}\n"

        links = "[`[Source]`](https://github.com/zRitsu/disnake-LL-music-bot)"

        if (await self.bot.application_info()).bot_public:
            links = f"[`[Invite]`](https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=" \
                    f"8&scope=bot%20applications.commands) **|** {links}"

        embed.description += f">  {links}\n"

        try:
            avatar = self.bot.owner.avatar.with_static_format("png").url
        except AttributeError:
            avatar = self.bot.owner.default_avatar.with_static_format("png").url

        embed.set_footer(
            icon_url=avatar,
            text=f"Dono(a): {self.bot.owner}"
        )

        # resolvi add essa opção...
        # mas caso use, por favor considere de alguma forma fornecer crédito :(
        if self.bot.config.get("HIDE_SOURCE_OWNER") != "false" and self.bot.owner.id == self.source_owner.id:
            embed.footer.text += f" | Source by: {self.source_owner}"

        await inter.send(embed=embed)


    @commands.slash_command(description="Exibir meu link de convite para você me adicionar no seu servidor.")
    async def invite(self, inter: disnake.ApplicationCommandInteraction):

        await inter.send(
            embed = disnake.Embed(
                colour=self.bot.get_color(inter.guild.me),
                description=f"[**Clique aqui**](https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=0&scope=bot%20applications.commands) "
                            f"para me adicionar no seu servidor."
            ),
            ephemeral=True
        )

    @commands.user_command(name="avatar")
    async def avatar(self, inter: disnake.UserCommandInteraction):

        embeds = []

        assets = {}

        user = await self.bot.fetch_user(inter.target.id) if not inter.target.bot else self.bot.get_user(
            inter.target.id)

        if inter.target.guild_avatar:
            assets["Avatar (Server)"] = inter.target.guild_avatar.with_static_format("png")
        assets["Avatar (User)"] = user.avatar.with_static_format("png")
        if user.banner:
            assets["Banner"] = user.banner.with_static_format("png")

        for name, asset in assets.items():
            embed = disnake.Embed(description=f"{inter.target.mention} **[{name}]({asset.with_size(2048).url})**",
                                  color=self.bot.get_color(inter.guild.me))
            embed.set_image(asset.with_size(256).url)
            embeds.append(embed)

        await inter.send(embeds=embeds, ephemeral=True)

    def cog_unload(self):

        try:
            self.task.cancel()
        except:
            pass


def setup(bot: BotCore):
    bot.add_cog(Misc(bot))
