# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Union, TYPE_CHECKING, Optional

import disnake
from disnake.ext import commands

from utils.others import CustomContext

if TYPE_CHECKING:
    from utils.client import BotCore


class ServerManagerView(disnake.ui.View):

    def __init__(self, inter: Union[disnake.Interaction, CustomContext]):
        super().__init__(timeout=300)
        self.message: Optional[disnake.Message] = None
        self.inter = inter
        self.bot = [b for b in inter.bot.pool.get_guild_bots(inter.guild.id) if b.guilds][0]
        self.pages = list(disnake.utils.as_chunks([g for g in self.bot.guilds], 25))
        self.current_page = 0
        self.current_guild = self.pages[self.current_page][0]
        self.rebuild_components()

    def bot_count(self, g: disnake.Guild):
        return len([m for m in g.members if m.bot])

    def member_count(self, g: disnake.Guild):
        return len([m for m in g.members if not m.bot])

    async def update_data(self, interaction: disnake.MessageInteraction):
        self.current_page = 0
        self.pages = list(disnake.utils.as_chunks([g for g in self.bot.guilds], 25))
        self.current_guild = self.pages[0][0]
        await self.update_message(interaction)

    def build_bot_select(self):

        opts = [
            disnake.SelectOption(
                label=f"{bot.user}", value=str(bot.user.id),
                description=f"{bot.user.id} / Servers: {len(bot.guilds)}",
                default=bot.user.id == self.bot.user.id
            ) for bot in self.bot.pool.get_guild_bots(self.inter.guild_id) if bot.guilds
        ]

        select = disnake.ui.Select(
            placeholder="Selecione um Bot:",
            options=opts
        )

        select.callback = self.select_bot

        return select

    def build_select(self):

        opts = [
            disnake.SelectOption(
                label=f"{guild.name}", value=str(guild.id),
                description=f"{guild.id} [m: {self.member_count(guild)} / b: {self.bot_count(guild)}]",
                default=guild.id == self.current_guild.id) for guild in self.pages[self.current_page]
        ]

        select = disnake.ui.Select(
            placeholder="Selecione um Servidor:",
            options=opts,
            custom_id="server_selection"
        )

        select.callback = self.opts_callback

        return select

    def build_embed(self, interaction: Union[disnake.MessageInteraction, CustomContext]):

        created_at = int(self.current_guild.created_at.timestamp())
        joined_at = int(self.current_guild.me.joined_at.timestamp())
        color = self.bot.get_color(self.current_guild.me)

        embed = disnake.Embed(
            color=color,
            description=f"```{self.current_guild.name}```\n"
                        f"**ID:** `{self.current_guild.id}`\n"
                        f"**Dono:** `{self.current_guild.owner} [{self.current_guild.owner.id}]`\n"
                        f"**Criado em:** <t:{created_at}:f> - <t:{created_at}:R>\n"
                        f"**Sou membro desde:** <t:{joined_at}:f> - <t:{joined_at}:R>\n"
                        f"**Nível de verificação:** `{self.current_guild.verification_level or 'nenhuma'}`\n"
                        f"**Membros:** `{self.member_count(self.current_guild)}`\n"
                        f"**Bots:** `{self.bot_count(self.current_guild)}`"
        )

        if len(self.pages) > 1:
            embed.title = f"Página atual: [{self.current_page+1}/{len(self.pages)}]"

        if self.current_guild.icon:
            embed.set_thumbnail(url=self.current_guild.icon.with_static_format("png").url)

        if interaction.guild.id == self.current_guild.id and interaction.bot.user.id == self.bot.user.id:
            embed.description += f"\n```ansi\n[32;1mEstou no servidor atual!```"

        embed.set_footer(text=f"{self.bot.user} [ID: {self.bot.user.id}]", icon_url=self.bot.user.display_avatar.url)

        return [embed]

    def rebuild_components(self):

        if (has_server_select:=len(self.pages[0]) > 1):

            self.add_item(self.build_select())

        if len(self.bot.pool.get_guild_bots(self.inter.guild_id)) > 1:
            self.add_item(self.build_bot_select())

        if has_server_select and len(self.pages) > 1:

            back = disnake.ui.Button(label="Voltar", emoji="⬅️")
            back.callback = self.previous_page
            self.add_item(back)

            next = disnake.ui.Button(label="Avançar", emoji="➡️")
            next.callback = self.next_page
            self.add_item(next)

        leave = disnake.ui.Button(label="Remover", emoji="♻️", style=disnake.ButtonStyle.red)
        leave.callback = self.leave_guild
        self.add_item(leave)

        stop = disnake.ui.Button(label="Parar", emoji="⏹️", style=disnake.ButtonStyle.blurple)
        stop.callback = self.stop_interaction
        self.add_item(stop)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:

        if interaction.author.id != self.inter.user.id:
            await interaction.response.send_message("Você não pode interagir aqui...", ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        for c in self.children:
            c.disabled = True
        await self.message.edit(view=self)

    async def update_message(self, interaction: disnake.MessageInteraction):

        self.clear_items()
        self.rebuild_components()

        func = interaction.response.edit_message if not interaction.response.is_done() else interaction.message.edit
        await func(embeds=self.build_embed(interaction), view=self)

    async def select_bot(self, interaction: disnake.MessageInteraction):
        self.bot = [b for b in self.bot.pool.get_guild_bots(interaction.guild_id) if str(b.user.id) == interaction.values[0]][0]
        await self.update_data(interaction)

    async def leave_guild(self, interaction: disnake.MessageInteraction):

        if interaction.guild.id == self.current_guild.id and interaction.bot.user.id == self.bot.user.id:
            await interaction.response.edit_message(
                embed=disnake.Embed(
                    description="**Você me removeu do servidor atual.**",
                    color=self.bot.get_color(interaction.guild.me)
                ),
                view=None
            )
            await self.current_guild.leave()
            self.stop()
            return

        await interaction.response.defer()
        await self.current_guild.leave()
        await self.update_data(interaction)

    async def stop_interaction(self, interaction: disnake.MessageInteraction):
        await interaction.message.delete()
        self.stop()

    async def next_page(self, interaction: disnake.MessageInteraction):
        if self.current_page == (len(self.pages) - 1):
            self.current_page = 0
        else:
            self.current_page += 1
        self.current_guild = self.pages[self.current_page][0]
        await self.update_message(interaction)

    async def previous_page(self, interaction: disnake.MessageInteraction):
        if self.current_page == 0:
            self.current_page = (len(self.pages)-1)
        else:
            self.current_page -= 1
        self.current_guild = self.pages[self.current_page][0]
        await self.update_message(interaction)

    async def opts_callback(self, interaction: disnake.MessageInteraction):
        self.current_guild = self.bot.get_guild(int(interaction.values[0]))
        await self.update_message(interaction)


class ServerManagerCog(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    @commands.max_concurrency(1, commands.BucketType.default)
    @commands.is_owner()
    @commands.command(name="servers", aliases=["servermanager"], hidden=True,
                      description="Gerenciar servidores em que o bot está.")
    async def servermanager(self, ctx: CustomContext):

        view = ServerManagerView(ctx)
        view.message = await ctx.reply(embeds=view.build_embed(ctx), view=view, fail_if_not_exists=False)
        await view.wait()

def setup(bot: BotCore):
    bot.add_cog(ServerManagerCog(bot))
