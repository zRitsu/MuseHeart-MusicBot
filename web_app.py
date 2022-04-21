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
    from utils.client import BotCore


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
                     f"Adicionar:<br><a href=\"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&" \
                     f"permissions=397287680080&scope=bot%20applications.commands\" target=\"_blank\">{bot.user}" \
                     f"</a></td></tr>"

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
        self.user_ids = []
        self.bot_id = None

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
            self.bot_id = ws_id
            bots_ws.append(self)
            return

        self.user_ids = ws_id

        print("\n".join(f"Nova conexão - User: {u} | {data}" for u in self.user_ids))

        for w in bots_ws:
            try:
                w.write_message(json.dumps(data))
            except Exception as e:
                print(f"Erro ao processar dados do rpc para o bot {w.bot_id}: {repr(e)}")

        users_ws.append(self)


    def check_origin(self, origin: str):
        return True

    def on_close(self):

        if self.user_ids:
            print("\n".join(f"Conexão Finalizada - User: {u}" for u in self.user_ids))
            users_ws.remove(self)
            return

        if not self.bot_id:
            print(f"Conexão Finalizada - IP: {self.request.remote_ip}")

        else:

            print(f"Conexão Finalizada - Bot: {self.bot_id}")

            data = {"op": "close", "bot_id": self.bot_id}

            for w in users_ws:
                try:
                    w.write_message(data)
                except Exception as e:
                    print(f"Erro ao processar dados do rpc para os usuários: [{', '.join(w.user_ids)}]: {repr(e)}")

        bots_ws.remove(self)


class WSClient:

    def __init__(self, url: str, bot: BotCore):
        self.bot: BotCore = bot
        self.url: str = url
        self.connection = None
        self.backoff: int = 7
        self.ready: bool  = False
        self.data: dict = {}

    async def connect(self):

        if self.ready:
            return

        await self.bot.wait_until_ready()

        if not self.bot.session:
            self.bot.session = aiohttp.ClientSession()

        self.connection = await self.bot.session.ws_connect(self.url, heartbeat=30)

        self.backoff = 7
        #print(f"RPC client conectado: {self.bot.user} - {self.url}")
        print(f"{self.bot.user} - RPC client conectado")

        await self.send({"user_ids": self.bot.user.id, "bot": True})

        for player in self.bot.music.players.values():
            self.bot.loop.create_task(player.process_rpc(player.guild.me.voice.channel))

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
                    print(f"{self.bot.user} - Servidor offline, tentando conectar novamente ao server RPC em {int(self.backoff)} segundos.")
                else:
                    print(f"{self.bot.user} - Reconectando ao server RPC em {int(self.backoff)} segundos.")

                self.ready = False
                await asyncio.sleep(self.backoff)
                self.backoff *= 2.5
                continue

            message = await self.connection.receive()

            if message.type is aiohttp.WSMsgType.CLOSED:
                print(f"{self.bot.user} - RPC Websocket Closed: {message.extra}")
                self.ready = False
                await asyncio.sleep(self.backoff)
                continue

            data = json.loads(message.data)

            users: list = data.get("user_ids")

            if not users:
                continue

            op = data.get("op")

            if op == "rpc_update":

                for player in self.bot.music.players.values():
                    vc: disnake.VoiceChannel = player.bot.get_channel(player.channel_id)
                    vc_user_ids = [m.id for m in vc.members if m.id in users]
                    if vc_user_ids:
                        self.bot.loop.create_task(player.process_rpc(vc))
                        for i in vc_user_ids:
                            users.remove(i)


def run_app(bots: Optional[list] = None, ws_url = f"http://localhost:{environ.get('PORT', 8080)}/ws"):

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

    app.listen(8080)


def start(bots: Optional[list] = None):
    run_app(bots)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    start()
