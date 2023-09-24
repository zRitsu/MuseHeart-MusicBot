# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import re
from inspect import iscoroutinefunction
from io import BytesIO
from typing import TYPE_CHECKING, Union, Optional

import disnake
from aiohttp import ClientSession
from disnake.ext import commands

from utils.db import DBModel
from utils.music.errors import GenericError, ArgumentParsingError

if TYPE_CHECKING:
    from utils.client import BotCore

token_regex = re.compile(r'[a-zA-Z0-9_-]{23,28}\.[a-zA-Z0-9_-]{6,7}\.[a-zA-Z0-9_-]{27,}')

class Test:

    def is_done(self):
        return False

class CommandArgparse(argparse.ArgumentParser):

    def __init__(self, *args, **kwargs):

        kwargs.pop('exit_on_error', None)
        kwargs.pop('allow_abbrev', None)
        kwargs.pop('add_help', None)

        super().__init__(*args, exit_on_error=False, allow_abbrev=False, add_help=False, **kwargs)

    def error(self, message: str):
        raise ArgumentParsingError(message)

class CustomContext(commands.Context):
    bot: BotCore
    def __init__(self, prefix, view, bot: BotCore, message):
        super(CustomContext, self).__init__(prefix=prefix, view=view, bot=bot, message=message)
        self.response = Test()
        self.response.defer = self.defer
        self.user = self.author
        self.guild_id = self.guild.id
        self.channel_id = self.channel.id
        self.store_message = None
        self.application_command = None

    async def defer(self, ephemeral: bool = False):
        await self.trigger_typing()
        return

    async def send(self, *args, **kwargs):

        try:
            kwargs.pop("ephemeral")
        except:
            pass

        return await self.reply(fail_if_not_exists=False, *args, **kwargs)

    async def reply(self, *args, **kwargs):

        try:
            kwargs.pop("ephemeral")
        except:
            pass

        return await super().reply(*args, **kwargs)

class PoolCommand(commands.Command):
    def __init__(self, func, **kwargs):
        super().__init__(func, **kwargs)
        self.pool_return_first = kwargs.pop("return_first", False)
        self.pool_check_player = kwargs.pop("check_player", True)
        self.pool_only_voiced = kwargs.pop("only_voiced", False)

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
    seek_to_start = "musicplayer_seek_to_start"
    readd = "musicplayer_readd_songs"
    loop_mode = "musicplayer_loop_mode"
    queue = "musicplayer_queue"
    nightcore = "musicplayer_nightcore"
    help_button = "musicplayer_help"
    restrict_mode = "musicplayer_restrict_mode"
    miniqueue = "musicplayer_miniqueue"
    song_request_thread = "musicplayer_song_request_thread"
    fav_manageer = "musicplayer_fav_manager"
    integration_manager = "musicplayer_integration_manager"
    autoplay = "musicplayer_autoplay"
    add_favorite = "musicplayer_add_favorite"


class SongRequestPurgeMode:
    on_message = "on_message" # mensagens serão apagadas assim que enviadas (ao iniciar player as mensagens serão limpas também).
    on_player_start = "on_player_start" # as mensagens serão deletadas apenas ao iniciar o player
    on_player_stop = "on_player_stop" # limpa as mensagens apenas ao desligar o player
    no_purge = "no_purge" # as mensagens não serão limpas


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
            await interaction.send(
                f"Apenas o membro {self.ctx.author.mention} pode usar os botões dessa mensagem...",
                ephemeral=True
            )
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


song_request_buttons = [
    disnake.ui.Button(label="Pedir uma música", emoji="🎶", custom_id=PlayerControls.add_song),
    disnake.ui.Button(label="Tocar favorito/integração", emoji="⭐", custom_id=PlayerControls.enqueue_fav)
]


def pool_command(*args, **kwargs)-> PoolCommand:
    return commands.command(*args, **kwargs, cls=PoolCommand)


def sync_message(bot: BotCore):
    app_commands_invite = f"https://discord.com/api/oauth2/authorize?client_id={bot.user.id}&scope=applications.commands"
    bot_invite = disnake.utils.oauth_url(bot.user.id, permissions=disnake.Permissions(bot.config['INVITE_PERMISSIONS']), scopes=('bot', 'applications.commands'), redirect_uri=bot.config['INVITE_REDIRECT_URL'])

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

    if isinstance(inter, CustomContext):
        await cmd.can_run(inter)

    else:
        for command_check in cmd.checks:
            c = (await command_check(inter)) if iscoroutinefunction(command_check) else command_check(inter)
            if not c:
                raise commands.CheckFailure()

    bucket = cmd._buckets.get_bucket(inter)  # type: ignore
    if bucket:
        retry_after = bucket.update_rate_limit()
        if retry_after:
            raise commands.CommandOnCooldown(cooldown=bucket, retry_after=retry_after, type=cmd._buckets.type)

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

        try:

            try:
                channel = inter.music_bot.get_channel(inter.channel_id)
            except AttributeError:
                channel = inter.channel

            if isinstance(channel.parent, disnake.ForumChannel) and (channel.archived or channel.locked) and \
                    channel.guild.me.guild_permissions.manage_threads:
                await channel.edit(archived=False, locked=False)

        except AttributeError:
            pass

        try:
            await inter.send(text, ephemeral=True, **kwargs)
        except disnake.InteractionTimedOut:
            await inter.channel.send(text, **kwargs)


async def send_idle_embed(
        target: Union[disnake.Message, disnake.TextChannel, disnake.Thread, disnake.MessageInteraction],
        text="", *, bot: BotCore, force=False, guild_data: dict = None
):
    try:
        is_forum = isinstance(target.channel.parent, disnake.ForumChannel)
    except AttributeError:
        is_forum = False

    try:
        guild_id = target.guild_id
    except AttributeError:
        guild_id = target.guild.id

    if not guild_data:
        guild_data = await bot.get_data(guild_id, db_name=DBModel.guilds)

    cmd = f"</play:" + str(bot.pool.controller_bot.get_global_command_named("play", cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"

    embed = disnake.Embed(description="**Entre em um canal de voz e peça uma música aqui " +
                                      ("no post" if is_forum else "no canal ou na conversa abaixo") +
                                      f" (ou clique no botão abaixo ou use o comando {cmd} aqui ou em algum outro canal)**\n\n"
                                      "**Você pode usar um nome ou um link de site compatível:**"
                                      " ```ansi\n[31;1mYoutube[0m, [33;1mSoundcloud[0m, [32;1mSpotify[0m, [34;1mTwitch[0m```\n",
                          color=bot.get_color(target.guild.me))

    if text:
        embed.description += f"**ÚLTIMA AÇÃO:** {text.replace('**', '')}\n"

    embed.set_thumbnail(target.guild.me.display_avatar.replace(size=256).url)

    components = []

    opts = [disnake.SelectOption(label=k, value=k, emoji=music_source_emoji_url(v['url']), description=v.get('description')) for k, v in sorted(guild_data["player_controller"]["fav_links"].items(), key=lambda k: k)]

    if opts:
        components.append(
            disnake.ui.Select(
                placeholder="Músicas/Playlists do servidor.",
                options=opts, custom_id="player_guild_pin",
                min_values=0, max_values=1
            )
        )

    components.extend(song_request_buttons)

    if is_forum:
        content = "🎶 Peça sua música aqui."
    else:
        content = None

    if isinstance(target, disnake.MessageInteraction):
        await target.response.edit_message(embed=embed, components=components, content=content)
        message = target.message

    elif isinstance(target, disnake.Message):

        if guild_data["player_controller"]["channel"] != str(target.channel.id) and not force:
            return target

        if target.author == target.guild.me:
            await target.edit(embed=embed, content=content, components=components)
            message = target
        else:
            message = await target.channel.send(embed=embed, components=components, content=content)
    else:

        message = await bot.get_channel(target.id).send(embed=embed, components=components, content=content)

    if isinstance(message.channel, (disnake.Thread, disnake.TextChannel)) and not message.pinned and not is_forum and target.guild.me.guild_permissions.manage_messages:
        await message.pin(reason="Player controller")

    return message


def string_to_file(txt, filename="result.txt"):
    if isinstance(txt, dict):
        txt = json.dumps(txt, indent=4, ensure_ascii=False)
    txt = BytesIO(bytes(str(txt), 'utf-8'))
    return disnake.File(fp=txt, filename=filename or "result.txt")


async def fav_list(inter, query: str):

    try:
        data = inter.global_user_data
    except:
        data = await inter.bot.get_global_data(inter.author.id, db_name=DBModel.users)
        inter.global_user_data = data

    lst = sorted([f"> itg: {integrationname}" for integrationname in data["integration_links"]
               if not query or query.lower() in integrationname.lower()])

    if len(lst) > 20:
        return lst

    lst.extend(sorted([f"> fav: {favname}" for favname in data["fav_links"] if not query or query.lower() in favname.lower()]))

    return lst[:20]


async def pin_list(inter, query: str, *, prefix=""):
    return sorted([f"{prefix}{pinname}" for pinname in
                   (await inter.bot.get_data(inter.guild.id, db_name=DBModel.guilds))["player_controller"]["fav_links"]
                   if not query or query.lower() in pinname.lower()][:20])


def paginator(txt: str):
    pages = commands.Paginator(prefix=None, suffix=None)
    pages.max_size = 1910
    for line in txt.splitlines():
        if len(line) >= pages.max_size - 3:
            l = [(line[i:i + pages.max_size - 3]) for i in range(0, len(line), pages.max_size - 3)]
            for l2 in l:
                pages.add_line(l2)
        else:
            pages.add_line(line)
    pages.close_page()
    return pages.pages


yt_url_regex = re.compile(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+")
sc_url_regex = re.compile(r"^(https?://)?(www\.)?(soundcloud\.com)/.+")
sp_url_regex = re.compile(r"^(https?://)?(www\.)?(open\.spotify\.com|spotify\.com)/.+")
tw_url_regex = re.compile(r"^(https?://)?(www\.)?(twitch\.tv)/([A-Za-z0-9_]{4,25})(/.+)?")

music_source_emoji_data = {
    "youtube": "<:youtube:647253940882374656>",
    "sourndcloud": "<:soundcloud:721530214764773427>",
    "spotify": "<:spotify:715717523626000445>",
    "twitch": "<:Twitch:803656463695478804>",
}

def music_source_emoji(name: str):
    return music_source_emoji_data.get(name, "<:play:734221719774035968>")

def music_source_emoji_url(url: str):

    if yt_url_regex.match(url):
        return music_source_emoji_data["youtube"]

    if sc_url_regex.match(url):
        return music_source_emoji_data["soundcloud"]

    if sp_url_regex.match(url):
        return music_source_emoji_data["spotify"]

    if tw_url_regex.match(url):
        return music_source_emoji_data["twitch"]

    return "<:play:734221719774035968>"

def music_source_emoji_id(id_: str):

    id_ = id_.replace("> itg: ", "").replace("> fav: ", "").split()[0]

    if id_ == "【YT】:":
        return music_source_emoji_data["youtube"]

    if id_ == "【SC】:":
        return music_source_emoji_data["soundcloud"]

    if id_ == "【SP】:":
        return music_source_emoji_data["spotify"]

    return "<:play:734221719774035968>"

async def select_bot_pool(inter, first=False):

    if isinstance(inter, CustomContext):
        if len(inter.bot.pool.bots) < 2:
            return inter, inter.bot

    bots = {}

    for pb in inter.bot.pool.bots:

        if pb.get_guild(inter.guild_id):
            bots[pb.user.id] = pb

    if not bots:

        kwargs = {"redirect_uri": inter.bot.config['INVITE_REDIRECT_URL']} if inter.bot.config['INVITE_REDIRECT_URL'] else {}

        bot_invites = "\n".join(
            f"[`{disnake.utils.escape_markdown(str(b.user.name))}`]({disnake.utils.oauth_url(b.user.id, permissions=disnake.Permissions(b.config['INVITE_PERMISSIONS']), scopes=('bot'), **kwargs)})"
            for b in inter.bot.pool.bots if b.appinfo.bot_public)

        if bot_invites:
            raise GenericError(f"**Será necessário adicionar no servidor pelo menos um dos bots abaixo para usar "
                               f"meus comandos:**\n{bot_invites}")
        else:
            raise GenericError("**Não há bots compatíveis com meus comandos no servidor...**")

    if len(bots) == 1 or first:
        return inter, list(bots.values())[0]
    else:
        opts = [disnake.SelectOption(label=f"{b.user}", value=f"{b.user.id}", emoji="🎶") for b in bots.values()]

        opts.append(disnake.SelectOption(label="Cancelar", value="cancel", emoji="❌"))

        try:
            add_id = f"_{inter.id}"
        except AttributeError:
            add_id = ""

        embed = disnake.Embed(
            color=inter.bot.get_color(),
            description="**Selecione um bot abaixo:**\n"
                        f'Nota: você tem apenas <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=45)).timestamp())}:R> para escolher!'
        )

        msg = await inter.send(
            inter.author.mention, embed=embed, ephemeral=True,
            components=[
                disnake.ui.Select(
                    custom_id=f"select_bot{add_id}",
                    options=opts
                )
            ]
        )

        def check_bot_selection(i: Union[CustomContext, disnake.MessageInteraction]):

            try:
                return i.data.custom_id == f"select_bot_{inter.id}" and i.author == inter.author
            except AttributeError:
                return i.author == inter.author and i.message.id == msg.id

        try:
            inter: disnake.MessageInteraction = await inter.bot.wait_for(
                "dropdown", timeout=45, check=check_bot_selection
            )
        except asyncio.TimeoutError:
            try:
                await msg.edit(conent="Tempo de seleção esgotado!", embed=None, view=None)
            except:
                pass
            return None, None

        try:
            func = inter.response.edit_message
        except AttributeError:
            func = msg.edit

        if inter.data.values[0] == "cancel":
            await func(
                embed=disnake.Embed(
                    description="**Seleção cancelada!**",
                    color=inter.bot.get_color()
                ),
                components=None
            )
            return None, None

        if msg:
            inter.store_message = msg

        try:
            return inter, bots[int(inter.data.values[0])]
        except KeyError:
            raise GenericError("**O bot selecionado foi removido do servidor antes de sua seleção...**")

def queue_track_index(inter: disnake.AppCmdInter, bot: BotCore, query: str, match_count: int = 1,
                      case_sensitive: bool = False):

    player = bot.music.players[inter.guild_id]

    try:
        query, unique_id = query.split(" || ID > ")
    except:
        unique_id = None

    query_split = query.lower().split()

    tracklist = []

    count = int(match_count)

    for counter, track in enumerate(player.queue):

        if unique_id is not None:

            if unique_id == track.unique_id:
                return [(counter, track,)]

            if match_count < 2:
                continue

        if case_sensitive:

            track_split = track.title.lower().split()

            try:
                check = all(w == track_split[i] for i, w in enumerate(query_split))
            except IndexError:
                continue

            if check:
                tracklist.append((counter, track,))
                count -= 1
                if not count:
                    break

        else:
            track_title = track.title.lower().split()

            q_found = 0

            for q in query_split:
                for t in track_title:
                    if q in t:
                        q_found += 1
                        track_title.remove(t)
                        break

            if q_found == len(query_split):

                tracklist.append((counter, track,))
                count -= 1
                if not count:
                    break

    return tracklist

async def update_vc_status(bot, channel: disnake.VoiceChannel, status: str = None):

    x = bot.config.get("X_SUPER_PROPERTIES")

    if not x:
        return

    headers = {
        "Authorization": f"Bot {bot.http.token}",
        "X-Super-Properties": x
    }

    url = f'https://discord.com/api/v9/channels/{channel.id}/voice-status'

    params = {"status": status} if status else {}

    async with ClientSession() as session:
        async with session.put(url, headers=headers, json=params) as resp:
            if resp.status != 204:
                raise Exception(f"{resp.status} - {await resp.text()}")
