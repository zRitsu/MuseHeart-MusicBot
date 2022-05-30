from __future__ import annotations
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Union, Optional
import disnake
from disnake.ext import commands

if TYPE_CHECKING:
    from utils.client import BotCore


class Test:

    def is_done(self):
        return True

class CustomContext(commands.Context):
    bot: BotCore
    def __init__(self, prefix, view, bot: BotCore, message):
        super(CustomContext, self).__init__(prefix=prefix, view=view, bot=bot, message=message)
        self.response = Test()
        self.response.defer = self.defer
        self.user = self.author
        self.guild_id = self.guild.id
        self.store_message = None

    async def defer(self, ephemeral: bool = False):
        return

    async def send(self, *args, **kwargs):
        try:
            kwargs.pop("ephemeral")
        except:
            pass
        if self.channel == self.message.channel:
            kwargs['mention_author'] = False
            return await super().reply(*args, **kwargs)
        return await super().send(*args, **kwargs)

    async def reply(self, *args, **kwargs):
        try:
            kwargs.pop("ephemeral")
        except:
            pass
        if self.channel != self.message.channel or self.author.bot:
            return await super().send(*args, **kwargs)
        kwargs['mention_author'] = False
        return await super().reply(*args, **kwargs)


class ProgressBar:

    def __init__(
            self,
            position: Union[int, float],
            total: Union[int, float],
            bar_count: int = 10
    ):
        self.start = int(bar_count * (position / total))
        self.end = int(bar_count - self.start) - 1


def sync_message(bot: BotCore):
    app_commands_invite = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&scope=applications.commands"
    bot_invite = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=397287680080&scope=bot%" \
                 f"20applications.commands"

    return f"`Caso os comandos de barra não apareçam,` [`clique aqui`]({app_commands_invite}) `para me permitir " \
           "criar comandos de barra no servidor.`\n\n" \
           "`Nota: Em alguns casos os comandos de barra podem demorar até uma hora pra aparecer/atualizar em todos " \
           "os servidores. Caso queira usar os comandos de barra imediatamente no servidor você terá que " \
           f"me expulsar do servidor e em seguida me adicionar novamente através deste` [`link`]({bot_invite})..."


async def check_cmd(cmd, inter: Union[disnake.Interaction, disnake.ModalInteraction]):

    try:
        await cmd._max_concurrency.acquire(inter)
    except AttributeError:
        pass

    bucket = cmd._buckets.get_bucket(inter)  # type: ignore
    if bucket:
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(cooldown=bucket, retry_after=retry_after, type=cmd._buckets.type)

    for command_check in cmd.checks:
        c = (await command_check(inter)) if iscoroutinefunction(command_check) else command_check(inter)
        if not c:
            raise commands.CheckFailure()


async def send_message(
        inter: Union[disnake.Interaction, disnake.ApplicationCommandInteraction],
        text=None,
        *,
        embed: disnake.Embed = None,
        components: Optional[list] = None,
):

    # correção temporária usando variavel kwargs.
    kwargs = {}

    if embed:
        kwargs["embed"] = embed

    if inter.response.is_done() and isinstance(inter, disnake.AppCmdInter):
        await inter.edit_original_message(content=text, components=components, **kwargs)

    else:

        if components:
            kwargs["components"] = components

        await inter.send(text, ephemeral=True, **kwargs)


async def send_idle_embed(target: Union[disnake.Message, disnake.TextChannel, disnake.Thread], text="", *, bot: BotCore):

    embed = disnake.Embed(description="**Entre em um canal de voz e peça uma música aqui no canal ou na conversa abaixo "
                                      "(ou clique no botão abaixo)**\n\n"
                                      "**FORMATOS SUPORTADOS (nome, link):**"
                                      " ```ini\n[Youtube, Soundcloud, Spotify, Twitch]```\n",
                          color=bot.get_color(target.guild.me))

    if text:
        embed.description += f"**ÚLTIMA AÇÃO:** {text.replace('**', '')}\n"

    try:
        avatar = target.guild.me.avatar.url
    except:
        avatar = target.guild.me.default_avatar.url
    embed.set_thumbnail(avatar)

    components = [
        disnake.ui.Button(
            emoji="🎶",
            custom_id="musicplayer_add_song",
            style=disnake.ButtonStyle.grey,
            label="Pedir música."
        ),
        disnake.ui.Button(
            emoji="⭐",
            custom_id="musicplayer_enqueue_fav",
            style=disnake.ButtonStyle.grey,
            label="Adicionar/Tocar favorito."
        )
    ]

    if isinstance(target, disnake.Message):
        if target.author == target.guild.me:
            await target.edit(embed=embed, content=None, components=components)
            message = target
        else:
            message = await target.channel.send(embed=embed, components=components)
    else:
        message = await target.send(embed=embed, components=components)

    return message
