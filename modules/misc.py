import disnake
from disnake.ext import commands
import asyncio
from typing import Optional
from aiohttp import ClientSession
from utils.client import BotCore
from utils.db import DBModel
from utils.music.checks import check_requester_channel
from utils.music.converters import time_format, URL_REG
import psutil
import humanize
from itertools import cycle
from random import shuffle
from os import getpid
import platform


class Misc(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.source_owner: Optional[disnake.User] = None
        self.activities = None
        self.task = self.bot.loop.create_task(self.presences())
        self.extra_user_bots = []
        self.extra_user_bots_ids = [int(i) for i in bot.config['ADDITIONAL_BOT_IDS'].split() if i.isdigit()]

    desc_prefix = "🔰 [Outros] 🔰 | "


    def placeholders(self, text: str):

        if not text:
            return ""

        return text \
            .replace("{users}", str(len([m for m in self.bot.users if not m.bot]))) \
            .replace("{playing}", str(len(self.bot.music.players))) \
            .replace("{guilds}", str(len(self.bot.guilds))) \
            .replace("{uptime}", time_format((disnake.utils.utcnow() - self.bot.uptime).total_seconds() * 1000,
                                             use_names=True))


    async def presences(self):

        if not self.activities:

            activities = []

            for i in self.bot.config.get("LISTENING_PRESENCES", "").split("||"):
                if i:
                    activities.append({"name":i, "type": "listening"})

            for i in self.bot.config.get("WATCHING_PRESENCES", "").split("||"):
                if i:
                    activities.append({"name": i, "type": "watching"})

            for i in self.bot.config.get("PLAYING_PRESENCES", "").split("||"):
                if i:
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

            await asyncio.sleep(self.bot.config["PRESENCE_INTERVAL"])


    @commands.Cog.listener("on_guild_join")
    async def guild_add(self, guild: disnake.Guild):

        if not guild.system_channel or not guild.system_channel.permissions_for(guild.me).send_messages:
            return

        prefix = (await self.bot.get_data(guild.id, db_name=DBModel.guilds))["prefix"] or self.bot.default_prefix

        embed = disnake.Embed(
            description="Olá! Para ver todos os meus comandos use **/**\n\n",
            color=self.bot.get_color(guild.me)
        )

        if cmd:=self.bot.get_slash_command("setup"):
            embed.description += f"Caso queira, use o comando **/{cmd.name}** para criar um canal dedicado para pedir " \
                                 "músicas sem comandos e deixar o music player fixo no canal.\n\n"

        embed.description += f"Caso os comandos de barra (/) não apareçam, use o comando:\n{prefix}syncguild"

        await guild.system_channel.send(embed=embed)


    @commands.command(name="about", aliases=["sobre", "info", "botinfo"], description="Exibir informações sobre mim.")
    async def about_legacy(self, ctx):
        await self.about.callback(self=self, inter=ctx)


    @commands.slash_command(description=f"{desc_prefix}Exibir informações sobre mim.")
    async def about(
            self,
            inter: disnake.AppCmdInter,
            hidden: bool = commands.Param(name="modo_oculto", description="Não exibir a mensagem do comando", default=False)
    ):

        if not self.source_owner:
            self.source_owner = await self.bot.get_or_fetch_user(184889853102653440)

        ram_usage = humanize.naturalsize(psutil.Process(getpid()).memory_info().rss)

        embed = disnake.Embed(
            description=f"**Sobre mim:**\n\n"
                        f"> **Estou em:** `{len(self.bot.guilds)} servidor(es)`\n",
            color=self.bot.get_color(inter.guild.me)
        )

        if self.bot.music.players:
            embed.description += f"> **Players ativos (bot atual):** `{len(self.bot.music.players)}`\n"

        active_players_other_bots = 0

        for bot in self.bot.pool.bots:
            if bot.user.id == self.bot.user.id:
                continue
            for player in bot.music.players:
                active_players_other_bots += 1

        if active_players_other_bots:
            embed.description += f"> **Players ativos (outros bots):** `{active_players_other_bots}`\n"

        if self.bot.pool.commit:
            embed.description += f"> **Commit atual:** [`{self.bot.pool.commit[:7]}`]({self.bot.pool.remote_git_url}/commit/{self.bot.pool.commit})\n"

        embed.description += f"> **Versão do Python:** `{platform.python_version()}`\n"\
                             f"> **Versão do Disnake:** `{disnake.__version__}`\n" \
                             f"> **Latencia:** `{round(self.bot.latency * 1000)}ms`\n" \
                             f"> **Uso de RAM:** `{ram_usage}`\n" \
                             f"> **Uptime:** `{time_format((disnake.utils.utcnow() - self.bot.uptime).total_seconds()*1000)}`\n"

        try:
            embed.set_thumbnail(url=self.bot.user.avatar.with_static_format("png").url)
        except AttributeError:
            pass

        guild_data = await self.bot.get_data(inter.guild.id, db_name=DBModel.guilds)

        prefix = guild_data["prefix"] or self.bot.default_prefix

        if self.bot.default_prefix and not self.bot.config["INTERACTION_COMMAND_ONLY"]:
            embed.description += f"> **Prefixo:** `{disnake.utils.escape_markdown(prefix, as_needed=True)}`\n"

        links = "[`[Source]`](https://github.com/zRitsu/disnake-LL-music-bot)"

        if (await self.bot.application_info()).bot_public:
            links = f"[`[Invite]`]({disnake.utils.oauth_url(self.bot.user.id, permissions=disnake.Permissions(self.bot.config['INVITE_PERMISSIONS']), scopes=('bot', 'applications.commands'))}) **|** {links}"

        if self.bot.config["SUPPORT_SERVER"]:
            links += f" **|** [`[Suporte]`]({self.bot.config['SUPPORT_SERVER']})"

        embed.description += f">  {links}\n"

        try:
            avatar = self.bot.owner.avatar.with_static_format("png").url
        except AttributeError:
            avatar = self.bot.owner.default_avatar.with_static_format("png").url

        embed.set_footer(
            icon_url=avatar,
            text=f"Dono(a): {self.bot.owner}"
        )

        if self.bot.config["HIDE_SOURCE_OWNER"] is not False and self.bot.owner.id == self.source_owner.id:
            embed.footer.text += f" | Source by: {self.source_owner}"

        await inter.send(embed=embed, ephemeral=hidden)


    @commands.command(name="invite", aliases=["convidar"], description="Exibir meu link de convite para você me adicionar no seu servidor.")
    async def invite_legacy(self, ctx):
        await self.invite.callback(self=self, inter=ctx)


    @commands.slash_command(description=f"{desc_prefix}Exibir meu link de convite para você me adicionar no seu servidor.")
    async def invite(self, inter: disnake.AppCmdInter):

        await inter.response.defer(ephemeral=True)

        if self.extra_user_bots_ids is not None:

            for bot_id in self.extra_user_bots_ids:

                if bot_id ==self.bot.user.id:
                    continue

                bot = await self.bot.get_or_fetch_user(bot_id)

                if bot:
                    self.extra_user_bots.append(bot)

            self.extra_user_bots_ids = None

        embed = disnake.Embed(
                colour=self.bot.get_color(inter.guild.me),
                description=f"[**Clique aqui**]({disnake.utils.oauth_url(self.bot.user.id, permissions=disnake.Permissions(self.bot.config['INVITE_PERMISSIONS']), scopes=('bot', 'applications.commands'))}) "
                            "para me adicionar no seu servidor."
            )

        if self.extra_user_bots:
            embed.description += "\n\n**Caso queira bots de música adicionais, você pode adicionar um dos bots abaixo:**\n\n" + \
                                 "\n".join(f"`{bot}:` [`adicionar`]({disnake.utils.oauth_url(bot.id, permissions=disnake.Permissions(self.bot.config['INVITE_PERMISSIONS']), scopes=('bot', 'applications.commands'))})" for bot in self.extra_user_bots)

        try:
            await inter.edit_original_message(embed=embed)
        except AttributeError:
            await inter.send(embed=embed, ephemeral=True)


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


    async def cog_check(self, ctx):
        return await check_requester_channel(ctx)


    def cog_unload(self):

        try:
            self.task.cancel()
        except:
            pass


class GuildLog(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.hook_url: str = ""

        if bot.config["BOT_ADD_REMOVE_LOG"]:

            if URL_REG.match(bot.config["BOT_ADD_REMOVE_LOG"]):
                self.hook_url = bot.config["BOT_ADD_REMOVE_LOG"]
            else:
                print("URL do webhook inválido (para envio de logs ao adicionar/remover bot).")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: disnake.Guild):

        print(f"Removido do servidor: {guild.name} - [{guild.id}]")

        try:
            await self.bot.music.players[guild.id].destroy()
        except:
            pass

        if not self.hook_url:
            return

        embed = disnake.Embed(
            description=f"**Me removeram do servidor:**\n"
                        f"```{guild.name}```\n"
                        f"**ID:** `{guild.id}`",
            color=disnake.Colour.red()
        )

        try:
            embed.set_thumbnail(url=guild.icon.replace(static_format="png").url)
        except AttributeError:
            pass

        await self.send_hook(self.bot.owner.mention, embed=embed)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: disnake.Guild):

        print(f"Novo servidor: {guild.name} - [{guild.id}]")

        if not self.hook_url:
            return

        created_at = int(guild.created_at.timestamp())

        embed =disnake.Embed(
            description="__**Me adicionaram em um novo servidor:**__\n"
                        f"```{guild.name}```\n"
                        f"**ID:** `{guild.id}`\n"
		                f"**Dono:** `{guild.owner}`\n"
                        f"**Criado em:** <t:{created_at}:f> - <t:{created_at}:R>\n"
		                f"**Nível de verificação:** `{guild.verification_level or 'nenhuma'}`\n"
		                f"**Membros:** `{len([m for m in guild.members if not m.bot])}`\n"
		                f"**Bots:** `{len([m for m in guild.members if m.bot])}`\n",
            color=disnake.Colour.green()
        )

        try:
            embed.set_thumbnail(url=guild.icon.replace(static_format="png").url)
        except AttributeError:
            pass

        await self.send_hook(self.bot.owner.mention, embed=embed)


    async def send_hook(self, content="", *, embed: disnake.Embed=None):

        async with ClientSession() as session:
            webhook = disnake.Webhook.from_url(self.hook_url, session=session)
            await webhook.send(
                content=content,
                username=self.bot.user.name,
                avatar_url=self.bot.user.avatar.replace(static_format='png').url,
                embed=embed
            )


def setup(bot: BotCore):
    bot.add_cog(Misc(bot))
    bot.add_cog(GuildLog(bot))
