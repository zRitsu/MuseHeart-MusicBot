# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import datetime
import json
import re
import traceback
from io import BytesIO
from typing import TYPE_CHECKING, Union, Optional

import disnake
from disnake.ext import commands

from utils.db import DBModel
from utils.music.converters import URL_REG, fix_characters, time_format
from utils.music.interactions import SelectInteraction
from utils.music.spotify import spotify_regex_w_user
from utils.others import CustomContext, music_source_emoji_id

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

        if (matches := spotify_regex_w_user.match(url)):

            if not self.bot.spotify:
                await inter.send(
                    embed=disnake.Embed(
                        description="**O suporte ao spotify não está disponível no momento...**",
                        color=disnake.Color.red()
                    ), ephemeral=True
                )
                return

            url_type, user_id = matches.groups()

            if url_type != "user":
                await inter.send(
                    embed=disnake.Embed(
                        description=f"**Você deve usar link de um perfil de usuário do spotify.** {url}",
                        color=disnake.Color.red()
                    ), ephemeral=True
                )
                return

            try:
                await inter.response.defer(ephemeral=True)
            except:
                pass

            try:
                result = await self.bot.spotify.get_user(user_id)
            except Exception as e:
                await inter.send(
                    embed=disnake.Embed(
                        description="**Ocorreu um erro ao obter informações do spotify:** ```py\n"
                                    f"{repr(e)}```",
                        color=self.bot.get_color()
                    )
                )
                traceback.print_exc()
                return

            if not result:
                await inter.send(
                    embed=disnake.Embed(
                        description="**O usuário do link informado não possui playlists públicas...**",
                        color=self.bot.get_color()
                    )
                )
                return

            data = {"title": f"[SP]: {result.name[:90]}", "url": url}

        else:

            if not self.bot.config["USE_YTDL"]:
                await inter.send(
                    embed=disnake.Embed(
                        description="**Não há suporte a esse tipo de link no momento...**",
                        color=self.bot.get_color()
                    )
                )
                return

            match = re.search(youtube_regex, url)

            if match:
                group = match.group(1)
                base_url = f"https://www.youtube.com/@{group}/playlists"
                source = "[YT]:"
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

                source = "[SC]:"

            loop = self.bot.loop or asyncio.get_event_loop()

            try:
                await inter.response.defer(ephemeral=True)
            except:
                pass

            info = await loop.run_in_executor(None, lambda: self.bot.pool.ytdl.extract_info(base_url, download=False))

            if not info:

                msg = f"**O usuário/canal do link informado não existe:**\n{url}"

                if source == "[YT]:":
                    msg += f"\n\n`Nota: Confira se no link contém usuário com @, ex: @ytchannel`"

                await inter.send(
                    embed=disnake.Embed(
                        description=msg,
                        color=disnake.Color.red()
                    ), ephemeral=True
                )
                return

            if not info['entries']:
                await inter.send(
                    embed=disnake.Embed(
                        description=f"**O usuário/canal do link informado não possui playlists públicas...**",
                        color=disnake.Color.red()
                    ), ephemeral=True
                )
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

            data["title"] = f'{source} {info["channel"]} - {data["title"]}' if info['extractor'].startswith("youtube") else f"{source} {info['title']}"

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
                description=f"**Integração adicionada/editada com sucesso:** [`{title}`]({data['url']})\n"
                            "**Ela vai aparecer nas seguintes ocasições:** ```\n"
                            "- Ao usar o comando /play (no preenchimento automático da busca)\n"
                            "- Ao clicar no botão de tocar favorito do player.\n"
                            "- Ao usar o comando play (prefixed) sem nome ou link.```",
                color=self.bot.get_color(me)
            ), view=None
        )


class IntegrationsView(disnake.ui.View):

    def __init__(self, bot: BotCore, ctx: Union[disnake.AppCmdInter, CustomContext], data: dict):
        super().__init__(timeout=180)
        self.bot = bot
        self.ctx = ctx
        self.current = None
        self.data = data
        self.message = None

        if data["integration_links"]:

            integration_select = disnake.ui.Select(options=[
                disnake.SelectOption(label=k, emoji=music_source_emoji_id(k)) for k, v in data["integration_links"].items()
            ], min_values=1, max_values=1)
            integration_select.options[0].default = True
            self.current = integration_select.options[0].label
            integration_select.callback = self.select_callback
            self.add_item(integration_select)

        integrationadd_button = disnake.ui.Button(label="Adicionar", emoji="💠")
        integrationadd_button.callback = self.integrationadd_callback
        self.add_item(integrationadd_button)

        if data["integration_links"]:

            remove_button = disnake.ui.Button(label="Remover", emoji="♻️")
            remove_button.callback = self.remove_callback
            self.add_item(remove_button)

            clear_button = disnake.ui.Button(label="Limpar Integrações", emoji="🚮")
            clear_button.callback = self.clear_callback
            self.add_item(clear_button)

            export_button = disnake.ui.Button(label="Exportar", emoji="📤")
            export_button.callback = self.export_callback
            self.add_item(export_button)

        import_button = disnake.ui.Button(label="Importar", emoji="📥")
        import_button.callback = self.import_callback
        self.add_item(import_button)

        cancel_button = disnake.ui.Button(label="Cancelar", emoji="❌")
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

    async def on_timeout(self):

        try:
            for i in self.children[0].options:
                i.default = self.current == i.value
        except:
            pass

        for c in self.children:
            c.disabled = True

        if isinstance(self.ctx, CustomContext):
            try:
                await self.message.edit(view=self)
            except:
                pass

        else:
            try:
                await self.ctx.edit_original_message(view=self)
            except:
                pass

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
            await inter.send(f"**Não há integração na lista com o nome:** {self.current}", ephemeral=True)
            return

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

        await inter.edit_original_message(embed=embed, components=None)
        self.stop()

    async def import_callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(
            title="Importar integração",
            custom_id="integration_import",
            components=[
                disnake.ui.TextInput(
                    style=disnake.TextInputStyle.long,
                    label="Inserir dados (em formato json)",
                    custom_id="json_data",
                    min_length=20,
                    required=True
                )
            ]
        )
        await inter.delete_original_message()

    async def export_callback(self, inter: disnake.MessageInteraction):
        await self.bot.get_cog("IntegrationManager").export_(inter)
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

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:

        if inter.author.id == self.ctx.author.id:
            return True

        await inter.send(f"Apenas o membro {self.ctx.author.mention} pode interagir nessa mensagem.", ephemeral=True)


class IntegrationManager(commands.Cog):

    emoji = "💠"
    name = "Integrações"
    desc_prefix = f"[{emoji} {name}] | "

    def __init__(self, bot: BotCore):
        self.bot = bot

    itg_cd = commands.CooldownMapping.from_cooldown(3, 15, commands.BucketType.member)

    async def integration(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @commands.command(name="integrations", aliases=["integrationmanager", "itg", "itgmgr", "itglist", "integrationlist"],
                      description="Gerenciar suas integrações.", cooldown=itg_cd)
    async def integratios_legacy(self, ctx: CustomContext):
        await self.integrations.callback(self=self, inter=ctx)

    @commands.max_concurrency(1, commands.BucketType.member, wait=False)
    @commands.slash_command(description=f"{desc_prefix}Gerenciar suas integrações de canais/perfis com playlists públicas.", cooldown=itg_cd)
    async def integrations(self, inter: disnake.AppCmdInter):

        supported_platforms = []

        if self.bot.config["USE_YTDL"]:
            supported_platforms.extend(["[31;1mYoutube[0m", "[33;1mSoundcloud[0m"])

        if self.bot.spotify:
            supported_platforms.append("[32;1mSpotify[0m")

        if not supported_platforms:
            await inter.send("**Não há suporte a esse recurso no momento...**\n\n"
                               "`Suporte ao spotify e YTDL não estão ativados.`", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        view = IntegrationsView(bot=self.bot, ctx=inter, data=user_data)

        embed = disnake.Embed(
            title="Gerenciador de integrações de canais/perfis com playlists públicas.",
            colour=self.bot.get_color(),
        )

        if user_data["integration_links"]:

            embed.description = f"**Suas integrações atuais:**\n\n" + "\n".join(f"> ` {n+1} ` [`{f[0]}`]({f[1]})" for n, f in enumerate(user_data["integration_links"].items()))

            cog = self.bot.get_cog("Music")

            if cog:

                try:
                    global_data = inter.global_guild_data
                except AttributeError:
                    global_data = await self.bot.get_global_data(inter.guild_id, db_name=DBModel.guilds)
                    inter.global_guild_data = global_data

                cmd = f"</play:" + str(self.bot.pool.controller_bot.get_global_command_named("play",
                                                                                             cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"

                embed.add_field(name="**Como tocar a playlist de uma integração?**", inline=False,
                                value=f"* Usando o comando {cmd} (no preenchimento automático da busca)\n"
                                      "* Clicando no botão de tocar favorito do player.\n"
                                      f"* Usando o comando {global_data['prefix'] or self.bot.default_prefix}{cog.play_legacy.name} sem usar um nome ou link.")

        embed.add_field(
            name="Links de perfis/canais suportados:", inline=False,
            value=f"```ansi\n{', '.join(supported_platforms)}```"
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

    integration_import_export_cd = commands.CooldownMapping.from_cooldown(1, 15, commands.BucketType.member)

    @commands.Cog.listener("on_modal_submit")
    async def modal_import(self, inter: disnake.ModalInteraction):

        if inter.custom_id != "integration_import":
            return

        try:
            json_data = json.loads(inter.text_values["json_data"])
        except Exception as e:
            await inter.send("**Ocorreu um erro ao analisar os dados ou foi enviado dados inválidos/não-formatado "
                               f"em formato json.**\n\n`{repr(e)}`", ephemeral=True)

        retry_after = self.integration_import_export_cd.get_bucket(inter).update_rate_limit()
        if retry_after:
            if retry_after < 1:
                retry_after = 1
            await inter.send("**Você deve aguardar {} para importar.**".format(
                time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        for name, url in json_data.items():

            if "> itg:" in name.lower():
                continue

            if len(url) > (max_url_chars := 150):
                await inter.edit_original_message(
                    f"**Um item de seu arquivo {url} ultrapassa a quantidade de caracteres permitido:{max_url_chars}**")
                return

            if not isinstance(url, str) or not URL_REG.match(url):
                await inter.edit_original_message(f"O seu arquivo contém link inválido: ```ldif\n{url}```")
                return

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        for name in json_data.keys():
            try:
                del user_data["integration_links"][name.lower()[:90]]
            except KeyError:
                continue

        if self.bot.config["MAX_USER_INTEGRATIONS"] > 0 and not (await self.bot.is_owner(inter.author)):

            if (json_size := len(json_data)) > self.bot.config["MAX_USER_INTEGRATIONS"]:
                await inter.edit_original_message(f"A quantidade de itens no seu arquivo de integrações excede "
                                   f"a quantidade máxima permitida ({self.bot.config['MAX_USER_INTEGRATIONS']}).")
                return

            if (json_size + (user_integrations := len(user_data["integration_links"]))) > self.bot.config[
                "MAX_USER_INTEGRATIONS"]:
                await inter.edit_original_message(
                    "Você não possui espaço suficiente para adicionar todos as integrações de seu arquivo...\n"
                    f"Limite atual: {self.bot.config['MAX_USER_INTEGRATIONS']}\n"
                    f"Quantidade de integrações salvas: {user_integrations}\n"
                    f"Você precisa de: {(json_size + user_integrations) - self.bot.config['MAX_USER_INTEGRATIONS']}")
                return

        user_data["integration_links"].update(json_data)

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        cmd = f"</play:" + str(self.bot.pool.controller_bot.get_global_command_named("play", cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"

        await inter.edit_original_message(
            embed=disnake.Embed(
                color=self.bot.get_color(),
                description="**Os links foram importados com sucesso!**\n"
                            f"**Use o comando {cmd} para conferir (no preenchimento automático da busca).**",
            )
        )

    async def export_(self, inter: disnake.MessageInteraction):

        retry_after = self.integration_import_export_cd.get_bucket(inter).update_rate_limit()
        if retry_after:
            if retry_after < 1:
                retry_after = 1
            await inter.send("**Você deve aguardar {} para exportar.**".format(
                time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        try:
            user_data = inter.global_user_data
        except AttributeError:
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            inter.global_user_data = user_data

        cmd = f"</{self.integrations.name}:" + str(
            self.bot.pool.controller_bot.get_global_command_named(self.integrations.name,
                                                                  cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"

        if not user_data["integration_links"]:
            await inter.edit_original_message(f"**Você não possui integrações adicionadas...\n"
                               f"Você pode adicionar usando o comando: {cmd}**")
            return

        fp = BytesIO(bytes(json.dumps(user_data["integration_links"], indent=4), 'utf-8'))

        embed = disnake.Embed(
            description=f"Suas integrações estão aqui.\nVocê pode importar usando o comando: {cmd}",
            color=self.bot.get_color())

        await inter.send(embed=embed, file=disnake.File(fp=fp, filename="integrations.json"), ephemeral=True)


def setup(bot: BotCore):

    if bot.config["USE_YTDL"] and not hasattr(bot.pool, 'ytdl'):

        from yt_dlp import YoutubeDL

        bot.pool.ytdl = YoutubeDL(
            {
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'lazy_playlist': True,
                'simulate': True,
                'cachedir': False,
                'allowed_extractors': [
                    r'.*youtube.*',
                    r'.*soundcloud.*',
                ],
                'extractor_args': {
                    'youtube': {
                        'skip': [
                            'hls',
                            'dash',
                            'translated_subs'
                        ],
                        'player_skip': [
                            'js',
                            'configs',
                            'webpage'
                        ],
                        'player_client': ['android_creator'],
                        'max_comments': [0],
                    },
                    'youtubetab': {
                        "skip": ["webpage"]
                    }
                }
            }
        )

    bot.add_cog(IntegrationManager(bot))
