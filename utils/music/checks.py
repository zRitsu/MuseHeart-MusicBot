from __future__ import annotations
import asyncio
import traceback
from typing import TYPE_CHECKING, Union

import disnake
from disnake.ext import commands

from utils.music.converters import time_format
from utils.music.errors import NoVoice, NoPlayer, NoSource, NotRequester, NotDJorStaff, \
    GenericError, MissingVoicePerms, DiffVoiceChannel, PoolException
from utils.music.models import LavalinkPlayer
from utils.db import DBModel
from utils.others import CustomContext


def can_send_message(
        channel: Union[disnake.TextChannel, disnake.VoiceChannel, disnake.Thread],
        bot: Union[disnake.ClientUser, disnake.Member]
):

    perms = channel.permissions_for(channel.guild.me)

    if not perms.send_messages:
        raise GenericError(f"**{bot.mention} não possui permissão de enviar mensagens no canal:** {channel.mention}")

    if not perms.embed_links:
        raise GenericError(f"**{bot.mention} não possui permissão de inserir links no canal: {channel.mention}**")

    return True


async def check_requester_channel(ctx: CustomContext):

    guild_data = await ctx.bot.get_data(ctx.guild_id, db_name=DBModel.guilds)

    if guild_data['player_controller']["channel"] == str(ctx.channel.id):

        if isinstance(ctx.channel.parent, disnake.ForumChannel):
            if ctx.channel.owner_id != ctx.bot.user.id:
                raise PoolException()
            else:
                return True

        raise GenericError("**Use apenas comandos de barra (/) neste canal!**", self_delete=True, delete_original=15)

    return True


def check_forum(inter, bot):

    if not bot.check_bot_forum_post(inter.channel, raise_error=False):

        if inter.channel.owner_id == bot.user.id:
            inter.music_bot = bot
            inter.music_guild = inter.guild
            return True
        else:
            raise PoolException()

async def check_pool_bots(inter, only_voiced: bool = False, check_player: bool = True, return_first=False):

    try:
        inter.music_bot
        return True
    except AttributeError:
        pass

    if isinstance(inter, (disnake.MessageInteraction, disnake.ModalInteraction)):
        return

    if not inter.bot.config["GLOBAL_PREFIX"]:
        try:
            inter.music_bot = inter.bot
            inter.music_guild = inter.guild
        except AttributeError:
            pass
        return True

    if not inter.guild_id:
        raise GenericError("**Esse comando não pode ser usado nas mensagens privada.**")

    try:
        if inter.bot.user.id in inter.author.voice.channel.voice_states:
            inter.music_bot = inter.bot
            inter.music_guild = inter.guild
            return True
    except AttributeError:
        pass

    mention_prefixed = False

    if isinstance(inter, CustomContext):

        is_forum = check_forum(inter, inter.bot)

        if is_forum:
            return True

        if not (mention_prefixed:=inter.message.content.startswith(tuple(inter.bot.pool.bot_mentions))):

            msg_id = f"{inter.guild_id}-{inter.channel.id}-{inter.message.id}"

            if msg_id in inter.bot.pool.message_ids:

                def check(ctx, b_id):
                    try:
                        return f"{ctx.guild_id}-{ctx.channel.id}-{ctx.message.id}" == msg_id
                    except AttributeError:
                        return

                inter.bot.dispatch("pool_payload_ready", inter)

                try:
                    ctx, bot_id = await inter.bot.wait_for("pool_dispatch", check=check, timeout=10)
                except asyncio.TimeoutError:
                    raise PoolException()

                if not bot_id or bot_id != inter.bot.user.id:
                    raise PoolException()

                inter.music_bot = inter.bot
                inter.music_guild = inter.guild

                return True

            inter.bot.pool.message_ids.add(msg_id)

        else:

            if not check_player and not only_voiced:

                if inter.author.voice:
                    pass
                else:
                    return True

            elif not inter.author.voice:

                if return_first:
                    return True

                raise NoVoice()

            if inter.bot.user.id in inter.author.voice.channel.voice_states:
                inter.music_bot = inter.bot
                inter.music_guild = inter.guild
                return True

            if only_voiced:
                pass

            elif not inter.guild.me.voice:
                inter.music_bot = inter.bot
                inter.music_guild = inter.guild
                return True

    free_bot = []

    for bot in sorted(inter.bot.pool.bots, key=lambda b: b.identifier):

        if not bot.bot_ready:
            continue

        if bot.user.id == inter.bot.user.id and mention_prefixed:
            continue

        if not (guild := bot.get_guild(inter.guild_id)):
            continue

        if not (author := guild.get_member(inter.author.id)):
            continue

        inter.author = author

        if not author.voice:

            inter.bot.dispatch("pool_dispatch", inter, None)

            if return_first:
                free_bot.append([bot, guild])
                continue

            raise NoVoice()

        if bot.user.id in author.voice.channel.voice_states:

            inter.music_bot = bot
            inter.music_guild = guild
            free_bot.clear()

            if isinstance(inter, CustomContext) and bot.user.id != inter.bot.user.id and not mention_prefixed:
                try:
                    await inter.music_bot.wait_for(
                        "pool_payload_ready", timeout=10,
                        check=lambda ctx: f"{ctx.guild_id}-{ctx.channel.id}-{ctx.message.id}" == msg_id
                    )
                except asyncio.TimeoutError:
                    pass
                inter.music_bot.dispatch("pool_dispatch", inter, bot.user.id)
                raise PoolException()
            return True

        if only_voiced:
            continue

        if not guild.me.voice:
            free_bot.append([bot, guild])

    try:
        if not isinstance(inter, CustomContext) and not inter.guild.voice_client:

            if only_voiced:
                inter.bot.dispatch("pool_dispatch", None)
                raise NoPlayer()

            inter.music_bot = inter.bot
            inter.music_guild = inter.guild
            inter.bot.dispatch("pool_dispatch", inter, None)
            return True
    except AttributeError:
        pass

    if free_bot:
        inter.music_bot, inter.music_guild = free_bot.pop(0)
        free_bot.clear()
        if isinstance(inter, CustomContext) and not mention_prefixed and inter.music_bot.user.id != inter.bot.user.id:
            try:
                await inter.music_bot.wait_for(
                    "pool_payload_ready", timeout=10,
                    check=lambda ctx: f"{ctx.guild_id}-{ctx.channel.id}-{ctx.message.id}" == msg_id
                )
            except asyncio.TimeoutError:
                pass
            inter.music_bot.dispatch("pool_dispatch", inter, inter.music_bot.user.id, bot=inter.music_bot)
            raise PoolException()
        return True

    elif check_player:

        inter.bot.dispatch("pool_dispatch", inter, None)

        if return_first:
            inter.music_bot = inter.bot
            inter.music_guild = inter.guild
            return True

        raise NoPlayer()

    extra_bots_counter = 0

    for bot in inter.bot.pool.bots:

        if not bot.appinfo.bot_public:
            continue

        if (bot.user.id == inter.bot.user.id):
            continue

        if bot.get_guild(inter.guild_id):
            continue

        extra_bots_counter += 1

    components = []

    if not inter.guild:

        extra_bots_invite = []

        msg = "**Não há bots de música compatível no servidor...**"

        for b in bot.pool.bots:

            if str(b.user.id) in bot.config["INTERACTION_BOTS"]:
                continue

            extra_bots_invite.append(f"[`{disnake.utils.escape_markdown(str(b.user.name))}`]({disnake.utils.oauth_url(b.user.id, scopes=['applications.commands'])})")

        if extra_bots_invite:
            msg += f"\n\nVocê terá que adicionar um dos seguintes bots no servidor:\n{' **|** '.join(extra_bots_invite)}"

    else:
        msg = "**Todos os bots estão em uso nomento...**"
        if extra_bots_counter:
            components = [disnake.ui.Button(custom_id="bot_invite", label="Precisa de mais bots de música? Clique aqui.")]

    inter.bot.dispatch("pool_dispatch", inter, None)

    await inter.send(embed=disnake.Embed(description=msg, color=inter.bot.get_color()), components=components)

    raise PoolException()

def has_player():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        return True

    return commands.check(predicate)


def is_dj():

    async def predicate(inter):

        if not await has_perm(inter):
            raise NotDJorStaff()

        return True

    return commands.check(predicate)


def can_send_message_check():

    async def predicate(inter):
        # adaptar pra checkar outros bots

        if not inter.guild:

            if inter.guild_id:
                return True

            raise GenericError("**Este comando deve ser usado em um servidor...**")

        # TODO: tempfix para canal de forum (thread arquyivada)
        if isinstance(inter.channel, disnake.PartialMessageable):
            try:
                await inter.response.defer(ephemeral=True)
                inter.channel = await inter.bot.fetch_channel(inter.channel_id)
                if inter.channel.archived:
                    await inter.channel.edit(archived=False)
            except:
                pass

        can_send_message(inter.channel, inter.guild.me)
        return True

    return commands.check(predicate)


def is_requester():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player: LavalinkPlayer = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if not player.current:
            raise NoSource()

        if player.current.requester == inter.author.id:
            return True

        try:
            if await has_perm(inter):
                return True

        except NotDJorStaff:
            pass

        raise NotRequester()

    return commands.check(predicate)


def check_voice():

    async def predicate(inter):

        try:
            guild = inter.music_guild
        except AttributeError:
            guild = inter.guild

        try:
            if not inter.author.voice:
                raise NoVoice()
        except AttributeError:
            pass

        if not guild.me.voice:

            perms = inter.author.voice.channel.permissions_for(guild.me)

            if not perms.connect:
                raise MissingVoicePerms(inter.author.voice.channel)

        try:
            if inter.author.id not in guild.me.voice.channel.voice_states:
                raise DiffVoiceChannel()
        except AttributeError:
            pass

        return True

    return commands.check(predicate)


def has_source():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if not player.current:
            raise NoSource()

        return True

    return commands.check(predicate)


def check_stage_topic():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player: LavalinkPlayer = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if player.stage_title_event and (time_:=int((disnake.utils.utcnow() - player.start_time).total_seconds())) < 120:
            raise GenericError(
                f"**Você terá que aguardar {time_format((120 - time_) * 1000, use_names=True)} para usar essa função "
                f"com o anúncio automático do palco ativo...**"
            )

        return True

    return commands.check(predicate)

def user_cooldown(rate: int, per: int):
    def custom_cooldown(inter: disnake.Interaction):
        # if (await inter.bot.is_owner(inter.author)):
        #   return None  # sem cooldown

        return commands.Cooldown(rate, per)

    return custom_cooldown


#######################################################################


async def has_perm(inter):

    try:
        bot = inter.music_bot
        guild = inter.music_guild
        channel = bot.get_channel(inter.channel.id)
    except AttributeError:
        bot = inter.bot
        guild = inter.guild
        channel = inter.channel

    try:
        player: LavalinkPlayer = bot.music.players[inter.guild_id]
    except KeyError:
        return True

    if inter.author.id == player.player_creator or inter.author.id in player.dj:
        return True

    if inter.author.guild_permissions.manage_channels:
        return True

    if player.keep_connected:
        raise GenericError(f"**Erro!** Apenas membros com a permissão de **gerenciar servidor** "
                           "podem usar este comando/botão com o **modo 24/7 ativo**...")

    user_roles = [r.id for r in inter.author.roles]

    guild_data = await bot.get_data(guild.id, db_name=DBModel.guilds)

    if [r for r in guild_data['djroles'] if int(r) in user_roles]:
        return True

    if player.restrict_mode:
        raise GenericError(f"**Erro!** Apenas DJ's ou membros com a permissão de **gerenciar servidor** "
                           "podem usar este comando/botão com o **modo restrito ativo**...")

    vc = player.last_channel

    if not vc and inter.author.voice:
        player.dj.add(inter.author.id)

    elif not [m for m in vc.members if not m.bot and (m.guild_permissions.manage_channels or m.id in player.dj or m.id == player.player_creator)]:
        player.dj.add(inter.author.id)
        await channel.send(embed=disnake.Embed(
            description=f"{inter.author.mention} foi adicionado à lista de DJ's por não haver um no canal <#{vc.id}>.",
            color=player.bot.get_color(guild.me)), delete_after=10)
        return True

def check_channel_limit(member: disnake.Member, channel: Union[disnake.VoiceChannel, disnake.StageChannel]):

    if not channel.user_limit:
        return True

    if member.guild_permissions.move_members:
        return True

    if member.id in channel.voice_states:
        return True

    if (channel.user_limit - len(channel.voice_states)) > 0:
        return True

def can_connect(
        channel: Union[disnake.VoiceChannel, disnake.StageChannel],
        guild: disnake.Guild,
        check_other_bots_in_vc: bool = False,
):

    perms = channel.permissions_for(guild.me)

    if not perms.connect:
        raise GenericError(f"**Não tenho permissão para conectar no canal {channel.mention}**")

    if not isinstance(channel, disnake.StageChannel):

        if not perms.speak:
            raise GenericError(f"**Não tenho permissão para falar no canal {channel.mention}**")

        if not guild.voice_client and not check_channel_limit(guild.me, channel):
            raise GenericError(f"**O canal {channel.mention} está lotado!**")

    if check_other_bots_in_vc and any(m for m in channel.members if m.bot and m.id != guild.me.id):
        raise GenericError(f"**Há outro bot conectado no canal:** <#{channel.id}>")

async def check_deafen(me: disnake.Member = None):

    if me.voice.deaf:
        return True
    elif me.guild_permissions.deafen_members:
        try:
            await me.edit(deafen=True)
            return True
        except:
            traceback.print_exc()