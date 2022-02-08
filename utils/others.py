from __future__ import annotations
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from utils.client import BotCore


class ProgressBar:

    def __init__(
            self,
            position: Union[int, float],
            total: Union[int, float],
    ):
        self.start = int(100 * position / total / 10)
        self.end = 9 - self.start


def sync_message(bot: BotCore):
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot" \
                 f"%20applications.commands "

    return f"`Caso os comandos de barra não apareçam,` [`clique aqui`]({invite_url}) `para me permitir " \
           "criar comandos de barra no servidor.`\n\n" \
           "`Nota: Em alguns casos os comandos de barra podem demorar até uma hora pra aparecer/atualizar em todos " \
           "os servidores. Caso queira usar os comandos de barra imediatamente neste servidor você terá que " \
           f"me expulsar do servidor e em seguida me adicionar novamente através deste` [`link`]({invite_url})..."
