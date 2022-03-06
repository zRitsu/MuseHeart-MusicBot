import asyncio
import os
import shutil
import subprocess
import json
from io import BytesIO
from typing import Union
import disnake
import wavelink
from disnake.ext import commands
from utils.client import BotCore
from utils.music.checks import check_voice
from utils.music.models import LavalinkPlayer
from utils.others import sync_message
from utils.owner_panel import panel_command
from utils.music.errors import GenericError


os_quote = "\"" if os.name == "nt" else "'"
git_format = f"--pretty=format:{os_quote}%H*****%h*****%s{os_quote}"

def replaces(txt):

    if os.name == "nt":
        return txt.replace("\"", f"\\'").replace("'", "\"")

    return txt.replace("\"", f"\\\"").replace("'", "\"")

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
    @panel_command(aliases=["rd", "recarregar"], description="Recarregar os módulos.", emoji="🔄",
                   alt_name="Carregar/Recarregar módulos.")
    async def reload(self, ctx: Union[commands.Context, disnake.MessageInteraction]):

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

        if isinstance(ctx, commands.Context):
            embed = disnake.Embed(colour=self.bot.get_color(ctx.me), description=txt)
            await ctx.send(embed=embed)
        else:
            return txt


    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.default)
    @panel_command(aliases=["up", "atualizar"], description="Atualizar meu code usando o git.",
                   emoji="<:git:944873798166020116>", alt_name="Atualizar Bot")
    async def update(self, ctx: Union[commands.Context, disnake.MessageInteraction], *,
                     opts: str = ""): #TODO: Rever se há alguma forma de usar commands.Flag sem um argumento obrigatório, ex: --pip.

        out_git = ""

        git_log = []

        force = "--force" in opts

        if not os.path.isdir("./.git") or force:

            if force:
                shutil.rmtree("./.git")

            for c in self.git_init_cmds:
                out_git += run_command(c) + "\n"

            self.bot.commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
            self.bot.remote_git_url = self.bot.config["SOURCE_REPO"][:-4]

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

            data = run_command(f"git log {commit} {git_format}").split("\n")

            for d in data:
                t = d.split("*****")
                git_log.append({"commit": t[0], "abbreviated_commit": t[1], "subject": t[2]})

        text = "`Reinicie o bot após as alterações.`"

        if "--pip" in opts:
            subprocess.check_output("pip3 install -U -r requirements.txt", shell=True, text=True)

        elif "requirements.txt" in text:
            text += "\n`Nota: Será necessário atualizar as dependências.`"

        txt = "`✅` **Atualização realizada com sucesso!**"

        if git_log:
            txt += f"\n\n{self.format_log(git_log[:10])}"

        txt += f"\n\n`📄` **Log:** ```py\n{out_git[:1000]}```{text}"

        if isinstance(ctx, commands.Context):
            embed = disnake.Embed(
                description=txt,
                color=self.bot.get_color(ctx.guild.me)
            )
            await ctx.send(embed=embed)

        else:
            return txt


    @commands.is_owner()
    @panel_command(aliases=["latest", "lastupdate"], description="Ver minhas atualizações mais recentes.", emoji="📈",
                   alt_name="Ultimas atualizações")
    async def updatelog(self, ctx: Union[commands.Context, disnake.MessageInteraction], amount: int = 10):

        if not os.path.isdir("./.git"):
            raise GenericError("Não há repositorio iniciado no diretório do bot...\nNota: Use o comando update.")

        if not self.bot.remote_git_url:
            self.bot.remote_git_url = self.bot.config["SOURCE_REPO"][:-4]

        git_log = []

        data = run_command(f"git log -{amount or 10} {git_format}").split("\n")

        for d in data:
            t = d.split("*****")
            git_log.append({"commit": t[0], "abbreviated_commit": t[1], "subject": t[2]})

        txt = f"🔰 ** | Atualizações recentes:**\n\n" + self.format_log(git_log)

        if isinstance(ctx, commands.Context):

            embed = disnake.Embed(
                description=txt,
                color=self.bot.get_color(ctx.guild.me)
            )

            await ctx.send(embed=embed)

        else:
            return txt

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(description="Sincronizar/Registrar os comandos de barra no servidor.", hidden=True)
    async def syncguild(self, ctx: Union[commands.Context, disnake.MessageInteraction]):

        embed = disnake.Embed(
            color=self.bot.get_color(ctx.guild.me),
            description="**Esse comando não é mais necessário ser usado (A sincronização dos comandos agora "
                        f"é automática).**\n\n{sync_message(self.bot)}"
        )

        await ctx.send(embed=embed)


    @commands.is_owner()
    @panel_command(aliases=["sync"], description="Sincronizar os comandos de barra manualmente.", emoji="<:slash:944875586839527444>",
                   alt_name="Sincronizar comandos manualmente.")
    async def synccmds(self, ctx: Union[commands.Context, disnake.MessageInteraction]):

        if self.bot.config["AUTO_SYNC_COMMANDS"] is True:
            raise GenericError(f"**Isso não pode ser usado com a sincronização automática ativada...**\n\n{sync_message(self.bot)}")

        await self.bot._sync_application_commands()

        txt = f"**Os comandos de barra foram sincronizados com sucesso!**\n\n{sync_message(self.bot)}"

        if isinstance(ctx, commands.Context):

            embed = disnake.Embed(
                color=self.bot.get_color(ctx.guild.me),
                description=txt
            )

            await ctx.send(embed=embed)

        else:
            return txt


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


    @commands.is_owner()
    @panel_command(aliases=["export"], description="Exportar minhas configs/secrets/env pra um arquivo no DM.", emoji="🔐",
                   alt_name="Exportar env/config")
    async def exportenv(self, ctx: Union[commands.Context, disnake.MessageInteraction]):

        fp = BytesIO(bytes(json.dumps(self.bot.config, indent=4), 'utf-8'))
        try:
            embed=disnake.Embed(
                    description="**Não divulge/mostre esse arquivo pra ninguém e muito cuidado ao postar print's "
                                "do conteudo dele e não adicione esse arquivo em locais públicos como github, repl.it, "
                                "glitch.com, etc!**",
                    color=self.bot.get_color(ctx.guild.me))
            embed.set_footer(text="Por medida de segurança, esta mensagem será deletada em 60 segundos.")
            await ctx.author.send(embed=embed,
                file=disnake.File(fp=fp, filename="config.json"), delete_after=60)

        except disnake.Forbidden:
            raise GenericError("Seu DM está desativado!")

        if isinstance(ctx, commands.Context):
            await ctx.message.add_reaction("👍")
        else:
            return "Arquivo de configuração enviado com sucesso no seu DM."


    @check_voice()
    @commands.command(description='inicializar um player no servidor.', aliases=["spawn", "sp", "spw", "smn"])
    async def summon(self, ctx: commands.Context):

        try:
            self.bot.music.players[ctx.guild.id] #type ignore
            raise GenericError("**Já há um player iniciado no servidor.**")
        except KeyError:
            pass

        node: wavelink.Node = self.bot.music.get_best_node()

        if not node:
            raise GenericError("**Não há servidores de música disponível!**")

        guild_data = await self.bot.db.get_data(ctx.guild.id, db_name="guilds")

        static_player = guild_data['player_controller']

        try:
            channel = ctx.guild.get_channel(int(static_player['channel'])) or ctx.channel
            message = await channel.fetch_message(int(static_player.get('message_id')))
        except (KeyError, TypeError):
            channel = ctx.channel
            message = None

        player: LavalinkPlayer = self.bot.music.get_player(
            node_id=node.identifier,
            guild_id=ctx.guild.id,
            cls=LavalinkPlayer,
            requester=ctx.author,
            guild=ctx.guild,
            channel=channel,
            message=message,
            static=bool(static_player['channel'])
        )

        channel = ctx.author.voice.channel

        await player.connect(channel.id)

        self.bot.loop.create_task(ctx.message.add_reaction("👍"))

        while not ctx.guild.me.voice:
            await asyncio.sleep(1)

        if isinstance(channel, disnake.StageChannel):

            stage_perms =  channel.permissions_for(ctx.guild.me)
            if stage_perms.manage_permissions:
                await ctx.guild.me.edit(suppress=False)
            elif stage_perms.request_to_speak:
                await ctx.guild.me.request_to_speak()

            await asyncio.sleep(1.5)

        await player.process_next()


def setup(bot: BotCore):
    bot.remove_command("help")
    bot.add_cog(Owner(bot))