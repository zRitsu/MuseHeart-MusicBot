from __future__ import annotations
from importlib import import_module

import aiohttp
from disnake.ext import commands
import disnake
from typing import Optional

from web_app import WSClient
from .music.models import music_mode
from .music.spotify import spotify_client
from utils.db import Database, LocalDatabase
import os
import traceback

class BotCore(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session: Optional[aiohttp.ClientError] = None
        self.db: Optional[LocalDatabase, Database] = None
        self.spotify = spotify_client()
        self.config = kwargs.pop('config', {})
        self.music = music_mode(self)
        self.session = aiohttp.ClientSession()
        self.color = kwargs.pop("embed_color", None)
        self.bot_ready = False
        self.player_skins = {}
        self.default_skin = self.config.get("DEFAULT_SKIN", "default")
        self.load_skins()
        self.commit = kwargs.get("commit", "N/A")
        self.remote_git_url = kwargs.get("remote_git_url", "")
        self.default_prefix = kwargs.get("default_prefix", None)
        self.ws_client = WSClient(self.config["RPC_SERVER"], bot=self)
        self.uptime = disnake.utils.utcnow()

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

        if not skin in self.player_skins:
            return "default"

        return skin

    async def on_message(self, message: disnake.Message):

        if message.content == f"<@{self.user.id}>" or message.content == f"<@!{self.user.id}>":

            prefix = (await self.get_prefix(message))[-1]

            embed = disnake.Embed(
                description=f"Olá, meu prefixo atual é: **{prefix}**\n"
                            f"Caso queira ver meus comandos de texto use **{prefix}help**\n",
                color=self.get_color(message.guild.me)
            )

            if self.slash_commands:
                embed.description += f"Veja também meus comandos de barra usando: **/**"

            await message.reply(embed=embed)
            return

        await self.process_commands(message)


    def get_color(self, me: disnake.Member):

        if self.color:
            return self.color

        if me.color.value == 0:
            return 0x2F3136

        return me.color

    async def on_application_command(self, inter: disnake.ApplicationCommandInteraction):

        if not self.bot_ready:
            await inter.send("O bot ainda não está pronto para uso.", ephemeral=True)
            return

        if self.db:
            # inter.user_data = await bot.db.get_data(inter.author.id, db_name="users")
            inter.guild_data = await self.db.get_data(inter.guild.id, db_name="guilds")
        else:
            # inter.user_data = None
            inter.guild_data = None

        await self.process_application_commands(inter)

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
                    print(f"{'=' * 50}\n[OK] {bot_name} - {filename}.py Recarregado.")
                    load_status["reloaded"].append(filename)
                except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
                    try:
                        self.load_extension(module_filename)
                        print(f"{'=' * 50}\n[OK] {bot_name} - {filename}.py Carregado.")
                        load_status["loaded"].append(filename)
                    except Exception:
                        print((f"{'=' * 50}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename} | Erro:"
                               f"\n{traceback.format_exc()}"))
                        load_status["error"].append(filename)
                except Exception:
                    print((f"{'=' * 50}\n[ERRO] {bot_name} - Falha ao carregar/recarregar o módulo: {filename} | Erro:"
                      f"\n{traceback.format_exc()}"))
                    load_status["error"].append(filename)

        print(f"{'=' * 50}")

        return load_status
