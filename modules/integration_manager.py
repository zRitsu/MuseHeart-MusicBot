# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import datetime
import json
import re
from io import BytesIO
from typing import TYPE_CHECKING, Union, Optional

import disnake
from disnake.ext import commands

from utils.db import DBModel
from utils.music.converters import URL_REG, fix_characters
from utils.music.errors import GenericError
from utils.music.interactions import SelectInteraction
from utils.others import CustomContext

youtube_regex = r"^(?:https?:\/\/)?(?:www\.)?youtube\.com\/(?:@)?([a-zA-Z0-9_-]{1,})(?:\/|$)"
soundcloud_regex = r"^(?:https?:\/\/)?(?:www\.)?soundcloud\.com\/([a-zA-Z0-9_-]+)"

if TYPE_CHECKING:
    from utils.client import BotCore


class IntegrationModal(disnake.ui.Modal):
    def __init__(self, bot: BotCore, name: Optional[str], url: Optional[str]):

        self.bot = bot
        self.name = name

        super().__init__(
            title="Adicionar integração",
            custom_id="user_integration_add",
            timeout=180,
            components=[
                disnake.ui.TextInput(
                    label="Link/Url:",
                    custom_id="user_integration_url",
                    min_length=10,
                    max_length=200,
                    value=url or None
                ),
            ]
        )

    async def callback(self, inter: disnake.ModalInteraction):

        url = inter.text_values["user_integration_url"].strip()

        try:
            url = URL_REG.findall(url)[0]
        except IndexError:
            await inter.send(
                embed=disnake.Embed(
                    description=f"**Nenhum link válido encontrado:** {url}",
                    color=disnake.Color.red()
                ), ephemeral=True
            )
            return

        match = re.search(youtube_regex, url)

        if match:
            group = match.group(1)
            base_url = f"https://www.youtube.com/@{group}/playlists"
        else:
            match = re.search(soundcloud_regex, url)

            if match:
                group = match.group(1)
                base_url = f"https://soundcloud.com/{group}/sets"
            else:
                await inter.send(
                    embed=disnake.Embed(
                        description=f"**Link informado não é suportado:** {url}",
                        color=disnake.Color.red()
                    ), ephemeral=True
                )
                return

        loop = self.bot.loop or asyncio.get_event_loop()

        try:
            await inter.response.defer(ephemeral=True)
        except:
            pass

        info = await loop.run_in_executor(None, lambda: self.bot.pool.ytdl.extract_info(base_url, download=False))

        if not info['entries']:
            return

        if info['entries'][0].get('id'):
            data = {"title": info["entries"][0]['title'], "url": base_url}

        else:

            if len(info['entries']) > 1:

                view = SelectInteraction(
                    user=inter.author,
                    opts=[
                        disnake.SelectOption(label=e['title'][:90], value=f"entrie_select_{c}") for c, e in enumerate(info['entries'])
                    ], timeout=30)

                embed = disnake.Embed(
                    description="**Escolha uma categoria de playlists abaixo:**\n"
                                f'Selecione uma opção em até <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=30)).timestamp())}:R> para prosseguir.',
                    color=self.bot.get_color()
                )

                await inter.edit_original_message(embed=embed, view=view)

                await view.wait()

                inter = view.inter

                try:
                    await inter.response.defer()
                except:
                    pass

                data = info["entries"][int(view.selected[14:])]

            else:
                data = info["entries"][0]

        data["title"] = f'@{group} - {data["title"]}' if info['extractor'].startswith("youtube") else f"@{info['title']}"

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        title = fix_characters(data['title'], 80)

        user_data["integration_links"][title] = data['url']

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        try:
            me = (inter.guild or self.bot.get_guild(inter.guild_id)).me
        except AttributeError:
            me = None

        await inter.edit_original_message(
            embed=disnake.Embed(
                description="**Integração adicionada com sucesso!\n"
                            "Ela vai aparecer nas seguintes ocasições:** ```\n"
                            "- Ao usar o comando /play (no preenchimento automático da busca)\n"
                            "- Ao clicar no botão de pedir música do player.\n"
                            "- Ao usar o comando play (prefixed) sem nome ou link.```",
                color=self.bot.get_color(me)
            ), view=None
        )


class IntegrationsView(disnake.ui.View):

    def __init__(self, bot: BotCore, ctx: Union[disnake.AppCmdInter, CustomContext], data: dict):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.current = None
        self.data = data
        self.message = None

        if data["integration_links"]:

            integration_select = disnake.ui.Select(options=[
                disnake.SelectOption(label=k) for k, v in data["integration_links"].items()
            ], min_values=1, max_values=1)
            integration_select.callback = self.select_callback
            self.add_item(integration_select)

        integrationadd_button = disnake.ui.Button(label="Adicionar", emoji="⭐")
        integrationadd_button.callback = self.integrationadd_callback
        self.add_item(integrationadd_button)

        if data["integration_links"]:

            remove_button = disnake.ui.Button(label="Remover", emoji="♻️")
            remove_button.callback = self.remove_callback
            self.add_item(remove_button)

            clear_button = disnake.ui.Button(label="Limpar Integrações", emoji="🚮")
            clear_button.callback = self.clear_callback
            self.add_item(clear_button)

        cancel_button = disnake.ui.Button(label="Cancelar", emoji="❌")
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

    async def on_timeout(self):

        if isinstance(self.ctx, CustomContext):
            try:
                await self.message.edit(
                    embed=disnake.Embed(description="**Tempo esgotado...**", color=self.bot.get_color()), view=None
                )
            except:
                pass

        else:
            await self.ctx.edit_original_message(
                embed=disnake.Embed(description="**Tempo esgotado...**", color=self.bot.get_color()), view=None
            )
        self.stop()

    async def integrationadd_callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(IntegrationModal(bot=self.bot, name=None, url=None))
        await inter.delete_original_message()
        self.stop()

    async def remove_callback(self, inter: disnake.MessageInteraction):

        if not self.current:
            await inter.send("Você deve selecionar um item!", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        try:
            del user_data["integration_links"][self.current]
        except:
            raise GenericError(f"**Não há integração na lista com o nome:** {self.current}")

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        await inter.edit_original_message(
            embed=disnake.Embed(
                description="**Integração removida com sucesso!**",
                color=self.bot.get_color()),
            view=None
        )
        self.stop()

    async def clear_callback(self, inter: disnake.MessageInteraction):

        await inter.response.defer(ephemeral=True)

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        if not user_data["integration_links"]:
            await inter.response.edit_message(content="**Você não possui integrações salvas!**", view=None)
            return

        user_data["integration_links"].clear()

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        embed = disnake.Embed(
            description="Sua lista de integrações foi limpa com sucesso!",
            color=self.bot.get_color()
        )

        await inter.response.edit_message(embed=embed, view=None)
        self.stop()

    async def cancel_callback(self, inter: disnake.MessageInteraction):
        await inter.response.edit_message(
            embed=disnake.Embed(
                description="**Operação com integrações cancelada...**",
                color=self.bot.get_color(),
            ), view=None
        )
        self.stop()

    async def select_callback(self, inter: disnake.MessageInteraction):
        self.current = inter.values[0]
        await inter.response.defer()


class IntegrationManager(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    desc_prefix = "💠 [Integrações] 💠 | "

    itg_cd = commands.CooldownMapping.from_cooldown(3, 15, commands.BucketType.member)

    @commands.max_concurrency(1, commands.BucketType.member, wait=False)
    @commands.slash_command()
    async def integration(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @commands.command(name="integrationmanager", aliases=["integrations", "itg", "itgmgr"],
                      description="Gerenciar suas integrações.", cooldown=itg_cd)
    async def integrationmanager_legacy(self, ctx: CustomContext):
        await self.manager.callback(self=self, inter=ctx)

    @integration.sub_command(
        description=f"{desc_prefix}Gerenciar suas integrações de canais/perfis com playlists públicas.", cooldown=itg_cd
    )
    async def manager(self, inter: disnake.AppCmdInter):

        await inter.response.defer(ephemeral=True)

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        view = IntegrationsView(bot=self.bot, ctx=inter, data=user_data)

        embed = disnake.Embed(
            description="## Gerenciador de integrações de canais/perfis com playlists públicas.\n\n"
                        "### Links de perfis/canais suportados:\n```ansi\n[31;1mYoutube[0m, [33;1mSoundcloud[0m```",
            colour=self.bot.get_color(),
        )

        if isinstance(inter, CustomContext):
            try:
                view.message = inter.store_message
                await inter.store_message.edit(embed=embed, view=view)
            except:
                view.message = await inter.send(embed=embed, view=view)
        else:
            try:
                await inter.edit_original_message(embed=embed, view=view)
            except:
                await inter.response.edit_message(embed=embed, view=view)

        await view.wait()

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(name="integrationlist", aliases=["itglist"], description="Exibir sua lista de integrações.")
    async def integrationlist_legacy(self, ctx: CustomContext):
        await self.list_.callback(self=self, inter=ctx, hidden=False)

    @commands.cooldown(1, 5, commands.BucketType.user)
    @integration.sub_command(
        name="list", description=f"{desc_prefix}Exibir sua lista de integrações."
    )
    async def list_(
            self, inter: disnake.ApplicationCommandInteraction,
            hidden: bool = commands.Param(
                name="ocultar",
                description="Apenas você poderá ver sua lista de integrações.",
                default=False)
    ):

        if hidden is False and not self.bot.check_bot_forum_post(inter.channel):
            hidden = True

        await inter.response.defer(ephemeral=hidden)

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        if not user_data["integration_links"]:
            raise GenericError(f"**Você não possui integrações..\n"
                               f"Você pode adicionar usando o comando: /{self.integration.name} {self.manager.name}**")

        embed = disnake.Embed(
            color=self.bot.get_color(),
            title="Suas integrações:",
            description="\n".join(f"{n+1}) [`{f[0]}`]({f[1]})" for n, f in enumerate(user_data["integration_links"].items()))
        )

        embed.set_footer(text="Você pode usá-los no comando /play")

        if isinstance(inter, CustomContext):
            await inter.send(embed=embed)
        else:
            await inter.edit_original_message(embed=embed)

    integration_import_export_cd = commands.CooldownMapping.from_cooldown(1, 15, commands.BucketType.member)

    @integration.sub_command(
        name="import", description=f"{desc_prefix}Importar suas integrações a partir de um arquivo.",
        cooldown=integration_import_export_cd
    )
    async def import_(
            self,
            inter: disnake.ApplicationCommandInteraction,
            file: disnake.Attachment = commands.Param(name="arquivo", description="arquivo em formato .json")
    ):

        if file.size > 2097152:
            raise GenericError("**O tamanho do arquivo não pode ultrapassar 2Mb!**")

        if not file.filename.endswith(".json"):
            raise GenericError("**Tipo de arquivo inválido!**")

        await inter.response.defer(ephemeral=True)

        try:
            data = (await file.read()).decode('utf-8')
            json_data = json.loads(data)
        except Exception as e:
            raise GenericError("**Ocorreu um erro ao ler o arquivo, por favor revise-o e use o comando novamente.**\n"
                               f"```py\n{repr(e)}```")

        for name, url in json_data.items():

            if "> itg:" in name.lower():
                continue

            if len(url) > (max_url_chars := 150):
                raise GenericError(f"**Um item de seu arquivo {url} ultrapassa a quantidade de caracteres permitido:{max_url_chars}**")

            if not isinstance(url, str) or not URL_REG.match(url):
                raise GenericError(f"O seu arquivo contém link inválido: ```ldif\n{url}```")

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        for name in json_data.keys():
            try:
                del user_data["integration_links"][name.lower()[:90]]
            except KeyError:
                continue

        if self.bot.config["MAX_USER_INTEGRATIONS"] > 0 and not (await self.bot.is_owner(inter.author)):

            if (json_size:=len(json_data)) > self.bot.config["MAX_USER_INTEGRATIONS"]:
                raise GenericError(f"A quantidade de itens no seu arquivo de integrações excede "
                                   f"a quantidade máxima permitida ({self.bot.config['MAX_USER_INTEGRATIONS']}).")

            if (json_size + (user_integrations:=len(user_data["integration_links"]))) > self.bot.config["MAX_USER_INTEGRATIONS"]:
                raise GenericError("Você não possui espaço suficiente para adicionar todos as integrações de seu arquivo...\n"
                                   f"Limite atual: {self.bot.config['MAX_USER_INTEGRATIONS']}\n"
                                   f"Quantidade de integrações salvas: {user_integrations}\n"
                                   f"Você precisa de: {(json_size + user_integrations)-self.bot.config['MAX_USER_INTEGRATIONS']}")

        user_data["integration_links"].update(json_data)

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        await inter.edit_original_message(
            embed = disnake.Embed(
                color=self.bot.get_color(),
                description = "**Os links foram importados com sucesso!**\n"
                              "**Eles vão aparecer quando usar o comando /play (no preenchimento automático da busca).**",
            )
        )

    @integration.sub_command(
        description=f"{desc_prefix}Exportar suas integrações em um arquivo json.",
        cooldown=integration_import_export_cd
    )
    async def export(self, inter: disnake.ApplicationCommandInteraction):

        await inter.response.defer(ephemeral=True)

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        if not user_data["integration_links"]:
            raise GenericError(f"**Você não possui integrações adicionadas...\n"
                               f"Você pode adicionar usando o comando: /{self.integration.name} {self.manager.name}**")

        fp = BytesIO(bytes(json.dumps(user_data["integration_links"], indent=4), 'utf-8'))

        embed = disnake.Embed(
            description=f"Suas integrações estão aqui.\nVocê pode importar usando o comando: `/{self.import_.name}`",
            color=self.bot.get_color())

        await inter.edit_original_message(embed=embed, file=disnake.File(fp=fp, filename="integrations.json"))


def setup(bot: BotCore):

    if not bot.config["USE_YTDL"]:
        return

    if not hasattr(bot.pool, 'ytdl'):
        from yt_dlp import YoutubeDL

        bot.pool.ytdl = YoutubeDL(
            {
                'ignoreerrors': True,
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'lazy_playlist': True,
                'simulate': True
            }
        )

    bot.add_cog(IntegrationManager(bot))
