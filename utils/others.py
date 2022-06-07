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

        return await super().send(*args, **kwargs)

    async def reply(self, *args, **kwargs):

        try:
            kwargs.pop("ephemeral")
        except:
            pass

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


class PlayerControls:
    add_song = "musicplayer_add_song"
    enqueue_fav = "musicplayer_enqueue_fav"
    play = "musicplayer_play"
    stop = "musicplayer_stop"
    pause_resume = "musicplayer_playpause"
    pause = "musicplayer_pause"
    resume = "musicplayer_resume"
    back = "musicplayer_back"
    skip = "musicplayer_skip"
    volume = "musicplayer_volume"
    shuffle = "musicplayer_shuffle"
    seek = "musicplayer_seek"
    loop_mode = "musicplayer_loop_mode"
    queue = "musicplayer_queue"
    nightcore = "musicplayer_nightcore"
    help_button = "musicplayer_help"


class EmbedPaginator(disnake.ui.View):

    def __init__(self, ctx: Union[CustomContext, disnake.MessageInteraction], embeds: list[disnake.Embed], *,timeout=180):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.embeds = embeds
        self.current = 0
        self.max_page = len(embeds) - 1
        self.message: Optional[disnake.Message] = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:

        if interaction.author != self.ctx.author:
            await interaction.send(f"O apenas o membro {self.ctx.author.mention} pode usar estes botões...")
            return False

        return True

    @disnake.ui.button(emoji='⬅️', style=disnake.ButtonStyle.grey)
    async def back(self, button, interaction: disnake.MessageInteraction):

        if self.current == 0:
            self.current = self.max_page
        else:
            self.current -= 1
        await interaction.response.edit_message(embed=self.embeds[self.current])

    @disnake.ui.button(emoji='➡️', style=disnake.ButtonStyle.grey)
    async def next(self, button, interaction: disnake.MessageInteraction):

        if self.current == self.max_page:
            self.current = 0
        else:
            self.current += 1
        await interaction.response.edit_message(embed=self.embeds[self.current])

    @disnake.ui.button(emoji='⏹️', style=disnake.ButtonStyle.red, label="Fechar")
    async def close(self, button, interaction: disnake.MessageInteraction):

        await interaction.message.delete()
        self.stop()

    async def on_timeout(self):

        try:
            await self.message.delete()
        except:
            pass

        self.stop()



def sync_message(bot: BotCore):
    app_commands_invite = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&scope=applications.commands"
    bot_invite = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&permissions=397287680080&scope=bot%" \
                 f"20applications.commands"

    return f"`Caso os comandos de barra não apareçam,` [`clique aqui`]({app_commands_invite}) `para me permitir " \
           "criar comandos de barra no servidor.`\n\n" \
           "`Nota: Em alguns casos os comandos de barra podem demorar até uma hora pra aparecer/atualizar em todos " \
           "os servidores. Caso queira usar os comandos de barra imediatamente no servidor você terá que " \
           f"me expulsar do servidor e em seguida me adicionar novamente através deste` [`link`]({bot_invite})..."


def chunk_list(lst: list, amount: int):
    return [lst[i:i + amount] for i in range(0, len(lst), amount)]


async def check_cmd(cmd, inter: Union[disnake.Interaction, disnake.ModalInteraction, CustomContext]):

    """try:
        inter.application_command = cmd
        await cmd._max_concurrency.acquire(inter)
    except AttributeError:
        pass"""

    bucket = cmd._buckets.get_bucket(inter)  # type: ignore
    if bucket:
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(cooldown=bucket, retry_after=retry_after, type=cmd._buckets.type)

    if isinstance(inter, CustomContext):
        await cmd.can_run(inter)
        return

    for command_check in cmd.checks:
        c = (await command_check(inter)) if iscoroutinefunction(command_check) else command_check(inter)
        if not c:
            raise commands.CheckFailure()

    """try:
        chkcmd = list(cmd.children.values())[0]
    except (AttributeError, IndexError):
        try:
            chkcmd = inter.bot.get_slash_command(cmd.qualified_name.split()[-2])
        except IndexError:
            chkcmd = None

    if chkcmd:
        await check_cmd(chkcmd, inter)"""



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
            custom_id=PlayerControls.add_song,
            style=disnake.ButtonStyle.grey,
            label="Pedir uma música."
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
