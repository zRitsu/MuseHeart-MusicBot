from __future__ import annotations
import asyncio
import disnake
import humanize
from disnake.ext import commands
from typing import TYPE_CHECKING, Union
from utils.music.checks import user_cooldown
from utils.music.converters import time_format
from utils.music.errors import GenericError
from utils.others import send_idle_embed, CustomContext
from utils.music.models import LavalinkPlayer, YTDLPlayer

if TYPE_CHECKING:
    from utils.client import BotCore

other_bots_vc_opts = commands.option_enum(
    {
        "Ativar": "enable",
        "Desativar": "disable",
    }
)


class MusicSettings(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    desc_prefix = "🔧 [Configurações] 🔧 | "


    # O nome desse comando está sujeito a alterações (tá ridiculo, mas não consegui pensar em um nome melhor no momento).
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Permitir/bloquear de me conectar em um canal onde há outros bots.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def dont_connect_other_bot_vc(
            self, inter: disnake.ApplicationCommandInteraction,
            opt: str = commands.Param(choices=["Ativar", "Desativar"], description="Escolha: ativar ou desativar")
    ):

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        guild_data["check_other_bots_in_vc"] = opt == "Ativar"

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name="guilds")

        embed = disnake.Embed(
            color=self.bot.get_color(inter.guild.me),
            description="**Configuração salva com sucesso!\n"
                        f"Agora {'não ' if opt == 'Ativar' else ''}irei me conectar em canais onde há outros bots.**"
        )

        await inter.send(embed=embed, ephemeral=True)


    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_channels=True, create_public_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1, 30), commands.BucketType.guild)
    @commands.command(
        name="setup", aliases=["requestchannel"], usage="[id do canal ou #canal] [--reset]",
        description="Criar/escolher um canal dedicado para pedir músicas e deixar player fixado."
    )
    async def setup_legacy(
            self,
            ctx: CustomContext,
            channel: Union[disnake.TextChannel, disnake.VoiceChannel] = None, *,
            reset: str = None
    ):

        if reset == "--reset":
            reset = "sim"

        await self.setup.callback(self=self, inter=ctx, target=channel, purge_messages=reset)


    @commands.bot_has_guild_permissions(manage_channels=True, create_public_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1, 30), commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Criar/escolher um canal dedicado para pedir músicas e deixar player fixado.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def setup(
            self,
            inter: disnake.AppCmdInter,
            target: Union[disnake.TextChannel, disnake.VoiceChannel] = commands.Param(
                name="canal", default=None, description="Selecionar um canal existente"
            ),
            purge_messages: str = commands.Param(
                name="limpar_mensagens", choices=["sim", "não"],  default="não",
                description="Limpar mensagens do canal selecionado (até 100 mensagens)",
            )
    ):

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

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        await inter.response.defer(ephemeral=True)

        try:
            original_message = await self.bot.get_channel(int(guild_data["player_controller"]["channel"]))\
                .fetch_message(int(guild_data["player_controller"]["message_id"]))
        except:
            original_message = None

        message = None

        embed_archived = disnake.Embed(
            description=f"**Este canal de pedir música foi reconfigurado pelo membro {inter.author.mention}.**",
            color=self.bot.get_color(inter.guild.me)
        )

        if not target:

            if original_message:
                try:
                    await original_message.edit(content=None, embed=embed_archived, view=None)
                except:
                    pass
                try:
                    await original_message.thread.edit(archived=True, reason=f"Player reconfigurado por {inter.author}.")
                except:
                    pass

            if inter.channel.category and inter.channel.category.permissions_for(inter.guild.me).send_messages:
                target = inter.channel.category
            else:
                target = inter.guild

            channel = await target.create_text_channel(f"{self.bot.user.name} player controller", overwrites=perms)

            msg = f"Canal para pedido de músicas criado: {channel.mention}"

        else:

            if purge_messages == "sim":
                await target.purge(limit=100, check=lambda m: m.author != inter.guild.me or not m.thread)


            if original_message:

                if original_message.channel != target:
                    try:
                        await original_message.edit(content=None, embed=embed_archived, view=None)
                    except:
                        pass
                    try:
                        await original_message.thread.edit(archived=True, reason=f"Player reconfigurado por {inter.author}.")
                    except:
                        pass

                else:
                    message = original_message

            if not message:

                async for m in target.history(limit=100):

                    if m.author == inter.guild.me and m.thread:
                        message = m
                        break

            await target.edit(overwrites=perms)

            channel = target

            msg = f"Canal de pedido de músicas definido para: <#{channel.id}>"

        message = await send_idle_embed(message or channel, bot=self.bot, force=True)

        try:
            player: Union[LavalinkPlayer, YTDLPlayer] = self.bot.music.players[inter.guild_id]
        except KeyError:
            pass
        else:
            try:
                await player.message.delete()
                player.message = None
            except:
                pass
            player.static = True
            player.text_channel = channel
            player.message = message
            player.process_hint()
            await player.invoke_np(force=True)

        if not isinstance(channel, disnake.VoiceChannel):
            if not message.thread:
                await message.create_thread(name="song requests")
            elif message.thread.archived:
                await message.thread.edit(archived=False, reason=f"Song request reativado por: {inter.author}.")

        guild_data['player_controller']['channel'] = str(channel.id)
        guild_data['player_controller']['message_id'] = str(message.id)
        await self.bot.db.update_data(inter.guild.id, guild_data, db_name='guilds')

        reset_txt = f"{inter.prefix}reset" if isinstance(inter, CustomContext) else "/reset"

        embed = disnake.Embed(
            description=f"**{msg}**\n\nObs: Caso queira reverter esta configuração, apenas use o comando {reset_txt} ou "
                        f"delete o canal {channel.mention}",
            color=self.bot.get_color(inter.guild.me)
        )

        try:
            await inter.edit_original_message(embed=embed)
        except AttributeError:
            await inter.send(embed=embed, ephemeral=True)


    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1, 30), commands.BucketType.guild)
    @commands.command(
        name="reset", usage="[--delete]",
        description="Resetar as configurações relacionadas ao canal de pedir música (song request)."
    )
    async def reset_legacy(self, ctx: CustomContext, *, delete_channel: str = None):

        if delete_channel == "--delete":
            delete_channel = "sim"

        await self.reset.callback(self=self, inter=ctx, delete_channel=delete_channel)


    @commands.bot_has_guild_permissions(manage_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1, 30), commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Resetar as configurações relacionadas ao canal de pedir música (song request).",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def reset(
            self,
            inter: disnake.AppCmdInter,
            delete_channel: str = commands.Param(
                name="deletar_canal",
                description="deletar o canal do player controller", default=None, choices=["sim", "não"]
            )
    ):

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        channel = self.bot.get_channel(int(guild_data['player_controller']['channel'] or 0))

        if not channel:
            raise GenericError(f"**Não há canais de pedido de música configurado (ou o canal foi deletado).**")

        await inter.response.defer(ephemeral=True)

        try:
            original_message = await channel.fetch_message(int(guild_data["player_controller"]["message_id"]))
        except:
            original_message = None

        guild_data["player_controller"].update({
            "message_id": None,
            "channel": None
        })

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name='guilds')

        try:
            func = inter.edit_original_message
        except AttributeError:
            func = inter.send

        await func(
            embed=disnake.Embed(
                color=self.bot.get_color(inter.guild.me),
                description="**O Canal de pedir música foi resetado com sucesso.**"
            )
        )

        try:
            player: Union[LavalinkPlayer, YTDLPlayer] = self.bot.music.players[inter.guild.id]
        except KeyError:
            return

        player.static = False
        player.message = None
        player.text_channel = inter.channel
        player.process_hint()
        await player.invoke_np(force=True)

        try:
            if delete_channel == "sim":
                await channel.delete(reason=f"Player resetado por: {inter.author}")

            else:

                await original_message.edit(
                    content=f"Canal de pedir música foi resetado pelo membro {inter.author.mention}.",
                    embed=None, components=[
                        disnake.ui.Button(label="Reconfigurar este canal", emoji="💠",
                                          custom_id="musicplayer_request_channel")
                    ]
                )
                await original_message.thread.edit(archived=True, reason=f"Player resetado por {inter.author}.")

        except:
            pass


    @commands.has_guild_permissions(manage_guild=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.command(name="adddjrole",description="Adicionar um cargo para a lista de DJ's do servidor.", usage="[id / nome / @cargo]")
    async def add_dj_role_legacy(self, ctx: CustomContext, *, role: disnake.Role):
        await self.add_dj_role(ctx, inter=ctx, role=role)


    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Adicionar um cargo para a lista de DJ's do servidor.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def add_dj_role(
            self,
            inter: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="cargo", description="Cargo")
    ):

        if role == inter.guild.default_role:
            await inter.send("Você não pode adicionar esse cargo.", ephemeral=True)
            return

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        if str(role.id) in guild_data['djroles']:
            await inter.send(f"O cargo {role.mention} já está na lista de DJ's", ephemeral=True)
            return

        guild_data['djroles'].append(str(role.id))

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name="guilds")

        await inter.send(f"O cargo {role.mention} foi adicionado à lista de DJ's", ephemeral=True)


    @commands.has_guild_permissions(manage_guild=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.command(description="Remover um cargo para a lista de DJ's do servidor.", usage="[id / nome / @cargo]")
    async def remove_dj_role_legacy(self, ctx: CustomContext, *, role: disnake.Role):
        await self.remove_dj_role(ctx, inter=ctx, role=role)


    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.slash_command(
        name="removedjrole", description=f"{desc_prefix}Remover um cargo para a lista de DJ's do servidor.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def remove_dj_role(
            self,
            inter: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="cargo", description="Cargo")
    ):

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        if not guild_data['djroles']:

            await inter.send("Não há cargos na lista de DJ's.", ephemeral=True)
            return

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        if str(role.id) not in guild_data['djroles']:
            await inter.send(f"O cargo {role.mention} não está na lista de DJ's\n\n" + "Cargos:\n" +
                                              " ".join(f"<#{r}>" for r in guild_data['djroles']), ephemeral=True)
            return

        guild_data['djroles'].remove(str(role.id))

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name="guilds")

        await inter.send(f"O cargo {role.mention} foi removido da lista de DJ's", ephemeral=True)


    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Alterar aparência/skin do player.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def change_skin(self, inter: disnake.AppCmdInter):

        await inter.response.defer(ephemeral=True)

        guild_data = await self.bot.db.get_data(inter.guild.id, db_name="guilds")

        selected = guild_data["player_controller"]["skin"] or self.bot.default_skin

        skin_list = [
            disnake.SelectOption(emoji="🎨", label=s, default=selected == s) for s in self.bot.player_skins if
            not s in self.bot.config["IGNORE_SKINS"].split()
        ]

        if not skin_list and not await self.bot.is_owner(inter.author):
            raise GenericError("**Não há novas skins disponíveis...**")

        await inter.edit_original_message(
            embed=disnake.Embed(
                description="**Selecione uma skin abaixo:**",
                colour=self.bot.get_color(inter.guild.me)
            ),
            components=[disnake.ui.Select(custom_id=f"skin_select_{inter.id}", options=skin_list)]
        )

        try:
            resp = await self.bot.wait_for(
                "dropdown",
                check=lambda i: i.data.custom_id == f"skin_select_{inter.id}",
                timeout=35
            )
        except asyncio.TimeoutError:
            msg = await inter.original_message()
            await msg.edit(view=None, embed=disnake.Embed(description="**Tempo esgotado!**", colour=self.bot.get_color(inter.guild.me)))
            return
        else:
            inter = resp
            skin = resp.data.values[0]

        await inter.response.defer(ephemeral=True)

        guild_data["player_controller"]["skin"] = skin

        await self.bot.db.update_data(inter.guild.id, guild_data, db_name="guilds")

        await inter.edit_original_message(
            embed=disnake.Embed(
                description="**A skin do player do servidor foi alterado com sucesso!**",
                color=self.bot.get_color(inter.guild.me)
            ),
            view=None
        )

        try:
            player: Union[LavalinkPlayer, YTDLPlayer] = self.bot.music.players[inter.guild.id]
        except KeyError:
            pass
        else:
            player.skin = self.bot.player_skins[skin]
            player.auto_update = 0 # linha temporária para resolver possíveis problemas com skins custom criadas por usuarios antes desse commit.
            player.set_command_log(text=f"{inter.author.mention} alterou a skin do player para: **{skin}**", emoji="🎨")
            await player.invoke_np(force=True)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(name="nodeinfo", description="Ver informações dos servidores de música.")
    async def nodeinfo_legacy(self, ctx: CustomContext):
        await self.nodeinfo(ctx, inter=ctx)


    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.slash_command(description=f"{desc_prefix}Ver informações dos servidores de música.")
    async def nodeinfo(self, inter: disnake.AppCmdInter):

        em = disnake.Embed(color=self.bot.get_color(inter.guild.me), title="Servidores de música:")

        if not self.bot.music.nodes:
            em.description = "**Não há servidores.**"
            await inter.send(embed=em)
            return

        for identifier, node in self.bot.music.nodes.items():

            if not node.available: continue

            txt = f"Região: `{node.region.title()}`\n"

            try:
                current_player = node.players[inter.guild.id]
            except KeyError:
                current_player = None

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
