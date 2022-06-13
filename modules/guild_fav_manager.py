from __future__ import annotations
import disnake
from disnake.ext import commands
from typing import TYPE_CHECKING, Union
from utils.music.converters import URL_REG, pin_list
from utils.music.errors import GenericError
from utils.music.models import YTDLPlayer, LavalinkPlayer
from utils.others import send_idle_embed

if TYPE_CHECKING:
    from utils.client import BotCore


class PinManager(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    desc_prefix = "📌 [Server playlist] 📌 | "


    async def process_idle_embed(self, guild: disnake.Guild):
        guild_data = await self.bot.db.get_data(guild.id, db_name="guilds")

        try:
            player: Union[LavalinkPlayer, YTDLPlayer] = self.bot.music.players[guild.id]
            if not player.current:
                await player.process_idle_message()
            return
        except KeyError:
            pass

        try:
            channel = self.bot.get_channel(int(guild_data["player_controller"]["channel"]))
            message = await channel.fetch_message(int(guild_data["player_controller"]["message_id"]))

        except:
            return

        await send_idle_embed(message or channel, bot=self.bot)


    @commands.max_concurrency(1, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    @commands.slash_command(name="pin")
    async def pin(self, inter: disnake.AppCmdInter):
        pass


    @pin.sub_command(description=f"{desc_prefix}Adicionar um link para lista de fixos do player.")
    async def add(
            self,
            inter: disnake.AppCmdInter,
            name: str = commands.Param(name="nome", description="Nome para o link."),
            url: str = commands.Param(name="link", description="Link (recomendável de playlist)."),
            description: str = commands.Param(name="descrição", description="Descrição do link.", default="")
    ):

        if "> fav:" in name.lower():
            raise GenericError("Você não pode adicionar um item incluindo esse nome: **> fav:**")

        if not URL_REG.match(url):
            raise GenericError("**Você não adicionou um link válido...**")

        if len(name) > 25:
            raise GenericError("**O nome não pode ultrapassar 25 caracteres.**")

        if len(description) > 50:
            raise GenericError("**A descrição não pode ultrapassar 50 caracteres.**")

        if len(url) > (max_url_chars:=self.bot.config["USER_FAV_MAX_URL_LENGTH"]):
            raise GenericError(f"**Quantidade máxima de caracteres permitidos no link: {max_url_chars}**")

        await inter.response.defer(ephemeral=True)

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        if len(guild_data["player_controller"]["fav_links"]) > 25:
            raise GenericError(f"**Você excedeu a quantidade de favoritos permitido: 25.**")

        if not guild_data["player_controller"]["channel"] or not self.bot.get_channel(int(guild_data["player_controller"]["channel"])):
            raise GenericError("**Não há player configurado no servidor! Use o comando /setup**")

        guild_data["player_controller"]["fav_links"][name] = {
            "url": url,
            "description": description
        }

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name="guilds")

        await inter.edit_original_message(content="Link Salvo/Atualizado com sucesso nos fixos do player!\n"
                         "Membros podem usá-lo diretamente no player-controller quando não estiver em uso.")

        await self.process_idle_embed(inter.guild)


    @pin.sub_command(description=f"{desc_prefix}Editar um item da lista de links fixos do servidor.")
    async def edit(
            self,
            inter: disnake.AppCmdInter,
            item: str = commands.Param(autocomplete=pin_list, description="item dos favoritos para editar."), *,
            name: str = commands.Param(name="novo_nome", default="", description="Novo nome para o favorito."),
            url: str = commands.Param(name="novo_link", default="", description="Novo link para o favorito."),
            description: str = commands.Param(name="descrição", description="Descrição do link.", default="")
    ):

        if not name and not url and not description:
            raise GenericError("**Você não especificou nenhum dos itens opcionais...**")

        if "> fav:" in name.lower():
            raise GenericError("Você não deve incluir esse nome no favorito: **> fav:**")

        if len(name) > 25:
            raise GenericError("**O nome não pode ultrapassar 25 caracteres.**")

        if len(description) > 50:
            raise GenericError("**A descrição não pode ultrapassar 50 caracteres.**")

        if len(url) > (max_url_chars:=self.bot.config["USER_FAV_MAX_URL_LENGTH"]):
            raise GenericError(f"**Quantidade máxima de caracteres permitidos no link: {max_url_chars}**")

        await inter.response.defer(ephemeral=True)

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        if not guild_data["player_controller"]["channel"] or not self.bot.get_channel(int(guild_data["player_controller"]["channel"])):
            raise GenericError("**Não há player configurado no servidor! Use o comando /setup**")

        try:
            if name:
                new_url = str(guild_data["player_controller"]["fav_links"][item])
                del guild_data["player_controller"]["fav_links"][item]
                guild_data["player_controller"]["fav_links"][name]['url'] = url or new_url

            elif url:
                guild_data["player_controller"]["fav_links"][item]['url'] = url

            if description:
                guild_data["player_controller"]["fav_links"][item]['description'] = description

        except KeyError:
            raise GenericError(f"**Não há link fixo com o nome:** {item}")

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name="guilds")

        await inter.edit_original_message(content="Link fixo editado com sucesso!")

        await self.process_idle_embed(inter.guild)


    @pin.sub_command(description=f"{desc_prefix}Remover um link da lista de links fixos do servidor.")
    async def remove(
            self,
            inter: disnake.AppCmdInter,
            item: str = commands.Param(autocomplete=pin_list, description="Favorito para remover."),
    ):

        await inter.response.defer(ephemeral=True)

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        try:
            del guild_data["player_controller"]["fav_links"][item]
        except:
            raise GenericError(f"**Não há favorito com o nome:** {item}")

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name="guilds")

        await inter.edit_original_message(content="Link removido com sucesso!")

        await self.process_idle_embed(inter.guild)


def setup(bot: BotCore):
    bot.add_cog(PinManager(bot))
