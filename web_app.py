# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import html
import json
import logging
from os import environ
from traceback import print_exc
from typing import TYPE_CHECKING, Optional

import aiohttp
import disnake
import tornado.ioloop
import tornado.web
import tornado.websocket
from packaging import version

from config_loader import load_config

if TYPE_CHECKING:
    from utils.client import BotPool

logging.getLogger('tornado.access').disabled = True

users_ws = {}
bots_ws = []

minimal_version = version.parse("2.6.1")


def _escape(value) -> str:
    return html.escape(str(value), quote=True)


def _render_bot_card(bot, guild_count: int, invite_url: str) -> str:
    avatar = bot.user.display_avatar.replace(size=256, static_format="png").url
    guild_label = "servidor" if guild_count == 1 else "servidores"

    return f"""
    <article class="group relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-5 shadow-2xl shadow-black/20 backdrop-blur-xl transition duration-300 hover:-translate-y-1 hover:border-cyan-300/30 hover:bg-white/10">
      <div class="absolute inset-0 bg-gradient-to-br from-cyan-400/10 via-transparent to-fuchsia-400/10 opacity-70"></div>
      <div class="relative flex flex-col gap-4 sm:flex-row sm:items-center">
        <img
          src="{_escape(avatar)}"
          alt="Avatar de {_escape(bot.user)}"
          class="h-20 w-20 rounded-2xl border border-white/10 object-cover shadow-lg shadow-cyan-950/30"
        >
        <div class="min-w-0 flex-1">
          <div class="mb-2 flex flex-wrap items-center gap-2">
            <span class="inline-flex items-center rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-slate-200">
              Online
            </span>
            <span class="inline-flex items-center rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-xs font-semibold text-emerald-100">
              {_escape(guild_count)} {guild_label}
            </span>
          </div>
          <h3 class="truncate text-xl font-semibold text-white">{_escape(bot.user)}</h3>
          <p class="mt-1 text-sm text-slate-300">Pronto para entrar no seu servidor e começar a tocar.</p>
        </div>
        <a
          href="{_escape(invite_url)}"
          rel="nofollow noopener noreferrer"
          target="_blank"
          class="inline-flex items-center justify-center rounded-2xl bg-cyan-300 px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
        >
          Adicionar bot
        </a>
      </div>
    </article>
    """


def _render_pending_card(identifier: str) -> str:
    return f"""
    <article class="rounded-3xl border border-amber-300/20 bg-amber-300/10 p-5 backdrop-blur-xl">
      <div class="flex items-start gap-3">
        <div class="mt-1 h-3 w-3 rounded-full bg-amber-300 shadow-[0_0_18px_rgba(252,211,77,0.9)]"></div>
        <div>
          <p class="text-sm font-semibold uppercase tracking-[0.24em] text-amber-100">Inicializando</p>
          <h3 class="mt-2 text-lg font-semibold text-white">{_escape(identifier)}</h3>
          <p class="mt-1 text-sm text-slate-200">Recarregue a página em instantes para verificar se ele já ficou disponível.</p>
        </div>
      </div>
    </article>
    """


def _render_failed_row(identifier: str, exception: str) -> str:
    return f"""
    <tr class="border-t border-white/10">
      <td class="px-4 py-3 font-medium text-white">{_escape(identifier)}</td>
      <td class="px-4 py-3 text-sm leading-6 text-rose-100">{_escape(exception)}</td>
    </tr>
    """


def _build_index_page(
    *,
    headline_message: str,
    ready_bots: list[str],
    pending_bots: list[str],
    failed_bots: list[str],
    rpc_auth_enabled: bool,
    default_prefix: str,
    commit: str,
    remote_git_url: str,
) -> str:
    intro_block = ""
    if headline_message:
        intro_block = f"""
        <section class="rounded-3xl border border-cyan-300/20 bg-cyan-300/10 p-5 text-slate-100 shadow-lg shadow-cyan-950/20 backdrop-blur-xl">
          <p class="text-sm font-medium leading-7">{headline_message}</p>
        </section>
        """

    pending_section = ""
    if pending_bots:
        pending_section = f"""
        <section class="space-y-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-semibold uppercase tracking-[0.3em] text-amber-200">Aquecendo os motores</p>
              <h2 class="mt-2 text-2xl font-semibold text-white">Bots em inicialização</h2>
            </div>
            <span class="rounded-full border border-amber-300/20 bg-amber-300/10 px-3 py-1 text-sm font-medium text-amber-100">
              {len(pending_bots)} pendente(s)
            </span>
          </div>
          <div class="grid gap-4">
            {''.join(pending_bots)}
          </div>
        </section>
        """

    failed_section = ""
    if failed_bots:
        failed_section = f"""
        <section class="rounded-3xl border border-rose-300/20 bg-rose-300/10 p-6 shadow-lg shadow-rose-950/20 backdrop-blur-xl">
          <div class="mb-4">
            <p class="text-sm font-semibold uppercase tracking-[0.3em] text-rose-100">Atenção</p>
            <h2 class="mt-2 text-2xl font-semibold text-white">Falha ao inicializar alguns bots</h2>
            <p class="mt-2 text-sm leading-6 text-rose-100">
              Os seguintes tokens configurados na ENV/SECRET/.env falharam durante a inicialização.
            </p>
          </div>
          <div class="overflow-hidden rounded-2xl border border-white/10">
            <table class="min-w-full border-collapse bg-slate-950/30">
              <thead class="bg-white/5 text-left text-xs uppercase tracking-[0.24em] text-slate-300">
                <tr>
                  <th class="px-4 py-3">Identificador</th>
                  <th class="px-4 py-3">Erro</th>
                </tr>
              </thead>
              <tbody>
                {''.join(failed_bots)}
              </tbody>
            </table>
          </div>
        </section>
        """

    rpc_auth_note = ""
    if rpc_auth_enabled:
        rpc_auth_note = """
        <p class="mt-4 text-sm leading-6 text-slate-300">
          Não esqueça de gerar o token no comando <span class="font-semibold text-white">/rich_presence</span> para configurar o app RPC.
        </p>
        """

    commit_block = ""
    if commit:
        commit_block = f"""
        <div class="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p class="text-xs uppercase tracking-[0.24em] text-slate-400">Commit atual</p>
          <a
            href="{_escape(remote_git_url)}/commit/{_escape(commit)}"
            target="_blank"
            rel="noopener noreferrer"
            class="mt-2 inline-flex text-sm font-semibold text-cyan-200 transition hover:text-cyan-100"
          >
            {_escape(commit[:7])}
          </a>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Painel do Music Bot</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <script>
        tailwind.config = {{
          theme: {{
            extend: {{
              fontFamily: {{
                sans: ["Segoe UI", "system-ui", "sans-serif"],
              }},
              boxShadow: {{
                glow: "0 0 0 1px rgba(255,255,255,0.05), 0 24px 80px rgba(15,23,42,0.45)",
              }},
            }},
          }},
        }};
      </script>
      <style>
        body {{
          background:
            radial-gradient(circle at top, rgba(34, 211, 238, 0.16), transparent 28%),
            radial-gradient(circle at 85% 10%, rgba(217, 70, 239, 0.16), transparent 24%),
            linear-gradient(160deg, #020617 0%, #0f172a 52%, #111827 100%);
        }}

        .grid-fade {{
          background-image:
            linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px);
          background-size: 30px 30px;
          mask-image: linear-gradient(to bottom, rgba(0,0,0,0.65), transparent);
        }}
      </style>
    </head>
    <body class="min-h-screen text-slate-100 antialiased">
      <div class="pointer-events-none absolute inset-0 overflow-hidden">
        <div class="grid-fade absolute inset-x-0 top-0 h-80"></div>
        <div class="absolute left-[8%] top-24 h-40 w-40 rounded-full bg-cyan-400/10 blur-3xl"></div>
        <div class="absolute right-[10%] top-12 h-56 w-56 rounded-full bg-fuchsia-400/10 blur-3xl"></div>
      </div>

      <main class="relative mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-8 px-4 py-8 sm:px-6 lg:px-8 lg:py-12">
        <section class="overflow-hidden rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl sm:p-8 lg:p-10">
          <div class="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <div class="max-w-3xl">
              <p class="text-sm font-semibold uppercase tracking-[0.34em] text-cyan-200">Music Bot Control Panel</p>
              <h1 class="mt-4 max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                Seus bots de música, prontos para convidar e sincronizar.
              </h1>
              <p class="mt-4 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
                Gerencie convites, acompanhe o status da inicialização e obtenha o endereço do app de Rich Presence do Discord em uma interface mais clara e responsiva.
              </p>
            </div>

            <div class="grid gap-3 sm:grid-cols-2">
              <div class="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p class="text-xs uppercase tracking-[0.24em] text-slate-400">Bots disponíveis</p>
                <p class="mt-2 text-3xl font-semibold text-white">{len(ready_bots)}</p>
              </div>
              <div class="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p class="text-xs uppercase tracking-[0.24em] text-slate-400">Prefixo padrão</p>
                <p class="mt-2 text-3xl font-semibold text-white">{_escape(default_prefix)}</p>
              </div>
              {commit_block}
            </div>
          </div>
        </section>

        {intro_block}

        <section class="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.8fr)]">
          <div class="space-y-6">
            <section class="space-y-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold uppercase tracking-[0.3em] text-emerald-200">Bots disponíveis</p>
                  <h2 class="mt-2 text-2xl font-semibold text-white">Convites prontos para uso</h2>
                </div>
                <span class="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-sm font-medium text-emerald-100">
                  {len(ready_bots)} online
                </span>
              </div>
              <div class="grid gap-4">
                {''.join(ready_bots) or '<div class="rounded-3xl border border-white/10 bg-white/5 p-6 text-slate-300">Nenhum bot disponível no momento.</div>'}
              </div>
            </section>

            {pending_section}
            {failed_section}
          </div>

          <aside class="space-y-6">
            <section class="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-glow backdrop-blur-xl">
              <p class="text-sm font-semibold uppercase tracking-[0.3em] text-cyan-200">Discord Rich Presence RPC</p>
              <h2 class="mt-3 text-2xl font-semibold text-white">Conecte o app de Rich Presence do Discord</h2>
              <p class="mt-3 text-sm leading-6 text-slate-300">
                Baixe o app RPC usado no Rich Presence do Discord, copie o endereço do websocket gerado automaticamente abaixo e finalize a configuração em poucos passos.
              </p>
              <div class="mt-5 flex flex-col gap-3">
                <a
                  href="https://github.com/zRitsu/DC-MusicBot-RPC/releases"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center justify-center rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-100"
                >
                  Baixar app de Rich Presence do Discord
                </a>
                <div class="rounded-2xl border border-cyan-300/20 bg-slate-950/60 p-4">
                  <p class="text-xs uppercase tracking-[0.24em] text-slate-400">URL websocket</p>
                  <p id="rpc-url" class="mt-2 break-all font-mono text-sm text-cyan-200">Carregando...</p>
                </div>
                {rpc_auth_note}
              </div>
            </section>

            <section class="rounded-3xl border border-white/10 bg-white/5 p-6 backdrop-blur-xl">
              <p class="text-sm font-semibold uppercase tracking-[0.3em] text-fuchsia-200">Resumo rápido</p>
              <ul class="mt-4 space-y-3 text-sm leading-6 text-slate-300">
                <li>Use o botão de convite para adicionar um bot ao seu servidor.</li>
                <li>Se algum bot estiver iniciando, esta página mostra o status na próxima recarga.</li>
                <li>Falhas de token aparecem destacadas para facilitar a correção da configuração.</li>
              </ul>
            </section>
          </aside>
        </section>
      </main>

      <script>
        (function setRpcUrl() {{
          const element = document.getElementById("rpc-url");
          if (!element) return;

          const url = new URL(window.location.href);
          const protocol = url.protocol === "https:" ? "wss:" : "ws:";
          let host = url.host;

          if (host.endsWith(".replit.dev")) {{
            host = host.replace(".replit.dev", ".replit.dev:443");
          }}

          element.textContent = `${{protocol}}//${{host}}/ws`;
        }})();
      </script>
    </body>
    </html>
    """

class IndexHandler(tornado.web.RequestHandler):

    def initialize(self, pool: Optional[BotPool] = None, message: str = "", config: dict = None):
        self.message = message
        self.pool = pool
        self.config = config

    async def prepare(self):

        bots = [asyncio.create_task(bot.wait_until_ready()) for bot in self.pool.bots if not bot.is_ready()]

        if bots:
            self.write("")
            await self.flush()
            await asyncio.wait(bots, timeout=7)

    async def get(self):

        try:
            killing_state = self.pool.killing_state
        except:
            killing_state = False

        if killing_state is True:
            self.write(
                "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>Painel do Music Bot</title>"
                "<script src='https://cdn.tailwindcss.com'></script></head>"
                "<body class='min-h-screen bg-slate-950 text-white'>"
                "<main class='mx-auto flex min-h-screen max-w-3xl items-center justify-center px-6'>"
                "<section class='rounded-3xl border border-amber-300/20 bg-amber-300/10 p-8 text-center shadow-2xl backdrop-blur-xl'>"
                "<p class='text-sm font-semibold uppercase tracking-[0.28em] text-amber-100'>Manutenção</p>"
                "<h1 class='mt-4 text-3xl font-semibold sm:text-4xl'>A aplicação será reiniciada em breve...</h1>"
                "</section></main></body></html>"
            )
            return

        message_html = ""

        if self.message:
            message_html = "<br>".join(_escape(line) for line in self.message.splitlines())

        failed_bots = []
        pending_bots = []
        ready_bots = []

        kwargs = {}

        for identifier, exception in self.pool.failed_bots.items():
            failed_bots.append(_render_failed_row(identifier, exception))

        for bot in sorted(self.pool.bots, key=lambda b: len(b.guilds)):

            if bot.is_ready():
                guilds = len(bot.guilds)
                invite_url = disnake.utils.oauth_url(
                    bot.user.id,
                    permissions=disnake.Permissions(bot.config['INVITE_PERMISSIONS']),
                    scopes=('bot', 'applications.commands'),
                    **kwargs,
                )
                ready_bots.append(
                    _render_bot_card(bot, guilds, invite_url)
                )
            else:
                pending_bots.append(_render_pending_card(bot.identifier))

        self.write(
            _build_index_page(
                headline_message=message_html,
                ready_bots=ready_bots,
                pending_bots=pending_bots,
                failed_bots=failed_bots,
                rpc_auth_enabled=self.config["ENABLE_RPC_AUTH"],
                default_prefix=self.pool.config['DEFAULT_PREFIX'],
                commit=self.pool.commit,
                remote_git_url=self.pool.remote_git_url,
            )
        )


class WebSocketHandler(tornado.websocket.WebSocketHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_ids: list = []
        self.bot_ids: list = []
        self.token = ""
        self.blocked = False
        self.auth_enabled = False

    def on_message(self, message):

        data = json.loads(message)

        ws_id = data.get("user_ids")
        bot_id = data.get("bot_id")
        token = data.pop("token", "") or ""
        app_version = version.parse(data.get("version", "0"))
        self.auth_enabled = data.pop("auth_enabled", False)

        if not ws_id:

            if not bot_id:
                print(f"desconectando: por falta de id de usuario {self.request.remote_ip}\nDados: {data}")
                self.write_message(json.dumps({"op": "disconnect", "reason": "Desconectando por falta de ids de usuario"}))
                self.close(code=4200)
                return

            try:

                if self.auth_enabled:

                    if users_ws[data["user"]].token != token:

                        if users_ws[data["user"]].blocked:
                            return

                        data.update(
                            {
                                "op": "exception",
                                "message": "token inválido! Por via das dúvidas gere um novo token usando o comando no "
                                           "bot: /rich_presence."
                            }
                        )

                        for d in ("token", "track", "info"):
                            data.pop(d, None)

                        users_ws[data["user"]].blocked = True

                    else:
                        users_ws[data["user"]].blocked = False

                users_ws[data["user"]].write_message(json.dumps(data))

            except KeyError:
                pass
            except Exception as e:
                print(f"Erro ao processar dados do rpc para o user [{data['user']}]: {repr(e)}")

            return

        is_bot = data.pop("bot", False)

        if is_bot:
            print(f"🤖 - Nova conexão - Bot: {ws_id} {self.request.remote_ip}")
            self.bot_ids = ws_id
            bots_ws.append(self)
            return

        if app_version < minimal_version:
            self.write_message(json.dumps({"op": "disconnect", "reason": "Versão do app não suportado! Certifique-se de que está usando "
                                         f"a versão mais recente do app ({minimal_version} ou superior)."}))
            self.close(code=4200)
            return

        if len(ws_id) > 3:
            self.write_message(json.dumps({"op": "disconnect", "reason": "Você está tentando conectar mais de 3 usuários consecutivamente..."}))
            self.close(code=4200)
            return

        if len(token) not in (0, 50):
            self.write_message(
                json.dumps({"op": "disconnect", "reason": f"O token precisa ter 50 caracteres..."}))
            self.close(code=4200)
            return

        self.user_ids = ws_id

        print("\n".join(f"👤 - Nova conexão - User: {u}" for u in self.user_ids))

        for u_id in ws_id:
            try:
                users_ws[u_id].write_message(json.dumps({"op": "disconnect",
                                               "reason": "Nova sessão iniciada em outro local..."}))
                users_ws[u_id].close(code=4200)
            except:
                pass
            users_ws[u_id] = self

        self.token = token

        for w in bots_ws:

            try:
                w.write_message(json.dumps(data))
            except Exception as e:
                print(f"🤖 - Erro ao processar dados do rpc para os bot's {w.bot_ids}: {repr(e)}")

    def check_origin(self, origin: str):
        return True

    def on_close(self):

        if self.user_ids:
            print("\n".join(f"👤 - Conexão Finalizada - User: {u}" for u in self.user_ids))
            for u_id in self.user_ids:
                try:
                    del users_ws[u_id]
                except KeyError:
                    continue
            return

        if not self.bot_ids:
            print(f"Conexão Finalizada - IP: {self.request.remote_ip}")

        else:

            print(f"🌐 - Conexão Finalizada - Bot ID's: {self.bot_ids}")

            data = {"op": "close", "bot_id": self.bot_ids}

            for w in users_ws.values():

                if w.blocked:
                    continue

                try:
                    w.write_message(data)
                except Exception as e:
                    print(
                        f"👤 - Erro ao processar dados do rpc para os usuários: [{', '.join(str(i) for i in w.user_ids)}]: {repr(e)}")

        bots_ws.remove(self)


class WSClient:

    def __init__(self, url: str, pool: BotPool):
        self.url: str = url
        self.pool = pool
        self.all_bots = None
        self.connection = None
        self.backoff: int = 7
        self.data: dict = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.connect_task = []

    async def connect(self):

        for t in self.connect_task:
            try:
                t.cancel()
            except:
                continue

        if not self.session:
            self.session = aiohttp.ClientSession()

        self.connection = await self.session.ws_connect(self.url, heartbeat=30)

        self.backoff = 7

        print("🌐 - RPC client conectado, sincronizando rpc dos bots...")

        if not self.all_bots:
            self.all_bots = self.pool.get_all_bots()

        self.connect_task = [asyncio.create_task(self.connect_bot_rpc())]

    @property
    def is_connected(self):
        return self.connection and not self.connection.closed

    async def connect_bot_rpc(self):

        bot_ids = set()

        for bot in self.all_bots:
            await bot.wait_until_ready()
            bot_ids.add(bot.user.id)

        if not bot_ids:
            print("🌐 - Conexão com servidor RPC ignorado: Lista de bots vazia...")
            return

        await self.send({"user_ids": list(bot_ids), "bot": True, "auth_enabled": self.pool.config["ENABLE_RPC_AUTH"]})

        await asyncio.sleep(1)

        for bot in self.all_bots:
            for player in bot.music.players.values():

                if not player.guild.me.voice:
                    continue

                if player.guild.me.voice.channel.voice_states:
                    bot.loop.create_task(player.process_rpc(player.last_channel))

        print(f"🌐 - [RPC client] - Os dados de rpc foram sincronizados com sucesso.")

    async def send(self, data: dict):

        if not self.is_connected:
            return

        try:
            await self.connection.send_json(data)
        except:
            print_exc()

    def clear_tasks(self):

        for t in self.connect_task:
            try:
                t.cancel()
            except:
                continue

        self.connect_task.clear()

    async def ws_loop(self):

        while True:

            try:

                if not self.is_connected:
                    self.clear_tasks()
                    await self.connect()

            except Exception as e:
                if isinstance(e, aiohttp.WSServerHandshakeError):
                    print(f"🌐 - Falha ao conectar no servidor RPC, tentando novamente em {(b:=int(self.backoff))} segundo{'s'[:b^1]}.")
                else:
                    print(f"🌐 - Conexão com servidor RPC perdida - Reconectando em {(b:=int(self.backoff))} segundo{'s'[:b^1]}.")

                await asyncio.sleep(self.backoff)
                self.backoff *= 2.5
                continue

            message = await self.connection.receive()

            if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                print(f"🌐 - RPC Websocket Closed: {message.extra}\nReconnecting in {self.backoff}s")
                await asyncio.sleep(self.backoff)
                continue

            elif message.type in (aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSE):
                print(f"🌐 - RPC Websocket Finalizado: {message.extra}")
                return

            data = json.loads(message.data)

            users: list = data.get("user_ids")

            if not users:
                continue

            op = data.get("op")

            if op == "rpc_update":

                for bot in self.all_bots:
                    for player in bot.music.players.values():
                        if not player.guild.me.voice:
                            continue
                        vc = player.guild.me.voice.channel
                        vc_user_ids = [i for i in vc.voice_states if i in users]
                        if vc_user_ids:
                            bot.loop.create_task(player.process_rpc(vc))
                            for i in vc_user_ids:
                                users.remove(i)


def run_app(pool: BotPool, message: str = "", config: dict = None):

    if not config:
        try:
            config = pool.config
        except IndexError:
            pass

    app = tornado.web.Application([
        (r'/', IndexHandler, {'pool': pool, 'message': message, 'config': config}),
        (r'/ws', WebSocketHandler),
    ])

    app.listen(port=config.get("PORT") or environ.get("PORT", 80))


def start(pool: BotPool, message="", config: dict = None):
    if not config:
        config = load_config()
    run_app(pool, message, config)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    start(BotPool())
