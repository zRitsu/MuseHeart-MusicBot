from __future__ import annotations

import asyncio
import json
import logging
import pprint
import time
import traceback
from typing import TYPE_CHECKING, Optional

import aiohttp
import disnake
import tornado.ioloop
import tornado.web
import tornado.websocket

if TYPE_CHECKING:
    from utils.music.models import LavalinkPlayer
    from utils.client import BotCore


logging.getLogger('tornado.access').disabled = True


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.write("olá :)")
        # self.render("index.html") #será implementado futuramente...

users_ws = {}
bots_ws = {}

class WebSocketHandler(tornado.websocket.WebSocketHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_id: Optional[int] = None
        self.is_bot: bool = False

    def on_message(self, message):

        data = json.loads(message)

        user_id = data.get("user_id")
        bot_id = data.get("bot_id")

        if not user_id:

            if not bot_id:
                stats = {
                    "op": "error",
                    "message": "Desconectado por falta de id de usuario..."
                }
                print(f"desconectando: por falta de id de usuario {self.request.remote_ip}\nDados: {data}")
                self.write_message(json.dumps(stats))
                self.close()

            for u, ws in users_ws.items():
                try:
                    ws.write_message(json.dumps(data))
                except Exception as e:
                    print(f"Erro ao processar dados do rpc para o user {u}: {repr(e)}")

            return

        self.user_id = int(user_id)

        self.is_bot = data.pop("bot", False)

        if self.is_bot:
            print(f"Nova conexão - Bot: {user_id} {self.request.remote_ip}")
            try:
                bots_ws[user_id].close()
            except:
                pass
            try:
                del bots_ws[user_id]
            except:
                pass
            bots_ws[user_id] = self
            return

        print(f"Nova conexão - User: {user_id} | {data}")

        try:
            del users_ws[user_id]
        except:
            pass
        users_ws[user_id] = self

        if not bots_ws:
            print(f"Não há conexões ws com bots pra processar rpc do user: {user_id}")
            return

        for i, b in bots_ws.items():
            try:
                b.write_message(json.dumps(data))
                print(f"dados [{data}] enviados ao bot: {i}")
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
                    del bots_ws[i]
                except:
                    pass

                data = {"op": "close", "bot_id": i}

                for i, w in users_ws.items():
                    try:
                        w.write_message(data)
                    except Exception as e:
                        print(f"Erro ao processar dados do rpc para o user {i}: {repr(e)}")

        else:

            print(f"Conexão Finalizada - User: {self.user_id}")

            try:
                del users_ws[self.user_id]
            except:
                pass


class WSClient:

    def __init__(self, url: str, bot: BotCore):
        self.bot: BotCore = bot
        self.url: str = url
        self.connection = None
        self.backoff = 7
        self.session = aiohttp.ClientSession()
        self.ready = False

    async def connect(self):

        if self.ready:
            return

        self.connection = await self.session.ws_connect(self.url, heartbeat=30)
        self.backoff = 7
        #print(f"RPC client conectado: {self.bot.user} - {self.url}")
        print(f"{self.bot.user} - RPC client conectado")

        await self.bot.wait_until_ready()
        await self.send({"user_id": self.bot.user.id, "bot": True})

        for player in self.bot.music.players.values():
            self.bot.loop.create_task(player.process_rpc(player.guild.me.voice.channel))

        self.ready = True

        await self.ws_loop()

    @property
    def is_connected(self):
        return self.connection and not self.connection.closed

    async def send(self, data):

        if not self.is_connected:
            try:
                await self.connect()
                self.backoff = 7
            except Exception as e:
                #print(f"Falha ao processar RPC: {repr(e)}")
                print(f"{self.bot.user} - Falha ao processar RPC!")
                print(f"{self.bot.user} - Reconectando ao server RPC em {self.backoff} segundos.")
                await asyncio.sleep(self.backoff)
                self.backoff *= 1.5
                await self.send(data)

        try:
            await self.connection.send_json(data)
        except:
            self.ready = False
            await self.send(data)

    async def ws_loop(self):

        while True:

            try:

                if not self.is_connected:
                    await self.connect()
                    return

                message = await self.connection.receive()

                if not message.data:
                    await asyncio.sleep(self.backoff)
                    self.backoff *= 1.10
                    continue

                data = json.loads(message.data)

                user_id = int(data.get("user_id", 0))

                if not user_id:
                    continue

                op = data.get("op")

                if op == "rpc_update":

                    player: Optional[LavalinkPlayer] = None

                    voice_channel: Optional[disnake.VoiceChannel] = None

                    for p in self.bot.music.players.values():
                        vc = p.bot.get_channel(p.channel_id)
                        if user_id in [m.id for m in vc.members]:
                            player = p
                            voice_channel = vc
                            break

                    if player and voice_channel:

                        if [m.id for m in voice_channel.members if m.id == user_id]:
                            self.bot.loop.create_task(player.process_rpc(voice_channel))

            except aiohttp.WSServerHandshakeError:
                print(f"{self.bot.user} - Servidor offline, tentando conectar novamente ao server RPC em {self.backoff} segundos.")
            except Exception:
                #traceback.print_exc()
                print(f"{self.bot.user} - Reconectando ao server RPC em {self.backoff} segundos.")

            self.ready = False
            await asyncio.sleep(self.backoff)
            self.backoff *= 1.5


def run_ws_client(bot: BotCore):
    bot.loop.create_task(bot.ws_client.ws_loop())


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
