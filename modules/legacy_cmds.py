import disnake
from disnake.ext import commands
import traceback
from utils.client import BotCore


class Owner(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot


    @commands.is_owner()
    @commands.command(aliases=["rd", "recarregar"], description="Recarregar os módulos (apenas para dono do bot).")
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


    @commands.command(aliases=["sync"], description="Sincronizar/Registrar os comandos de barra.", hidden=True)
    @commands.has_guild_permissions(manage_guild=True)
    @commands.cooldown(2, 300, commands.BucketType.guild)
    async def syncguild(self, ctx: commands.Context):

        embed = disnake.Embed(color=disnake.Colour.green())
        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={ctx.bot.user.id}&scope=applications.commands"

        embed.description = f"Este comando atualmente não é mais necessário ser usado..." \
                            f"Mas caso os comandos de barra não apareçam, [clique aqui]({invite_url}) para permitir o bot " \
                            f"criar comandos slash no servidor e use este mesmo comando novamente.\n" \
                            f"Se o problema ainda persistir, tente reiniciar seu discord."
        await ctx.send(embed=embed)


    @commands.command(name="help", aliases=["ajuda"], hidden=True)
    @commands.cooldown(1, 3, commands.BucketType.guild)
    async def help_(self, ctx: commands.Context):

        embed = disnake.Embed(color=self.bot.get_color(ctx.me), title="Meus comandos", description="")

        if ctx.me.avatar:
            embed.set_thumbnail(url=ctx.me.avatar.with_static_format("png").url)

        for cmd in self.bot.commands:

            if cmd.hidden:
                continue

            embed.description += f"**{cmd.name}**"

            if cmd.aliases:
                embed.description += f" [{', '.join(a for a in cmd.aliases)}]"

            if cmd.description:
                embed.description += f" ```ldif\n{cmd.description}```"

            embed.description += "\n"

        if self.bot.slash_commands:
            embed.description += "`Veja meus comandos de barra usando:` **/**"

        await ctx.reply(embed=embed)


def setup(bot: BotCore):
    bot.remove_command("help")
    bot.add_cog(Owner(bot))
