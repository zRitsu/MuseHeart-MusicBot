import aiohttp
from disnake.ext import commands
import disnake
from typing import Optional
from .music.spotify import spotify_client
from utils.db import Database, LocalDatabase
import os
import traceback
from utils.music.models import music_mode


class BotCore(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mongo = kwargs.get('mongo')
        self.session: Optional[aiohttp.ClientError] = None
        self.db = Database(token=mongo, name=kwargs.pop("db_name", "botdiscord")) if mongo else LocalDatabase(self)
        self.tests = None
        self.spotify = spotify_client()
        self.config = kwargs.pop('config', {})
        self.music = music_mode(self)
        self.session = aiohttp.ClientSession()

    async def on_application_command(self, inter: disnake.ApplicationCommandInteraction):

        if self.db:
            # inter.user_data = await bot.db.get_data(inter.author.id, db_name="users")
            inter.guild_data = await self.db.get_data(inter.guild.id, db_name="guilds")
        else:
            # inter.user_data = None
            inter.guild_data = None

        await self.process_application_commands(inter)

    def load_modules(self):

        modules_dir = "modules"

        load_status = {
            "reloaded": [],
            "loaded": [],
            "error": []
        }

        for item in os.walk(modules_dir):
            files = filter(lambda f: f.endswith('.py'), item[-1])
            for file in files:
                filename, _ = os.path.splitext(file)
                module_filename = os.path.join(modules_dir, filename).replace('\\', '.').replace('/', '.')
                try:
                    self.reload_extension(module_filename)
                    print(f"{'=' * 50}\n[OK] {filename}.py Recarregado.")
                    load_status["reloaded"].append(filename)
                except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
                    try:
                        self.load_extension(module_filename)
                        print(f"{'=' * 50}\n[OK] {filename}.py Carregado.")
                        load_status["loaded"].append(filename)
                    except Exception:
                        print((f"{'=' * 50}\n[ERRO] Falha ao carregar/recarregar o módulo: {filename} | Erro:"
                               f"\n{traceback.format_exc()}"))
                        load_status["error"].append(filename)
                except Exception:
                    print((f"{'=' * 50}\n[ERRO] Falha ao carregar/recarregar o módulo: {filename} | Erro:"
                      f"\n{traceback.format_exc()}"))
                    load_status["error"].append(filename)

        print(f"{'=' * 50}")

        return load_status
