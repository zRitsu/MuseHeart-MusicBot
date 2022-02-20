from __future__ import annotations
import disnake
from disnake.ext import commands
from utils.music.errors import parse_error
from utils.others import send_message
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.client import BotCore

class ErrorHandler(commands.Cog):
    
    def __init__(self, bot: BotCore):
        self.bot = bot


    @commands.Cog.listener('on_user_command_error')
    @commands.Cog.listener('on_message_command_error')
    @commands.Cog.listener('on_slash_command_error')
    async def on_interaction_command_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception):

        embed = disnake.Embed(color=disnake.Colour.red())

        error_msg = parse_error(inter, error)

        if not error_msg:
            embed.description = "**Ocorreu um erro no comando:**\n" \
                                f"```py\n{repr(error)[:2020].replace(self.bot.http.token, 'mytoken')}```"

            if self.bot.config["SUPPORT_SERVER"]:
                embed.description += f"\nCaso queira, reporte esse erro no meu [`servidor de suporte`]({self.bot.config['SUPPORT_SERVER']})."

        else:

            embed.description = error_msg

        await send_message(inter, embed=embed)


    @commands.Cog.listener("on_command_error")
    async def on_legacy_command_error(self, ctx: commands.Context, error: Exception):

        embed = disnake.Embed(color=disnake.Colour.red())

        if isinstance(error, commands.CommandNotFound):
            return

        error_msg = parse_error(ctx, error)

        if not error_msg:
            embed.description = "**Ocorreu um erro no comando:**\n" \
                                f"```py\n{repr(error)[:2020].replace(self.bot.http.token, 'mytoken')}```"

            if self.bot.config["SUPPORT_SERVER"]:
                embed.description += f"\nCaso queira, reporte esse erro no meu [`servidor de suporte`]({self.bot.config['SUPPORT_SERVER']})."

        else:

            embed.description = error_msg

        await ctx.reply(embed=embed)


def setup(bot: BotCore):
    bot.add_cog(ErrorHandler(bot))