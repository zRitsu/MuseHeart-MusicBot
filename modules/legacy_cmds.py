import disnake
from disnake.ext import commands
import traceback
from utils.client import BotCore


class Owner(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot


    @commands.is_owner()
    @commands.command(aliases=["rd", "recarregar"], hidden=True)
    async def reload(self, ctx):

        data = self.bot.load_modules()

        txt = ""

        if data["loaded"]:
            txt += f'```ini\n[Carregados]: {len(data["loaded"])}```\n'

        if data["reloaded"]:
            txt += f'```ini\n[Recarregados]: {len(data["reloaded"])}```\n'

        if data["error"]:
            txt += f'```ml\n\'Falharam\': {", ".join(m + ".py" for m in data["error"])}```'

        if not txt:
            txt = "**Nenhum módulo encontrado...**"

        embed = disnake.Embed(colour=self.bot.get_color(ctx.me), description=txt)
        await ctx.send(embed=embed)


    @commands.command()
    @commands.is_owner()
    async def syncglobal(self, ctx: commands.Context):

        embed = disnake.Embed(color=disnake.Colour.green())

        original_list = self.bot._test_guilds
        original_sync_config = self.bot._sync_commands
        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={ctx.bot.user.id}&scope=applications.commands"

        self.bot._test_guilds = None
        self.bot._sync_commands = True

        try:
            await self.bot._sync_application_commands()
            embed.description = f"**Comandos globais sincronizados**\n`(as alterações podem demorar até 1 hora)`\n\n" \
                                f"Caso os comandos não apareçam após esse tempo, [clique aqui]({invite_url}) para permitir o bot " \
                                f"criar comandos slash no servidor e use este mesmo comando novamente."
            await ctx.send(embed=embed)

        except Exception as e:
            traceback.print_exc()
            embed.colour = disnake.Colour.red()
            embed.description = f"**Falha ao sincronizar:** ```py\n{repr(e)}```"
            await ctx.send(embed=embed)

        self.bot._test_guilds = original_list
        self.bot._sync_commands = original_sync_config


    @commands.command(aliases=["sync"])
    @commands.has_guild_permissions(manage_guild=True)
    @commands.cooldown(2, 300, commands.BucketType.guild)
    async def syncguild(self, ctx: commands.Context):

        embed = disnake.Embed(color=disnake.Colour.green())

        original_list = self.bot._test_guilds
        original_sync_config = self.bot._sync_commands
        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={ctx.bot.user.id}&scope=applications.commands"

        self.bot._test_guilds = [ctx.guild.id]
        self.bot._sync_commands = True

        try:
            await self.bot._sync_application_commands()
            embed.description = f"**Comandos sincronizados para o servidor:**\n`{ctx.guild.name} [{ctx.guild.id}]`\n\n" \
                                f"Caso os comandos de barra não apareçam, [clique aqui]({invite_url}) para permitir o bot " \
                                f"criar comandos slash no servidor e use este mesmo comando novamente."
            await ctx.send(embed=embed)
        except Exception as e:
            traceback.print_exc()
            embed.colour = disnake.Colour.red()
            embed.description = f"**Falha ao sincronizar:** ```py\n{repr(e)}```"
            await ctx.send(embed=embed)

        self.bot._test_guilds = original_list
        self.bot._sync_commands = original_sync_config


def setup(bot: BotCore):
    bot.add_cog(Owner(bot))
