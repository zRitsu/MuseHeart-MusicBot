# -*- coding: utf-8 -*-
import datetime
import json
import pprint
import re
import traceback
import asyncio
from copy import deepcopy
from typing import Union, Optional
from random import shuffle

import aiofiles
import aiohttp
import disnake
import psutil
from aiohttp import ClientConnectorCertificateError
from disnake.ext import commands

import wavelink

from utils.client import BotCore
from utils.db import DBModel
from utils.music.errors import GenericError, MissingVoicePerms, NoVoice, PoolException, parse_error, EmptyFavIntegration
from utils.music.spotify import process_spotify, spotify_regex_w_user
from utils.music.checks import check_voice, has_player, has_source, is_requester, is_dj, \
    can_send_message_check, check_requester_channel, can_send_message, can_connect, check_deafen, check_pool_bots, \
    check_channel_limit, check_stage_topic, check_queue_loading
from utils.music.models import LavalinkPlayer, LavalinkTrack, LavalinkPlaylist
from utils.music.converters import time_format, fix_characters, string_to_seconds, URL_REG, \
    YOUTUBE_VIDEO_REG, google_search, percentage, music_source_image, perms_translations
from utils.music.interactions import VolumeInteraction, QueueInteraction, SelectInteraction
from utils.others import check_cmd, send_idle_embed, CustomContext, PlayerControls, fav_list, queue_track_index, \
    pool_command, string_to_file, CommandArgparse, music_source_emoji_url, SongRequestPurgeMode, song_request_buttons


class Music(commands.Cog):

    emoji = "🎶"
    name = "Música"
    desc_prefix = f"[{emoji} {name}] | "

    search_sources_opts = [
        disnake.OptionChoice("Youtube", "ytsearch"),
        disnake.OptionChoice("Youtube Music", "ytmsearch"),
        disnake.OptionChoice("Soundcloud", "scsearch"),
    ]

    playlist_opts = [
        disnake.OptionChoice("Misturar Playlist", "shuffle"),
        disnake.OptionChoice("Inverter Playlist", "reversed"),
    ]

    sources = {
        "yt": "ytsearch",
        "y": "ytsearch",
        "ytb": "ytsearch",
        "youtube": "ytsearch",
        "ytm": "ytmsearch",
        "ytmsc": "ytmsearch",
        "ytmusic": "ytmsearch",
        "youtubemusic": "ytmsearch",
        "sc": "scsearch",
        "scd": "scsearch",
        "soundcloud": "scsearch",
    }

    audio_formats = ("audio/mpeg", "audio/ogg", "audio/mp4", "audio/aac")

    def __init__(self, bot: BotCore):

        self.bot = bot

        self.extra_hints = bot.config["EXTRA_HINTS"].split("||")

        self.song_request_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

        self.player_interaction_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

        self.song_request_cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=300,
                                                                            type=commands.BucketType.member)

        self.music_settings_cooldown = commands.CooldownMapping.from_cooldown(rate=3, per=15,
                                                                              type=commands.BucketType.guild)

        if self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"]:
            self.error_report_queue = asyncio.Queue()
            self.error_report_task = bot.loop.create_task(self.error_report_loop())
        else:
            self.error_report_queue = None

    async def update_cache(self):

        async with aiofiles.open("./playlist_cache.json", "w") as f:
            await f.write(json.dumps(self.bot.pool.playlist_cache))

    @commands.is_owner()
    @commands.command(hidden=True, aliases=["ac"])
    async def addcache(self, ctx: CustomContext, url: str):

        url = url.strip("<>")

        async with ctx.typing():
            tracks, node = await self.get_tracks(url, ctx.author, use_cache=False)

        tracks_info = []

        try:
            tracks = tracks.tracks
        except AttributeError:
            pass

        for t in tracks:
            tinfo = {"track": t.id, "info": t.info}
            tinfo["info"]["extra"]["playlist"] = {"name": t.playlist_name, "url": t.playlist_url}
            tracks_info.append(tinfo)

        self.bot.pool.playlist_cache[url] = tracks_info

        await self.update_cache()

        await ctx.send("As músicas do link foram adicionadas com sucesso em cache.", delete_after=30)

    @commands.is_owner()
    @commands.cooldown(1, 300, commands.BucketType.default)
    @commands.command(hidden=True, aliases=["uc"])
    async def updatecache(self, ctx: CustomContext, *args):

        if "-fav" in args:
            try:
                data = ctx.global_user_data
            except AttributeError:
                data = await self.bot.get_global_data(ctx.author.id, db_name=DBModel.users)
                ctx.global_user_data = data

            self.bot.pool.playlist_cache.update({url: [] for url in data["fav_links"].values()})

        try:
            if not self.bot.pool.playlist_cache:
                raise GenericError("**Seu cache de playlist está vazio...**")
        except KeyError:
            raise GenericError(f"**Você ainda não usou o comando: {ctx.prefix}{self.addcache.name}**")

        msg = None

        counter = 0

        amount = len(self.bot.pool.playlist_cache)

        txt = ""

        for url in list(self.bot.pool.playlist_cache):

            try:
                async with ctx.typing():
                    tracks, node = await self.get_tracks(url, ctx.author, use_cache=False)
            except:
                traceback.print_exc()
                tracks = None
                try:
                    del self.bot.pool.playlist_cache[url]
                except:
                    pass

            if not tracks:
                txt += f"[`❌ Falha`]({url})\n"

            else:

                tracks_info = []

                try:
                    tracks = tracks.tracks
                except AttributeError:
                    pass

                for t in tracks:
                    tinfo = {"track": t.id, "info": t.info}
                    tinfo["info"]["extra"]["playlist"] = {"name": t.playlist_name, "url": t.playlist_url}
                    tracks_info.append(tinfo)

                self.bot.pool.playlist_cache[url] = tracks_info

                txt += f"[`{tracks_info[0]['info']['extra']['playlist']['name']}`]({url})\n"

            counter += 1

            embed = disnake.Embed(
                description=txt, color=self.bot.get_color(ctx.guild.me),
                title=f"Playlist verificadas: {counter}/{amount}"
            )

            if not msg:
                msg = await ctx.send(embed=embed)
            else:
                await msg.edit(embed=embed)

        await self.update_cache()

    @commands.is_owner()
    @commands.command(hidden=True, aliases=["rc"])
    async def removecache(self, ctx: CustomContext, url: str):

        try:
            del self.bot.pool.playlist_cache[url]
        except KeyError:
            raise GenericError("**Não há itens salvo em cache com a url informada...**")

        await self.update_cache()

        await ctx.send("As músicas do link foram removidas com sucesso do cache.", delete_after=30)

    @commands.is_owner()
    @commands.command(hidden=True, aliases=["cc"])
    async def clearcache(self, ctx: CustomContext):

        try:
            self.bot.pool.playlist_cache.clear()
        except KeyError:
            raise GenericError("**Você não possui links de playlists salva em cache...**")

        await self.update_cache()

        await ctx.send("O cache de playlist foi limpo com sucesso.", delete_after=30)

    @commands.is_owner()
    @commands.command(hidden=True, aliases=["ec"])
    async def exportcache(self, ctx: CustomContext):

        await ctx.send(file=disnake.File("playlist_cache.json"))

    @commands.is_owner()
    @commands.command(hidden=True, aliases=["ic"])
    async def importcache(self, ctx: CustomContext, url: str):

        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    self.bot.pool.playlist_cache.update(json.loads((await r.read()).decode('utf-8')))

        await self.update_cache()

        await ctx.send("O arquivo de cache foi importado com sucesso!", delete_after=30)

    stage_cd = commands.CooldownMapping.from_cooldown(2, 45, commands.BucketType.guild)
    stage_mc = commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @has_source()
    @commands.has_guild_permissions(manage_guild=True)
    @pool_command(
        only_voiced=True, name="stageannounce", aliases=["stagevc", "togglestageannounce"],
        description="Ativar o sistema de anuncio automático do palco com o nome da música.",
        cooldown=stage_cd, max_concurrency=stage_mc, extras={"exclusive_cooldown": True},
        usage="{prefix}{cmd} <placeholders>\nEx: {track.author} - {track.title}"
    )
    async def stageannounce_legacy(self, ctx: CustomContext, *, template: str = None):

        await self.stage_announce.callback(self=self, inter=ctx, template=template)

    @has_source()
    @commands.slash_command(
        description=f"{desc_prefix}Ativar/editar o sistema de anuncio automático do palco com o nome da música.",
        extras={"only_voiced": True, "exclusive_cooldown": True},
        default_member_permissions=disnake.Permissions(manage_guild=True), cooldown=stage_cd, max_concurrency=stage_mc
    )
    async def stage_announce(
            self,
            inter: disnake.AppCmdInter,
            template: str = commands.Param(
                name=disnake.Localized("template", data={disnake.Locale.pt_BR: "modelo"}),
                description=f"{desc_prefix}Ativar o sistema de anuncio automático do palco com o nome da música."
            )
    ):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = inter.guild

        if not isinstance(guild.me.voice.channel, disnake.StageChannel):
            raise GenericError("**Você deve estar em um canal de palco para ativar/desativar esse sistema.**")

        if not guild.me.guild_permissions.manage_guild:
            raise GenericError(f"{bot.user.mention} não possui permissão de: **{perms_translations['manage_guild']}.**")

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not template:
            template = player.stage_title_template

        elif not any(p in template for p in (
                '{track.title}', '{track.author}', '{track.duration}', '{track.source}', '{track.playlist}',
                '{requester.name}', '{requester.tag}', '{requester.id}'
        )):
            raise GenericError(
                "**Você deve usar pelo menos um placeholder válido na mensagem.**\n\n"
                "**PLACEHOLDERS:** ```ansi\n"
                "[34;1m{track.title}[0m -> Nome da música\n"
                "[34;1m{track.author}[0m -> Nome do Artista/Uploader/Author da música.\n"
                "[34;1m{track.duration}[0m -> Duração da música.\n"
                "[34;1m{track.source}[0m -> Origem/Fonte da música (Youtube/Spotify/Soundcloud etc)\n"
                "[34;1m{track.playlist}[0m -> Nome da playlist de origem da música (caso tenha)\n"
                "[34;1m{requester.name}[0m -> Nome/Nick do membro que pediu a música\n"
                "[34;1m{requester.tag}[0m -> Tag/Discriminator do membro que pediu a música\n"
                "[34;1m{requester.id}[0m -> ID do membro que pediu a música\n```"
            )

        if player.stage_title_event and player.stage_title_template == template:

            raise GenericError("**O anúncio automático do palco já está ativado (e não houve alterações no "
                               "template do título).\n"
                               "Caso queira desativar você pode parar o player (todos os membros do palco serão "
                               "desconectados automaticamente nesse processo).**")

        player.stage_title_event = True
        player.stage_title_template = template
        player.start_time = disnake.utils.utcnow()

        txt = [f"ativou/Alterou o sistema de anúncio automático do palco.",
               f"📢 **⠂{inter.author.mention} ativou/alterou o sistema de anúncio automático do palco "
               f"{guild.me.voice.channel.mention}.**\n\n"
               f"`Nota: Caso o player seja desligado, todos os membros do palco serão desconectados automaticamente.`\n\n"
               f"**Modelo usado:** `{disnake.utils.escape_markdown(template)}`"]

        await self.interaction_message(inter, txt, emoji="📢", force=True)

    @stage_announce.autocomplete("template")
    async def stage_announce_autocomplete(self, inter: disnake.Interaction, query: str):

        return [
            "Tocando: {track.title} | {track.author}",
            "{track.title} | Pedido por: {requester.name}#{requester.tag}",
            "Rádio 24/7 | {track.title}",
            "{track.title} | Playlist: {track.playlist}",
        ]

    play_cd = commands.CooldownMapping.from_cooldown(3, 12, commands.BucketType.member)
    play_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @check_voice()
    @can_send_message_check()
    @commands.message_command(name="add to queue", extras={"check_player": False},
                              cooldown=play_cd, max_concurrency=play_mc)
    async def message_play(self, inter: disnake.MessageCommandInteraction):

        if not inter.target.content:
            emb = disnake.Embed(description=f"Não há texto na [mensagem]({inter.target.jump_url}) selecionada...",
                                color=disnake.Colour.red())
            await inter.send(embed=emb, ephemeral=True)
            return

        await self.play.callback(
            self=self,
            inter=inter,
            query=inter.target.content,
            position=0,
            options="",
            manual_selection=False,
            source="ytsearch",
            repeat_amount=0,
            force_play="no",
        )

    @check_voice()
    @can_send_message_check()
    @commands.slash_command(name="search", extras={"check_player": False}, cooldown=play_cd, max_concurrency=play_mc,
                            description=f"{desc_prefix}Buscar música e escolher uma entre os resultados para tocar.")
    async def search(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="busca", desc="Nome ou link da música."),
            *,
            position: int = commands.Param(name="posição", description=f"{desc_prefix}Colocar a música em uma posição específica",
                                           default=0),
            force_play: str = commands.Param(
                name="tocar_agora",
                description="Tocar a música imediatamente (ao invés de adicionar na fila).",
                default="no",
                choices=[
                    disnake.OptionChoice(disnake.Localized("Yes", data={disnake.Locale.pt_BR: "Sim"}), "yes"),
                    disnake.OptionChoice(disnake.Localized("No", data={disnake.Locale.pt_BR: "Não"}), "no")
                ]
            ),
            options: str = commands.Param(name="opções", description="Opções para processar playlist",
                                          choices=playlist_opts, default=False),
            source: str = commands.Param(name="fonte",
                                         description="Selecionar site para busca de músicas (não links)",
                                         choices=search_sources_opts,
                                         default="ytsearch"),
            repeat_amount: int = commands.Param(name="repetições", description="definir quantidade de repetições.",
                                                default=0),
            server: str = commands.Param(name="server", desc="Usar um servidor de música específico na busca.",
                                         default=None)
    ):

        await self.play.callback(
            self=self,
            inter=inter,
            query=query,
            position=position,
            force_play=force_play,
            options=options,
            manual_selection=True,
            source=source,
            repeat_amount=repeat_amount,
            server=server
        )

    @search.autocomplete("busca")
    async def search_autocomplete(self, inter: disnake.Interaction, current: str):

        if not current:
            return []

        if URL_REG.match(current):
            return [current] if len(current) < 100 else []

        try:
            await check_pool_bots(inter, only_voiced=True)
            bot = inter.music_bot
        except GenericError:
            return [current[:99]]
        except:
            bot = inter.bot

        try:
            if not inter.author.voice:
                return []
        except AttributeError:
            return [current[:99]]

        return await google_search(bot, current)

    @is_dj()
    @has_player()
    @can_send_message_check()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.slash_command(
        extras={"only_voiced": True},
        description=f"{desc_prefix}Me conectar em um canal de voz (ou me mover para um)."
    )
    async def connect(
            self,
            inter: disnake.AppCmdInter,
            channel: Union[disnake.VoiceChannel, disnake.StageChannel] = commands.Param(
                name="canal",
                description="Canal para me conectar"
            )
    ):
        try:
            channel = inter.music_bot.get_channel(channel.id)
        except AttributeError:
            pass

        await self.do_connect(inter, channel)

    async def do_connect(
            self,
            ctx: Union[disnake.AppCmdInter, commands.Context, disnake.Message],
            channel: Union[disnake.VoiceChannel, disnake.StageChannel] = None,
            check_other_bots_in_vc: bool = False,
            bot: BotCore = None,
            me: disnake.Member = None,
            check_pool: bool = True,
    ):

        if not channel:
            try:
                channel = ctx.music_bot.get_channel(ctx.author.voice.channel.id) or ctx.author.voice.channel
            except AttributeError:
                channel = ctx.author.voice.channel

        if not bot:
            try:
                bot = ctx.music_bot
            except AttributeError:
                bot = self.bot

        if not me:
            try:
                me = ctx.music_guild.me
            except AttributeError:
                me = ctx.guild.me

        try:
            guild_id = ctx.guild_id
        except AttributeError:
            guild_id = ctx.guild.id

        try:
            text_channel = ctx.music_bot.get_channel(ctx.channel.id)
        except AttributeError:
            text_channel = ctx.channel

        try:
            player = bot.music.players[guild_id]
        except KeyError:
            print(f"Player debug test 20: {bot.user} | {self.bot.user}")
            raise GenericError(
                f"**O player do bot {bot.user.mention} foi finalizado antes de conectar no canal de voz "
                f"(ou o player não foi inicializado)...\nPor via das dúvidas tente novamente.**"
            )

        can_connect(channel, me.guild, check_other_bots_in_vc=check_other_bots_in_vc, bot=bot)

        deafen_check = True

        if isinstance(ctx, disnake.AppCmdInter) and ctx.application_command.name == self.connect.name:

            perms = channel.permissions_for(me)

            if not perms.connect or not perms.speak:
                raise MissingVoicePerms(channel)

            await player.connect(channel.id, self_deaf=True)

            if channel != me.voice and me.voice.channel:
                txt = [
                    f"me moveu para o canal <#{channel.id}>",
                    f"**Movido com sucesso para o canal** <#{channel.id}>"
                ]

                deafen_check = False


            else:
                txt = [
                    f"me conectou no canal <#{channel.id}>",
                    f"**Conectei no canal** <#{channel.id}>"
                ]

            await self.interaction_message(ctx, txt, emoji="🔈", rpc_update=True)

        else:
            await player.connect(channel.id, self_deaf=True)

        try:
            player.members_timeout_task.cancel()
        except:
            pass

        if deafen_check and bot.config["GUILD_DEAFEN_WARN"]:

            retries = 0

            while retries < 5:

                if me.voice:
                    break

                await asyncio.sleep(1)
                retries += 0

            if not await check_deafen(me):
                await text_channel.send(
                    embed=disnake.Embed(
                        title="Aviso:",
                        description="Para manter sua privacidade e me ajudar a economizar "
                                    "recursos, recomendo desativar meu áudio do canal clicando "
                                    "com botão direito sobre mim e em seguida marcar: desativar "
                                    "áudio no servidor.",
                        color=self.bot.get_color(me),
                    ).set_image(
                        url="https://cdn.discordapp.com/attachments/554468640942981147/1012533546386210956/unknown.png"
                    ), delete_after=20
                )

        if isinstance(channel, disnake.StageChannel):

            while not me.voice:
                await asyncio.sleep(1)

            stage_perms = channel.permissions_for(me)

            if stage_perms.mute_members:
                await me.edit(suppress=False)
            else:
                embed = disnake.Embed(color=self.bot.get_color(me))

                embed.description = f"**Preciso que algum staff me convide para falar no palco: " \
                                    f"[{channel.name}]({channel.jump_url}).**"

                embed.set_footer(
                    text="💡 Dica: para me permitir falar no palco automaticamente será necessário me conceder "
                         "permissão de silenciar membros (no servidor ou apenas no canal de palco escolhido).")

                await text_channel.send(ctx.author.mention, embed=embed, delete_after=45)

    @can_send_message_check()
    @check_voice()
    @commands.bot_has_guild_permissions(send_messages=True)
    @commands.max_concurrency(1, commands.BucketType.member)
    @pool_command(name="addposition", description="Adicionar música em uma posição especifica da fila.",
                  aliases=["adp", "addpos"], check_player=False, cooldown=play_cd, max_concurrency=play_mc,
                  usage="{prefix}{cmd} [posição(Nº)] [nome|link]\nEx: {prefix}{cmd} 2 sekai - burn me down")
    async def addpos_legacy(self, ctx: CustomContext, position: int, *, query: str):

        if position < 1:
            raise GenericError("**Número da posição da fila tem que ser 1 ou superior.**")

        await self.play.callback(self=self, inter=ctx, query=query, position=position, options=False,
                                 force_play="no", manual_selection=False,
                                 source="ytsearch", repeat_amount=0, server=None)

    play_flags = CommandArgparse()
    play_flags.add_argument('query', nargs='*', help="nome ou link da música")
    play_flags.add_argument('-position', '-pos', '-p', type=int, default=0, help='Colocar a música em uma posição específica.\nEx: -p 10')
    play_flags.add_argument('-next', '-proximo', action='store_true', help='Adicionar a música/playlist no topo da fila (equivalente ao: -pos 1)')
    play_flags.add_argument('-reverse', '-r', action='store_true', help='Inverter a ordem das músicas adicionadas (efetivo apenas ao adicionar playlist).')
    play_flags.add_argument('-shuffle', '-sl', action='store_true', help='Misturar as músicas adicionadas (efetivo apenas ao adicionar playlist).')
    play_flags.add_argument('-select', '-s', action='store_true', help='Escolher a música entre os resultados encontrados.')
    play_flags.add_argument('-source', '-scr', type=str, default="ytsearch", help='Fazer a busca da música usando uma fonte específica [youtube/soundcloud etc]')
    play_flags.add_argument('-force', '-now', '-n', '-f', action='store_true', help='Tocar a música adicionada imediatamente (efetivo apenas se houver uma música tocando atualmente.)')
    play_flags.add_argument('-loop', '-lp', type=int, default=0, help="Definir a quantidade de repetições da música escolhida.\nEx: -loop 5")
    play_flags.add_argument('-server', '-sv', type=str, default=None, help='Usar um servidor de música específico.')

    @can_send_message_check()
    @check_voice()
    @commands.bot_has_guild_permissions(send_messages=True)
    @commands.max_concurrency(1, commands.BucketType.member)
    @pool_command(name="play", description="Tocar música em um canal de voz.", aliases=["p"], check_player=False,
                  cooldown=play_cd, max_concurrency=play_mc, extras={"flags": play_flags},
                  usage="{prefix}{cmd} [nome|link]\nEx: {prefix}{cmd} sekai - burn me down")
    async def play_legacy(self, ctx: CustomContext, *, flags: str = ""):

        args, unknown = ctx.command.extras['flags'].parse_known_args(flags.split())

        await self.play.callback(
            self = self,
            inter = ctx,
            query = " ".join(args.query + unknown),
            position= 1 if args.next else args.position if args.position > 0 else 0,
            options = "shuffle" if args.shuffle else "reversed" if args.reverse else None,
            force_play = "yes" if args.force else "no",
            manual_selection = args.select,
            source = self.sources.get(args.source, "ytsearch"),
            repeat_amount = args.loop,
            server = args.server
        )

    @can_send_message_check()
    @check_voice()
    @commands.bot_has_guild_permissions(send_messages=True)
    @pool_command(name="search", description="Pesquisar por músicas e escolher uma entre os resultados para tocar.",
                  aliases=["sc"], check_player=False, cooldown=play_cd, max_concurrency=play_mc,
                  usage="{prefix}{cmd} [nome]\nEx: {prefix}{cmd} sekai - burn me down")
    async def search_legacy(self, ctx: CustomContext, *, query):

        await self.play.callback(self=self, inter=ctx, query=query, position=0, options=False, force_play="no",
                                 manual_selection=True, source="ytsearch", repeat_amount=0, server=None)

    @can_send_message_check()
    @check_voice()
    @commands.slash_command(
        name="play_music_file",
        description=f"{desc_prefix}Tocar arquivo de música em um canal de voz.",
        extras={"check_player": False}, cooldown=play_cd, max_concurrency=play_mc
    )
    async def play_file(
            self,
            inter: Union[disnake.AppCmdInter, CustomContext],
            file: disnake.Attachment = commands.Param(
                name="arquivo", description="arquivo de audio para tocar ou adicionar na fila"
            ),
            position: int = commands.Param(name="posição", description="Colocar a música em uma posição específica",
                                           default=0),
            force_play: str = commands.Param(
                name="tocar_agora",
                description="Tocar a música imediatamente (ao invés de adicionar na fila).",
                default="no",
                choices=[
                    disnake.OptionChoice(disnake.Localized("Yes", data={disnake.Locale.pt_BR: "Sim"}), "yes"),
                    disnake.OptionChoice(disnake.Localized("No", data={disnake.Locale.pt_BR: "Não"}), "no")
                ]
            ),
            repeat_amount: int = commands.Param(name="repetições", description="definir quantidade de repetições.",
                                                default=0),
            server: str = commands.Param(name="server", desc="Usar um servidor de música específico na busca.",
                                         default=None),
    ):

        class DummyMessage:
            attachments = [file]

        try:
            thread = inter.message.thread
        except:
            thread = None
        inter.message = DummyMessage()
        inter.message.thread = thread

        await self.play.callback(self=self, inter=inter, query="", position=position, options=False, force_play=force_play,
                                 manual_selection=False, source="ytsearch", repeat_amount=repeat_amount, server=server)

    @can_send_message_check()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Tocar música em um canal de voz.",
        extras={"check_player": False}, cooldown=play_cd, max_concurrency=play_mc
    )
    async def play(
            self,
            inter: Union[disnake.AppCmdInter, CustomContext],
            query: str = commands.Param(name="busca", desc="Nome ou link da música."), *,
            position: int = commands.Param(name="posição", description="Colocar a música em uma posição específica",
                                           default=0),
            force_play: str = commands.Param(
                name="tocar_agora",
                description="Tocar a música imediatamente (ao invés de adicionar na fila).",
                default="no",
                choices=[
                    disnake.OptionChoice(disnake.Localized("Yes", data={disnake.Locale.pt_BR: "Sim"}), "yes"),
                    disnake.OptionChoice(disnake.Localized("No", data={disnake.Locale.pt_BR: "Não"}), "no")
                ]
            ),
            manual_selection: bool = commands.Param(name="selecionar_manualmente",
                                                    description="Escolher uma música manualmente entre os resultados encontrados",
                                                    default=False),
            options: str = commands.Param(name="opções", description="Opções para processar playlist",
                                          choices=playlist_opts, default=False),
            source: str = commands.Param(name="fonte",
                                         description="Selecionar site para busca de músicas (não links)",
                                         choices=search_sources_opts,
                                         default="ytsearch"),
            repeat_amount: int = commands.Param(name="repetições", description="definir quantidade de repetições.",
                                                default=0),
            server: str = commands.Param(name="server", desc="Usar um servidor de música específico na busca.",
                                         default=None),
    ):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
            channel = bot.get_channel(inter.channel.id)
        except AttributeError:
            bot = inter.bot
            guild = inter.guild
            channel = inter.channel

        can_send_message(channel, bot.user)

        if not guild.voice_client and not check_channel_limit(guild.me, inter.author.voice.channel):
            raise GenericError(f"**O canal {inter.author.voice.channel.mention} está lotado!**")

        msg = None

        ephemeral = None

        warn_message = None

        try:
            if isinstance(inter.message, disnake.Message):
                message_inter = inter.message
            else:
                message_inter = None
        except AttributeError:
            message_inter = None

        try:
            modal_message_id = int(inter.data.custom_id[15:])
        except:
            modal_message_id = None

        attachment: Optional[disnake.Attachment] = None

        try:
            voice_channel = bot.get_channel(inter.author.voice.channel.id)
        except AttributeError:
            raise NoVoice()

        try:
            player = bot.music.players[guild.id]

            if not server:
                node = player.node
            else:
                node = bot.music.get_node(server) or player.node

            guild_data = {}

        except KeyError:

            node = bot.music.get_node(server)

            if not node:
                node = await self.get_best_node(bot)

            guild_data = None

            if inter.bot == bot:
                try:
                    guild_data = inter.guild_data
                except AttributeError:
                    guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)
                    try:
                        inter.guild_data = guild_data
                    except AttributeError:
                        pass

            if not guild_data:
                guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

            if not guild.me.voice:
                can_connect(voice_channel, guild, guild_data["check_other_bots_in_vc"], bot=bot)

            static_player = guild_data['player_controller']

            if not inter.response.is_done():
                ephemeral = await self.is_request_channel(inter, data=guild_data, ignore_thread=True)
                await inter.response.defer(ephemeral=ephemeral)

            if static_player['channel']:
                channel, warn_message = await self.check_channel(guild_data, inter, channel, guild, bot)

        if ephemeral is None:
            ephemeral = await self.is_request_channel(inter, data=guild_data, ignore_thread=True)

        is_pin = None

        if not query:

            if self.bot.config["ENABLE_DISCORD_URLS_PLAYBACK"]:

                try:
                    attachment = inter.message.attachments[0]

                    if attachment.size > 18000000:
                        raise GenericError("**O arquivo que você enviou deve ter o tamanho igual ou inferior a 18mb.**")

                    if attachment.content_type not in self.audio_formats:
                        raise GenericError("**O arquivo que você enviou não é um arquivo de música válido...**")

                    query = attachment.url

                except IndexError:
                    pass

        if not query:

            try:
                user_data = inter.global_user_data
            except:
                user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
                inter.global_user_data = user_data

            db_favs = {}

            for k, v in user_data["integration_links"].items():
                db_favs[f"> itg: {k}"] = v

            for k, v in user_data["fav_links"].items():
                db_favs[f"> fav: {k}"] = v

            if not db_favs:
                raise EmptyFavIntegration()

            if len(db_favs) == 1:
                query = list(db_favs)[0]

            else:
                embed = disnake.Embed(
                    color=self.bot.get_color(guild.me),
                    description="**Selecione um favorito ou integração abaixo:**\n"
                                f'Nota: você tem apenas <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=45)).timestamp())}:R> para escolher!'
                )

                try:
                    if bot.user.id != self.bot.user.id:
                        embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
                except AttributeError:
                    pass

                kwargs = {
                    "content": "",
                    "embed": embed
                }

                try:
                    if inter.message.author.bot:
                        kwargs["content"] = inter.author.mention
                except AttributeError:
                    pass

                view = SelectInteraction(
                    user=inter.author,  timeout=45,
                    opts=[disnake.SelectOption(label=k, value=k, emoji=music_source_emoji_url(v)) for k, v in db_favs.items()]
                )

                if isinstance(inter, disnake.MessageInteraction) and not inter.response.is_done():
                    await inter.response.defer(ephemeral=ephemeral)

                try:
                    msg = await inter.followup.send(ephemeral=ephemeral, view=view, wait=True, **kwargs)
                except (disnake.InteractionTimedOut, AttributeError):
                    msg = await inter.channel.send(view=view, **kwargs)

                await view.wait()

                select_interaction = view.inter

                if not select_interaction or view.selected is False:

                    text = "### Tempo de seleção esgotado!" if view.selected is not False else "### Cancelado pelo usuário."

                    try:
                        await msg.edit(embed=disnake.Embed(description=text, color=self.bot.get_color(guild.me)), components=song_request_buttons)
                    except AttributeError:
                        traceback.print_exc()
                        pass
                    return

                if select_interaction.data.values[0] == "cancel":
                    await msg.edit(
                        embed=disnake.Embed(
                            description="**Seleção cancelada!**",
                            color=self.bot.get_color(guild.me)
                        ),
                        components=None
                    )
                    return

                try:
                    inter.store_message = msg
                except AttributeError:
                    pass

                inter.token = select_interaction.token
                inter.id = select_interaction.id
                inter.response = select_interaction.response
                query = select_interaction.data.values[0]

        if query.startswith("> pin: "):
            is_pin = True
            query = query[7:]

        if query.startswith(("> fav: ", "> itg: ")):
            try:
                user_data = inter.global_user_data
            except AttributeError:
                user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
                inter.global_user_data = user_data

            if query.startswith("> fav:"):
                query = user_data["fav_links"][query[7:]]

            else:

                query = user_data["integration_links"][query[7:]]

                if (matches := spotify_regex_w_user.match(query)):

                    if not self.bot.spotify:
                        raise GenericError("**O suporte ao spotify não está disponível no momento...**")

                    url_type, user_id = matches.groups()

                    if url_type != "user":
                        raise GenericError("**Link não suportado usando este método...**")

                    try:
                        await inter.response.defer(ephemeral=True)
                    except:
                        pass

                    result = await self.bot.spotify.get_user_playlists(user_id)

                    info = {"entries": [{"title": t.name, "url": t.external_urls["spotify"]} for t in result]}

                elif not self.bot.config["USE_YTDL"]:
                    raise GenericError("**Não há suporte a esse tipo de requisição no momento...**")

                else:

                    loop = self.bot.loop or asyncio.get_event_loop()

                    try:
                        await inter.response.defer(ephemeral=True)
                    except:
                        pass

                    info = await loop.run_in_executor(None, lambda: self.bot.pool.ytdl.extract_info(query, download=False))

                    try:
                        if not info["entries"]:
                            raise GenericError(f"**Conteúdo indisponível (ou privado):**\n{query}")
                    except KeyError:
                        raise GenericError("**Ocorreu um erro ao tentar obter resultados para a opção selecionada...**")

                if len(info["entries"]) == 1:
                    query = info["entries"][0]['url']

                else:

                    emoji = music_source_emoji_url(query)

                    view = SelectInteraction(
                        user=inter.author,
                        opts=[
                            disnake.SelectOption(label=e['title'][:90], value=f"entrie_select_{c}",
                                                 emoji=emoji) for c, e in enumerate(info['entries'])
                        ], timeout=30)

                    embed = disnake.Embed(
                        description="**Escolha uma playlist abaixo:**\n"
                                    f'Selecione uma opção em até <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=30)).timestamp())}:R> para prosseguir.',
                        color=self.bot.get_color(guild.me)
                    )

                    kwargs = {}

                    try:
                        func = msg.edit
                    except AttributeError:
                        try:
                            func = inter.edit_original_message
                        except AttributeError:
                            kwargs["ephemeral"] = True
                            try:
                                func = inter.followup.send
                            except AttributeError:
                                func = inter.send

                    msg = await func(embed=embed, view=view, **kwargs)

                    await view.wait()

                    if not view.inter or view.selected is False:

                        try:
                            func = msg.edit
                        except:
                            func = view.inter.response.edit_message

                        await func(embed=disnake.Embed(color=self.bot.get_color(guild.me),
                            description="**Tempo esgotado!**" if not view.selected is False else "### Cancelado pelo usuário."),
                            components=song_request_buttons
                        )
                        return

                    query = info["entries"][int(view.selected[14:])]["url"]

                    if not isinstance(inter, disnake.ModalInteraction):
                        inter.token = view.inter.token
                        inter.id = view.inter.id
                        inter.response = view.inter.response
                    else:
                        inter = view.inter

        else:

            query = query.strip("<>")

            urls = URL_REG.findall(query)

            if not urls:

                query = f"{source}:{query}"

            else:

                if not self.bot.config["ENABLE_DISCORD_URLS_PLAYBACK"] and "cdn.discordapp.com/attachments/" in query:
                    raise GenericError("**O suporte a links do discord está desativado.**")

                for p in ("&ab_channel=", "&start_radio="):
                    if p in query:
                        try:
                            query = f'https://www.youtube.com/watch?v={re.search(r"v=([a-zA-Z0-9_-]+)", query).group(1)}'
                        except:
                            pass
                        break

                if "&list=" in query and (link_re := YOUTUBE_VIDEO_REG.match(query)):

                    view = SelectInteraction(
                        user=inter.author,
                        opts=[
                            disnake.SelectOption(label="Música", emoji="🎵",
                                                 description="Carregar apenas a música do link.", value="music"),
                            disnake.SelectOption(label="Playlist", emoji="🎶",
                                                 description="Carregar playlist com a música atual.", value="playlist"),
                        ], timeout=30)

                    embed = disnake.Embed(
                        description='**O link contém vídeo com playlist.**\n'
                                    f'Selecione uma opção em até <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=30)).timestamp())}:R> para prosseguir.',
                        color=self.bot.get_color(guild.me)
                    )

                    try:
                        if bot.user.id != self.bot.user.id:
                            embed.set_footer(text=f"Via: {bot.user.display_name}",
                                             icon_url=bot.user.display_avatar.url)
                    except AttributeError:
                        pass

                    msg = await inter.send(embed=embed, view=view, ephemeral=ephemeral)

                    await view.wait()

                    if not view.inter or view.selected is False:

                        try:
                            func = inter.edit_original_message
                        except AttributeError:
                            func = msg.edit

                        mention = ""

                        try:
                            if inter.message.author.bot:
                                mention = f"{inter.author.mention}, "
                        except AttributeError:
                            pass

                        await func(
                            content=f"{mention}{'operação cancelada' if view.selected is not False else 'tempo esgotado'}" if view.selected is not False else "Cancelado pelo usuário.",
                            embed=None, components=song_request_buttons
                        )
                        return

                    if view.selected == "music":
                        query = link_re.group()

                    try:
                        inter.store_message = msg
                    except AttributeError:
                        pass

                    if not isinstance(inter, disnake.ModalInteraction):
                        inter.token = view.inter.token
                        inter.id = view.inter.id
                        inter.response = view.inter.response
                    else:
                        inter = view.inter

        if not inter.response.is_done():
            await inter.response.defer(ephemeral=ephemeral)

        tracks, node = await self.get_tracks(query, inter.user, node=node, track_loops=repeat_amount)

        try:
            player = bot.music.players[inter.guild_id]
        except KeyError:
            await check_pool_bots(inter, check_player=False)

            try:
                bot = inter.music_bot
                guild = inter.music_guild
                channel = bot.get_channel(inter.channel.id)
            except AttributeError:
                bot = inter.bot
                guild = inter.guild
                channel = inter.channel

            try:
                player = bot.music.players[inter.guild_id]
            except KeyError:
                player = None

                guild_data = None

                if inter.bot == bot:
                    try:
                        guild_data = inter.guild_data
                    except AttributeError:
                        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)
                        try:
                            inter.guild_data = guild_data
                        except AttributeError:
                            pass

                if not guild_data:
                    guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

                static_player = guild_data['player_controller']

                if static_player['channel']:
                    channel, warn_message = await self.check_channel(guild_data, inter, channel, guild, bot)

        if not player:

            skin = guild_data["player_controller"]["skin"]
            static_skin = guild_data["player_controller"]["static_skin"]

            try:
                global_data = inter.global_guild_data
            except AttributeError:
                global_data = await self.bot.get_global_data(guild.id, db_name=DBModel.guilds)
                try:
                    inter.global_guild_data = global_data
                except:
                    pass

            if global_data["global_skin"]:
                skin = global_data["player_skin"] or skin
                static_skin = global_data["player_skin_static"] or guild_data["player_controller"]["static_skin"]

            try:
                invite = global_data["listen_along_invites"][str(inter.channel.id)]
            except KeyError:
                invite = None

            else:

                try:
                    invite = (await self.bot.fetch_invite(invite)).url
                except disnake.NotFound:
                    invite = None

                if not invite:
                    print(
                        f'{"-"*15}\n'
                        f'Removendo invite: {invite} \n'
                        f'Servidor: {inter.guild.name} [{inter.guild_id}]\n'
                        f'Canal: {inter.channel.name} [{inter.channel.id}]\n'
                        f'{"-" * 15}'
                    )
                    del global_data["listen_along_invites"][str(inter.channel.id)]
                    await self.bot.update_global_data(inter.guild_id, global_data, db_name=DBModel.guilds)

            player: LavalinkPlayer = bot.music.get_player(
                guild_id=inter.guild_id,
                cls=LavalinkPlayer,
                player_creator=inter.author.id,
                guild=guild,
                channel=channel or bot.get_channel(inter.channel_id),
                last_message_id=guild_data['player_controller']['message_id'],
                node_id=node.identifier,
                static=bool(static_player['channel']),
                skin=bot.check_skin(skin),
                custom_skin_data=global_data["custom_skins"],
                custom_skin_static_data=global_data["custom_skins_static"],
                skin_static=bot.check_static_skin(static_skin),
                extra_hints=self.extra_hints,
                restrict_mode=guild_data['enable_restrict_mode'],
                listen_along_invite=invite,
                volume=int(guild_data['default_player_volume']),
                autoplay=guild_data["autoplay"],
                prefix=global_data["prefix"] or bot.default_prefix,
                purge_mode=guild_data['player_controller']['purge_mode']
            )

            if static_player['channel']:

                if isinstance(player.text_channel, disnake.Thread):
                    channel_check = player.text_channel.parent
                else:
                    channel_check = player.text_channel

                bot_perms = channel_check.permissions_for(guild.me)

                if not bot_perms.read_message_history:

                    if not bot_perms.manage_permissions:

                        player.set_command_log(
                            emoji="⚠️",
                            text=f"Não tenho permissão de ver historico de mensagens no canal: {channel_check.mention} "
                                 f"(e nem permissão de gerenciar permissões para corrigir isso automaticamente), o "
                                 f"player funcionará da forma padrão..."
                        )

                        player.static = False

                    else:

                        overwrites = {
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

                        await channel_check.edit(overwrites=overwrites)

                if not player.message:
                    try:
                        player.message = await channel.fetch_message(int(static_player['message_id']))
                    except TypeError:
                        player.message = None
                    except:
                        player.message = await send_idle_embed(channel, bot=bot, guild_data=guild_data)

            if not player.static:

                if message_inter:
                    player.message = message_inter
                elif modal_message_id:
                    try:
                        player.message = await inter.channel.fetch_message(modal_message_id)
                    except:
                        pass

                if not player.has_thread:
                    player.message = None
                else:
                    await self.thread_song_request(message_inter.thread, reopen=True)

        pos_txt = ""

        embed = disnake.Embed(color=disnake.Colour.red())

        embed.colour = self.bot.get_color(guild.me)

        position -= 1

        if isinstance(tracks, list):

            if manual_selection and len(tracks) > 1:

                embed.description = f"**Selecione a(s) música(s) desejada(s) abaixo:**"

                try:
                    func = inter.edit_original_message
                except AttributeError:
                    func = inter.send

                try:
                    add_id = f"_{inter.id}"
                except AttributeError:
                    add_id = ""

                tracks = tracks[:25]

                msg = await func(
                    embed=embed,
                    components=[
                        disnake.ui.Select(
                            placeholder='Resultados:',
                            custom_id=f"track_selection{add_id}",
                            min_values=1,
                            max_values=len(tracks),
                            options=[
                                disnake.SelectOption(
                                    label=f"{n+1}. {t.title[:96]}",
                                    value=f"track_select_{n}",
                                    description=f"{t.author} [{time_format(t.duration)}]")
                                for n, t in enumerate(tracks)
                            ]
                        )
                    ]
                )

                def check_song_selection(i: Union[CustomContext, disnake.MessageInteraction]):

                    try:
                        return i.data.custom_id == f"track_selection_{inter.id}" and i.author == inter.author
                    except AttributeError:
                        return i.author == inter.author and i.message.id == msg.id

                try:
                    select_interaction: disnake.MessageInteraction = await self.bot.wait_for(
                        "dropdown",
                        timeout=45,
                        check=check_song_selection
                    )
                except asyncio.TimeoutError:
                    raise GenericError("Tempo esgotado!")

                if len(select_interaction.data.values) > 1:

                    indexes = set(int(v[13:]) for v in select_interaction.data.values)

                    selected_tracks = []

                    for i in indexes:
                        for n, t in enumerate(tracks):
                            if i == n:
                                selected_tracks.append(t)
                                break

                    tracks = selected_tracks

                else:

                    tracks = tracks[int(select_interaction.data.values[0][13:])]

                if isinstance(inter, CustomContext):
                    inter.message = msg

            else:

                tracks = tracks[0]

                if tracks.info.get("sourceName") == "http":

                    if tracks.title == "Unknown title":
                        if attachment:
                            tracks.info["title"] = attachment.filename
                        else:
                            tracks.info["title"] = tracks.uri.split("/")[-1]
                        tracks.title = tracks.info["title"]

                    tracks.uri = ""

            if not isinstance(tracks, list):

                if force_play == "yes":
                    player.queue.insert(0, tracks)
                elif position < 0:
                    player.queue.append(tracks)
                else:
                    player.queue.insert(position, tracks)
                    pos_txt = f" na posição {position + 1} da fila"

                duration = time_format(tracks.duration) if not tracks.is_stream else '🔴 Livestream'

                log_text = f"{inter.author.mention} adicionou [`{fix_characters(tracks.title, 20)}`]({tracks.uri or tracks.search_uri}){pos_txt} `({duration})`."

                embed.set_author(
                    name=fix_characters(tracks.title, 35),
                    url=tracks.uri or tracks.search_uri,
                    icon_url=music_source_image(tracks.info['sourceName'])
                )
                embed.set_thumbnail(url=tracks.thumb)
                embed.description = f"`{fix_characters(tracks.author, 15)}`**┃**`{time_format(tracks.duration) if not tracks.is_stream else '🔴 Livestream'}`**┃**{inter.author.mention}"
                emoji = "🎵"

            else:

                if options == "shuffle":
                    shuffle(tracks)

                if position < 0 or len(tracks) < 2:

                    if options == "reversed":
                        tracks.reverse()
                    for track in tracks:
                        player.queue.append(track)
                else:
                    if options != "reversed":
                        tracks.reverse()
                    for track in tracks:
                        player.queue.insert(position, track)

                    pos_txt = f" (Pos. {position + 1})"

                query = fix_characters(query.replace(f"{source}:", '', 1), 25)

                log_text = f"{inter.author.mention} adicionou `{len(tracks)} músicas` via busca: `{query}`{pos_txt}."

                total_duration = 0

                for t in tracks:
                    if not t.is_stream:
                        total_duration += t.duration

                embed.set_author(name=f"Busca: {query}", icon_url=music_source_image(tracks[0].info['sourceName']))
                embed.set_thumbnail(url=tracks[0].thumb)
                embed.description = f"`{len(tracks)} música(s)`**┃**`{time_format(total_duration)}`**┃**{inter.author.mention}"
                emoji = "🎶"

        else:

            if options == "shuffle":
                shuffle(tracks.tracks)

            if position < 0 or len(tracks.tracks) < 2:

                if options == "reversed":
                    tracks.tracks.reverse()
                for track in tracks.tracks:
                    player.queue.append(track)
            else:
                if options != "reversed":
                    tracks.tracks.reverse()
                for track in tracks.tracks:
                    player.queue.insert(position, track)

                pos_txt = f" (Pos. {position + 1})"

            log_text = f"{inter.author.mention} adicionou a playlist [`{fix_characters(tracks.name, 20)}`]({tracks.url}){pos_txt} `({len(tracks.tracks)})`."

            total_duration = 0

            for t in tracks.tracks:
                if not t.is_stream:
                    total_duration += t.duration

            try:
                embed.set_author(
                    name="⠂" + fix_characters(tracks.name, 35),
                    url=tracks.url,
                    icon_url=music_source_image(tracks.tracks[0].info['sourceName'])
                )
            except KeyError:
                embed.set_author(
                    name="⠂ Spotify Playlist",
                    icon_url=music_source_image(tracks.tracks[0].info['sourceName'])
                )
            embed.set_thumbnail(url=tracks.tracks[0].thumb)
            embed.description = f"`{len(tracks.tracks)} música(s)`**┃**`{time_format(total_duration)}`**┃**{inter.author.mention}"
            emoji = "🎶"

        embed.description += player.controller_link

        if not is_pin:

            if not player.is_connected:
                try:
                    embed.description += f"\n`Canal de voz:` {voice_channel.mention}"
                except AttributeError:
                    pass

            try:
                func = inter.edit_original_message
            except AttributeError:
                if msg:
                    func = msg.edit
                elif inter.message.author.id == bot.user.id:
                    func = inter.message.edit
                else:
                    func = inter.send

            try:
                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
            except AttributeError:
                pass

            await func(embed=embed, view=None)

        if not player.is_connected:

            try:
                guild_data["check_other_bots_in_vc"]
            except KeyError:
                guild_data = None

                if inter.bot == bot:
                    try:
                        guild_data = inter.guild_data
                    except AttributeError:
                        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)
                        try:
                            inter.guild_data = guild_data
                        except AttributeError:
                            pass

                if not guild_data:
                    guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

            if not inter.author.voice:
                raise NoVoice()

            await self.do_connect(
                inter, channel=voice_channel,
                check_other_bots_in_vc=guild_data["check_other_bots_in_vc"],
                bot=bot, me=guild.me, check_pool=True
            )

        if not player.current:
            if warn_message:
                player.set_command_log(emoji="⚠️", text=warn_message)
            await player.process_next()
        elif force_play == "yes":
            player.set_command_log(
                emoji="▶️",
                text=f"{inter.author.mention} adicionou a música atual para tocar imediatamente."
            )
            await player.track_end()
            await player.process_next()
        elif player.current.autoplay:
            player.set_command_log(text=log_text, emoji=emoji)
            await player.track_end()
            await player.process_next()
        else:
            if ephemeral:
                player.set_command_log(text=log_text, emoji=emoji)
            player.update = True

    @play.autocomplete("busca")
    async def fav_add_autocomplete(self, inter: disnake.Interaction, query: str):

        if URL_REG.match(query):
            return [query] if len(query) < 100 else []

        favs: list = await fav_list(inter, query)

        if not inter.guild:
            try:
                await check_pool_bots(inter, return_first=True)
            except:
                return [query] if len(query) < 100 else []

        try:
            vc = inter.author.voice
        except AttributeError:
            vc = True

        if not vc or not query or (favs_size := len(favs)) >= 20:
            return favs[:20]

        return await google_search(self.bot, query, max_entries=20 - favs_size) + favs

    skip_back_cd = commands.CooldownMapping.from_cooldown(2, 13, commands.BucketType.member)
    skip_back_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    case_sensitive_args = CommandArgparse()
    case_sensitive_args.add_argument('-casesensitive', '-cs', action='store_true',
                             help="Buscar por músicas com letra exatas ao invés de buscar palavra por palavra no nome da música")
    @check_stage_topic()
    @is_requester()
    @check_queue_loading()
    @check_voice()
    @pool_command(name="skip", aliases=["next", "n", "s", "pular", "skipto"], cooldown=skip_back_cd,
                  max_concurrency=skip_back_mc, description=f"Pular a música atual que está tocando.",
                  extras={"flags": case_sensitive_args}, only_voiced=True,
                  usage="{prefix}{cmd} <termo>\nEx: {prefix}{cmd} sekai")
    async def skip_legacy(self, ctx: CustomContext, *, flags: str = ""):

        args, unknown = ctx.command.extras['flags'].parse_known_args(flags.split())

        if ctx.invoked_with == "skipto" and not unknown:
            raise GenericError("**Você deve adicionar um nome para usar o skipto.**")

        await self.skip.callback(self=self, inter=ctx, query=" ".join(unknown), case_sensitive=args.casesensitive)

    @check_stage_topic()
    @is_requester()
    @check_queue_loading()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Pular para uma música específica da fila.",
        extras={"only_voiced": True}, cooldown=skip_back_cd, max_concurrency=skip_back_mc
    )
    async def skipto(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(
                name="nome",
                description="Nome da música (completa ou parte dela)."
            ),
            case_sensitive: bool = commands.Param(
                name="nome_exato", default=False,
                description="Buscar por músicas com letra exatas ao invés de buscar palavra por palavra no nome da música",

            )
    ):

        await self.skip.callback(self=self, inter=inter, query=query, case_sensitive=case_sensitive)

    @check_stage_topic()
    @is_requester()
    @check_queue_loading()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Pular a música atual que está tocando.",
        extras={"only_voiced": True}, cooldown=skip_back_cd, max_concurrency=skip_back_mc
    )
    async def skip(
            self,
            inter: disnake.AppCmdInter, *,
            query: str = commands.Param(
                name="nome",
                description="Nome da música (completa ou parte dela).",
                default=None,
            ),
            play_only: str = commands.Param(
                name=disnake.Localized("play_only", data={disnake.Locale.pt_BR: "tocar_apenas"}),
                choices=[
                    disnake.OptionChoice(
                        disnake.Localized("Yes", data={disnake.Locale.pt_BR: "Sim"}), "yes"
                    ),
                    disnake.OptionChoice(
                        disnake.Localized("No", data={disnake.Locale.pt_BR: "Não"}), "no"
                    )
                ],
                description="Apenas tocar a música imediatamente (sem rotacionar a flia)",
                default="no"
            ),
            case_sensitive: bool = commands.Param(
                name="nome_exato", default=False,
                description="Buscar por músicas com letra exatas ao invés de buscar palavra por palavra no nome da música",

            )
    ):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = bot.get_guild(inter.guild_id)

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        ephemeral = await self.is_request_channel(inter)

        interaction = None

        if query:

            try:
                index = queue_track_index(inter, bot, query, case_sensitive=case_sensitive)[0][0]
            except IndexError:
                raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

            track = player.queue[index]

            player.queue.append(player.last_track)
            player.last_track = None

            if player.loop == "current":
                player.loop = False

            if play_only == "yes":
                del player.queue[index]
                player.queue.appendleft(track)

            elif index > 0:
                player.queue.rotate(0 - index)

            player.set_command_log(emoji="⤵️", text=f"{inter.author.mention} pulou para a música atual.")

            embed = disnake.Embed(
                color=self.bot.get_color(guild.me),
                description= f"⤵️ **⠂{inter.author.mention} pulou para a música:**\n"
                             f"╰[`{fix_characters(track.title, 43)}`]({track.uri or track.search_uri}){player.controller_link}"
            )

            try:
                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
            except AttributeError:
                pass

            if isinstance(inter, disnake.MessageInteraction) and inter.data.custom_id == "queue_track_selection":
                await inter.response.edit_message(embed=embed, view=None)
            else:
                await inter.send(embed=embed, ephemeral=ephemeral)

        else:

            if isinstance(inter, disnake.MessageInteraction):
                player.set_command_log(text=f"{inter.author.mention} pulou a música.", emoji="⏭️")
                if not inter.response.is_done():
                    try:
                        await inter.response.defer()
                    except:
                        pass
                interaction = inter
            else:

                player.set_command_log(emoji="⏭️", text=f"{inter.author.mention} pulou a música.")

                embed = disnake.Embed(
                    color=self.bot.get_color(guild.me),
                    description=f"⏭️ **⠂{inter.author.mention} pulou a música:\n"
                                f"╰[`{fix_characters(player.current.title, 43)}`]({player.current.uri or player.current.search_uri})**"
                                f"{player.controller_link}"
                )

                try:
                    if bot.user.id != self.bot.user.id:
                        embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
                except AttributeError:
                    pass

                await inter.send(embed=embed, ephemeral=ephemeral)

            if player.loop == "current":
                player.loop = False

        try:
            (player.current or player.last_track).info["extra"]["track_loops"] = 0
        except AttributeError:
            pass

        await player.track_end()
        player.ignore_np_once = True
        await player.process_next(inter=interaction)

    @check_stage_topic()
    @is_dj()
    @check_queue_loading()
    @has_player()
    @check_voice()
    @pool_command(name="back", aliases=["b", "voltar"], description="Voltar para a música anterior.", only_voiced=True,
                  cooldown=skip_back_cd, max_concurrency=skip_back_mc)
    async def back_legacy(self, ctx: CustomContext):
        await self.back.callback(self=self, inter=ctx)

    @check_stage_topic()
    @is_dj()
    @has_player()
    @check_queue_loading()
    @check_voice()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.slash_command(
        description=f"{desc_prefix}Voltar para a música anterior.",
        extras={"only_voiced": True}, cooldown=skip_back_cd, max_concurrency=skip_back_mc
    )
    async def back(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not len(player.queue) and (player.keep_connected or not len(player.played)):
            await player.seek(0)
            await self.interaction_message(inter, "voltou para o início da música.", emoji="⏪")
            return

        if player.keep_connected:
            track = player.queue.pop()
            player.queue.appendleft(player.current)
        else:
            try:
                track = player.played.pop()
            except:
                track = player.queue.pop()

            if player.current and not player.current.autoplay:
                player.queue.appendleft(player.current)

        player.last_track = None

        player.queue.appendleft(track)

        if isinstance(inter, disnake.MessageInteraction):
            interaction = inter
            player.set_command_log(text=f"{inter.author.mention} voltou para a música atual.", emoji="⏮️")
            await inter.response.defer()
        else:

            interaction = None

            t = player.queue[0]

            txt = [
                "voltou para a música atual.",
                f"⏮️ **⠂{inter.author.mention} voltou para a música:\n╰[`{fix_characters(t.title, 43)}`]({t.uri or t.search_uri})**"
            ]

            await self.interaction_message(inter, txt, emoji="⏮️", store_embed=True)

        if player.loop == "current":
            player.loop = False

        player.ignore_np_once = True

        if not player.current:
            await player.process_next(inter=interaction)
        else:
            player.is_previows_music = True
            await player.track_end()
            await player.process_next(inter=interaction)

    @check_stage_topic()
    @check_queue_loading()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Votar para pular a música atual.",
        extras={"only_voiced": True}
    )
    async def voteskip(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = inter.guild

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        embed = disnake.Embed()

        if inter.author.id in player.votes:
            raise GenericError("**Você já votou para pular a música atual.**")

        embed.colour = self.bot.get_color(guild.me)

        txt = [
            f"votou para pular a música atual (votos: {len(player.votes) + 1}/{self.bot.config['VOTE_SKIP_AMOUNT']}).",
            f"{inter.author.mention} votou para pular a música atual (votos: {len(player.votes) + 1}/{self.bot.config['VOTE_SKIP_AMOUNT']}).",
        ]

        if len(player.votes) < self.bot.config.get('VOTE_SKIP_AMOUNT', 3):
            embed.description = txt
            player.votes.add(inter.author.id)
            await self.interaction_message(inter, txt, emoji="✋")
            return

        await self.interaction_message(inter, txt, emoji="✋")
        await player.track_end()
        await player.process_next()

    volume_cd = commands.CooldownMapping.from_cooldown(1, 7, commands.BucketType.member)
    volume_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(name="volume", description="Ajustar volume da música.", aliases=["vol", "v"], only_voiced=True,
                  cooldown=volume_cd, max_concurrency=volume_mc, usage="{prefix}{cmd} [nivel]\nEx: {prefix}{cmd} 50")
    async def volume_legacy(self, ctx: CustomContext, level: int):

        if not 4 < level < 151:
            raise GenericError("**Volume inválido! escolha entre 5 a 150**", self_delete=7)

        await self.volume.callback(self=self, inter=ctx, value=int(level))

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(description=f"{desc_prefix}Ajustar volume da música.", extras={"only_voiced": True},
                            cooldown=volume_cd, max_concurrency=volume_mc)
    async def volume(
            self,
            inter: disnake.AppCmdInter, *,
            value: int = commands.Param(name="nível", description="nível entre 5 a 150", min_value=5.0, max_value=150.0)
    ):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = inter.guild

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        embed = disnake.Embed(color=disnake.Colour.red())

        if value is None:

            view = VolumeInteraction(inter)

            embed.colour = self.bot.get_color(guild.me)
            embed.description = "**Selecione o nível do volume abaixo:**"

            try:
                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
            except AttributeError:
                pass

            await inter.send(embed=embed, ephemeral=await self.is_request_channel(inter), view=view)
            await view.wait()
            if view.volume is None:
                return

            value = view.volume

        elif not 4 < value < 151:
            raise GenericError("O volume deve estar entre **5** a **150**.")

        await player.set_volume(value)

        txt = [f"ajustou o volume para **{value}%**", f"🔊 **⠂{inter.author.mention} ajustou o volume para {value}%**"]
        await self.interaction_message(inter, txt, emoji="🔊")

    pause_resume_cd = commands.CooldownMapping.from_cooldown(2, 7, commands.BucketType.member)
    pause_resume_mc =commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(name="pause", aliases=["pausar"], description="Pausar a música.", only_voiced=True,
                  cooldown=pause_resume_cd, max_concurrency=pause_resume_mc)
    async def pause_legacy(self, ctx: CustomContext):
        await self.pause.callback(self=self, inter=ctx)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Pausar a música.", extras={"only_voiced": True},
        cooldown=pause_resume_cd, max_concurrency=pause_resume_mc
    )
    async def pause(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if player.paused:
            raise GenericError("**A música já está pausada.**")

        await player.set_pause(True)

        txt = ["pausou a música.", f"⏸️ **⠂{inter.author.mention} pausou a musica.**"]

        await self.interaction_message(inter, txt, rpc_update=True, emoji="⏸️")

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(name="resume", aliases=["unpause"], description="Retomar/Despausar a música.", only_voiced=True,
                  cooldown=pause_resume_cd, max_concurrency=pause_resume_mc)
    async def resume_legacy(self, ctx: CustomContext):
        await self.resume.callback(self=self, inter=ctx)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Retomar/Despausar a música.",
        extras={"only_voiced": True}, cooldown=pause_resume_cd, max_concurrency=pause_resume_mc
    )
    async def resume(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not player.paused:
            raise GenericError("**A música não está pausada.**")

        await player.set_pause(False)

        txt = ["retomou a música.", f"▶️ **⠂{inter.author.mention} despausou a música.**"]
        await self.interaction_message(inter, txt, rpc_update=True, emoji="▶️")

    seek_cd = commands.CooldownMapping.from_cooldown(2, 10, commands.BucketType.member)
    seek_mc =commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @check_stage_topic()
    @is_dj()
    @check_queue_loading()
    @has_source()
    @check_voice()
    @pool_command(name="seek", aliases=["sk"], description="Avançar/Retomar a música para um tempo específico.",
                  only_voiced=True, cooldown=seek_cd, max_concurrency=seek_mc,
                  usage="{prefix}{cmd} [tempo]\n"
                        "Ex 1: {prefix}{cmd} 10 (tempo 0:10)\n"
                        "Ex 2: {prefix}{cmd} 1:45 (tempo 1:45)")
    async def seek_legacy(self, ctx: CustomContext, *, position: str):
        await self.seek.callback(self=self, inter=ctx, position=position)

    @check_stage_topic()
    @is_dj()
    @check_queue_loading()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Avançar/Retomar a música para um tempo específico.",
        extras={"only_voiced": True}, cooldown=seek_cd, max_concurrency=seek_mc
    )
    async def seek(
            self,
            inter: disnake.AppCmdInter,
            position: str = commands.Param(name="tempo", description="Tempo para avançar/voltar (ex: 1:45 / 40 / 0:30)")
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if player.current.is_stream:
            raise GenericError("**Você não pode usar esse comando em uma livestream.**")

        position = position.split(" | ")[0].replace(" ", ":")

        seconds = string_to_seconds(position)

        if seconds is None:
            raise GenericError(
                "**Você usou um tempo inválido! Use segundos (1 ou 2 digitos) ou no formato (minutos):(segundos)**")

        milliseconds = seconds * 1000

        if milliseconds < 0:
            milliseconds = 0

        if milliseconds > player.position:

            emoji = "⏩"

            txt = [
                f"avançou o tempo da música para: `{time_format(milliseconds)}`",
                f"{emoji} **⠂{inter.author.mention} avançou o tempo da música para:** `{time_format(milliseconds)}`"
            ]

        else:

            emoji = "⏪"

            txt = [
                f"voltou o tempo da música para: `{time_format(milliseconds)}`",
                f"{emoji} **⠂{inter.author.mention} voltou o tempo da música para:** `{time_format(milliseconds)}`"
            ]

        await player.seek(milliseconds)

        if player.paused:
            await player.set_pause(False)

        await self.interaction_message(inter, txt, emoji=emoji)

        await asyncio.sleep(2)
        await player.process_rpc()

    @seek.autocomplete("tempo")
    async def seek_suggestions(self, inter: disnake.Interaction, query: str):

        try:
            if not inter.author.voice:
                return
        except AttributeError:
            pass

        if query:
            return [time_format(string_to_seconds(query)*1000)]

        try:
            await check_pool_bots(inter, only_voiced=True)
            bot = inter.music_bot
        except:
            return

        try:
            player: LavalinkPlayer = bot.music.players[inter.guild_id]
        except KeyError:
            return

        if not player.current or player.current.is_stream:
            return

        seeks = []

        if player.current.duration >= 90000:
            times = [int(n * 0.5 * 10) for n in range(20)]
        else:
            times = [int(n * 1 * 10) for n in range(20)]

        for p in times:
            percent = percentage(p, player.current.duration)
            seeks.append(f"{time_format(percent)} | {p}%")

        return seeks

    loop_cd = commands.CooldownMapping.from_cooldown(3, 5, commands.BucketType.member)
    loop_mc =commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(
        description=f"Selecionar modo de repetição entre: música atual / fila / desativar / quantidade (usando números).",
        only_voiced=True, cooldown=loop_cd, max_concurrency=loop_mc,
        usage="{prefix}{cmd} <quantidade|modo>\nEx 1: {prefix}{cmd} 1\nEx 2: {prefix}{cmd} queue")
    async def loop(self, ctx: CustomContext, mode: str = None):

        if not mode:

            embed = disnake.Embed(
                description="**Selecione um modo de repetição:**",
                color=self.bot.get_color(ctx.guild.me)
            )

            msg = await ctx.send(
                ctx.author.mention,
                embed=embed,
                components=[
                    disnake.ui.Select(
                        placeholder="Selecione uma opção:",
                        custom_id="loop_mode_legacy",
                        options=[
                            disnake.SelectOption(label="Música Atual", value="current"),
                            disnake.SelectOption(label="Fila do player", value="queue"),
                            disnake.SelectOption(label="Desativar repetição", value="off")
                        ]
                    )
                ]
            )

            try:
                select: disnake.MessageInteraction = await self.bot.wait_for(
                    "dropdown", timeout=30,
                    check=lambda i: i.message.id == msg.id and i.author == ctx.author
                )
            except asyncio.TimeoutError:
                embed.description = "Tempo de seleção esgotado!"
                try:
                    await msg.edit(embed=embed, view=None)
                except:
                    pass
                return

            mode = select.data.values[0]
            ctx.store_message = msg

        if mode.isdigit():

            if len(mode) > 2 or int(mode) > 10:
                raise GenericError(f"**Quantidade inválida: {mode}**\n"
                                   "`Quantidade máxima permitida: 10`")

            await self.loop_amount.callback(self=self, inter=ctx, value=int(mode))
            return

        if mode not in ('current', 'queue', 'off'):
            raise GenericError("Modo inválido! escolha entre: current/queue/off")

        await self.loop_mode.callback(self=self, inter=ctx, mode=mode)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Selecionar modo de repetição entre: atual / fila ou desativar.",
        extras={"only_voiced": True}, cooldown=loop_cd, max_concurrency=loop_mc
    )
    async def loop_mode(
            self,
            inter: disnake.AppCmdInter,
            mode: str = commands.Param(
                name="modo",
                choices=[
                    disnake.OptionChoice(
                        disnake.Localized("Current", data={disnake.Locale.pt_BR: "Música Atual"}), "current"
                    ),
                    disnake.OptionChoice(
                        disnake.Localized("Queue", data={disnake.Locale.pt_BR: "Fila"}), "queue"
                    ),
                    disnake.OptionChoice(
                        disnake.Localized("Off", data={disnake.Locale.pt_BR: "Desativar"}), "off"
                    ),
                ]
            )
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if mode == player.loop:
            raise GenericError("**O modo de repetição selecionado já está ativo...**")

        if mode == 'off':
            mode = False
            player.current.info["extra"]["track_loops"] = 0
            emoji = "⭕"
            txt = ['desativou a repetição.', f"{emoji} **⠂{inter.author.mention}desativou a repetição.**"]

        elif mode == "current":
            player.current.info["extra"]["track_loops"] = 0
            emoji = "🔂"
            txt = ["ativou a repetição da música atual.",
                   f"{emoji} **⠂{inter.author.mention} ativou a repetição da música atual.**"]

        else:  # queue
            emoji = "🔁"
            txt = ["ativou a repetição da fila.", f"{emoji} **⠂{inter.author.mention} ativou a repetição da fila.**"]

        player.loop = mode

        bot.loop.create_task(player.process_rpc())

        await self.interaction_message(inter, txt, emoji=emoji)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Definir quantidade de repetições da música atual.",
        extras={"only_voiced": True}, cooldown=loop_cd, max_concurrency=loop_mc
    )
    async def loop_amount(
            self,
            inter: disnake.AppCmdInter,
            value: int = commands.Param(name="valor", description="número de repetições.")
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        player.current.info["extra"]["track_loops"] = value

        txt = [
            f"definiu a quantidade de repetições da música "
            f"[`{(fix_characters(player.current.title, 25))}`]({player.current.uri or player.current.search_uri}) para **{value}**.",
            f"🔄 **⠂{inter.author.mention} definiu a quantidade de repetições da música para [{value}]:**\n"
            f"╰[`{player.current.title}`]({player.current.uri or player.current.search_uri})"
        ]

        await self.interaction_message(inter, txt, rpc_update=True, emoji="🔄")

    remove_mc = commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="remove", aliases=["r", "del"], description="Remover uma música específica da fila.",
                  only_voiced=True, max_concurrency=remove_mc, extras={"flags": case_sensitive_args},
                  usage="{prefix}{cmd} [nome]\nEx: {prefix}{cmd} sekai")
    async def remove_legacy(self, ctx: CustomContext, *, flags: str = ""):

        args, unknown = ctx.command.extras['flags'].parse_known_args(flags.split())

        if not unknown:
            raise GenericError("**Você não adicionou o nome da música.**")

        await self.remove.callback(self=self, inter=ctx, query=" ".join(unknown), case_sensitive=args.casesensitive)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Remover uma música específica da fila.",
        extras={"only_voiced": True}, max_concurrency=remove_mc
    )
    async def remove(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="nome", description="Nome da música completo."),
            case_sensitive: bool = commands.Param(
                name="nome_exato", default=False,
                description="Buscar por músicas com letra exatas ao invés de buscar palavra por palavra no nome da música",

            )
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            index = queue_track_index(inter, bot, query, case_sensitive=case_sensitive)[0][0]
        except IndexError:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        track = player.queue[index]

        player.queue.remove(track)

        txt = [
            f"removeu a música [`{(fix_characters(track.title, 25))}`]({track.uri or track.search_uri}) da fila.",
            f"♻️ **⠂{inter.author.mention} removeu a música da fila:**\n╰[`{track.title}`]({track.uri or track.search_uri})"
        ]

        await self.interaction_message(inter, txt, emoji="♻️")

        await player.update_message()

    queue_manipulation_cd = commands.CooldownMapping.from_cooldown(2, 15, commands.BucketType.guild)

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="readd", aliases=["readicionar", "rdd"], only_voiced=True, cooldown=queue_manipulation_cd,
                  max_concurrency=remove_mc, description="Readicionar as músicas tocadas na fila.")
    async def readd_legacy(self, ctx: CustomContext):
        await self.readd_songs.callback(self=self, inter=ctx)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Readicionar as músicas tocadas na fila.",
        extras={"only_voiced": True}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc
    )
    async def readd_songs(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not player.played and not player.failed_tracks:
            raise GenericError("**Não há músicas tocadas.**")

        qsize = len(player.played) + len(player.failed_tracks)

        player.played.reverse()
        player.failed_tracks.reverse()
        player.queue.extend(player.failed_tracks)
        player.queue.extend(player.played)
        player.played.clear()
        player.failed_tracks.clear()

        txt = [
            f"readicionou [{qsize}] música(s) tocada(s) na fila.",
            f"🎶 **⠂{inter.author.mention} readicionou {qsize} música(s) na fila.**"
        ]

        await self.interaction_message(inter, txt, emoji="🎶")

        await player.update_message()

        if not player.current:
            await player.process_next()
        else:
            await player.update_message()

    move_args = CommandArgparse()
    move_args.add_argument('-count', '-counter', '-amount', '-c', '-max', type=int, default=None,
                           help="Especificar uma quantidade de músicas para mover com o nome especificado.\nEx: -amount 5")
    move_args.add_argument('-casesensitive', '-cs',  action='store_true',
                           help="Buscar por músicas com letra exatas ao invés de buscar palavra por palavra no nome "
                                "da música")
    move_args.add_argument('-position', '-pos', help="Especificar uma posição de destino (isso serve pra situações no qual o nome pra busca começe com número).\nEx: -pos 1", type=int, default=None)

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="move", aliases=["mv", "mover"], only_voiced=True, max_concurrency=remove_mc,
                  description="Mover músicas pra uma posição especificada da fila.", extras={"flags": move_args},
                  usage="{prefix}{cmd} <posição(nº)> [nome]\nEx 1: {prefix}{cmd} 2 sekai\nEx 2: {prefix}{cmd} sekai\n"
                        "(Nota: caso não seja especificado uma posição via arg ou flag, a música será movida pra posição 1)")
    async def move_legacy(self, ctx: CustomContext, position: Optional[int] = None, *, flags: str = ""):

        args, unknown = ctx.command.extras['flags'].parse_known_args(flags.split())

        if args.position:
            if position:
                unknown.insert(0, str(position))
            position = args.position

        elif not position:
            raise GenericError("**Você não informou uma posição da fila.**")

        if not unknown:
            raise GenericError("**Você não adicionou o nome da música.**")

        await self.move.callback(self=self, inter=ctx, position=position, query=" ".join(unknown), match_count=args.count or 1, case_sensitive=args.casesensitive)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Mover uma música para a posição especificada da fila.",
        extras={"only_voiced": True}, max_concurrency=remove_mc
    )
    async def move(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="nome", description="Nome da música."),
            position: int = commands.Param(name="posição", description="Posição de destino na fila.", default=1),
            match_count: int = commands.Param(
                name="quantidade",
                description="Especificar uma quantidade de músicas para mover com o nome especificado.",
                default=1, min_value=1, max_value=999,
            ),
            case_sensitive: bool = commands.Param(
                name="nome_exato", default=False,
                description="Buscar por músicas por termo exato ao invés de buscar palavra por palavra no nome da música",

            )
    ):

        if position < 1:
            raise GenericError(f"**Você usou uma posição inválida: {position}**.")

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = inter.guild

        player: LavalinkPlayer = bot.music.players[guild.id]

        indexes = queue_track_index(inter, bot, query, match_count=match_count, case_sensitive=case_sensitive)

        if not indexes:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        for index, track in reversed(indexes):
            player.queue.remove(track)

            player.queue.insert(int(position) - 1, track)

        if (i_size := len(indexes)) == 1:
            track = indexes[0][1]

            txt = [
                f"moveu a música [`{fix_characters(track.title, limit=25)}`]({track.uri or track.search_uri}) para a posição **[{position}]** da fila.",
                f"↪️ **⠂{inter.author.mention} moveu uma música para a posição [{position}]:**\n"
                f"╰[`{fix_characters(track.title, limit=43)}`]({track.uri or track.search_uri})"
            ]

            await self.interaction_message(inter, txt, emoji="↪️")

        else:

            tracklist = "\n".join(f"[`{fix_characters(t.title, 45)}`]({t.uri or t.search_uri})" for i, t in indexes[:10])

            position_text = position if i_size == 1 else (str(position) + '-' + str(position+i_size-1))

            embed = disnake.Embed(
                color=self.bot.get_color(guild.me),
                description=f"↪️ **⠂{inter.author.mention} moveu [{i_size}] músicas com o nome \"{query}\" para " \
                            f"a posição [{position_text}] da fila:**\n\n{tracklist}"
            )

            embed.set_thumbnail(url=indexes[0][1].thumb)

            if i_size > 20:
                embed.description += f"\n\n`E mais {i_size - 20} música(s).`"

            if player.controller_link:
                embed.description += f" `|`{player.controller_link}"

            ephemeral = await self.is_request_channel(inter)

            if ephemeral:
                player.set_command_log(
                    text=f"{inter.author.mention} moveu **[{i_size}]** músicas com o nome **{fix_characters(query, 25)}"
                         f"** para a posição **[{position_text}]** da fila.", emoji="↪️")

            try:
                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
            except AttributeError:
                pass

            await inter.send(embed=embed, ephemeral=ephemeral)

        await player.update_message()

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="rotate", aliases=["rt", "rotacionar"], only_voiced=True,
                  description="Rotacionar a fila para a música especificada.",
                  cooldown=queue_manipulation_cd, max_concurrency=remove_mc, extras={"flags": case_sensitive_args},
                  usage="{prefix}{cmd} [nome]\nEx: {prefix}{cmd} sekai")
    async def rotate_legacy(self, ctx: CustomContext, *, flags: str = ""):

        args, unknown = ctx.command.extras['flags'].parse_known_args(flags.split())

        if not unknown:
            raise GenericError("**Você não adicionou o nome da música.**")

        await self.rotate.callback(self=self, inter=ctx, query=" ".join(unknown), case_sensitive=args.casesensitive)

    @is_dj()
    @check_queue_loading()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Rotacionar a fila para a música especificada.",
        extras={"only_voiced": True}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc
    )
    async def rotate(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="nome", description="Nome da música completo."),
            case_sensitive: bool = commands.Param(
                name="nome_exato", default=False,
                description="Buscar por músicas com letra exatas ao invés de buscar palavra por palavra no nome da música",
            )
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        index = queue_track_index(inter, bot, query, case_sensitive=case_sensitive)

        if not index:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        index = index[0][0]

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        track = player.queue[index]

        if index <= 0:
            raise GenericError(f"**A música **[`{track.title}`]({track.uri or track.search_uri}) já é a próxima da fila.")

        player.queue.rotate(0 - (index))

        txt = [
            f"rotacionou a fila para a música [`{(fix_characters(track.title, limit=25))}`]({track.uri or track.search_uri}).",
            f"🔃 **⠂{inter.author.mention} rotacionou a fila para a música:**\n╰[`{track.title}`]({track.uri or track.search_uri})."
        ]

        await self.interaction_message(inter, txt, emoji="🔃")

        await player.update_message()

    song_request_thread_cd = commands.CooldownMapping.from_cooldown(1, 120, commands.BucketType.guild)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.bot_has_guild_permissions(manage_threads=True)
    @pool_command(name="songrequestthread", aliases=["songrequest", "srt"], only_voiced=True,
                  description="Criar uma thread/conversa temporária para song-request (pedido de música)")
    async def song_request_thread_legacy(self, ctx: CustomContext):

        await self.song_request_thread.callback(self=self, inter=ctx)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(extras={"only_voiced": True}, cooldown=song_request_thread_cd,
                            description=f"{desc_prefix}Criar uma thread/conversa temporária para song-request (pedido de música)")
    async def song_request_thread(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = inter.guild

        if not self.bot.intents.message_content:
            raise GenericError("**Atualmente não tenho a intent de message-content para conferir "
                               "o conteúdo de mensagens**")

        player: LavalinkPlayer = bot.music.players[guild.id]

        if player.static:
            raise GenericError("**Você não pode usar esse comando com um canal de song-request configurado.**")

        if player.has_thread:
            raise GenericError("**Já há uma thread/conversa ativa no player.**")

        if not isinstance(player.text_channel, disnake.TextChannel):
            raise GenericError(f"**O player-controller está ativo em um canal incompatível com "
                               f"criação de thread/conversa.**")

        if not player.controller_mode:
            raise GenericError("**A skin/aparência atual não é compatível com o sistem de song-request "
                               "via thread/conversa\n\n"
                               "Nota:** `Esse sistema requer uma skin que use botões.`")

        if not player.text_channel.permissions_for(guild.me).create_public_threads:
            raise GenericError("**Não tenho permissão de criar tópicos públicos**")

        if not [m for m in player.guild.me.voice.channel.members if not m.bot and
                player.text_channel.permissions_for(m).send_messages_in_threads]:
            raise GenericError(f"**Não há membros no canal <#{player.channel_id}> com permissão de enviar mensagens "
                               f"em tópicos no canal {player.text_channel.mention}")

        await inter.response.defer(ephemeral=True)

        thread = await player.message.create_thread(name=f"{bot.user.name} temp. song-request", auto_archive_duration=10080)

        txt = [
            "Ativou o sistema de thread/conversa temporária para pedido de música.",
            f"💬 **⠂{inter.author.mention} criou uma [thread/conversa]({thread.jump_url}) temporária para pedido de música.**"
        ]

        await self.interaction_message(inter, txt, emoji="💬", defered=True, force=True)

    @rotate.autocomplete("nome")
    @move.autocomplete("nome")
    @skip.autocomplete("nome")
    @skipto.autocomplete("nome")
    @remove.autocomplete("nome")
    async def queue_tracks(self, inter: disnake.AppCmdInter, query: str):

        try:
            if not inter.author.voice:
                return
        except AttributeError:
            pass

        try:
            if not await check_pool_bots(inter, only_voiced=True):
                return
        except PoolException:
            pass
        except:
            return

        try:
            player = inter.music_bot.music.players[inter.guild_id]
        except KeyError:
            return

        results = []

        count = 0

        for track in player.queue:

            if count == 20:
                break

            title = track.title.lower().split()

            query_words = query.lower().split()

            word_count = 0

            for query_word in query.lower().split():
                for title_word in title:
                    if query_word in title_word:
                        title.remove(title_word)
                        word_count += 1
                        break

            if word_count == len(query_words):
                results.append(f"{track.title[:81]} || ID > {track.unique_id}")
                count += 1

        return results or [f"{track.title[:81]} || ID > {track.unique_id}" for n, track in enumerate(player.queue)
                if query.lower() in track.title.lower()][:20]

    nightcore_cd = commands.CooldownMapping.from_cooldown(1, 7, commands.BucketType.guild)
    nightcore_mc = commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(name="nightcore", aliases=["nc"], only_voiced=True, cooldown=nightcore_cd, max_concurrency=nightcore_mc,
                  description="Ativar/Desativar o efeito nightcore (Música acelerada com tom mais agudo).")
    async def nightcore_legacy(self, ctx: CustomContext):

        await self.nightcore.callback(self=self, inter=ctx)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Ativar/Desativar o efeito nightcore (Música acelerada com tom mais agudo).",
        extras={"only_voiced": True}, cooldown=nightcore_cd, max_concurrency=nightcore_mc,
    )
    async def nightcore(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        player.nightcore = not player.nightcore

        if player.nightcore:
            await player.set_timescale(pitch=1.2, speed=1.1)
            txt = "ativou"
        else:
            await player.set_timescale(enabled=False)
            await player.update_filters()
            txt = "desativou"

        txt = [f"{txt} o efeito nightcore.", f"🇳 **⠂{inter.author.mention} {txt} o efeito nightcore.**"]

        await self.interaction_message(inter, txt, emoji="🇳")

    controller_cd = commands.CooldownMapping.from_cooldown(1, 10, commands.BucketType.member)
    controller_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @has_source()
    @check_voice()
    @pool_command(name="controller", aliases=["np", "ctl"], only_voiced=True, cooldown=controller_cd,
                  max_concurrency=controller_mc, description="Enviar player controller para um canal específico/atual.")
    async def controller_legacy(self, ctx: CustomContext):
        await self.controller.callback(self=self, inter=ctx)

    @has_source()
    @check_voice()
    @commands.slash_command(description=f"{desc_prefix}Enviar player controller para um canal específico/atual.",
                            extras={"only_voiced": True}, cooldown=controller_cd, max_concurrency=controller_mc,)
    async def controller(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
            channel = bot.get_channel(inter.channel.id)
        except AttributeError:
            bot = inter.bot
            guild = inter.guild
            channel = inter.channel

        player: LavalinkPlayer = bot.music.players[guild.id]

        if player.static:
            raise GenericError("Esse comando não pode ser usado no modo fixo do player.")

        if player.has_thread:
            raise GenericError("**Esse comando não pode ser usado com uma conversa ativa na "
                               f"[mensagem]({player.message.jump_url}) do player.**")

        if not inter.response.is_done():
            await inter.response.defer(ephemeral=True)

        if channel != player.text_channel:

            await is_dj().predicate(inter)

            try:

                player.set_command_log(
                    text=f"{inter.author.mention} moveu o player-controller para o canal {inter.channel.mention}.",
                    emoji="💠"
                )

                embed = disnake.Embed(
                    description=f"💠 **⠂{inter.author.mention} moveu o player-controller para o canal:** {channel.mention}",
                    color=self.bot.get_color(guild.me)
                )

                try:
                    if bot.user.id != self.bot.user.id:
                        embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
                except AttributeError:
                    pass

                await player.text_channel.send(embed=embed)

            except:
                pass

        await player.destroy_message()

        player.text_channel = channel

        await player.invoke_np()

        if not isinstance(inter, CustomContext):
            await inter.edit_original_message("**Player reenviado com sucesso!**")

    @is_dj()
    @has_player()
    @check_voice()
    @commands.user_command(name=disnake.Localized("Add DJ", data={disnake.Locale.pt_BR: "Adicionar DJ"}),
                           extras={"only_voiced": True})
    async def adddj_u(self, inter: disnake.UserCommandInteraction):
        await self.add_dj(interaction=inter, user=inter.target)

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="adddj", aliases=["adj"], only_voiced=True,
                  description="Adicionar um membro à lista de DJ's na sessão atual do player.",
                  usage="{prefix}{cmd} [id|nome|@user]\nEx: {prefix}{cmd} @membro")
    async def add_dj_legacy(self, ctx: CustomContext, user: disnake.Member):
        await self.add_dj.callback(self=self, inter=ctx, user=user)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Adicionar um membro à lista de DJ's na sessão atual do player.",
        extras={"only_voiced": True}
    )
    async def add_dj(
            self,
            inter: disnake.AppCmdInter, *,
            user: disnake.User = commands.Param(name="membro", description="Membro a ser adicionado.")
    ):

        error_text = None

        try:
            bot = inter.music_bot
            guild = inter.music_guild
            channel = bot.get_channel(inter.channel.id)
        except AttributeError:
            bot = inter.bot
            guild = inter.guild
            channel = inter.channel

        player: LavalinkPlayer = bot.music.players[guild.id]

        user = guild.get_member(user.id)

        if user.bot:
            error_text = "**Você não pode adicionar um bot na lista de DJ's.**"
        elif user == inter.author:
            error_text = "**Você não pode adicionar a si mesmo na lista de DJ's.**"
        elif user.guild_permissions.manage_channels:
            error_text = f"você não pode adicionar o membro {user.mention} na lista de DJ's (ele(a) possui permissão de **gerenciar canais**)."
        elif user.id == player.player_creator:
            error_text = f"**O membro {user.mention} é o criador do player...**"
        elif user.id in player.dj:
            error_text = f"**O membro {user.mention} já está na lista de DJ's**"

        if error_text:
            raise GenericError(error_text)

        player.dj.add(user.id)

        text = [f"adicionou {user.mention} à lista de DJ's.",
                f"🎧 **⠂{inter.author.mention} adicionou {user.mention} na lista de DJ's.**"]

        if (player.static and channel == player.text_channel) or isinstance(inter.application_command,
                                                                            commands.InvokableApplicationCommand):
            await inter.send(f"{user.mention} adicionado à lista de DJ's!{player.controller_link}")

        await self.interaction_message(inter, txt=text, emoji="🎧")

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Remover um membro da lista de DJ's na sessão atual do player.",
        extras={"only_voiced": True}
    )
    async def remove_dj(
            self,
            inter: disnake.AppCmdInter, *,
            user: disnake.User = commands.Param(name="membro", description="Membro a ser adicionado.")
    ):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
            channel = bot.get_channel(inter.channel.id)
        except AttributeError:
            bot = inter.bot
            guild = inter.guild
            channel = inter.channel

        player: LavalinkPlayer = bot.music.players[guild.id]

        user = guild.get_member(user.id)

        if user.id == player.player_creator:
            if inter.author.guild_permissions.manage_guild:
                player.player_creator = None
            else:
                raise GenericError(f"**O membro {user.mention} é o criador do player.**")

        elif user.id not in player.dj:
            GenericError(f"O membro {user.mention} não está na lista de DJ's")

        else:
            player.dj.remove(user.id)

        text = [f"removeu {user.mention} da lista de DJ's.",
                f"🎧 **⠂{inter.author.mention} removeu {user.mention} da lista de DJ's.**"]

        if (player.static and channel == player.text_channel) or isinstance(inter.application_command,
                                                                            commands.InvokableApplicationCommand):
            await inter.send(f"{user.mention} adicionado à lista de DJ's!{player.controller_link}")

        await self.interaction_message(inter, txt=text, emoji="🎧")

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="stop", aliases=["leave", "parar"], only_voiced=True,
                  description="Parar o player e me desconectar do canal de voz.")
    async def stop_legacy(self, ctx: CustomContext):
        await self.stop.callback(self=self, inter=ctx)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Parar o player e me desconectar do canal de voz.",
        extras={"only_voiced": True}
    )
    async def stop(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
            inter_destroy = inter if bot.user.id == self.bot.user.id else None
        except AttributeError:
            bot = inter.bot
            guild = inter.guild
            inter_destroy = inter

        player: LavalinkPlayer = bot.music.players[inter.guild_id]
        player.command_log = f"{inter.author.mention} **parou o player!**"

        if isinstance(inter, disnake.MessageInteraction):
            await player.destroy(inter=inter_destroy)
        else:

            embed = disnake.Embed(
                color=self.bot.get_color(guild.me),
                description=f"🛑 **⠂{inter.author.mention} parou o player.**"
            )

            try:
                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
            except AttributeError:
                pass

            await inter.send(
                embed=embed,
                components=song_request_buttons if inter.guild else [],
                ephemeral=player.static and player.text_channel.id == inter.channel_id
            )
            await player.destroy()

    @has_player()
    @check_voice()
    @commands.slash_command(name="queue", extras={"only_voiced": True})
    async def q(self, inter):
        pass

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="shuffle", aliases=["sf", "shf", "sff", "misturar"], only_voiced=True,
                  description="Misturar as músicas da fila", cooldown=queue_manipulation_cd, max_concurrency=remove_mc)
    async def shuffle_legacy(self, ctx: CustomContext):
        await self.shuffle_.callback(self, inter=ctx)

    @is_dj()
    @q.sub_command(
        name="shuffle",
        description=f"{desc_prefix}Misturar as músicas da fila",
        extras={"only_voiced": True}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc)
    async def shuffle_(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if len(player.queue) < 3:
            raise GenericError("**A fila tem que ter no mínimo 3 músicas para ser misturada.**")

        shuffle(player.queue)

        await self.interaction_message(
            inter,
            ["misturou as músicas da fila.",
             f"🔀 **⠂{inter.author.mention} misturou as músicas da fila.**"],
            emoji="🔀"
        )

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="reverse", aliases=["invert", "inverter", "rv"], only_voiced=True,
                  description="Inverter a ordem das músicas na fila", cooldown=queue_manipulation_cd, max_concurrency=remove_mc)
    async def reverse_legacy(self, ctx: CustomContext):
        await self.reverse.callback(self=self, inter=ctx)

    @is_dj()
    @q.sub_command(
        description=f"{desc_prefix}Inverter a ordem das músicas na fila",
        extras={"only_voiced": True}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc
    )
    async def reverse(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if len(player.queue) < 2:
            raise GenericError("**A fila tem que ter no mínimo 2 músicas para inverter a ordem.**")

        player.queue.reverse()
        await self.interaction_message(
            inter,
            txt=["inverteu a ordem das músicas na fila.",
                 f"🔄 **⠂{inter.author.mention} inverteu a ordem das músicas na fila.**"],
            emoji="🔄"
        )

    queue_show_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @check_voice()
    @has_player()
    @check_voice()
    @pool_command(name="queue", aliases=["q", "fila"], description="Exibir as músicas que estão na fila.",
                  only_voiced=True, max_concurrency=queue_show_mc)
    async def queue_show_legacy(self, ctx: CustomContext):
        await self.display.callback(self=self, inter=ctx)

    @commands.max_concurrency(1, commands.BucketType.member)
    @q.sub_command(
        description=f"{desc_prefix}Exibir as músicas que estão na fila.", max_concurrency=queue_show_mc
    )
    async def display(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not player.queue:
            raise GenericError("**Não há músicas na fila.**")

        view = QueueInteraction(player, inter.author)
        embed = view.embed

        try:
            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
        except AttributeError:
            pass

        await inter.response.defer(ephemeral=True)

        kwargs = {
            "embed": embed,
            "view": view
        }

        try:
            func = inter.followup.send
            kwargs["ephemeral"] = True
        except AttributeError:
            try:
                func = inter.edit_original_message
            except AttributeError:
                func = inter.send
                kwargs["ephemeral"] = True

        view.message = await func(**kwargs)

        await view.wait()

    clear_flags = CommandArgparse()
    clear_flags.add_argument('-songtitle', '-name', '-title', '-songname',nargs='+', help="incluir nome que tiver na música.\nEx: -name NCS", default=[])
    clear_flags.add_argument('-uploader', '-author', '-artist', nargs = '+', default=[],
                             help="Remover músicas com o nome que tiver no autor especificado.\nEx: -uploader sekai")
    clear_flags.add_argument('-member', '-user', '-u', nargs='+', default=[],
                             help="Remover músicas pedidas pelo usuário especificado.\nEx: -user @user")
    clear_flags.add_argument('-duplicates', '-dupes', '-duplicate', action='store_true',
                             help="Remover músicas duplicadas.")
    clear_flags.add_argument('-playlist', '-list', '-pl', nargs='+', default=[],
                             help="Remover música que tiver com nome especificado na playlist associada.\nEx: -playlist minhaplaylist")
    clear_flags.add_argument('-minimaltime', '-mintime', '-min','-minduration', '-minduration',  default=None,
                             help="Remover músicas com a duração mínima especificada.\nEx: -min 1:23.")
    clear_flags.add_argument('-maxduration', '-maxtime', '-max', default=None,
                             help="Remover músicas com a duração máxima especificada.\nEx: -max 1:23.")
    clear_flags.add_argument('-startposition', '-startpos', '-start', type=int, default=None,
                             help="Remover músicas a partir de uma posição inicial da fila.\nEx: -start 10")
    clear_flags.add_argument('-endposition', '-endpos', '-end', type=int, default=None,
                             help="Remover músicas da fila até uma posição específica na fila.\nEx: -end 15")
    clear_flags.add_argument('-absentmembers', '-absent', '-abs', action='store_true',
                             help="Remover músicas adicionads por membros que saíram do canal")

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="clear", aliases=["limpar"], description="Limpar a fila de música.", only_voiced=True,
                  extras={"flags": clear_flags}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc)
    async def clear_legacy(self, ctx: CustomContext, *, flags: str = ""):

        args, unknown = ctx.command.extras['flags'].parse_known_args(flags.split())

        await self.clear.callback(
            self=self, inter=ctx,
            song_name=" ".join(args.songtitle + unknown),
            song_author=" ".join(args.uploader),
            user=await commands.MemberConverter().convert(ctx, " ".join(args.member)) if args.member else None,
            duplicates=args.duplicates,
            playlist=" ".join(args.playlist),
            min_duration=args.minimaltime,
            max_duration=args.maxduration,
            range_start=args.startposition,
            range_end=args.endposition,
            absent_members=args.absentmembers
        )

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        name="clear_queue",
        description=f"{desc_prefix}Limpar a fila de música.",
        extras={"only_voiced": True}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc
    )
    async def clear(
            self,
            inter: disnake.AppCmdInter,
            song_name: str = commands.Param(name="nome_da_música", description="incluir nome que tiver na música.",
                                            default=None),
            song_author: str = commands.Param(name="nome_do_autor",
                                              description="Incluir nome que tiver no autor da música.", default=None),
            user: disnake.Member = commands.Param(name='usuário',
                                                  description="Incluir músicas pedidas pelo usuário selecionado.",
                                                  default=None),
            duplicates: bool = commands.Param(name="duplicados", description="Incluir músicas duplicadas",
                                              default=False),
            playlist: str = commands.Param(description="Incluir nome que tiver na playlist.", default=None),
            min_duration: str = commands.Param(name="duração_inicial",
                                               description="incluir músicas com duração acima/igual (ex. 1:23).",
                                               default=None),
            max_duration: str = commands.Param(name="duração_máxima",
                                               description="incluir músicas com duração máxima especificada (ex. 1:45).",
                                               default=None),
            range_start: int = commands.Param(name="posição_inicial",
                                              description="incluir músicas da fila a partir de uma posição específica "
                                                          "da fila.",
                                              min_value=1.0, max_value=500.0, default=None),
            range_end: int = commands.Param(name="posição_final",
                                            description="incluir músicas da fila até uma posição específica da fila.",
                                            min_value=1.0, max_value=500.0, default=None),
            absent_members: bool = commands.Param(name="membros_ausentes",
                                                  description="Incluir músicas adicionads por membros fora do canal",
                                                  default=False)
    ):

        if min_duration and max_duration:
            raise GenericError(
                "Você deve escolher apenas uma das opções: **duração_abaixo_de** ou **duração_acima_de**.")

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not player.queue:
            raise GenericError("**Não há musicas na fila.**")

        filters = []
        final_filters = set()

        txt = []
        playlist_hyperlink = set()

        if song_name:
            filters.append('song_name')
        if song_author:
            filters.append('song_author')
        if user:
            filters.append('user')
        if playlist:
            filters.append('playlist')
        if min_duration:
            filters.append('time_below')
            min_duration = string_to_seconds(min_duration) * 1000
        if max_duration:
            filters.append('time_above')
            max_duration = string_to_seconds(max_duration) * 1000
        if absent_members:
            filters.append('absent_members')
        if duplicates:
            filters.append('duplicates')

        if not filters and not range_start and not range_end:
            player.queue.clear()
            txt = ['limpou a fila de música.', f'♻️ **⠂{inter.author.mention} limpou a fila de música.**']

        else:

            if range_start and range_end:

                if range_start >= range_end:
                    raise GenericError("**A posição final deve ser maior que a posição inicial!**")

                song_list = list(player.queue)[range_start - 1: range_end - 1]
                txt.append(f"**Posição inicial da fila:** `{range_start}`\n"
                           f"**Posição final da fila:** `{range_end}`")

            elif range_start:
                song_list = list(player.queue)[range_start - 1:]
                txt.append(f"**Posição inicial da fila:** `{range_start}`")
            elif range_end:
                song_list = list(player.queue)[:range_end - 1]
                txt.append(f"**Posição final da fila:** `{range_end}`")
            else:
                song_list = list(player.queue)

            deleted_tracks = 0

            duplicated_titles = set()

            for t in song_list:

                temp_filter = list(filters)

                if 'duplicates' in temp_filter:
                    if (title:=f"{t.author} - {t.title}".lower()) in duplicated_titles:
                        temp_filter.remove('duplicates')
                        final_filters.add('duplicates')
                    else:
                        duplicated_titles.add(title)

                if 'time_below' in temp_filter and t.duration >= min_duration:
                    temp_filter.remove('time_below')
                    final_filters.add('time_below')

                elif 'time_above' in temp_filter and t.duration <= max_duration:
                    temp_filter.remove('time_above')
                    final_filters.add('time_above')

                if 'song_name' in temp_filter and song_name.lower() in t.title.lower():
                    temp_filter.remove('song_name')
                    final_filters.add('song_name')

                if 'song_author' in temp_filter and song_author.lower() in t.author.lower():
                    temp_filter.remove('song_author')
                    final_filters.add('song_author')

                if 'user' in temp_filter and user.id == t.requester:
                    temp_filter.remove('user')
                    final_filters.add('user')

                elif 'absent_members' in temp_filter and t.requester not in player.guild.me.voice.channel.voice_states:
                    temp_filter.remove('absent_members')
                    final_filters.add('absent_members')

                if 'playlist' in temp_filter:
                    if playlist == t.playlist_name:
                        playlist_hyperlink.add(f"[`{fix_characters(t.playlist_name)}`]({t.playlist_url})")
                        temp_filter.remove('playlist')
                        final_filters.add('playlist')
                    elif isinstance(inter, CustomContext) and playlist.lower() in t.playlist_name.lower():
                        playlist_hyperlink.add(f"[`{fix_characters(t.playlist_name)}`]({t.playlist_url})")
                        temp_filter.remove('playlist')
                        final_filters.add('playlist')

                if not temp_filter:
                    player.queue.remove(t)
                    deleted_tracks += 1

            duplicated_titles.clear()

            if not deleted_tracks:
                await inter.send("Nenhuma música encontrada!", ephemeral=True)
                return

            try:
                final_filters.remove("song_name")
                txt.append(f"**Inclui nome:** `{fix_characters(song_name)}`")
            except:
                pass

            try:
                final_filters.remove("song_author")
                txt.append(f"**Inclui nome no uploader/artista:** `{fix_characters(song_author)}`")
            except:
                pass

            try:
                final_filters.remove("user")
                txt.append(f"**Pedido pelo membro:** {user.mention}")
            except:
                pass

            try:
                final_filters.remove("playlist")
                txt.append(f"**Playlist:** {' | '.join(playlist_hyperlink)}")
            except:
                pass

            try:
                final_filters.remove("time_below")
                txt.append(f"**Com duração inicial/igual:** `{time_format(min_duration)}`")
            except:
                pass

            try:
                final_filters.remove("time_above")
                txt.append(f"**Com duração máxima:** `{time_format(max_duration)}`")
            except:
                pass

            try:
                final_filters.remove("duplicates")
                txt.append(f"**Músicas duplicadas**")
            except:
                pass

            try:
                final_filters.remove("absent_members")
                txt.append("`Músicas pedidas por membros que saíram do canal.`")
            except:
                pass

            txt = [f"removeu {deleted_tracks} música(s) da fila via clear.",
                   f"♻️ **⠂{inter.author.mention} removeu {deleted_tracks} música(s) da fila usando os seguintes "
                   f"filtros:**\n\n" + '\n'.join(txt)]

        await self.interaction_message(inter, txt, emoji="♻️")

    @clear.autocomplete("playlist")
    async def queue_playlist(self, inter: disnake.Interaction, query: str):

        try:
            if not inter.author.voice:
                return
        except:
            pass

        try:
            await check_pool_bots(inter, only_voiced=True)
            bot = inter.music_bot
        except:
            traceback.print_exc()
            return

        try:
            player = bot.music.players[inter.guild_id]
        except KeyError:
            return

        return list(set([track.playlist_name for track in player.queue if track.playlist_name and
                         query.lower() in track.playlist_name.lower()]))[:20]

    @clear.autocomplete("nome_do_autor")
    async def queue_author(self, inter: disnake.Interaction, query: str):

        if not query:
            return

        try:
            await check_pool_bots(inter, only_voiced=True)
            bot = inter.music_bot
        except:
            return

        if not inter.author.voice:
            return

        try:
            player = bot.music.players[inter.guild_id]
        except KeyError:
            return

        return list(set([track.author for track in player.queue if query.lower() in track.author.lower()]))[:20]

    restrict_cd = commands.CooldownMapping.from_cooldown(2, 7, commands.BucketType.member)
    restrict_mc =commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="restrictmode", aliases=["rstc", "restrict", "restrito", "modorestrito"], only_voiced=True, cooldown=restrict_cd, max_concurrency=restrict_mc,
                  description="Ativar/Desativar o modo restrito de comandos que requer DJ/Staff.")
    async def restrict_mode_legacy(self, ctx: CustomContext):

        await self.restrict_mode.callback(self=self, inter=ctx)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        description=f"{desc_prefix}Ativar/Desativar o modo restrito de comandos que requer DJ/Staff.",
        extras={"only_voiced": True}, cooldown=restrict_cd, max_concurrency=restrict_mc)
    async def restrict_mode(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        player.restrict_mode = not player.restrict_mode

        msg = ["ativou", "🔐"] if player.restrict_mode else ["desativou", "🔓"]

        text = [
            f"{msg[0]} o modo restrito de comandos do player (que requer DJ/Staff).",
            f"{msg[1]} **⠂{inter.author.mention} {msg[0]} o modo restrito de comandos do player (que requer DJ/Staff).**"
        ]

        await self.interaction_message(inter, text, emoji=msg[1])

    nonstop_cd = commands.CooldownMapping.from_cooldown(2, 15, commands.BucketType.member)
    nonstop_mc =commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @has_player()
    @check_voice()
    @commands.has_guild_permissions(manage_guild=True)
    @pool_command(name="247", aliases=["nonstop"], only_voiced=True, cooldown=nonstop_cd, max_concurrency=nonstop_mc,
                  description="Ativar/Desativar o modo 24/7 do player (Em testes).")
    async def nonstop_legacy(self, ctx: CustomContext):
        await self.nonstop.callback(self=self, inter=ctx)

    @has_player()
    @check_voice()
    @commands.slash_command(
        name="247",
        description=f"{desc_prefix}Ativar/Desativar o modo 24/7 do player (Em testes).",
        default_member_permissions=disnake.Permissions(manage_guild=True),
        extras={"only_voiced": True}, cooldown=nonstop_cd, max_concurrency=nonstop_mc
    )
    async def nonstop(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        player.keep_connected = not player.keep_connected

        msg = ["ativou", "♾️"] if player.keep_connected else ["desativou", "❌"]

        text = [
            f"{msg[0]} o modo 24/7 (interrupto) do player.",
            f"{msg[1]} **⠂{inter.author.mention} {msg[0]} o modo 24/7 (interrupto) do player.**"
        ]

        if not len(player.queue):
            player.queue.extend(player.played)
            player.played.clear()

        await player.process_save_queue()

        if player.current:
            await self.interaction_message(inter, txt=text, emoji=msg[1])
            return

        await self.interaction_message(inter, text)

        await player.process_next()

    autoplay_cd = commands.CooldownMapping.from_cooldown(2, 15, commands.BucketType.member)
    autoplay_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @has_player()
    @check_voice()
    @pool_command(name="autoplay", aliases=["ap", "aplay"], only_voiced=True, cooldown=autoplay_cd, max_concurrency=autoplay_mc,
                  description="Ativar/Desativar a reprodução automática ao acabar as músicas da fila.")
    async def autoplay_legacy(self, ctx: CustomContext):
        await self.autoplay.callback(self=self, inter=ctx)

    @has_player()
    @check_voice()
    @commands.slash_command(
        name="autoplay",
        description=f"{desc_prefix}Ativar/Desativar a reprodução automática ao acabar as músicas da fila.",
        extras={"only_voiced": True}, cooldown=autoplay_cd, max_concurrency=autoplay_mc
    )
    async def autoplay(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        player.autoplay = not player.autoplay

        msg = ["ativou", "🔄"] if player.autoplay else ["desativou", "❌"]

        text = [f"{msg[0]} a reprodução automática.",
                f"{msg[1]} **⠂{inter.author.mention} {msg[0]} a reprodução automática.**"]

        if player.current:
            await self.interaction_message(inter, txt=text, emoji=msg[1])
            return

        await self.interaction_message(inter, text)

        await player.process_next()

    @check_voice()
    @has_player()
    @is_dj()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Migrar o player para outro servidor de música."
    )
    async def change_node(
            self,
            inter: disnake.AppCmdInter,
            node: str = commands.Param(name="servidor", description="Servidor de música")
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        if node not in bot.music.nodes:
            raise GenericError(f"O servidor de música **{node}** não foi encontrado.")

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if node == player.node.identifier:
            raise GenericError(f"O player já está no servidor de música **{node}**.")

        await player.change_node(node)

        await self.interaction_message(
            inter,
            [f"Migrou o player para o servidor de música **{node}**",
             f"**O player foi migrado para o servidor de música:** `{node}`"],
            emoji="🌎"
        )

    @search.autocomplete("server")
    @play.autocomplete("server")
    @change_node.autocomplete("servidor")
    async def node_suggestions(self, inter: disnake.Interaction, query: str):

        try:
            await check_pool_bots(inter)
            bot = inter.music_bot
        except GenericError:
            return
        except:
            bot = inter.bot

        try:
            node = bot.music.players[inter.guild_id].node
        except KeyError:
            node = None

        if not query:
            return [n.identifier for n in bot.music.nodes.values() if
                    n != node and n.available and n.is_available]

        return [n.identifier for n in bot.music.nodes.values() if n != node
                and query.lower() in n.identifier.lower() and n.available and n.is_available]

    @commands.command(aliases=["puptime"], description="Ver informações de tempo que o player está ativo no servidor.")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def playeruptime(self, ctx: CustomContext):

        uptime_info = []
        for bot in self.bot.pool.bots:
            try:
                player = bot.music.players[ctx.guild.id]
                uptime_info.append(f"**Bot:** {bot.user.mention}\n"
                            f"**Uptime:** <t:{player.uptime}:R>\n"
                            f"**Canal:** {player.guild.me.voice.channel.mention}")
            except KeyError:
                continue

        if not uptime_info:
            raise GenericError("**Não há players ativos no servidor.**")

        await ctx.reply(
            embed=disnake.Embed(
                title="**Player Uptime:**",
                description="\n-----\n".join(uptime_info),
                color=self.bot.get_color(ctx.guild.me)
            )
        )

    @commands.Cog.listener("on_message_delete")
    async def player_message_delete(self, message: disnake.Message):

        if not message.guild:
            return

        try:

            player: LavalinkPlayer = self.bot.music.players[message.guild.id]

            if message.id != player.message.id:
                return

        except (AttributeError, KeyError):
            return

        thread = self.bot.get_channel(message.id)

        if not thread:
            return

        player.message = None
        await thread.edit(archived=True, locked=True, name=f"arquivado: {thread.name}")

    @commands.Cog.listener('on_ready')
    async def resume_players_ready(self):

        for guild_id in list(self.bot.music.players):

            try:

                player: LavalinkPlayer = self.bot.music.players[guild_id]

                try:
                    channel_id = player.guild.me.voice.channel.id
                except AttributeError:
                    channel_id = player.channel_id

                vc = self.bot.get_channel(channel_id) or player.last_channel

                try:
                    player.guild.voice_client.cleanup()
                except:
                    pass

                if not vc:
                    print(
                        f"{self.bot.user} - {player.guild.name} [{guild_id}] - Player finalizado por falta de canal de voz")
                    try:
                        await player.destroy()
                    except:
                        traceback.print_exc()
                    continue

                await player.connect(vc.id)

                if not player.is_paused and not player.is_playing:
                    await player.process_next()
                print(f"{self.bot.user} - {player.guild.name} [{guild_id}] - Player Reconectado no canal de voz")
            except:
                traceback.print_exc()

    async def is_request_channel(self, ctx: Union[disnake.AppCmdInter, disnake.MessageInteraction, CustomContext], *,
                                 data: dict = None, ignore_thread=False) -> bool:

        if isinstance(ctx, (CustomContext, disnake.MessageInteraction)):
            return True

        try:
            bot = ctx.music_bot
            channel_ctx = bot.get_channel(ctx.channel_id)
        except AttributeError:
            bot = ctx.bot
            channel_ctx = ctx.channel

        if not self.bot.check_bot_forum_post(channel_ctx):
            return True

        try:
            player: LavalinkPlayer = bot.music.players[ctx.guild_id]

            if not player.static:
                return False

            if isinstance(channel_ctx, disnake.Thread) and player.text_channel == channel_ctx.parent:
                return not ignore_thread

            return player.text_channel == channel_ctx

        except KeyError:

            try:
                guild_data = ctx.guild_data
            except AttributeError:
                guild_data = data or await bot.get_data(ctx.guild_id, db_name=DBModel.guilds)

            try:
                channel = bot.get_channel(int(guild_data["player_controller"]["channel"]))
            except:
                channel = None

            if not channel:
                return False

            if isinstance(channel_ctx, disnake.Thread) and channel == channel_ctx.parent:
                return not ignore_thread

            return channel.id == channel_ctx.id

    async def check_channel(
            self,
            guild_data: dict,
            inter: Union[disnake.AppCmdInter, CustomContext],
            channel: Union[disnake.TextChannel, disnake.VoiceChannel, disnake.Thread],
            guild: disnake.Guild,
            bot: BotCore
    ):

        static_player = guild_data['player_controller']

        warn_message = None

        try:
            channel_db = bot.get_channel(int(static_player['channel'])) or await bot.fetch_channel(
                int(static_player['channel']))
        except (TypeError, disnake.NotFound):
            channel_db = None
        except disnake.Forbidden:
            channel_db = bot.get_channel(inter.channel_id)
            warn_message = f"Não tenho permissão de acessar o canal <#{static_player['channel']}>, o player será usado no modo tradicional."
            static_player["channel"] = None

        if not channel_db or channel_db.guild.id != inter.guild_id:
            await self.reset_controller_db(inter.guild_id, guild_data, inter)

        else:

            if channel_db.id != channel.id:

                try:
                    if isinstance(channel_db, disnake.Thread):

                        if not channel_db.parent:
                            await self.reset_controller_db(inter.guild_id, guild_data, inter)
                            channel_db = None

                        else:
                            if (channel_db.archived or channel_db.locked) and not channel_db.parent.permissions_for(guild.me).manage_threads:

                                if isinstance(channel.parent, disnake.ForumChannel):
                                    warn_message = f"**{bot.user.mention} não possui permissão de gerenciar tópicos " \
                                                    f"para desarquivar/destrancar o tópico: {channel_db.mention}**"

                            else:
                                await channel_db.edit(archived=False, locked=False)

                except AttributeError:
                    pass

                if channel_db:

                    channel_db_perms = channel_db.permissions_for(guild.me)

                    if not channel_db_perms.send_messages:
                        raise GenericError(
                            f"**{bot.user.mention} não possui permissão para enviar mensagens no canal <#{static_player['channel']}>**\n"
                            "Caso queira resetar a configuração do canal de pedir música, use o comando /reset ou /setup "
                            "novamente..."
                        )

                    if not channel_db_perms.embed_links:
                        raise GenericError(
                            f"**{bot.user.mention} não possui permissão para anexar links/embeds no canal <#{static_player['channel']}>**\n"
                            "Caso queira resetar a configuração do canal de pedir música, use o comando /reset ou /setup "
                            "novamente..."
                        )

        return channel_db, warn_message

    async def process_player_interaction(
            self,
            interaction: Union[disnake.MessageInteraction, disnake.ModalInteraction],
            command: Optional[disnake.AppCmdInter],
            kwargs: dict
    ):

        if not command:
            raise GenericError("comando não encontrado/implementado.")

        await check_cmd(command, interaction)

        await command(interaction, **kwargs)

        try:
            player: LavalinkPlayer = self.bot.music.players[interaction.guild_id]
            player.interaction_cooldown = True
            await asyncio.sleep(1)
            player.interaction_cooldown = False
            await command._max_concurrency.release(interaction)
        except (KeyError, AttributeError):
            pass

    @commands.Cog.listener("on_dropdown")
    async def guild_pin(self, interaction: disnake.MessageInteraction):

        if not self.bot.bot_ready:
            await interaction.send("Ainda estou inicializando...\nPor favor aguarde mais um pouco...", ephemeral=True)
            return

        if interaction.data.custom_id != "player_guild_pin":
            return

        if not interaction.data.values:
            await interaction.response.defer()
            return

        if not interaction.user.voice:
            await interaction.send("Você deve entrar em um canal de voz para usar isto.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            guild_data = interaction.guild_data
        except AttributeError:
            guild_data = await self.bot.get_data(interaction.guild_id, db_name=DBModel.guilds)
            interaction.guild_data = guild_data

        try:
            query = guild_data["player_controller"]["fav_links"][interaction.data.values[0]]['url']
        except KeyError:
            await interaction.send("**O item selecionado não foi encontrado na base de dados...**", ephemeral=True)
            await send_idle_embed(interaction.message, bot=self.bot, guild_data=guild_data, force=True)
            return

        kwargs = {
            "query": f"> pin: {query}",
            "position": 0,
            "options": False,
            "manual_selection": True,
            "source": "ytsearch",
            "repeat_amount": 0,
            "server": None,
            "force_play": "no"
        }

        try:
            await self.play.callback(self=self, inter=interaction, **kwargs)
        except Exception as e:
            self.bot.dispatch('interaction_player_error', interaction, e)

    @commands.Cog.listener("on_dropdown")
    async def player_dropdown_event(self, interaction: disnake.MessageInteraction):

        if not interaction.data.custom_id.startswith("musicplayer_dropdown_"):
            return

        if not interaction.values:
            await interaction.response.defer()
            return

        await self.player_controller(interaction, interaction.values[0])

    @commands.Cog.listener("on_button_click")
    async def player_button_event(self, interaction: disnake.MessageInteraction):

        if not interaction.data.custom_id.startswith("musicplayer_"):
            return

        await self.player_controller(interaction, interaction.data.custom_id)

    async def player_controller(self, interaction: disnake.MessageInteraction, control: str, **kwargs):

        if not self.bot.bot_ready:
            await interaction.send("Ainda estou inicializando...", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.response.edit_message(components=None)
            return

        cmd_kwargs = {}

        cmd: Optional[disnake.AppCmdInter] = None

        try:

            if control == "musicplayer_request_channel":
                cmd = self.bot.get_slash_command("setup")
                cmd_kwargs = {"target": interaction.channel}
                await self.process_player_interaction(interaction, cmd, cmd_kwargs)
                return

            if control == PlayerControls.fav_manageer:

                if str(interaction.user.id) not in interaction.message.content:
                    await interaction.send("Você não pode interagir aqui!", ephemeral=True)
                    return

                cmd = self.bot.get_slash_command("fav").children.get("manager")
                await self.process_player_interaction(interaction, cmd, cmd_kwargs)
                return

            if control == PlayerControls.integration_manager:

                if str(interaction.user.id) not in interaction.message.content:
                    await interaction.send("Você não pode interagir aqui!", ephemeral=True)
                    return

                cmd = self.bot.get_slash_command("integration").children.get("manager")
                await self.process_player_interaction(interaction, cmd, cmd_kwargs)
                return

            if control == PlayerControls.add_song:

                if not interaction.user.voice:
                    raise GenericError("**Você deve entrar em um canal de voz para usar esse botão.**")

                await interaction.response.send_modal(
                    title="Pedir uma música",
                    custom_id=f"modal_add_song" + (f"_{interaction.message.id}" if interaction.message.thread else ""),
                    components=[
                        disnake.ui.TextInput(
                            style=disnake.TextInputStyle.short,
                            label="Nome/link da música.",
                            placeholder="Nome ou link do youtube/spotify/soundcloud etc.",
                            custom_id="song_input",
                            max_length=150,
                            required=True
                        ),
                        disnake.ui.TextInput(
                            style=disnake.TextInputStyle.short,
                            label="Posição da fila (número).",
                            placeholder="Opcional, caso não seja usado será adicionada no final.",
                            custom_id="song_position",
                            max_length=3,
                            required=False
                        ),
                    ]
                )

                return

            if control == PlayerControls.enqueue_fav:

                cmd_kwargs = {
                    "query": kwargs.get("query", ""),
                    "position": 0,
                    "options": False,
                    "source": "ytsearch",
                    "repeat_amount": 0,
                    "server": None,
                    "force_play": "no"
                }

                cmd_kwargs["manual_selection"] = not cmd_kwargs["query"]

                cmd = self.bot.get_slash_command("play")

            else:

                try:
                    player: LavalinkPlayer = self.bot.music.players[interaction.guild_id]
                except KeyError:
                    await interaction.send("Não há player ativo no servidor...", ephemeral=True)
                    await send_idle_embed(interaction.message, bot=self.bot)
                    return

                if interaction.message != player.message:
                    return

                if player.interaction_cooldown:
                    raise GenericError("O player está em cooldown, tente novamente em instantes.")

                try:
                    vc = player.guild.me.voice.channel
                except AttributeError:
                    self.bot.loop.create_task(player.destroy(force=True))
                    return

                if control == PlayerControls.help_button:
                    embed = disnake.Embed(
                        description="📘 **IFORMAÇÕES SOBRE OS BOTÕES** 📘\n\n"
                                    "⏯️ `= Pausar/Retomar a música.`\n"
                                    "⏮️ `= Voltar para a música tocada anteriormente.`\n"
                                    "⏭️ `= Pular para a próxima música.`\n"
                                    "🔀 `= Misturar as músicas da fila.`\n"
                                    "🎶 `= Adicionar música/playlist/favorito.`\n"
                                    "⏹️ `= Parar o player e me desconectar do canal.`\n"
                                    "📑 `= Exibir a fila de música.`\n"
                                    "🛠️ `= Alterar algumas configurações do player:`\n"
                                    "`volume / efeito nightcore / repetição / modo restrito.`\n",
                        color=self.bot.get_color(interaction.guild.me)
                    )

                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                if not interaction.author.voice or interaction.author.voice.channel != vc:
                    raise GenericError(f"Você deve estar no canal <#{vc.id}> para usar os botões do player.")

                if control == PlayerControls.miniqueue:
                    await is_dj().predicate(interaction)
                    player.mini_queue_enabled = not player.mini_queue_enabled
                    player.set_command_log(
                        emoji="📑",
                        text=f"{interaction.author.mention} {'ativou' if player.mini_queue_enabled else 'desativou'} "
                             f"a mini-fila do player."
                    )
                    await player.invoke_np(interaction=interaction)
                    return

                try:
                    await self.player_interaction_concurrency.acquire(interaction)
                except commands.MaxConcurrencyReached:
                    raise GenericError(
                        "**Você tem uma interação em aberto!**\n`Se for uma mensagem oculta, evite clicar em \"ignorar\".`")

                if control == PlayerControls.add_favorite:

                    choices = {}
                    msg = ""

                    if player.current.uri:
                        choices["Track"] = {
                            "name": player.current.title,
                            "url": player.current.uri,
                            "emoji": "🎵"
                        }
                        msg += f"**Música:** [`{player.current.title}`]({player.current.uri})\n"

                    if player.current.album_url:
                        choices["Album"] = {
                            "name": player.current.album_name,
                            "url": player.current.album_url,
                            "emoji": "💽"
                        }
                        msg += f"**Album:** [`{player.current.album_name}`]({player.current.album_url})\n"

                    if player.current.playlist_url:
                        choices["Playlist"] = {
                            "name": player.current.playlist_name,
                            "url": player.current.playlist_url,
                            "emoji": "<:music_queue:703761160679194734>"
                        }
                        msg += f"**Playlist:** [`{player.current.playlist_name}`]({player.current.playlist_url})\n"

                    if not choices:
                        try:
                            await self.player_interaction_concurrency.release(interaction)
                        except:
                            pass
                        await interaction.send(
                            embed=disnake.Embed(
                                color=self.bot.get_color(interaction.guild.me),
                                description="### Não há itens para favoritar na música atual."
                            ), ephemeral=True
                        )
                        return

                    if len(choices) == 1:
                        select_type, info = list(choices.items())[0]

                    else:
                        view = SelectInteraction(
                            user=interaction.author, timeout=30,
                            opts=[disnake.SelectOption(label=k, description=v["name"][:50], emoji=v["emoji"]) for k,v in choices.items()]
                        )

                        await interaction.send(
                            embed=disnake.Embed(
                                color=self.bot.get_color(interaction.guild.me),
                                description=f"### Selecione um item da música atual para adicionar nos seus favoritos:"
                                            f"\n\n{msg}"
                            ), view=view, ephemeral=True
                        )

                        await view.wait()

                        select_interaction = view.inter

                        if not select_interaction or view.selected is False:
                            try:
                                await self.player_interaction_concurrency.release(interaction)
                            except:
                                pass
                            await interaction.edit_original_message(
                                embed=disnake.Embed(
                                    color=self.bot.get_color(interaction.guild.me),
                                    description="### Operação cancelada!"
                                ), view=None
                            )
                            return

                        interaction = select_interaction

                        select_type = view.selected
                        info = choices[select_type]

                    await interaction.response.defer()

                    user_data = await self.bot.get_global_data(interaction.author.id, db_name=DBModel.users)

                    if self.bot.config["MAX_USER_FAVS"] > 0 and not (await self.bot.is_owner(interaction.author)):

                        if len(user_data["fav_links"]) >= self.bot.config["MAX_USER_FAVS"]:
                            await interaction.response.edit_message(
                                embed=disnake.Embed(
                                    color=self.bot.get_color(interaction.guild.me),
                                    description="Você não possui espaço suficiente para adicionar todos os favoritos de seu arquivo...\n"
                                                f"Limite atual: {self.bot.config['MAX_USER_FAVS']}"
                                ), view=None)
                            return

                    user_data["fav_links"][fix_characters(info["name"], self.bot.config["USER_FAV_MAX_URL_LENGTH"])] = info["url"]

                    await self.bot.update_global_data(interaction.author.id, user_data, db_name=DBModel.users)

                    global_data = await self.bot.get_global_data(interaction.author.id, db_name=DBModel.guilds)

                    slashcmd = f"</play:" + str(self.bot.pool.controller_bot.get_global_command_named("play", cmd_type=disnake.ApplicationCommandType.chat_input).id) + ">"

                    await interaction.edit_original_response(
                        embed=disnake.Embed(
                            color=self.bot.get_color(interaction.guild.me),
                            description="### Item adicionado/editado com sucesso nos seus favoritos:\n\n"
                                        f"**{select_type}:** [`{info['name']}`]({info['url']})\n\n"
                                        f"### Como usar?\n"
                                        f"* Usando o comando {slashcmd} (no preenchimento automático da busca)\n"
                                        f"* Clicando no botão/select de tocar favorito/integração do player.\n"
                                        f"* Usando o comando {global_data['prefix'] or self.bot.default_prefix}{self.play_legacy.name} sem incluir um nome ou link de uma música/vídeo."
                        ), view=None
                    )

                    try:
                        await self.player_interaction_concurrency.release(interaction)
                    except:
                        pass

                    return

                if control == PlayerControls.volume:
                    cmd_kwargs = {"value": None}

                elif control == PlayerControls.queue:
                    cmd = self.bot.get_slash_command("queue").children.get("display")

                elif control == PlayerControls.shuffle:
                    cmd = self.bot.get_slash_command("queue").children.get("shuffle")

                elif control == PlayerControls.seek_to_start:
                    cmd = self.bot.get_slash_command("seek")
                    cmd_kwargs = {"position": "0"}

                elif control == PlayerControls.pause_resume:
                    control = PlayerControls.pause if not player.paused else PlayerControls.resume

                elif control == PlayerControls.loop_mode:

                    if player.loop == "current":
                        cmd_kwargs['mode'] = 'queue'
                    elif player.loop == "queue":
                        cmd_kwargs['mode'] = 'off'
                    else:
                        cmd_kwargs['mode'] = 'current'

                elif control == PlayerControls.skip:
                    cmd_kwargs = {"query": None, "play_only": "no"}

            if not cmd:
                cmd = self.bot.get_slash_command(control[12:])

            await self.process_player_interaction(
                interaction=interaction,
                command=cmd,
                kwargs=cmd_kwargs
            )

            try:
                await self.player_interaction_concurrency.release(interaction)
            except:
                pass

        except Exception as e:
            try:
                await self.player_interaction_concurrency.release(interaction)
            except:
                pass
            self.bot.dispatch('interaction_player_error', interaction, e)

    @commands.Cog.listener("on_modal_submit")
    async def song_request_modal(self, inter: disnake.ModalInteraction):

        if inter.custom_id.startswith("modal_add_song"):

            try:

                query = inter.text_values["song_input"]
                position = inter.text_values["song_position"]

                if position:
                    if not position.isdigit():
                        raise GenericError("**A posição da fila tem que ser um número.**")
                    position = int(position)

                    if position < 1:
                        raise GenericError("**Número da posição da fila tem que ser 1 ou superior.**")

                kwargs = {
                    "query": query,
                    "position": position or 0,
                    "options": False,
                    "manual_selection": True,
                    "source": "ytsearch",
                    "repeat_amount": 0,
                    "server": None,
                    "force_play": "no",
                }

                await self.process_player_interaction(
                    interaction=inter,
                    command=self.bot.get_slash_command("play"),
                    kwargs=kwargs,
                )
            except Exception as e:
                self.bot.dispatch('interaction_player_error', inter, e)

    async def delete_message(self, message: disnake.Message, delay: int = None, ignore=False):

        if ignore:
            return

        try:
            is_forum = isinstance(message.channel.parent, disnake.ForumChannel)
        except AttributeError:
            is_forum = False

        if message.is_system() and is_forum:
            return

        if message.channel.permissions_for(message.guild.me).manage_messages:

            try:
                await message.delete(delay=delay)
            except:
                traceback.print_exc()

    @commands.Cog.listener("on_song_request")
    async def song_requests(self, ctx: Optional[CustomContext], message: disnake.Message):

        if ctx.command or message.mentions:
            return

        if message.author.bot and not isinstance(message.channel, disnake.StageChannel):
            return

        try:
            data = await self.bot.get_data(message.guild.id, db_name=DBModel.guilds)
        except AttributeError:
            return

        player: Optional[LavalinkPlayer] = self.bot.music.players.get(message.guild.id)

        if player and isinstance(message.channel, disnake.Thread) and not player.static:

            if player.message.id != message.channel.id:
                return

            if not player.controller_mode:
                return

            text_channel = message.channel

        else:

            static_player = data['player_controller']

            channel_id = static_player['channel']

            if not channel_id or (
                    static_player['message_id'] != str(message.channel.id) and str(message.channel.id) != channel_id):
                return

            text_channel = self.bot.get_channel(int(channel_id))

            if not text_channel or not text_channel.permissions_for(message.guild.me).send_messages:
                return

            if not self.bot.intents.message_content:

                if self.song_request_cooldown.get_bucket(message).update_rate_limit():
                    return

                await message.channel.send(
                    message.author.mention,
                    embed=disnake.Embed(
                        description="Infelizmente não posso conferir o conteúdo de sua mensagem...\n"
                                    "Tente adicionar música usando **/play** ou clique em um dos botões abaixo:",
                        color=self.bot.get_color(message.guild.me)
                    ),
                    components=song_request_buttons, delete_after=20
                )
                return

        if message.content.startswith("/") or message.is_system():
            await self.delete_message(message)
            return

        try:
            if isinstance(message.channel, disnake.Thread):

                if isinstance(message.channel.parent, disnake.ForumChannel):

                    if data['player_controller']["channel"] != str(message.channel.id):
                        return
                    if message.is_system():
                        await self.delete_message(message, ignore=data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)

        except AttributeError:
            pass

        msg = None
        error = None
        has_exception = None

        try:
            if message.author.bot:
                if message.is_system() and not isinstance(message.channel, disnake.Thread):
                    await self.delete_message(message, ignore=data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)
                if message.author.id == self.bot.user.id:
                    await self.delete_message(message, delay=15, ignore=data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)
                return

            if not message.content:

                if message.type == disnake.MessageType.thread_starter_message:
                    return

                if message.is_system():
                    await self.delete_message(message)
                    return

                try:
                    attachment = message.attachments[0]
                except IndexError:
                    await message.channel.send(f"{message.author.mention} você deve enviar um link/nome da música.")
                    return

                else:

                    if attachment.size > 18000000:
                        await message.channel.send(f"{message.author.mention} o arquivo que você enviou deve ter o tamanho "
                                                   f"inferior a 18mb.")
                        return

                    if attachment.content_type not in self.audio_formats:
                        await message.channel.send(f"{message.author.mention} o arquivo que você enviou deve ter o tamanho "
                                                   f"inferior a 18mb.")
                        return

                    message.content = attachment.url

            try:
                await self.song_request_concurrency.acquire(message)
            except:

                await message.channel.send(
                    f"{message.author.mention} você deve aguardar seu pedido de música anterior carregar...",
                )

                await self.delete_message(message, ignore=data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)
                return

            message.content = message.content.strip("<>")

            urls = URL_REG.findall(message.content)

            if not urls:
                message.content = f"ytsearch:{message.content}"

            else:
                message.content = urls[0]

                if "&list=" in message.content:

                    view = SelectInteraction(
                        user=message.author,
                        opts=[
                            disnake.SelectOption(label="Música", emoji="🎵",
                                                 description="Carregar apenas a música do link.", value="music"),
                            disnake.SelectOption(label="Playlist", emoji="🎶",
                                                 description="Carregar playlist com a música atual.", value="playlist"),
                        ], timeout=30)

                    embed = disnake.Embed(
                        description="**O link contém vídeo com playlist.**\n"
                                    f'Selecione uma opção em até <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=30)).timestamp())}:R> para prosseguir.',
                        color=self.bot.get_color(message.guild.me)
                    )

                    msg = await message.channel.send(message.author.mention, embed=embed, view=view)

                    await view.wait()

                    try:
                        await view.inter.response.defer()
                    except:
                        pass

                    if view.selected == "music":
                        message.content = YOUTUBE_VIDEO_REG.match(message.content).group()

            await self.parse_song_request(message, text_channel, data, response=msg)

        except GenericError as e:
            error = f"{message.author.mention}. {e}"

        except Exception as e:
            traceback.print_exc()
            has_exception = e
            error = f"{message.author.mention} **ocorreu um erro ao tentar obter resultados para sua busca:** ```py\n{e}```"

        if error:

            await self.delete_message(message, ignore=data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)

            try:
                if msg:
                    await msg.edit(content=error, embed=None, view=None)
                else:
                    await message.channel.send(error)
            except:
                traceback.print_exc()

        await self.song_request_concurrency.release(message)

        if has_exception and self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"]:

            cog = self.bot.get_cog("ErrorHandler")

            if not cog:
                return

            max_concurrency = cog.webhook_max_concurrency

            await max_concurrency.acquire(message)

            try:
                error_msg, full_error_msg, kill_process = parse_error(message, has_exception)

                embed = disnake.Embed(
                    title="Ocorreu um erro em um servidor (song-request):",
                    timestamp=disnake.utils.utcnow(),
                    description=f"```py\n{repr(has_exception)[:2030].replace(self.bot.http.token, 'mytoken')}```"
                )

                embed.set_footer(
                    text=f"{message.author} [{message.author.id}]",
                    icon_url=message.author.display_avatar.with_static_format("png").url
                )

                embed.add_field(
                    name="Servidor:", inline=False,
                    value=f"```\n{disnake.utils.escape_markdown(ctx.guild.name)}\nID: {ctx.guild.id}```"
                )

                embed.add_field(
                    name="Conteúdo do pedido de música:", inline=False,
                    value=f"```\n{message.content}```"
                )

                embed.add_field(
                    name="Canal de texto:", inline=False,
                    value=f"```\n{disnake.utils.escape_markdown(ctx.channel.name)}\nID: {ctx.channel.id}```"
                )

                if vc := ctx.author.voice:
                    embed.add_field(
                        name="Canal de voz (user):", inline=False,
                        value=f"```\n{disnake.utils.escape_markdown(vc.channel.name)}" +
                              (f" ({len(vc.channel.voice_states)}/{vc.channel.user_limit})"
                               if vc.channel.user_limit else "") + f"\nID: {vc.channel.id}```"
                    )

                if vcbot := ctx.guild.me.voice:
                    if vcbot.channel != vc.channel:
                        embed.add_field(
                            name="Canal de voz (bot):", inline=False,
                            value=f"{vc.channel.name}" +
                                  (f" ({len(vc.channel.voice_states)}/{vc.channel.user_limit})"
                                   if vc.channel.user_limit else "") + f"\nID: {vc.channel.id}```"
                        )

                if ctx.guild.icon:
                    embed.set_thumbnail(url=ctx.guild.icon.with_static_format("png").url)

                await cog.send_webhook(
                    embed=embed,
                    file=string_to_file(full_error_msg, "error_traceback_songrequest.txt")
                )

            except:
                traceback.print_exc()

            await asyncio.sleep(20)

            try:
                await max_concurrency.release(message)
            except:
                pass


    async def parse_song_request(self, message: disnake.Message, text_channel, data, *, response=None, attachment: disnake.Attachment=None):

        if not message.author.voice:
            raise GenericError("Você deve entrar em um canal de voz para pedir uma música.")

        can_connect(
            channel=message.author.voice.channel,
            guild=message.guild,
            check_other_bots_in_vc=data["check_other_bots_in_vc"],
            bot=self.bot
        )

        try:
            if message.guild.me.voice.channel != message.author.voice.channel:
                raise GenericError(
                    f"Você deve entrar no canal <#{message.guild.me.voice.channel.id}> para pedir uma música.")
        except AttributeError:
            pass

        tracks, node = await self.get_tracks(message.content, message.author)

        try:
            message_id = int(data['player_controller']['message_id'])
        except TypeError:
            message_id = None

        try:
            player = self.bot.music.players[message.guild.id]
            destroy_message = True
        except KeyError:
            destroy_message = False
            skin = data["player_controller"]["skin"]
            static_skin = data["player_controller"]["static_skin"]

            global_data = await self.bot.get_global_data(message.guild.id, db_name=DBModel.guilds)

            if global_data["global_skin"]:
                skin = global_data["player_skin"] or skin
                static_skin = global_data["player_skin_static"] or static_skin

            try:
                invite = global_data["listen_along_invites"][str(message.author.voice.channel.id)]
            except (KeyError, AttributeError):
                invite = None

            else:
                try :
                    invite = (await self.bot.fetch_invite(invite)).url
                except disnake.NotFound:
                    print(
                        f'{"-"*15}\n'
                        f'Removendo invite: {invite} \n'
                        f'Servidor: {message.guild.name} [{message.guild.id}]\n'
                        f'Canal: {message.channel.name} [{message.channel.id}]\n'
                        f'{"-" * 15}'
                    )
                    invite = None
                    del global_data["listen_along_invites"][str(message.author.voice.channel.id)]
                    await self.bot.update_global_data(message.guild.id, global_data, db_name=DBModel.guilds)

            player: LavalinkPlayer = self.bot.music.get_player(
                guild_id=message.guild.id,
                cls=LavalinkPlayer,
                player_creator=message.author.id,
                guild=message.guild,
                channel=text_channel,
                static=True,
                skin=self.bot.check_skin(skin),
                skin_static=self.bot.check_static_skin(static_skin),
                custom_skin_data=global_data["custom_skins"],
                custom_skin_static_data=global_data["custom_skins_static"],
                node_id=node.identifier,
                extra_hints=self.extra_hints,
                last_message_id=message_id,
                restrict_mode=data['enable_restrict_mode'],
                listen_along_invite=invite,
                volume=int(data['default_player_volume']),
                autoplay=data["autoplay"],
                prefix=global_data["prefix"] or self.bot.default_prefix,
                purge_mode=data['player_controller']['purge_mode']
            )

        if not player.message:
            try:
                cached_message = await text_channel.fetch_message(message_id)
            except:
                cached_message = await send_idle_embed(message, bot=self.bot, guild_data=data)
                data['player_controller']['message_id'] = str(cached_message.id)
                await self.bot.update_data(message.guild.id, data, db_name=DBModel.guilds)

            player.message = cached_message

        embed = disnake.Embed(color=self.bot.get_color(message.guild.me))

        try:
            components = [disnake.ui.Button(emoji="🎛️", label="Ir para o player-controller", url=player.message.jump_url)]
        except AttributeError:
            components = []

        if not isinstance(tracks, list):
            player.queue.extend(tracks.tracks)
            if (isinstance(message.channel, disnake.Thread) and
                    (not isinstance(message.channel.parent, disnake.ForumChannel) or
                     data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)):
                embed.description = f"✋ **⠂ Pedido por:** {message.author.mention}\n" \
                                    f"🎼 **⠂ Música(s):** `[{len(tracks.tracks)}]`"
                embed.set_thumbnail(url=tracks.tracks[0].thumb)
                embed.set_author(name="⠂" + fix_characters(tracks.tracks[0].playlist_name, 35), url=message.content,
                                 icon_url=music_source_image(tracks.tracks[0].info["sourceName"]))

                try:
                    embed.description += f"\n🔊 **⠂ Canal de voz:** {message.author.voice.channel.mention}"
                except AttributeError:
                    pass

                if response:
                    await response.edit(content=None, embed=embed, components=components)
                else:
                    await message.reply(embed=embed, fail_if_not_exists=False, mention_author=False)

            elif data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message:

                txt = f"> 🎼 **⠂** [`{fix_characters(tracks.tracks[0].playlist_name, 35)}`](<{message.content}>) `[{len(tracks.tracks)} música(s)]` {message.author.mention}"

                try:
                    txt += f" `|` {message.author.voice.channel.mention}"
                except AttributeError:
                    pass

                if response:
                    await response.edit(content=txt, embed=None, components=components)
                else:
                    await message.reply(txt, components=components, allowed_mentions=disnake.AllowedMentions(users=False, everyone=False, roles=False), fail_if_not_exists=False, mention_author=False)

            else:
                player.set_command_log(
                    text=f"{message.author.mention} adicionou a playlist [`{fix_characters(tracks.data['playlistInfo']['name'], 20)}`]"
                         f"({tracks.tracks[0].playlist_url}) `({len(tracks.tracks)})`.",
                    emoji="🎶"
                )
                if destroy_message:
                    await self.delete_message(message)

        else:
            track = tracks[0]

            if track.info.get("sourceName") == "http":

                if track.title == "Unknown title":
                    if attachment:
                        track.info["title"] = attachment.filename
                    else:
                        track.info["title"] = track.uri.split("/")[-1]
                    track.title = track.info["title"]

                track.uri = ""

            player.queue.append(track)
            if (isinstance(message.channel, disnake.Thread) and
                    (not isinstance(message.channel.parent, disnake.ForumChannel) or
                     data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)):
                embed.description = f"💠 **⠂ Uploader:** `{track.author}`\n" \
                                    f"✋ **⠂ Pedido por:** {message.author.mention}\n" \
                                    f"⏰ **⠂ Duração:** `{time_format(track.duration) if not track.is_stream else '🔴 Livestream'}`"

                try:
                    embed.description += f"\n🔊 **⠂ Canal de voz:** {message.author.voice.channel.mention}"
                except AttributeError:
                    pass

                embed.set_thumbnail(url=track.thumb)
                embed.set_author(name=fix_characters(track.title, 35), url=track.uri or track.search_uri, icon_url=music_source_image(track.info["sourceName"]))
                if response:
                    await response.edit(content=None, embed=embed, components=components)
                else:
                    await message.reply(embed=embed, fail_if_not_exists=False, mention_author=False, components=components)

            elif data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message:

                txt = f"> 🎵 **⠂** [`{fix_characters(track.title, 35)}`](<{track.uri}>) `[{time_format(track.duration) if not track.is_stream else '🔴 Livestream'}]` {message.author.mention}"

                try:
                    txt += f" `|` {message.author.voice.channel.mention}"
                except AttributeError:
                    pass

                if response:
                    await response.edit(content=txt, embed=None, components=components)
                else:
                    await message.reply(txt, components=components, allowed_mentions=disnake.AllowedMentions(users=False, everyone=False, roles=False), fail_if_not_exists=False, mention_author=False)

            else:
                duration = time_format(tracks[0].duration) if not tracks[0].is_stream else '🔴 Livestream'
                player.set_command_log(
                    text=f"{message.author.mention} adicionou [`{fix_characters(tracks[0].title, 20)}`]({tracks[0].uri or tracks[0].search_uri}) `({duration})`.",
                    emoji="🎵"
                )
                if destroy_message:
                    await self.delete_message(message, ignore=data['player_controller']['purge_mode'] != SongRequestPurgeMode.on_message)

        if not player.is_connected:
            await self.do_connect(
                message,
                channel=message.author.voice.channel,
                check_other_bots_in_vc=data["check_other_bots_in_vc"]
            )

        if not player.current:
            await player.process_next()
        else:
            await player.update_message()

        await asyncio.sleep(1)

    async def cog_check(self, ctx: CustomContext) -> bool:

        return await check_requester_channel(ctx)

    def cog_unload(self):
        try:
            self.error_report_task.cancel()
        except:
            pass


    async def interaction_message(self, inter: Union[disnake.Interaction, CustomContext], txt, emoji: str = "✅",
                                  rpc_update: bool = False, data: dict = None, store_embed: bool = False, force=False,
                                  defered=False):

        try:
            txt, txt_ephemeral = txt
        except:
            txt_ephemeral = False

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = inter.guild

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        component_interaction = isinstance(inter, disnake.MessageInteraction)

        ephemeral = await self.is_request_channel(inter, data=data)

        if ephemeral:
            player.set_command_log(text=f"{inter.author.mention} {txt}", emoji=emoji)
            player.update = True

        await player.update_message(interaction=inter if (bot.user.id == self.bot.user.id and component_interaction) \
            else False, rpc_update=rpc_update, force=force)

        if isinstance(inter, CustomContext):
            embed = disnake.Embed(color=self.bot.get_color(guild.me),
                                  description=f"{txt_ephemeral or txt}{player.controller_link}")

            try:
                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
            except AttributeError:
                pass

            if store_embed and not player.controller_mode and len(player.queue) > 0:
                player.temp_embed = embed

            else:
                try:
                    await inter.store_message.edit(embed=embed, view=None, content=None)
                except AttributeError:
                    await inter.send(embed=embed)

        elif not component_interaction:

            if not inter.response.is_done():
                embed = disnake.Embed(
                    color=self.bot.get_color(guild.me),
                    description=(txt_ephemeral or f"{inter.author.mention} **{txt}**") + player.controller_link
                )

                try:
                    if bot.user.id != self.bot.user.id:
                        embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
                except AttributeError:
                    pass

                await inter.send(embed=embed, ephemeral=ephemeral)

            elif defered:
                embed = disnake.Embed(
                    color=self.bot.get_color(guild.me),
                    description=(txt_ephemeral or f"{inter.author.mention} **{txt}**") + player.controller_link
                )

                try:
                    if bot.user.id != self.bot.user.id:
                        embed.set_footer(text=f"Via: {bot.user.display_name}", icon_url=bot.user.display_avatar.url)
                except AttributeError:
                    pass

                await inter.edit_original_response(embed=embed)

    async def process_nodes(self, data: dict, start_local: bool = False):

        await self.bot.wait_until_ready()

        if str(self.bot.user.id) in self.bot.config["INTERACTION_BOTS_CONTROLLER"]:
            return

        for k, v in data.items():
            self.bot.loop.create_task(self.connect_node(v))

        if start_local:
            self.bot.loop.create_task(self.connect_local_lavalink())

    @commands.Cog.listener("on_wavelink_node_connection_closed")
    async def node_connection_closed(self, node: wavelink.Node):

        retries = 0
        backoff = 7

        if not node.restarting:

            print(f"{self.bot.user} - [{node.identifier}] Conexão perdida - reconectando em {int(backoff)} segundos.")

            for player in list(node.players.values()):

                try:
                    player._new_node_task.cancel()
                except:
                    pass

                player._new_node_task = self.bot.loop.create_task(player._wait_for_new_node())

        await asyncio.sleep(backoff)

        while True:

            if retries == 30:
                print(f"{self.bot.user} - [{node.identifier}] Todas as tentativas de reconectar falharam...")
                return

            await self.bot.wait_until_ready()

            try:
                async with self.bot.session.get(node.rest_uri) as r:
                    if r.status in [401, 200, 400]:
                        await node.connect(self.bot)
                        return
                    error = r.status
            except Exception as e:
                error = repr(e)

            backoff *= 1.5
            print(
                f'{self.bot.user} - Falha ao reconectar no servidor [{node.identifier}] nova tentativa em {int(backoff)}'
                f' segundos. Erro: {error}')
            await asyncio.sleep(backoff)
            retries += 1
            continue

    @commands.Cog.listener("on_wavelink_websocket_closed")
    async def node_ws_voice_closed(self, node, payload: wavelink.events.WebsocketClosed):

        if payload.code == 1000:
            return

        player: LavalinkPlayer = payload.player

        if not player.guild.me:
            return

        try:
            vc = player.last_channel or player.guild.me.voice.channel
        except AttributeError:
            vc = None

        if payload.code == 4014 and player.guild.me.voice:
            pass
        else:
            print(
                ("-" * 15) +
                f"\nErro no canal de voz!"
                f"\nBot: {player.bot.user} [{player.bot.user.id}] | " + ("Online" if self.bot.is_ready() else "Offline") +
                f"\nGuild: {player.guild.name} [{player.guild.id}]"
                f"\nCanal: {vc.name} [{vc.id}]"
                f"\nServer: {player.node.identifier} | code: {payload.code} | reason: {payload.reason}\n" +
                ("-" * 15)
            )

        if player.is_closing:
            return

        if payload.code in (
                4000,  # internal error
                1006,
                1001,
                4016,  # Connection started elsewhere
                4005,  # Already authenticated.
                4006,  # Session is no longer valid.
        ):
            try:
                vc_id = player.guild.me.voice.channel.id
            except AttributeError:
                vc_id = player.last_channel.id

            await asyncio.sleep(3)

            if player.is_closing:
                return

            await player.connect(vc_id)
            return

        if payload.code == 4014:

            if player.static:
                player.command_log = "Desliguei o player por perca de conexão com o canal de voz."
                await player.destroy()

            else:
                embed = disnake.Embed(description="**Desliguei o player por perca de conexão com o canal de voz.**",
                                      color=self.bot.get_color(player.guild.me))
                try:
                    self.bot.loop.create_task(player.text_channel.send(embed=embed, delete_after=7))
                except:
                    traceback.print_exc()
                await player.destroy()

            return

    @commands.Cog.listener('on_wavelink_track_exception')
    async def wavelink_track_error(self, node, payload: wavelink.TrackException):
        player: LavalinkPlayer = payload.player
        track = player.last_track
        embed = disnake.Embed(
            description=f"**Falha ao reproduzir música:\n[{track.title}]({track.uri or track.search_uri})** ```java\n{payload.message}```\n"
                        f"**Causa:** ```java\n{payload.cause}```\n"
                        f"**Nível:** `{payload.severity}`\n"
                        f"**Servidor de música:** `{player.node.identifier}`",
            color=disnake.Colour.red())
        await player.text_channel.send(embed=embed, delete_after=10)

        error_format = pprint.pformat(payload.data)

        print(("-" * 50) + f"\nErro ao reproduzir a música: {track.uri or track.search_uri}\n"
              f"Servidor: {player.node.identifier}\n"
              f"{error_format}\n" + ("-" * 50))

        if self.error_report_queue:

            embed.description += f"\n**Servidor:** `{disnake.utils.escape_markdown(player.guild.name)} [{player.guild.id}]`"

            try:
                embed.description += f"\n**Canal:** `{disnake.utils.escape_markdown(player.guild.me.voice.channel.name)} [{player.guild.me.voice.channel.id}]`\n"
            except:
                pass

            embed.description += f"**Data:** <t:{int(disnake.utils.utcnow().timestamp())}:F>"

            if player.guild.icon:
                embed.set_thumbnail(url=player.guild.icon.with_format("png").url)

            await self.error_report_queue.put({"embed": embed})

        if player.locked:
            return

        player.current = None

        if payload.error == "This IP address has been blocked by YouTube (429)" or (payload.cause.startswith("java.lang.RuntimeException: Not success status code: 403") and track.info["sourceName"] == "youtube"):
            player.node.available = False

            try:
                player._new_node_task.cancel()
            except:
                pass
            player._new_node_task = player.bot.loop.create_task(player._wait_for_new_node(f"O servidor **{node.identifier}** tomou ratelimit do youtube está indisponível no momento (aguardando um novo servidor ficar disponível)."))
            return

        if payload.cause.startswith((
                "java.net.SocketTimeoutException: Read timed out",
                "java.net.SocketTimeoutException: connect timed out",
                "java.net.UnknownHostException:",
                "java.lang.IllegalStateException: Current position is beyond this element",
                "javax.script.ScriptEngine.eval(String)",
                "com.sedmelluq.discord.lavaplayer.tools.io.PersistentHttpStream$PersistentHttpException: Not success status code: 403",
        )):
            player.queue.appendleft(track)

        elif payload.cause == "java.lang.InterruptedException":
            player.queue.appendleft(track)

            if player.node.identifier == "LOCAL":
                return
            else:
                try:
                    n = await self.get_best_node()
                except:
                    if player.static:
                        player.set_command_log(text="O player foi desligado por falta de servidores de música...")
                    else:
                        await player.text_channel.send("**O player foi desligado por falta de servidores de música...**")
                    await player.destroy()
                    return
                await player.change_node(n.identifier)

        elif not track.track_loops:
            player.failed_tracks.append(track)

        elif player.keep_connected and not track.autoplay and len(player.queue) > 15:
            player.queue.append(track)

        player.locked = True
        await asyncio.sleep(10)

        try:
            player = player.bot.music.players[player.guild.id]
        except:
            return

        player.locked = False
        await player.process_next()

    @commands.Cog.listener("on_wavelink_node_ready")
    async def node_ready(self, node: wavelink.Node):
        msg = f'{self.bot.user} - Servidor de música: [{node.identifier}] está pronto para uso!'

        if node.restarting:

            print(msg + " Reconectando players...")

            node.restarting = False

            for guild_id in list(node.players):
                try:
                    player = node.players[guild_id]
                    await player.change_node(node.identifier, force=True)
                    player.set_command_log(
                        text="O servidor de música foi reconectado com sucesso!",
                        emoji="🔰"
                    )
                    player.locked = False
                    if player.current:
                        if not player.paused:
                            await player.play(player.current, start=player.position)
                        player.update = True
                    else:
                        await player.process_next()
                except:
                    traceback.print_exc()
                    continue

        else:
            print(msg)

    @commands.Cog.listener('on_wavelink_track_start')
    async def track_start(self, node, payload: wavelink.TrackStart):

        player: LavalinkPlayer = payload.player

        if not player.text_channel.permissions_for(player.guild.me).send_messages:
            try:
                print(f"{player.guild.name} [{player.guild_id}] - Desligando player por falta de permissão para enviar "
                      f"mensagens no canal: {player.text_channel.name} [{player.text_channel.id}]")
            except Exception:
                traceback.print_exc()
            await player.destroy()
            return

        if not player.guild.me.voice:
            try:
                await self.bot.wait_for(
                    "voice_state_update", check=lambda m, b, a: m == player.guild.me and m.voice, timeout=7
                )
            except asyncio.TimeoutError:
                player.update = True
                return

        await player.process_save_queue()

    @commands.Cog.listener("on_wavelink_track_end")
    async def track_end(self, node: wavelink.Node, payload: wavelink.TrackEnd):

        player: LavalinkPlayer = payload.player

        if player.locked:
            return

        if payload.reason == "FINISHED":
            player.set_command_log()

        elif payload.reason == "STOPPED":

            if len(player.queue) == 0:
                return

            player.ignore_np_once = True

        else:
            return

        try:
            player.message_updater_task.cancel()
        except:
            pass

        try:
            player = self.bot.music.players[player.guild.id]
        except:
            return

        await player.track_end()

        player.update = False

        await player.process_next()

    async def connect_node(self, data: dict):

        if data["identifier"] in self.bot.music.nodes:
            node = self.bot.music.nodes[data['identifier']]
            if not node.is_connected:
                await node.connect(self.bot)
            return

        data = deepcopy(data)

        data['rest_uri'] = ("https" if data.get('secure') else "http") + f"://{data['host']}:{data['port']}"
        data['user_agent'] = self.bot.pool.current_useragent
        search = data.pop("search", True)
        node_website = data.pop('website', '')
        region = data.pop('region', 'us_central')
        heartbeat = int(data.pop('heartbeat', 30))

        try:
            max_retries = int(data.pop('retries'))
        except (TypeError, KeyError):
            max_retries = 0

        if max_retries:

            backoff = 9
            retries = 1

            print(f"{self.bot.user} - Iniciando servidor de música: {data['identifier']}")

            while not self.bot.is_closed():
                if retries >= max_retries:
                    print(
                        f"{self.bot.user} - Todas as tentativas de conectar ao servidor [{data['identifier']}] falharam.")
                    return
                else:
                    await asyncio.sleep(backoff)
                    try:
                        async with self.bot.session.get(data['rest_uri'], timeout=10) as r:
                            break
                    except Exception:
                        print(f'{self.bot.user} - Falha ao conectar no servidor [{data["identifier"]}], '
                              f'nova tentativa [{retries}/{max_retries}] em {backoff} segundos.')
                        backoff += 2
                        retries += 1
                        continue

        data["identifier"] = data["identifier"].replace(" ", "_")
        node = await self.bot.music.initiate_node(auto_reconnect=False, region=region, heartbeat=heartbeat, **data)
        node.search = search
        node.website = node_website

    async def get_tracks(
            self, query: str, user: disnake.Member, node: wavelink.Node = None,
            track_loops=0, use_cache=True):

        if not node:
            node = await self.get_best_node()

        tracks = await process_spotify(self.bot, user.id, query)

        if not tracks:

            if use_cache:
                try:
                    cached_tracks = self.bot.pool.playlist_cache[query]
                except KeyError:
                    pass
                else:

                    tracks = LavalinkPlaylist(
                        {
                            'loadType': 'PLAYLIST_LOADED',
                            'playlistInfo': {
                                'name': cached_tracks[0]["info"]["extra"]["playlist"]["name"],
                                'selectedTrack': -1
                            },
                            'tracks': cached_tracks
                        },
                        requester=user.id,
                        url=cached_tracks[0]["info"]["extra"]["playlist"]["url"]
                    )

            if not tracks:

                if node.search:
                    node_search = node
                else:
                    try:
                        node_search = \
                            sorted(
                                [n for n in self.bot.music.nodes.values() if
                                 n.search and n.available and n.is_available and not n.restarting],
                                key=lambda n: len(n.players))[0]
                    except IndexError:
                        node_search = node

                try:
                    tracks = await node_search.get_tracks(
                        query, track_cls=LavalinkTrack, playlist_cls=LavalinkPlaylist, requester=user.id
                    )
                except ClientConnectorCertificateError:
                    node_search.available = False

                    for n in self.bot.music.nodes.values():

                        if not n.available or not n.is_available or n.restarting:
                            continue

                        try:
                            tracks = await n.get_tracks(
                                query, track_cls=LavalinkTrack, playlist_cls=LavalinkPlaylist, requester=user.id
                            )
                            node_search = n
                            break
                        except ClientConnectorCertificateError:
                            n.available = False
                            continue

                    if not node_search:
                        raise GenericError("**Não há servidores de música disponível.**")

        if not tracks:
            raise GenericError("Não houve resultados para sua busca.")

        if isinstance(tracks, list):
            tracks[0].info["extra"]["track_loops"] = track_loops

        else:

            if (selected := tracks.data['playlistInfo']['selectedTrack']) > 0:
                tracks.tracks = tracks.tracks[selected:] + tracks.tracks[:selected]

        return tracks, node

    async def connect_local_lavalink(self):

        if 'LOCAL' not in self.bot.music.nodes:

            localnode = {
                'host': '127.0.0.1',
                'port': 8090,
                'password': 'youshallnotpass',
                'identifier': 'LOCAL',
                'region': 'us_central',
                'retries': 25
            }

            self.bot.loop.create_task(self.connect_node(localnode))

    @commands.Cog.listener("on_thread_create")
    async def thread_song_request(self, thread: disnake.Thread, reopen: bool = False):

        try:
            player: LavalinkPlayer = self.bot.music.players[thread.guild.id]
        except KeyError:
            return

        if player.static or player.message.id != thread.id:
            return

        if not thread.parent.permissions_for(thread.guild.me).send_messages_in_threads:
            await player.text_channel.send(
                embed=disnake.Embed(
                    color=self.bot.get_color(thread.guild.me),
                    description="**Não tenho permissão de enviar mensagens em conversas do canal atual para ativar "
                                "o sistema de song-request...**\n\n"
                                f"Mensagens enviadas na conversa {thread.mention} serão ignoradas."
                ), delete_after=30
            )
            return

        embed = disnake.Embed(color=self.bot.get_color(thread.guild.me))

        if not self.bot.intents.message_content:
            embed.description = "**Aviso! Não estou com a intent de message_content ativada por meu desenvolvedor...\n" \
                                "A funcionalidade de pedir música aqui pode não ter um resultado esperado...**"

        elif not player.controller_mode:
            embed.description = "**A skin/aparência atual não é compatível com o sistem de song-request " \
                               "via thread/conversa\n\n" \
                               "Nota:** `Esse sistema requer uma skin que use botões.`"

        else:
            if reopen:
                embed.description = "**A sessão para pedidos de música nessa conversa foi reaberta na conversa atual.**"
            else:
                embed.description = "**Essa conversa será usada temporariamente para pedido de músicas.**\n\n" \
                                    "**Peça sua música aqui enviando o nome dela ou o link de uma música/vídeo " \
                                    "que seja de uma das seguintes plataformas suportadas:** " \
                                    "```ansi\n[31;1mYoutube[0m, [33;1mSoundcloud[0m, [32;1mSpotify[0m, [34;1mTwitch[0m```"

        await thread.send(embed=embed)

    @commands.Cog.listener("on_voice_state_update")
    async def player_vc_disconnect(
            self,
            member: disnake.Member,
            before: disnake.VoiceState,
            after: disnake.VoiceState
    ):

        if before.channel == after.channel:
            return

        if member.bot and self.bot.user.id != member.id:
            # ignorar outros bots
            return

        try:
            player: LavalinkPlayer = self.bot.music.players[member.guild.id]
        except KeyError:
            return

        try:
            player.members_timeout_task.cancel()
            player.members_timeout_task = None
        except AttributeError:
            pass

        if member.id == self.bot.user.id and member.guild.voice_client and after.channel:
            # tempfix para channel do voice_client não ser setado ao mover bot do canal.
            player.guild.voice_client.channel = after.channel
            player.last_channel = after.channel

        try:
            check = any(m for m in player.guild.me.voice.channel.members if not m.bot)
        except:
            check = None

        if isinstance(before.channel, disnake.StageChannel) and player.stage_title_event:

            if before.channel.instance:
                try:
                    await before.channel.instance.edit(topic="atualização automática desativada")
                except:
                    traceback.print_exc()

            player.stage_title_event = False

        player.members_timeout_task = self.bot.loop.create_task(player.members_timeout(check=check))

        # rich presence stuff

        if player.auto_pause:
            return

        if player.is_closing or (member.bot and not before.channel):
            return

        channels = set()

        try:
            channels.add(before.channel.id)
        except:
            pass

        try:
            channels.add(after.channel.id)
        except:
            pass

        try:
            try:
                vc = player.guild.me.voice.channel
            except AttributeError:
                vc = player.last_channel

            if vc.id not in channels:
                return
        except AttributeError:
            pass

        if not after or before.channel != after.channel:

            try:
                vc = player.guild.me.voice.channel
            except AttributeError:
                vc = before.channel

            if vc:

                try:
                    await player.process_rpc(vc, users=[member.id], close=not player.guild.me.voice or after.channel != player.guild.me.voice.channel, wait=True)
                except AttributeError:
                    traceback.print_exc()
                    pass

                await player.process_rpc(vc, users=[m for m in vc.voice_states if (m != member.id)])

    async def reset_controller_db(self, guild_id: int, data: dict, inter: disnake.AppCmdInter = None):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        data['player_controller']['channel'] = None
        data['player_controller']['message_id'] = None

        try:
            player: LavalinkPlayer = bot.music.players[guild_id]
        except KeyError:
            return

        player.static = False

        try:
            if isinstance(inter.channel.parent, disnake.TextChannel):
                player.text_channel = inter.channel.parent
            else:
                player.text_channel = inter.channel
        except AttributeError:
            player.text_channel = inter.channel

        try:
            await bot.update_data(guild_id, data, db_name=DBModel.guilds)
        except Exception:
            traceback.print_exc()

    async def get_best_node(self, bot: BotCore = None):

        if not bot:
            bot = self.bot

        try:
            return sorted(
                [n for n in bot.music.nodes.values() if n.stats and n.is_available and n.available and not n.restarting],
                key=lambda n: n.stats.players
            )[0]

        except IndexError:
            try:
                node = bot.music.nodes['LOCAL']
            except KeyError:
                pass
            else:
                if not node._websocket.is_connected:
                    await node.connect(bot)
                return node

            raise GenericError("**Não há servidores de música disponível.**")

    async def error_report_loop(self):

        while True:

            data = await self.error_report_queue.get()

            async with aiohttp.ClientSession() as session:
                webhook = disnake.Webhook.from_url(self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"], session=session)
                await webhook.send(username=self.bot.user.display_name, avatar_url=self.bot.user.display_avatar.url, **data)

            await asyncio.sleep(15)


def setup(bot: BotCore):
    bot.add_cog(Music(bot))
