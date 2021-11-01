from disnake.ext import commands
from wavelink import Client
from .music.spotify import spotify_client
from utils.db import Database, LocalDatabase
import os
import traceback


class BotCore(commands.Bot):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        mongo = kwargs.get('mongo')
        self.db = Database(token=mongo, name=kwargs.pop("db_name", "botdiscord")) if mongo else LocalDatabase(self)
        self.wavelink = Client(bot=self)
        self.tests = None
        self.spotify = spotify_client()
        self.config = kwargs.pop('config', {})

    def load_modules(self):
        print('-' * 30)
        for filename in os.listdir('./modules'):
            if not filename.endswith('.py'):
                continue
            try:
                self.reload_extension(f'modules.{filename[:-3]}')
                print(f"[OK] Módulo [{filename}] recarregado.\n{'-' * 30}")
            except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
                try:
                    self.load_extension(f'modules.{filename[:-3]}')
                    print(f"[OK] Módulo [{filename}] carregado.\n{'-' * 30}")
                except:
                    print(f"[ERRO] Falha ao carregar o módulo: [{filename}] | Erro:"
                          f"\n{traceback.format_exc()}\n{'-' * 30}")
            except:
                print(f"Falha ao carregar/recarregar o módulo: {filename} | Erro:"
                      f"\n{traceback.format_exc()}\n{'-' * 30}\n")
