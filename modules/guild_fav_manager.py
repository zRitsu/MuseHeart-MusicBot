# -*- coding: utf-8 -*-
from __future__ import annotations

from io import BytesIO
import json
import traceback
from typing import TYPE_CHECKING, Union, Optional

import disnake
from disnake.ext import commands

from utils.music.converters import URL_REG, time_format
from utils.music.models import LavalinkPlayer
from utils.others import send_idle_embed, select_bot_pool, CustomContext, music_source_emoji_url
from utils.db import DBModel

if TYPE_CHECKING:
    from utils.client import BotCore


class GuildFavModal(disnake.ui.Modal):
    def __init__(self, bot: BotCore, name: Optional[str], description: Optional[str], url: Optional[str]):

        self.bot = bot
        self.name = name

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
                    value=description or None,
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

    async def callback(self, inter: disnake.ModalInteraction):

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

        guild_data = await self.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        if not guild_data["player_controller"]["channel"] or not self.bot.get_channel(int(guild_data["player_controller"]["channel"])):
            await inter.edit_original_message("**Não há player configurado no servidor! Use o comando /setup**")
            return

        name = inter.text_values["guild_fav_name"].strip()
        description = inter.text_values["guild_fav_description"].strip()

        if not guild_data["player_controller"]["channel"] or not self.bot.get_channel(
                int(guild_data["player_controller"]["channel"])):
            await inter.edit_original_message("**Não há player configurado no servidor! Use o comando /setup**")
            return

        try:
            if name != self.name:
                del guild_data["player_controller"]["fav_links"][self.name]
        except KeyError:
            pass

        guild_data["player_controller"]["fav_links"][name] = {'url': valid_url, "description": description}

        await self.bot.update_data(inter.guild_id, guild_data, db_name=DBModel.guilds)

        guild = inter.guild or self.bot.get_guild(inter.guild_id)

        await inter.edit_original_message(embed=disnake.Embed(description="**Link adicionado/atualizado com sucesso nos fixos do player!\n"
                         "Membros podem usá-lo diretamente no player-controller quando não estiver em uso.**",
                                                              color=self.bot.get_color(guild.me)), view=None)

        await self.bot.get_cog("PinManager").process_idle_embed(self.bot, guild, guild_data=guild_data)

class GuildFavView(disnake.ui.View):

    def __init__(self, bot: BotCore, ctx: Union[disnake.AppCmdInter, CustomContext], data: dict):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.current = None
        self.data = data
        self.message = None

        if data["player_controller"]["fav_links"]:

            fav_select = disnake.ui.Select(options=[
                disnake.SelectOption(label=k, emoji=music_source_emoji_url(v['url']),description=v.get("description")) for k, v in data["player_controller"]["fav_links"].items()
            ], min_values=1, max_values=1)
            fav_select.options[0].default = True
            self.current = fav_select.options[0].label
            fav_select.callback = self.select_callback
            self.add_item(fav_select)

        favadd_button = disnake.ui.Button(label="Adicionar", emoji="📌")
        favadd_button.callback = self.favadd_callback
        self.add_item(favadd_button)

        if data["player_controller"]["fav_links"]:

            edit_button = disnake.ui.Button(label="Editar", emoji="✍️")
            edit_button.callback = self.edit_callback
            self.add_item(edit_button)

            remove_button = disnake.ui.Button(label="Remover", emoji="♻️")
            remove_button.callback = self.remove_callback
            self.add_item(remove_button)

            clear_button = disnake.ui.Button(label="Limpar favoritos", emoji="🚮")
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

    async def favadd_callback(self, inter: disnake.MessageInteraction):

        guild = self.bot.get_guild(inter.guild_id) or inter.guild

        if not guild:
            await inter.send("Você não pode executar essa ação fora de um servidor.", ephemeral=True)
            return

        await inter.response.send_modal(GuildFavModal(bot=self.bot, name=None, url=None, description=None))
        await inter.delete_original_message()
        self.stop()

    async def edit_callback(self, inter: disnake.MessageInteraction):

        guild = self.bot.get_guild(inter.guild_id) or inter.guild

        if not guild:
            await inter.send("Você não pode executar essa ação fora de um servidor.", ephemeral=True)
            return

        if not self.current:
            await inter.send("Você deve selecionar um item!", ephemeral=True)
            return

        try:
            await inter.response.send_modal(
                GuildFavModal(
                    bot=self.bot, name=self.current,
                    url=self.data["player_controller"]["fav_links"][self.current]["url"],
                    description=self.data["player_controller"]["fav_links"][self.current]["description"]
                )
            )
        except KeyError:
            await inter.send(f"**Não há favorito com nome:** {self.current}", ephemeral=True)
            return

        if isinstance(self.ctx, disnake.AppCmdInter):
            await self.ctx.delete_original_message()
        else:
            await inter.message.delete()
        self.stop()

    async def remove_callback(self, inter: disnake.MessageInteraction):

        guild = self.bot.get_guild(inter.guild_id)

        if not guild:
            await inter.send("Você não pode executar essa ação fora de um servidor.", ephemeral=True)
            return

        if not self.current:
            await inter.send("Você deve selecionar um item!", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        guild_data = await self.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        try:
            del guild_data["player_controller"]["fav_links"][self.current]
        except KeyError:
            try:
                await self.bot.get_cog("PinManager").process_idle_embed(self.bot, guild, guild_data=guild_data)
            except Exception:
                traceback.print_exc()

            await inter.edit_original_message(
                embed=disnake.Embed(
                    description=f"**Não há links da lista com o nome:** {self.current}",
                    color=self.bot.get_color(guild.me)),
                view=None
            )

        await self.bot.update_data(inter.guild_id, guild_data, db_name=DBModel.guilds)

        await inter.edit_original_message(
            embed=disnake.Embed(description="**Link removido com sucesso!**", color=self.bot.get_color(guild.me)),
            view=None)

        await self.bot.get_cog("PinManager").process_idle_embed(self.bot, guild, guild_data=guild_data)
        self.stop()

    async def clear_callback(self, inter: disnake.MessageInteraction):

        guild = self.bot.get_guild(inter.guild_id) or inter.guild

        if not guild:
            await inter.send("Você não pode executar essa ação fora de um servidor.", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        guild_data = await self.bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        if not guild_data["player_controller"]["fav_links"]:
            await inter.send("**Não há links favoritos no servidor.**", ephemeral=True)
            return

        guild_data["player_controller"]["fav_links"].clear()

        await self.bot.update_data(inter.guild_id, guild_data, db_name=DBModel.guilds)

        embed = disnake.Embed(
            description="Os favoritos do server foram removidos com sucesso.",
            color=self.bot.get_color()
        )

        await inter.edit_original_message(embed=embed, components=None)

        await self.bot.get_cog("PinManager").process_idle_embed(self.bot, guild, guild_data=guild_data)
        self.stop()

    async def import_callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(
            title="Importar Playlists para o Servidor",
            custom_id="guild_fav_import",
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
        await self.bot.get_cog("PinManager").export_(inter)
        self.stop()

    async def cancel_callback(self, inter: disnake.MessageInteraction):
        await inter.response.edit_message(
            embed=disnake.Embed(
                description="**Operação com favoritos do servidor cancelada...**",
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


class PinManager(commands.Cog):

    emoji = "📌"
    name = "Server Playlist"
    desc_prefix = f"[{emoji} {name}] | "

    def __init__(self, bot: BotCore):
        self.bot = bot

    async def process_idle_embed(self, bot: BotCore, guild: disnake.Guild, guild_data: dict):

        try:
            player: LavalinkPlayer = bot.music.players[guild.id]
            #if not player.current:
            #    await player.process_idle_message()
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

    server_playlist_cd = commands.CooldownMapping.from_cooldown(3, 30, commands.BucketType.guild)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(name="serverplaylist", aliases=["spl", "svp", "svpl"],
                      description="Gerenciar playlists/favoritos do servidor.",
                      cooldown=server_playlist_cd)
    async def serverplaylist_legacy(self, ctx: CustomContext):
        await self.server_playlist.callback(self=self, interaction=ctx)

    @commands.max_concurrency(1, commands.BucketType.guild, wait=False)
    @commands.slash_command(
        description=f"{desc_prefix}Gerenciar playlists/favoritos do servidor.",
        default_member_permissions=disnake.Permissions(manage_guild=True),
        cooldown=server_playlist_cd, dm_permission=False
    )
    async def server_playlist(self, interaction: disnake.AppCmdInter):

        inter, bot = await select_bot_pool(interaction)

        if not bot:
            return

        await inter.response.defer(ephemeral=True)

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        view = GuildFavView(bot=bot, ctx=inter, data=guild_data)

        embed = disnake.Embed(
            description="**Gerenciador de favoritos do servidor.**",
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

    @commands.Cog.listener("on_modal_submit")
    async def modal_import(self, inter: disnake.ModalInteraction):

        if inter.custom_id != "guild_fav_import":
            return

        if not inter.guild_id:
            await inter.send("Você não pode executar isso no DM.", ephemeral=True)
            return

        inter, bot = select_bot_pool(inter)

        try:
            json_data = json.loads(inter.text_values["json_data"])
        except Exception as e:
            await inter.send("**Ocorreu um erro ao analisar os dados ou foi enviado dados inválidos/não-formatado "
                               f"em formato json.**\n\n`{repr(e)}`", ephemeral=True)
            return

        if retry_after:=self.server_playlist_cd.get_bucket(inter).update_rate_limit():
            if retry_after < 1:
                retry_after = 1
            await inter.send("**Você deve aguardar {} para importar.**".format(
                time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
            return

        for name, data in json_data.items():

            if "> fav:" in name.lower():
                continue

            if len(data['url']) > (max_url_chars := bot.config["USER_FAV_MAX_URL_LENGTH"]):
                await inter.send(f"**Um item de seu arquivo ultrapassa a quantidade de caracteres permitido:{max_url_chars}\nURL:** {data['url']}", ephemeral=True)
                return

            if len(data['description']) > 50:
                await inter.send(f"**Um item de seu arquivo ultrapassa a quantidade de caracteres permitido:{max_url_chars}\nDescrição:** {data['description']}", ephemeral=True)
                return

            if not isinstance(data['url'], str) or not URL_REG.match(data['url']):
                await inter.send(f"O seu arquivo contém link inválido: ```ldif\n{data['url']}```", ephemeral=True)
                return

        await inter.response.defer(ephemeral=True)

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        if not guild_data["player_controller"]["channel"] or not bot.get_channel(int(guild_data["player_controller"]["channel"])):
            await inter.edit_original_message("**Não há player configurado no servidor! Use o comando /setup**")
            return

        for name in json_data.keys():
            if len(name) > (max_name_chars := 25):
                await inter.edit_original_message(f"**Um item de seu arquivo ({name}) ultrapassa a quantidade de caracteres permitido:{max_name_chars}**")
                return
            try:
                del guild_data["player_controller"]["fav_links"][name]
            except KeyError:
                continue

        if (json_size:=len(json_data)) > 25:
            await inter.edit_original_message(f"A quantidade de itens no arquivo excede a quantidade máxima permitida (25).")
            return

        if (json_size + (user_favs:=len(guild_data["player_controller"]["fav_links"]))) > 25:
            await inter.edit_original_message("A lista de músicas/playlist do servidor não possui espaço suficiente para adicionar todos os itens de seu arquivo...\n"
                                f"Limite atual: 25\n"
                                f"Quantidade de links salvos: {user_favs}\n"
                                f"Você precisa de: {(json_size + user_favs)-25}")
            return

        guild_data["player_controller"]["fav_links"].update(json_data)

        await bot.update_data(inter.guild_id, guild_data, db_name=DBModel.guilds)

        guild = bot.get_guild(inter.guild_id)

        try:
            cmd = f"</play:" + str(self.bot.pool.controller_bot.get_global_command_named("play", cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"
        except AttributeError:
            cmd = "/play"

        await inter.edit_original_message(
            embed=disnake.Embed(
                color=self.bot.get_color(),
                description="**Os links foram importados com sucesso!**\n"
                            f"**Use o comando {cmd} para conferir (no preenchimento automático da busca).**",
            )
        )

        await self.process_idle_embed(bot, guild, guild_data=guild_data)

    async def export_(self, inter: disnake.MessageInteraction):

        inter, bot = await select_bot_pool(inter)

        if not bot:
            return

        if retry_after:=self.server_playlist_cd.get_bucket(inter).update_rate_limit():
            if retry_after < 1:
                retry_after = 1
            await inter.send("**Você deve aguardar {} para exportar.**".format(
                time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        try:
            cmd = f"</{self.server_playlist.name}:" + str(self.bot.pool.controller_bot.get_global_command_named(self.server_playlist.name, cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"
        except AttributeError:
            cmd = "/play"

        if not guild_data["player_controller"]["fav_links"]:
            await inter.edit_original_message(content=f"**Não há músicas/playlists fixadas no servidor..\n"
                               f"Você pode adicionar usando o comando: {cmd}**")

        fp = BytesIO(bytes(json.dumps(guild_data["player_controller"]["fav_links"], indent=4), 'utf-8'))

        guild = bot.get_guild(inter.guild_id) or inter.guild

        embed = disnake.Embed(
            description=f"**Os dados dos links de músicas/playlists fixas do servidor estão aqui.\n"
                        f"Você pode importar usando o comando:** {cmd}",
            color=self.bot.get_color(guild.me))

        await inter.edit_original_message(embed=embed, file=disnake.File(fp=fp, filename="guild_favs.json"), view=None)


def setup(bot: BotCore):
    bot.add_cog(PinManager(bot))
