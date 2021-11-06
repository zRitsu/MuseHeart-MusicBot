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

        embed = disnake.Embed(colour=ctx.me.color, description=txt)
        await ctx.send(embed=embed)

    @commands.command(aliases=["syncglobal"])
    @commands.is_owner()
    async def syncguild(self, ctx, guild_id: int = None):

        embed = disnake.Embed(color=disnake.Colour.green())

        if not guild_id:
            guild = ctx.guild
        else:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                embed.colour = disnake.Colour.red()
                embed.description = f"**Servidor com id** `{guild_id}` **não encontrado.**"
                await ctx.send(embed=embed)
                return

        original_list = self.bot._test_guilds
        original_sync_config = self.bot._sync_commands

        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={ctx.bot.user.id}&scope=applications.commands"

        if ctx.invoked_with == "syncguild":
            self.bot._test_guilds = [guild.id]
            embed.description = f"**Comandos sincronizados para o servidor:**\n`{guild.name} [{guild.id}]`\n\n" \
                                f"Caso os comandos de barra não apareçam [clique aqui]({invite_url}) para permitir o bot " \
                                f"criar comandos slash no servidor e use este mesmo comando novamente."
        else:
            self.bot._test_guilds = None
            embed.description = f"**Comandos globais sincronizados**\n`(as alterações podem demorar até 1 hora)`\n\n" \
                                f"Caso os comandos não apareçam após esse tempo, [clique aqui]({invite_url}) para permitir o bot " \
                                f"criar comandos slash no servidor e use este mesmo comando novamente."

        self.bot._sync_commands = True

        try:
            await self.bot._sync_application_commands()
            await ctx.send(embed=embed)
        except Exception as e:
            traceback.print_exc()
            embed.colour = disnake.Colour.red()
            embed.description = f"**Falha ao sincronizar:** ```py\n{repr(e)}```"
            await ctx.send(embed=embed)

        self.bot._test_guilds = original_list
        self.bot._sync_commands = original_sync_config

def setup(bot):
    bot.add_cog(Owner(bot))
