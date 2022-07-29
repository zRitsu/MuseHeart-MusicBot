from __future__ import annotations
import asyncio
import json
import logging
import traceback
from typing import TYPE_CHECKING, Optional
from os import environ
import aiohttp
import disnake
import tornado.ioloop
import tornado.web
import tornado.websocket


if TYPE_CHECKING:
    from utils.client import BotPool


logging.getLogger('tornado.access').disabled = True

users_ws = []
bots_ws = []


class IndexHandler(tornado.web.RequestHandler):

    def initialize(self, bots: list, ws_url: str):
        self.bots = bots
        self.ws_url = ws_url
        self.text = ""

    async def prepare(self):

        cells = ""

        for bot in self.bots:
            await bot.wait_until_ready()
            try:
                avatar = bot.user.avatar.with_static_format("png").url
            except AttributeError:
                avatar = bot.user.default_avatar.with_static_format("png").url

            cells += f"<tr><td><img src=\"{avatar}\" width=128 weight=128></img></td>\n" \
                     f"<td style=\"padding-top: 10px ; padding-bottom: 10px; padding-left: 10px; padding-right: 10px\">" \
                     f"Adicionar:<br><a href=\"{disnake.utils.oauth_url(bot.user.id, permissions=disnake.Permissions(bot.config['INVITE_PERMISSIONS']), scopes=('bot', 'applications.commands'))}\" " \
                     f"target=\"_blank\">{bot.user}</a></td></tr>"

        if cells:

            style = """<style>
            table, th, td {
                border:1px solid black;
                text-align: center;
            }
            </style>"""

            self.text = f"<p style=\"font-size:30px\">Bots Disponíveis:</p>{style}\n<table>{cells}</table>"

    def get(self):
        self.write(f"{self.text or 'olá :]'}<br><p><a href=\"https://github.com/zRitsu/DC-MusicBot-RPC/releases\" "
                   f"target=\"_blank\">Baixe o app de rich presence aqui.</a></p><br>Link para adicionar no app de RPC "
                   f"abaixo:<p style=\"color:blue\">{self.ws_url}</p><br>")
        # self.render("index.html") #será implementado futuramente...


class WebSocketHandler(tornado.websocket.WebSocketHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_ids: list = []
        self.bot_ids: list = []

    def on_message(self, message):

        data = json.loads(message)

        ws_id = data.get("user_ids")
        bot_id = data.get("bot_id")

        if not ws_id:

            if not bot_id:
                print(f"desconectando: por falta de id de usuario {self.request.remote_ip}\nDados: {data}")
                self.close(code=1005, reason="Desconectando: por falta de ids de usuario")
                return

            for ws in users_ws:
                try:
                    ws.write_message(json.dumps(data))
                except Exception as e:
                    print(f"Erro ao processar dados do rpc para os users [{', '.join(ws.user_ids)}]: {repr(e)}")

            return

        is_bot = data.pop("bot", False)

        if is_bot:
            print(f"Nova conexão - Bot: {ws_id} {self.request.remote_ip}")
            self.bot_ids = ws_id
            bots_ws.append(self)
            return

        self.user_ids = ws_id

        print("\n".join(f"Nova conexão - User: {u} | {data}" for u in self.user_ids))

        for w in bots_ws:
            try:
                w.write_message(json.dumps(data))
            except Exception as e:
                print(f"Erro ao processar dados do rpc para os bot's {w.bot_ids}: {repr(e)}")

        users_ws.append(self)


    def check_origin(self, origin: str):
        return True

    def on_close(self):

        if self.user_ids:
            print("\n".join(f"Conexão Finalizada - User: {u}" for u in self.user_ids))
            users_ws.remove(self)
            return

        if not self.bot_ids:
            print(f"Conexão Finalizada - IP: {self.request.remote_ip}")

        else:

            print(f"Conexão Finalizada - Bot ID's: {self.bot_ids}")

            data = {"op": "close", "bot_id": self.bot_ids}

            for w in users_ws:
                try:
                    w.write_message(data)
                except Exception as e:
                    print(f"Erro ao processar dados do rpc para os usuários: [{', '.join(w.user_ids)}]: {repr(e)}")

        bots_ws.remove(self)


class WSClient:

    def __init__(self, url: str, pool: BotPool):
        self.url: str = url
        self.pool = pool
        self.connection = None
        self.backoff: int = 7
        self.ready: bool  = False
        self.data: dict = {}
        self.session: Optional[aiohttp.ClientSession] = None

    async def connect(self):

        if self.ready:
            return

        if not self.session:
            self.session = aiohttp.ClientSession()

        self.connection = await self.session.ws_connect(self.url, heartbeat=30)

        self.backoff = 7
        #print(f"RPC client conectado: {self.bot.user} - {self.url}")
        print("RPC client conectado, sincronizando rpc dos bots...")

        for bot in self.pool.bots:

            await bot.wait_until_ready()

        await self.send({"user_ids": [b.user.id for b in self.pool.bots], "bot": True})

        print("RPC client - Os dados de rpc dos bots foram sincronizados com sucesso.")

        self.ready = True

    @property
    def is_connected(self):
        return self.connection and not self.connection.closed

    async def send(self, data: dict):

        self.data = data

        if not self.is_connected:
            return

        try:
            await self.connection.send_json(self.data)
        except Exception:
            traceback.print_exc()

    async def ws_loop(self):

        while True:

            try:

                if not self.is_connected:
                    await self.connect()

            except Exception as e:
                if isinstance(e, aiohttp.WSServerHandshakeError):
                    print(f"Falha ao conectar no servidor RPC, tentando novamente em {int(self.backoff)} segundo(s).")
                else:
                    print(f"Conexão com servidor RPC perdida - Reconectando em {int(self.backoff)} segundo(s).")

                self.ready = False
                await asyncio.sleep(self.backoff)
                self.backoff *= 2.5
                continue

            message = await self.connection.receive()

            if message.type is aiohttp.WSMsgType.CLOSED:
                print(f"RPC Websocket Closed: {message.extra}\nReconnecting in {self.backoff}s")
                self.ready = False
                await asyncio.sleep(self.backoff)
                continue

            data = json.loads(message.data)

            users: list = data.get("user_ids")

            if not users:
                continue

            op = data.get("op")

            if op == "rpc_update":

                for bot in self.pool.bots:
                    for player in bot.music.players.values():
                        vc: disnake.VoiceChannel = player.bot.get_channel(player.channel_id)
                        vc_user_ids = [i for i in vc.voice_states if i in users]
                        if vc_user_ids:
                            bot.loop.create_task(player.process_rpc(vc))
                            for i in vc_user_ids:
                                users.remove(i)


def run_app(bots: Optional[list] = None, ws_url = f"http://0.0.0.0:{environ.get('PORT', 8080)}/ws"):

    try:
        # repl.it stuff
        ws_url = f"wss://{environ['REPL_SLUG']}.{environ['REPL_OWNER']}.repl.co:443/ws"
    except KeyError:
        pass

    bots = bots or []

    app = tornado.web.Application([
        (r'/', IndexHandler, {'bots': bots, 'ws_url': ws_url}),
        (r'/ws', WebSocketHandler),
    ])

    app.listen(environ.get("PORT", 8080))


def start(bots: Optional[list] = None):
    run_app(bots)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    start()
