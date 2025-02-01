from __future__ import annotations

import asyncio
import os.path
import traceback
import uuid
from typing import TYPE_CHECKING, Optional

import disnake
import ruamel.yaml
from disnake.ext import commands
from g4f.requests import aiohttp

from utils.music.errors import GenericError
from utils.others import CustomContext

if TYPE_CHECKING:
    from utils.client import BotCore


class YtOauthView(disnake.ui.View):

    def __init__(self, bot: BotCore, ctx: CustomContext):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.bot = bot

        # dados obtidos no repositório: https://github.com/lavalink-devs/youtube-source/blob/main/common/src/main/java/dev/lavalink/youtube/http/YoutubeOauth2Handler.java#L34
        self.client_id = '861556708454-d6dlm3lh05idd8npek18k6be8ba3oc68.apps.googleusercontent.com'
        self.client_secret = 'SboVhoG9s0rNafixCSGGKXAT'

        self.interaction: Optional[disnake.MessageInteraction] = None
        self.exception_txt = ""
        self.refresh_token = None

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

                self.refresh_token = response_data['refresh_token']
                return

    async def get_device_code(self, session: aiohttp.ClientSession):

        async with session.post(
                'https://oauth2.googleapis.com/device/code', data={
                    'client_id': self.client_id,
                    'scope': 'http://gdata.youtube.com https://www.googleapis.com/auth/youtube',
                    'device_id': str(uuid.uuid4()).replace("-", ""),
                    'device_model': "ytlr::",
                }
        ) as response:

            response_data = await response.json()

            if response.status != 200:
                raise GenericError(f"**Falha ao solicitar código de dispositivo:** `({response.status}) - {response_data}`")

            user_code = response_data['user_code']
            verification_url = response_data['verification_url']

            return response_data['device_code'], response_data['expires_in'], f"{verification_url}?user_code={user_code}"

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
            device_code, expire_in, verification_url = await self.get_device_code(session)

            self.bot.pool.yt_oauth_loop = self.bot.loop.create_task(
                self.check_session_loop(device_code=device_code, expire_in=expire_in)
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

        if not view.refresh_token:
            raise GenericError("**Tempo para vincular conta do google esgotado!**")

        txts = []

        if os.path.isfile("./application.yml"):

            try:

                yaml = ruamel.yaml.YAML()
                yaml.preserve_quotes = True
                yaml.explicit_start = True

                with open('./application.yml', 'r', encoding='utf-8') as file:
                    yml_data = yaml.load(file.read())

                new_value = {
                    "enabled": True,
                    "refreshToken": view.refresh_token
                }

                try:
                    yml_data['plugins']['youtube']['oauth'].update(new_value)
                except KeyError:
                    yml_data['plugins']['youtube'] = {'oauth': new_value}

                with open('./application.yml', 'w') as file:
                    yaml.dump(yml_data, file)

                if (node := self.bot.music.nodes.get("LOCAL")) and "youtube" in node.info["sourceManagers"] and "youtube-plugin" in node.info["plguins"]:
                    resp = await node.session.post(
                        f"{node.rest_uri}/youtube", headers=node._websocket.headers,
                        json={"refreshToken": view.refresh_token}
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

        if view.interaction:
            func = view.interaction.edit_original_message
        else:
            func = msg.edit

        txts.append("Evite mostrar esse token publicamente!")

        await func(embed=disnake.Embed(
            color=color,
            description=f"### refreshToken da conta do google obtido com sucesso!\n```{view.refresh_token}```\n**Nota:**\n" + "\n".join(f"* {t}" for t in txts)
        ), view=None)

def setup(bot: BotCore):
    bot.add_cog(YtOauthLL(bot))
