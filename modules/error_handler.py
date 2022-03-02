from __future__ import annotations
import disnake
from aiohttp import ClientSession
from disnake.ext import commands
from utils.music.converters import URL_REG
from utils.music.errors import parse_error
from utils.others import send_message
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.client import BotCore


class ErrorHandler(commands.Cog):
    
    def __init__(self, bot: BotCore):
        self.bot = bot
        self.components = []

        if self.bot.config["ERROR_REPORT_WEBHOOK"]:
            self.components.append(
                disnake.ui.Button(
                    label="Reporte esse erro",
                    custom_id="report_error",
                    emoji="⚠"
                )
            )

        if self.bot.config["SUPPORT_SERVER"]:
            self.components.append(
                disnake.ui.Button(
                    label="Servidor de suporte",
                    url=self.bot.config["SUPPORT_SERVER"]
                )
            )


    @commands.Cog.listener('on_user_command_error')
    @commands.Cog.listener('on_message_command_error')
    @commands.Cog.listener('on_slash_command_error')
    async def on_interaction_command_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception):

        embed = disnake.Embed(color=disnake.Colour.red())

        error_msg = parse_error(inter, error)

        if not error_msg:
            components = self.components
            embed.title = "Ocorreu um erro no comando:"
            embed.description = f"```py\n{repr(error)[:2030].replace(self.bot.http.token, 'mytoken')}```"

        else:
            components = None
            embed.description = error_msg

        await send_message(inter, text=inter.author.mention, embed=embed, components=components)


    @commands.Cog.listener("on_command_error")
    async def on_legacy_command_error(self, ctx: commands.Context, error: Exception):

        embed = disnake.Embed(color=disnake.Colour.red())

        if isinstance(error, commands.CommandNotFound):
            return

        error_msg = parse_error(ctx, error)

        if not error_msg:
            components = self.components
            embed.title = "Ocorreu um erro no comando:"
            embed.description = f"```py\n{repr(error)[:2030].replace(self.bot.http.token, 'mytoken')}```"

        else:
            components = None
            embed.description = error_msg

        await ctx.send(ctx.author.mention, embed=embed, components=components)


    @commands.Cog.listener("on_button_click")
    async def on_error_report(self, inter: disnake.MessageInteraction):

        if inter.data.custom_id != "report_error":
            return

        if str(inter.author.id) not in inter.message.content:
            await inter.send(f"Apenas o usuário {inter.message.content} pode usar esse botão!", ephemeral=True)
            return

        await inter.response.send_modal(
            title="Reportar erro",
            custom_id=f"error_report_submit_{inter.message.id}",
            components=[
                disnake.ui.TextInput(
                    style=disnake.TextInputStyle.long,
                    label="Detalhes",
                    custom_id="error_details",
                    max_length=1900,
                    required=True
                ),
                disnake.ui.TextInput(
                    style=disnake.TextInputStyle.short,
                    label="Link de imagem/print do erro (Opcional)",
                    custom_id="image_url",
                    max_length=300,
                    required=False
                )
            ]
        )


    @commands.Cog.listener("on_modal_submit")
    async def on_report_submit(self, inter: disnake.ModalInteraction):

        if not inter.custom_id.startswith("error_report_submit"):
            return

        try:
            original_message = await inter.channel.fetch_message(int(inter.custom_id[20:]))
        except (disnake.Forbidden, disnake.HTTPException):
            await inter.send("A Mensagem original foi deletada ou está inacessível.", ephemeral=True)
            return

        if not original_message.embeds:
            await inter.send(
                embed=disnake.Embed(
                    title="A embed da mensagem foi removida!",
                    description=inter.text_values["error_details"]
                ), ephemeral=True
            )
            return


        image_url = inter.text_values["image_url"]

        if image_url and not URL_REG.match(image_url):

            await inter.send(
                embed=disnake.Embed(
                    title="Link de imagem inválida!",
                    description=inter.text_values["error_details"]
                ), ephemeral=True
            )
            return

        embed = disnake.Embed(
            color=self.bot.get_color(inter.guild.me),
            description=inter.text_values["error_details"],
            title="Report de erro"
        )

        embed.add_field(name="Log:", value=original_message.embeds[0].description)

        await original_message.delete()

        await inter.send(
            embed=disnake.Embed(
                description="**Erro reportado com sucesso!**",
                color=self.bot.get_color(inter.guild.me)
            )
        )

        try:
            user_avatar = inter.author.avatar.with_static_format("png").url
        except AttributeError:
            user_avatar = inter.author.avatar.url

        embed.set_author(name=f"Erro reportado: {inter.author} - {inter.author.id}", icon_url=user_avatar)

        guild_txt = f"Servidor: {inter.guild.name} [{inter.guild.id}]"

        try:
            embed.set_footer(text=guild_txt, icon_url=inter.guild.icon.with_static_format("png").url)
        except AttributeError:
            embed.set_footer(text=guild_txt)

        if image_url:
            embed.set_image(url=image_url)

        async with ClientSession() as session:
            webhook = disnake.Webhook.from_url(self.bot.config["ERROR_REPORT_WEBHOOK"], session=session)
            await webhook.send(
                username=self.bot.user.name,
                avatar_url=self.bot.user.avatar.replace(static_format='png').url,
                embed=embed
            )


def setup(bot: BotCore):
    bot.add_cog(ErrorHandler(bot))