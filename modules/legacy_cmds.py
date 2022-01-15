import os
import subprocess
import json
import disnake
from disnake.ext import commands
import traceback
from utils.client import BotCore
from utils.music.errors import GenericError


def run_command(cmd):
    return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()


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

    @commands.is_owner()
    @commands.command(aliases=["up", "atualizar"],
                      description="Atualizar o code do bot usando git (apenas para meu dono).")
    async def update(self, ctx: commands.Context, usepip="no"):

        if usepip not in ["pip", "no"]:
            raise GenericError(f"Opção inválida: {usepip}")

        if not os.path.isdir("./.git"):
            raise GenericError("Não há pasta .git no diretório do bot.")

        await ctx.message.add_reaction("⏲️")

        try:
            run_command("git reset --hard")
        except Exception as e:
            raise GenericError(f"Ocorreu um erro no git reset.\nCode: {e.returncode} | {e.output}")

        with open("requirements.txt") as f:
            original_req = f.read()

        try:
            out_git = run_command("git pull --allow-unrelated-histories -X theirs")
        except Exception as e:
            raise GenericError(f"Ocorreu um erro no git pull:\nCode: {e.returncode} | {e.output}")

        if "Already up to date" in out_git:
            raise GenericError("Já estou com os ultimos updates instalados...")

        commit = ""

        for l in out_git.split("\n"):
            if l.startswith("Updating"):
                commit = l.replace("Updating ", "").replace("..", "...")
                break

        git_format = "--pretty=format:\"{%n  'commit': '%H',%n  'abbreviated_commit': '%h',%n  'tree': '%T',%n  " \
                     "'abbreviated_tree': '%t',%n  'parent': '%P',%n  'abbreviated_parent': '%p',%n  'refs': '%D',%n  " \
                     "'encoding': '%e',%n  'subject': '%s',%n  'sanitized_subject_line': '%f',%n  'body': '%b',%n  " \
                     "'commit_notes': '%N',%n  'verification_flag': '%G?',%n  'signer': '%GS',%n  'signer_key': " \
                     "'%GK',%n  'author': {%n    'name': '%aN',%n    'email': '%aE',%n    'date': '%aD'%n  }," \
                     "%n  'commiter': {%n    'name': '%cN',%n    'email': '%cE',%n    'date': '%cD'%n  }%n},\""
        git_log = json.loads("[" + run_command(f"git log {commit} {git_format}").replace("'", "\"")[:-1] + "]")

        with open("requirements.txt") as f:
            new_req = f.read()

        if usepip == "pip":
            subprocess.check_output("pip3 install -U -r requirements.txt", shell=True, text=True)

        text = "`Reinicie o bot após as alterações.`"

        if original_req != new_req:
            text += "\n`Nota: Será necessário atualizar as dependências.`"

        txt = "\n".join(
            f"[`{c['abbreviated_commit']}`]({self.bot.remote_git_url}/commit/{c['commit']}) `- {(c['subject'][:60] + '...') if len(c['subject']) > 59 else c['subject']}`"
            for c in git_log[:10])

        embed = disnake.Embed(
            description=f"{txt}\n\n`📄` **Log:** ```py\n{out_git[:1000]}```{text}",
            title="`✅` Atualização realizada com sucesso!",
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
            description="**Este comando não é mais necessário ser usado (A sincronização dos comandos agora é automático).**\n\n" \
                        f"`Caso os comandos de barra não apareçam,` [`clique aqui`]({invite_url}) `para me permitir "
                        f"permissão de criar comandos de barra no servidor.`\n\n" \
                        "`Nota: Em alguns casos os comandos de barra podem demorar até uma hora pra aparecer em todos "
                        "os servidores. Caso queira usar os comandos de barra imediatamente neste servidor você terá que "
                        "me expulsar do servidor e em seguida me adicionar novamente através deste` [`link`]({invite_url})..."
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

            embed.description += "\n"

        if self.bot.slash_commands:
            embed.description += "`Veja meus comandos de barra usando:` **/**"

        await ctx.reply(embed=embed)


def setup(bot: BotCore):
    bot.remove_command("help")
    bot.add_cog(Owner(bot))
