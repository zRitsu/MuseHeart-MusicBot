import asyncio
import os
import shutil
import json
import traceback
from io import BytesIO
from typing import Union, Optional
from zipfile import ZipFile
import disnake
import dotenv
import wavelink
import psutil
from disnake.ext import commands
from utils.client import BotCore
from utils.db import DBModel
from utils.music.checks import check_voice, check_requester_channel
from utils.music.local_lavalink import run_lavalink
from utils.music.models import LavalinkPlayer
from utils.others import sync_message, chunk_list, EmbedPaginator, CustomContext
from utils.owner_panel import panel_command, PanelView
from utils.music.errors import GenericError
from aiohttp import ClientSession
from config_loader import DEFAULT_CONFIG

os_quote = "\"" if os.name == "nt" else "'"
git_format = f"--pretty=format:{os_quote}%H*****%h*****%s*****%ct{os_quote}"


def format_git_log(data_list: list):
    data = []

    for d in data_list:
        if not d:
            continue
        t = d.split("*****")
        data.append({"commit": t[0], "abbreviated_commit": t[1], "subject": t[2], "timestamp": t[3]})

    return data


def string_to_file(txt, filename="result.txt"):
    if isinstance(txt, dict):
        txt = json.dumps(txt, indent=4, ensure_ascii=False)
    txt = BytesIO(bytes(str(txt), 'utf-8'))
    return disnake.File(fp=txt, filename=filename or "result.txt")


async def run_command(cmd: str):

    p = await asyncio.create_subprocess_shell(
        cmd, stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, stderr = await p.communicate()
    r = ShellResult(p.returncode, stdout, stderr)
    if r.status != 0:
        raise GenericError(f"{r.stderr or r.stdout}\n\nStatus Code: {r.status}")
    return str(r.stdout)


class ShellResult:

    def __init__(self, status: int, stdout: Optional[bytes], stderr: Optional[bytes]):
        self.status = status
        self.stdout = stdout.decode(encoding="utf-8", errors="replace") if stdout is not None else None
        self.stderr = stderr.decode(encoding="utf-8", errors="replace") if stderr is not None else None


class Owner(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.git_init_cmds = [
            "git init",
            f'git remote add origin {self.bot.config["SOURCE_REPO"]}',
            'git fetch origin',
            'git checkout -b main -f --track origin/main'
        ]
        self.owner_view: Optional[PanelView] = None

    def format_log(self, data: list):
        return "\n".join(f"[`{c['abbreviated_commit']}`]({self.bot.pool.remote_git_url}/commit/{c['commit']}) `- "
                         f"{(c['subject'][:40].replace('`', '') + '...') if len(c['subject']) > 39 else c['subject']}` "
                         f"(<t:{c['timestamp']}:R>)" for c in data)

    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.is_owner()
    @commands.command(
        hidden=True, aliases=["gls", "lavalink", "lllist", "lavalinkservers"],
        description="Baixar um arquivo com lista de servidores lavalink para usá-los no sistema de música."
    )
    async def getlavaservers(self, ctx: CustomContext):

        await ctx.defer()

        await self.download_lavalink_serverlist()

        await ctx.send(
            embed=disnake.Embed(
                description="**O arquivo lavalink.ini foi baixado com sucesso!\n"
                            "Será necessário me reiniciar para usar os servidores deste arquivo.**"
            )
        )

    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.command(hidden=True, aliases=["ull", "updatell", "llupdate", "llu"])
    async def updatelavalink(self, ctx: CustomContext):

        async with ctx.typing():

            async with ClientSession() as session:
                async with session.get(self.bot.config["LAVALINK_FILE_URL"]) as r:
                    lavalink_jar = await r.read()
                    with open("./Lavalink.jar", "wb") as f:
                        f.write(lavalink_jar)

        for process in psutil.process_iter():
            try:
                if "Lavalink.jar" in process.cmdline():
                    print(f"{ctx.invoked_with} - Reiniciando lavalink...")
                    process.terminate()
                    run_lavalink(
                        lavalink_file_url=self.bot.config['LAVALINK_FILE_URL'],
                        lavalink_initial_ram=self.bot.config['LAVALINK_INITIAL_RAM'],
                        lavalink_ram_limit=self.bot.config['LAVALINK_RAM_LIMIT'],
                        lavalink_additional_sleep=int(self.bot.config['LAVALINK_ADDITIONAL_SLEEP']),
                    )
            except (psutil.AccessDenied, PermissionError):
                continue
            except Exception:
                traceback.print_exc()

    @commands.is_owner()
    @panel_command(aliases=["rd", "recarregar"], description="Recarregar os módulos.", emoji="🔄",
                   alt_name="Carregar/Recarregar módulos.")
    async def reload(self, ctx: Union[CustomContext, disnake.MessageInteraction]):

        data = self.bot.load_modules()

        for bot in self.bot.pool.bots:

            if bot.user.id != self.bot.user.id:
                bot.load_modules()

        txt = ""

        if data["loaded"]:
            txt += f'**Módulos carregados:** ```ansi\n[0;34m{" [0;37m| [0;34m".join(data["loaded"])}```\n'

        if data["reloaded"]:
            txt += f'**Módulos recarregados:** ```ansi\n[0;32m{" [0;37m| [0;32m".join(data["reloaded"])}```\n'

        if data["error"]:
            txt += f'**Módulos que falharam:** ```ansi\n[0;31m{" [0;37m| [0;31m".join(data["error"])}```\n'

        if not txt:
            txt = "**Nenhum módulo encontrado...**"

        if isinstance(ctx, CustomContext):
            embed = disnake.Embed(colour=self.bot.get_color(ctx.me), description=txt)
            await ctx.send(embed=embed, view=self.owner_view)
        else:
            return txt

    @commands.is_owner()
    @commands.max_concurrency(1, commands.BucketType.default)
    @panel_command(aliases=["up", "atualizar"], description="Atualizar meu code usando o git.",
                   emoji="<:git:944873798166020116>", alt_name="Atualizar Bot")
    async def update(self, ctx: Union[CustomContext, disnake.MessageInteraction], *,
                     opts: str = ""):  # TODO: Rever se há alguma forma de usar commands.Flag sem um argumento obrigatório, ex: --pip.

        out_git = ""

        git_log = []

        force = "--force" in opts

        if shutil.which("poetry"):
            file = "./pyproject.toml"
            use_poetry = True
        else:
            file = "./requirements.txt"
            use_poetry = False

        requirements_old = ""
        try:
            with open(file) as f:
                requirements_old = f.read()
        except:
            pass

        if not os.path.isdir("./.git") or force:

            out_git += await self.cleanup_git(force=force)

        else:

            try:
                await ctx.response.defer()
            except:
                pass

            try:
                await run_command("git reset --hard")
            except:
                pass

            try:
                pull_log = await run_command("git pull --allow-unrelated-histories -X theirs")
                if "Already up to date" in pull_log:
                    raise GenericError("**Já estou com os ultimos updates instalados...**")
                out_git += pull_log

            except GenericError as e:
                raise e

            except Exception as e:

                if "Already up to date" in str(e):
                    raise GenericError("Já estou com os ultimos updates instalados...")

                elif not "Fast-forward" in str(e):
                    out_git += await self.cleanup_git(force=True)

            commit = ""

            for l in out_git.split("\n"):
                if l.startswith("Updating"):
                    commit = l.replace("Updating ", "").replace("..", "...")
                    break

            data = (await run_command(f"git log {commit} {git_format}")).split("\n")

            git_log += format_git_log(data)

        text = "`Será necessário me reiniciar após as alterações.`"

        txt = f"`✅` **[Atualização realizada com sucesso!]({self.bot.pool.remote_git_url}/commits/main)**"

        if git_log:
            txt += f"\n\n{self.format_log(git_log[:10])}"

        txt += f"\n\n`📄` **Log:** ```py\n{out_git[:1000]}```\n{text}"

        if isinstance(ctx, CustomContext):
            embed = disnake.Embed(
                description=txt,
                color=self.bot.get_color(ctx.guild.me)
            )
            await ctx.send(embed=embed, view=self.owner_view)

            self.bot.loop.create_task(self.update_deps(ctx, requirements_old, opts, use_poetry=use_poetry))

        else:
            self.bot.loop.create_task(self.update_deps(ctx, requirements_old, opts, use_poetry=use_poetry))
            return txt

    async def update_deps(self, ctx, original_reqs, opts, use_poetry=False):

        if use_poetry:
            cmd = "poetry install"
            file = "./pyproject.toml"
        else:
            cmd = "pip3 install -U -r requirements.txt --no-cache-dir"
            file = "./requirements.txt"

        if "--pip" in opts:

            embed = disnake.Embed(
                description="**Instalando as dependências.\nPor favor aguarde...**",
                color=self.bot.get_color(ctx.guild.me)
            )

            msg = await ctx.channel.send(embed=embed)

            await run_command(cmd)

            embed.description = "**As dependências foram instaladas com sucesso!**"

            await msg.edit(embed=embed)

        else:

            with open(file) as f:
                requirements_new = f.read()

            if original_reqs != requirements_new:

                txt = ""

                if venv:=os.getenv("VIRTUAL_ENV"):
                    if os.name == "nt":
                        txt += "call " + venv.split('\\')[-1] + " && "
                    else:
                        txt += ". ./" + venv.split('/')[-1] + " && "

                await ctx.send(
                    embed=disnake.Embed(
                        description="**Será necessário atualizar as dependências usando o comando "
                                    "abaixo no terminal/shell:**\n"
                                    f"```sh\n{txt}{cmd}```\nou usar usar o comando: "
                                    f"```\n{disnake.utils.escape_mentions(ctx.prefix)}{ctx.invoked_with} "
                                    f"update --force --pip``` \n"
                                    f"**Nota:** Dependendo da hospedagem (ou que não tenha 150mb de RAM livre) você "
                                    f"deve enviar o arquivo requirements.txt ao invés de usar uma das opções acima.",
                        color=self.bot.get_color(ctx.guild.me)
                    )
                )

    async def cleanup_git(self, force=False):

        if force:
            try:
                shutil.rmtree("./.git")
            except FileNotFoundError:
                pass

        out_git = ""

        for c in self.git_init_cmds:
            try:
                out_git += (await run_command(c)) + "\n"
            except Exception as e:
                out_git += f"{e}\n"

        self.bot.pool.commit = await run_command("git rev-parse HEAD")
        self.bot.pool.remote_git_url = self.bot.config["SOURCE_REPO"][:-4]

        return out_git

    @commands.is_owner()
    @panel_command(aliases=["latest", "lastupdate"], description="Ver minhas atualizações mais recentes.", emoji="📈",
                   alt_name="Ultimas atualizações")
    async def updatelog(self, ctx: Union[CustomContext, disnake.MessageInteraction], amount: int = 10):

        if not os.path.isdir("./.git"):
            raise GenericError("Não há repositorio iniciado no diretório do bot...\nNota: Use o comando update.")

        if not self.bot.pool.remote_git_url:
            self.bot.pool.remote_git_url = self.bot.config["SOURCE_REPO"][:-4]

        git_log = []

        data = (await run_command(f"git log -{amount or 10} {git_format}")).split("\n")

        git_log += format_git_log(data)

        txt = f"🔰 ** | [Atualizações recentes:]({self.bot.pool.remote_git_url}/commits/main)**\n\n" + self.format_log(
            git_log)

        if isinstance(ctx, CustomContext):

            embed = disnake.Embed(
                description=txt,
                color=self.bot.get_color(ctx.guild.me)
            )

            await ctx.send(embed=embed, view=self.owner_view)

        else:
            return txt

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(description="Sincronizar/Registrar os comandos de barra no servidor.", hidden=True)
    async def syncguild(self, ctx: Union[CustomContext, disnake.MessageInteraction]):

        embed = disnake.Embed(
            color=self.bot.get_color(ctx.guild.me),
            description="**Esse comando não é mais necessário ser usado (A sincronização dos comandos agora "
                        f"é automática).**\n\n{sync_message(self.bot)}"
        )

        await ctx.send(embed=embed)

    @commands.is_owner()
    @panel_command(aliases=["sync"], description="Sincronizar os comandos de barra manualmente.",
                   emoji="<:slash:944875586839527444>",
                   alt_name="Sincronizar comandos manualmente.")
    async def synccmds(self, ctx: Union[CustomContext, disnake.MessageInteraction]):

        if self.bot.config["AUTO_SYNC_COMMANDS"] is True:
            raise GenericError(
                f"**Isso não pode ser usado com a sincronização automática ativada...**\n\n{sync_message(self.bot)}")

        await self.bot._sync_application_commands()

        txt = f"**Os comandos de barra foram sincronizados com sucesso!**\n\n{sync_message(self.bot)}"

        if isinstance(ctx, CustomContext):

            embed = disnake.Embed(
                color=self.bot.get_color(ctx.guild.me),
                description=txt
            )

            await ctx.send(embed=embed, view=self.owner_view)

        else:
            return txt

    @commands.command(name="help", aliases=["ajuda"], hidden=True)
    @commands.cooldown(1, 3, commands.BucketType.member)
    async def help_(self, ctx: CustomContext, cmd_name: str = None):

        if cmd_name:

            cmd = self.bot.get_command(cmd_name)

            if not cmd:
                raise GenericError(f"O comando **{cmd_name}** não existe.")

            embed = disnake.Embed(
                color=self.bot.get_color(ctx.guild.me),
                title=f"**Informações do comando: {cmd.name}**"
            )

            if cmd.description:
                embed.add_field(name="Descrição:", value=f"```ldif\n{cmd.description}```", inline=False)

            if cmd.aliases:
                embed.add_field(name="Aliases/Sinônimos:", value="```ldif\n{}```".format(
                    " | ".join(f"{ctx.clean_prefix}{a}" for a in cmd.aliases)), inline=False)

            if cmd.usage:
                embed.add_field(name="Como usar:", value=f" ```ldif\n{ctx.clean_prefix}{cmd.name} {cmd.usage}```",
                                inline=False)

            await ctx.send(embed=embed)
            return

        cmds = [c for c in self.bot.commands if not c.hidden]

        cmds_final = []

        for cmd in cmds:

            txt = ""

            prefix = ctx.prefix if ctx.guild.me.mention != ctx.prefix else ""

            cmd_name = f"**{prefix}{cmd.name}**"

            if cmd.aliases:
                cmd_name += f" ({', '.join(a for a in cmd.aliases)})"

            txt += f" ```ldif\n{cmd.description or 'Sem descrição...'}```"

            txt += "\n"

            cmds_final.append([cmd_name, txt])

        embeds = []

        slash_msg = "`Veja meus comandos de barra usando:` **/**\n\n" if self.bot.slash_commands else ""

        txt_chunked = chunk_list(cmds_final, 9)

        for c, txt_pages in enumerate(txt_chunked):

            embed = disnake.Embed(color=self.bot.get_color(ctx.me), title=f"Meus comandos ({len(cmds)}):",
                                  description=slash_msg)

            embed.set_footer(
                text=f"Página: {c + 1}/{len(txt_chunked)} | para ver informações detalhadas de um comando especifico use: {ctx.clean_prefix}{ctx.invoked_with} comando")

            for cmd_name, cmd_desc in txt_pages:
                embed.add_field(name=cmd_name, value=cmd_desc)

            embeds.append(embed)

        view = EmbedPaginator(ctx, embeds, timeout=60)

        view.message = await ctx.reply(embed=embeds[0], view=view)

        await view.wait()

    @commands.has_guild_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.command(
        aliases=["mudarprefixo", "prefix", "changeprefix"],
        description="Alterar o prefixo do servidor",
        usage="prefixo"
    )
    async def setprefix(self, ctx: CustomContext, prefix: str = None):

        if not prefix:
            raise GenericError("**Você não informou um novo prefixo.**")

        if " " in prefix or len(prefix) > 5:
            raise GenericError("**O prefixo não pode conter espaços ou ter acima de 5 caracteres.**")

        data = await self.bot.get_data(ctx.guild.id, db_name=DBModel.guilds)

        data["prefix"] = prefix
        await self.bot.update_data(ctx.guild.id, data, db_name=DBModel.guilds)

        embed = disnake.Embed(
            description=f"**O prefixo deste servidor agora é:** {disnake.utils.escape_markdown(prefix)}",
            color=self.bot.get_color(ctx.guild.me)
        )

        await ctx.send(embed=embed)

    @commands.is_owner()
    @panel_command(aliases=["expsource", "export", "exs"],
                   description="Exportar minha source para um arquivo zip.", emoji="💾",
                   alt_name="Exportar source/código-fonte.")
    async def exportsource(self, ctx:Union[CustomContext, disnake.MessageInteraction], *, flags: str = ""):

        if not os.path.isdir("./.git"):
            await self.cleanup_git(force=True)

        try:
            env_file = dotenv.dotenv_values("./.env")
        except:
            env_file = {}

        try:
            with open("config.json") as f:
                config_json = json.load(f)
        except FileNotFoundError:
            config_json = {}

        SECRETS = dict(DEFAULT_CONFIG)
        SECRETS.update({"TOKEN": ""})

        for env in os.environ:
            if env.lower().startswith(("token_bot_", "test_guilds_", "lavalink_node_")):
                SECRETS[env] = os.environ[env]

        for i in SECRETS:
            try:
                SECRETS[i] = os.environ[i]
            except KeyError:
                continue

        SECRETS.update(config_json)
        SECRETS.update(env_file)

        if not os.path.isfile("./.env-temp"):
            shutil.copyfile("./.env-example", "./.env-temp")

        for i in SECRETS:
            if not isinstance(SECRETS[i], str):
                SECRETS[i] = str(SECRETS[i]).lower()
            dotenv.set_key("./.env-temp", i, SECRETS[i])

        if flags.endswith(("--externalservers", "-externalservers", "--llservers", "-llservers", "--lls", "-lls")):
            await self.download_lavalink_serverlist()

        filelist = await run_command("git ls-files --others --exclude-standard --cached")

        try:
            os.remove("./source.zip")
        except:
            pass

        with ZipFile("./source.zip", 'a') as zipf:

            for f in filelist.split("\n"):
                if f == ".env-temp":
                    zipf.write('./.env-temp', './.env')
                else:
                    zipf.write(f"./{f}")

        os.remove("./.env-temp")

        try:
            embed = disnake.Embed(
                description="**Não envie o arquivo source.zip ou o arquivo .env pra ninguém e muito cuidado ao postar "
                            "print's do conteudo do arquivo .env e não adicione esse arquivo em locais públicos como "
                            "github, repl.it, glitch.com, etc.**",
                color=self.bot.get_color(ctx.guild.me))
            embed.set_footer(text="Por medida de segurança, esta mensagem será deletada em 2 minutos.")

            msg = await ctx.author.send(
                embed=embed,
                file=disnake.File("./source.zip", filename=f"{self.bot.user}_source.zip"),
                delete_after=120
            )

            os.remove("./source.zip")

        except disnake.Forbidden:
            os.remove("./source.zip")
            raise GenericError("Seu DM está desativado!")

        if isinstance(ctx, CustomContext):
            await ctx.send(
                embed=disnake.Embed(
                    description=f"**O arquivo [source.zip]({msg.jump_url}) foi enviado no seu privado.**",
                    color=self.bot.get_color(ctx.guild.me)
                )
            )
        else:
            return f"Arquivo [source.zip]({msg.jump_url}) foi enviado com sucesso no seu DM."

    @commands.is_owner()
    @commands.command(hidden=True)
    async def cleardm(self, ctx: CustomContext, amount: int = 20):

        counter = 0

        async with ctx.typing():

            async for msg in ctx.author.history(limit=int(amount)):
                if msg.author.id == self.bot.user.id:
                    await msg.delete()
                    await asyncio.sleep(0.5)
                    counter += 1

        if not counter:
            raise GenericError(f"**Nenhuma mensagem foi deletada de {amount} verificada(s)...**")

        if counter == 1:
            txt = "**Uma mensagem foi deletada do seu DM.**"
        else:
            txt = f"**{counter} mensagens foram deletadas do seu DM.**"

        await ctx.send(embed=disnake.Embed(description=txt, colour=self.bot.get_color(ctx.guild.me)))

    @commands.Cog.listener("on_button_click")
    async def close_shell_result(self, inter: disnake.MessageInteraction):

        if inter.data.custom_id != "close_shell_result":
            return

        if not await self.bot.is_owner(inter.author):
            return await inter.send("**Apenas meu dono pode usar este botão!**", ephemeral=True)

        await inter.response.edit_message(
            content="```ini\n🔒 - [Shell Fechado!] - 🔒```",
            attachments=None,
            view=None,
            embed=None
        )

    @commands.is_owner()
    @commands.command(aliases=["sh"], hidden=True)
    async def shell(self, ctx: CustomContext, *, command: str):

        if command.startswith('```') and command.endswith('```'):
            if command[4] != "\n":
                command = f"```\n{command[3:]}"
            if command[:-4] != "\n":
                command = command[:-3] + "\n```"
            command = '\n'.join(command.split('\n')[1:-1])
        else:
            command = command.strip('` \n')

        try:
            async with ctx.typing():
                result = await run_command(command)
        except GenericError as e:
            kwargs = {}
            if len(e.text) > 2000:
                kwargs["file"] = string_to_file(e.text, filename="error.txt")
            else:
                kwargs["content"] = f"```py\n{e.text}```"

            try:
                await ctx.author.send(**kwargs)
                await ctx.message.add_reaction("⚠️")
            except disnake.Forbidden:
                traceback.print_exc()
                raise GenericError(
                    "**Ocorreu um erro (verifique os logs/terminal ou libere seu DM para o próximo "
                    "resultado ser enviado diretamente no seu DM).**"
                )

        else:

            kwargs = {}
            if len(result) > 2000:
                kwargs["file"] = string_to_file(result, filename=f"shell_result_{ctx.message.id}.txt")
            else:
                kwargs["content"] = f"```py\n{result}```"

            await ctx.reply(
                components=[
                    disnake.ui.Button(label="Fechar Shell", custom_id="close_shell_result", emoji="♻️")
                ],
                mention_author=False,
                **kwargs
            )

    @check_voice()
    @commands.command(description='inicializar um player no servidor.', aliases=["spawn", "sp", "spw", "smn"])
    async def summon(self, ctx: CustomContext):

        try:
            self.bot.music.players[ctx.guild.id]  # type ignore
            raise GenericError("**Já há um player iniciado no servidor.**")
        except KeyError:
            pass

        node: wavelink.Node = self.bot.music.get_best_node()

        if not node:
            raise GenericError("**Não há servidores de música disponível!**")

        guild_data = await self.bot.get_data(ctx.guild.id, db_name=DBModel.guilds)

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

            stage_perms = channel.permissions_for(ctx.guild.me)
            if stage_perms.manage_permissions:
                await ctx.guild.me.edit(suppress=False)
            elif stage_perms.request_to_speak:
                await ctx.guild.me.request_to_speak()

            await asyncio.sleep(1.5)

        await player.process_next()

    async def cog_check(self, ctx: CustomContext) -> bool:
        return await check_requester_channel(ctx)

    async def cog_load(self) -> None:
        self.owner_view = PanelView(self.bot)

    async def download_lavalink_serverlist(self):
        async with ClientSession() as session:
            async with session.get(self.bot.config["LAVALINK_SERVER_LIST"]) as r:
                ini_file = await r.read()
                with open("lavalink.ini", "wb") as f:
                    f.write(ini_file)


def setup(bot: BotCore):
    bot.remove_command("help")
    bot.add_cog(Owner(bot))
