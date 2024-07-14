# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import datetime
import os
import pickle
import random
import string
import traceback
from base64 import b64decode
from typing import TYPE_CHECKING, Union, Optional

import disnake
import humanize
from disnake.ext import commands

from utils.db import DBModel
from utils.music.converters import perms_translations, time_format
from utils.music.errors import GenericError, NoVoice
from utils.music.interactions import SkinEditorMenu
from utils.music.models import LavalinkPlayer
from utils.others import send_idle_embed, CustomContext, select_bot_pool, pool_command, CommandArgparse, update_inter

if TYPE_CHECKING:
    from utils.client import BotCore

channel_perms = ("send_messages", "embed_links", "read_messages")

thread_perms = ("send_messages_in_threads", "embed_links", "read_messages")

forum_perms = ("create_forum_threads", "send_messages_in_threads", "read_messages", "embed_links")

def check_channel_perm(channel: Union[disnake.StageChannel, disnake.VoiceChannel, disnake.ForumChannel, disnake.TextChannel]):

    if isinstance(channel, disnake.ForumChannel):
        missing_perms = [p for p, v in channel.permissions_for(channel.guild.me) if p in forum_perms and not v]
    elif isinstance(channel, disnake.Thread):
        missing_perms = [p for p,v in channel.parent.permissions_for(channel.guild.me) if p in thread_perms and not v]
    else:
        missing_perms = [p for p, v in channel.permissions_for(channel.guild.me) if p in channel_perms and not v]

    if missing_perms:
        raise GenericError(
            f"**{channel.guild.me.mention} kanal üzerinde aşağıdaki gerekli izinlere sahip değil {channel.mention}** ```ansi\n" +
            "\n".join(f"[0;33m{perms_translations.get(p, p)}[0m" for p in missing_perms) + "```")


class SkinSelector(disnake.ui.View):

    def __init__(
            self,
            ctx: Union[disnake.AppCmdInter, CustomContext],
            embed: disnake.Embed,
            select_opts: list,
            static_select_opts: list,
            global_select_opts: list = None,
            global_static_select_opts: list = None,
            global_mode=False,
    ):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.interaction: Optional[disnake.MessageInteraction] = None
        self.global_mode = global_mode
        self.skin_selected = None
        self.static_skin_selected = None
        self.select_opts = select_opts
        self.static_select_opts = static_select_opts
        self.global_select_opts = global_select_opts
        self.global_static_select_opts = global_static_select_opts
        self.embed = embed

        if not global_mode:
            self.skin_selected = [s.value for s in select_opts if s.default][0]
            self.static_skin_selected = [s.value for s in static_select_opts if s.default][0]
        else:
            try:
                self.skin_selected = [s.value for s in global_select_opts if s.default][0]
            except IndexError:
                self.skin_selected = self.ctx.bot.pool.default_skin
            try:
                self.static_skin_selected = [s.value for s in global_static_select_opts if s.default][0]
            except IndexError:
                self.static_skin_selected = self.ctx.bot.pool.default_static_skin

        self.rebuild_selects()

    def rebuild_selects(self):

        self.clear_items()

        if not self.global_mode:
            self.embed.title = "Görünüm seçici (Seçilen bota uygula)"

            for s in self.select_opts:
                s.default = self.skin_selected == s.value

            for s in self.static_select_opts:
                s.default = self.static_skin_selected == s.value

            select_opts = self.select_opts
            static_select_opts = self.static_select_opts

        else:
            self.embed.title = "Görünüm seçici (Sunucudaki tüm botlara uygulayın)"

            for s in self.global_select_opts:
                s.default = self.skin_selected == s.value

            for s in self.global_static_select_opts:
                s.default = self.static_skin_selected == s.value

            select_opts = self.global_select_opts
            static_select_opts = self.global_static_select_opts

        select_opts = disnake.ui.Select(options=select_opts, min_values=1, max_values=1)
        select_opts.callback = self.skin_callback
        self.add_item(select_opts)

        static_select_opts = disnake.ui.Select(options=static_select_opts, min_values=1, max_values=1)
        static_select_opts.callback = self.static_skin_callback
        self.add_item(static_select_opts)

        global_mode = disnake.ui.Button(label=("Devredışı Bırak" if self.global_mode else "Etkinleştir") + " Global Mod ", emoji="🌐")
        global_mode.callback = self.mode_callback
        self.add_item(global_mode)

        confirm_button = disnake.ui.Button(label="Kaydet", emoji="💾")
        confirm_button.callback = self.confirm_callback
        self.add_item(confirm_button)

        cancel_button = disnake.ui.Button(label="İptal", emoji="❌")
        cancel_button.callback = self.stop_callback
        self.add_item(cancel_button)

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:

        if inter.author.id == self.ctx.author.id:
            return True

        await inter.send(f"Sadece {self.ctx.author.mention} buradan etkileşime geçebilir!", ephemeral=True)
        return False

    async def skin_callback(self, inter: disnake.MessageInteraction):
        self.skin_selected = inter.data.values[0]
        self.rebuild_selects()
        await inter.response.edit_message(view=self)

    async def static_skin_callback(self, inter: disnake.MessageInteraction):
        self.static_skin_selected = inter.data.values[0]
        self.rebuild_selects()
        await inter.response.edit_message(view=self)

    async def mode_callback(self, inter: disnake.MessageInteraction):
        self.global_mode = not self.global_mode
        self.rebuild_selects()
        await inter.response.edit_message(view=self, embed=self.embed)

    async def confirm_callback(self, inter: disnake.MessageInteraction):
        self.interaction = inter
        self.stop()

    async def stop_callback(self, inter: disnake.MessageInteraction):
        self.interaction = inter
        self.skin_selected = None
        self.stop()


class PlayerSettings(disnake.ui.View):

    def __init__(self, ctx: Union[disnake.AppCmdInter, CustomContext], bot: BotCore, data: dict):
        super().__init__()
        self.ctx = ctx
        self.bot = bot
        self.enable_autoplay = data["autoplay"]
        self.check_other_bots_in_vc = data['check_other_bots_in_vc']
        self.enable_restrict_mode = data['enable_restrict_mode']
        self.default_player_volume = data['default_player_volume']
        self.message: Optional[disnake.Message] = None
        self.load_buttons()

    def load_buttons(self):

        self.clear_items()

        player_volume_select = disnake.ui.Select(
            placeholder="Standart bir birim seçin.",
            options=[
                        disnake.SelectOption(label=f"Standart Ses: {i}", default=i == self.default_player_volume,
                                             value=str(i)) for i in range(5, 101, 5)
                    ] + [
                disnake.SelectOption(label=f"Standart Ses: {i}", default=i == self.default_player_volume,
                                     description="Not: Yüzde 100'ün üzerinde ses kötü olabilir.",
                                     value=str(i)) for i in range(110, 151, 10)
            ]
        )

        player_volume_select.callback = self.volume_callback
        self.add_item(player_volume_select)

        check_other_bots_button = disnake.ui.Button(label="Uyumsuz botlara bağlanmayın.",
                                                    emoji="✅" if self.check_other_bots_in_vc else "🚫")
        check_other_bots_button.callback = self.check_other_bots_callback
        self.add_item(check_other_bots_button)

        restrict_mode_button = disnake.ui.Button(label="Kısıtlı mod",
                                                    emoji="✅" if self.enable_restrict_mode else "🚫")
        restrict_mode_button.callback = self.restrict_mode_callback
        self.add_item(restrict_mode_button)

        check_autoplay_button = disnake.ui.Button(label="Otomatik Oynatma.",
                                                    emoji="✅" if self.enable_autoplay else "🚫")
        check_autoplay_button.callback = self.autoplay_callback
        self.add_item(check_autoplay_button)

        close_button = disnake.ui.Button(label="Kaydet/Kapat", emoji="💾")
        close_button.callback = self.close_callback
        self.add_item(close_button)

    async def check_other_bots_callback(self, interaction: disnake.MessageInteraction):
        self.check_other_bots_in_vc = not self.check_other_bots_in_vc
        self.load_buttons()
        await interaction.response.edit_message(view=self)

    async def restrict_mode_callback(self, interaction: disnake.MessageInteraction):
        self.enable_restrict_mode = not self.enable_restrict_mode
        self.load_buttons()
        await interaction.response.edit_message(view=self)

    async def volume_callback(self, interaction: disnake.MessageInteraction):
        self.default_player_volume = int(interaction.data.values[0])
        self.load_buttons()
        await interaction.response.edit_message(view=self)

    async def autoplay_callback(self, interaction: disnake.MessageInteraction):
        self.enable_autoplay = not self.enable_autoplay
        self.load_buttons()
        await interaction.response.edit_message(view=self)

    async def close_callback(self, interaction: disnake.MessageInteraction):

        try:
            if isinstance(self.ctx, CustomContext):
                await self.message.edit(content="Değişiklikler başarıyla kaydedildi!", view=None, embed=None)
            else:
                await self.ctx.edit_original_message(content="Değişiklikler başarıyla kaydedildi!", view=None, embed=None)
        except Exception:
            traceback.print_exc()
        await self.save_data()
        self.stop()

    async def interaction_check(self, inter: disnake.MessageInteraction) -> bool:

        if inter.author.id == self.ctx.author.id:
            return True

        await inter.send(f"Sadece {self.ctx.author.mention} buradan etkileşime geçebilirsiniz!", ephemeral=True)
        return False

    async def save_data(self):
        guild_data = await self.bot.get_data(self.ctx.guild_id, db_name=DBModel.guilds)
        guild_data['autoplay'] = self.enable_autoplay
        guild_data['check_other_bots_in_vc'] = self.check_other_bots_in_vc
        guild_data['enable_restrict_mode'] = self.enable_restrict_mode
        guild_data['default_player_volume'] = int(self.default_player_volume)

        await self.bot.update_data(self.ctx.guild_id, guild_data, db_name=DBModel.guilds)

        try:
            player: LavalinkPlayer = self.bot.music.players[self.ctx.guild_id]
        except KeyError:
            pass
        else:
            await player.process_save_queue()

    async def on_timeout(self):

        if isinstance(self.ctx, CustomContext):
            await self.message.edit(
                embed=disnake.Embed(description="**Zaman doldu...**", color=self.bot.get_color()), view=None
            )
        else:
            await self.ctx.edit_original_message(
                embed=disnake.Embed(description="**Zaman doldu...**", color=self.bot.get_color()), view=None
            )

        await self.save_data()

        self.stop()


class MusicSettings(commands.Cog):

    emoji = "🔧"
    name = "Ayarlar"
    desc_prefix = f"[{emoji} {name}] | "

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.invite_cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=45, type=commands.BucketType.guild)

    player_settings_cd = commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.guild)
    player_settings_mc = commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(
        name="playersettings", aliases=["ps", "settings"],
        description="Oynatıcının varsayılan ayarlarından bazılarını değiştirme.",
        cooldown=player_settings_cd, max_concurrency=player_settings_mc
    )
    async def player_settings_legacy(self, ctx: CustomContext):
        await self.player_settings.callback(self=self, interaction=ctx)

    @commands.slash_command(
        description=f"{desc_prefix}Oynatıcının varsayılan ayarlarından bazılarını değiştirin.",
        default_member_permissions=disnake.Permissions(manage_guild=True), dm_permission=False
    )
    async def player_settings(self, interaction: disnake.AppCmdInter):

        inter, bot = await select_bot_pool(interaction, return_new=True)

        if not bot:
            return

        await inter.response.defer(ephemeral=True)

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        try:
            func = inter.store_message.edit
        except AttributeError:
            try:
                func = inter.edit_original_message
            except AttributeError:
                func = inter.send

        view = PlayerSettings(inter, bot, guild_data)

        view.message = await func(
            embed=disnake.Embed(
                description="**Oynatıcının varsayılan ayarlarını yapın:**",
                color=self.bot.get_color()
            ).set_author(name=str(bot.user), icon_url=bot.user.display_avatar.url), view=view
        )

        await view.wait()

    setup_cd = commands.CooldownMapping.from_cooldown(1, 20, commands.BucketType.guild)
    setup_mc =commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    setup_args = CommandArgparse()
    setup_args.add_argument('-reset', '--reset', '-purge', '--purge', action="store_true",
                             help="Seçilen kanaldaki mesajları temizleyin (100 mesaja kadar, forumlarda etkili değildir).")

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(
        name="setup", aliases=["songrequestchannel", "sgrc"], usage="{prefix}{cmd} [id|#canal]\nEx: {prefix}{cmd} #canal",
        description="Müzik istemek için özel bir kanal oluşturun/seçin ve sabit bir oynatıcı bırakın.",
        cooldown=setup_cd, max_concurrency=setup_mc, extras={"flags": setup_args}
    )
    async def setup_legacy(
            self,
            ctx: CustomContext,
            channel: Union[disnake.TextChannel, disnake.VoiceChannel, disnake.ForumChannel, None] = None, *args
    ):

        args, unknown = ctx.command.extras['flags'].parse_known_args(args)

        await self.setup.callback(self=self, interaction=ctx, target=channel,
                                  purge_messages=args.reset)

    @commands.slash_command(
        description=f"{desc_prefix}Müzik istemek için özel bir kanal oluşturun/seçin ve sabit bir oynatıcı bırakın.",
        default_member_permissions=disnake.Permissions(manage_guild=True), cooldown=setup_cd, max_concurrency=setup_mc,
        dm_permission=False
    )
    async def setup(
            self,
            interaction: disnake.AppCmdInter,
            target: Union[disnake.TextChannel, disnake.VoiceChannel, disnake.ForumChannel, disnake.StageChannel] = commands.Param(
                name="canal", default=None, description="Mevcut bir kanalı seçin"
            ),
            purge_messages: str = commands.Param(
                name="limpar_mensagens", default="no",
                description="Seçilen kanaldaki mesajları temizleyin (100 mesaja kadar, forumlarda etkili değildir).",
                choices=[
                    disnake.OptionChoice(
                        disnake.Localized("Yes", data={disnake.Locale.pt_BR: "Evet"}), "yes"
                    ),
                    disnake.OptionChoice(
                        disnake.Localized("No", data={disnake.Locale.pt_BR: "Hayır"}), "no"
                    )
                ],
            )
    ):

        inter, bot = await select_bot_pool(interaction, return_new=True)

        if not bot:
            return

        guild = bot.get_guild(inter.guild_id)

        channel = bot.get_channel(inter.channel.id)

        if target and bot != self.bot:
            target = bot.get_channel(target.id)

        channel_name = f'{bot.user.name} Song Request'

        if isinstance(target, disnake.ForumChannel) and not isinstance(inter, CustomContext):

            await inter.response.send_modal(
                title="Gönderi için bir isim seçin (30 saniye içinde)",
                custom_id=str(inter.id),
                components=[
                    disnake.ui.TextInput(
                        style=disnake.TextInputStyle.short,
                        label="Nome",
                        custom_id="forum_title",
                        min_length=4,
                        max_length=30,
                        value=channel_name[:30],
                        required=True
                    )
                ]
            )

            try:
                modal_inter: disnake.ModalInteraction = await inter.bot.wait_for("modal_submit", timeout=30,
                                                                           check=lambda i: i.data.custom_id == str(inter.id))
            except asyncio.TimeoutError:
                if isinstance(inter, disnake.MessageInteraction):
                    try:
                        await inter.delete_original_message()
                    except:
                        pass
                return

            if isinstance(inter, disnake.MessageInteraction):
                try:
                    await inter.delete_original_message()
                except:
                    pass

            update_inter(interaction, modal_inter)
            inter = modal_inter
            channel_name = inter.text_values["forum_title"]

        perms_dict = {
            "embed_links": True,
            "send_messages": True,
            "send_messages_in_threads": True,
            "read_messages": True,
            "create_public_threads": True,
            "read_message_history": True,
            "manage_messages": True,
            "manage_channels": True,
            "attach_files": True,
        }

        if guild.me.guild_permissions.administrator:
            perms_dict["manage_permissions"] = True

        channel_kwargs = {
            "overwrites": {
                guild.me: disnake.PermissionOverwrite(**perms_dict)
            }
        }

        await inter.response.defer(ephemeral=True)

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        original_message = None
        existing_channel = True

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
            description=f"**Bu müzik istek kanalı üye tarafından yeniden yapılandırıldı {inter.author.mention}.**",
            color=bot.get_color(guild.me)
        )

        async def get_message(original_message, target):

            if original_message and original_message.channel != target and original_message.guild.id == target.guild.id:

                try:
                    if isinstance(original_message.channel.parent, disnake.ForumChannel):
                        await original_message.thread.delete(reason=f"Oyuncu tarafından yeniden yapılandırıldı {inter.author}.")
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
                        reason=f"Oyuncu tarafından yeniden yapılandırıldı {inter.author}."
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

            buttons = [
                disnake.ui.Button(label="Metin kanalı oluştur", custom_id=f"text_channel_{id_}", emoji="💬", disabled=not guild.me.guild_permissions.manage_channels),
                disnake.ui.Button(label="Ses kanalı oluştur", custom_id=f"voice_channel_{id_}", emoji="🔊", disabled=not guild.me.guild_permissions.manage_channels),
                disnake.ui.Button(label="İptal", custom_id=f"voice_channel_cancel_{id_}", emoji="❌")
            ]

            if "COMMUNITY" in guild.features:
                buttons.insert(2, disnake.ui.Button(label="Sahne kanalı oluştur", custom_id=f"stage_channel_{id_}",
                                  emoji="<:stagechannel:1077351815533826209>", disabled=not guild.me.guild_permissions.manage_channels))

            color = self.bot.get_color(guild.me)

            embeds = [
                disnake.Embed(
                    description="**Bir kanal seçin " + ("veya aşağıdaki düğmelerden birine tıklayarak yeni bir kanal oluşturup şarkı talep edebilirsiniz." if guild.me.guild_permissions.manage_channels else "abaixo:") +'**' ,
                    color=color
                ).set_footer(text="Bir seçeneği seçmek/tıklamak için sadece 45 saniyeniz var.")
            ]

            if not guild.me.guild_permissions.manage_channels:
                embeds.append(
                    disnake.Embed(
                        description=f"Kanal oluşturma düğmeleri bot nedeniyle devre dışı bırakıldı **{bot.user.mention}** "
                                    "sahip değil **gerenciar canais** sunucu üzerinde.",
                        color=color
                    )
                )

            disnake.Embed(color=color).set_footer(
                text="Not: Bir forum kanalı kullanmak istiyorsanız, kanal listesinden bir kanal seçmeniz gerekir. "
                     "(Eğer bir forum kanalınız yoksa, manuel olarak bir forum kanalı oluşturmanız ve bunu kullanmanız gerekecektir. "
                     "komutunu tekrar ver."
            )

            msg_select = await func(
                embeds=embeds,
                components=[
                    disnake.ui.ChannelSelect(
                        custom_id=f"existing_channel_{id_}",
                        min_values=1, max_values=1,
                        channel_types=[
                            disnake.ChannelType.text,
                            disnake.ChannelType.voice,
                            disnake.ChannelType.stage_voice,
                            disnake.ChannelType.forum
                        ]
                    ),
                ] + buttons,
                **kwargs_msg
            )

            if isinstance(inter, CustomContext):
                bot_inter = bot
                check = (lambda i: i.message.id == msg_select.id and i.author.id == inter.author.id)
            else:
                bot_inter = inter.bot
                check = (lambda i: i.data.custom_id.endswith(f"_{id_}") and i.author.id == inter.author.id)

            done, pending = await asyncio.wait([
                bot_inter.loop.create_task(bot_inter.wait_for('button_click', check=check)),
                bot_inter.loop.create_task(bot_inter.wait_for('dropdown', check=check))
            ],
                timeout=45, return_when=asyncio.FIRST_COMPLETED)

            for future in pending:
                future.cancel()

            if not done:

                try:
                    inter.application_command.reset_cooldown(inter)
                except AttributeError:
                    try:
                        inter.command.reset_cooldown(inter)
                    except:
                        pass

                if msg_select:
                    func = msg_select.edit
                else:
                    try:
                        func = (await inter.original_message()).edit
                    except:
                        func = inter.message.edit

                try:
                    await func(
                        embed=disnake.Embed(
                            description="**Zaman doldu!**",
                            color=disnake.Color.red()
                        ),
                        components=None
                    )
                except disnake.NotFound:
                    pass
                except Exception:
                    traceback.print_exc()

                return

            inter_message = done.pop().result()

            update_inter(interaction, inter_message)

            if inter_message.data.custom_id.startswith("voice_channel_cancel"):

                await inter_message.response.edit_message(
                    embed=disnake.Embed(
                        description="**Operasyon iptal edildi...**",
                        color=self.bot.get_color(guild.me),
                    ), components=None
                )
                return

            if channel.category and channel.category.permissions_for(guild.me).send_messages:
                target = channel.category
            else:
                target = guild

            if inter_message.data.custom_id.startswith("existing_channel_"):
                target = bot.get_channel(int(inter_message.data.values[0]))
                existing_channel = True

            else:

                if not guild.me.guild_permissions.manage_channels:
                    raise GenericError(f"**Bot {bot.user.mention} yeni bir kanal oluşturmak için kanalları yönetme iznine sahip değildir.**")

                await inter_message.response.defer()
                if inter_message.data.custom_id.startswith("voice_channel_"):
                    target = await target.create_voice_channel(f"{bot.user.name} player controller", **channel_kwargs)
                elif inter_message.data.custom_id.startswith("stage_channel_"):
                    target = await target.create_stage_channel(f"{bot.user.name} player controller", **channel_kwargs)
                else:
                    target = await target.create_text_channel(f"{bot.user.name} player controller", **channel_kwargs)

                existing_channel = False

            inter = inter_message

        if target == guild.public_updates_channel:
            raise GenericError("**Discord güncelleme kanalını kullanamazsınız.**")

        if target == guild.rules_channel:
            raise GenericError("**Bir kural kanalı kullanamazsınız.**")

        check_channel_perm(target)

        if isinstance(target, disnake.ForumChannel):

            channel_kwargs.clear()

            if not target.permissions_for(guild.me).create_forum_threads:
                raise GenericError(f"**{bot.user.mention} kanalda yayın yapma iznine sahip değil {target.mention}.**")

            try:
                id_ = f"modal_{inter.id}"
            except AttributeError:
                id_ = f"modal_{inter.message.id}"

            if not inter.response.is_done():

                await inter.response.send_modal(
                    title="Forum gönderisi için bir ad tanımlayın",
                    custom_id=id_,
                    components=[
                        disnake.ui.TextInput(
                            style=disnake.TextInputStyle.short,
                            label="Nome",
                            custom_id="forum_title",
                            min_length=4,
                            max_length=30,
                            value=channel_name[:30],
                            required=True
                        )
                    ]
                )

                try:
                    modal_inter: disnake.ModalInteraction = await inter.bot.wait_for("modal_submit", timeout=30, check=lambda i: i.custom_id == id_)
                except asyncio.TimeoutError:
                    try:
                        func = inter.edit_original_message
                    except AttributeError:
                        func = msg_select.edit
                    await func(embed=disnake.Embed(description="### Zaman doldu.!", color=bot.get_color(guild.me)), view=None)
                    return

                try:
                    await msg_select.delete()
                except:
                    pass

                update_inter(interaction, modal_inter)
                inter = modal_inter

                await inter.response.defer()

                channel_name = inter.text_values["forum_title"]

            thread = None
            message = None

            for t in target.threads:
                if t.owner_id == bot.user.id:
                    try:
                        message = await t.fetch_message(t.id)
                    except disnake.NotFound:
                        continue
                    thread = t
                    thread_kw = {}
                    if thread.locked and target.permissions_for(target.guild.me).manage_threads:
                        thread_kw.update({"locked": False, "archived": False})
                    elif thread.archived:
                        thread_kw["archived"] = False
                    if thread_kw:
                        await t.edit(**thread_kw)
                    break

            if not thread and guild.me.guild_permissions.read_message_history:
                async for t in target.archived_threads(limit=100):
                    if t.owner_id == bot.user.id:
                        try:
                            message = await t.fetch_message(t.id)
                        except disnake.NotFound:
                            continue
                        thread = t
                        thread_kw = {}
                        if thread.locked and target.permissions_for(target.guild.me).manage_threads:
                            thread_kw.update({"locked": False, "archived": False})
                        elif thread.archived:
                            thread_kw["archived"] = False
                        if thread_kw:
                            await t.edit(**thread_kw)
                        break

            if not thread:

                if not target.permissions_for(guild.me).manage_threads:
                    raise GenericError(
                        f"**{bot.user.mention} kanaldaki konuları yönetme iznine sahip değil {target.mention}.**\n"
                        f"`Not: Bu izni geçici olarak verebilir ve ardından komutu tekrar kullanabilirsiniz "
                        f"bu izni kaldırabilirsiniz.`")

                """if not target.permissions_for(guild.me).create_forum_threads:
                    raise GenericError(
                        f"**{bot.user.mention} kanalda yayın yapma iznine sahip değil {target.mention}.**")"""

                thread_wmessage = await target.create_thread(
                    name=channel_name,
                    content="Şarkı istekleri için gönder.",
                    auto_archive_duration=10080,
                    slowmode_delay=5,
                )
                message = thread_wmessage.message

            message = await send_idle_embed(target=message, bot=bot, force=True,
                                            guild_data=guild_data)

            target = message.channel

            await get_message(original_message, target)

        else:

            if existing_channel and not guild.me.guild_permissions.administrator and not target.permissions_for(guild.me).manage_permissions:
                raise GenericError(f"**{guild.me.mention} yönetici iznine sahip değil veya "
                                   f"kanal izinlerini yönetme {target.mention}** izinleri düzenlemek için "
                                   f"müzik istek sisteminin düzgün çalışması için gerekli.\n\n"
                                   f"Yönetici izni vermek veya yönetici izinlerini düzenlemek istemiyorsanız"
                                   f" Kanal {target.mention} kanal izinlerini yönetmeme izin vermek için. Şu komutu kullanabilirsiniz "
                                   f"bir hedef kanal seçmeden.")

            if not target.permissions_for(guild.me).read_messages:
                raise GenericError(f"{bot.user.mention} kanaldaki mesajları okuma izni {target.mention}")

            if purge_messages == "yes":
                await target.purge(limit=100, check=lambda m: m.author != guild.me or not m.thread)

            message = await get_message(original_message, target)

            if not message:

                async for m in target.history(limit=100):

                    if m.author == guild.me and m.thread:
                        message = m
                        break

        if existing_channel:
            try:
                await target.edit(**channel_kwargs)
            except:
                traceback.print_exc()

        channel = target

        msg = f"{inter.author.mention}, kanalda müzik istek sistemi kurulmuştur <#{channel.id}> bot aracılığıyla: {bot.user.mention}"

        if player and player.text_channel != target:
            if player.static:
                try:
                    await player.message.thread.edit(
                        archived=True,
                        locked=True,
                        reason=f"Oyuncu tarafından yeniden yapılandırıldı {inter.author}."
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

        if isinstance(channel, disnake.TextChannel):
            if not message.thread:
                if channel.permissions_for(guild.me).create_public_threads:
                    await message.create_thread(name="sarki-istekleri", auto_archive_duration=10080)
            else:
                thread_kw = {}
                if message.thread.locked and message.thread.permissions_for(guild.me).manage_threads:
                    thread_kw.update({"locked": False, "archived": False})
                elif message.thread.archived and message.thread.owner_id == bot.user.id:
                    thread_kw["archived"] = False
                if thread_kw:
                    await message.thread.edit(reason=f"Şarkı isteği tarafından yeniden etkinleştirildi: {inter.author}.", **thread_kw)
        elif player and isinstance(channel, (disnake.VoiceChannel, disnake.StageChannel)) and player.guild.me.voice.channel != channel:
            await player.connect(channel.id)

        guild_data['player_controller']['channel'] = str(channel.id)
        guild_data['player_controller']['message_id'] = str(message.id)
        await bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)

        reset_txt = f"{inter.prefix}reset" if isinstance(inter, CustomContext) else "/reset"

        embed = disnake.Embed(
            description=f"**{msg}**\n\nNot: Bu ayarı geri almak isterseniz, şu komutu kullanmanız yeterlidir {reset_txt} veya "
                        f"kanalı/gönderiyi sil {channel.mention}",
            color=bot.get_color(guild.me)
        )

        if not inter.response.is_done():
            try:
                await inter.response.edit_message(embed=embed, components=None)
            except AttributeError:
                await inter.send(embed=embed)
        try:
            await inter.edit_original_message(embed=embed, components=None)
        except (AttributeError, disnake.InteractionNotEditable):
            try:
                await inter.response.edit_message(embed=embed, components=None)
            except:
                await inter.send(embed=embed, ephemeral=True)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.bot_has_guild_permissions(manage_threads=True)
    @commands.command(
        name="reset",
        description="Şarkı istek kanalı ile ilgili ayarları sıfırlayın.",
        cooldown=setup_cd, max_concurrency=setup_mc
    )
    async def reset_legacy(self, ctx: CustomContext, *, delete_channel: str = None):

        if delete_channel == "--delete":
            delete_channel = "Evet"

        await self.reset.callback(self=self, interaction=ctx, delete_channel=delete_channel)

    @commands.slash_command(
        description=f"{desc_prefix}Şarkı istek kanalı ile ilgili ayarları sıfırlayın.",
        default_member_permissions=disnake.Permissions(manage_guild=True), cooldown=setup_cd, max_concurrency=setup_mc,
        dm_permission=False
    )
    async def reset(
            self,
            interaction: disnake.AppCmdInter,
            delete_channel: str = commands.Param(
                name="deletar_canal",
                description="doyuncu kumanda kanalını seçme", default=None, choices=["Evet", "Hayır"]
            )
    ):

        inter, bot = await select_bot_pool(interaction)

        if not bot:
            return

        await inter.response.defer(ephemeral=True)

        guild = bot.get_guild(inter.guild_id) or inter.guild

        if not guild.me.guild_permissions.manage_threads:
            raise GenericError(f"Bunu yapmama izin yok. **{perms_translations['manage_threads']}** sunucu üzerinde.")

        channel_inter = bot.get_channel(inter.channel.id)

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        try:
            channel = bot.get_channel(int(guild_data['player_controller']['channel'])) or \
                      await bot.fetch_channel(int(guild_data['player_controller']['channel']))
        except:
            channel = None

        if not channel or channel.guild.id != inter.guild_id:
            raise GenericError(f"**Ayarlanmış müzik istek kanalı yok (veya kanal silinmiş).**")

        try:
            if isinstance(channel.parent, disnake.ForumChannel):
                await channel.delete(reason=f"{inter.author.id} resetou player")
                if channel_inter != channel:
                    await inter.edit_original_message("Gönderi başarıyla silindi!", embed=None, components=None)

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
                description="**Müzik istek kanalı başarıyla sıfırlandı.**"
            ), components=[]
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
            if delete_channel == "Evet":
                await channel.delete(reason=f"Oyuncu sıfırlama: {inter.author}")

            elif original_message:
                await original_message.edit(
                    content=f"Müzik istek kanalı üye tarafından sıfırlandı {inter.author.mention}.",
                    embed=None, components=[
                        disnake.ui.Button(label="Bu kanalı yeniden yapılandırın", emoji="💠",
                                          custom_id="musicplayer_request_channel")
                    ]
                )
                await original_message.thread.edit(archived=True, reason=f"Oyuncu tarafından sıfırlandı {inter.author}.")
        except Exception as e:
            traceback.print_exc()
            raise GenericError(
                "**Müzik istek kanalı veritabanından sıfırlandı ancak işlem sırasında bir hata oluştu:** "
                f"```py\n{repr(e)}```"
            )

    djrole_cd = commands.CooldownMapping.from_cooldown(1, 7, commands.BucketType.guild)
    djrole_mc =commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(name="adddjrole",description="Sunucunun DJ listesine bir iş ekleyin.",
                      usage="{prefix}{cmd} [id|isim|@rol]\nÖrn: {prefix}{cmd} @djrol", cooldown=djrole_cd, max_concurrency=djrole_mc)
    async def add_dj_role_legacy(self, ctx: CustomContext, *, role: disnake.Role):
        await self.add_dj_role.callback(self=self, interaction=ctx, role=role)

    @commands.slash_command(
        description=f"{desc_prefix}Sunucunun DJ listesine bir iş ekleyin.", dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True), cooldown=djrole_cd, max_concurrency=djrole_mc
    )
    async def add_dj_role(
            self,
            interaction: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="rol", description="rol")
    ):

        inter, bot = await select_bot_pool(interaction)
        guild = bot.get_guild(inter.guild_id) or inter.guild
        role = guild.get_role(role.id)

        if role == guild.default_role:
            await inter.send("Bu pozisyonu ekleyemezsiniz.", ephemeral=True)
            return

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        if str(role.id) in guild_data['djroles']:
            await inter.send(f"{role.mention} Rolü zaten DJ listesinde", ephemeral=True)
            return

        guild_data['djroles'].append(str(role.id))

        await bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)

        await inter.send(f"{role.mention} Rolü DJ listesine eklenmiştir.", ephemeral=True)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(name="removedjrole", description="Sunucunun DJ listesinden bir işi kaldırın.",
                      usage="{prefix}{cmd} [id|isim|@rol]\nÖrn: {prefix}{cmd} @djrol",
                      cooldown=djrole_cd, max_concurrency=djrole_mc)
    async def remove_dj_role_legacy(self, ctx: CustomContext, *, role: disnake.Role):
        await self.remove_dj_role.callback(self=self, interaction=ctx, role=role)

    @commands.slash_command(
        description=f"{desc_prefix}Sunucunun DJ listesinden bir işi kaldırın.", dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True), cooldown=djrole_cd, max_concurrency=djrole_mc
    )
    async def remove_dj_role(
            self,
            interaction: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="pozisyon", description="Pozisyon")
    ):

        inter, bot = await select_bot_pool(interaction)

        if not bot:
            return

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        if not guild_data['djroles']:

            await inter.send("DJ listesinde herhangi bir Rol bulunmamaktadır.", ephemeral=True)
            return

        guild = bot.get_guild(inter.guild_id) or inter.guild
        role = guild.get_role(role.id)

        if str(role.id) not in guild_data['djroles']:
            await inter.send(f"{role.mention} Rolü DJ listesinde değil\n\n" + "Pozisyon:\n" +
                                              " ".join(f"<#{r}>" for r in guild_data['djroles']), ephemeral=True)
            return

        guild_data['djroles'].remove(str(role.id))

        await bot.update_data(guild.id, guild_data, db_name=DBModel.guilds)

        await inter.send(f"{role.mention} Rolü DJ listesinden çıkarıldı.", ephemeral=True)

    skin_cd = commands.CooldownMapping.from_cooldown(1, 20, commands.BucketType.guild)
    skin_mc =commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @commands.has_guild_permissions(manage_guild=True)
    @commands.command(description="Oyuncu görünümünü/cildini değiştirme.", name="changeskin", aliases=["skin", "skins"],
                      cooldown=skin_cd, max_concurrency=skin_mc)
    async def change_skin_legacy(self, ctx: CustomContext):

        await self.change_skin.callback(self=self, interaction=ctx)

    @commands.slash_command(
        description=f"{desc_prefix}Oyuncu görünümünü/cildini değiştirme.", cooldown=skin_cd, max_concurrency=skin_mc,
        default_member_permissions=disnake.Permissions(manage_guild=True), dm_permission=False
    )
    async def change_skin(self, interaction: disnake.AppCmdInter):

        inter, bot = await select_bot_pool(interaction, return_new=True)

        if not bot:
            return

        skin_list = [s for s in bot.player_skins if s not in bot.config["IGNORE_SKINS"].split()]
        static_skin_list = [s for s in bot.player_static_skins if s not in bot.config["IGNORE_STATIC_SKINS"].split()]

        await inter.response.defer(ephemeral=True)

        guild = bot.get_guild(inter.guild_id) or inter.guild

        add_skin_prefix = (lambda d: [f"> custom_skin: {i}" for i in d.keys()])

        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

        global_data = await bot.get_global_data(guild.id, db_name=DBModel.guilds)

        global_mode = global_data["global_skin"]

        selected = guild_data["player_controller"]["skin"] or bot.pool.default_skin
        static_selected = guild_data["player_controller"]["static_skin"] or bot.pool.default_static_skin

        global_selected = global_data["player_skin"] or bot.pool.default_skin
        global_static_selected = global_data["player_skin_static"] or bot.pool.default_static_skin

        skins_opts = [disnake.SelectOption(emoji="💠" if s.startswith("> custom_skin: ") else "🎨", label=f"Normal Mod: {s.replace('> custom_skin: ', '')}", value=s, **{"default": True, "description": "Aktif Skin"} if selected == s else {}) for s in skin_list + add_skin_prefix(global_data["custom_skins"])]
        static_skins_opts = [disnake.SelectOption(emoji="💠" if s.startswith("> custom_skin: ") else "🎨", label=f"Şarkı İsteği: {s.replace('> custom_skin: ', '')}", value=s, **{"default": True, "description": "Aktif Skin"} if static_selected == s else {}) for s in static_skin_list + add_skin_prefix(global_data["custom_skins_static"])]

        global_skins_opts = [disnake.SelectOption(emoji="💠" if s.startswith("> custom_skin: ") else "🎨", label=f"Normal Mod: {s.replace('> custom_skin: ', '')}", value=s, **{"default": True, "description": "Aktif Skin"} if global_selected == s else {}) for s in skin_list + add_skin_prefix(global_data["custom_skins"])]
        global_static_skins_opts = [disnake.SelectOption(emoji="💠" if s.startswith("> custom_skin: ") else "🎨", label=f"Şarkı İsteği: {s.replace('> custom_skin: ', '')}", value=s, **{"default": True, "description": "Aktif Skin"} if global_static_selected == s else {}) for s in static_skin_list + add_skin_prefix(global_data["custom_skins_static"])]

        embed = disnake.Embed(
            description="```ansi\n[31;1mNormal Mod:[0m``` " + ", ".join(f"[`[{s}]`]({bot.player_skins[s].preview})" for s in skin_list) + "\n\n" 
                        "```ansi\n[33;1mSabit Mod (Şarkı İsteği):[0m``` " + ", ".join(f"[`[{s}]`]({bot.player_static_skins[s].preview})" for s in static_skin_list) +
                        "\n\n`Not: Genel(Global) modda dış görünüm tüm botlara genel olarak uygulanacaktır.`",
            colour=bot.get_color(guild.me)
        ).set_image("https://cdn.discordapp.com/attachments/554468640942981147/1082887587770937455/rainbow_bar2.gif")

        try:
            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Bot seçildi: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
        except AttributeError:
            pass

        select_view = SkinSelector(inter, embed, skins_opts, static_skins_opts, global_skins_opts, global_static_skins_opts, global_mode)

        try:
            func = inter.store_message.edit
        except:
            try:
                func = inter.edit_original_message
            except AttributeError:
                func = inter.send

        msg = await func(
            embed=embed,
            view=select_view
        )

        await select_view.wait()

        if select_view.skin_selected is None:
            await select_view.interaction.response.edit_message(
                view=None,
                embed=disnake.Embed(description="**Talep iptal edildi.**", colour=bot.get_color(guild.me))
            )
            return

        if not select_view.interaction:
            try:
                msg = await inter.original_message()
            except AttributeError:
                pass
            for c in select_view.children:
                c.disabled = True
            await msg.edit(view=select_view)
            return

        update_inter(interaction, select_view.interaction)

        inter = select_view.interaction

        await inter.response.defer()

        try:
            global_data.update({"global_skin": select_view.global_mode})
        except:
            pass

        changed_skins_txt = ""

        if select_view.global_mode:
            try:
                global_data.update(
                    {
                        "player_skin": select_view.skin_selected,
                        "player_skin_static": select_view.static_skin_selected
                    }
                )
            except:
                pass
            else:
                await bot.update_global_data(inter.guild_id, global_data, db_name=DBModel.guilds)

            if global_selected != select_view.skin_selected:
                try:
                    changed_skins_txt += f"Global - Normal Mod: [`{select_view.skin_selected}`]({self.bot.player_skins[select_view.skin_selected].preview})\n"
                except:
                    changed_skins_txt += f"Global - Normal Mod: `{select_view.skin_selected.replace('> custom_skin: ', '[custom skin]: ')}`\n"

            if global_static_selected != select_view.static_skin_selected:
                try:
                    changed_skins_txt += f"Global - Şarkı İsteği: [`{select_view.static_skin_selected}`]({self.bot.player_static_skins[select_view.static_skin_selected].preview})\n"
                except:
                    changed_skins_txt += f"Global - Şarkı İsteği: `{select_view.static_skin_selected.replace('> custom_skin: ', '[custom skin]: ')}`\n"

        else:
            guild_data["player_controller"]["skin"] = select_view.skin_selected
            guild_data["player_controller"]["static_skin"] = select_view.static_skin_selected
            await bot.update_data(inter.guild_id, guild_data, db_name=DBModel.guilds)

            if selected != select_view.skin_selected:
                try:
                    changed_skins_txt += f"Normal Mod: [`{select_view.skin_selected}`]({self.bot.player_skins[select_view.skin_selected].preview})\n"
                except:
                    changed_skins_txt += f"Normal Mod: `{select_view.skin_selected.replace('> custom_skin: ', '[custom skin]: ')}`\n"

            if static_selected != select_view.static_skin_selected:
                try:
                    changed_skins_txt += f"Şarkı İsteği: [`{select_view.static_skin_selected}`]({self.bot.player_static_skins[select_view.static_skin_selected].preview})\n"
                except:
                    changed_skins_txt += f"Şarkı İsteği: `{select_view.static_skin_selected.replace('> custom_skin: ', '[custom skin]: ')}`\n"

        if global_mode != select_view.global_mode:
            changed_skins_txt += "Global Skin: `" + ("Aktif" if select_view.global_mode else "Kapalı") + "`\n"

        if not changed_skins_txt:
            txt = "**Skin ayarlarında herhangi bir değişiklik yapılmadı...**"
        else:
            txt = f"**Sunucunun oyuncu görünümü başarıyla değiştirildi.**\n{changed_skins_txt}"

        kwargs = {
            "embed": disnake.Embed(
                description=txt,
                color=bot.get_color(guild.me)
            ).set_footer(text=f"{bot.user} - [{bot.user.id}]", icon_url=bot.user.display_avatar.with_format("png").url)
        }

        if isinstance(inter, CustomContext):
            await msg.edit(view=None, **kwargs)
        elif inter.response.is_done():
            await inter.edit_original_message(view=None, **kwargs)
        else:
            await inter.send(ephemeral=True, **kwargs)

        for b in self.bot.pool.get_guild_bots(interaction.guild_id):

            try:
                player: LavalinkPlayer = b.music.players[inter.guild_id]
            except KeyError:
                continue

            last_skin = str(player.skin)
            last_static_skin = str(player.skin_static)

            if player.static:

                if select_view.static_skin_selected == last_static_skin:
                    continue

            elif select_view.skin_selected == last_skin:
                continue

            try:
                await player.destroy_message()
            except:
                traceback.print_exc()

            player.skin = select_view.skin_selected
            player.skin_static = select_view.static_skin_selected

            for n, s in global_data["custom_skins"].items():
                if isinstance(s, str):
                    global_data["custom_skins"][n] = pickle.loads(b64decode(s))

            for n, s in global_data["custom_skins_static"].items():
                if isinstance(s, str):
                    global_data["custom_skins_static"][n] = pickle.loads(b64decode(s))

            player.custom_skin_data = global_data["custom_skins"]
            player.custom_skin_static_data = global_data["custom_skins_static"]
            player.setup_features()

            player.setup_hints()
            player.process_hint()
            player.set_command_log(text=f"{inter.author.mention} alterou a skin do player.", emoji="🎨")

            try:
                if player.controller_mode and not [m for m in player.guild.me.voice.channel.members if not m.bot]:
                    player.start_auto_skip()
            except:
                traceback.print_exc()

            await player.invoke_np(force=True)
            await asyncio.sleep(1.5)

    @commands.cooldown(2, 10, commands.BucketType.member)
    @commands.has_guild_permissions(manage_channels=True)
    @pool_command(aliases=["la"], description="RPC aracılığıyla birlikte dinlemek için davet göndermeyi etkinleştirin "
                                                                "(Sistem hala test ediliyor)")
    async def listenalong(self, ctx: CustomContext):

        try:
            bot = ctx.music_bot
            guild = ctx.music_guild
        except AttributeError:
            bot = ctx.bot
            guild = bot.get_guild(ctx.guild_id)

        #if not guild.me.guild_permissions.create_instant_invite:
        #    raise GenericError(f"**{bot.user.mention} não possui permissão de criar convites instantâneos...**")

        if not ctx.author.voice:
            raise NoVoice()

        await ctx.reply(
            embed=disnake.Embed(
                description=f"**Bir kanal daveti oluşturun {ctx.author.voice.channel.mention}"
                            f"\"Misafir olarak davet et\" işaretleyin ve ardından aşağıdaki düğmeye tıklayarak bağlantıyı "
                            f"açılan kısma girin.**\n\n"
                            f"Dikkat edin! Bu seçeneğe sahip değilseniz, bu özellik discordunuzda mevcut değil demektir. "
                            f"Bota kalıcı erişim vermekten kaçınmak veya izin sorunlarından kaçınmak için "
                            f"devam etmenizi önermiyorum."
            ).set_image(url="https://cdn.discordapp.com/attachments/1261835711783370802/1261835733547749486/gSuyP8D.jpg").
            set_footer(text="Not: son kullanma tarihi, kullanım sayısı veya kullanım süresi gibi sınırlamalar olmaksızın bir davetiye oluşturun. "
                            "invite linkini bir kişilik oluşturmanızı öneririm."),
            components=[disnake.ui.Button(label="Davetiye gönder", custom_id=f"listen_along_{ctx.author.id}")],
            fail_if_not_exists=False
        )

    @commands.Cog.listener("on_button_click")
    async def send_listen_along_invite(self, inter: disnake.MessageInteraction):

        if not inter.data.custom_id.startswith("listen_along_"):
            return

        if not inter.data.custom_id.endswith(str(inter.author.id)):
            return await inter.send("**Bu düğmeyi kullanamazsınız.**", ephemeral=True)

        if not inter.author.voice.channel:
            return await inter.send("**Davetiyeyi göndermek için bir ses kanalında olmanız gerekir.**", ephemeral=True)

        await inter.response.send_modal(
            title="Birlikte dinlemeye davet edin",
            custom_id="listen_along_modal",
            components=[
                disnake.ui.TextInput(
                    style=disnake.TextInputStyle.short,
                    label="Davetiyeyi aşağıdaki alana yapıştırın:",
                    custom_id="invite_url",
                    min_length=25,
                    max_length=36,
                    required=True,
                ),
            ]
        )

    @commands.Cog.listener("on_modal_submit")
    async def listen_along_modal(self, inter: disnake.ModalInteraction):

        if inter.data.custom_id != "listen_along_modal":
            return

        if not inter.author.voice.channel:
            return await inter.send("**Davetiyeyi göndermek için bir ses kanalında olmanız gerekir.**", ephemeral=True)

        bucket = self.invite_cooldown.get_bucket(inter)
        retry_after = bucket.update_rate_limit()

        if retry_after:
            return await inter.send("**Beklemelisin {} davetiye göndermek için**".format(time_format(int(retry_after) * 1000, use_names=True)), ephemeral=True)

        await inter.response.defer(ephemeral=True)

        try:
            invite = await self.bot.fetch_invite(inter.text_values['invite_url'].strip(), with_expiration=True)
        except disnake.NotFound:
            return await inter.edit_original_message("Geçersiz bağlantı veya davetiye mevcut değil/süresi dolmuş")

        if invite.max_uses:
            return await inter.edit_original_message("Davetiyenin maksimum sayıda kullanımı olabilir")

        if invite.target_user:
            return await inter.edit_original_message("Davetiye yalnızca 1 kullanıcının kullanması için yapılandırılamaz.")

        channel = None

        for bot in self.bot.pool.get_guild_bots(inter.guild_id):

            channel = bot.get_channel(invite.channel.id)

            if not channel:
                continue

            if not isinstance(channel, disnake.VoiceChannel):
                return await inter.edit_original_message("**Bu özellik yalnızca ses kanallarında çalışır.**")

            break

        if not channel:
            return await inter.edit_original_message("**Verilen davetin sunucusuna eklenmiş uyumlu bot yok.**")

        global_data = await self.bot.get_global_data(inter.guild_id, db_name=DBModel.guilds)

        if len(global_data["listen_along_invites"]) > 4:
            return await inter.edit_original_message(
                embed=disnake.Embed(
                    description="**Geçerli sunucuda davet sınırı aşıldı, davetiyelerden en az birini silin "
                                "sunucunun altında:** ```ansi\n" +
                                ", ".join(f"[31;1m{c}[0m" for c in global_data["listen_along_invites"]) + "```",
                    color=self.bot.get_color()
                )
            )

        global_data["listen_along_invites"][str(channel.id)] = invite.url

        await self.bot.update_global_data(inter.guild_id, global_data, db_name=DBModel.guilds)

        await inter.edit_original_message(
            f"**Bağlantı {invite} olduğunda RPC aracılığıyla gönderilmek üzere başarıyla etkinleştirildi / güncellendi "
            f"kanaldaki aktif oyuncu {inter.author.voice.channel.mention}.**\n"
            f"`Not: Durumunuzu görüntülemek istiyorsanız ve RPC uygulamanız yoksa, /rich_presence komutunu kullanarak "
            f"daha fazla bilgi için.`"
        )

        for bot in self.bot.pool.get_guild_bots(inter.guild_id):

            try:
                p = bot.music.players[inter.guild_id]
            except KeyError:
                continue

            if p.guild.me.voice.channel == inter.author.voice.channel:
                p.listen_along_invite = invite.url
                await p.process_rpc()
                await p.process_save_queue()

    @commands.Cog.listener("on_modal_submit")
    async def rpc_create_modal(self, inter: disnake.ModalInteraction):

        if inter.data.custom_id != "rpc_token_create":
            return

        await inter.response.defer(ephemeral=True)

        data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)

        if inter.text_values["token_input"] == data["token"]:
            await inter.send("Seu token é igual ao token atual!", ephemeral=True)
            return

        await self.bot.get_cog("RPCCog").close_presence(inter)

        data["token"] = inter.text_values["token_input"]

        await self.bot.update_global_data(id_=inter.author.id, data=data, db_name=DBModel.users)

        await inter.edit_original_message(f"Belirteciniz başarıyla içe aktarıldı/düzenlendi!\n"
                                          f"Not: RPC uygulamasında belirteci ekleyin/güncelleyin.")

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.command(
        name="nodeinfo",
        aliases=["llservers", "ll"],
        description="Müzik sunucuları hakkındaki bilgileri görüntüleyin."
    )
    async def nodeinfo_legacy(self, ctx: CustomContext):
        await self.nodeinfo.callback(self=self, interaction=ctx)

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.slash_command(
        description=f"{desc_prefix}Müzik sunucuları hakkındaki bilgileri görüntüleyin. (lavalink servers).", dm_permission=False
    )
    async def nodeinfo(self, interaction: disnake.AppCmdInter):

        inter, bot = await select_bot_pool(interaction, return_new=True)

        if not bot:
            return

        guild = bot.get_guild(inter.guild_id) or inter.guild

        em = disnake.Embed(color=bot.get_color(guild.me), title="Müzik sunucuları:")

        if not bot.music.nodes:
            em.description = "**Sunucu yok.**"
            await inter.send(embed=em)
            return

        failed_nodes = set()

        for identifier, node in bot.music.nodes.items():

            if not node.available: continue

            try:
                current_player = node.players[inter.guild_id]
            except KeyError:
                current_player = None

            if not node.stats or not node.is_available:
                failed_nodes.add(node.identifier)
                continue

            txt = f"Bölge: `{node.region.title()}`\n"

            used = humanize.naturalsize(node.stats.memory_used)
            total = humanize.naturalsize(node.stats.memory_allocated)
            free = humanize.naturalsize(node.stats.memory_free)
            cpu_cores = node.stats.cpu_cores
            cpu_usage = f"{node.stats.lavalink_load * 100:.2f}"
            started = node.stats.players

            txt += f'RAM: `{used}/{free}`\n' \
                   f'RAM Toplam: `{total}`\n' \
                   f'CPU Çekirdekleri: `{cpu_cores}`\n' \
                   f'CPU kullanımı: `{cpu_usage}%`\n' \
                   f'Lavalink sürümü: `v{node.version}`\n' \
                   f'Çalışma süresi: <t:{int((disnake.utils.utcnow() - datetime.timedelta(milliseconds=node.stats.uptime)).timestamp())}:R>\n'

            if started:
                txt += "Oynatıcılar: "
                players = node.stats.playing_players
                idle = started - players
                if players:
                    txt += f'`[▶️{players}]`' + (" " if idle else "")
                if idle:
                    txt += f'`[💤{idle}]`'

                txt += "\n"

            if node.website:
                txt += f'[`Website do server`]({node.website})\n'

            status = "🌟" if current_player else "✅"

            em.add_field(name=f'**{identifier}** `{status}`', value=txt)
            em.set_footer(text=f"{bot.user} - [{bot.user.id}]", icon_url=bot.user.display_avatar.with_format("png").url)

        embeds = [em]

        if failed_nodes:
            embeds.append(
                disnake.Embed(
                    title="**Başarısız sunucular** `❌`",
                    description=f"```ansi\n[31;1m" + "\n".join(failed_nodes) + "[0m\n```",
                    color=bot.get_color(guild.me)
                )
            )

        if isinstance(inter, disnake.MessageInteraction):
            await inter.response.edit_message(embeds=embeds, view=None)
        else:
            await inter.send(embeds=embeds, ephemeral=True)

    customskin_cd = commands.CooldownMapping.from_cooldown(1, 10, commands.BucketType.guild)
    customskin__mc =commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="customskin", aliases=["setskin", "cskin", "cs", "ss"],
                      description="Müzik çalarda kullanmak için kendi görünümlerinizi/şablonlarınızı oluşturun.",
                      cooldown=customskin_cd, max_concurrency=customskin__mc)
    async def customskin_legacy(self, ctx: CustomContext):
        await self.custom_skin.callback(self=self, inter=ctx)

    @commands.slash_command(cooldown=customskin_cd, max_concurrency=customskin__mc,
                            description=f"{desc_prefix}Müzik çalar için kendi görünümlerinizi/şablonlarınızı oluşturun.",
                            default_member_permissions=disnake.Permissions(administrator=True), dm_permission=False)
    async def custom_skin(self, inter: disnake.AppCmdInter):

        inter, bot = await select_bot_pool(inter, return_new=True)

        if not bot:
            return

        await inter.response.defer()

        global_data = await bot.get_global_data(inter.guild_id, db_name=DBModel.guilds)

        view = SkinEditorMenu(inter, bot, guild=bot.get_guild(inter.guild_id), global_data=global_data)

        if isinstance(inter, disnake.MessageInteraction):
            func = inter.edit_original_message
        else:
            func = inter.send
        view.message = await func(view=view, **view.build_embeds())
        await view.wait()

    @commands.Cog.listener("on_button_click")
    async def editor_placeholders(self, inter: disnake.MessageInteraction):

        if inter.data.custom_id != "skin_editor_placeholders" or not inter.guild:
            return

        await inter.send(
            ephemeral=True,
            embed=disnake.Embed(
                color=self.bot.get_color(inter.guild.me),
                description="### Özel görünümler için yer tutucular:\n```ansi\n"
                            "[34;1m{track.title}[0m -> Şarkının adı\n"
                            "[34;1m{track.title_25}[0m -> Şarkının adı (en fazla 25 karakter)\n"
                            "[34;1m{track.title_42}[0m -> Şarkının adı (en fazla 42 karakter)\n"
                            "[34;1m{track.title_58}[0m -> Şarkının adı (en fazla 58 karakter)\n"
                            "[34;1m{track.url}[0m -> Müzik bağlantısı\n"
                            "[34;1m{track.author}[0m -> Yükleyicinin/Şarkı Sanatçısının Adı\n"
                            "[34;1m{track.duration}[0m -> Müzik temposu/süresi\n"
                            "[34;1m{track.thumb}[0m -> Şarkı küçük resmi/artwork bağlantısı\n"
                            "[34;1m{playlist.name}[0m -> Müziğin kaynak çalma listesinin adı\n"
                            "[34;1m{playlist.url}[0m -> Şarkının kaynak çalma listesinin bağlantısı/Url'si\n"
                            "[34;1m{player.loop.mode}[0m -> Oyuncu tekrar modu\n"
                            "[34;1m{player.queue.size}[0m -> Kuyruktaki şarkı sayısı\n"
                            "[34;1m{player.volume}[0m -> Oyuncu ses seviyesi\n"
                            "[34;1m{player.autoplay}[0m -> Otomatik Oynatma (Açık/Kapalı)\n"
                            "[34;1m{player.nightcore}[0m -> Nightcore efekti (Açık/Kapalı)\n"
                            "[34;1m{player.hint}[0m -> Oynatıcıyı kullanmak için ipuçları\n"
                            "[34;1m{player.log.text}[0m -> Oyuncu günlüğü\n"
                            "[34;1m{player.log.emoji}[0m -> Oyuncu günlüğü emojisi\n"
                            "[34;1m{requester.global_name}[0m -> Şarkıyı talep eden üyenin global adı.\n"
                            "[34;1m{requester.display_name}[0m -> Şarkıyı talep eden üyenin görünen adı.\n"
                            "[34;1m{requester.mention}[0m -> Şarkıyı talep eden üyeden bahsedin\n"
                            "[34;1m{requester.avatar}[0m -> Şarkıyı talep eden üyenin avatarına bağlantı\n"
                            "[34;1m{guild.color}[0m -> Botun sunucudaki en yüksek konumunun rengi\n"
                            "[34;1m{guild.icon}[0m -> Sunucu simgesi bağlantısı\n"
                            "[34;1m{guild.name}[0m -> Sunucu adı\n"
                            "[34;1m{guild.id}[0m -> Sunucu Kimliği\n"
                            "[34;1m{queue_format}[0m -> Önceden biçimlendirilmiş kuyruktaki şarkılar (yapılandır düğmesini kullanın "
                            "stili değiştirmek istiyorsanız yer tutucu)\n"
                            "[34;1m{track.number}[0m -> Şarkının kuyruktaki konumunun numarası (aşağıdakilerle birlikte işlevseldir "
                            "yer tutucu: [31;1m{queue_format}[0m)```"
            )
        )

class RPCCog(commands.Cog):

    emoji = "🔧"
    name = "Configurações"
    desc_prefix = f"[{emoji} {name}] | "

    def __init__(self, bot: BotCore):
        self.bot = bot

    rpc_cd = commands.CooldownMapping.from_cooldown(1, 30, commands.BucketType.user)

    @commands.command(description="Durumunuzda rich-presence sistemini etkinleştirin/devre dışı bırakın.",
                      name="richpresence", aliases=["rich_presence", "rpc"], cooldown=rpc_cd)
    async def rich_presence_legacy(self, ctx: CustomContext):

        await self.rich_presence.callback(self=self, inter=ctx)

    @commands.slash_command(
        description=f"{desc_prefix}Durumunuzda rich-presence sistemini etkinleştirin/devre dışı bırakın.", cooldown=rpc_cd,
        dm_permission=False
    )
    async def rich_presence(self, inter: disnake.AppCmdInter):

        if not self.bot.config["ENABLE_RPC_COMMAND"] and not any([await b.is_owner(inter.author) for b in self.bot.pool.get_guild_bots(inter.guild_id)]):
            raise GenericError("**Bu komut ayarlarımda devre dışı bırakıldı...**\n"
                               "Bu komutu yalnızca geliştiricim herkese açık olarak etkinleştirebilir.")

        if not self.bot.config["RPC_PUBLIC_URL"] and not self.bot.config["RPC_SERVER"]:
            raise GenericError("**O RPC_SERVER não foi configurado na ENV/ENVIRONMENTS (ou arquivo .env)**")

        components = []

        embed = disnake.Embed(
            color=self.bot.get_color(),
            description="**RPC aracılığıyla dinlediğiniz müziği görüntülemek için uygulamayı kullanmaya yönelik mini kılavuz:\n\n"
                        "Uygulamayı indirin (musicbot_rpc.zip) "
                        "[aqui](https://github.com/zRitsu/Discord-MusicBot-RPC/releases).\n\n"
                        "musicbot_rpc.zip dosyasını çıkarın ve klasördeki musicbot_rpc dosyasını açın ve " \
                        "Aşağıdaki websocket bağlantısını uygulamaya ekleyin (sekme: Soket Ayarları):** ```ansi\n" \
                        f"{(self.bot.config['RPC_PUBLIC_URL'] or self.bot.config['RPC_SERVER']).replace('$PORT', os.environ.get('PORT', '80'))}```"
        )

        embed.set_footer(text="Not: Şu anda sadece discord masaüstü ile windows üzerinde çalışıyor, mobil cihazlarda ve discord web'de "
                              "çalışmıyor.\n\nDikkat: Bu özelliği botun sahibi aktif etmemiş olabilir!")

        if self.bot.config["ENABLE_RPC_AUTH"]:

            embed.description += "\n**RPC erişimini yetkilendirmek için bir belirteç oluşturmanız/oluşturmanız/ithal etmeniz gerekecektir " \
                                 "(Aşağıdaki düğmeleri kontrol edin), belirteci kopyalayın ve uygulamada (Sekme: Soket Ayarları) " \
                                 "üzerine tıklayın \"Jeton kolye\"**"

            components.extend(
                [
                    disnake.ui.Button(label="Tokeni oluştur/sıfırla", custom_id=f"rpc_gen.{inter.author.id}", emoji="🔑",
                                      row=0),
                    disnake.ui.Button(label="Tokeni içe aktar/düzenle/görüntüle", custom_id=f"rpc_create.{inter.author.id}",
                                      emoji="✍️", row=0),
                    disnake.ui.Button(label="Tokeni Kaldır (Devre Dışı Bırak)", custom_id=f"rpc_remove.{inter.author.id}",
                                      emoji="♻️", row=1),
                ]
            )

        embed.description += "\n\n**Şimdi tek yapmanız gereken \"Presence\'ı Başlat\" düğmesine tıklamak" \
                             "ve uyumlu botlarla müzik dinlemek.**"

        embed.set_author(
            name=f"{inter.author.display_name}#{inter.author.discriminator} - [ {inter.author.id} ]",
            icon_url=inter.author.display_avatar.with_static_format("png").url
        )

        if isinstance(inter, CustomContext):
            components.append(
                disnake.ui.Button(label="Kapat", custom_id=f"rpc_close.{inter.author.id}", emoji="❌", row=1),
            )

        await inter.send(
            embed=embed,
            components=components,
            ephemeral=True
        )

    @commands.Cog.listener("on_button_click")
    async def rpc_button_event(self, inter: disnake.MessageInteraction):

        if not inter.data.custom_id.startswith("rpc_"):
            return

        button_id, user_id = inter.data.custom_id.split(".")

        if user_id != str(inter.author.id):
            await inter.send(f"Sadece <@{user_id}> mesaj butonlarını kullanabilirsiniz!", ephemeral=True)
            return

        if button_id == "rpc_gen":
            await inter.response.defer()

            data = await self.bot.get_global_data(id_=user_id, db_name=DBModel.users)

            if data["token"]:
                await self.close_presence(inter)

            data["token"] = "".join(random.choice(string.ascii_letters + string.digits) for i in range(50))
            await self.bot.update_global_data(id_=user_id, data=data, db_name=DBModel.users)
            msg = f"RPC (Rich Presence) uygulamasında kullanılacak token başarıyla oluşturuldu!\n\n" \
                  f"`Jeton üretildi:` ||{data['token']}||"

        elif button_id == "rpc_create":

            kwargs = {}

            try:

                data = await self.bot.get_global_data(id_=user_id, db_name=DBModel.users)

                if len(data["token"]) == 50:
                    kwargs["value"] = data["token"]
            except:
                pass

            await inter.response.send_modal(
                title="Tokeni içe aktar",
                custom_id="rpc_token_create",
                components=[
                    disnake.ui.TextInput(
                        style=disnake.TextInputStyle.short,
                        label="Belirteci aşağıdaki alana yapıştırın:",
                        placeholder="Not: Güvenlik nedeniyle, buraya asla kişisel bir şifre eklemeyin!",
                        custom_id="token_input",
                        min_length=50,
                        max_length=50,
                        required=True,
                        **kwargs
                    ),
                ]
            )

            if not inter.message.flags.ephemeral:
                await inter.message.delete()

            return

        elif button_id == "rpc_remove":

            await inter.response.defer()

            await self.close_presence(inter)

            data = await self.bot.get_global_data(id_=user_id, db_name=DBModel.users)

            data["token"] = ""
            await self.bot.update_global_data(id_=user_id, data=data, db_name=DBModel.users)
            msg = "Belirteç başarıyla kaldırıldı!\n" \
                  "RPC sistemi artık kullanıcınızda devre dışı bırakılacaktır."

        else: # button_id == "rpc_close"
            await inter.message.delete()
            return

        if inter.message.flags.ephemeral:
            await inter.edit_original_message(content=msg, embeds=[], components=[])
        else:
            await inter.send(f"{inter.author.mention}: {msg}", embeds=[], components=[], ephemeral=True)
            await inter.message.delete()

    async def close_presence(self, inter: Union[disnake.MessageInteraction, disnake.ModalInteraction]):

        for b in self.bot.pool.get_guild_bots(inter.guild_id):
            try:
                player: LavalinkPlayer = b.music.players[inter.guild_id]
            except KeyError:
                continue

            try:
                if inter.author.id not in player.guild.me.voice.channel.voice_states:
                    continue
            except AttributeError:
                continue

            stats = {
                "op": "close",
                "bot_id": self.bot.user.id,
                "bot_name": str(self.bot.user),
                "thumb": self.bot.user.display_avatar.replace(size=512, static_format="png").url,
            }

            await player._send_rpc_data([inter.author.id], stats)

def setup(bot: BotCore):

    bot.add_cog(MusicSettings(bot))
    bot.add_cog(RPCCog(bot))

