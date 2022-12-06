from __future__ import annotations
import asyncio
import datetime
import traceback
import disnake
import humanize
from disnake.ext import commands
from typing import TYPE_CHECKING, Union, Optional
from utils.db import DBModel
from utils.music.checks import user_cooldown, ensure_bot_instance
from utils.music.converters import perms_translations
from utils.music.errors import GenericError
from utils.others import send_idle_embed, CustomContext, select_bot_pool
from utils.music.models import LavalinkPlayer

if TYPE_CHECKING:
    from utils.client import BotCore

other_bots_vc_opts = commands.option_enum(
    {
        "Ativar": "enable",
        "Desativar": "disable",
    }
)


class SkinSelector(disnake.ui.View):

    def __init__(self, ctx: Union[disnake.AppCmdInter, CustomContext], select_opts: list, static_select_opts: list):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.interaction: Optional[disnake.MessageInteraction] = None
        self.skin_selected = "default"
        self.static_skin_selected = "default"

        select_opts = disnake.ui.Select(options=select_opts, min_values=1, max_values=1)
        select_opts.callback = self.skin_callback
        self.add_item(select_opts)

        static_select_opts = disnake.ui.Select(options=static_select_opts, min_values=1, max_values=1)
        static_select_opts.callback = self.static_skin_callback
        self.add_item(static_select_opts)

        confirm_button = disnake.ui.Button(label="Salvar Alterações", emoji="💾")
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)

        cancel_button = disnake.ui.Button(label="Cancelar", emoji="❌")
        cancel_button.callback = self.stop_callback
        self.add_item(cancel_button)

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:

        if inter.author.id == self.ctx.author.id:
            return True

        await inter.send(f"Apenas {self.ctx.author.mention} pode interagir aqui!", ephemeral=True)

    async def skin_callback(self, inter: disnake.MessageInteraction):
        self.skin_selected = inter.data.values[0]
        await inter.response.defer()

    async def static_skin_callback(self, inter: disnake.MessageInteraction):
        self.static_skin_selected = inter.data.values[0]
        await inter.response.defer()

    async def confirm_callback(self, inter: disnake.MessageInteraction):
        self.interaction = inter
        self.stop()

    async def stop_callback(self, inter: disnake.MessageInteraction):
        self.interaction = inter
        self.skin_selected = None
        self.stop()


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

        bot = await select_bot_pool(inter)

        if not bot:
            return

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        guild_data["check_other_bots_in_vc"] = opt == "Ativar"

        await bot.update_data(inter.guild_id, guild_data, db_name=DBModel.guilds)

        guild = bot.get_guild(inter.guild_id) or inter.guild

        embed = disnake.Embed(
            color=self.bot.get_color(guild.me),
            description="**Configuração salva com sucesso!\n"
                        f"Agora {'não ' if opt == 'Ativar' else ''}irei me conectar em canais onde há outros bots.**"
        )

        try:
            await inter.edit_original_message(embed=embed, components=None)
        except (AttributeError, disnake.InteractionNotEditable):
            try:
                await inter.response.edit_message(embed=embed, components=None)
            except:
                await inter.send(embed=embed, ephemeral=True)

    @commands.cooldown(1, 10, commands.BucketType.user)
    @ensure_bot_instance(return_first=True)
    @commands.command(aliases=["mgf", "migrarfavoritos", "migrate"],
                      description="Migrar seus favoritos para database global (comando temporário).")
    @ensure_bot_instance()
    async def migratefav(self, ctx: CustomContext):

        async with ctx.typing():
            user_data = await self.bot.get_data(ctx.author.id, db_name=DBModel.users)
            global_user_data = await self.bot.get_global_data(ctx.author.id, db_name=DBModel.users)

            if not user_data["fav_links"]:
                raise GenericError("**Você não possui favoritos na database antiga.**")

            global_user_data["fav_links"].update(user_data["fav_links"])
            await self.bot.update_global_data(ctx.author.id, global_user_data, db_name=DBModel.users)

            user_data["fav_links"].clear()
            await self.bot.update_data(ctx.author.id, user_data, db_name=DBModel.users)

        await ctx.send(
            embed=disnake.Embed(
                description="**Os dados foram migrados com sucesso.**",
                color=self.bot.get_color(ctx.guild.me)
            )
        )

    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_channels=True, create_public_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1, 30), commands.BucketType.guild)
    @ensure_bot_instance(return_first=True)
    @commands.command(
        name="setup", aliases=["songrequestchannel", "sgrc"], usage="[id do canal ou #canal] [--reset]",
        description="Criar/escolher um canal dedicado para pedir músicas e deixar player fixado."
    )
    async def setup_legacy(
            self,
            ctx: CustomContext,
            channel: Union[disnake.TextChannel, disnake.VoiceChannel, disnake.ForumChannel, None] = None, *args
    ):

        args = list(args)

        if "--reset" in args:
            purge_messages = "yes"
            args.remove("--reset")
        else:
            purge_messages = "no"

        if args:
            raise GenericError("**Opção inválida:** " + " ".join(args))

        await self.setup.callback(self=self, inter=ctx, target=channel,
                                  purge_messages=purge_messages)

    @commands.dynamic_cooldown(user_cooldown(1, 30), commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Criar/escolher um canal dedicado para pedir músicas e deixar player fixado.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def setup(
            self,
            inter: disnake.AppCmdInter,
            target: Union[disnake.TextChannel, disnake.VoiceChannel, disnake.ForumChannel] = commands.Param(
                name="canal", default=None, description="Selecionar um canal existente"
            ),
            purge_messages: str = commands.Param(
                name="limpar_mensagens", default="no",
                description="Limpar mensagens do canal selecionado (até 100 mensagens, não efetivo em forum).",
                choices=[
                    disnake.OptionChoice(
                        disnake.Localized("Yes", data={disnake.Locale.pt_BR: "Sim"}), "yes"
                    ),
                    disnake.OptionChoice(
                        disnake.Localized("No", data={disnake.Locale.pt_BR: "Não"}), "no"
                    )
                ],
            )
    ):

        bot = await select_bot_pool(inter)

        if not bot:
            return

        guild = bot.get_guild(inter.guild_id)

        if not guild.me.guild_permissions.manage_channels or not guild.me.guild_permissions.create_public_threads:
            raise GenericError(f"Não tenho permissão de **{perms_translations['manage_threads']}** e "
                               f"**{perms_translations['create_public_threads']}** no servidor.")

        channel = bot.get_channel(inter.channel.id)

        try:
            target = bot.get_channel(target.id)
        except AttributeError:
            pass

        if guild.me.guild_permissions.administrator:

            channel_kwargs = {
                "overwrites": {
                    guild.me: disnake.PermissionOverwrite(
                        embed_links=True,
                        send_messages=True,
                        send_messages_in_threads=True,
                        read_messages=True,
                        create_public_threads=True,
                        read_message_history=True,
                        manage_messages=True,
                        manage_channels=True,
                        attach_files=True,
                        manage_permissions=True,
                    )
                }
            }


        else:

            channel_kwargs = {
                "overwrites": {
                    guild.me: disnake.PermissionOverwrite(
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
            }

        await inter.response.defer(ephemeral=True)

        guild_data = await bot.get_data(guild.id, db_name=DBModel.guilds)

        original_message = None
        message = None

        try:
            player: LavalinkPlayer = bot.music.players[guild.id]
            if player.static:
                original_message = player.message
        except KeyError:
            player = None

        if not original_message:

            try:
                channel_db = bot.get_channel(int(guild_data["player_controller"]["channel"])) or \
                             await bot.fetch_channel(int(guild_data["player_controller"]["channel"]))
                original_message = await channel_db.fetch_message(int(guild_data["player_controller"]["message_id"]))
            except:
                pass

        embed_archived = disnake.Embed(
            description=f"**Este canal de pedir música foi reconfigurado pelo membro {inter.author.mention}.**",
            color=bot.get_color(guild.me)
        )

        async def get_message(original_message):

            if original_message and original_message.channel != target and original_message.guild.id == target.guild.id:

                try:
                    if isinstance(original_message.channel.parent, disnake.ForumChannel):
                        await original_message.thread.delete(reason=f"Player reconfigurado por {inter.author}.")
                        return
                except AttributeError:
                    pass
                except Exception:
                    traceback.print_exc()
                    return

                try:
                    await original_message.edit(content=None, embed=embed_archived, view=None)
                except:
                    pass

                try:
                    await original_message.thread.edit(
                        archived=True,
                        locked=True,
                        reason=f"Player reconfigurado por {inter.author}."
                    )
                except:
                    pass

            else:
                return original_message

        if not target:

            try:
                id_ = inter.id
            except AttributeError:
                id_ = ""

            kwargs_msg = {}
            try:
                func = inter.edit_original_message
            except:
                try:
                    func = inter.store_message.edit
                except:
                    try:
                        func = inter.response.edit_message
                    except:
                        func = inter.send
                        kwargs_msg = {"ephemeral": True}

            if isinstance(inter, CustomContext):
                txt = "mencionando um canal de forum existente"
            else:
                txt = "usando um canal de forum na opção \"canal\" deste mesmo comando"

            msg_select = await func(
                embed=disnake.Embed(
                    description="**Qual tipo de canal para pedir música você quer criar?**\n"
                                f"`Nota: para canal de forum, cancele e use o comando novamente {txt}.`",
                    color=self.bot.get_color(guild.me)
                ).set_footer(text="Você tem apenas 30 segundos para clicar em um botão."),
                components=[
                    disnake.ui.Button(label="Canal de texto", custom_id=f"text_channel_{id_}", emoji="💬"),
                    disnake.ui.Button(label="Canal de voz", custom_id=f"voice_channel_{id_}", emoji="🔊"),
                    disnake.ui.Button(label="Cancelar", custom_id="voice_channel_cancel", emoji="❌")
                ],
                **kwargs_msg
            )

            def check(i: disnake.MessageInteraction):

                try:
                    return i.data.custom_id.endswith(f"_{inter.id}") and i.author == inter.author
                except AttributeError:
                    return i.message.id == msg_select.id and i.author == inter.author

            try:
                inter = await self.bot.wait_for("button_click", check=check, timeout=30)
            except asyncio.TimeoutError:
                try:
                    inter.application_command.reset_cooldown(inter)
                except AttributeError:
                    inter.command.reset_cooldown(inter)

                if msg_select:
                    func = msg_select.edit
                else:
                    try:
                        func = (await inter.original_message()).edit
                    except:
                        func = inter.message.edit

                await func(
                    embed=disnake.Embed(
                        description="**Tempo esgotado!**",
                        color=disnake.Color.red()
                    ),
                    components=None
                )
                return

            if inter.data.custom_id == "voice_channel_cancel":
                await inter.response.edit_message(
                    embed=disnake.Embed(
                        description="**Operação cancelada...**",
                        color=self.bot.get_color(guild.me),
                    ), components=None
                )
                return

            await inter.response.defer()

            if original_message and original_message.guild.id == inter.guild_id:

                try:
                    await original_message.edit(content=None, embed=embed_archived, view=None)
                except:
                    pass
                try:
                    if original_message.thread:
                        await original_message.thread.edit(
                            archived=True,
                            locked=True,
                            reason=f"Player reconfigurado por {inter.author}.")
                except:
                    pass

            if channel.category and channel.category.permissions_for(guild.me).send_messages:
                target = channel.category
            else:
                target = guild

            create_func = target.create_voice_channel if \
                inter.data.custom_id.startswith("voice_channel_") else target.create_text_channel

            channel = await create_func(f"{bot.user.name} player controller", **channel_kwargs)

            msg = f"Canal para pedido de músicas criado: {channel.mention}"

        else:

            if isinstance(target, disnake.ForumChannel):

                channel_kwargs.clear()

                thread_wmessage = await target.create_thread(
                    name=f"{bot.user.name} song request",
                    content="Post para pedido de músicas.",
                    auto_archive_duration=10080,
                    slowmode_delay=5,
                )

                await get_message(original_message)

                message = await send_idle_embed(target=thread_wmessage.message, bot=bot, force=True,
                                                guild_data=guild_data)

                target = message.channel

            else:

                if not guild.me.guild_permissions.administrator and not target.permissions_for(guild.me).manage_permissions:
                    raise GenericError(f"**{guild.me.mention} não possui permissão de administrador ou permissão de "
                                       f"gerenciar permissões do canal {target.mention}** para editar as permissões "
                                       f"necessárias para o sistema de pedir música funcionar devidamente.\n\n"
                                       f"Caso não queira fornecer a permissão de administrador ou editar as permissões do"
                                       f" canal {target.mention} para me permitir gerenciar permissões, reuse o comando "
                                       f"sem selecionar um canal de destino.")

                if purge_messages == "yes":
                    await target.purge(limit=100, check=lambda m: m.author != guild.me or not m.thread)

                if original_message:

                    message = await get_message(original_message)

                if not message:

                    async for m in target.history(limit=100):

                        if m.author == guild.me and m.thread:
                            message = m
                            break

            await target.edit(**channel_kwargs)

            channel = target

            msg = f"O canal de pedido de músicas foi definido para <#{channel.id}> através do bot: {bot.user.mention}"

        if player and player.text_channel != target:
            if player.static:
                try:
                    await player.message.thread.edit(
                        archived=True,
                        locked=True,
                        reason=f"Player reconfigurado por {inter.author}."
                    )
                except:
                    pass
            else:
                try:
                    await player.message.delete()
                except:
                    pass
            if not message or message.channel.id != channel.id:
                message = await send_idle_embed(channel, bot=bot, force=True, guild_data=guild_data)
            player.message = message
            player.static = True
            player.text_channel = channel
            player.setup_hints()
            await player.invoke_np(force=True)

        elif not message or message.channel.id != channel.id:
            message = await send_idle_embed(channel, bot=bot, force=True, guild_data=guild_data)

        if not isinstance(channel, disnake.VoiceChannel):
            if not message.thread:
                await message.create_thread(name="song requests", auto_archive_duration=10080)
            elif message.thread.archived:
                await message.thread.edit(archived=False, reason=f"Song request reativado por: {inter.author}.")
        elif player and player.guild.me.voice.channel != channel:
            await player.connect(channel.id)

        guild_data['player_controller']['channel'] = str(channel.id)
        guild_data['player_controller']['message_id'] = str(message.id)
        await bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)

        reset_txt = f"{inter.prefix}reset" if isinstance(inter, CustomContext) else "/reset"

        embed = disnake.Embed(
            description=f"**{msg}**\n\nObs: Caso queira reverter esta configuração, apenas use o comando {reset_txt} ou "
                        f"delete o canal/post {channel.mention}",
            color=bot.get_color(guild.me)
        )
        try:
            await inter.edit_original_message(embed=embed, components=None)
        except (AttributeError, disnake.InteractionNotEditable):
            try:
                await inter.response.edit_message(embed=embed, components=None)
            except:
                await inter.send(embed=embed, ephemeral=True)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1, 30), commands.BucketType.guild)
    @ensure_bot_instance(return_first=True)
    @commands.command(
        name="reset", usage="[--delete]",
        description="Resetar as configurações relacionadas ao canal de pedir música (song request)."
    )
    async def reset_legacy(self, ctx: CustomContext, *, delete_channel: str = None):

        if delete_channel == "--delete":
            delete_channel = "sim"

        await self.reset.callback(self=self, inter=ctx, delete_channel=delete_channel)

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

        bot = await select_bot_pool(inter)

        if not bot:
            return

        await inter.response.defer(ephemeral=True)

        guild = bot.get_guild(inter.guild_id) or inter.guild

        if not guild.me.guild_permissions.manage_threads:
            raise GenericError(f"Não tenho permissão de **{perms_translations['manage_threads']}** no servidor.")

        channel_inter = bot.get_channel(inter.channel.id)

        guild_data = await bot.get_data(guild.id, db_name=DBModel.guilds)

        try:
            channel = bot.get_channel(int(guild_data['player_controller']['channel'])) or \
                      await bot.fetch_channel(int(guild_data['player_controller']['channel']))
        except:
            channel = None

        if not channel or channel.guild.id != inter.guild_id:
            raise GenericError(f"**Não há canais de pedido de música configurado (ou o canal foi deletado).**")

        try:
            if isinstance(channel.parent, disnake.ForumChannel):
                await channel.delete(reason=f"{inter.author.id} resetou player")
                if channel_inter != channel:
                    await inter.edit_original_message("O post foi deletado com sucesso!", embed=None, components=None)
                return
        except AttributeError:
            pass

        try:
            original_message = await channel.fetch_message(int(guild_data["player_controller"]["message_id"]))
        except:
            original_message = None

        guild_data["player_controller"].update({
            "message_id": None,
            "channel": None
        })

        await self.bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)

        try:
            func = inter.edit_original_message
        except AttributeError:
            try:
                func = inter.response.edit_message
            except AttributeError:
                func = inter.send

        await func(
            embed=disnake.Embed(
                color=self.bot.get_color(guild.me),
                description="**O Canal de pedir música foi resetado com sucesso.**"
            ), components=None
        )

        try:
            player: LavalinkPlayer = bot.music.players[guild.id]
        except KeyError:
            pass
        else:
            player.static = False
            player.message = None
            player.text_channel = channel_inter
            player.process_hint()
            await player.invoke_np(force=True)

        try:
            if delete_channel == "sim":
                await channel.delete(reason=f"Player resetado por: {inter.author}")

            elif original_message:
                await original_message.edit(
                    content=f"Canal de pedir música foi resetado pelo membro {inter.author.mention}.",
                    embed=None, components=[
                        disnake.ui.Button(label="Reconfigurar este canal", emoji="💠",
                                          custom_id="musicplayer_request_channel")
                    ]
                )
                await original_message.thread.edit(archived=True, reason=f"Player resetado por {inter.author}.")
        except Exception as e:
            traceback.print_exc()
            raise GenericError(
                "**O canal de pedir música foi resetado da base de dados mas ocorreu um erro no processo:** "
                f"```py\n{repr(e)}```"
            )

    @commands.has_guild_permissions(manage_guild=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @ensure_bot_instance(return_first=True)
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

        bot = await select_bot_pool(inter)
        guild = bot.get_guild(inter.guild_id) or inter.guild
        role = guild.get_role(role.id)

        if role == guild.default_role:
            await inter.send("Você não pode adicionar esse cargo.", ephemeral=True)
            return

        guild_data = await bot.get_data(guild.id, db_name=DBModel.guilds)

        if str(role.id) in guild_data['djroles']:
            await inter.send(f"O cargo {role.mention} já está na lista de DJ's", ephemeral=True)
            return

        guild_data['djroles'].append(str(role.id))

        await bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)

        await inter.send(f"O cargo {role.mention} foi adicionado à lista de DJ's\nBot: {bot.user.mention}", ephemeral=True)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @ensure_bot_instance(return_first=True)
    @commands.command(description="Remover um cargo para a lista de DJ's do servidor.", usage="[id / nome / @cargo]")
    async def remove_dj_role_legacy(self, ctx: CustomContext, *, role: disnake.Role):
        await self.remove_dj_role(ctx, inter=ctx, role=role)

    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Remover um cargo para a lista de DJ's do servidor.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def remove_dj_role(
            self,
            inter: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="cargo", description="Cargo")
    ):

        bot = await select_bot_pool(inter)

        if not bot:
            return

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        if not guild_data['djroles']:

            await inter.send("Não há cargos na lista de DJ's.", ephemeral=True)
            return

        guild = bot.get_guild(inter.guild_id) or inter.guild
        role = guild.get_role(role.id)

        if str(role.id) not in guild_data['djroles']:
            await inter.send(f"O cargo {role.mention} não está na lista de DJ's\n\n" + "Cargos:\n" +
                                              " ".join(f"<#{r}>" for r in guild_data['djroles']), ephemeral=True)
            return

        guild_data['djroles'].remove(str(role.id))

        await bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)

        await inter.send(f"O cargo {role.mention} foi removido da lista de DJ's\nBot: {bot.user.mention}", ephemeral=True)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @ensure_bot_instance(return_first=True)
    @commands.command(description="Alterar aparência/skin do player.", name="changeskin", aliases=["setskin", "skin"])
    async def change_skin_legacy(self, ctx: CustomContext):

        await self.change_skin.callback(self=self, inter=ctx)

    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Alterar aparência/skin do player.",
        default_member_permissions=disnake.Permissions(manage_guild=True)
    )
    async def change_skin(self, inter: disnake.AppCmdInter):

        bot = await select_bot_pool(inter)

        if not bot:
            return

        skin_list = [s for s in bot.player_skins if s not in bot.config["IGNORE_SKINS"].split()]
        static_skin_list = [s for s in bot.player_static_skins if s not in bot.config["IGNORE_STATIC_SKINS"].split()]

        await inter.response.defer(ephemeral=True)

        guild = bot.get_guild(inter.guild_id) or inter.guild

        guild_data = await bot.get_data(guild.id, db_name=DBModel.guilds)

        selected = guild_data["player_controller"]["skin"] or bot.default_skin
        static_selected = guild_data["player_controller"]["static_skin"] or bot.default_static_skin

        skins_opts = [disnake.SelectOption(emoji="🎨", label=f"Modo normal: {s}", value=s, default=selected == s) for s in skin_list]
        static_skins_opts = [disnake.SelectOption(emoji="🎨", label=f"Song-Request: {s}", value=s, default=static_selected == s) for s in static_skin_list]

        select_view = SkinSelector(inter, skins_opts, static_skins_opts)
        select_view.skin_selected = selected
        select_view.static_skin_selected = static_selected

        try:
            func = inter.store_message.edit
        except:
            try:
                func = inter.edit_original_message
            except AttributeError:
                func = inter.send

        embed = disnake.Embed(
            description="**Selecione as skins disponíveis abaixo:**\n\n"
                        "**Modo Normal:**\n\n" + "\n".join(f"`{s}` [`(visualizar)`]({bot.player_skins[s].preview})" for s in skin_list) + "\n\n" 
                        "**Modo fixo (song-request):**\n\n" + "\n".join(f"`{s}` [`(visualizar)`]({bot.player_static_skins[s].preview})" for s in static_skin_list),
            colour=bot.get_color(guild.me)
        )

        msg = await func(
            embed=embed,
            view=select_view
        )

        await select_view.wait()

        if select_view.skin_selected is None:
            await select_view.interaction.response.edit_message(
                view=None,
                embed=disnake.Embed(description="**Solicitação cancelada.**", colour=bot.get_color(guild.me))
            )
            return

        if not select_view.interaction:
            try:
                msg = await inter.original_message()
            except AttributeError:
                pass
            await msg.edit(view=None, embed=disnake.Embed(description="**Tempo esgotado!**", colour=bot.get_color(guild.me)))
            return

        inter = select_view.interaction

        guild_data["player_controller"]["skin"] = select_view.skin_selected
        guild_data["player_controller"]["static_skin"] = select_view.static_skin_selected

        await bot.update_data(inter.guild_id, guild_data, db_name=DBModel.guilds)

        kwargs = {
            "embed": disnake.Embed(
                description=f"**A skin do player do servidor foi alterado com sucesso.**\n"
                            f"Modo normal: `{select_view.skin_selected}`\n"
                            f"Modo fixo (song-request): `{select_view.static_skin_selected}`",
                color=bot.get_color(guild.me)
            ).set_footer(text=f"{bot.user} - [{bot.user.id}]", icon_url=bot.user.display_avatar.with_format("png").url)
        }

        if msg:
            await msg.edit(view=None, **kwargs)
        elif inter.response.is_done():
            await inter.edit_original_message(view=None, **kwargs)
        else:
            await inter.send(ephemeral=True, **kwargs)

        try:
            player: LavalinkPlayer = bot.music.players[inter.guild_id]
        except KeyError:
            pass
        else:
            if not player.static:
                await player.destroy_message()
            player.skin = select_view.skin_selected
            player.skin_static = select_view.static_skin_selected
            player.auto_update = 0 # linha temporária para resolver possíveis problemas com skins custom criadas por usuarios antes desse commit.
            player.controller_mode = True
            player.set_command_log(text=f"{inter.author.mention} alterou a skin do player para: "
                                        f"**{select_view.skin_selected} / {select_view.static_skin_selected}**",
                                   emoji="🎨")
            player.process_hint()
            await player.invoke_np(force=True)

    @ensure_bot_instance()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @ensure_bot_instance(return_first=True)
    @commands.command(
        name="nodeinfo",
        aliases=["llservers", "ll"],
        description="Ver informações dos servidores de música."
    )
    async def nodeinfo_legacy(self, ctx: CustomContext):
        await self.nodeinfo.callback(self=self, inter=ctx)

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.slash_command(
        description=f"{desc_prefix}Ver informações dos servidores de música (lavalink servers)."
    )
    async def nodeinfo(self, inter: disnake.AppCmdInter):

        bot = await select_bot_pool(inter)

        if not bot:
            return

        guild = bot.get_guild(inter.guild_id) or inter.guild

        em = disnake.Embed(color=bot.get_color(guild.me), title="Servidores de música:")

        if not bot.music.nodes:
            em.description = "**Não há servidores.**"
            await inter.send(embed=em)
            return

        for identifier, node in bot.music.nodes.items():

            if not node.available: continue

            txt = f"Região: `{node.region.title()}`\n"

            try:
                current_player = node.players[inter.guild_id]
            except KeyError:
                current_player = None

            if not node.stats:
                txt += "`Sem informações adicionais...`"

            else:
                used = humanize.naturalsize(node.stats.memory_used)
                total = humanize.naturalsize(node.stats.memory_allocated)
                free = humanize.naturalsize(node.stats.memory_free)
                cpu_cores = node.stats.cpu_cores
                cpu_usage = f"{node.stats.lavalink_load * 100:.2f}"
                started = node.stats.players

                txt += f'RAM: `{used}/{free}`\n' \
                       f'RAM Total: `{total}`\n' \
                       f'CPU Cores: `{cpu_cores}`\n' \
                       f'Uso de CPU: `{cpu_usage}%`\n' \
                       f'Uptime: <t:{int((disnake.utils.utcnow() - datetime.timedelta(milliseconds=node.stats.uptime)).timestamp())}:R>\n'

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
            em.set_footer(text=f"{bot.user} - [{bot.user.id}]", icon_url=bot.user.display_avatar.with_format("png").url)

        await inter.send(embed=em, ephemeral=True)


def setup(bot: BotCore):
    bot.add_cog(MusicSettings(bot))
