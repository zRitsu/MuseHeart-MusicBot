from __future__ import annotations

from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Union

import disnake
from disnake.ext import commands

if TYPE_CHECKING:
    from utils.client import BotCore


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
    invite_url = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=8&scope=bot" \
                 f"%20applications.commands "

    return f"`Caso os comandos de barra não apareçam,` [`clique aqui`]({invite_url}) `para me permitir " \
           "criar comandos de barra no servidor.`\n\n" \
           "`Nota: Em alguns casos os comandos de barra podem demorar até uma hora pra aparecer/atualizar em todos " \
           "os servidores. Caso queira usar os comandos de barra imediatamente neste servidor você terá que " \
           f"me expulsar do servidor e em seguida me adicionar novamente através deste` [`link`]({invite_url})..."


async def check_cmd(cmd, inter: disnake.Interaction):

    bucket = cmd._buckets.get_bucket(inter)  # type: ignore
    if bucket:
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(cooldown=bucket, retry_after=retry_after, type=cmd._buckets.type)

    try:
        # inter.user_data = await inter.bot.db.get_data(inter.author.id, db_name="users")
        inter.guild_data = await inter.bot.db.get_data(inter.guild.id, db_name="guilds")
    except AttributeError:
        # inter.user_data = None
        inter.guild_data = None

    for command_check in cmd.checks:
        c = (await command_check(inter)) if iscoroutinefunction(command_check) else command_check(inter)
        if not c:
            raise commands.CheckFailure()


async def send_message(
        inter: Union[disnake.Interaction, disnake.ApplicationCommandInteraction],
        text=None,
        *,
        embed: disnake.Embed = None,
):

    # correção temporária usando variavel kwargs.
    kwargs = {}
    if embed:
        kwargs["embed"] = embed

    if inter.response.is_done():
        await inter.edit_original_message(content=text **kwargs)
    else:
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
            label="Adicionar música."
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
