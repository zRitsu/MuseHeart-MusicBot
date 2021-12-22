import sys
import subprocess

import disnake
from disnake.ext import commands
import traceback
from utils.client import BotCore
from utils.music.errors import GenericError


class Owner(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot


    @commands.is_owner()
    @commands.command(aliases=["rd", "recarregar"], description="Recarregar os módulos (apenas para meu dono).")
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


    def run_command(self, cmd):
        return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()


    @commands.is_owner()
    @commands.command(aliases=["up", "atualizar"], description="Atualizaro code do bot (apenas para meu dono).")
    async def update(self, ctx: commands.Context, usepip="no"):

        if usepip not in ["píp", "no"]:
            raise GenericError(f"Opção inválida: {usepip}")

        await ctx.message.add_reaction("⏲️")

        embed = disnake.Embed(color=self.bot.get_color(ctx.guild.me))

        try:
            self.run_command("git reset --hard")
        except Exception as e:
            embed.title = "Ocorreu um erro no git reset:"
            embed.description = f"Code: {e.returncode} | {e.output}"
            await ctx.send(embed=embed)
            return

        with open("requirements.txt") as f:
            original_req = f.read()

        try:
            out_git = self.run_command("git pull")
        except Exception as e:
            embed.title = "Ocorreu um erro no git pull:"
            embed.description = f"Code: {e.returncode} | {e.output}"
            await ctx.send(embed=embed)
            return

        if "Already up to date" in out_git:
            embed.description = f"**Já estou com os ultimos updates instalados...**"
            await ctx.send(embed=embed)
            return

        with open("requirements.txt") as f:
            new_req = f.read()

        if usepip == "pip":
            subprocess.check_output("pip3 install -r requirements.txt", shell=True, text=True)

        text = "Reinicie o bot após as alterações."

        if original_req != new_req:
            text += "\nNota: Será necessário atualizar as dependências."

        embed.title = "Status do update:"
        embed.description = f"```{out_git[:1018]}```\n\n{text}",

        await ctx.send(embed=embed)


    async def sync_guild_commands(self, *, ctx: commands.Context = None, guilds = None):

        original_list = self.bot._test_guilds
        original_sync_config = self.bot._sync_commands

        self.bot._test_guilds = guilds if not guilds is None else []
        self.bot._sync_commands = True

        try:
            await self.bot._sync_application_commands()
            error_txt = ""
        except Exception as e:
            traceback.print_exc()
            error_txt = repr(e)

        if ctx:

            embed = disnake.Embed(color=disnake.Colour.green())

            if not error_txt:

                invite_url = f"https://discord.com/api/oauth2/authorize?client_id={ctx.bot.user.id}&scope=applications.commands"

                if len(guilds) > 1:
                    txt = f"**Comandos sincronizados para {len(guilds)} servidores**"
                else:
                    txt = f"**Comandos sincronizados para o servidor:**\n`{ctx.guild.name} [{ctx.guild.id}]`"

                embed.description = f"{txt}\n\n" \
                                    f"`Caso os comandos de barra não apareçam,` [`clique aqui`]({invite_url}) `para me permitir " \
                                    f"criar comandos slash no servidor e use este mesmo comando novamente.`\n\n" \
                                    f"`Nota: Caso o comando de barra sofra alguma atualização/alteração nos parâmetros e " \
                                    f"texto será necessário usar este comando em todos os servidores novamente, recomendo " \
                                    f"que use o comando: {self.syncglobal.name}`"
                await ctx.send(embed=embed)

            else:

                embed.colour = disnake.Colour.red()
                embed.description = f"**Falha ao sincronizar:** ```py\n{error_txt}```"
                await ctx.send(embed=embed)

        self.bot._test_guilds = original_list
        self.bot._sync_commands = original_sync_config


    @commands.command(aliases=["sync"], description="Sincronizar/Registrar os comandos de barra no servidor.")
    @commands.has_guild_permissions(manage_guild=True)
    @commands.cooldown(2, 300, commands.BucketType.guild)
    async def syncguild(self, ctx: commands.Context):

        await self.sync_guild_commands(ctx=ctx, guilds=[ctx.guild.id])


    @commands.command(aliases=["sgs"], description="Sincronizar/Registrar os comandos de barra em todos os servidores (apenas para meu dono).\n"
                                                   "Nota: Dependendo da quantidade de servidores que o bot está. "
                                                   "Recomendo usar o comando syncglobal ao invés deste")
    @commands.is_owner()
    async def syncguilds(self, ctx: commands.Context):
        await self.sync_guild_commands(ctx=ctx, guilds=[g.id for g in ctx.bot.guilds])


    @commands.command(description="Sincronizar/Registrar os comandos de barra globalmente (apenas para meu dono).\n"
                                  "Nota: Os comandos de barra podem demorar 60 minutos ou mais pra aparecer em todos os servidores.")
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
            embed.description = f"**Comandos globais sincronizados**\n\n" \
                                "Caso os comandos não apareçam tente alguns procedimentos abaixo:\n\n" \
                                f"`1 -` [`clique aqui`]({invite_url}) `para me permitir criar comandos de barra no servidor.`\n\n" \
                                "`2 - Caso o passo acima não funcione, experimente reabrir seu discord.`\n\n" \
                                f"`3 - Se o problema persistir, aguarde 60 minutos para concluir a sincronização dos comandos globais.`"   
            await ctx.send(embed=embed)

        except Exception as e:
            traceback.print_exc()
            embed.colour = disnake.Colour.red()
            embed.description = f"**Falha ao sincronizar:** ```py\n{repr(e)}```"
            await ctx.send(embed=embed)

        self.bot._test_guilds = original_list
        self.bot._sync_commands = original_sync_config


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
