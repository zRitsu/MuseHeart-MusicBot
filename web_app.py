from __future__ import annotations

import pprint
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


class WebSocketHandler(tornado.websocket.WebSocketHandler):

    bots: List[BotCore]

    def initialize(self):
        self.user_id: Optional[int] = None

    def on_message(self, message):
        data = json.loads(message)
        user_id = int(data.get("user_id", 0))

        if not user_id:
            stats = {
                "op": "error",
                "message": "Desconectado por falta de id de usuario..."
            }
            print(f"desconectando: por falta de id de usuario {self.request.remote_ip}")
            self.write_message(json.dumps(stats))
            self.close()
            return

        print(f"Nova conexão - User: {user_id}")

        self.user_id = user_id

        user = {
            "ws": self,
            "ip": self.request.remote_ip,
            "last": {},
        }

        for bot in self.bots:

            player: Optional[LavalinkPlayer, YTDLPlayer] = None

            try:
                del bot.ws_users[user_id]
            except KeyError:
                pass

            bot.ws_users[user_id] = user
            voice_channel: Optional[disnake.VoiceChannel] = None

            for p in bot.music.players.values():
                vc = p.bot.get_channel(p.channel_id)
                if user_id in [m.id for m in vc.members]:
                    player = p
                    voice_channel = vc
                    break

            if player and voice_channel:

                if [m.id for m in voice_channel.members if m.id == user_id]:
                    bot.loop.create_task(player.process_rpc(voice_channel))


    def check_origin(self, origin: str):
        return True

    def on_close(self):
        if not self.user_id:
            print(f"Conexão Finalizada - IP: {self.request.remote_ip}")
        else:
            print(f"Conexão Finalizada - User: {self.user_id}")
            for bot in self.bots:
                try:
                    del bot.ws_users[self.user_id]
                except KeyError:
                    continue


def run_app(bots: list):
    WebSocketHandler.bots = bots
    app = tornado.web.Application([
        (r'/', IndexHandler),
        (r'/ws', WebSocketHandler),
    ])

    app.listen(8080)


if __name__ == '__main__':
    run_app([])
    tornado.ioloop.IOLoop.instance().start()
