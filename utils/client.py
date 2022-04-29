from __future__ import annotations
import asyncio
import datetime
from importlib import import_module
import aiohttp
from disnake.ext import commands
import disnake
from typing import Optional, Union
from web_app import WSClient
from .music.models import music_mode
from utils.db import MongoDatabase, LocalDatabase
from asyncspotify import Client as SpotifyClient
import os
import traceback

from utils.others import sync_message
from .owner_panel import PanelView


class BotCore(commands.AutoShardedBot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: Optional[aiohttp.ClientError] = None
        self.db: Optional[LocalDatabase, MongoDatabase] = None
        self.config = kwargs.pop('config', {})
        self.default_prefix = kwargs.pop("default_prefix", "!!!")
        self.spotify: Optional[SpotifyClient] = kwargs.pop('spotify', None)
        self.music = music_mode(self)
        self.session = aiohttp.ClientSession()
        self.color = kwargs.pop("embed_color", None)
        self.bot_ready = False
        self.player_skins = {}
        self.default_skin = self.config.get("DEFAULT_SKIN", "default")
        self.load_skins()
        self.commit = kwargs.get("commit", "N/A")
        self.remote_git_url = kwargs.get("remote_git_url", "")
        self.ws_client = WSClient(self.config["RPC_SERVER"], bot=self)
        self.uptime = disnake.utils.utcnow()
        self.env_owner_ids = set()
        self.dm_cooldown = commands.CooldownMapping.from_cooldown(rate=2, per=30, type=commands.BucketType.member)

        for i in self.config["OWNER_IDS"].split("||"):

            if not i:
                continue

            try:
                self.env_owner_ids.add(int(i))
            except ValueError:
                print(f"Owner_ID inválido: {i}")


    def load_skins(self):

        for skin in os.listdir("./utils/music/skins"):

            if not skin.endswith(".py"):
                continue

            try:
                skin_file = import_module(f"utils.music.skins.{skin[:-3]}")

                if not hasattr(skin_file, "load"):
                    print(f"Skin ignorada: {skin} | Função load() não configurada/encontrada...")
                    continue

                self.player_skins[skin[:-3]] = skin_file.load

            except Exception:
                print(f"Falha ao carregar skin: {traceback.format_exc()}")

        if not self.default_skin in self.player_skins:
            self.default_skin = "default"


    def check_skin(self, skin: str):

        if skin is None or skin == "default" or skin not in self.player_skins:
            return self.default_skin

        return skin


    async def is_owner(self, user: Union[disnake.User, disnake.Member]) -> bool:

        if user.id in self.env_owner_ids:
            return True

        return await super().is_owner(user)


    async def can_send_message(self, message: disnake.Message):

        if not message.channel.permissions_for(message.guild.me).send_messages:

            print(f"Can't send message in: {message.channel.name} [{message.channel.id}] (Missing permissions)")

            bucket = self.dm_cooldown.get_bucket(message)
            retry_after = bucket.update_rate_limit()

            if retry_after:
                return

            try:
                await message.author.send(f"Não tenho permissão para enviar mensagens no canal {message.channel.mention}...")
            except disnake.HTTPException:
                pass

        return True


    async def on_message(self, message: disnake.Message):

        if not self.bot_ready:
            return

        if not message.guild:
            return

        if message.content in (f"<@{self.user.id}>",  f"<@!{self.user.id}>"):

            if not await self.can_send_message(message):
                return

            embed = disnake.Embed(color=self.get_color(message.guild.me))

            if not (await self.is_owner(message.author)):

                prefix = (await self.get_prefix(message))[-1]

                embed.description = f"**Olá {message.author.mention}.\n" \
                                    f"Para ver todos os meus comandos use: /**"

                if message.author.guild_permissions.administrator:
                    embed.description += f"\n\n{sync_message(self)}"

                else:
                    embed.description += "\n\n`Caso os meus comandos de barra não estejam aparecendo. Peça para " \
                                         "um administrador me marcar para seguir alguns procedimentos para corrigir" \
                                         " esse problema.`"

                if not self.config["INTERACTION_COMMAND_ONLY"]:
                    embed.description += f"\n\nTambém tenho comandos de texto por prefixo.\n" \
                                        f"Para ver todos os meus comandos de texto use **{prefix}help**\n"

                view = None

            else:

                view = PanelView(self)
                embed.title = "PAINEL DE CONTROLE."
                embed.set_footer(text="Clique em uma tarefa que deseja executar.")
                view.embed = embed

            await message.reply(embed=embed, view=view)
            return

        ctx: commands.Context = await self.get_context(message)

        if not ctx.valid:
            return

        if not await self.can_send_message(message):
            return

        await self.invoke(ctx)


    def get_color(self, me: disnake.Member):

        if self.color:
            return self.color

        if me.color.value == 0:
            return 0x2F3136

        return me.color


    async def on_application_command_autocomplete(self, inter: disnake.ApplicationCommandInteraction):

        if not self.bot_ready:
            return

        await super().on_application_command_autocomplete(inter)


    async def on_application_command(self, inter: disnake.ApplicationCommandInteraction):

        if not inter.guild:
            await inter.send("Meus comandos não podem ser usados no DM.\n"
                             "Use em algum servidor que estou presente.")
            return

        if not self.bot_ready:
            await inter.send("O bot ainda não está pronto para uso.", ephemeral=True)
            return

        if self.config["COMMAND_LOG"]:
            print(f"cmd log: [user: {inter.author} - {inter.author.id}] - [guild: {inter.guild.name} - {inter.guild.id}]"
                  f" - [cmd: {inter.data.name}] "
                  f"{datetime.datetime.utcnow().strftime('%d/%m/%Y - %H:%M:%S')} (UTC)\n" + ("-"*15))

        await super().on_application_command(inter)


    def load_modules(self, bot_name: str = None):

        modules_dir = "modules"

        load_status = {
            "reloaded": [],
            "loaded": [],
            "error": []
        }

        if not bot_name:
            bot_name = self.user

        for item in os.walk(modules_dir):
            files = filter(lambda f: f.endswith('.py'), item[-1])
            for file in files:
                filename, _ = os.path.splitext(file)
                module_filename = os.path.join(modules_dir, filename).replace('\\', '.').replace('/', '.')
                try:
                    self.reload_extension(module_filename)
                    print(f"{'=' * 48}\n[OK] {bot_name} - {filename}.py Recarregado.")
                    load_status["reloaded"].append(f"{filename}.py")
                except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
                    try:
                        self.load_extension(module_filename)
                        print(f"{'=' * 48}\n[OK] {bot_name} - {filename}.py Carregado.")
                        load_status["loaded"].append(f"{filename}.py")
                    except Exception:
                        print((f"{'=' * 48}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename} | Erro:"
                               f"\n{traceback.format_exc()}"))
                        load_status["error"].append(f"{filename}.py")
                except Exception:
                    print((f"{'=' * 48}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename} | Erro:"
                      f"\n{traceback.format_exc()}"))
                    load_status["error"].append(f"{filename}.py")

        print(f"{'=' * 48}")

        for c in self.slash_commands:
            if (desc:=len(c.description)) > 100:
                raise Exception(f"A descrição do comando {c.name} excedeu a quantidade de caracteres permitido "
                                f"no discord (100), quantidade atual: {desc}")

        return load_status