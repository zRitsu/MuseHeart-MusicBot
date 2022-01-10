import disnake
from disnake.ext import commands
from .errors import NoVoice, NoPlayer, NoSource, NotRequester, NotDJorStaff, DiffVoiceChannel, GenericError


def has_player():

    def predicate(inter):

        try:
            inter.player
        except AttributeError:
            inter.player = inter.bot.music.players.get(inter.guild.id)

        if not inter.player:
            raise NoPlayer()

        return True

    return commands.check(predicate)


def is_dj():

    async def predicate(inter):

        if not await has_perm(inter):
            raise NotDJorStaff()

        return True

    return commands.check(predicate)


def can_send_message():

    async def predicate(inter):

        if not inter.channel.permissions_for(inter.guild.me).send_messages:
            raise GenericError("Não tenho permissão de enviar mensagens neste canal.")

        return True

    return commands.check(predicate)


def is_requester():
    async def predicate(inter):

        inter.player = inter.bot.music.players.get(inter.guild.id)

        if not inter.player:
            raise NoPlayer()

        if not inter.player.current:
            raise NoSource()

        if inter.player.current.requester == inter.author:
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

        try:
            if inter.author.voice.channel != inter.guild.me.voice.channel:
                raise DiffVoiceChannel()
        except AttributeError:
            pass

        if not inter.author.voice:
            raise NoVoice()

        return True

    return commands.check(predicate)


def has_source():
    def predicate(inter):

        try:
            inter.player
        except:
            inter.player = inter.bot.music.players.get(inter.guild.id)

        if not inter.player:
            raise NoPlayer()

        if not inter.player.current:
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
        player = inter.player
    except AttributeError:
        inter.player = inter.bot.music.players.get(inter.guild.id)
        player = inter.player

    if not player:
        return True

    if inter.author in player.dj:
        return True

    if inter.author.guild_permissions.manage_channels:
        return True

    if inter.guild_data:
        user_roles = [r.id for r in inter.author.roles]

        if [r for r in inter.guild_data['djroles'] if int(r) in user_roles]:
            return True

    vc = inter.bot.get_channel(player.channel_id)

    if not vc and inter.author.voice:
        player.dj.append(inter.author)

    elif inter.bot.intents.members and not [m for m in vc.members if
                                        not m.bot and (m.guild_permissions.manage_channels or m in player.dj)]:
        player.dj.append(inter.author)
        await inter.channel.send(embed=disnake.Embed(
            description=f"{inter.author.mention} foi adicionado à lista de DJ's por não haver um no canal <#{vc.id}>.",
            color=player.bot.get_color(inter.guild.me)), delete_after=10)
        return True
