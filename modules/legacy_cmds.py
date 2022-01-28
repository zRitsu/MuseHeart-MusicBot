import os
import shutil
import subprocess
import json
import traceback
import disnake
from disnake.ext import commands
from utils.client import BotCore
from utils.music.errors import GenericError

if os.name == "nt":
    q1 = "\"" ; q2 = "'"
else:
    q1 = "'" ; q2 = "\""

git_format = f"--pretty=format:{q1}" + "{" + f"{q2}commit{q2}: {q2}%H{q2}, " \
                                                f"{q2}abbreviated_commit{q2}: {q2}%h{q2}, " \
                                                f"{q2}subject{q2}: {q2}%s{q2}" + "}" + q1 + ","

def run_command(cmd):
    return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()


class Owner(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.git_init_cmds = [
            "git init",
            f'git remote add origin {self.bot.config["SOURCE_REPO"]}',
            'git fetch origin',
            'git checkout -b main -f --track origin/main'
        ]


    def format_log(self, data: list):
        return "\n".join( f"[`{c['abbreviated_commit']}`]({self.bot.remote_git_url}/commit/{c['commit']}) `- "
                          f"{(c['subject'][:60] + '...') if len(c['subject']) > 59 else c['subject']}`" for c in data)


    @commands.is_owner()
    @commands.command(aliases=["rd", "recarregar"], description="Recarregar os módulos (apenas para meu dono).")
    async def reload(self, ctx):

        data = self.bot.load_modules()

        txt = ""

        if data["loaded"]:
            txt += f'**Módulos carregados:** ```ansi\n[0;34m{" [0;37m| [0;34m".join(data["loaded"])}```\n'

        if data["reloaded"]:
            txt += f'**Módulos recarregados:** ```ansi\n[0;32m{" [0;37m| [0;32m".join(data["reloaded"])}```\n'

        if data["error"]:
            txt += f'**Módulos que falharam:** ```ansi\n[0;31m{" [0;37m| [0;31m".join(data["error"])}```\n'

        if not txt:
            txt = "**Nenhum módulo encontrado...**"

        embed = disnake.Embed(colour=self.bot.get_color(ctx.me), description=txt)
        await ctx.send(embed=embed)


    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.default)
    @commands.command(aliases=["up", "atualizar"],
                      description="Atualizar o code do bot usando git (apenas para meu dono).")
    async def update(self, ctx: commands.Context, *, opts: str = ""): #TODO: Rever se há alguma forma de usar commands.Flag sem um argumento obrigatório, ex: --pip.

        out_git = ""

        git_log = []

        with open("requirements.txt") as f:
            original_req = f.read()

        async with ctx.typing():

            if not os.path.isdir("./.git") or (force:="--force" in opts):

                if force:
                    shutil.rmtree("./.git")

                for c in self.git_init_cmds:
                    out_git += run_command(c) + "\n"

            else:

                try:
                    run_command("git reset --hard")
                except Exception as e:
                    raise GenericError(f"Ocorreu um erro no git reset.\nCode: {e.returncode} | {e.output}")

                try:
                    out_git += run_command("git pull --allow-unrelated-histories -X theirs")
                except:
                    try:
                        run_command(f"git reset --hard HEAD~1")
                        out_git += run_command("git pull --allow-unrelated-histories -X theirs")
                    except Exception as e:
                        raise GenericError(f"Ocorreu um erro no git pull:\nCode: {e.returncode} | {e.output}")

                if "Already up to date" in out_git:
                    raise GenericError("Já estou com os ultimos updates instalados...")

                commit = ""

                for l in out_git.split("\n"):
                    if l.startswith("Updating"):
                        commit = l.replace("Updating ", "").replace("..", "...")
                        break

                try:
                    git_log = json.loads("[" + run_command(f"git log {commit} {git_format}")[:-1].replace("'", "\"") + "]")
                except:
                    traceback.print_exc()

            with open("requirements.txt") as f:
                new_req = f.read()

            text = "`Reinicie o bot após as alterações.`"

            if "--pip" in opts:
                subprocess.check_output("pip3 install -U -r requirements.txt", shell=True, text=True)

            elif original_req != new_req:
                text += "\n`Nota: Será necessário atualizar as dependências.`"

            txt = self.format_log(git_log[:10])

            embed = disnake.Embed(
                description=f"{txt}\n\n`📄` **Log:** ```py\n{out_git[:1000]}```{text}",
                title="`✅` Atualização realizada com sucesso!",
                color=self.bot.get_color(ctx.guild.me)
            )

            await ctx.send(embed=embed)


    @commands.is_owner()
    @commands.command(aliases=["latest", "lastupdate"], description="Ver meus últimos updates.")
    async def updatelog(self, ctx: commands.Context, amount: int = 10):

        data = self.format_log(json.loads("[" + run_command(f"git log -{amount or 10} {git_format}")[:-1]
                                          .replace("'", "\"") + "]"))

        embed = disnake.Embed(
            description=f"🔰 ** | Atualizações recentes:**\n\n{data}",
            color=self.bot.get_color(ctx.guild.me)
        )

        await ctx.send(embed=embed)


    @commands.command(aliases=["sync"], description="Sincronizar/Registrar os comandos de barra no servidor.",
                      hidden=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def syncguild(self, ctx: commands.Context):

        invite_url = f"https://discord.com/api/oauth2/authorize?client_id={ctx.bot.user.id}&permissions=8&scope=bot" \
                     f"%20applications.commands "

        embed = disnake.Embed(
            color=self.bot.get_color(ctx.guild.me),
            description="**Este comando não é mais necessário ser usado (A sincronização dos comandos agora é automática).**\n\n" \
                        f"`Caso os comandos de barra não apareçam,` [`clique aqui`]({invite_url}) `para me permitir "
                        "criar comandos de barra no servidor.`\n\n" \
                        "`Nota: Em alguns casos os comandos de barra podem demorar até uma hora pra aparecer em todos "
                        "os servidores. Caso queira usar os comandos de barra imediatamente neste servidor você terá que "
                        f"me expulsar do servidor e em seguida me adicionar novamente através deste` [`link`]({invite_url})..."
        )

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

            if cmd.usage:
                embed.description += f" ```ldif\n{self.bot.default_prefix}{cmd.name} {cmd.usage}```"

            embed.description += "\n"

        if self.bot.slash_commands:
            embed.description += "`Veja meus comandos de barra usando:` **/**"

        await ctx.reply(embed=embed)


    @commands.has_guild_permissions(administrator=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.command(
        aliases=["mudarprefixo", "prefix", "changeprefix"],
        description="Alterar o prefixo do servidor",
        usage="prefixo"
    )
    async def setprefix(self, ctx: commands.Context, prefix: str):

        data = await self.bot.db.get_data(ctx.guild.id, db_name="guilds")
        data["prefix"] = prefix
        await self.bot.db.update_data(ctx.guild.id, data, db_name="guilds")

        embed = disnake.Embed(
            description=f"**Prefixo do servidor agora é:** {prefix}",
            color=self.bot.get_color(ctx.guild.me)
        )

        await ctx.send(embed=embed)


def setup(bot: BotCore):
    bot.remove_command("help")
    bot.add_cog(Owner(bot))