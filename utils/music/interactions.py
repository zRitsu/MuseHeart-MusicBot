# -*- coding: utf-8 -*-
from __future__ import annotations
import asyncio
import json
import re
import traceback
from io import BytesIO
from typing import List, Union, Optional, TYPE_CHECKING

import disnake
from disnake.ext import commands

from utils.db import DBModel
from utils.music.checks import check_pool_bots
from utils.music.converters import time_format, fix_characters, URL_REG
from utils.music.errors import GenericError
from utils.music.spotify import spotify_regex_w_user
from utils.others import check_cmd, CustomContext, send_idle_embed, music_source_emoji_url, \
    music_source_emoji_id, PlayerControls

if TYPE_CHECKING:
    from utils.client import BotCore


class VolumeInteraction(disnake.ui.View):

    def __init__(self, inter):
        self.inter = inter
        self.volume = None
        super().__init__(timeout=30)
        self.process_buttons()

    def process_buttons(self):

        opts = []

        for l in [5, 20, 40, 60, 80, 100, 120, 150]:

            if l > 100:
                description = "Acima de 100% o audio pode ficar bem ruim."
            else:
                description = None
            opts.append(disnake.SelectOption(label=f"{l}%", value=f"vol_{l}", description=description))

        select = disnake.ui.Select(placeholder='Nível:', options=opts)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: disnake.MessageInteraction):
        await interaction.response.edit_message(content=f"Volume alterado!",embed=None, view=None)
        self.volume = int(interaction.data.values[0][4:])
        self.stop()


class QueueInteraction(disnake.ui.View):

    def __init__(self, player, user: disnake.Member, timeout=60):

        self.player = player
        self.bot = player.bot
        self.user = user
        self.pages = []
        self.select_pages = []
        self.current = 0
        self.max_page = len(self.pages) - 1
        self.message: Optional[disnake.Message] = None
        super().__init__(timeout=timeout)
        self.embed = disnake.Embed(color=self.bot.get_color(user.guild.me))
        self.update_pages()
        self.update_embed()

    def update_pages(self):

        counter = 1

        self.pages = list(disnake.utils.as_chunks(self.player.queue, max_size=12))
        self.select_pages.clear()

        self.clear_items()

        for n, page in enumerate(self.pages):

            txt = "\n"
            opts = []

            for t in page:

                duration = time_format(t.duration) if not t.is_stream else '🔴 Livestream'

                txt += f"`┌ {counter})` [`{fix_characters(t.title, limit=50)}`]({t.uri})\n" \
                       f"`└ ⏲️ {duration}`" + (f" - `Repetições: {t.track_loops}`" if t.track_loops else  "") + \
                       f" **|** `✋` <@{t.requester}>\n"

                opts.append(
                    disnake.SelectOption(
                        label=f"{counter}. {t.author}"[:25], description=f"[{duration}] | {t.title}"[:50],
                        value=f"queue_select_{t.unique_id}",
                    )
                )

                counter += 1

            self.pages[n] = txt
            self.select_pages.append(opts)

        track_select = disnake.ui.Select(
            placeholder="Tocar uma música específica da página:",
            options=self.select_pages[self.current],
            custom_id="queue_track_selection",
            max_values=1
        )

        track_select.callback = self.track_select_callback

        self.add_item(track_select)

        first = disnake.ui.Button(emoji='⏮️', style=disnake.ButtonStyle.grey)
        first.callback = self.first
        self.add_item(first)

        back = disnake.ui.Button(emoji='⬅️', style=disnake.ButtonStyle.grey)
        back.callback = self.back
        self.add_item(back)

        next = disnake.ui.Button(emoji='➡️', style=disnake.ButtonStyle.grey)
        next.callback = self.next
        self.add_item(next)

        last = disnake.ui.Button(emoji='⏭️', style=disnake.ButtonStyle.grey)
        last.callback = self.last
        self.add_item(last)

        stop_interaction = disnake.ui.Button(emoji='⏹️', style=disnake.ButtonStyle.grey)
        stop_interaction.callback = self.stop_interaction
        self.add_item(stop_interaction)

        update_q = disnake.ui.Button(emoji='🔄', label="Refresh", style=disnake.ButtonStyle.grey)
        update_q.callback = self.update_q
        self.add_item(update_q)

        self.current = 0
        self.max_page = len(self.pages) - 1

    async def on_timeout(self) -> None:

        if not self.message:
            return

        embed = self.message.embeds[0]
        embed.set_footer(text="Tempo para interagir esgotado!")

        for c in self.children:
            c.disabled = True

        await self.message.edit(embed=embed, view=self)


    def update_embed(self):
        self.embed.title = f"**Músicas da fila [{self.current+1} / {self.max_page+1}]**"
        self.embed.description = self.pages[self.current]
        self.children[0].options = self.select_pages[self.current]

        for n, c in enumerate(self.children):
            if isinstance(c, disnake.ui.StringSelect):
                self.children[n].options = self.select_pages[self.current]

    async def track_select_callback(self, interaction: disnake.MessageInteraction):

        track_id = interaction.values[0][13:]

        track = None

        for t in  self.player.queue:
            if t.unique_id == track_id:
                track = t
                break

        if not track:
            await interaction.send(f"Música com id \"{track_id}\" não encontrada na fila do player...", ephemeral=True)
            return

        command = self.bot.get_slash_command("skip")

        interaction.music_bot = self.bot
        interaction.music_guild = self.user.guild

        try:
            await check_cmd(command, interaction)
            await command(interaction, query=f"{track.title} || ID > {track.unique_id}")
            self.stop()
        except Exception as e:
            self.bot.dispatch('interaction_player_error', interaction, e)

    async def first(self, interaction: disnake.MessageInteraction):

        self.current = 0
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def back(self, interaction: disnake.MessageInteraction):

        if self.current == 0:
            self.current = self.max_page
        else:
            self.current -= 1
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def next(self, interaction: disnake.MessageInteraction):

        if self.current == self.max_page:
            self.current = 0
        else:
            self.current += 1
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)

    async def last(self, interaction: disnake.MessageInteraction):

        self.current = self.max_page
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)


    async def stop_interaction(self, interaction: disnake.MessageInteraction):

        await interaction.response.edit_message(content="Queue fechada", embed=None, view=None)
        self.stop()

    async def update_q(self, interaction: disnake.MessageInteraction):

        self.current = 0
        self.max_page = len(self.pages) - 1
        self.update_pages()
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)


class SelectInteraction(disnake.ui.View):

    def __init__(self, user: disnake.Member, opts: List[disnake.SelectOption], *, timeout=180):
        super().__init__(timeout=timeout)
        self.user = user
        self.selected = None
        self.item_pages = list(disnake.utils.as_chunks(opts, 25))
        self.current_page = 0
        self.max_page = len(self.item_pages)-1
        self.inter = None

        self.load_components()

    def load_components(self):

        self.clear_items()

        select_menu = disnake.ui.Select(placeholder='Selecione uma opção:', options=self.item_pages[self.current_page])
        select_menu.callback = self.callback
        self.add_item(select_menu)
        self.selected = self.item_pages[self.current_page][0].value

        if len(self.item_pages) > 1:

            back_button = disnake.ui.Button(emoji="⬅")
            back_button.callback = self.back_callback
            self.add_item(back_button)

            next_button = disnake.ui.Button(emoji="➡")
            next_button.callback = self.next_callback
            self.add_item(next_button)

        button = disnake.ui.Button(label="Cancelar", emoji="❌")
        button.callback = self.cancel_callback
        self.add_item(button)

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:

        if interaction.user.id == self.user.id:
            return True

        await interaction.send(f"Apenas {self.user.mention} pode interagir aqui.", ephemeral = True)

    async def back_callback(self, interaction: disnake.MessageInteraction):
        if self.current_page == 0:
            self.current_page = self.max_page
        else:
            self.current_page -= 1
        self.load_components()
        await interaction.response.edit_message(view=self)

    async def next_callback(self, interaction: disnake.MessageInteraction):
        if self.current_page == self.max_page:
            self.current_page = 0
        else:
            self.current_page += 1
        self.load_components()
        await interaction.response.edit_message(view=self)

    async def cancel_callback(self, interaction: disnake.MessageInteraction):
        self.selected = False
        self.inter = interaction
        self.stop()

    async def callback(self, interaction: disnake.MessageInteraction):
        self.selected = interaction.data.values[0]
        self.inter = interaction
        self.stop()


class AskView(disnake.ui.View):

    def __init__(self, *, ctx: Union[commands.Context, disnake.Interaction], timeout=None):
        super().__init__(timeout=timeout)
        self.selected = None
        self.ctx = ctx
        self.interaction_resp: Optional[disnake.MessageInteraction] = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:

        if interaction.user != self.ctx.author:
            await interaction.send("Você não pode usar este botão!", ephemeral=True)
            return False

        return True

    @disnake.ui.button(label="Sim", emoji="✅")
    async def allow(self, button, interaction: disnake.MessageInteraction):
        self.selected = True
        self.interaction_resp = interaction
        self.stop()

    @disnake.ui.button(label="Não", emoji="❌")
    async def deny(self, button, interaction: disnake.MessageInteraction):
        self.selected = False
        self.interaction_resp = interaction
        self.stop()

youtube_regex = r"https?://www\.youtube\.com/(?:channel/|@)[^/]+"
soundcloud_regex = r"^(?:https?:\/\/)?(?:www\.)?soundcloud\.com\/([a-zA-Z0-9_-]+)"

async def process_idle_embed(bot: BotCore, guild: disnake.Guild, guild_data: dict):

    try:
        bot.music.players[guild.id]
        return
    except KeyError:
        pass

    try:
        channel = bot.get_channel(int(guild_data["player_controller"]["channel"]))
    except:
        return

    try:
        message = await channel.fetch_message(int(guild_data["player_controller"]["message_id"]))
    except:
        message = None

    await send_idle_embed(message or channel, bot=bot, guild_data=guild_data)

class ViewMode:
    fav_manager = "0"
    guild_fav_manager = "1"
    integrations_manager = "2"

class FavModalImport(disnake.ui.Modal):

    def __init__(self, view):

        self.view = view

        if self.view.mode == ViewMode.fav_manager:
            super().__init__(
                title="Importar Favoritos",
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
            return

        if self.view.mode == ViewMode.guild_fav_manager:
            super().__init__(
                title="Importar Playlists para o Servidor",
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

        if self.view.mode == ViewMode.integrations_manager:
            super().__init__(
                title="Importar integração",
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
            return

        raise GenericError(f"Modo atual ainda não implementado: {self.view.mode}")

    async def callback(self, inter: disnake.ModalInteraction, /) -> None:

        try:
            json_data = json.loads(inter.text_values["json_data"])
        except Exception as e:
            await inter.send("**Ocorreu um erro ao analisar os dados ou foi enviado dados inválidos/não-formatado "
                               f"em formato json.**\n\n`{repr(e)}`", ephemeral=True)
            return

        if self.view.mode == ViewMode.fav_manager:

            if retry_after := self.view.bot.get_cog("Music").fav_import_export_cd.get_bucket(inter).update_rate_limit():
                if retry_after < 1:
                    retry_after = 1
                await inter.send("**Você deve aguardar {} para importar.**".format(
                    time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
                return

            for name, url in json_data.items():

                if "> fav:" in name.lower():
                    continue

                if len(url) > (max_url_chars := self.view.bot.config["USER_FAV_MAX_URL_LENGTH"]):
                    await inter.send(
                        f"**Um item de seu arquivo {url} ultrapassa a quantidade de caracteres permitido:{max_url_chars}**",
                        ephemeral=True)
                    return

                if not isinstance(url, str) or not URL_REG.match(url):
                    await inter.send(f"O seu arquivo contém link inválido: ```ldif\n{url}```", ephemeral=True)
                    return

            await inter.response.defer(ephemeral=True)

            self.view.data = await self.view.bot.get_global_data(inter.author.id, db_name=DBModel.users)

            for name in json_data.keys():
                if len(name) > (max_name_chars := self.view.bot.config["USER_FAV_MAX_NAME_LENGTH"]):
                    await inter.edit_original_message(
                        f"**Um item de seu arquivo ({name}) ultrapassa a quantidade de caracteres permitido:{max_name_chars}**")
                    return
                try:
                    del self.view.data["fav_links"][name.lower()]
                except KeyError:
                    continue

            if self.view.bot.config["MAX_USER_FAVS"] > 0 and not (await self.view.bot.is_owner(inter.author)):

                if (json_size := len(json_data)) > self.view.bot.config["MAX_USER_FAVS"]:
                    await inter.edit_original_message(f"A quantidade de itens no seu arquivo de favorito excede "
                                                      f"a quantidade máxima permitida ({self.view.bot.config['MAX_USER_FAVS']}).")
                    return

                if (json_size + (user_favs := len(self.view.data["fav_links"]))) > self.view.bot.config[
                    "MAX_USER_FAVS"]:
                    await inter.edit_original_message(
                        "Você não possui espaço suficiente para adicionar todos os favoritos de seu arquivo...\n"
                        f"Limite atual: {self.view.bot.config['MAX_USER_FAVS']}\n"
                        f"Quantidade de favoritos salvos: {user_favs}\n"
                        f"Você precisa de: {(json_size + user_favs) - self.view.bot.config['MAX_USER_FAVS']}")
                    return

            self.view.data["fav_links"].update(json_data)

            await self.view.bot.update_global_data(inter.author.id, self.view.data, db_name=DBModel.users)

            await inter.edit_original_message(content="**Favoritos importados com sucesso!**")

            if (s := len(json_data)) > 1:
                self.view.log = f"{s} favoritos foram importados com sucesso."
            else:
                name = next(iter(json_data))
                self.view.log = f"O favorito [`{name}`]({json_data[name]}) foi importado com sucesso."


        elif self.view.mode == ViewMode.guild_fav_manager:

            if retry_after := self.view.bot.get_cog("Music").fav_import_export_cd.get_bucket(inter).update_rate_limit():
                if retry_after < 1:
                    retry_after = 1
                await inter.send("**Você deve aguardar {} para importar.**".format(
                    time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
                return

            for name, data in json_data.items():

                if "> fav:" in name.lower():
                    continue

                if len(data['url']) > (max_url_chars := self.view.bot.config["USER_FAV_MAX_URL_LENGTH"]):
                    await inter.send(
                        f"**Um item de seu arquivo ultrapassa a quantidade de caracteres permitido:{max_url_chars}\nURL:** {data['url']}",
                        ephemeral=True)
                    return

                if len(data['description']) > 50:
                    await inter.send(
                        f"**Um item de seu arquivo ultrapassa a quantidade de caracteres permitido:{max_url_chars}\nDescrição:** {data['description']}",
                        ephemeral=True)
                    return

                if not isinstance(data['url'], str) or not URL_REG.match(data['url']):
                    await inter.send(f"O seu arquivo contém link inválido: ```ldif\n{data['url']}```", ephemeral=True)
                    return

            await inter.response.defer(ephemeral=True)

            self.view.guild_data = await self.view.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

            if not self.view.guild_data["player_controller"]["channel"] or not self.view.bot.get_channel(
                    int(self.view.guild_data["player_controller"]["channel"])):
                await inter.edit_original_message("**Não há player configurado no servidor! Use o comando /setup**")
                return

            for name in json_data.keys():
                if len(name) > (max_name_chars := 25):
                    await inter.edit_original_message(
                        f"**Um item de seu arquivo ({name}) ultrapassa a quantidade de caracteres permitido:{max_name_chars}**")
                    return
                try:
                    del self.view.guild_data["player_controller"]["fav_links"][name]
                except KeyError:
                    continue

            if (json_size := len(json_data)) > 25:
                await inter.edit_original_message(
                    f"A quantidade de itens no arquivo excede a quantidade máxima permitida (25).")
                return

            if (json_size + (user_favs := len(self.view.guild_data["player_controller"]["fav_links"]))) > 25:
                await inter.edit_original_message(
                    "A lista de músicas/playlist do servidor não possui espaço suficiente para adicionar todos os itens de seu arquivo...\n"
                    f"Limite atual: 25\n"
                    f"Quantidade de links salvos: {user_favs}\n"
                    f"Você precisa de: {(json_size + user_favs) - 25}")
                return

            self.view.guild_data["player_controller"]["fav_links"].update(json_data)

            await self.view.bot.update_data(inter.guild_id, self.view.guild_data, db_name=DBModel.guilds)

            guild = self.view.bot.get_guild(inter.guild_id)

            await inter.edit_original_message(content="**Links fixos do servidor foram importados com sucesso!**")

            if (s := len(json_data)) > 1:
                self.view.log = f"{s} links foram importados com sucesso para a lista de favoritos do servidor."
            else:
                name = next(iter(json_data))
                self.view.log = f"O link [`{name}`]({json_data[name]}) foi importado com sucesso para a lista de links do servidor.."

            await process_idle_embed(self.view.bot, guild, guild_data=self.view.guild_data)

        elif self.view.mode == ViewMode.integrations_manager:

            if retry_after := self.view.bot.get_cog("Music").fav_import_export_cd.get_bucket(inter).update_rate_limit():
                if retry_after < 1:
                    retry_after = 1
                await inter.send("**Você deve aguardar {} para importar.**".format(
                    time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
                return

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

            await inter.response.defer(ephemeral=True)

            self.view.data = await self.view.bot.get_global_data(inter.author.id, db_name=DBModel.users)

            for name in json_data.keys():
                try:
                    del self.view.data["integration_links"][name.lower()[:90]]
                except KeyError:
                    continue

            if self.view.bot.config["MAX_USER_INTEGRATIONS"] > 0 and not (await self.view.bot.is_owner(inter.author)):

                if (json_size := len(json_data)) > self.view.bot.config["MAX_USER_INTEGRATIONS"]:
                    await inter.edit_original_message(f"A quantidade de itens no seu arquivo de integrações excede "
                                       f"a quantidade máxima permitida ({self.view.bot.config['MAX_USER_INTEGRATIONS']}).")
                    return

                if (json_size + (user_integrations := len(self.view.data["integration_links"]))) > self.view.bot.config[
                    "MAX_USER_INTEGRATIONS"]:
                    await inter.edit_original_message(
                        "Você não possui espaço suficiente para adicionar todos as integrações de seu arquivo...\n"
                        f"Limite atual: {self.view.bot.config['MAX_USER_INTEGRATIONS']}\n"
                        f"Quantidade de integrações salvas: {user_integrations}\n"
                        f"Você precisa de: {(json_size + user_integrations) - self.view.bot.config['MAX_USER_INTEGRATIONS']}")
                    return

            self.view.data["integration_links"].update(json_data)

            await self.view.bot.update_global_data(inter.author.id, self.view.data, db_name=DBModel.users)

            await inter.edit_original_message(
                content="**Integrações importadas com sucesso!**"
            )

            if s := len(json_data) > 1:
                self.view.log = f"{s} integrações foram importadas com sucesso."
            else:
                name = next(iter(json_data))
                self.view.log = f"A integração [`{name}`]({json_data[name]}) foi importada com sucesso."

        else:
            raise GenericError(f"**Modo ainda não implementado: {self.view.mode}**")

        if not isinstance(self.view.ctx, CustomContext):
            await self.view.ctx.edit_original_message(embed=self.view.build_embed(), view=self.view)
        elif self.view.message:
            await self.view.message.edit(embed=self.view.build_embed(), view=self.view)


class FavModalAdd(disnake.ui.Modal):
    def __init__(self, name: Optional[str], url: Optional[str], view, **kwargs):

        self.view = view
        self.name = name

        if self.view.mode == ViewMode.fav_manager:
            super().__init__(
                title="Adicionar/Editar playlist/favorito",
                custom_id="user_fav_edit",
                timeout=180,
                components=[
                    disnake.ui.TextInput(
                        label="Nome da playlist/favorito:",
                        custom_id="user_fav_name",
                        min_length=2,
                        max_length=25,
                        value=name or None
                    ),
                    disnake.ui.TextInput(
                        label="Link/Url:",
                        custom_id="user_fav_url",
                        min_length=10,
                        max_length=200,
                        value=url or None
                    ),
                ]
            )
            return

        if self.view.mode == ViewMode.guild_fav_manager:
            super().__init__(
                title="Adicionar/Editar playlist/favorito",
                custom_id="guild_fav_edit",
                timeout=180,
                components=[
                    disnake.ui.TextInput(
                        label="Nome do favorito/playlist:",
                        custom_id="guild_fav_name",
                        min_length=2,
                        max_length=25,
                        value=name or None
                    ),
                    disnake.ui.TextInput(
                        label="Descrição:",
                        custom_id="guild_fav_description",
                        min_length=3,
                        max_length=50,
                        value=kwargs.get('description', None),
                        required=False
                    ),
                    disnake.ui.TextInput(
                        label="Link/Url:",
                        custom_id="guild_fav_url",
                        min_length=10,
                        max_length=250,
                        value=url or None
                    ),
                ]
            )
            return

        if self.view.mode == ViewMode.integrations_manager:
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
            return

        raise GenericError(f"**Modo ainda não implementado: {self.view.mode}**")


    async def callback(self, inter: disnake.ModalInteraction):

        if self.view.mode == ViewMode.fav_manager:

            url = inter.text_values["user_fav_url"].strip()

            try:
                valid_url = URL_REG.findall(url)[0]
            except IndexError:
                await inter.send(
                    embed=disnake.Embed(
                        description=f"**Nenhum link válido encontrado:** {url}",
                        color=disnake.Color.red()
                    ), ephemeral=True
                )
                return

            await inter.response.defer(ephemeral=True)

            self.view.data = await self.view.bot.get_global_data(inter.author.id, db_name=DBModel.users)

            name = inter.text_values["user_fav_name"].strip()

            try:
                if name != self.name:
                    del self.view.data["fav_links"][self.name]
            except KeyError:
                pass

            self.view.data["fav_links"][name] = valid_url

            await self.view.bot.update_global_data(inter.author.id, self.view.data, db_name=DBModel.users)

            try:
                me = (inter.guild or self.view.bot.get_guild(inter.guild_id)).me
            except AttributeError:
                me = None

            await inter.edit_original_message(
                embed=disnake.Embed(
                    description="**Link salvo/atualizado com sucesso nos seus favoritos!\n"
                                "Ele vai aparecer nas seguintes ocasições:** ```\n"
                                "- Ao usar o comando /play (selecionando no preenchimento automático da busca)\n"
                                "- Ao clicar no botão de tocar favorito do player.\n"
                                "- Ao usar o comando play (prefixed) sem nome ou link.```",
                    color=self.view.bot.get_color(me)
                )
            )

        elif self.view.mode == ViewMode.guild_fav_manager:
            url = inter.text_values["guild_fav_url"].strip()

            try:
                valid_url = URL_REG.findall(url)[0]
            except IndexError:
                await inter.send(
                    embed=disnake.Embed(
                        description=f"**Nenhum link válido encontrado:** {url}",
                        color=disnake.Color.red()
                    ), ephemeral=True
                )
                return

            await inter.response.defer(ephemeral=True)

            self.view.guild_data = await self.view.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

            if not self.view.guild_data["player_controller"]["channel"] or not self.bot.get_channel(
                    int(self.view.guild_data["player_controller"]["channel"])):
                await inter.edit_original_message("**Não há player configurado no servidor! Use o comando /setup**")
                return

            name = inter.text_values["guild_fav_name"].strip()
            description = inter.text_values["guild_fav_description"].strip()

            if not self.view.guild_data["player_controller"]["channel"] or not self.view.bot.get_channel(
                    int(self.view.guild_data["player_controller"]["channel"])):
                await inter.edit_original_message("**Não há player configurado no servidor! Use o comando /setup**")
                return

            try:
                if name != self.name:
                    del self.view.guild_data["player_controller"]["fav_links"][self.name]
            except KeyError:
                pass

            self.view.guild_data["player_controller"]["fav_links"][name] = {'url': valid_url, "description": description}

            await self.view.bot.update_data(inter.guild_id, self.view.guild_data, db_name=DBModel.guilds)

            guild = inter.guild or self.view.bot.get_guild(inter.guild_id)

            await inter.edit_original_message(
                embed=disnake.Embed(description="**Link adicionado/atualizado com sucesso nos fixos do player!\n"
                                                "Membros podem usá-lo diretamente no player-controller quando não estiver em uso.**",
                                    color=self.view.bot.get_color(guild.me)), view=None)

            await process_idle_embed(self.view.bot, guild, guild_data=self.view.guild_data)

        elif self.view.mode == ViewMode.integrations_manager:
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

                if not self.view.bot.spotify:
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
                    result = await self.view.bot.spotify.get_user(user_id)
                except Exception as e:
                    await inter.send(
                        embed=disnake.Embed(
                            description="**Ocorreu um erro ao obter informações do spotify:** ```py\n"
                                        f"{repr(e)}```",
                            color=self.view.bot.get_color()
                        )
                    )
                    traceback.print_exc()
                    return

                if not result:
                    await inter.send(
                        embed=disnake.Embed(
                            description="**O usuário do link informado não possui playlists públicas...**",
                            color=self.view.bot.get_color()
                        )
                    )
                    return

                data = {"title": f"[SP]: {result.name[:90]}", "url": url}

            else:

                if not self.view.bot.config["USE_YTDL"]:
                    await inter.send(
                        embed=disnake.Embed(
                            description="**Não há suporte a esse tipo de link no momento...**",
                            color=self.view.bot.get_color()
                        )
                    )
                    return

                match = re.search(youtube_regex, url)

                if match:
                    base_url = f"{match.group(0)}/playlists"
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

                loop = self.view.bot.loop or asyncio.get_event_loop()

                try:
                    await inter.response.defer(ephemeral=True)
                except:
                    pass

                try:
                    info = await loop.run_in_executor(None, lambda: self.view.bot.pool.ytdl.extract_info(base_url, download=False))
                except Exception as e:
                    traceback.print_exc()
                    await inter.edit_original_message(f"**Ocorreu um erro ao obter informação da url:** ```py\n{repr(e)}```")
                    return

                if not info:

                    msg = f"**O usuário/canal do link informado não existe:**\n{url}"

                    if source == "[YT]:":
                        msg += f"\n\n`Nota: Confira se no link contém usuário com @, ex: @ytchannel`"

                    await inter.edit_original_message(
                        embed=disnake.Embed(
                            description=msg,
                            color=disnake.Color.red()
                        )
                    )
                    return

                if not info['entries']:
                    await inter.edit_original_message(
                        embed=disnake.Embed(
                            description=f"**O usuário/canal do link informado não possui playlists públicas...**",
                            color=disnake.Color.red()
                        )
                    )
                    return

                data = {"title": f"{source} {info['title']}", "url": info["original_url"]}

            self.view.data = await self.view.bot.get_global_data(inter.author.id, db_name=DBModel.users)

            title = fix_characters(data['title'], 80)

            self.view.data["integration_links"][title] = data['url']

            await self.view.bot.update_global_data(inter.author.id, self.view.data, db_name=DBModel.users)

            try:
                me = (inter.guild or self.view.bot.get_guild(inter.guild_id)).me
            except AttributeError:
                me = None

            await inter.edit_original_message(
                embed=disnake.Embed(
                    description=f"**Integração adicionada/editada com sucesso:** [`{title}`]({data['url']})\n"
                                "**Ela vai aparecer nas seguintes ocasições:** ```\n"
                                "- Ao usar o comando /play (selecionando a integração no preenchimento automático da busca)\n"
                                "- Ao clicar no botão de tocar favorito do player.\n"
                                "- Ao usar o comando play (prefixed) sem nome ou link.```",
                    color=self.view.bot.get_color(me)
                ), view=None
            )

            self.view.log = f"[`{data['title']}`]({data['url']}) foi adicionado nas suas integrações."

        if not isinstance(self.view.ctx, CustomContext):
            await self.view.ctx.edit_original_message(embed=self.view.build_embed(), view=self.view)
        elif self.view.message:
            await self.view.message.edit(embed=self.view.build_embed(), view=self.view)

class FavMenuView(disnake.ui.View):

    def __init__(self, bot: BotCore, ctx: Union[disnake.AppCmdInter, CustomContext], data: dict, log: str = "",
                 prefix="", mode: str = ViewMode.fav_manager):
        super().__init__(timeout=180)
        self.mode = mode
        self.bot = bot
        self.ctx = ctx
        self.current = None
        self.data = data
        self.guild_data = {}
        self.message = None
        self.log = log
        self.prefix = prefix
        self.components_updater_task = bot.loop.create_task(self.auto_update())

    def update_components(self):

        self.clear_items()

        mode_select = disnake.ui.Select(
            options=[
                disnake.SelectOption(label="Gerenciador de Favoritos", value="fav_view_mode_0", emoji="⭐",
                                     default=self.mode == ViewMode.fav_manager),
                disnake.SelectOption(label="Gerenciador de Integrações", value="fav_view_mode_2", emoji="💠",
                                     default=self.mode == ViewMode.integrations_manager)
            ], min_values=1, max_values=1
        )

        if self.ctx.author.guild_permissions.manage_guild:
            mode_select.options.insert(1, disnake.SelectOption(label="Gerenciador de Playlists do Servidor",
                                                               value="fav_view_mode_1", emoji="📌",
                                                               default=self.mode == ViewMode.guild_fav_manager))

        mode_select.callback = self.mode_callback
        self.add_item(mode_select)

        if self.mode == ViewMode.fav_manager:

            if self.data["fav_links"]:
                fav_select = disnake.ui.Select(options=[
                    disnake.SelectOption(label=k, emoji=music_source_emoji_url(v)) for k, v in
                    self.data["fav_links"].items()
                ], min_values=1, max_values=1)
                fav_select.options[0].default = True
                self.current = fav_select.options[0].label
                fav_select.callback = self.select_callback
                self.add_item(fav_select)

        elif self.mode == ViewMode.guild_fav_manager:

            bots_in_guild = []

            for b in sorted(self.bot.pool.bots, key=lambda b: b.identifier):
                if b.bot_ready and b.user in self.ctx.guild.members:
                    bots_in_guild.append(disnake.SelectOption(emoji="🎶",
                                                              label=f"Bot: {b.user.display_name}"[:25],
                                                              value=f"bot_select_{b.user.id}",
                                                              description=f"ID: {b.user.id}", default=b == self.bot))

            if bots_in_guild:
                bot_select = disnake.ui.Select(options=bots_in_guild, min_values=1, max_values=1)
                bot_select.callback = self.bot_select
                self.add_item(bot_select)

            if self.guild_data["player_controller"]["fav_links"]:
                fav_select = disnake.ui.Select(options=[
                    disnake.SelectOption(label=k, emoji=music_source_emoji_url(v['url']),
                                         description=v.get("description")) for k, v in
                    self.guild_data["player_controller"]["fav_links"].items()
                ], min_values=1, max_values=1)
                fav_select.options[0].default = True
                self.current = fav_select.options[0].label
                fav_select.callback = self.select_callback
                self.add_item(fav_select)

        elif self.mode == ViewMode.integrations_manager:

            if self.data["integration_links"]:

                integration_select = disnake.ui.Select(options=[
                    disnake.SelectOption(label=k, emoji=music_source_emoji_id(k)) for k, v in self.data["integration_links"].items()
                ], min_values=1, max_values=1)
                integration_select.options[0].default = True
                self.current = integration_select.options[0].label
                integration_select.callback = self.select_callback
                self.add_item(integration_select)

        add_button = disnake.ui.Button(label="Adicionar", emoji="<:add_music:588172015760965654>")
        add_button.callback = self.add_callback
        self.add_item(add_button)

        if self.mode == ViewMode.fav_manager:
            edit_button = disnake.ui.Button(label="Editar", emoji="✍️", disabled=not self.data["fav_links"])
            edit_button.callback = self.edit_callback
            self.add_item(edit_button)

            remove_button = disnake.ui.Button(label="Remover", emoji="♻️", disabled=not self.data["fav_links"])
            remove_button.callback = self.remove_callback
            self.add_item(remove_button)

            clear_button = disnake.ui.Button(label="Limpar favoritos", emoji="🚮", disabled=not self.data["fav_links"])
            clear_button.callback = self.clear_callback
            self.add_item(clear_button)

            export_button = disnake.ui.Button(label="Exportar", emoji="📤", disabled=not self.data["fav_links"])
            export_button.callback = self.export_callback
            self.add_item(export_button)

        elif self.mode == ViewMode.guild_fav_manager:
            edit_button = disnake.ui.Button(label="Editar", emoji="✍️", disabled=not self.guild_data["player_controller"]["fav_links"])
            edit_button.callback = self.edit_callback
            self.add_item(edit_button)

            remove_button = disnake.ui.Button(label="Remover", emoji="♻️", disabled=not self.guild_data["player_controller"]["fav_links"])
            remove_button.callback = self.remove_callback
            self.add_item(remove_button)

            clear_button = disnake.ui.Button(label="Limpar favoritos", emoji="🚮", disabled=not self.guild_data["player_controller"]["fav_links"])
            clear_button.callback = self.clear_callback
            self.add_item(clear_button)

            export_button = disnake.ui.Button(label="Exportar", emoji="📤", disabled=not self.guild_data["player_controller"]["fav_links"])
            export_button.callback = self.export_callback
            self.add_item(export_button)

        elif self.mode == ViewMode.integrations_manager:
            remove_button = disnake.ui.Button(label="Remover", emoji="♻️", disabled=not self.data["integration_links"])
            remove_button.callback = self.remove_callback
            self.add_item(remove_button)

            clear_button = disnake.ui.Button(label="Limpar Integrações", emoji="🚮", disabled=not self.data["integration_links"])
            clear_button.callback = self.clear_callback
            self.add_item(clear_button)

            export_button = disnake.ui.Button(label="Exportar", emoji="📤", disabled=not self.data["integration_links"])
            export_button.callback = self.export_callback
            self.add_item(export_button)

        import_button = disnake.ui.Button(label="Importar", emoji="📥")
        import_button.callback = self.import_callback
        self.add_item(import_button)

        if self.mode == ViewMode.fav_manager:
            play_button = disnake.ui.Button(label="Tocar o favorito selecionado", emoji="▶", custom_id="favmanager_play_button")
            play_button.callback = self.play_callback
            self.add_item(play_button)

        elif self.mode == ViewMode.integrations_manager:
            if self.data["integration_links"]:
                play_button = disnake.ui.Button(label="Tocar uma playlist da integração selecionada", emoji="▶", custom_id="favmanager_play_button")
                play_button.callback = self.play_callback
                self.add_item(play_button)

        cancel_button = disnake.ui.Button(label="Fechar", emoji="❌")
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)

    async def auto_update(self):

        while True:

            if self.mode != ViewMode.fav_manager:
                return

            user, data, url = await self.bot.wait_for("fav_add", check=lambda user, data, url: user.id == self.ctx.author.id)

            self.log = f"{url} foi adicionado nos seus favoritos."

            if not isinstance(self.ctx, CustomContext):
                await self.ctx.edit_original_message(embed=self.build_embed(), view=self)
            elif self.message:
                await self.message.edit(embed=self.build_embed(), view=self)

    async def on_timeout(self):

        try:
            self.components_updater_task.cancel()
        except:
            pass

        try:
            for i in self.children[1].options:
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

    def build_embed(self):

        supported_platforms = []

        if self.mode == ViewMode.integrations_manager:

            if self.bot.config["USE_YTDL"]:
                supported_platforms.extend(["[31;1mYoutube[0m", "[33;1mSoundcloud[0m"])

            if self.bot.spotify:
                supported_platforms.append("[32;1mSpotify[0m")

            if not supported_platforms:
                return

        self.update_components()

        try:
            cmd = f"</play:" + str(self.bot.pool.controller_bot.get_global_command_named("play", cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"
        except AttributeError:
            cmd = "/play"

        if self.mode == ViewMode.fav_manager:
            embed = disnake.Embed(
                title="Gerenciador de favoritos.",
                colour=self.bot.get_color(),
            )

            if not self.data["fav_links"]:
                embed.description = "Você não possui favoritos (clique no botão de adicionar abaixo)."

            else:
                embed.description = f"**Seus favoritos atuais:**\n\n" + "\n".join(
                    f"> ` {n + 1} ` [`{f[0]}`]({f[1]})" for n, f in enumerate(self.data["fav_links"].items())
                )

            embed.add_field(name="**Como usá-los?**", inline=False,
                            value=f"* Usando o comando {cmd} (selecionando o favorito no preenchimento automático da busca)\n"
                                  "* Clicando no botão/select de tocar favorito/integração do player.\n"
                                  f"* Usando o comando {self.prefix}{self.bot.get_cog('Music').play_legacy.name} sem incluir um nome ou link de uma música/vídeo.\n"
                                  "* Usando o botão de tocar favorito abaixo.")

        elif self.mode == ViewMode.guild_fav_manager:
            embed = disnake.Embed(
                title="Gerenciador de favoritos do servidor.",
                colour=self.bot.get_color(),
            )
            embed.set_author(name=f"Bot selecionado: {self.bot.user.display_name}", icon_url=self.bot.user.display_avatar.url)

            if not self.guild_data["player_controller"]["fav_links"]:
                embed.description = f"Não há links adicionados no bot {self.bot.user.mention} (clique no botão de adicionar abaixo)."

            else:
                embed.description = f"**Links atuais no bot {self.bot.user.mention}:**\n\n" + "\n".join(
                    f"> ` {n + 1} ` [`{f[0]}`]({f[1]['url']})" for n, f in enumerate(self.guild_data["player_controller"]["fav_links"].items())
                )

            embed.add_field(name="**Como usá-los?**", inline=False,
                            value=f"* Usando o menu de seleção do player durante o modo de espera.")

        elif self.mode == ViewMode.integrations_manager:
            embed = disnake.Embed(
                title="Gerenciador de integrações de canais/perfis com playlists públicas.",
                colour=self.bot.get_color(),
            )

            if not self.data["integration_links"]:
                embed.description = "**Você não possui integrações no momento (clique no botão de adicionar abaixo).**"

            else:
                embed.description = f"**Suas integrações atuais:**\n\n" + "\n".join(
                    f"> ` {n + 1} ` [`{f[0]}`]({f[1]})" for n, f in enumerate(self.data["integration_links"].items()))

                embed.add_field(name="**Como tocar a playlist de uma integração?**", inline=False,
                                value=f"* Usando o comando {cmd} (no preenchimento automático da busca)\n"
                                      "* Clicando no botão/select de tocar favorito/integração do player.\n"
                                      f"* Usando o comando {self.prefix}{self.bot.get_cog('Music').play_legacy.name} sem incluir um nome ou link de uma música/vídeo.\n"
                                      "* Usando o botão de tocar integração abaixo.")

        else:
            raise GenericError(f"**Modo não implementado:** {self.mode}")

        if self.log:
            embed.add_field(name="Última interação:", value=self.log)

        if self.mode == ViewMode.integrations_manager:
            embed.add_field(
                name="Links de perfis/canais suportados:", inline=False,
                value=f"```ansi\n{', '.join(supported_platforms)}```"
            )
        return embed

    async def add_callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(FavModalAdd(name=None, url=None, view=self))

    async def edit_callback(self, inter: disnake.MessageInteraction):

        if not self.current:
            await inter.send("Você deve selecionar um item!", ephemeral=True)
            return

        if self.mode == ViewMode.fav_manager:
            try:
                await inter.response.send_modal(
                    FavModalAdd(name=self.current, url=self.data["fav_links"][self.current], view=self)
                )
            except KeyError:
                await inter.send(f"**Não há favorito com o nome:** {self.current}", ephemeral=True)

        elif self.mode == ViewMode.guild_fav_manager:
            guild = self.bot.get_guild(inter.guild_id) or inter.guild

            if not guild:
                await inter.send("Você não pode executar essa ação fora de um servidor.", ephemeral=True)
                return
            try:
                await inter.response.send_modal(
                    FavModalAdd(
                        bot=self.bot, name=self.current,
                        url=self.data["player_controller"]["fav_links"][self.current]["url"],
                        description=self.data["player_controller"]["fav_links"][self.current]["description"],
                        view=self
                    )
                )
            except KeyError:
                await inter.send(f"**Não há favorito com nome:** {self.current}", ephemeral=True)

    async def remove_callback(self, inter: disnake.MessageInteraction):

        if not self.current:
            await inter.send("Você deve selecionar um item!", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        guild = None

        if self.mode == ViewMode.guild_fav_manager:

            guild = self.bot.get_guild(inter.guild_id)

            if not guild:
                await inter.send("Você não pode executar essa ação fora de um servidor.", ephemeral=True)
                return

            if not self.guild_data:
                self.guild_data = await self.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        else:
            try:
                self.data = inter.global_user_data
            except AttributeError:
                self.data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
                inter.global_user_data = self.data

        if self.mode == ViewMode.fav_manager:
            try:
                url = f'[`{self.current}`]({self.data["fav_links"][self.current]})'
                del self.data["fav_links"][self.current]
            except:
                await inter.edit_original_message(f"**Não há favorito na lista com o nome:** {self.current}")
                return

            await self.bot.update_global_data(inter.author.id, self.data, db_name=DBModel.users)

            self.log = f"Favorito {url} foi removido com sucesso!"

        elif self.mode == ViewMode.guild_fav_manager:
            try:
                url = f'[`{self.current}`]({self.guild_data["player_controller"]["fav_links"][self.current]})'
                del self.guild_data["player_controller"]["fav_links"][self.current]
            except KeyError:
                try:
                    await process_idle_embed(self.bot, guild, guild_data=self.guild_data)
                except Exception:
                    traceback.print_exc()

                await inter.edit_original_message(
                    embed=disnake.Embed(
                        description=f"**Não há links da lista com o nome:** {self.current}",
                        color=self.bot.get_color(guild.me)),
                    view=None
                )
                return

            await self.bot.update_data(inter.guild_id, self.guild_data, db_name=DBModel.guilds)

            self.log = f"Link {url} foi removido com sucesso da lista de favoritos do servidor!"

        elif self.mode == ViewMode.integrations_manager:
            try:
                url = f'[`{self.current}`]({self.data["integration_links"][self.current]})'
                del self.data["integration_links"][self.current]
            except:
                await inter.send(f"**Não há integração na lista com o nome:** {self.current}", ephemeral=True)
                return

            await self.bot.update_global_data(inter.author.id, self.data, db_name=DBModel.users)

            self.log = f"Integração {url} foi removida com sucesso!"

        await inter.edit_original_message(embed=self.build_embed(), view=self)

    async def bot_select(self, inter: disnake.MessageInteraction):

        value = int(inter.values[0][11:])
        for b in self.bot.pool.bots:
            try:
                if b.user.id == value:
                    self.bot = b
                    break
            except AttributeError:
                continue

        self.guild_data = await self.bot.get_data(inter.guild.id, db_name=DBModel.guilds)

        await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def clear_callback(self, inter: disnake.MessageInteraction):

        guild = None

        if self.mode == ViewMode.guild_fav_manager:

            guild = self.bot.get_guild(inter.guild_id) or inter.guild

            if not guild:
                await inter.send("Você não pode executar essa ação fora de um servidor.", ephemeral=True)
                return

            await inter.response.defer(ephemeral=True)

            if not self.guild_data:
                self.guild_data = await self.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        else:

            await inter.response.defer(ephemeral=True)

            try:
                self.data = inter.global_user_data
            except AttributeError:
                self.data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
                inter.global_user_data = self.data


        if self.mode == ViewMode.fav_manager:
            if not self.data["fav_links"]:
                await inter.send("**Você não possui links favoritos!**", ephemeral=True)
                return

            fp = BytesIO(bytes(json.dumps(self.data["fav_links"], indent=4), 'utf-8'))

            self.data["fav_links"].clear()

            await self.bot.update_global_data(inter.author.id, self.data, db_name=DBModel.users)

            self.log = "Sua lista de favoritos foi limpa com sucesso!"

            await inter.send("### Seus favoritos foram excluídos com sucesso!\n"
                             "`Um arquivo de backup foi gerado e caso queira reverter essa exclusão, copie o "
                             "conteúdo do arquivo e clique no botão \"importar\" e cole o conteudo no campo indicado.`",
                             ephemeral=True, file=disnake.File(fp, filename="favs.json"))

        elif self.mode == ViewMode.guild_fav_manager:

            if not self.guild_data["player_controller"]["fav_links"]:
                await inter.send("**Não há links favoritos no servidor.**", ephemeral=True)
                return

            fp = BytesIO(bytes(json.dumps(self.guild_data["player_controller"]["fav_links"], indent=4), 'utf-8'))

            self.guild_data["player_controller"]["fav_links"].clear()

            await self.bot.update_data(inter.guild_id, self.guild_data, db_name=DBModel.guilds)

            try:
                await process_idle_embed(self.bot, guild, guild_data=self.guild_data)
            except:
                traceback.print_exc()

            self.log = "Lista de favoritos do server foi limpa com sucesso!"

            await inter.send("### Os links de favoritos do server foram excluídos com sucesso!\n"
                             "`um arquivo de backup foi gerado e caso queira reverter essa exclusão, copie o "
                             "conteúdo do arquivo e clique no botão \"importar\" e cole o conteudo no campo indicado.`",
                             ephemeral=True, file=disnake.File(fp, filename="guild_favs.json"))

        elif self.mode == ViewMode.integrations_manager:

            if not self.data["integration_links"]:
                await inter.response.edit_message(content="**Você não possui integrações salvas!**", view=None)
                return

            fp = BytesIO(bytes(json.dumps(self.data["integration_links"], indent=4), 'utf-8'))

            self.data["integration_links"].clear()

            await self.bot.update_global_data(inter.author.id, self.data, db_name=DBModel.users)

            self.log = "Sua lista de integrações foi limpa com sucesso!"

            await inter.send("### Suas integrações foram excluídas com sucesso!\n"
                             "`um arquivo de backup foi gerado e caso queira reverter essa exclusão, copie o "
                             "conteúdo do arquivo e clique no botão \"importar\" e cole o conteudo no campo indicado.`",
                             ephemeral=True, file=disnake.File(fp, filename="integrations.json"))

        if not isinstance(self.ctx, CustomContext):
            await self.ctx.edit_original_message(embed=self.build_embed(), view=self)
        elif self.message:
            await self.message.edit(embed=self.build_embed(), view=self)

    async def import_callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(FavModalImport(view=self))

    async def play_callback(self, inter: disnake.MessageInteraction):
        await check_pool_bots(inter, check_player=False)
        await self.bot.get_cog("Music").player_controller(inter, PlayerControls.enqueue_fav, query=f"> itg: {self.current}" if self.mode == ViewMode.integrations_manager else f"> fav: {self.current}")

    async def export_callback(self, inter: disnake.MessageInteraction):
        cog = self.bot.get_cog("Music")

        if retry_after := cog.fav_import_export_cd.get_bucket(inter).update_rate_limit():
            if retry_after < 1:
                retry_after = 1
            await inter.send("**Você deve aguardar {} para exportar.**".format(
                time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        try:
            cmd = f"</{cog.fav_manager.name}:" + str(
                self.bot.pool.controller_bot.get_global_command_named(cog.fav_manager.name,
                                                                      cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"
        except AttributeError:
            cmd = "/play"

        if self.mode == ViewMode.fav_manager:
            if not self.data["fav_links"]:
                await inter.send(f"**Você não possui links favoritos..\n"
                                 f"Você pode adicionar usando o comando: {cmd}**", ephemeral=True)
                return

            fp = BytesIO(bytes(json.dumps(self.data["fav_links"], indent=4), 'utf-8'))

            await inter.send(embed=disnake.Embed(
                description=f"Seus favoritos estão aqui.\nVocê pode importar usando o comando: {cmd}",
                color=self.bot.get_color()), file=disnake.File(fp=fp, filename="favoritos.json"), ephemeral=True)

        elif self.mode == ViewMode.guild_fav_manager:
            if not self.guild_data["player_controller"]["fav_links"]:
                await inter.edit_original_message(content=f"**Não há músicas/playlists fixadas no servidor..\n"
                                                          f"Você pode adicionar usando o comando: {cmd}**")

            fp = BytesIO(bytes(json.dumps(self.guild_data["player_controller"]["fav_links"], indent=4), 'utf-8'))

            guild = self.bot.get_guild(inter.guild_id) or inter.guild

            embed = disnake.Embed(
                description=f"**Os dados dos links de músicas/playlists fixas do servidor estão aqui.\n"
                            f"Você pode importar usando o comando:** {cmd}",
                color=self.bot.get_color(guild.me))

            await inter.send(embed=embed, file=disnake.File(fp=fp, filename="guild_favs.json"), ephemeral=True)

        elif self.mode == ViewMode.integrations_manager:

            if not self.data["integration_links"]:
                await inter.edit_original_message(f"**Você não possui integrações adicionadas...\n"
                                                  f"Você pode adicionar usando o comando: {cmd}**")
                return

            fp = BytesIO(bytes(json.dumps(self.data["integration_links"], indent=4), 'utf-8'))

            await inter.send(embed=disnake.Embed(
                description=f"Suas integrações estão aqui.\nVocê pode importar usando o comando: {cmd}",
                color=self.bot.get_color()), file=disnake.File(fp=fp, filename="integrations.json"), ephemeral=True)

    async def cancel_callback(self, inter: disnake.MessageInteraction):

        try:
            self.components_updater_task.cancel()
        except:
            pass

        await inter.response.edit_message(
            embed=disnake.Embed(
                description="**Gerenciador fechado.**",
                color=self.bot.get_color(),
            ), view=None
        )
        self.stop()

    async def mode_callback(self, inter: disnake.MessageInteraction):
        self.mode = inter.values[0][14:]

        try:
            self.components_updater_task.cancel()
        except:
            pass

        if self.mode == ViewMode.fav_manager:
            self.components_updater_task = self.bot.loop.create_task(self.auto_update())

        elif self.mode == ViewMode.guild_fav_manager:
            if not self.guild_data:
                await inter.response.defer()
                self.guild_data = await self.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        if inter.response.is_done():
            await inter.edit_original_message(embed=self.build_embed(), view=self)
        else:
            await inter.response.edit_message(embed=self.build_embed(), view=self)

    async def select_callback(self, inter: disnake.MessageInteraction):
        self.current = inter.values[0]
        await inter.response.defer()

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:

        if inter.author.id == self.ctx.author.id:
            return True

        await inter.send(f"Apenas o membro {self.ctx.author.mention} pode interagir nessa mensagem.", ephemeral=True)
