# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import disnake
from disnake.ext import commands

from utils.db import DBModel
from utils.music.errors import GenericError
from utils.music.models import LavalinkPlayer
from utils.music.skin_utils import skin_converter
from utils.others import CustomContext

if TYPE_CHECKING:
    from utils.client import BotCore


class Skinbutton(disnake.ui.View):

    def __init__(self, user: disnake.Member, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.mode = None

    @disnake.ui.button(label="Modo normal")
    async def normal(self, button, interaction: disnake.MessageInteraction):
        self.mode = "custom_skins"
        self.stop()

    @disnake.ui.button(label="Modo estático (song-request)")
    async def static(self, button, interaction: disnake.MessageInteraction):
        self.mode = "custom_skins_static"
        self.stop()

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:

        if inter.user.id != self.user.id:
            await inter.send(f"Apenas o membro {self.user.mention} pode usar es botões da mensagem.", ephemeral=True)
            return False

        return True


class CustomSkin(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(hidden=True)
    async def setskin(self, ctx: CustomContext, *, data: str):

        data = data.replace('\\\n', '\n').replace("\`", "`")

        if data.startswith('```'):
            data = "\n".join(data[:-3].split("\n")[1:])

        player = None

        for b in self.bot.pool.bots:
            try:
                player = b.music.players[ctx.guild.id]
                break
            except KeyError:
                continue

        preview_data = skin_converter(data, ctx, player)

        msg = await ctx.reply(fail_if_not_exists=False, **preview_data)

        emojis = ["✅", "❌"]

        for e in emojis:
            await msg.add_reaction(e)

        try:
            reaction, user = await self.bot.wait_for("reaction_add", check=lambda r, u: r.message.id == msg.id and u.id == ctx.author.id and str(r.emoji) in emojis, timeout=120)
        except asyncio.TimeoutError:
            await msg.clear_reactions()
            raise GenericError("**Tempo esgotado!**")

        emoji = str(reaction.emoji)

        if emoji == "❌":
            await msg.clear_reactions()
            await ctx.reply(
                embed=disnake.Embed(description=f"**Cancelado pelo usuário.**", color=disnake.Color.red()),
                fail_if_not_exists=False
            )
            return

        await ctx.send("Envie o nome que deseja dar a skin (em até 30 segundos e no máximo 15 caracteres).")

        try:
            msg = await self.bot.wait_for(
                "message",
                timeout=30,
                check=lambda m: m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
            )
        except asyncio.TimeoutError:
            await ctx.reply("Tempo esgotado!", fail_if_not_exists=False)
            return

        if (msg_len:=len(msg.content)) > 15:
            await ctx.reply(
                f"A quantidade de caracteres do nome ({msg_len}) ultrapassou o limite (15).",
                fail_if_not_exists=False
            )
            return

        skin_name = msg.content

        view = Skinbutton(ctx.author, timeout=30)
        msg = await ctx.send("Selecione o modo que deseja aplicar a skin aplicar.", view=view)

        await view.wait()

        if view.mode is None:
            await msg.edit("Tempo esgotado!", components=[])
            return

        try:
            global_data = ctx.global_guild_data
        except AttributeError:
            global_data = await self.bot.get_global_data(ctx.guild_id, db_name=DBModel.guilds)
            ctx.global_guild_data = global_data

        global_data[view.mode][skin_name] = json.dumps(json.loads(data))

        for b in self.bot.pool.bots:
            try:
                player: LavalinkPlayer = b.music.players[ctx.guild.id]
            except KeyError:
                continue
            else:
                player.custom_skin_data = global_data["custom_skins"]
                player.custom_skin_static_data = global_data["custom_skins_static"]

        await self.bot.update_global_data(ctx.guild_id, global_data, db_name=DBModel.guilds)

        await msg.edit("a skin foi salva/alterada com sucesso!", view=None)

def setup(bot):
    bot.add_cog(CustomSkin(bot))
