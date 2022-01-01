from __future__ import annotations
import asyncio
import pprint
import time
import aiohttp
import disnake
import tornado.ioloop
import tornado.web
import tornado.websocket
import logging
import json
import traceback
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from utils.client import BotCore
    from utils.music.models import LavalinkPlayer, YTDLPlayer


logging.getLogger('tornado.access').disabled = True


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("olá :)")
        # self.render("index.html") #será implementado futuramente...

users_ws = {}
bots_ws = {}

class WebSocketHandler(tornado.websocket.WebSocketHandler):

    bots: List[BotCore]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.users_ws = users_ws
        self.bots_ws = bots_ws
        for b in self.bots:
            b.ws_server = self

        self.user_id: Optional[int] = None
        self.is_bot: bool = False

    #def initialize(self):
    #    self.user_id: Optional[int] = None
    #    self.is_bot: bool = False

    def on_message(self, message):

        self.data = json.loads(message)

        user_id = self.data.get("user_id")
        bot_id = self.data.get("bot_id")

        if not user_id:

            if not bot_id:
                stats = {
                    "op": "error",
                    "message": "Desconectado por falta de id de usuario..."
                }
                print(f"desconectando: por falta de id de usuario {self.request.remote_ip}\nDados: {self.data}")
                self.write_message(json.dumps(stats))
                self.close()

            for u in self.users_ws.values():
                try:
                    u.write_message(json.dumps(self.data))
                except Exception as e:
                    print(f"Erro ao processar dados do rpc para o user {user_id}: {repr(e)}")

            return

        self.user_id = int(user_id)

        self.is_bot = self.data.pop("bot", False)

        if self.is_bot:
            print(f"Nova conexão - Bot: {user_id} {self.request.remote_ip}")
            try:
                del self.bots_ws[user_id]
            except:
                pass
            self.bots_ws[user_id] = self
            return

        print(f"Nova conexão - User: {user_id}")

        try:
            del self.users_ws[user_id]
        except:
            pass
        self.users_ws[user_id] = self

        if not self.bots_ws:
            print(f"Não há conexões ws com bots pra processar rpc do user: {user_id}")
            return

        for b in self.bots_ws.values():
            try:
                b.write_message(json.dumps(self.data))
            except Exception as e:
                print(f"Erro ao processar dados do rpc para o bot {user_id}: {repr(e)}")


    def check_origin(self, origin: str):
        return True

    def on_close(self):

        if not self.user_id:
            print(f"Conexão Finalizada - IP: {self.request.remote_ip}")
            return

        if self.is_bot:

            # método temporário pra corrigir um problema ao logar múltiplos bots no mesmo ip.
            for i in list(bots_ws):

                try:
                    b = bots_ws[i]
                except KeyError:
                    continue

                if self.request.remote_ip != b.request.remote_ip:
                    continue

                print(f"Conexão Finalizada - Bot: {i}")

                try:
                    del self.bots_ws[i]
                except:
                    pass

                data = {"op": "close", "bot_id": i}
                for i, w in self.users_ws.items():
                    try:
                        w.write_message(data)
                        print("op sent")
                    except Exception as e:
                        print(f"Erro ao processar dados do rpc para o user {i}: {repr(e)}")

        else:

            print(f"Conexão Finalizada - User: {self.user_id}")

            try:
                del self.users_ws[self.user_id]
            except:
                pass


class WSClient:

    def __init__(self, url: str, bots=None):
        self.bots: list = bots or []
        self.url: str = url
        self.connection = None
        self.ws_loop_task = None
        self.backoff = 7
        self.session = aiohttp.ClientSession()

    async def connect(self):
        self.connection = await self.session.ws_connect(self.url)
        self.backoff = 7
        print(f"RPC Server Conectado: {self.url}")

        for bot in self.bots:
            for player in bot.music.players.values():
                voice_channel = player.vc.channel
                bot.loop.create_task(player.process_rpc(voice_channel))

    @property
    def is_connected(self):
        return self.connection and not self.connection.closed

    async def send(self, data):

        if not self.is_connected:
            try:
                await self.connect()
                self.backoff = 7
            except Exception as e:
                print(f"Falha ao processar rpc: {repr(e)}")
                print(f"Reconectando ao server RPC em {self.backoff} segundos.")
                await asyncio.sleep(self.backoff)
                self.backoff *= 1.5
                await self.send(data)

        await self.connection.send_json(data)

    async def ws_loop(self):

        while True:

            try:

                if not self.is_connected:
                    await self.connect()

                message = await self.connection.receive()

                if not message.data:
                    #await asyncio.sleep(self.backoff)
                    #self.backoff *= 1.5
                    continue

                data = json.loads(message.data)

                pprint.pprint(data)

                user_id = int(data.get("user_id", 0))

                if not user_id:
                    continue

                op = data.get("op")

                if op == "rpc_update":

                    player: Optional[LavalinkPlayer, YTDLPlayer] = None

                    voice_channel: Optional[disnake.VoiceChannel] = None

                    for bot in self.bots:

                        for p in bot.music.players.values():
                            vc = p.bot.get_channel(p.channel_id)
                            if user_id in [m.id for m in vc.members]:
                                player = p
                                voice_channel = vc
                                break

                        if player and voice_channel:

                            if [m.id for m in voice_channel.members if m.id == user_id]:
                                bot.loop.create_task(player.process_rpc(voice_channel))

            except aiohttp.WSServerHandshakeError:
                print(f"Servidor offline, tentando conectar novamente ao server RPC em {self.backoff} segundos.")
            except Exception:
                traceback.print_exc()
                print(f"Reconectando ao server RPC em {self.backoff} segundos.")

            await asyncio.sleep(self.backoff)
            self.backoff *= 1.5


async def run_ws_client(url, bots):
    ws = WSClient(url, bots=bots)
    for bot in bots:
        bot.ws_client = ws
    await ws.ws_loop()


def run_app(bots: list):
    WebSocketHandler.bots = bots
    app = tornado.web.Application([
        (r'/', IndexHandler),
        (r'/ws', WebSocketHandler),
    ])

    app.listen(8080)


if __name__ == '__main__':
    run_app([])
    time.sleep(3)
    run_ws_client("http://localhost:8080", [])
    tornado.ioloop.IOLoop.instance().start()
