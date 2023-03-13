import argparse
import datetime
import json
import traceback
import asyncio
from typing import Union, Optional
from random import shuffle

import aiofiles
import aiohttp
import disnake
from aiohttp import ClientConnectorCertificateError
from disnake.ext import commands
import wavelink

from utils.client import BotCore
from utils.db import DBModel
from utils.music.errors import GenericError, MissingVoicePerms, NoVoice, PoolException
from utils.music.spotify import process_spotify
from utils.music.checks import check_voice, has_player, has_source, is_requester, is_dj, \
    can_send_message_check, check_requester_channel, can_send_message, can_connect, check_deafen, check_pool_bots, \
    check_channel_limit, check_stage_topic
from utils.music.models import LavalinkPlayer, LavalinkTrack, LavalinkPlaylist
from utils.music.converters import time_format, fix_characters, string_to_seconds, URL_REG, \
    YOUTUBE_VIDEO_REG, google_search, percentage
from utils.music.interactions import VolumeInteraction, QueueInteraction, SelectInteraction
from utils.others import check_cmd, send_idle_embed, CustomContext, PlayerControls, fav_list, queue_track_index, \
    pool_command
from user_agent import generate_user_agent


class Music(commands.Cog):

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

    u_agent = generate_user_agent()

    def __init__(self, bot: BotCore):

        self.bot = bot

        self.extra_hints = bot.config["EXTRA_HINTS"].split("||")

        self.song_request_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

        self.player_interaction_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

        self.song_request_cooldown = commands.CooldownMapping.from_cooldown(rate=1, per=300,
                                                                            type=commands.BucketType.member)

        self.music_settings_cooldown = commands.CooldownMapping.from_cooldown(rate=3, per=15,
                                                                              type=commands.BucketType.guild)

    desc_prefix = "🎶 [Música] 🎶 | "

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
            data = await self.bot.get_global_data(ctx.author.id, db_name=DBModel.users)
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
        only_voiced=True, name="stageannounce", aliases=["stagevc", "togglestageannounce"], hidden=True,
        description="Ativar o sistema de anuncio automático do palco com o nome da música.\n\n"
                    "Placeholders:\n"
                    "{track.title} -> Nome da música\n"
                    "{track.author} -> Nome do Artista/Uploader/Author da música.\n"
                    "{track.duration} -> Duração da música.\n"
                    "{track.source} -> Origem/Fonte da música (Youtube/Spotify/Soundcloud etc)\n"
                    "{track.playlist} -> Nome da playlist de origem da música (caso tenha)\n"
                    "{requester.name} -> Nome/Nick do membro que pediu a música\n"
                    "{requester.tag} -> Tag/Discriminator do membro que pediu a música\n"
                    "{requester.id} -> ID do membro que pediu a música\n",
        cooldown=stage_cd, max_concurrency=stage_mc, extras={"exclusive_cooldown": True},
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
                description="{track.title} {track.author} {track.duration} {track.playlist} {requester.name} {requester.tag}"
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

        if not guild.me.voice.channel.permissions_for(guild.me).mute_members:
            raise GenericError(f"**{bot.user.mention} precisa da permissão de silenciar membros.**")

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not template:
            template = player.stage_title_template

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
                channel = ctx.music_bot.get_channel(ctx.author.voice.channel.id)
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

        can_connect(channel, me.guild, check_other_bots_in_vc=check_other_bots_in_vc)

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
                  aliases=["adp", "addpos"], check_player=False, cooldown=play_cd, max_concurrency=play_mc)
    async def addpos_legacy(self, ctx: CustomContext, position: Optional[int] = None, *, query: str = None):

        if not position:
            raise GenericError("Você não informou uma posição válida.**")

        if position < 1:
            raise GenericError("**Número da posição da fila tem que ser 1 ou superior.**")

        if not query:
            raise GenericError("Você não adicionou um nome ou link de uma música.**")

        await self.play.callback(self=self, inter=ctx, query=query, position=position, options=False,
                                 force_play="no", manual_selection=False,
                                 source="ytsearch", repeat_amount=0, server=None)

    play_flags = argparse.ArgumentParser(exit_on_error=False)
    play_flags.add_argument('query', nargs='*', help="nome ou link da música")
    play_flags.add_argument('-position', '-pos', '-p', type=int, default=0, help='Colocar a música em uma posição específica. Ex: -p 10')
    play_flags.add_argument('-next', '-proximo', action='store_true', help='Adicionar a música/playlist no topo da fila (equivalente ao: -pos 1)')
    play_flags.add_argument('-reverse', '-r', action='store_true', help='Inverter a ordem das músicas adicionadas (efetivo apenas ao adicionar playlist).')
    play_flags.add_argument('-shuffle', '-sl', action='store_true', help='Misturar as músicas adicionadas (efetivo apenas ao adicionar playlist).')
    play_flags.add_argument('-select', '-s', action='store_true', help='Escolher a música entre os resultados encontrados.')
    play_flags.add_argument('-source', '-scr', type=str, default="ytsearch", help='Fazer a busca da música usando uma fonte específica [youtube/soundcloud etc]')
    play_flags.add_argument('-force', '-now', '-n', '-f', action='store_true', help='Tocar a música adicionada imediatamente (efetivo apenas se houver uma música tocando atualmente.)')
    play_flags.add_argument('-loop', '-lp', type=int, default=0, help="Definir a quantidade de repetições da música escolhida. Ex: -loop 5")
    play_flags.add_argument('-server', '-sv', type=str, default=None, help='Usar um servidor de música específico.')

    @can_send_message_check()
    @check_voice()
    @commands.bot_has_guild_permissions(send_messages=True)
    @commands.max_concurrency(1, commands.BucketType.member)
    @pool_command(name="play", description="Tocar música em um canal de voz.", aliases=["p"], check_player=False,
                  cooldown=play_cd, max_concurrency=play_mc)
    async def play_legacy(self, ctx: CustomContext, *, flags: str = ""):

        args, unknown = self.play_flags.parse_known_args(flags.split())

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
                  aliases=["sc"], check_player=False, cooldown=play_cd, max_concurrency=play_mc)
    async def search_legacy(self, ctx: CustomContext, *, query: str = None):

        if not query:
            raise GenericError("**Você não adicionou um nome ou link para tocar.**")

        await self.play.callback(self=self, inter=ctx, query=query, position=0, options=False, force_play="no",
                                 manual_selection=True, source="ytsearch", repeat_amount=0, server=None)

    @can_send_message_check()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("play_nusic_file", data={disnake.Locale.pt_BR: "tocar_arquivo"}),
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

        inter.message = DummyMessage()

        await self.play.callback(self=self, inter=inter, query="", position=position, options=False, force_play=force_play,
                                 manual_selection=False, source="ytsearch", repeat_amount=repeat_amount, server=server)

    @can_send_message_check()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("play", data={disnake.Locale.pt_BR: "tocar"}),
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

        attachment: Optional[disnake.Attachment] = None

        try:
            player = bot.music.players[guild.id]
            node = player.node
            guild_data = {}

        except KeyError:

            node = bot.music.get_node(server)

            if not node:
                node = self.get_best_node(bot)

            guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

            if not guild.me.voice:
                can_connect(inter.author.voice.channel, guild, guild_data["check_other_bots_in_vc"])

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

                    if attachment.content_type not in ("audio/mpeg", "audio/ogg"):
                        raise GenericError("**O arquivo que você enviou não é um arquivo de música válido...**")

                    query = attachment.url

                except IndexError:
                    pass

        if not query:

            favs = await fav_list(inter, "")

            if not favs:
                raise GenericError("**Você não possui favoritos...**\n"
                                   "`Adicione um usando o comando: /fav manager.`\n"
                                   "`Ou use este comando adicionando um nome ou link de uma música/vídeo.`")

            if len(favs) == 1:
                query = f"> fav: {favs[0]}"

            else:
                opts = [disnake.SelectOption(label=f, value=f, emoji="<:play:734221719774035968>") for f in favs]

                opts.append(disnake.SelectOption(label="Cancelar", value="cancel", emoji="❌"))

                try:
                    add_id = f"_{inter.id}"
                except AttributeError:
                    add_id = ""

                embed = disnake.Embed(
                    color=self.bot.get_color(guild.me),
                    description="**Selecione um favorito Abaixo:**\n"
                                f'Nota: você tem apenas <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=45)).timestamp())}:R> para escolher!'
                )

                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

                kwargs = {
                    "content": inter.author.mention,
                    "components": [
                        disnake.ui.Select(
                            custom_id=f"enqueue_fav{add_id}",
                            options=opts
                        )
                    ],
                    "embed": embed
                }

                try:
                    msg = await inter.send(ephemeral=ephemeral, **kwargs)
                except disnake.InteractionTimedOut:
                    msg = await inter.channel.send(**kwargs)

                def check_fav_selection(i: Union[CustomContext, disnake.MessageInteraction]):

                    try:
                        return i.data.custom_id == f"enqueue_fav_{inter.id}" and i.author == inter.author
                    except AttributeError:
                        return i.author == inter.author and i.message.id == msg.id

                try:
                    select_interaction: disnake.MessageInteraction = await self.bot.wait_for(
                        "dropdown", timeout=45, check=check_fav_selection
                    )
                except asyncio.TimeoutError:
                    try:
                        await msg.edit(conent="Tempo de seleção esgotado!", embed=None, view=None)
                    except:
                        pass
                    return

                try:
                    func = select_interaction.response.edit_message
                except AttributeError:
                    func = msg.edit

                if select_interaction.data.values[0] == "cancel":
                    await func(
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
                query = f"> fav: {select_interaction.data.values[0]}"

        if query.startswith("> pin: "):
            is_pin = True
            query = query[7:]

        if query.startswith("> fav:"):
            user_data = await self.bot.get_global_data(inter.author.id, db_name=DBModel.users)
            query = user_data["fav_links"][query[7:]]

        else:

            query = query.strip("<>")

            urls = URL_REG.findall(query)

            if not urls:

                query = f"{source}:{query}"

            else:

                if not self.bot.config["ENABLE_DISCORD_URLS_PLAYBACK"] and "cdn.discordapp.com/attachments/" in query:
                    raise GenericError("**O suporte a links do discord está desativado.**")

                query = urls[0].split("&ab_channel=")[0]

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

                    if bot.user.id != self.bot.user.id:
                        embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

                    msg = await inter.send(embed=embed, view=view, ephemeral=ephemeral)

                    await view.wait()

                    if not view.inter:

                        try:
                            func = inter.edit_original_message
                        except AttributeError:
                            func = msg.edit

                        await func(
                            content=f"{inter.author.mention}, tempo esgotado!",
                            embed=None, view=None
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
                guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)
                static_player = guild_data['player_controller']

                if static_player['channel']:
                    channel, warn_message = await self.check_channel(guild_data, inter, channel, guild, bot)

        if not player:

            skin = guild_data["player_controller"]["skin"]
            static_skin = guild_data["player_controller"]["static_skin"]

            global_data = await self.bot.get_global_data(guild.id, db_name=DBModel.guilds)

            if self.bot.config["GLOBAL_PREFIX"]:
                if global_data["global_skin"]:
                    skin = global_data["player_skin"] or skin
                    static_skin = global_data["player_skin_static"] or guild_data["player_controller"]["static_skin"]

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

                try:
                    message = await channel.fetch_message(int(static_player['message_id']))
                except TypeError:
                    message = None
                except:
                    message = await send_idle_embed(channel, bot=bot)

                player.message = message

        pos_txt = ""

        embed = disnake.Embed(color=disnake.Colour.red())

        embed.colour = self.bot.get_color(guild.me)

        position -= 1

        if isinstance(tracks, list):

            if manual_selection and len(tracks) > 1:

                embed.description = f"**Selecione uma música abaixo:**"

                try:
                    func = inter.edit_original_message
                except AttributeError:
                    func = inter.send

                try:
                    add_id = f"_{inter.id}"
                except AttributeError:
                    add_id = ""

                msg = await func(
                    embed=embed,
                    components=[
                        disnake.ui.Select(
                            placeholder='Resultados:',
                            custom_id=f"track_selection{add_id}",
                            options=[
                                disnake.SelectOption(
                                    label=t.title[:99],
                                    value=f"track_select_{n}",
                                    description=f"{t.author} [{time_format(t.duration)}]")
                                for n, t in enumerate(tracks[:25])
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

                track = tracks[int(select_interaction.data.values[0][13:])]

                if isinstance(inter, CustomContext):
                    inter.message = msg

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

            if force_play == "yes":
                player.queue.insert(0, track)
            elif position < 0:
                player.queue.append(track)
            else:
                player.queue.insert(position, track)
                pos_txt = f" na posição {position + 1} da fila"

            duration = time_format(track.duration) if not track.is_stream else '🔴 Livestream'

            log_text = f"{inter.author.mention} adicionou [`{fix_characters(track.title, 20)}`]({track.uri}){pos_txt} `({duration})`."

            embed.set_author(
                name=fix_characters(track.title, 35),
                url=track.uri
            )
            embed.set_thumbnail(url=track.thumb)
            embed.description = f"`{fix_characters(track.author, 15)}`**┃**`{time_format(track.duration) if not track.is_stream else '🔴 Livestream'}`**┃**{inter.author.mention}"
            emoji = "🎵"

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
                embed.set_author(name=fix_characters(tracks.name, 35), url=tracks.url)
            except KeyError:
                embed.set_author(
                    name="Spotify Playlist",
                )
            embed.set_thumbnail(url=tracks.tracks[0].thumb)
            embed.description = f"`{len(tracks.tracks)} música(s)`**┃**`{time_format(total_duration)}`**┃**{inter.author.mention}"
            emoji = "🎶"

        embed.description += player.controller_link

        if not is_pin:

            if not player.is_connected:
                try:
                    embed.description += f"\n`Canal de voz:` {inter.author.voice.channel.mention}"
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

            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

            await func(embed=embed, view=None)

        if not player.is_connected:

            try:
                guild_data["check_other_bots_in_vc"]
            except KeyError:
                guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

            if not inter.author.voice:
                raise NoVoice()

            await self.do_connect(
                inter, channel=inter.author.voice.channel,
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
            await player.stop()
        else:
            if ephemeral:
                player.set_command_log(text=log_text, emoji=emoji)
            player.update = True

    @play.autocomplete("busca")
    async def fav_add_autocomplete(self, inter: disnake.Interaction, query: str):

        if URL_REG.match(query):
            return [query] if len(query) < 100 else []

        favs: list = await fav_list(inter, query, prefix="> fav: ")

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

    @check_stage_topic()
    @is_requester()
    @check_voice()
    @pool_command(name="skip", aliases=["next", "n", "s", "pular", "skipto"], cooldown=skip_back_cd,
                  max_concurrency=skip_back_mc, description=f"Pular a música atual que está tocando.",
                  only_voiced=True)
    async def skip_legacy(self, ctx: CustomContext, *, query: str = None):

        if ctx.invoked_with == "skipto" and not query:
            raise GenericError("**Você deve adicionar um nome para usar o skipto.**")

        await self.skip.callback(self=self, inter=ctx, query=query)

    @check_stage_topic()
    @is_requester()
    @has_source()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("skipto", data={disnake.Locale.pt_BR: "pular_para"}),
        description=f"{desc_prefix}Pular para uma música específica da fila.",
        extras={"only_voiced": True}, cooldown=skip_back_cd, max_concurrency=skip_back_mc
    )
    async def skipto(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(
                name="nome",
                description="Nome da música (completa ou parte dela)."
            )):

        await self.skip.callback(self=self, inter=inter, query=query)

    @check_stage_topic()
    @is_requester()
    @has_source()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("skip", data={disnake.Locale.pt_BR: "pular"}),
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
            )):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if query:

            try:
                index = queue_track_index(inter, bot, query)[0][0]
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

            txt = [
                "pulou para a música atual.",
                f"⤵️ **⠂{inter.author.mention} pulou para a música:**\n╰[`{fix_characters(track.title, 43)}`]({track.uri})"
            ]

            await self.interaction_message(inter, txt, emoji="⤵️", store_embed=True)

        else:

            if isinstance(inter, disnake.MessageInteraction):
                player.set_command_log(text=f"{inter.author.mention} pulou a música.", emoji="⏭️")
                await inter.response.defer()
            else:
                txt = ["pulou a música.", f"⏭️ **⠂{inter.author.mention} pulou a música:\n"
                                          f"╰[`{fix_characters(player.current.title, 43)}`]({player.current.uri})**"]
                await self.interaction_message(inter, txt, emoji="⏭️", store_embed=True)

            if player.loop == "current":
                player.loop = False

        await player.stop()

    @check_stage_topic()
    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="back", aliases=["b", "voltar"], description="Voltar para a música anterior.", only_voiced=True,
                  cooldown=skip_back_cd, max_concurrency=skip_back_mc)
    async def back_legacy(self, ctx: CustomContext):
        await self.back.callback(self=self, inter=ctx)

    @check_stage_topic()
    @is_dj()
    @has_player()
    @check_voice()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("back", data={disnake.Locale.pt_BR: "voltar"}),
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
                player.queue.appendleft(player.current)

        player.last_track = None
                
        player.queue.appendleft(track)

        if isinstance(inter, disnake.MessageInteraction):
            player.set_command_log(text=f"{inter.author.mention} voltou para a música atual.", emoji="⏮️")
            await inter.response.defer()
        else:
            t = player.queue[0]

            txt = [
                "voltou para a música atual.",
                f"⏮️ **⠂{inter.author.mention} voltou para a música:\n╰[`{fix_characters(t.title, 43)}`]({t.uri})**"
            ]

            await self.interaction_message(inter, txt, emoji="⏮️", store_embed=True)

        if player.loop == "current":
            player.loop = False
        if not player.current:
            await player.process_next()
        else:
            player.is_previows_music = True
            await player.stop()

    @check_stage_topic()
    @has_source()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("voteskip", data={disnake.Locale.pt_BR: "votar_pular"}),
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
        await player.stop()

    volume_cd = commands.CooldownMapping.from_cooldown(1, 7, commands.BucketType.member)
    volume_mc = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

    @is_dj()
    @has_source()
    @check_voice()
    @pool_command(name="volume", description="Ajustar volume da música.", aliases=["vol", "v"], only_voiced=True,
                  cooldown=volume_cd, max_concurrency=volume_mc)
    async def volume_legacy(self, ctx: CustomContext, level: str = None):

        if not level:
            raise GenericError("**Você não informou o volume (entre 5-150).**")

        if not level.isdigit() or len(level) > 3:
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

            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

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
        name=disnake.Localized("pause", data={disnake.Locale.pt_BR: "pausar"}),
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
        name=disnake.Localized("resume", data={disnake.Locale.pt_BR: "despausar"}),
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
    @has_source()
    @check_voice()
    @pool_command(name="seek", aliases=["sk"], description="Avançar/Retomar a música para um tempo específico.",
                  only_voiced=True, cooldown=seek_cd, max_concurrency=seek_mc)
    async def seek_legacy(self, ctx: CustomContext, *, position: str = None):

        if not position:
            raise GenericError("**Você não informou o tempo para avançar/voltar (ex: 1:55 | 33 | 0:45).**")

        await self.seek.callback(self=self, inter=ctx, position=position)

    @check_stage_topic()
    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("seek", data={disnake.Locale.pt_BR: "avançar"}),
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
        self.bot.loop.create_task(player.process_rpc())

    @seek.autocomplete("tempo")
    async def seek_suggestions(self, inter: disnake.Interaction, query: str):

        try:
            if query or not inter.author.voice:
                return
        except AttributeError:
            pass

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
        only_voiced=True, cooldown=loop_cd, max_concurrency=loop_mc)
    async def loop(self, ctx: CustomContext, mode: str = None):

        try:
            bot = ctx.music_bot
        except AttributeError:
            bot = ctx.bot

        if not mode:

            embed = disnake.Embed(
                description="**Selecione um modo de repetição:**",
                color=self.bot.get_color(ctx.guild.me)
            )

            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

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
        name=disnake.Localized("loop_mode", data={disnake.Locale.pt_BR: "modo_repetição"}),
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

        self.bot.loop.create_task(player.process_rpc())

        await self.interaction_message(inter, txt, emoji=emoji)

    @is_dj()
    @has_source()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("loop_amount", data={disnake.Locale.pt_BR: "quantidade_repetição"}),
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
            f"[`{(fix_characters(player.current.title, 25))}`]({player.current.uri}) para **{value}**.",
            f"🔄 **⠂{inter.author.mention} definiu a quantidade de repetições da música para [{value}]:**\n"
            f"╰[`{player.current.title}`]({player.current.uri})"
        ]

        await self.interaction_message(inter, txt, rpc_update=True, emoji="🔄")

    remove_mc = commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="remove", aliases=["r", "del"], description="Remover uma música específica da fila.",
                  only_voiced=True, max_concurrency=remove_mc)
    async def remove_legacy(self, ctx: CustomContext, *, query: str = None):

        if not query:
            raise GenericError("**Você não adicionou um nome ou posição de uma música.**")

        await self.remove.callback(self=self, inter=ctx, query=query)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("remove", data={disnake.Locale.pt_BR: "remover"}),
        description=f"{desc_prefix}Remover uma música específica da fila.",
        extras={"only_voiced": True}, max_concurrency=remove_mc
    )
    async def remove(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="nome", description="Nome da música completo.")
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            index = queue_track_index(inter, bot, query)[0][0]
        except IndexError:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        track = player.queue[index]

        player.queue.remove(track)

        txt = [
            f"removeu a música [`{(fix_characters(track.title, 25))}`]({track.uri}) da fila.",
            f"♻️ **⠂{inter.author.mention} removeu a música da fila:**\n╰[`{track.title}`]({track.uri})"
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
        name=disnake.Localized("readd_songs", data={disnake.Locale.pt_BR: "readicionar_músicas"}),
        description=f"{desc_prefix}Readicionar as músicas tocadas na fila.",
        extras={"only_voiced": True}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc
    )
    async def readd_songs(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        if not player.played:
            raise GenericError("**Não há músicas tocadas.**")

        qsize = len(player.played)

        player.played.reverse()
        player.queue.extend(player.played)
        player.played.clear()

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

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="move", aliases=["mv", "mover"], only_voiced=True, max_concurrency=remove_mc,
                  description="Mover uma música para a posição especificada da fila.")
    async def move_legacy(self, ctx: CustomContext, position: Optional[int], *, query: str = None):

        if not position:
            raise GenericError("**Você não informou uma posição da fila.**")

        if not query:
            raise GenericError("**Você não adicionou o nome da música.**")

        if query.endswith(" --all"):
            query = query[:-5]
            search_all = "yes"
        else:
            search_all = "no"

        await self.move.callback(self=self, inter=ctx, position=position, query=query, search_all=search_all)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("move", data={disnake.Locale.pt_BR: "mover"}),
        description=f"{desc_prefix}Mover uma música para a posição especificada da fila.",
        extras={"only_voiced": True}, max_concurrency=remove_mc
    )
    async def move(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="nome", description="Nome da música."),
            position: int = commands.Param(name="posição", description="Posição de destino na fila.", default=1),
            search_all: str = commands.Param(
                name="mover_vários",
                description="Incluir todas as músicas da fila com o nome especificado.",
                choices=[
                    disnake.OptionChoice(
                        disnake.Localized("Yes", data={disnake.Locale.pt_BR: "Sim"}), "yes"
                    ),
                    disnake.OptionChoice(
                        disnake.Localized("No", data={disnake.Locale.pt_BR: "Não"}), "no"
                    )
                ],
                default="no"
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

        indexes = queue_track_index(inter, bot, query, check_all=search_all == "yes")

        if not indexes:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        for index, track in reversed(indexes):
            player.queue.remove(track)

            player.queue.insert(int(position) - 1, track)

        if (i_size := len(indexes)) == 1:
            track = indexes[0][1]

            txt = [
                f"moveu a música [`{fix_characters(track.title, limit=25)}`]({track.uri}) para a posição **[{position}]** da fila.",
                f"↪️ **⠂{inter.author.mention} moveu uma música para a posição [{position}]:**\n"
                f"╰[`{fix_characters(track.title, limit=43)}`]({track.uri})"
            ]

            await self.interaction_message(inter, txt, emoji="↪️")

        else:

            tracklist = "\n".join(f"[`{fix_characters(t.title, 45)}`]({t.uri})" for i, t in indexes[:10])

            embed = disnake.Embed(
                color=self.bot.get_color(guild.me),
                description=f"↪️ **⠂{inter.author.mention} moveu [{i_size}] músicas com o nome \"{query}\" para " \
                            f"a posição [{position}] da fila:**\n\n{tracklist}"
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
                         f"** para a posição **[{position}]** da fila.", emoji="↪️")

            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

            await inter.send(embed=embed, ephemeral=ephemeral)

        await player.update_message()

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="rotate", aliases=["rt", "rotacionar"], only_voiced=True,
                  description="Rotacionar a fila para a música especificada.",
                  cooldown=queue_manipulation_cd, max_concurrency=remove_mc)
    async def rotate_legacy(self, ctx: CustomContext, *, query: str = None):

        if not query:
            raise GenericError("**Você não adicionou um nome ou posição de uma música.**")

        await self.rotate.callback(self=self, inter=ctx, query=query)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("rotate", data={disnake.Locale.pt_BR: "rotacionar_fila"}),
        description=f"{desc_prefix}Rotacionar a fila para a música especificada.",
        extras={"only_voiced": True}, cooldown=queue_manipulation_cd, max_concurrency=remove_mc
    )
    async def rotate(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(
                name="nome", description="Nome da música completo.")
    ):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        index = queue_track_index(inter, bot, query)

        if not index:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        index = index[0][0]

        player: LavalinkPlayer = bot.music.players[inter.guild_id]

        track = player.queue[index]

        if index <= 0:
            raise GenericError(f"**A música **[`{track.title}`]({track.uri}) já é a próxima da fila.")

        player.queue.rotate(0 - (index))

        txt = [
            f"rotacionou a fila para a música [`{(fix_characters(track.title, limit=25))}`]({track.uri}).",
            f"🔃 **⠂{inter.author.mention} rotacionou a fila para a música:**\n╰[`{track.title}`]({track.uri})."
        ]

        await self.interaction_message(inter, txt, emoji="🔃")

        await player.update_message()

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

        return [f"{track.title}"[:100] for n, track in enumerate(player.queue) if query.lower() in track.title.lower()][
               :20]

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

                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

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
        await self.add_dj(inter, user=inter.target)

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="adddj", aliases=["adj"], only_voiced=True,
                  description="Adicionar um membro à lista de DJ's na sessão atual do player.")
    async def add_dj_legacy(self, ctx: CustomContext, user: Optional[disnake.Member] = None):

        if not user:
            raise GenericError(f"**Você não informou um membro (ID, menção, nome, etc).**")

        await self.add_dj.callback(self=self, inter=ctx, user=user)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("add_dj", data={disnake.Locale.pt_BR: "adicionar_dj"}),
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

        if user == inter.author:
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
        name=disnake.Localized("remove_dj", data={disnake.Locale.pt_BR: "remover_dj"}),
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
        name=disnake.Localized("stop", data={disnake.Locale.pt_BR: "parar"}),
        description=f"{desc_prefix}Parar o player e me desconectar do canal de voz.",
        extras={"only_voiced": True}
    )
    async def stop(self, inter: disnake.AppCmdInter):

        try:
            bot = inter.music_bot
            inter_destroy = inter if bot.user.id == self.bot.user.id else None
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            inter_destroy = inter
            guild = inter.guild

        player: LavalinkPlayer = bot.music.players[inter.guild_id]
        player.command_log = f"{inter.author.mention} **parou o player!**"

        if isinstance(inter, disnake.MessageInteraction):
            await player.destroy(inter=inter_destroy)
        else:

            embed = disnake.Embed(
                color=self.bot.get_color(guild.me),
                description=f"🛑 **⠂{inter.author.mention} parou o player.**"
            )

            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

            await inter.send(
                embed=embed,
                components=[
                    disnake.ui.Button(label="Pedir uma música", emoji="🎶", custom_id=PlayerControls.add_song),
                    disnake.ui.Button(label="Tocar favorito", emoji="⭐", custom_id=PlayerControls.enqueue_fav)
                ] if inter.guild else [],
                ephemeral=player.static and player.text_channel.id == inter.channel_id
            )
            await player.destroy()

    @has_player()
    @check_voice()
    @commands.slash_command(name=disnake.Localized("queue", data={disnake.Locale.pt_BR: "fila"}),
                            extras={"only_voiced": True})
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
        name=disnake.Localized("shuffle", data={disnake.Locale.pt_BR: "misturar"}),
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
        name=disnake.Localized("reverse", data={disnake.Locale.pt_BR: "inverter"}),
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
        name=disnake.Localized("display", data={disnake.Locale.pt_BR: "exibir"}),
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
        if bot.user.id != self.bot.user.id:
            embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

        await inter.send(embed=embed, view=view, ephemeral=True)

        await view.wait()

    clear_flags = argparse.ArgumentParser(exit_on_error=False)
    clear_flags.add_argument('song_name', nargs='*', help="incluir nome que tiver na música.")
    clear_flags.add_argument('-uploader', '-author', '-artist', nargs = '+', default="",
                             help="Incluir nome que tiver no autor da música.")
    clear_flags.add_argument('-member', '-user', '-u', nargs='+', default="",
                             help="Incluir músicas pedidas pelo usuário selecionado.")
    clear_flags.add_argument('-playlist', '-list', '-pl', nargs='+', default="",
                             help="Incluir nome que tiver na playlist.")
    clear_flags.add_argument('-minimal_time', '-mintime', '-min','-min_duration', '-minduration',  default=None,
                             help="incluir músicas com duração mínima especificada (ex. 1:23).")
    clear_flags.add_argument('-max_time', '-maxtime', '-max', '-max_duration', '-maxduration', default=None,
                             help="incluir músicas da fila a partir de uma posição específica da fila.")
    clear_flags.add_argument('-start_position', '-startpos', '-start', type=int, default=None,
                             help="incluir músicas da fila a partir de uma posição específica da fila.")
    clear_flags.add_argument('-end_position', '-endpos', '-end', type=int, default=None,
                             help="incluir músicas da fila até uma posição específica da fila.")
    clear_flags.add_argument('-absent', '-absentmembers', '-abs', action='store_true',
                             help="Incluir músicas adicionads por membros fora do canal")

    @is_dj()
    @has_player()
    @check_voice()
    @pool_command(name="clear", aliases=["limpar"], description="Limpar a fila de música.", only_voiced=True,
                  cooldown=queue_manipulation_cd, max_concurrency=remove_mc)
    async def clear_legacy(self, ctx: CustomContext, *, flags: str = ""):

        args, unknown = self.clear_flags.parse_known_args(flags.split())

        await self.clear.callback(
            self=self, inter=ctx,
            song_name=" ".join(args.song_name + unknown),
            song_author=" ".join(args.uploader),
            user=await commands.MemberConverter().convert(ctx, " ".join(args.member)) if args.member else None,
            playlist=" ".join(args.playlist),
            min_duration=args.minimal_time,
            max_duration=args.max_time,
            range_start=args.start_position,
            range_end=args.end_position,
            absent_members=args.absent
        )

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("clear_queue", data={disnake.Locale.pt_BR: "limpar_fila"}),
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
            playlist: str = commands.Param(description="Incluir nome que tiver na playlist.", default=None),
            min_duration: str = commands.Param(name="duração_mínima",
                                               description="incluir músicas com duração mínima especificada (ex. 1:23).",
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

            for t in song_list:

                temp_filter = list(filters)

                if 'time_below' in temp_filter and t.duration <= min_duration:
                    temp_filter.remove('time_below')
                    final_filters.add('time_below')

                elif 'time_above' in temp_filter and t.duration >= max_duration:
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
                        temp_filter.remove('playlist')
                        final_filters.add('playlist')
                    elif isinstance(inter, CustomContext) and playlist.lower() in t.playlist_name.lower():
                        playlist = t.playlist_name
                        temp_filter.remove('playlist')
                        final_filters.add('playlist')

                if not temp_filter:
                    player.queue.remove(t)
                    deleted_tracks += 1

            if not deleted_tracks:
                await inter.send("Nenhuma música encontrada!", ephemeral=True)
                return

            try:
                final_filters.remove("song_name")
                txt.append(f"**inclui nome:** `{fix_characters(song_name)}`")
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
                txt.append(f"**Playlist:** `{fix_characters(playlist)}`")
            except:
                pass

            try:
                final_filters.remove("time_below")
                txt.append(f"**Com duração mínima:** `{min_duration}`")
            except:
                pass

            try:
                final_filters.remove("time_above")
                txt.append(f"**Com duração máxima:** `{max_duration}`")
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
    @pool_command(name="restrict", aliases=["rstc", "restrito"], only_voiced=True, cooldown=restrict_cd, max_concurrency=restrict_mc,
                  description="Ativar/Desativar o modo restrito de comandos que requer DJ/Staff.")
    async def restrict_mode_legacy(self, ctx: CustomContext):

        await self.restrict_mode.callback(self=self, inter=ctx)

    @is_dj()
    @has_player()
    @check_voice()
    @commands.slash_command(
        name=disnake.Localized("restrict_mode", data={disnake.Locale.pt_BR: "modo_restrito"}),
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

    nonstop_cd = commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.member)
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

    @commands.Cog.listener()
    async def on_ready(self):

        for guild_id in list(self.bot.music.players):
            try:
                player: LavalinkPlayer = self.bot.music.players[guild_id]

                if player.is_connected:
                    continue

                await player.connect(player.last_channel.id)
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

                            if (channel_db.archived or channel_db.locked) and not channel_db.parent.permissions_for(
                                    guild.me).manage_threads:
                                raise GenericError(
                                    f"**{bot.user.mention} não possui permissão de gerenciar tópicos para "
                                    f"desarquivar/destrancar o tópico: {channel_db.mention}**")

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

        guild_data = await self.bot.get_data(interaction.guild_id, db_name=DBModel.guilds)

        try:
            query = guild_data["player_controller"]["fav_links"][interaction.data.values[0]]['url']
        except KeyError:
            raise GenericError("**O item selecionado não foi encontrado na base de dados...**")

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

    async def player_controller(self, interaction: disnake.MessageInteraction, control: str):

        if not self.bot.bot_ready:
            await interaction.send("Ainda estou inicializando...", ephemeral=True)
            return

        if not interaction.guild:
            await interaction.response.edit_message(components=None)
            return

        kwargs = {}

        cmd: Optional[disnake.AppCmdInter] = None

        try:

            if control == "musicplayer_request_channel":
                cmd = self.bot.get_slash_command("setup")
                kwargs = {"target": interaction.channel}
                await self.process_player_interaction(interaction, cmd, kwargs)
                return

            if control == PlayerControls.add_song:

                if not interaction.user.voice:
                    raise GenericError("**Você deve entrar em um canal de voz para usar esse botão.**")

                await interaction.response.send_modal(
                    title="Pedir uma música",
                    custom_id="modal_add_song",
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

                kwargs = {
                    "query": "",
                    "position": 0,
                    "options": False,
                    "manual_selection": True,
                    "source": "ytsearch",
                    "repeat_amount": 0,
                    "server": None,
                    "force_play": "no"
                }

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

                vc = player.last_channel

                if not vc:
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

                if control == PlayerControls.volume:
                    kwargs = {"value": None}

                elif control == PlayerControls.queue:
                    cmd = self.bot.get_slash_command("queue").children.get("display")

                elif control == PlayerControls.shuffle:
                    cmd = self.bot.get_slash_command("queue").children.get("shuffle")

                elif control == PlayerControls.seek_to_start:
                    cmd = self.bot.get_slash_command("seek")
                    kwargs = {"position": "0"}

                elif control == PlayerControls.pause_resume:
                    control = PlayerControls.pause if not player.paused else PlayerControls.resume

                elif control == PlayerControls.loop_mode:

                    if player.loop == "current":
                        kwargs['mode'] = 'queue'
                    elif player.loop == "queue":
                        kwargs['mode'] = 'off'
                    else:
                        kwargs['mode'] = 'current'

                elif control == PlayerControls.skip:
                    kwargs = {"query": None, "play_only": "no"}

                try:
                    await self.player_interaction_concurrency.acquire(interaction)
                except commands.MaxConcurrencyReached:
                    raise GenericError(
                        "**Você tem uma interação em aberto!**\n`Se for uma mensagem oculta, evite clicar em \"ignorar\".`")

            if not cmd:
                cmd = self.bot.get_slash_command(control[12:])

            await self.process_player_interaction(
                interaction=interaction,
                command=cmd,
                kwargs=kwargs
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

        if inter.custom_id == "modal_add_song":

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

    @commands.Cog.listener("on_song_request")
    async def song_requests(self, ctx: Optional[CustomContext], message: disnake.Message):

        try:
            player: LavalinkPlayer = self.bot.music.players[message.guild.id]
            if player.text_channel == message.channel and not message.flags.ephemeral:
                player.last_message_id = message.id
        except (AttributeError, KeyError):
            player: Optional[LavalinkPlayer] = None

        if ctx.command or message.mentions:
            return

        if message.author.bot and not isinstance(message.channel, disnake.StageChannel):
            return

        try:
            data = await self.bot.get_data(message.guild.id, db_name=DBModel.guilds)
        except AttributeError:
            return

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
                    components=[
                        disnake.ui.Button(emoji="🎶", custom_id=PlayerControls.add_song, label="Pedir uma música"),
                        disnake.ui.Button(emoji="⭐", custom_id=PlayerControls.enqueue_fav, label="Tocar favorito")
                    ],
                    delete_after=20
                )
                return

        try:
            if isinstance(message.channel, disnake.Thread):

                if isinstance(message.channel.parent, disnake.ForumChannel):

                    if data['player_controller']["channel"] != str(message.channel.id):
                        return
                    if message.is_system():
                        await message.delete()

        except AttributeError:
            pass

        if message.author.bot:
            if message.is_system() and not isinstance(message.channel, disnake.Thread):
                await message.delete()
            return

        if not message.content:

            if message.is_system():
                return

            if message.type == disnake.MessageType.thread_starter_message:
                return

            try:
                attachment = message.attachments[0]
            except IndexError:
                await message.channel.send(f"{message.author.mention} você deve enviar um link/nome da música.",
                                           delete_after=9)
                return

            else:

                if attachment.size > 18000000:
                    await message.channel.send(f"{message.author.mention} o arquivo que você enviou deve ter o tamanho "
                                               f"inferior a 18mb.", delete_after=9)
                    return

                if attachment.content_type not in ("audio/mpeg", "audio/ogg"):
                    await message.channel.send(f"{message.author.mention} o arquivo que você enviou deve ter o tamanho "
                                               f"inferior a 18mb.", delete_after=9)
                    return

                message.content = attachment.url

        try:
            await self.song_request_concurrency.acquire(message)
        except:
            await message.channel.send(
                f"{message.author.mention} você deve aguardar seu pedido de música anterior carregar...",
                delete_after=10)
            return

        message.content = message.content.strip("<>")

        msg = None

        error = None

        try:

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

            try:
                await msg.delete()
            except:
                pass

        except GenericError as e:
            error = f"{message.author.mention}. {e}"

        except Exception as e:
            traceback.print_exc()
            error = f"{message.author.mention} **ocorreu um erro ao tentar obter resultados para sua busca:** ```py\n{e}```"

        if error:

            try:
                if msg:
                    await msg.edit(content=error, embed=None, view=None, delete_after=7)
                else:
                    await message.channel.send(error, delete_after=7)
            except:
                traceback.print_exc()

        await self.song_request_concurrency.release(message)

    async def parse_song_request(self, message, text_channel, data, *, response=None, attachment: disnake.Attachment=None):

        if not message.author.voice:
            raise GenericError("Você deve entrar em um canal de voz para pedir uma música.")

        can_connect(
            channel=message.author.voice.channel,
            guild=message.guild,
            check_other_bots_in_vc=data["check_other_bots_in_vc"]
        )

        try:
            if message.guild.me.voice.channel != message.author.voice.channel:
                raise GenericError(
                    f"Você deve entrar no canal <#{message.guild.me.voice.channel.id}> para pedir uma música.")
        except AttributeError:
            pass

        tracks, node = await self.get_tracks(message.content, message.author)

        try:
            player = self.bot.music.players[message.guild.id]
            if not player.static and not player.has_thread:
                await message.delete()
        except KeyError:
            skin = data["player_controller"]["skin"]
            static_skin = data["player_controller"]["static_skin"]

            global_data = await self.bot.get_global_data(message.guild.id, db_name=DBModel.guilds)

            if self.bot.config["GLOBAL_PREFIX"] and global_data["global_skin"]:
                skin = global_data["player_skin"] or skin
                static_skin = global_data["player_skin_static"] or static_skin

            player: LavalinkPlayer = self.bot.music.get_player(
                guild_id=message.guild.id,
                cls=LavalinkPlayer,
                player_creator=message.author.id,
                guild=message.guild,
                channel=text_channel,
                last_message_id=data['player_controller']['message_id'],
                static=True,
                skin=self.bot.check_skin(skin),
                skin_static=self.bot.check_static_skin(static_skin),
                custom_skin_data=global_data["custom_skins"],
                custom_skin_static_data=global_data["custom_skins_static"],
                node_id=node.identifier,
                extra_hints=self.extra_hints,
            )

        if not player.message:
            try:
                cached_message = await text_channel.fetch_message(int(data['player_controller']['message_id']))
            except:
                cached_message = await send_idle_embed(message, bot=self.bot)
                data['player_controller']['message_id'] = str(cached_message.id)
                await self.bot.update_data(message.guild.id, data, db_name=DBModel.guilds)

            player.message = cached_message

        embed = disnake.Embed(color=self.bot.get_color(message.guild.me))

        try:
            player.queue.extend(tracks.tracks)
            if isinstance(message.channel, disnake.Thread) and not isinstance(message.channel.parent,
                                                                              disnake.ForumChannel):
                embed.description = f"> 🎶 **┃ Playlist adicionada:** [`{tracks.data['playlistInfo']['name']}`]({message.content})\n" \
                                    f"> ✋ **┃ Pedido por:** {message.author.mention}\n" \
                                    f"> 🎼 **┃ Música(s):** `[{len(tracks.tracks)}]`"
                embed.set_thumbnail(url=tracks.tracks[0].thumb)
                if response:
                    await response.edit(content=None, embed=embed, view=None)
                else:
                    await message.channel.send(embed=embed)

            else:
                player.set_command_log(
                    text=f"{message.author.mention} adicionou a playlist [`{fix_characters(tracks.data['playlistInfo']['name'], 20)}`]"
                         f"({tracks.tracks[0].playlist_url}) `({len(tracks.tracks)})`.",
                    emoji="🎶"
                )

        except AttributeError:

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
            if isinstance(message.channel, disnake.Thread) and not isinstance(message.channel.parent,
                                                                              disnake.ForumChannel):
                embed.description = f"> 🎵 **┃ Adicionado:** [`{tracks[0].title}`]({tracks[0].uri})\n" \
                                    f"> 💠 **┃ Uploader:** `{tracks[0].author}`\n" \
                                    f"> ✋ **┃ Pedido por:** {message.author.mention}\n" \
                                    f"> ⌛ **┃ Duração:** `{time_format(tracks[0].duration) if not tracks[0].is_stream else '🔴 Livestream'}` "
                embed.set_thumbnail(url=tracks[0].thumb)
                if response:
                    await response.edit(content=None, embed=embed, view=None)
                else:
                    await message.channel.send(embed=embed)

            else:
                duration = time_format(tracks[0].duration) if not tracks[0].is_stream else '🔴 Livestream'
                player.set_command_log(
                    text=f"{message.author.mention} adicionou [`{fix_characters(tracks[0].title, 20)}`]({tracks[0].uri}) `({duration})`.",
                    emoji="🎵"
                )

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

    async def interaction_message(self, inter: Union[disnake.Interaction, CustomContext], txt, emoji: str = "✅",
                                  rpc_update: bool = False, data: dict = None, store_embed: bool = False, force=False):

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

            if bot.user.id != self.bot.user.id:
                embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

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

                if bot.user.id != self.bot.user.id:
                    embed.set_footer(text=f"Usando: {bot.user}", icon_url=bot.user.display_avatar.url)

                await inter.send(embed=embed, ephemeral=ephemeral)

    async def process_nodes(self, data: dict, start_local: bool = False):

        await self.bot.wait_until_ready()

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

                    try:
                        new_node: wavelink.Node = self.get_best_node()
                    except:
                        try:
                            await player.text_channel.send(
                                "O player foi finalizado por falta de servidores de música...",
                                delete_after=11)
                        except:
                            pass
                        await player.destroy()
                        continue

                    await player.change_node(new_node.identifier)
                    await player.update_message()

                except:
                    traceback.print_exc()
                    continue

        await asyncio.sleep(backoff)

        while True:

            if retries == 30:
                print(f"{self.bot.user} - [{node.identifier}] Todas as tentativas de reconectar falharam...")
                return

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

        print("-" * 15)
        print(f"Erro no canal de voz!")
        print(f"guild: {player.guild.name} | canal: {player.last_channel.id}")
        print(f"server: {payload.player.node.identifier} | ")
        print(f"reason: {payload.reason} | code: {payload.code}")
        print("-" * 15)

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

            player.is_resuming = True
            vc_id = player.last_channel.id
            await asyncio.sleep(3)
            await player.connect(vc_id)
            player.is_resuming = False
            return

    @commands.Cog.listener('on_wavelink_track_exception')
    async def wavelink_track_error(self, node, payload: wavelink.TrackException):
        player: LavalinkPlayer = payload.player
        track = player.last_track
        embed = disnake.Embed(
            description=f"**Falha ao reproduzir música:\n[{track.title}]({track.uri})** ```java\n{payload.error}```"
                        f"**Servidor:** `{player.node.identifier}`",
            color=disnake.Colour.red())
        await player.text_channel.send(embed=embed, delete_after=10 if player.static else None)

        if player.locked:
            return

        player.current = None

        if payload.error == "This IP address has been blocked by YouTube (429)":
            player.node.available = False
            newnode = [n for n in self.bot.music.nodes.values() if n != player.node and n.available and n.is_available]
            if newnode:
                player.queue.appendleft(player.last_track)
                await player.change_node(newnode[0].identifier)
            else:
                embed = disnake.Embed(
                    color=self.bot.get_color(player.guild.me),
                    description="**O player foi finalizado por falta de servidores disponíveis.**"
                )
                await player.text_channel.send(embed=embed, delete_after=15)
                await player.destroy(force=True)
                return

        elif not player.keep_connected and not player.loop:
            player.played.append(player.last_track)

        player.locked = True
        await asyncio.sleep(6)
        player.locked = False
        await player.process_next()

    @commands.Cog.listener("on_wavelink_node_ready")
    async def node_ready(self, node: wavelink.Node):
        print(f'{self.bot.user} - Servidor de música: [{node.identifier}] está pronto para uso!')

        if node.restarting:
            node.restarting = False

            for guild_id in list(node.players):
                try:
                    player = node.players[guild_id]
                    await player.change_node(node.identifier, force=True)
                    player.set_command_log(
                        text="O servidor de música foi reconectado com sucesso!",
                        emoji="🔰"
                    )
                    if not player.current and len(player.queue) > 0:
                        await player.process_next()
                    else:
                        await player.invoke_np()
                except:
                    traceback.print_exc()
                    continue

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

        player.process_hint()

        if not player.guild.me.voice:
            try:
                await self.bot.wait_for(
                    "voice_state_update", check=lambda m, b, a: m == player.guild.me and m.voice, timeout=7
                )
            except asyncio.TimeoutError:
                player.update = True
                return

        # TODO: rever essa parte caso adicione função de ativar track loops em músicas da fila
        if player.loop != "current" or (not player.controller_mode and player.current.track_loops == 0):

            await player.invoke_np(
                force=True if (player.static or not player.loop or not player.is_last_message()) else False,
                rpc_update=True)

            try:
                player.message_updater_task.cancel()
            except:
                pass

            self.bot.loop.create_task(player.message_updater())

        cog = self.bot.get_cog("PlayerSession")

        if not cog:
            return

        await cog.save_info(player)

        player.queue_updater_task = self.bot.loop.create_task(cog.queue_updater_task(player))

    @commands.Cog.listener("on_wavelink_track_end")
    async def track_end(self, node: wavelink.Node, payload: wavelink.TrackEnd):

        player: LavalinkPlayer = payload.player

        if player.locked:
            return

        if payload.reason == "FINISHED":
            player.set_command_log()
        elif payload.reason == "STOPPED":
            player.ignore_np_once = True
            pass
        else:
            return

        player.update = False

        await player.track_end()

        try:
            player.message_updater_task.cancel()
        except:
            pass

        await player.process_next()

    async def connect_node(self, data: dict):

        if data["identifier"] in self.bot.music.nodes:
            return

        data['rest_uri'] = ("https" if data.get('secure') else "http") + f"://{data['host']}:{data['port']}"
        data['user_agent'] = self.u_agent
        search = data.pop("search", True)
        max_retries = data.pop('retries', 0)
        node_website = data.pop('website', '')
        region = data.pop('region', 'us_central')

        if max_retries:

            backoff = 7
            retries = 1

            print(f"{self.bot.user} - Iniciando servidor de música: {data['identifier']}")

            while not self.bot.is_closed():
                if retries >= max_retries:
                    print(
                        f"{self.bot.user} - Todas as tentativas de conectar ao servidor [{data['identifier']}] falharam.")
                    return
                else:
                    try:
                        async with self.bot.session.get(data['rest_uri'], timeout=10) as r:
                            break
                    except Exception:
                        backoff += 2
                        # print(f'{self.bot.user} - Falha ao conectar no servidor [{data["identifier"]}], '
                        #       f'nova tentativa [{retries}/{max_retries}] em {backoff} segundos.')
                        await asyncio.sleep(backoff)
                        retries += 1
                        continue

        data["identifier"] = data["identifier"].replace(" ", "_")
        node = await self.bot.music.initiate_node(auto_reconnect=False, region=region, **data)
        node.search = search
        node.website = node_website

    async def get_tracks(
            self, query: str, user: disnake.Member, node: wavelink.Node = None,
            track_loops=0, use_cache=True):

        if not node:
            node = self.get_best_node()

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
                                 n.search and n.available and n.is_available],
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

                        if not n.available or not n.is_available:
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
            await asyncio.sleep(7)

            await self.bot.wait_until_ready()

            localnode = {
                'host': '127.0.0.1',
                'port': 8090,
                'password': 'youshallnotpass',
                'identifier': 'LOCAL',
                'region': 'us_central',
                'retries': 25
            }

            self.bot.loop.create_task(self.connect_node(localnode))

    @commands.Cog.listener("on_thread_delete")
    async def player_thread_delete(self, thread: disnake.Thread):

        player: Optional[LavalinkPlayer] = None

        if not player:
            return

        if player.is_closing:
            return

        if thread.id != player.message.id:
            return

    @commands.Cog.listener("on_thread_create")
    async def thread_song_request(self, thread: disnake.Thread):

        try:
            player: LavalinkPlayer = self.bot.music.players[thread.guild.id]
        except KeyError:
            return

        if player.static or player.message.id != thread.id:
            return

        embed = disnake.Embed(color=self.bot.get_color(thread.guild.me))

        if self.bot.intents.message_content:
            embed.description = "**Esta conversa será usada temporariamente para pedir músicas apenas enviando " \
                                "o nome/link sem necessidade de usar comando.**"
        else:
            embed.description = "**Aviso! Não estou com a intent de message_content ativada por meu desenvolvedor...\n" \
                                "A funcionalidade de pedir música aqui pode não ter um resultado esperado...**"

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

        destroy_player = False

        if member.bot:

            if member.id != self.bot.user.id:  # ignorar outros bots
                return

            if before.channel and not after.channel:
                destroy_player = True

        try:
            player: LavalinkPlayer = self.bot.music.players[member.guild.id]
        except KeyError:
            return

        try:
            player.members_timeout_task.cancel()
            player.members_timeout_task = None
        except AttributeError:
            pass

        if destroy_player and not player.is_resuming:

            if player.static:
                player.command_log = "Desliguei o player por me desconectarem do canal de voz."
                await player.destroy()

            else:
                embed = disnake.Embed(description="**Desliguei o player por me desconectarem do canal de voz.**",
                                      color=self.bot.get_color(player.guild.me))
                try:
                    self.bot.loop.create_task(player.text_channel.send(embed=embed, delete_after=7))
                except:
                    traceback.print_exc()
                await player.destroy()

            return

        if member.id == self.bot.user.id:
            # tempfix para channel do voice_client não ser setado ao mover bot do canal.
            player.guild.voice_client.channel = after.channel
            player.last_channel = after.channel

        try:
            check = any(m for m in player.guild.me.voice.channel.members if not m.bot)
        except:
            check = None

        if not check:
            player.members_timeout_task = self.bot.loop.create_task(player.members_timeout())

        # rich presence stuff

        if player.is_closing or member.bot:
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
            if player.last_channel.id not in channels:
                return
        except AttributeError:
            pass

        if not after or before.channel != after.channel:

            try:
                vc = player.guild.me.voice.channel
            except AttributeError:

                try:
                    await player.destroy()
                except:
                    pass

                vc = before.channel

            if vc:

                try:
                    self.bot.loop.create_task(
                        player.process_rpc(vc, users=[member.id], close=after.channel != player.guild.me.voice.channel))
                except AttributeError:
                    pass

                self.bot.loop.create_task(
                    player.process_rpc(vc, users=[m for m in vc.voice_states if (m != member.id)]))

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

    def get_best_node(self, bot: BotCore = None):

        if not bot:
            bot = self.bot

        try:
            return sorted(
                [n for n in bot.music.nodes.values() if n.stats and n.is_available and n.available],
                key=lambda n: n.stats.players
            )[0]
        except IndexError:
            raise GenericError("**Não há servidores de música disponível.**")


def setup(bot: BotCore):
    bot.add_cog(Music(bot))
