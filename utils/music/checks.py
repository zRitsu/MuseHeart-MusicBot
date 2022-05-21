from typing import Union
import disnake
from disnake.ext import commands
from .converters import perms_translations
from .errors import NoVoice, NoPlayer, NoSource, NotRequester, NotDJorStaff, DiffVoiceChannel, GenericError, \
    MissingVoicePerms
from .models import LavalinkPlayer, YTDLPlayer


def has_player():

    def predicate(inter):

        try:
            inter.bot.music.players[inter.guild.id]
        except KeyError:
            raise NoPlayer()

        return True

    return commands.check(predicate)


def is_dj():

    async def predicate(inter):

        try:
            if not inter.bot.music.players[inter.guild.id].restrict_mode:
                return True
        except KeyError:
            return True

        if not await has_perm(inter):
            raise NotDJorStaff()

        return True

    return commands.check(predicate)


def can_send_message():

    async def predicate(inter):

        if not inter.channel.permissions_for(inter.guild.me).send_messages:
            raise GenericError("Não tenho permissão de enviar mensagens no canal atual.")

        return True

    return commands.check(predicate)


def is_requester():

    async def predicate(inter):

        try:
            player: Union[LavalinkPlayer, YTDLPlayer] = inter.bot.music.players[inter.guild.id]
        except KeyError:
            raise NoPlayer()

        if not player.current:
            raise NoSource()

        if player.current.requester == inter.author or not player.restrict_mode:
            return True

        try:
            if await has_perm(inter):
                return True

        except NotDJorStaff:
            pass

        raise NotRequester()

    return commands.check(predicate)


def check_voice():

    def predicate(inter):

        if not inter.author.voice:
            raise NoVoice()

        try:
            if inter.author.voice.channel != inter.guild.me.voice.channel:
                raise DiffVoiceChannel()
        except AttributeError:
            pass

        if not inter.guild.me.voice:

            perms = inter.author.voice.channel.permissions_for(inter.guild.me)

            if not perms.connect or not perms.speak:
                raise MissingVoicePerms(inter.author.voice.channel)

        return True

    return commands.check(predicate)


def has_source():

    def predicate(inter):

        try:
            player = inter.bot.music.players[inter.guild.id]
        except KeyError:
            raise NoPlayer()

        if not player.current:
            raise NoSource()

        return True

    return commands.check(predicate)


def user_cooldown(rate: int, per: int):

    def custom_cooldown(inter: disnake.Interaction):
        #if (await inter.bot.is_owner(inter.author)):
        #   return None  # sem cooldown

        return commands.Cooldown(rate, per)

    return custom_cooldown


#######################################################################


async def has_perm(inter):

    try:
        player: Union[LavalinkPlayer, YTDLPlayer] = inter.bot.music.players[inter.guild.id]
    except KeyError:
        return True

    if inter.author in player.dj:
        return True

    if inter.author.guild_permissions.manage_channels:
        return True

    elif player.nonstop:
        raise GenericError(f"**Erro!** Apenas membros com a permissão de **{perms_translations['manage_channels']}** "
                           "podem usar este comando/botão com o **modo 24/7 ativo**...")

    user_roles = [r.id for r in inter.author.roles]

    guild_data = await inter.bot.db.get_data(inter.guild.id, db_name="guilds")

    if [r for r in guild_data['djroles'] if int(r) in user_roles]:
        return True

    vc = inter.bot.get_channel(player.channel_id)

    if not vc and inter.author.voice:
        player.dj.add(inter.author)

    elif inter.bot.intents.members and not [m for m in vc.members if
                                        not m.bot and (m.guild_permissions.manage_channels or m in player.dj)]:
        player.dj.add(inter.author)
        await inter.channel.send(embed=disnake.Embed(
            description=f"{inter.author.mention} foi adicionado à lista de DJ's por não haver um no canal <#{vc.id}>.",
            color=player.bot.get_color(inter.guild.me)), delete_after=10)
        return True
