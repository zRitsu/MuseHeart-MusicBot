from __future__ import annotations
from typing import Union, TYPE_CHECKING

import disnake
from disnake.ext import commands

from utils.others import CustomContext, select_bot_pool

if TYPE_CHECKING:
    from utils.client import BotCore


class ServerManagerView(disnake.ui.View):

    def __init__(self, inter: Union[disnake.Interaction, CustomContext], bot: BotCore):
        super().__init__(timeout=500)
        self.inter = inter
        self.bot = bot
        self.current_page = 0
        self.pages = list(disnake.utils.as_chunks(bot.guilds, 25))
        self.current_guild = self.pages[self.current_page][0]
        self.update_components_()

    def bot_count(self, g: disnake.Guild):
        return len([m for m in g.members if m.bot])

    def member_count(self, g: disnake.Guild):
        return len([m for m in g.members if not m.bot])

    async def update_data(self, interaction: disnake.MessageInteraction):
        self.current_page = 0
        self.pages = list(disnake.utils.as_chunks(self.bot.guilds, 25))
        self.current_guild = self.pages[self.current_page][0]
        await self.update_message(interaction)

    def build_bot_select(self):

        opts = [
            disnake.SelectOption(
                label=f"{bot.user}", value=str(bot.user.id),
                description=f"{bot.user.id} / Servers: {len(bot.guilds)}",
                default=bot.user.id == self.bot.user.id
            ) for bot in self.bot.pool.bots
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

    def build_embed(self):

        created_at = int(self.current_guild.created_at.timestamp())
        joined_at = int(self.current_guild.me.joined_at.timestamp())
        color = self.bot.get_color(self.current_guild.me)
        embeds=[]

        embed1 = disnake.Embed(
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

        if self.current_guild.icon:
            embed1.set_thumbnail(url=self.current_guild.icon.with_static_format("png").url)

        embed1.set_footer(text=f"{self.bot.user} [{self.bot.user.id}]", icon_url=self.bot.user.display_avatar.url)

        embeds.append(embed1)

        if len(self.pages) > 1:
            embeds.append(
                disnake.Embed(
                    color=color,
                    description=f"```ansi\n[32;1mPágina atual: [0m [34;1m[{self.current_page}/{len(self.pages)-1}][0m```"
                )
            )

        return embeds

    def update_components_(self):

        if len(self.pages[0]) > 1:

            self.add_item(self.build_select())

            if len(self.pages) > 1:

                back = disnake.ui.Button(label="Voltar", emoji="⬅️")
                back.callback = self.previous_page
                self.add_item(back)

                next = disnake.ui.Button(label="Avançar", emoji="➡️")
                next.callback = self.next_page
                self.add_item(next)

        if len(self.bot.pool.bots) > 1:
            self.add_item(self.build_bot_select())

        leave = disnake.ui.Button(label="Remover", emoji="♻️", style=disnake.ButtonStyle.red)
        leave.callback = self.leave_guild
        self.add_item(leave)

        stop = disnake.ui.Button(label="Parar", emoji="⏹️", style=disnake.ButtonStyle.blurple)
        stop.callback = self.stop_interaction
        self.add_item(stop)

    async def update_message(self, interaction: disnake.MessageInteraction):

        self.clear_items()
        self.update_components_()

        func = interaction.response.edit_message if not interaction.response.is_done() else interaction.message.edit
        await func(embeds=self.build_embed(), view=self)

    async def select_bot(self, interaction: disnake.MessageInteraction):
        self.bot = [b for b in self.bot.pool.bots if str(b.user.id) == interaction.values[0]][0]
        await self.update_data(interaction)

    async def leave_guild(self, interaction: disnake.MessageInteraction):
        guild = self.bot.get_guild(int(interaction.values[0]))
        await interaction.response.defer()
        await guild.leave()
        await self.update_data(interaction)

    async def stop_interaction(self, interaction: disnake.MessageInteraction):
        await interaction.message.delete()
        self.stop()

    async def next_page(self, interaction: disnake.MessageInteraction):
        if self.current_page == (len(self.pages) - 1):
            self.current_page = 0
        else:
            self.current_page += 1
        await self.update_message(interaction)

    async def previous_page(self, interaction: disnake.MessageInteraction):
        if self.current_page == 0:
            self.current_page += (len(self.pages)-1)
        else:
            self.current_page -= 1
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

        ctx, bot = await select_bot_pool(ctx)

        if not bot:
            return

        view = ServerManagerView(ctx, bot)
        await ctx.response.edit_message(embeds=view.build_embed(), view=view)
        await view.wait()

def setup(bot: BotCore):
    bot.add_cog(ServerManagerCog(bot))