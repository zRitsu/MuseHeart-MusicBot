from __future__ import annotations
import asyncio
import disnake
from disnake.ext import commands
from typing import TYPE_CHECKING
from utils.music.converters import URL_REG, fav_list
from utils.music.errors import GenericError
from io import BytesIO
import json

if TYPE_CHECKING:
    from utils.client import BotCore

desc_prefix = "⭐ [Favoritos] ⭐ | "


class FavManager(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot


    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.slash_command(name="fav")
    async def fav(self, inter: disnake.ApplicationCommandInteraction):
        pass


    @fav.sub_command(description=f"{desc_prefix}Adicionar um link (recomendável: de playlist) para sua lista de favoritos.")
    async def add(
            self,
            inter: disnake.ApplicationCommandInteraction,
            name: str = commands.Param(name="nome", description="Nome do favorito."),
            url: str = commands.Param(name="link", description="link para favoritar (recomendável: de playlist)"),
    ):

        if len(name) > (max_name_chars:=self.bot.config["USER_FAV_MAX_NAME_LENGTH"]):
            raise GenericError(f"**Quantidade máxima de caracteres permitidos no nome: {max_name_chars}**")

        if len(url) > (max_url_chars:=self.bot.config["USER_FAV_MAX_URL_LENGTH"]):
            raise GenericError(f"**Quantidade máxima de caracteres permitidos no link: {max_url_chars}**")

        if not URL_REG.match(url):
            raise GenericError("**Você não adicionou um link válido...**")

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        if len(user_data["fav_links"]) > (max_favs:=self.bot.config["MAX_USER_FAVS"]) and not \
                (await self.bot.is_owner(inter.author)):
            raise GenericError(f"**Você excedeu a quantidade de favoritos permitido ({max_favs}).**")

        try:
            del user_data["fav_links"][name.lower()]
        except KeyError:
            pass

        user_data["fav_links"][name] = url

        await self.bot.db.update_data(inter.author.id, user_data, db_name="users")

        await inter.send("Link Salvo/Atualizado com sucesso nos seus favoritos!\n"
                         "Ele vai aparecer quando usar o comando /play (no preenchimento automático da busca).",
                         ephemeral=True)


    @fav.sub_command(description=f"{desc_prefix}Editar um item da sua lista de favoritos.")
    async def edit(
            self,
            inter: disnake.ApplicationCommandInteraction,
            item: str = commands.Param(autocomplete=fav_list, description="item dos favoritos para editar."), *,
            name: str = commands.Param(name="novo_nome", default="", description="Novo nome para o favorito."),
            url: str = commands.Param(name="novo_link", default="", description="Novo link para o favorito.")
    ):

        if not name and not url:
            raise GenericError("**Você não especificou nenhum dos itens opcionais: novo_nome e novo_link.**")

        if len(name) > (max_name_chars:=self.bot.config["USER_FAV_MAX_NAME_LENGTH"]):
            raise GenericError(f"**Quantidade máxima de caracteres permitidos no nome: {max_name_chars}**")

        if len(url) > (max_url_chars:=self.bot.config["USER_FAV_MAX_URL_LENGTH"]):
            raise GenericError(f"**Quantidade máxima de caracteres permitidos no link: {max_url_chars}**")

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        try:
            if name:
                new_url = str(user_data["fav_links"][item])
                del user_data["fav_links"][item]
                user_data["fav_links"][name] = url or new_url

            elif url:
                user_data["fav_links"][item] = url

        except KeyError:
            raise GenericError(f"**Não há favorito com o nome:** {item}")

        await self.bot.db.update_data(inter.author.id, user_data, db_name="users")

        await inter.send("Favorito editado com sucesso!", ephemeral=True)


    @fav.sub_command(description=f"{desc_prefix}Remover um link da sua lista de favoritos.")
    async def remove(
            self,
            inter: disnake.ApplicationCommandInteraction,
            item: str = commands.Param(autocomplete=fav_list, description="Favorito para remover."),
    ):

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        try:
            del user_data["fav_links"][item]
        except:
            raise GenericError(f"**Não há favorito com o nome:** {item}")

        await self.bot.db.update_data(inter.author.id, user_data, db_name="users")

        await inter.send("Link removido com sucesso!", ephemeral=True)


    @fav.sub_command(name="clear", description=f"{desc_prefix}Limpar sua lista de favoritos.")
    async def clear_(self, inter: disnake.ApplicationCommandInteraction):

        data = await self.bot.db.get_data(inter.author.id, db_name="users")

        if not data["fav_links"]:
            raise GenericError("**Você não possui links favoritos!**")

        data["fav_links"].clear()

        await self.bot.db.update_data(inter.author.id, data, db_name="users")

        embed = disnake.Embed(
            description="Sua lista de favoritos foi limpa com sucesso!",
            color=self.bot.get_color(inter.guild.me)
        )

        await inter.send(embed=embed, ephemeral=True)


    @fav.sub_command(name="list", description=f"{desc_prefix}Exibir sua lista de favoritos.")
    async def list_(
            self, inter: disnake.ApplicationCommandInteraction,
            hidden: bool = commands.Param(
                name="ocultar",
                description="Apenas você pode ver a lista de favoritos.",
                default=False)
    ):

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        if not user_data["fav_links"]:
            raise GenericError(f"**Você não possui links favoritos..\n"
                               f"Você pode adicionar usando o comando: /{self.add.name}**")

        embed = disnake.Embed(
            color=self.bot.get_color(inter.guild.me),
            title="Seus Links Favoritos:",
            description="\n".join(f"{n+1}) [`{f[0]}`]({f[1]})" for n, f in enumerate(user_data["fav_links"].items()))
        )

        embed.set_footer(text="Você pode usá-los no comando /play")

        await inter.send(embed=embed, ephemeral=hidden)


    @fav.sub_command(name="import",description=f"{desc_prefix}Importar seus favoritos a partir de um arquivo.")
    async def import_(
            self,
            inter: disnake.ApplicationCommandInteraction,
            file: disnake.Attachment = commands.Param(name="arquivo", description="arquivo em formato .json")
    ):

        if file.size > 2097152:
            raise GenericError("**O tamanho do arquivo não pode ultrapassar 2Mb!**")

        if not file.filename.endswith(".json"):
            raise GenericError("**Tipo de arquivo inválido!**")

        try:
            data = (await file.read()).decode('utf-8')
            json_data = json.loads(data)
        except Exception as e:
            raise GenericError("**Ocorreu um erro ao ler o arquivo, por favor revise-o e use o comando novamente.**\n"
                               f"```py\n{repr(e)}```")

        for url in json_data.values():

            if len(url) > (max_url_chars := self.bot.config["USER_FAV_MAX_URL_LENGTH"]):
                raise GenericError(f"**Um item de seu arquivo {url} ultrapassa a quantidade de caracteres permitido:{max_url_chars}**")

            if not isinstance(url, str) or not URL_REG.match(url):
                raise GenericError(f"O seu arquivo contém link inválido: ```ldif\n{url}```")

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

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

        await self.bot.db.update_data(inter.author.id, user_data, db_name="users")

        await inter.send(
            ephemeral=True,
            embed = disnake.Embed(
                color=self.bot.get_color(inter.guild.me),
                description = "**Os links foram importados com sucesso!**\n"
                              "**Eles vão aparecer quando usar o comando /play (no preenchimento automático da busca).**",
            )
        )


    @fav.sub_command(description=f"{desc_prefix}Exportar seus favoritos em um arquivo no seu DM.")
    async def export(self, inter: disnake.ApplicationCommandInteraction):

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        if not user_data["fav_links"]:
            raise GenericError(f"**Você não possui links favoritos..\n"
                               f"Você pode adicionar usando o comando: /{self.add.name}**")

        fp = BytesIO(bytes(json.dumps(user_data["fav_links"], indent=4), 'utf-8'))

        embed = disnake.Embed(
            description=f"Seus favoritos estão aqui.\nVocê pode importar usando o comando: `/{self.import_.name}`",
            color=self.bot.get_color(inter.guild.me))

        await inter.send(embed=embed, file=disnake.File(fp=fp, filename="favoritos.json"), ephemeral=True)


def setup(bot: BotCore):
    bot.add_cog(FavManager(bot))
