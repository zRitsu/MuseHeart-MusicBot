from __future__ import annotations

import json
import random
import asyncio

from typing import TYPE_CHECKING, Optional

import disnake
from disnake.ext import commands

from utils.music.converters import fix_characters, time_format
from utils.music.errors import GenericError
from utils.others import CustomContext
from utils.music.models import LavalinkPlayer

if TYPE_CHECKING:
    from utils.client import BotCore


def preview(ctx: CustomContext, data: str, player: Optional[LavalinkPlayer] = None) -> dict:

    if player:

        requester = ctx.guild.get_member(player.current.requester)

        data = data. \
            replace('{track.title_25}', fix_characters(player.current.title, 25)). \
            replace('{track.title_42}', fix_characters(player.current.title, 42)). \
            replace('{track.title_58}', fix_characters(player.current.title, 58)). \
            replace('{track.title}', player.current.title). \
            replace('{track.url}', player.current.uri). \
            replace('{track.author}', player.current.author). \
            replace('{track.duration}', time_format(player.current.duration)). \
            replace('{track.thumb}', player.current.thumb). \
            replace('{playlist.name}', player.current.playlist_name or "Nenhuma"). \
            replace('{playlist.url}', player.current.playlist_url). \
            replace('{loop.mode}', 'Desativado' if not player.loop else 'Música atual' if player.loop == "current" else "Fila"). \
            replace('{log.text}', player.command_log or ""). \
            replace('{log.emoji}', player.command_log_emoji or "Sem registro."). \
            replace('{requester.mention}', f'<@{player.current.requester}>'). \
            replace('{requester.avatar}', requester.display_avatar.with_static_format("png").url). \
            replace('{requester.tag}', f"{requester.display_name}#{requester.discriminator}"). \
            replace('{requester.color}', str(player.bot.get_color(player.guild.me).value)). \
            replace('{guild.icon}', player.guild.icon.with_static_format("png").url if ctx.guild.icon else ""). \
            replace('{guild.name}', player.guild.name). \
            replace('{guild.id}', str(player.guild.id)). \
            replace('{player.queue.size}', str(len(player.queue))). \
            replace('{player.volume}', str(player.volume))

    else:

        track_title = 'Sekai - Burn Me Down [NCS Release]'

        data = data.\
            replace('{track.title_25}', fix_characters(track_title, 25)). \
            replace('{track.title_42}', fix_characters(track_title, 42)). \
            replace('{track.title_58}', fix_characters(track_title, 58)). \
            replace('{track.title}', track_title). \
            replace('{track.url}', 'https://youtu.be/B6DmYzyjjMU'). \
            replace('{track.author}', "NoCopyrightSounds"). \
            replace('{track.duration}', '3:35'). \
            replace('{track.thumb}', "https://img.youtube.com/vi/2vFA0HL9kTk/mqdefault.jpg"). \
            replace('{playlist.name}', "🎵 DV 🎶"). \
            replace('{playlist.url}', "https://www.youtube.com/playlist?list=PLKlXSJdWVVAD3iztmL2vFVrwA81sRkV7n"). \
            replace('{loop.mode}', "Música Atual"). \
            replace('{log.emoji}', "⏭️"). \
            replace('{log.text}', f"{random.choice(ctx.guild.members)} pulou a música."). \
            replace('{requester.mention}', ctx.author.mention). \
            replace('{requester.avatar}', ctx.author.display_avatar.with_static_format("png").url). \
            replace('{requester.tag}', f"{ctx.author.display_name}#{ctx.author.discriminator}"). \
            replace('{requester.color}', str(ctx.bot.get_color(ctx.guild.me).value)). \
            replace('{guild.icon}', ctx.guild.icon.with_static_format("png").url if ctx.guild.icon else ""). \
            replace('{guild.name}', ctx.guild.name). \
            replace('{guild.id}', str(ctx.guild.id)). \
            replace('{player.queue.size}', "6"). \
            replace('{player.volume}', "100")

    data = json.loads(data)

    if embeds := data.get("embeds"):
        for d in embeds:
            try:
                d["color"] = int(d["color"])
            except:
                try:
                    d["color"] = int(d["color"], 16)
                except KeyError:
                    continue

    return {'content': data.pop('content', ""), 'embeds': [disnake.Embed.from_dict(e) for e in data.get("embeds")]}

class CustomSkin(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    @commands.is_owner()
    @commands.command(hidden=True)
    async def setskin(self, ctx: CustomContext, *, data: str):

        data = data.replace('\\\n', '\n').replace("\`", "`")

        if data.startswith('```'):
            data = "\n".join(data[:-3].split("\n")[1:])

        player = None

        for b in ctx.bot.pool.bots:
            try:
                player = b.music.players[ctx.guild.id]
                break
            except KeyError:
                continue

        msg = await ctx.reply(**preview(ctx, data, player))

        emojis = ["✅", "❌"]

        for e in emojis:
            await msg.add_reaction(e)

        try:
            reaction, user = await ctx.bot.wait_for("reaction_add", check=lambda r, u: r.message.id == msg.id and u.id == ctx.author.id and str(r.emoji) in emojis, timeout=120)
        except asyncio.TimeoutError:
            await msg.clear_reactions()
            raise GenericError("**Tempo esgotado!**")

        emoji = str(reaction.emoji)

        if emoji == "❌":
            await msg.clear_reactions()
            await ctx.reply(embed=disnake.Embed(description=f"**Cancelado pelo usuário.**", color=disnake.Color.red()))
            return

        await ctx.reply("Skin aplicada com sucesso.")

def setup(bot):
    bot.add_cog(CustomSkin(bot))
