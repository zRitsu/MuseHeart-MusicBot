from __future__ import annotations

import asyncio
import os.path
import traceback
import uuid
from typing import TYPE_CHECKING, Optional

import aiohttp
import disnake
import ruamel.yaml
from disnake.ext import commands

from utils.music.errors import GenericError
from utils.music.interactions import AskView
from utils.others import CustomContext

if TYPE_CHECKING:
    from utils.client import BotCore


class YtOauthView(disnake.ui.View):

    def __init__(self, bot: BotCore, ctx: CustomContext):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.bot = bot
        self.data = {}

        # dados obtidos no repositório: https://github.com/lavalink-devs/youtube-source/blob/main/common/src/main/java/dev/lavalink/youtube/http/YoutubeOauth2Handler.java#L34
        self.client_id = '861556708454-d6dlm3lh05idd8npek18k6be8ba3oc68.apps.googleusercontent.com'
        self.client_secret = 'SboVhoG9s0rNafixCSGGKXAT'

        self.interaction: Optional[disnake.MessageInteraction] = None
        self.exception_txt = ""

        btn = disnake.ui.Button(label="Vincular conta do google")
        btn.callback = self.send_authurl_callback
        self.add_item(btn)

    async def exchange_device_code(self, device_code: str, expire=1800):

        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': device_code,
            'grant_type': 'http://oauth.net/grant_type/device/1.0',
        }

        await asyncio.sleep(10)

        retries_count = 15

        while retries_count <= expire:

            async with self.bot.session.post('https://oauth2.googleapis.com/token', data=payload) as response:
                response_data = await response.json()

                if response.status != 200:

                    if response_data["error"] != "authorization_pending":
                        self.exception_txt = f"**Falha ao aguardar autorização da conta:** `({response.status}) - {response_data['error_description']}`"
                        return

                    await asyncio.sleep(15)
                    retries_count += 15
                    continue

                self.data = response_data
                return

    async def get_device_code(self, session: aiohttp.ClientSession):

        async with session.post(
                'https://oauth2.googleapis.com/device/code', data={
                    'client_id': self.client_id,
                    'scope': 'http://gdata.youtube.com https://www.googleapis.com/auth/youtube email profile',
                    'device_id': str(uuid.uuid4()).replace("-", ""),
                    'device_model': "ytlr::",
                }
        ) as response:

            response_data = await response.json()

            if response.status != 200:
                raise GenericError(f"**Falha ao solicitar código de dispositivo:** `({response.status}) - {response_data}`")

            return response_data

    async def check_session_loop(self, device_code: str, expire_in: int):
        await self.exchange_device_code(device_code=device_code, expire=expire_in)
        self.stop()

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.send("Você não pode usar esse botão", ephemeral=True)
            return False
        return True

    async def send_authurl_callback(self, interaction: disnake.MessageInteraction):

        await interaction.response.defer(ephemeral=True, with_message=True)

        self.interaction = interaction

        try:
            self.bot.pool.yt_oauth_loop.cancel()
        except:
            pass

        async with aiohttp.ClientSession() as session:
            data = await self.get_device_code(session)
            verification_url = f"{data['verification_url']}?user_code={data['user_code']}"

        self.bot.pool.yt_oauth_loop = self.bot.loop.create_task(
            self.check_session_loop(device_code=data['device_code'], expire_in=data['expires_in'])
        )

        await interaction.message.delete()

        await interaction.send(embed=disnake.Embed(
            color=self.bot.get_color(self.ctx.guild.me),
            description=f"**Link para autenticar conta do google:**"
                        f" ```\n{verification_url}``` "
                        "`Caso já tenha autorizado a aplicação você deve aguardar até 15 segundos para "
                        "essa mensagem atualizar confirmando o processo.`"),
            components=[disnake.ui.Button(label="Abrir link", url=verification_url)],
            ephemeral=True)

class YtOauthLL(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    @commands.is_owner()
    @commands.command(hidden=True)
    async def ytoauth(self, ctx: CustomContext):

        try:
            self.bot.pool.yt_oauth_loop.cancel()
        except:
            pass

        try:
            self.bot.pool.yt_oauth_loop_command.cancel()
        except:
            pass

        self.bot.pool.yt_oauth_loop_command = self.bot.loop.create_task(self.oauth_command(ctx))

    async def oauth_command(self, ctx: CustomContext):

        color = self.bot.get_color(ctx.guild.me)

        view = YtOauthView(bot=self.bot, ctx=ctx)

        embed = disnake.Embed(
            color=color,
            description=f"## Obter refresh-token de uma conta do google\n\n"
                        f"⚠️ **Cuidado!** Use (ou crie) uma conta descartável ao invés de prosseguir com uma conta de "
                        f"uso pessoal devido a alta chance da conta ser banida pelo google (evite usar contas que podem conter algum número de telefone ou email de recuperação, caso crie uma agora evite colocar número de telefone e email de recuperação)."
        )

        msg = await ctx.send(embed=embed, view=view)

        await view.wait()

        if view.interaction:
            ctx.inter = view.interaction

        if view.exception_txt:
            raise GenericError(view.exception_txt)

        if not (refresh_token:=view.data.get('refresh_token')):
            raise GenericError("**Tempo para vincular conta do google esgotado!**")

        async with self.bot.session.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers={'Authorization': f'Bearer {view.data["access_token"]}'}
        ) as resp:

            if resp.status != 200:
                resp.raise_for_status()

            data = await resp.json()

        if view.interaction:
            func = view.interaction.edit_original_message
        else:
            func = msg.edit

        name = data['name']

        if (given_name:=data.get("given_name")) and given_name != name:
            name = f"{given_name} ({name})"

        embed = disnake.Embed(
            color=color,
            description=f"## Confirmação de conta:\n"
                        f"**Email autorizado:** ```ansi\n[31;1m{data['email']}[0m``` "
                        f"**Nome:** ```ansi\n[31;1m{name}[0m``` "
                        "⚠️ Cuidado! Caso essa conta seja de uso pessoal, clique no botão \"Não\" e use (ou crie) uma conta descartável!"
        ).set_thumbnail(data["picture"])

        view_confirm = AskView(ctx=ctx)

        await func(embed=embed, view=view_confirm)

        await view_confirm.wait()

        if view_confirm.interaction_resp:
            ctx.inter = view_confirm.interaction_resp
            if view_confirm.selected:
                func = ctx.inter.edit_original_message
            else:
                func = ctx.inter.response.edit_message

        if not view_confirm.selected:
            await func(content="**Operação cancelada.**", embed=None, view=None)
            return

        await view_confirm.interaction_resp.response.defer()

        txts = []

        if self.bot.pool.mongo_database:
            try:
                await self.bot.pool.mongo_database.update_data(
                    id_="youtube_data",
                    data={"refresh_tokens": {data['email']: refresh_token}},
                    collection="global",
                    db_name="global",
                )
            except Exception as e:
                txts.append(f"Falha ao salvar refreshToken no MongoDB: {repr(e)}")

        if os.path.isfile("./application.yml"):

            try:

                yaml = ruamel.yaml.YAML()
                yaml.preserve_quotes = True
                yaml.explicit_start = True

                with open('./application.yml', 'r', encoding='utf-8') as file:
                    yml_data = yaml.load(file.read())

                new_value = {
                    "enabled": True,
                    "refreshToken": refresh_token
                }

                try:
                    yml_data['plugins']['youtube']['oauth'].update(new_value)
                except KeyError:
                    yml_data['plugins']['youtube'] = {'oauth': new_value}

                with open('./application.yml', 'w') as file:
                    yaml.dump(yml_data, file)

                if (node := self.bot.music.nodes.get("LOCAL")) and "youtube-plugin" in node.info["plugins"]:
                    resp = await self.bot.session.post(
                        f"{node.rest_uri}/youtube", headers=node._websocket.headers,
                        json={"refreshToken": refresh_token}
                    )

                    if resp.status != 204:
                        txts.append(f"Erro ao aplicar refreshToken no lavalink LOCAL: {resp.status} - {await resp.text()}")
                    else:
                        txts.append("O refreshToken foi configurado automaticamente no servidor lavalink LOCAL")

                else:
                    txts.append("O refreshToken foi adicionado no application.yml com sucesso!")

            except Exception as e:
                traceback.print_exc()
                txts.append(f"Erro ao salvar refreshToken no application.yml: {repr(e)}")

        txts.append("Evite mostrar esse token publicamente!")

        await func(embed=disnake.Embed(
            color=color,
            description=f"### refreshToken da conta do google obtido com sucesso!\n```{refresh_token}``` "
                        f"**Usuário autorizado:**  ```ansi\n[34;1m{name}[0m``` "
                        f"**Email:** ```ansi\n[34;1m{data['email']}[0m``` "
                        f"**Nota{'s'[:len(txts)^1]}:**\n" + "\n".join(f"* {t}" for t in txts)
        ).set_thumbnail(data["picture"]), view=None)

def setup(bot: BotCore):
    bot.add_cog(YtOauthLL(bot))
