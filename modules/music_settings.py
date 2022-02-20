from __future__ import annotations
import disnake
import humanize
from disnake.ext import commands
from typing import TYPE_CHECKING
from utils.music.checks import user_cooldown
from utils.music.converters import time_format
from utils.others import send_idle_embed
from utils.music.models import LavalinkPlayer

if TYPE_CHECKING:
    from utils.client import BotCore

other_bots_vc_opts = commands.option_enum(
    {
        "Ativar": "enable",
        "Desativar": "disable",
    }
)


desc_prefix = "🛠️ [Configurações]🛠️ | "


class MusicSettings(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot


    # O nome desse comando está sujeito a alterações (tá ridiculo, mas não consegui pensar em um nome melhor no momento).
    @commands.has_guild_permissions(administrator=True)
    @commands.slash_command(description=f"{desc_prefix}Permitir/bloquear de me conectar em um canal onde há outros bots.")
    async def dont_connect_other_bot_vc(
            self, inter: disnake.ApplicationCommandInteraction,
            opt: str = commands.Param(choices=["Ativar", "Desativar"], description="Escolha: ativar ou desativar")
    ):

        inter.guild_data["check_other_bots_in_vc"] = opt == "Ativar"

        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name="guilds")

        embed = disnake.Embed(
            color=self.bot.get_color(inter.guild.me),
            description="**Configuração salva com sucesso!\n"
                        f"Agora {'não ' if opt == 'Ativar' else ''}irei me conectar em canais onde há outros bots.**"
        )

        await inter.send(embed=embed, ephemeral=True)


    @commands.has_guild_permissions(administrator=True)
    @commands.bot_has_guild_permissions(manage_channels=True, create_public_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1,30), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Criar um canal dedicado para pedir músicas e deixar player fixado.")
    async def setup(self, inter: disnake.AppCmdInter):


        if inter.channel.category and inter.channel.category.permissions_for(inter.guild.me).send_messages:
            target = inter.channel.category
        else:
            target = inter.guild

        perms = {
            inter.guild.default_role: disnake.PermissionOverwrite(
                embed_links=False,
                send_messages=True,
                send_messages_in_threads=True,
                read_messages=True,
                read_message_history=True
            ),
            inter.guild.me: disnake.PermissionOverwrite(
                embed_links=True,
                send_messages=True,
                send_messages_in_threads=True,
                read_messages=True,
                create_public_threads=True,
                read_message_history=True,
                manage_messages=True,
                manage_channels=True,
                attach_files=True,
            )
        }

        channel = await target.create_text_channel(
            f"{inter.guild.me.name} player controller",
            overwrites=perms
        )

        player: LavalinkPlayer = self.bot.music.players.get(inter.guild_id)

        if player:
            player.text_channel = channel
            await player.destroy_message()
            player.static = True
            await player.invoke_np()
            message = player.message

        else:
            message = await send_idle_embed(channel, bot=self.bot)

        await message.create_thread(name="song requests")

        inter.guild_data['player_controller']['channel'] = str(channel.id)
        inter.guild_data['player_controller']['message_id'] = str(message.id)
        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name='guilds')

        embed = disnake.Embed(description=f"**Canal criado: {channel.mention}**\n\nObs: Caso queira reverter esta configuração, apenas delete o canal {channel.mention}", color=self.bot.get_color(inter.guild.me))
        await inter.send(embed=embed, ephemeral=True)


    @commands.has_guild_permissions(administrator=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Adicionar um cargo para a lista de DJ's do servidor.")
    async def add_dj_role(
            self,
            inter: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="cargo", description="Cargo")
    ):

        if role == inter.guild.default_role:
            await inter.send("Você não pode adicionar este cargo.", ephemeral=True)
            return

        if str(role.id) in inter.guild_data['djroles']:
            await inter.send("Este cargo já está na lista de DJ's", ephemeral=True)
            return

        inter.guild_data['djroles'].append(str(role.id))

        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name="guilds")

        await inter.send(f"O cargo {role.mention} foi adicionado à lista de DJ's", ephemeral=True)


    @commands.has_guild_permissions(administrator=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Remover um cargo para a lista de DJ's do servidor.")
    async def remove_dj_role(
            self,
            inter: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="cargo", description="Cargo")
    ):

        if not inter.guild_data['djroles']:

            await inter.send("Não há cargos na lista de DJ's.", ephemeral=True)
            return

        if str(role.id) not in inter.guild_data['djroles']:
            await inter.send("Este cargo não está na lista de DJ's\n\n" + "Cargos:\n" +
                                              " ".join(f"<#{r}>" for r in inter.guild_data['djroles']), ephemeral=True)
            return

        inter.guild_data['djroles'].remove(str(role.id))

        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name="guilds")

        await inter.send(f"O cargo {role.mention} foi removido da lista de DJ's", ephemeral=True)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.slash_command(description=f"{desc_prefix}Ver informações dos servidores de música.")
    async def nodeinfo(self, inter: disnake.ApplicationCommandInteraction):

        em = disnake.Embed(color=self.bot.get_color(inter.guild.me), title="Servidores de música:")

        if not self.bot.music.nodes:
            em.description = "**Não há servidores.**"
            await inter.send(embed=em)
            return

        for identifier, node in self.bot.music.nodes.items():

            if not node.available: continue

            txt = f"Região: `{node.region.title()}`\n"

            current_player = True if node.players.get(inter.guild.id) else False

            if node.stats:
                used = humanize.naturalsize(node.stats.memory_used)
                total = humanize.naturalsize(node.stats.memory_allocated)
                free = humanize.naturalsize(node.stats.memory_free)
                cpu_cores = node.stats.cpu_cores
                cpu_usage = f"{node.stats.lavalink_load * 100:.2f}"
                started = node.stats.players

                ram_txt = f'RAM: `{used}/{free} ({total})`'

                txt += f'{ram_txt}\n' \
                       f'CPU Cores: `{cpu_cores}`\n' \
                       f'Uso de CPU: `{cpu_usage}%`\n' \
                       f'Uptime: `{time_format(node.stats.uptime)}\n`'

                if started:
                    txt += "Players: "
                    players = node.stats.playing_players
                    idle = started - players
                    if players:
                        txt += f'`[▶️{players}]`' + (" " if idle else "")
                    if idle:
                        txt += f'`[💤{idle}]`'

                    txt += "\n"

                if node.website:
                    txt += f'[`Website do server`]({node.website})\n'

            if current_player:
                status = "🌟"
            else:
                status = "✅" if node.is_available else '❌'

            em.add_field(name=f'**{identifier}** `{status}`', value=txt)

        await inter.send(embed=em, ephemeral=True)


def setup(bot: BotCore):
    bot.add_cog(MusicSettings(bot))
