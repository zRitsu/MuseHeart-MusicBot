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


class FavManager(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot


    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.slash_command(name="fav")
    async def fav(self, inter: disnake.ApplicationCommandInteraction):
        pass


    @fav.sub_command(description="Adcionar um link para sua lista de favoritos.")
    async def add(
            self,
            inter: disnake.ApplicationCommandInteraction,
            name: str = commands.Param(name="nome"),
            url: str = commands.Param(name="link", description="link para favoritar (recomendável: link de playlist)"),
    ):

        if not URL_REG.match(url):
            raise GenericError("Você não adicionou um link válido...")

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        user_data["fav_links"][name.lower()] = url

        await self.bot.db.update_data(inter.author.id, user_data, db_name="users")

        await inter.send("Link Salvo/Atualizado com sucesso nos seus favoritos!\n"
                         "Ele vai aparecer quando usar o comando /play (no preenchimento automático da busca).",
                         ephemeral=True)


    @fav.sub_command(description="Editar o nome de um link da sua lista de favoritos.")
    async def edit(
            self,
            inter: disnake.ApplicationCommandInteraction,
            item: str = commands.Param(autocomplete=fav_list), *,
            name: str = commands.Param(name="novo_nome", default=""),
            url: str = commands.Param(name="novo_link", default="")
    ):

        if not name and not url:
            raise GenericError("Você não especificou nenhum dos itens opcionais: novo_nome e novo_link.")

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        try:
            if name:
                new_url = str(user_data["fav_links"][item.lower()])
                del user_data["fav_links"][item.lower()]
                user_data["fav_links"][name.lower()] = url or new_url

            elif url:
                user_data["fav_links"][item.lower()] = url

        except KeyError:
            raise GenericError(f"Não há favorito com o nome: {item}")

        await self.bot.db.update_data(inter.author.id, user_data, db_name="users")

        await inter.send("Favorito editado com sucesso!", ephemeral=True)


    @fav.sub_command(description="Remover um link da sua lista de favoritos.")
    async def remove(
            self,
            inter: disnake.ApplicationCommandInteraction,
            item: str = commands.Param(autocomplete=fav_list),
    ):

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        try:
            del user_data["fav_links"][item.lower()]
        except:
            raise GenericError(f"Não há favorito com o nome: {item}")

        await self.bot.db.update_data(inter.author.id, user_data, db_name="users")

        await inter.send("Link removido com sucesso!", ephemeral=True)


    @fav.sub_command(name="import",description="Importar seus favoritos a partir de um arquivo.")
    async def import_(self, inter: disnake.ApplicationCommandInteraction):

        try:
            msg = await inter.author.send("Envie o arquivo de sua playlist em até 60 segundos.")
        except disnake.Forbidden:
            raise GenericError("Seu DM está desativado...\nAtive-o e repita o comando.")

        await inter.send("Enviei uma solicitação em suas mensagens privadas.", ephemeral=True)

        data = None

        try:
            while not self.bot.is_closed():
                resp: disnake.Message = await self.bot.wait_for("message", check=lambda
                    m: m.channel == msg.channel and m.author.id == inter.author.id and m.attachments, timeout=60)

                if resp.attachments:

                    if not resp.attachments[0].filename.endswith(".json"):
                        await inter.author.send("Formato inválido! Envie novamente...")
                        continue

                    data = (await resp.attachments[0].read()).decode('utf-8')
                    break

        except asyncio.TimeoutError:
            await msg.channel.send("Tempo esgotado!")
            return

        if not data:
            return

        try:
            json_data = json.loads(data)
        except:
            raise GenericError("Ocorreu um erro ao ler o arquivo, por favor revise-o e use o comando novamente.")

        for url in json_data.values():

            if not isinstance(url, str) or not URL_REG.match(url):
                raise GenericError(f"O seu arquivo contém link inválido: ```ldif\n{url}```")

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        if self.bot.config["MAX_USER_FAVS"] > 0:

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

        await inter.author.send("Os links foram importados com sucesso!\n"
                                "Eles vão aparecer quando usar o comando /play (no preenchimento automático da busca).")


    @fav.sub_command(description="Exportar seus favoritos em um arquivo no seu DM.")
    async def export(self, inter: disnake.ApplicationCommandInteraction):

        user_data = await self.bot.db.get_data(inter.author.id, db_name="users")

        if not user_data["fav_links"]:
            raise GenericError(f"Você não possui links favoritos..\n"
                               f"Adicione um usando o comando: /{self.add.name}")

        fp = BytesIO(bytes(json.dumps(user_data["fav_links"], indent=4), 'utf-8'))
        try:
            embed = disnake.Embed(
                description=f"Seus favoritos estão aqui.\nVocê pode importar usando o comando: `/{self.import_.name}`",
                color=self.bot.get_color(inter.guild.me))
            await inter.author.send(embed=embed, file=disnake.File(fp=fp, filename="favoritos.json"))

        except disnake.Forbidden:
            raise GenericError("Seu DM está desativado!")

        await inter.send("Seus favoritos foram enviados no seu DM.")


def setup(bot: BotCore):
    bot.add_cog(FavManager(bot))
