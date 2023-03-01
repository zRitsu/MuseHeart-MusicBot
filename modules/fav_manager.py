from __future__ import annotations
from typing import TYPE_CHECKING, Union, Optional
from io import BytesIO
import json

import disnake
from disnake.ext import commands

from utils.db import DBModel
from utils.music.converters import URL_REG
from utils.others import CustomContext
from utils.music.errors import GenericError

if TYPE_CHECKING:
    from utils.client import BotCore


class UserFavModal(disnake.ui.Modal):
    def __init__(self, bot: BotCore, name: Optional[str], url: Optional[str]):

        self.bot = bot
        self.name = name

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

    async def callback(self, inter: disnake.ModalInteraction):

        url = inter.text_values["user_fav_url"]

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

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        name = inter.text_values["user_fav_name"]

        try:
            if name != self.name:
                del user_data["fav_links"][self.name]
        except KeyError:
            pass

        user_data["fav_links"][name] = valid_url

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        guild = inter.guild or self.bot.get_guild(inter.guild_id)

        await inter.edit_original_message(
            embed=disnake.Embed(
                description="**Link salvo/atualizado com sucesso nos seus favoritos!\n"
                            "Ele vai aparecer nas seguintes ocasições:** ```\n"
                            "- Ao usar o comando /play (no preenchimento automático da busca)\n"
                            "- Ao clicar no botão de pedir música do player.\n"
                            "- Ao usar o comando play (prefixed) sem nome ou link.```",
                color=self.bot.get_color(guild.me)
            )
        )

class UserFavView(disnake.ui.View):

    def __init__(self, bot: BotCore, ctx: Union[disnake.AppCmdInter, CustomContext], data: dict):
        super().__init__(timeout=60)
        self.bot = bot
        self.ctx = ctx
        self.current = None
        self.data = data
        self.message = None

        if data["fav_links"]:

            fav_select = disnake.ui.Select(options=[
                disnake.SelectOption(label=k) for k, v in data["fav_links"].items()
            ], min_values=1, max_values=1)
            fav_select.callback = self.select_callback
            self.add_item(fav_select)

        favadd_button = disnake.ui.Button(label="Adicionar", emoji="⭐")
        favadd_button.callback = self.favadd_callback
        self.add_item(favadd_button)

        if data["fav_links"]:

            edit_button = disnake.ui.Button(label="Editar", emoji="✍️")
            edit_button.callback = self.edit_callback
            self.add_item(edit_button)

            remove_button = disnake.ui.Button(label="Remover", emoji="♻️")
            remove_button.callback = self.remove_callback
            self.add_item(remove_button)

            clear_button = disnake.ui.Button(label="Limpar favoritos", emoji="🚮")
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

    async def favadd_callback(self, inter: disnake.MessageInteraction):
        await inter.response.send_modal(UserFavModal(bot=self.bot, name=None, url=None))
        await inter.delete_original_message()
        self.stop()

    async def edit_callback(self, inter: disnake.MessageInteraction):

        if not self.current:
            await inter.send("Você deve selecionar um item!", ephemeral=True)
            return

        try:
            await inter.response.send_modal(
                UserFavModal(
                    bot=self.bot, name=self.current,
                    url=self.data["fav_links"][self.current],
                )
            )
        except KeyError:
            await inter.send(f"**Não há favorito com o nome:** {self.current}", ephemeral=True)
            return

        if isinstance(self.ctx, disnake.AppCmdInter):
            await self.ctx.delete_original_message()
        else:
            await inter.message.delete()
        self.stop()

    async def remove_callback(self, inter: disnake.MessageInteraction):

        if not self.current:
            await inter.send("Você deve selecionar um item!", ephemeral=True)
            return

        await inter.response.defer(ephemeral=True)

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        try:
            del user_data["fav_links"][self.current]
        except:
            raise GenericError(f"**Não há favorito na lista com o nome:** {self.current}")

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        guild = self.bot.get_guild(inter.guild_id) or inter.guild

        await inter.edit_original_message(
            embed=disnake.Embed(
                description="**Link/Favorito foi removido com sucesso!**",
                color=self.bot.get_color(guild.me)),
            view=None
        )
        self.stop()

    async def clear_callback(self, inter: disnake.MessageInteraction):

        await inter.response.defer(ephemeral=True)

        data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        if not data["fav_links"]:
            raise GenericError("**Você não possui links favoritos!**")

        data["fav_links"].clear()

        await self.bot.update_global_data(inter.author.id, data, db_name=DBModel.users)

        embed = disnake.Embed(
            description="Sua lista de favoritos foi limpa com sucesso!",
            color=self.bot.get_color()
        )

        await inter.edit_original_message(embed=embed)
        self.stop()

    async def cancel_callback(self, inter: disnake.MessageInteraction):
        await inter.response.edit_message(
            embed=disnake.Embed(
                description="**Operação com favoritos cancelada...**",
                color=self.bot.get_color(),
            ), view=None
        )
        self.stop()

    async def select_callback(self, inter: disnake.MessageInteraction):
        self.current = inter.values[0]
        await inter.response.defer()


class FavManager(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    desc_prefix = "⭐ [Favoritos] ⭐ | "

    fav_cd = commands.CooldownMapping.from_cooldown(3, 15, commands.BucketType.member)

    @commands.max_concurrency(1, commands.BucketType.member, wait=False)
    @commands.slash_command()
    async def fav(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @commands.command(name="favmanager", aliases=["favs", "favoritos", "fvmgr"],
                      description="Gerenciar suas playlists/favoritos.", cooldown=fav_cd)
    async def favmanager_legacy(self, ctx: CustomContext):
        await self.manager.callback(self=self, inter=ctx)

    @fav.sub_command(
        description=f"{desc_prefix}Gerenciar suas playlists/favoritos.", cooldown=fav_cd
    )
    async def manager(self, inter: disnake.AppCmdInter):

        await inter.response.defer(ephemeral=True)

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        view = UserFavView(bot=self.bot, ctx=inter, data=user_data)

        embed = disnake.Embed(
            description="**Gerenciador de favoritos do usuário.**",
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
    @commands.command(name="favlist", description="Exibir sua lista de favoritos.")
    async def favlist_legacy(self, ctx: CustomContext):
        await self.list_.callback(self=self, inter=ctx, hidden=False)

    @commands.cooldown(1, 5, commands.BucketType.user)
    @fav.sub_command(
        name="list", description=f"{desc_prefix}Exibir sua lista de favoritos."
    )
    async def list_(
            self, inter: disnake.ApplicationCommandInteraction,
            hidden: bool = commands.Param(
                name="ocultar",
                description="Apenas você pode ver a lista de favoritos.",
                default=False)
    ):

        if hidden is False and not self.bot.check_bot_forum_post(inter.channel):
            hidden = True

        await inter.response.defer(ephemeral=hidden)

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        if not user_data["fav_links"]:
            raise GenericError(f"**Você não possui links favoritos..\n"
                               f"Você pode adicionar usando o comando: /{self.fav.name} {self.manager.name}**")

        embed = disnake.Embed(
            color=self.bot.get_color(),
            title="Seus Links Favoritos:",
            description="\n".join(f"{n+1}) [`{f[0]}`]({f[1]})" for n, f in enumerate(user_data["fav_links"].items()))
        )

        embed.set_footer(text="Você pode usá-los no comando /play")

        if isinstance(inter, CustomContext):
            await inter.send(embed=embed)
        else:
            await inter.edit_original_message(embed=embed)

    fav_import_export_cd = commands.CooldownMapping.from_cooldown(1, 15, commands.BucketType.member)

    @fav.sub_command(
        name="import", description=f"{desc_prefix}Importar seus favoritos a partir de um arquivo.",
        cooldown=fav_import_export_cd
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

            if "> fav:" in name.lower():
                continue

            if len(url) > (max_url_chars := self.bot.config["USER_FAV_MAX_URL_LENGTH"]):
                raise GenericError(f"**Um item de seu arquivo {url} ultrapassa a quantidade de caracteres permitido:{max_url_chars}**")

            if not isinstance(url, str) or not URL_REG.match(url):
                raise GenericError(f"O seu arquivo contém link inválido: ```ldif\n{url}```")

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        for name in json_data.keys():
            if len(name) > (max_name_chars := self.bot.config["USER_FAV_MAX_NAME_LENGTH"]):
                raise GenericError(f"**Um item de seu arquivo ({name}) ultrapassa a quantidade de caracteres permitido:{max_name_chars}**")
            try:
                del user_data["fav_links"][name.lower()]
            except KeyError:
                continue

        if self.bot.config["MAX_USER_FAVS"] > 0 and not (await self.bot.is_owner(inter.author)):

            if (json_size:=len(json_data)) > self.bot.config["MAX_USER_FAVS"]:
                raise GenericError(f"A quantidade de itens no seu arquivo de favorito excede "
                                   f"a quantidade máxima permitida ({self.bot.config['MAX_USER_FAVS']}).")

            if (json_size + (user_favs:=len(user_data["fav_links"]))) > self.bot.config["MAX_USER_FAVS"]:
                raise GenericError("Você não possui espaço suficiente para adicionar todos os favoritos de seu arquivo...\n"
                                   f"Limite atual: {self.bot.config['MAX_USER_FAVS']}\n"
                                   f"Quantidade de favoritos salvos: {user_favs}\n"
                                   f"Você precisa de: {(json_size + user_favs)-self.bot.config['MAX_USER_FAVS']}")

        user_data["fav_links"].update(json_data)

        await self.bot.update_global_data(inter.author.id, user_data, db_name=DBModel.users)

        await inter.edit_original_message(
            embed = disnake.Embed(
                color=self.bot.get_color(),
                description = "**Os links foram importados com sucesso!**\n"
                              "**Eles vão aparecer quando usar o comando /play (no preenchimento automático da busca).**",
            )
        )

    @fav.sub_command(
        description=f"{desc_prefix}Exportar seus favoritos em um arquivo json.",
        cooldown=fav_import_export_cd
    )
    async def export(self, inter: disnake.ApplicationCommandInteraction):

        await inter.response.defer(ephemeral=True)

        user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        if not user_data["fav_links"]:
            raise GenericError(f"**Você não possui links favoritos..\n"
                               f"Você pode adicionar usando o comando: /{self.fav.name} {self.manager.name}**")

        fp = BytesIO(bytes(json.dumps(user_data["fav_links"], indent=4), 'utf-8'))

        embed = disnake.Embed(
            description=f"Seus favoritos estão aqui.\nVocê pode importar usando o comando: `/{self.import_.name}`",
            color=self.bot.get_color())

        await inter.edit_original_message(embed=embed, file=disnake.File(fp=fp, filename="favoritos.json"))


def setup(bot: BotCore):
    bot.add_cog(FavManager(bot))
