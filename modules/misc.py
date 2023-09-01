# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime
import json
import os.path
import traceback
from itertools import cycle
from random import shuffle
from os import getpid
import platform
import asyncio
from typing import TYPE_CHECKING

import aiofiles
import disnake
import psutil
import humanize
from disnake.ext import commands
from aiohttp import ClientSession

from utils.db import DBModel, db_models
from utils.music.checks import check_requester_channel
from utils.music.converters import time_format, URL_REG
from utils.others import select_bot_pool, CustomContext, paginator

if TYPE_CHECKING:
    from utils.client import BotCore


def remove_blank_spaces(d):

    for k, v in list(d.items()):

        new_k = k.strip()
        if new_k != k:
            d[new_k] = d.pop(k)

        if isinstance(v, str):
            new_v = v.strip()
            if new_v != v:
                d[new_k] = new_v
        elif isinstance(v, dict):
            remove_blank_spaces(v)


class Misc(commands.Cog):

    emoji = "🔰"
    name = "Diversos"
    desc_prefix = f"[{emoji} {name}] | "

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.activities = None
        self.task = self.bot.loop.create_task(self.presences())
        self.extra_user_bots = []
        self.extra_user_bots_ids = [int(i) for i in bot.config['ADDITIONAL_BOT_IDS'].split() if i.isdigit()]

    def placeholders(self, text: str):

        if not text:
            return ""

        return text \
            .replace("{users}", f'{len([m for m in self.bot.users if not m.bot]):,}'.replace(",", ".")) \
            .replace("{playing}", f'{len(self.bot.music.players):,}'.replace(",", ".")) \
            .replace("{guilds}", f'{len(self.bot.guilds):,}'.replace(",", ".")) \
            .replace("{uptime}", time_format((disnake.utils.utcnow() - self.bot.uptime).total_seconds() * 1000,
                                             use_names=True))


    async def presences(self):

        if not self.activities:

            activities = []

            for i in self.bot.config["LISTENING_PRESENCES"].split("||"):
                if i:
                    activities.append({"name":i, "type": "listening"})

            for i in self.bot.config["WATCHING_PRESENCES"].split("||"):
                if i:
                    activities.append({"name": i, "type": "watching"})

            for i in self.bot.config["PLAYING_PRESENCES"].split("||"):
                if i:
                    activities.append({"name": i, "type": "playing"})

            for i in self.bot.config["CUSTOM_STATUS_PRESENCES"].split("||"):
                if i:
                    activities.append({"name": i, "type": "custom_status"})

            for i in self.bot.config["STREAMING_PRESENCES"].split("|||"):
                if i:
                    try:
                        name, url = i.split("||")
                        activities.append({"name": name, "url": url.strip(" "), "type": "streaming"})
                    except Exception:
                        traceback.print_exc()

            shuffle(activities)

            self.activities = cycle(activities)

        while True:

            await self.bot.wait_until_ready()

            activity_data = next(self.activities)

            if activity_data["type"] == "listening":
                activity = disnake.Activity(
                    type=disnake.ActivityType.listening,
                    name=self.placeholders(activity_data["name"])
                )

            elif activity_data["type"] == "watching":
                activity = disnake.Activity(
                    type=disnake.ActivityType.watching,
                    name=self.placeholders(activity_data["name"])
                )

            elif activity_data["type"] == "streaming":
                activity = disnake.Activity(
                    type=disnake.ActivityType.streaming,
                    name=self.placeholders(activity_data["name"]),
                    url=activity_data["url"]
                )

            elif activity_data["type"] == "listening":
                activity = disnake.Game(name=self.placeholders(activity_data["name"]))

            else:
                activity = disnake.Activity(
                    name="customstatus",
                    type=disnake.ActivityType.custom,
                    state=self.placeholders(activity_data["name"]),
                )

            await self.bot.change_presence(activity=activity)

            await asyncio.sleep(self.bot.config["PRESENCE_INTERVAL"])


    @commands.Cog.listener("on_guild_join")
    async def guild_add(self, guild: disnake.Guild):

        if str(self.bot.user.id) in self.bot.config["INTERACTION_BOTS_CONTROLLER"]:
            await guild.leave()
            return

        interaction_invite = ""

        bots_in_guild = []

        for bot in self.bot.pool.bots:

            if bot == self.bot:
                continue

            if bot.user in guild.members:
                bots_in_guild.append(bot)

        components = [disnake.ui.Button(custom_id="bot_invite", label="Precisa de mais bots de música? Clique aqui.")] if [b for b in self.bot.pool.bots if b.appinfo and b.appinfo.bot_public] else []

        if self.bot.pool.controller_bot != self.bot:
            interaction_invite = f"[`{disnake.utils.escape_markdown(str(self.bot.user.name))}`]({disnake.utils.oauth_url(self.bot.user.id, scopes=['applications.commands'])})"

        if cmd:=self.bot.get_command("setup"):
            cmd_text = f"Se desejar, use o comando **/{cmd.name}** para criar um canal dedicado pra pedir " \
                        "músicas sem comandos e deixar o music player fixo em um canal dedicado.\n\n"
        else:
            cmd_text = ""

        if self.bot.config["SUPPORT_SERVER"]:
            support_server = f"Caso tenha alguma dúvida ou queira acompanhar as últimas novidades, você pode entrar no meu [`servidor de suporte`]({self.bot.config['SUPPORT_SERVER']})"
        else:
            support_server = ""

        if self.bot.default_prefix and not self.bot.config["INTERACTION_COMMAND_ONLY"]:
            guild_data = await self.bot.get_global_data(guild.id, db_name=DBModel.guilds)
            prefix = disnake.utils.escape_markdown(guild_data['prefix'], as_needed=True)
        else:
            prefix = ""

        image = "https://cdn.discordapp.com/attachments/554468640942981147/1082887587770937455/rainbow_bar2.gif"

        color = self.bot.get_color()

        try:
            channel = guild.system_channel if guild.system_channel.permissions_for(guild.me).send_messages else None
        except AttributeError:
            channel = None

        if not channel:

            if guild.me.guild_permissions.view_audit_log:

                async for entry in guild.audit_logs(action=disnake.AuditLogAction.integration_create, limit=50):

                    if entry.target.application_id == self.bot.user.id:

                        embeds = []

                        embeds.append(
                            disnake.Embed(
                                color=color,
                                description=f"Olá! Agradeço muito por ter me adicionado no servidor: **{guild.name}** :)"
                            ).set_image(url=image)
                        )

                        if interaction_invite:
                            embeds.append(
                                disnake.Embed(
                                    color=color,
                                    description=f"**Observação importante:** Meus comandos de barra funcionam através "
                                                f"da seguinte aplicação: {interaction_invite}\n\n"
                                                f"Caso os comandos da aplicação acima não sejam exibidos ao digitar "
                                                f"barra (**/**) em um canal do servidor **{guild.name}** você terá que "
                                                f"clicar no nome acima para integrar os comandos de barra no servidor "
                                                f"**{guild.name}**.\n`Nota: Caso os comandos ainda não apareçam após "
                                                f"integrar os comandos, talvez seu servidor tenha atingido o limite de "
                                                f"bots com comandos de barra registrados.`"
                                ).set_image(url=image)
                            )
                        else:
                            embeds.append(
                                disnake.Embed(
                                    color=color,
                                    description=f"Para ver todos os meus comandos use barra (**/**) no servidor " \
                                                 f"**{guild.name}**"
                                ).set_image(url=image)
                            )

                        if prefix:
                            prefix_msg = f"Meu prefixo no servidor **{guild.name}** é: **{prefix}**"
                        else:
                            prefix = self.bot.default_prefix
                            prefix_msg = f"Meu prefixo padrão é **{prefix}**"

                        embeds.append(
                            disnake.Embed(
                                color=color,
                                description=f"Também tenho comandos de texto por prefixo. {prefix_msg} (minha menção "
                                            f"também funciona como prefixo). Pra ver todos os meus comandos de texto "
                                            f"use **{prefix}help** em um canal do servidor **{guild.name}**. "
                                            f"Caso queira alterar meu prefixo use o comando **{prefix}setprefix** "
                                            f"(você pode ter um prefixo pessoal usando o comando "
                                            f"**{prefix}setmyprefix**)."
                            ).set_image(url=image)
                        )

                        if bots_in_guild:
                            embeds.append(
                                disnake.Embed(
                                    color=color,
                                    description=f"Notei que há outros bots no servidor **{guild.name}** no qual sou compatível com " \
                                                 f"o sistema de multi-voice: {', '.join(b.user.mention for b in bots_in_guild)}\n\n"
                                                f"Ao usar usar os comandos de música (ex: play) sem um dos bots "
                                                f"conectado no canal, será usado um dos bots que estiver livre no "
                                                f"servidor."
                                ).set_image(url=image)
                            )

                        if support_server:
                            embeds.append(disnake.Embed(color=color, description=support_server).set_image(url=image))

                        try:
                            return await entry.user.send(embeds=embeds, components=components)
                        except disnake.Forbidden:
                            pass
                        except Exception:
                            traceback.print_exc()
                        break

        if not channel:

            for c in (guild.public_updates_channel, guild.rules_channel):

                if c and c.permissions_for(guild.me).send_messages:
                    channel = c
                    break

            if not channel:
                return

        embeds = []

        if interaction_invite:

            embeds.append(
                disnake.Embed(
                    color=color,
                    description=f"Olá! Para ver todos os meus comandos digite barra (**/**) e confira "
                                f"os comandos da seguinte aplicação: {interaction_invite}\n\n"
                                f"Caso os comandos da aplicação acima não sejam exibidos ao digitar barra (**/**) você "
                                f"terá que clicar no nome acima para integrar os comandos de barra no seu servidor.\n"
                                f"`Nota: Caso os comandos ainda não apareçam após integrar os comandos, talvez seu "
                                f"servidor tenha atingido o limite de bots com comandos de barra registrados.`"

                ).set_image(url=image)
            )

        else:
            embeds.append(
                disnake.Embed(
                    color=color, description="Olá! Para ver todos os meus comandos use barra (**/**)"
                ).set_image(url=image)
            )

        if prefix:
            prefix_msg = f"Meu prefixo no servidor é: **{prefix}**"
        else:
            prefix = self.bot.default_prefix
            prefix_msg = f"Meu prefixo padrão é **{prefix}**"

        embeds.append(
            disnake.Embed(
                color=color,
                description=f"Também tenho comandos de texto por prefixo. {prefix_msg} (minha menção "
                            f"também funciona como prefixo). Pra ver todos os meus comandos de texto use "
                            f"**{prefix}help**. Caso queira alterar meu prefixo use o comando **{prefix}setprefix** "
                            f"(você pode ter um prefixo pessoal usando o comando **{prefix}setmyprefix**)."
            ).set_image(url=image)
        )

        if bots_in_guild:
            embeds.append(
                disnake.Embed(
                    color=color,
                    description=f"Notei que há outros bots no servidor **{guild.name}** no qual sou compatível com " \
                                f"o sistema de multi-voice: {', '.join(b.user.mention for b in bots_in_guild)}\n\n"
                                f"Ao usar usar os comandos de música (ex: play) sem um dos bots "
                                f"conectado no canal, será usado um dos bots que estiver livre no "
                                f"servidor."
                ).set_image(url=image)
            )

        embeds.append(disnake.Embed(color=color, description=cmd_text).set_image(url=image))

        if support_server:
            embeds.append(disnake.Embed(color=color, description=support_server).set_image(url=image))

        kwargs = {"delete_after": 60} if channel == guild.rules_channel else {"delete_after": 300}

        timestamp = int((disnake.utils.utcnow() + datetime.timedelta(seconds=kwargs["delete_after"])).timestamp())

        embeds[-1].description += f"\n\nEssa mensagem será deletada automaticamente: <t:{timestamp}:R>"

        try:
            await channel.send(embeds=embeds, components=components, **kwargs)
        except:
            print(f"Falha ao enviar mensagem de novo servidor no canal: {channel}\n"
                  f"ID do canal: {channel.id}\n"
                  f"Tipo de canal: {type(channel)}\n"
                  f"{traceback.format_exc()}")

        await self.bot.update_appinfo()


    about_cd = commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.member)

    @commands.command(name="about", aliases=["sobre", "info", "botinfo"], description="Exibir informações sobre mim.",
                      cooldown=about_cd)
    async def about_legacy(self, ctx: CustomContext):
        await self.about.callback(self=self, inter=ctx)


    @commands.slash_command(
        description=f"{desc_prefix}Exibir informações sobre mim.", cooldown=about_cd
    )
    async def about(
            self,
            inter: disnake.AppCmdInter
    ):

        await inter.response.defer(ephemeral=True)

        inter, bot = await select_bot_pool(inter, first=True)

        if not bot:
            return

        ram_usage = humanize.naturalsize(psutil.Process(getpid()).memory_info().rss)

        guild = bot.get_guild(inter.guild_id) or inter.guild

        embed = disnake.Embed(
            description=f"**Sobre mim:**\n\n",
            color=bot.get_color(inter.guild.me if inter.guild else guild.me)
        )

        active_players_other_bots = 0
        inactive_players_other_bots = 0
        paused_players_other_bots = 0

        all_guilds_ids = set()

        for b in bot.pool.bots:

            try:
                if str(b.user.id) in self.bot.config["INTERACTION_BOTS_CONTROLLER"]:
                    continue
            except:
                pass

            for g in b.guilds:
                all_guilds_ids.add(g.id)

        guilds_size = len(all_guilds_ids)

        embed.description += f"> **Servidores" + (" (todos os bots)" if guilds_size > 1 else "") + \
                             f":** `{guilds_size}`\n"

        public_bot_count = 0
        private_bot_count = 0

        for b in bot.pool.bots:

            try:
                if str(b.user.id) in self.bot.config["INTERACTION_BOTS_CONTROLLER"]:
                    continue
            except:
                pass

            for p in b.music.players.values():

                if p.auto_pause:
                    inactive_players_other_bots += 1

                elif p.paused:
                    try:
                        if any(m for m in p.guild.me.voice.channel.members if not m.bot):
                            paused_players_other_bots += 1
                            continue
                    except AttributeError:
                        pass
                    inactive_players_other_bots += 1

                else:
                    active_players_other_bots += 1

            if not b.appinfo or not b.appinfo.bot_public:
                private_bot_count += 1
            else:
                public_bot_count += 1

        if public_bot_count:
            embed.description += f"> **Bot(s) público(s):** `{public_bot_count}`\n"

        if private_bot_count:
            embed.description += f"> **Bot(s) privado(s):** `{private_bot_count}`\n"

        if active_players_other_bots:
            embed.description += f"> **Players ativos" + (" (todos os bots)" if len(bot.pool.bots) > 1 else "") + \
                                 f":** `{active_players_other_bots}`\n"

        if paused_players_other_bots:
            embed.description += f"> **Players em pausa" + (" (todos os bots)" if len(bot.pool.bots) > 1 else "") + \
                                 f":** `{paused_players_other_bots}`\n"

        if inactive_players_other_bots:
            embed.description += f"> **Players inativos" + (" (todos os bots)" if len(bot.pool.bots) > 1 else "") + \
                                 f":** `{inactive_players_other_bots}`\n"

        if bot.pool.commit:
            embed.description += f"> **Commit atual:** [`{bot.pool.commit[:7]}`]({bot.pool.remote_git_url}/commit/{bot.pool.commit})\n"

        embed.description += f"> **Versão do Python:** `{platform.python_version()}`\n" \
                             f"> **Versão do Disnake:** `{disnake.__version__}`\n" \
                             f"> **Latencia:** `{round(bot.latency * 1000)}ms`\n" \
                             f"> **Uso de RAM:** `{ram_usage}`\n" \
                             f"> **Uptime:** <t:{int(bot.uptime.timestamp())}:R>\n"

        if not bot.config["INTERACTION_COMMAND_ONLY"]:

            try:
                guild_data = inter.global_guild_data
            except AttributeError:
                guild_data = await bot.get_global_data(inter.guild_id, db_name=DBModel.guilds)
                inter.global_guild_data = guild_data

            if guild_data["prefix"]:
                embed.description += f"> **Prefixo do servidor:** `{disnake.utils.escape_markdown(guild_data['prefix'], as_needed=True)}`\n"
            else:
                embed.description += f"> **Prefixo padrão:** `{disnake.utils.escape_markdown(bot.default_prefix, as_needed=True)}`\n"

            try:
                user_data = inter.global_user_data
            except AttributeError:
                user_data = await bot.get_global_data(inter.author.id, db_name=DBModel.users)
                inter.global_user_data = user_data

            if user_data["custom_prefix"]:
                embed.description += f"> **Seu prefixo de usuário:** `{disnake.utils.escape_markdown(user_data['custom_prefix'], as_needed=True)}`\n"

        links = "[`[Source]`](https://github.com/zRitsu/MuseHeart-MusicBot)"

        if bot.config["SUPPORT_SERVER"]:
            links += f" **|** [`[Suporte]`]({bot.config['SUPPORT_SERVER']})"

        embed.description += f">  {links}\n"

        try:
            owner = bot.appinfo.team.owner
        except AttributeError:
            owner = bot.appinfo.owner

        try:
            avatar = owner.avatar.with_static_format("png").url
        except AttributeError:
            avatar = owner.default_avatar.with_static_format("png").url

        embed.set_footer(
            icon_url=avatar,
            text=f"Dono(a): {owner} [{owner.id}]"
        )

        components = [disnake.ui.Button(custom_id="bot_invite", label="Me adicione no seu servidor")] if [b for b in bot.pool.bots if b.appinfo and (b.appinfo.bot_public or await b.is_owner(inter.author))] else None

        try:
            await inter.edit_original_message(embed=embed, components=components)
        except (AttributeError, disnake.InteractionNotEditable):
            try:
                await inter.response.edit_message(embed=embed, components=components)
            except:
                await inter.send(embed=embed, ephemeral=True, components=components)


    @commands.Cog.listener("on_button_click")
    async def invite_button(self, inter: disnake.MessageInteraction, is_command=False):

        if not is_command and inter.data.custom_id != "bot_invite":
            return

        bots_invites = []
        bots_in_guild = []

        guild = inter.guild

        if not guild:
            for bot in self.bot.pool.bots:
                if (guild:=bot.get_guild(inter.guild_id)):
                    break

        for bot in sorted(self.bot.pool.bots, key=lambda b: len(b.guilds)):

            try:
                if not bot.appinfo.bot_public and not await bot.is_owner(inter.author):
                    continue
            except:
                continue

            if str(bot.user.id) in bot.config['INTERACTION_BOTS_CONTROLLER']:
                continue

            kwargs = {"redirect_uri": self.bot.config['INVITE_REDIRECT_URL']} if self.bot.config['INVITE_REDIRECT_URL'] else {}

            invite = f"[`{disnake.utils.escape_markdown(str(bot.user.name))}`]({disnake.utils.oauth_url(bot.user.id, permissions=disnake.Permissions(bot.config['INVITE_PERMISSIONS']), scopes=('bot', 'applications.commands'), **kwargs)})"

            if not str(bot.user.id) not in self.bot.config["INTERACTION_BOTS_CONTROLLER"] and bot.appinfo.flags.gateway_message_content_limited:
                invite += f" ({len(bot.guilds)}/100)"
            else:
                invite += f" ({len(bot.guilds)})"

            if guild and inter.author.guild_permissions.manage_guild and bot.user in guild.members:
                bots_in_guild.append(invite)
            else:
                bots_invites.append(invite)

        txt = ""

        if bots_invites:
            txt += "**Bots de música disponíveis:**\n"
            for i in disnake.utils.as_chunks(bots_invites, 2):
                txt += " | ".join(i) + "\n"
            txt += "\n"

        if bots_in_guild:
            txt += "**Bots de música que já estão no servidor atual:**\n"
            for i in disnake.utils.as_chunks(bots_in_guild, 2):
                txt += " | ".join(i) + "\n"

        if not txt:
            await inter.send(
                embed=disnake.Embed(
                    colour=self.bot.get_color(
                        inter.guild.me if inter.guild else guild.me if guild else None
                    ),
                    title="**Não há bots públicos disponível...**",
                ), ephemeral=True
            )
            return

        controller_bot = self.bot.pool.controller_bot

        if (len(bots_in_guild) + len(bots_invites)) > 1 and f"client_id={controller_bot.user.id}" not in txt:
            invite = f"[`{disnake.utils.escape_markdown(str(controller_bot.user.name))}`]({disnake.utils.oauth_url(controller_bot.user.id, scopes=['applications.commands'])})"
            txt = f"**Registrar os comandos de barra no servidor:**\n{invite}\n\n" + txt

        color = self.bot.get_color(inter.guild.me if inter.guild else guild.me if guild else None)

        embeds = [
            disnake.Embed(
                colour=self.bot.get_color(inter.guild.me if inter.guild else guild.me if guild else None),
                description=p, color=color
            ) for p in paginator(txt)
        ]

        await inter.send(embeds=embeds, ephemeral=True)


    @commands.command(name="invite", aliases=["convidar"], description="Exibir meu link de convite para você me adicionar no seu servidor.")
    async def invite_legacy(self, ctx):
        await self.invite.callback(self=self, inter=ctx)


    @commands.slash_command(
        description=f"{desc_prefix}Exibir meu link de convite para você me adicionar no seu servidor."
    )
    async def invite(self, inter: disnake.AppCmdInter):

        await inter.response.defer(ephemeral=True)

        await self.invite_button(inter, is_command=True)

    @commands.user_command(name="avatar")
    async def avatar(self, inter: disnake.UserCommandInteraction):

        embeds = []

        assets = {}

        if self.bot.intents.members:
            user = (await self.bot.fetch_user(inter.target.id) if not inter.target.bot else self.bot.get_user(inter.target.id))
        else:
            user = inter.target

        try:
            if inter.target.guild_avatar:
                assets["Avatar (Server)"] = inter.target.guild_avatar.with_static_format("png")
        except AttributeError:
            pass
        assets["Avatar (User)"] = user.display_avatar.with_static_format("png")
        if user.banner:
            assets["Banner"] = user.banner.with_static_format("png")

        for name, asset in assets.items():
            embed = disnake.Embed(description=f"{inter.target.mention} **[{name}]({asset.with_size(2048).url})**",
                                  color=self.bot.get_color(inter.guild.me if inter.guild else None))
            embed.set_image(asset.with_size(256).url)
            embeds.append(embed)

        await inter.send(embeds=embeds, ephemeral=True)

    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.default)
    @commands.command(hidden=True, description="Comando temporário para corrigir favoritos com espaços em branco "
                                               "que ocasionam erros em algumas situações.")
    async def fixfavs(self, ctx: CustomContext):

        if not os.path.isdir("./local_database/fixfavs_backup"):
            os.makedirs("./local_database/fixfavs_backup")

        async with ctx.typing():

            for bot in self.bot.pool.bots:

                db_data = await bot.pool.database.query_data(collection=str(bot.user.id), db_name=DBModel.guilds, limit=300)
    
                async with aiofiles.open(f"./local_database/fixfavs_backup/guild_favs_{bot.user.id}.json", "w") as f:
                    await f.write(json.dumps(db_data, indent=4))

                for data in db_data:
                    try:
                        remove_blank_spaces(data["player_controller"]["fav_links"])
                    except KeyError:
                        continue
                    await bot.update_data(id_=data["_id"], data=data, db_name=DBModel.guilds)

            db_data = await self.bot.pool.database.query_data(collection="global", db_name=DBModel.users, limit=500)

            async with aiofiles.open("./local_database/fixfavs_backup/user_favs.json", "w") as f:
                await f.write(json.dumps(db_data, indent=4))

            for data in db_data:
                remove_blank_spaces(data["fav_links"])
                await self.bot.update_global_data(id_=data["_id"], data=data, db_name=DBModel.users)

            await ctx.send("os favoritos foram corrigidos com sucesso!")

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

        if str(self.bot.user.id) in self.bot.config["INTERACTION_BOTS_CONTROLLER"]:
            return

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
            guild_data = await self.bot.get_data(guild.id, db_name=DBModel.guilds)
            guild_data["player_controller"] = db_models[DBModel.guilds]["player_controller"]
            await self.bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)
        except:
            traceback.print_exc()

        try:
            embed.set_thumbnail(url=guild.icon.replace(static_format="png").url)
        except AttributeError:
            pass

        try:
            await self.send_hook(", ".join(f"<@{owner_id}>" for owner_id in self.bot.owner_ids) or self.bot.owner.mention, embed=embed)
        except:
            traceback.print_exc()

        await self.bot.update_appinfo()

    @commands.Cog.listener()
    async def on_guild_join(self, guild: disnake.Guild):

        if str(self.bot.user.id) in self.bot.config["INTERACTION_BOTS_CONTROLLER"]:
            return

        print(f"Novo servidor: {guild.name} - [{guild.id}]")

        try:
            guild_data = await self.bot.get_data(guild.id, db_name=DBModel.guilds)
            guild_data["player_controller"] = db_models[DBModel.guilds]["player_controller"]
            await self.bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)
        except:
            traceback.print_exc()

        if not self.hook_url:
            return

        created_at = int(guild.created_at.timestamp())

        embed =disnake.Embed(
            description="__**Me adicionaram em um novo servidor:**__\n"
                        f"```{guild.name}```\n"
                        f"**ID:** `{guild.id}`\n"
		                f"**Dono:** `{guild.owner} [{guild.owner.id}]`\n"
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

        try:
            await self.send_hook(", ".join(f"<@{owner_id}>" for owner_id in self.bot.owner_ids) or self.bot.owner.mention, embed=embed)
        except:
            traceback.print_exc()

        await self.bot.update_appinfo()

    async def send_hook(self, content="", *, embed: disnake.Embed=None):

        async with ClientSession() as session:
            webhook = disnake.Webhook.from_url(self.hook_url, session=session)
            await webhook.send(
                content=content,
                username=self.bot.user.name,
                avatar_url=self.bot.user.display_avatar.replace(size=256, static_format="png").url,
                embed=embed
            )


def setup(bot: BotCore):
    bot.add_cog(Misc(bot))
    bot.add_cog(GuildLog(bot))
