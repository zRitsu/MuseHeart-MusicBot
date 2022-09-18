import datetime
import json
import aiofiles
import aiohttp
import disnake
from disnake.ext import commands
import traceback
import wavelink
import asyncio
from typing import Union, Optional
from random import shuffle
from urllib import parse
from utils.client import BotCore
from utils.db import DBModel
from utils.music.errors import GenericError, MissingVoicePerms
from utils.music.spotify import SpotifyPlaylist, process_spotify
from utils.music.checks import check_voice, user_cooldown, has_player, has_source, is_requester, is_dj, \
    can_send_message_check, check_requester_channel, can_send_message, can_connect, check_deafen
from utils.music.models import LavalinkPlayer, LavalinkTrack
from utils.music.converters import time_format, fix_characters, string_to_seconds, URL_REG, \
    YOUTUBE_VIDEO_REG, search_suggestions, queue_tracks, seek_suggestions, queue_author, queue_playlist, \
    node_suggestions, fav_add_autocomplete, fav_list, queue_track_index
from utils.music.interactions import VolumeInteraction, QueueInteraction, SelectInteraction
from utils.others import check_cmd, send_idle_embed, CustomContext, PlayerControls
from user_agent import generate_user_agent

PlayOpts = commands.option_enum(
    {
        "Misturar Playlist": "shuffle",
        "Inverter Playlist": "reversed",
    }
)

SearchSource = commands.option_enum(
    {
        "Youtube": "ytsearch",
        "Soundcloud": "scsearch"
    }
)

u_agent = generate_user_agent()


class Music(commands.Cog):

    def __init__(self, bot: BotCore):

        self.bot = bot

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

        tracks = [
            LavalinkTrack(
                t.id, t.info,
                requester=ctx.author.id,
                playlist={"name": tracks.data['playlistInfo']['name'], "url": url}
            ) for t in tracks.tracks]

        self.bot.pool.playlist_cache[url] = [{"track": t.id, "info": t.info} for t in tracks]

        await self.update_cache()

        await ctx.send("As músicas do link foram adicionadas com sucesso em cache.", delete_after=30)

    @commands.is_owner()
    @commands.cooldown(1, 300, commands.BucketType.default)
    @commands.command(hidden=True, aliases=["uc"])
    async def updatecache(self, ctx: CustomContext):

        try:
            if not self.bot.pool.playlist_cache:
                raise GenericError("**Seu cache de playlist está vazio...**")
        except KeyError:
            raise GenericError(f"**Você ainda não usou o comando: {ctx.prefix}{self.addcache.name}**")

        msg = None

        counter = 0

        amount = len(self.bot.pool.playlist_cache)

        txt = ""

        for url in self.bot.pool.playlist_cache:

            try:
                async with ctx.typing():
                    tracks, node = await self.get_tracks(url, ctx.author, use_cache=False)
            except:
                traceback.print_exc()
                tracks = None

            if not tracks:
                txt += f"[`❌ Falha`]({url})\n"

            else:
                newtracks = [
                    LavalinkTrack(
                        t.id, t.info,
                        requester=ctx.author.id,
                        playlist={"name": tracks.data['playlistInfo']['name'], "url": url}
                    ) for t in tracks.tracks]

                self.bot.pool.playlist_cache[url] = [{"track": t.id, "info": t.info} for t in newtracks]

                txt += f"[`{tracks.data['playlistInfo']['name']}`]({url})\n"

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

    @check_voice()
    @can_send_message_check()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.message_command(name="add to queue")
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
    @commands.bot_has_guild_permissions(embed_links=True, send_messages=True)
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.slash_command(name="search",
                            description=f"{desc_prefix}Buscar música e escolher uma entre os resultados para tocar.")
    async def search(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="busca", desc="Nome ou link da música.", autocomplete=search_suggestions),
            *,
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
            options: PlayOpts = commands.Param(name="opções", description="Opções para processar playlist",
                                               default=False),
            source: SearchSource = commands.Param(name="fonte",
                                                  description="Selecionar site para busca de músicas (não links)",
                                                  default="ytsearch"),
            repeat_amount: int = commands.Param(name="repetições", description="definir quantidade de repetições.",
                                                default=0),
            hide_playlist: bool = commands.Param(description="Não incluir detalhes da playlist nas músicas.",
                                                 default=False),
            server: str = commands.Param(name="server", desc="Usar um servidor de música específico na busca.",
                                         autocomplete=node_suggestions, default=None)
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
            hide_playlist=hide_playlist,
            server=server
        )

    @has_player()
    @can_send_message_check()
    @is_dj()
    @commands.slash_command(description=f"{desc_prefix}Me conectar em um canal de voz (ou me mover para um).")
    async def connect(
            self,
            inter: disnake.AppCmdInter,
            channel: Union[disnake.VoiceChannel, disnake.StageChannel] = commands.Param(name="canal",
                                                                                        description="Canal para me conectar",
                                                                                        default=None)
    ):
        await self.do_connect(inter, channel)

    async def do_connect(
            self,
            ctx: Union[disnake.AppCmdInter, commands.Context, disnake.Message],
            channel: Union[disnake.VoiceChannel, disnake.StageChannel] = None,
            check_other_bots_in_vc: bool = False
    ):

        if not channel:
            channel: Union[disnake.VoiceChannel, disnake.StageChannel] = ctx.author.voice.channel

        player = self.bot.music.players[ctx.guild.id]

        can_connect(channel, check_other_bots_in_vc)

        deafen_warn = self.bot.config["GUILD_DEAFEN_WARN"]

        if isinstance(ctx, disnake.AppCmdInter) and ctx.application_command.name == self.connect.name:

            perms = channel.permissions_for(ctx.guild.me)

            if not perms.connect or not perms.speak:
                raise MissingVoicePerms(channel)

            await player.connect(channel.id, self_deaf=True)

            if channel != ctx.guild.me.voice and ctx.guild.me.voice.channel:
                txt = [
                    f"me moveu para o canal <#{channel.id}>",
                    f"**Movido com sucesso para o canal** <#{channel.id}>"
                ]

            else:
                txt = [
                    f"me conectou no canal <#{channel.id}>",
                    f"**Conectei no canal** <#{channel.id}>"
                ]

                if await check_deafen(ctx.guild):
                    deafen_warn = False

            await self.interaction_message(ctx, txt, emoji="🔈", rpc_update=True)

        else:
            await player.connect(channel.id, self_deaf=True)

            await asyncio.sleep(1)

            if await check_deafen(ctx.guild):
                deafen_warn = False

        try:
            player.members_timeout_task.cancel()
        except:
            pass

        if deafen_warn:

            await player.text_channel.send(
                embed=disnake.Embed(
                    title="Aviso:",
                    description="Para manter sua privacidade e me ajudar a economizar "
                                "recursos, recomendo desativar meu áudio do canal clicando "
                                "com botão direito sobre mim e em seguida marcar: desativar "
                                "áudio no servidor.",
                    color=self.bot.get_color(ctx.guild.me),
                ).set_image(
                    url="https://cdn.discordapp.com/attachments/554468640942981147/1012533546386210956/unknown.png"
                ), delete_after=20
            )

        if isinstance(channel, disnake.StageChannel):

            while not ctx.guild.me.voice:
                await asyncio.sleep(1)

            stage_perms = channel.permissions_for(ctx.guild.me)

            if stage_perms.manage_roles:
                await asyncio.sleep(1.5)
                await ctx.guild.me.edit(suppress=False)
            else:

                embed = disnake.Embed(color=self.bot.get_color(ctx.guild.me))

                if stage_perms.request_to_speak:
                    await ctx.guild.me.request_to_speak()
                    embed.description = f"**Preciso que aceite minha solicitação pra falar no palco: " \
                                        f"[{channel.name}]({channel.jump_url}).**"
                else:
                    embed.description = f"**Não tenho autoridade de falar no palco " \
                                        f"[{channel.name}]({channel.jump_url}) automaticamente (preciso da permissão " \
                                        f"de um staff).**"

                await ctx.channel.send(ctx.author.mention, embed=embed, delete_after=45)

    @check_voice()
    @can_send_message_check()
    @commands.bot_has_guild_permissions(embed_links=True, send_messages=True)
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="addposition", description="Adicionar música em uma posição especifica da fila.",
                      aliases=["adp", "addpos"])
    async def addpos_legacy(self, ctx: CustomContext, position: Optional[int] = None, *, query: str = None):

        if not position:
            raise GenericError("Você não informou uma posição válida.**")

        if not query:
            raise GenericError("Você não adicionou um nome ou link de uma música.**")

        position -= 1

        await self.play.callback(self=self, inter=ctx, query=query, position=position, options=False,
                                 force_play="no", manual_selection=False,
                                 source="ytsearch", repeat_amount=0, hide_playlist=False, server=None)

    @check_voice()
    @can_send_message_check()
    @commands.bot_has_guild_permissions(embed_links=True, send_messages=True)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.command(name="play", description="Tocar música em um canal de voz.", aliases=["p"])
    async def play_legacy(self, ctx: CustomContext, *, query: str = ""):

        await self.play.callback(self=self, inter=ctx, query=query, position=0, options=False, force_play="no",
                                 manual_selection=False, source="ytsearch", repeat_amount=0, hide_playlist=False,
                                 server=None)

    @check_voice()
    @can_send_message_check()
    @commands.bot_has_guild_permissions(embed_links=True, send_messages=True)
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.command(name="search", description="Buscar música e escolher uma entre os resultados para tocar.",
                      aliases=["sc"])
    async def search_legacy(self, ctx: CustomContext, *, query: str = None):

        if not query:
            raise GenericError("**Você não adicionou um nome ou link para tocar.**")

        await self.play.callback(self=self, inter=ctx, query=query, position=0, options=False, force_play="no",
                                 manual_selection=True, source="ytsearch", repeat_amount=0, hide_playlist=False,
                                 server=None)

    @check_voice()
    @can_send_message_check()
    @commands.bot_has_guild_permissions(embed_links=True, send_messages=True)
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("play", data={disnake.Locale.pt_BR: "tocar"}),
        description=f"{desc_prefix}Tocar música em um canal de voz.")
    async def play(
            self,
            inter: Union[disnake.AppCmdInter, CustomContext],
            query: str = commands.Param(name="busca", desc="Nome ou link da música.",
                                        autocomplete=fav_add_autocomplete), *,
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
            options: PlayOpts = commands.Param(name="opções", description="Opções para processar playlist",
                                               default=False),
            source: SearchSource = commands.Param(name="fonte",
                                                  description="Selecionar site para busca de músicas (não links)",
                                                  default="ytsearch"),
            repeat_amount: int = commands.Param(name="repetições", description="definir quantidade de repetições.",
                                                default=0),
            hide_playlist: bool = commands.Param(name="esconder_playlist",
                                                 description="Não incluir detalhes da playlist nas músicas.",
                                                 default=False),
            server: str = commands.Param(name="server", desc="Usar um servidor de música específico na busca.",
                                         autocomplete=node_suggestions, default=None),
    ):

        if not inter.guild.voice_client:
            if inter.author.voice.channel.user_limit and \
                    (inter.author.voice.channel.user_limit - len(inter.author.voice.channel.voice_states)) < 1:
                raise GenericError(f"**O canal {inter.author.voice.channel.mention} está lotado!**")

        node = self.bot.music.get_node(server)

        if not node:
            node = self.get_best_node()

        msg = None

        guild_data = await self.bot.get_data(inter.guild.id, db_name=DBModel.guilds)

        if not inter.guild.me.voice:
            can_connect(inter.author.voice.channel, check_other_bots_in_vc=guild_data["check_other_bots_in_vc"])

        static_player = guild_data['player_controller']

        if static_player['channel']:
            if not (channel := self.bot.get_channel(int(static_player['channel']))):
                await self.reset_controller_db(inter.guild.id, guild_data, inter)
                channel = inter.channel

        else:
            channel = inter.channel

        can_send_message(channel)

        is_pin = None

        ephemeral = hide_playlist or await self.is_request_channel(inter, data=guild_data, ignore_thread=True)

        if not query:

            opts = [disnake.SelectOption(label=f, value=f, emoji="<:play:734221719774035968>")
                    for f in (await fav_list(inter, ""))]

            if not opts:
                raise GenericError("**Você não possui favoritos...**\n"
                                   "`Adicione um usando o comando: /fav add.`\n"
                                   "`Ou use este comando adicionando um nome ou link de uma música/vídeo.`")

            opts.append(disnake.SelectOption(label="Cancelar", value="cancel", emoji="❌"))

            try:
                add_id = f"_{inter.id}"
            except AttributeError:
                add_id = ""

            msg = await inter.send(
                inter.author.mention,
                embed=disnake.Embed(
                    color=self.bot.get_color(inter.guild.me),
                    description="**Selecione um favorito Abaixo:**\n"
                                f'Nota: você tem apenas <t:{int((disnake.utils.utcnow() + datetime.timedelta(seconds=45)).timestamp())}:R> para escolher!'
                ),
                components=[
                    disnake.ui.Select(
                        custom_id=f"enqueue_fav{add_id}",
                        options=opts
                    )
                ],
                ephemeral=ephemeral
            )

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
                        color=self.bot.get_color(inter.guild.me)
                    ),
                    components=None
                )
                return

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

            if not URL_REG.match(query):
                query = f"{source}:{query}"

            elif "&list=" in query:

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
                    color=self.bot.get_color(inter.guild.me)
                )

                await inter.send(embed=embed, view=view, ephemeral=ephemeral)

                await view.wait()

                if not view.inter:
                    await inter.edit_original_message(
                        content=f"{inter.author.mention}, tempo esgotado!",
                        embed=None, view=None
                    )
                    return

                if view.selected == "music":
                    query = YOUTUBE_VIDEO_REG.match(query).group()

                inter = view.inter

        await inter.response.defer(ephemeral=ephemeral)

        tracks, node = await self.get_tracks(query, inter.user, node=node, track_loops=repeat_amount,
                                             hide_playlist=hide_playlist)

        skin = self.bot.check_skin(guild_data["player_controller"]["skin"])

        player: LavalinkPlayer = self.bot.music.get_player(
            guild_id=inter.guild.id,
            cls=LavalinkPlayer,
            player_creator=inter.author,
            guild=inter.guild,
            channel=channel,
            keep_connected=guild_data["keep_connected"],
            node_id=node.identifier,
            static=bool(static_player['channel']),
            skin=skin
        )

        if static_player['channel'] and not player.message:

            try:
                message = await channel.fetch_message(int(static_player['message_id']))
            except TypeError:
                message = None
            except:
                message = await send_idle_embed(inter.channel, bot=self.bot)
            player.message = message

        pos_txt = ""

        embed = disnake.Embed(color=disnake.Colour.red())

        embed.colour = self.bot.get_color(inter.guild.me)

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

            if force_play == "yes":
                player.queue.insert(0, track)
                pos_txt = " para tocar imediatamente."
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
            embed.description = f"`{fix_characters(track.author, 15)}`**┃**`{time_format(track.duration) if not track.is_stream else '🔴 Livestream'}`**┃**{inter.author.mention}{player.controller_link}"
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

            if hide_playlist:
                log_text = f"Adicionou uma playlist com {len(tracks.tracks)} música(s) {pos_txt}."
            else:
                log_text = f"{inter.author.mention} adicionou a playlist [`{fix_characters(tracks.data['playlistInfo']['name'], 20)}`]({query}){pos_txt} `({len(tracks.tracks)})`."

            total_duration = 0

            for t in tracks.tracks:
                if not t.is_stream:
                    total_duration += t.duration

            embed.set_author(
                name=fix_characters(tracks.data['playlistInfo']['name'], 35),
                url=query
            )
            embed.set_thumbnail(url=tracks.tracks[0].thumb)
            embed.description = f"`{len(tracks.tracks)} música(s)`**┃**`{time_format(total_duration)}`**┃**{inter.author.mention}{player.controller_link}"
            emoji = "🎶"

        if not is_pin:
            try:
                func = inter.edit_original_message
            except AttributeError:
                if msg:
                    func = msg.edit
                elif inter.message.author == inter.guild.me:
                    func = inter.message.edit
                else:
                    func = inter.send

            await func(embed=embed, view=None)

        if not player.is_connected:
            await self.do_connect(
                inter, channel=inter.author.voice.channel,
                check_other_bots_in_vc=guild_data["check_other_bots_in_vc"]
            )

        if not player.current or (force_play == "yes" and len(player.queue)) > 0:
            await player.process_next()
        else:
            if ephemeral:
                player.set_command_log(text=log_text, emoji=emoji)
            await player.update_message()

    @check_voice()
    @has_source()
    @is_requester()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="skip", aliases=["next", "n", "s", "pular"],
                      description=f"Pular a música atual que está tocando.")
    async def skip_legacy(self, ctx: CustomContext):
        await self.skip.callback(self=self, inter=ctx)

    @check_voice()
    @has_source()
    @is_requester()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("skip", data={disnake.Locale.pt_BR: "pular"}),
        description=f"{desc_prefix}Pular a música atual que está tocando."
    )
    async def skip(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if not len(player.queue):
            raise GenericError("**Não há músicas na fila...**")

        if isinstance(inter, disnake.MessageInteraction):
            player.set_command_log(text=f"{inter.author.mention} pulou a música.", emoji="⏭️")
            await inter.response.defer()
        else:
            txt = ["pulou a música.", f"⏭️ **⠂{inter.author.mention} pulou a música:\n"
                                      f"╰[`{fix_characters(player.current.title, 43)}`]({player.current.uri})**"]
            await self.interaction_message(inter, txt, emoji="⏭️")

        if player.loop == "current":
            player.loop = False

        player.current.info["extra"]["track_loops"] = 0

        await player.stop()

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.command(name="back", aliases=["b", "voltar"], description="Voltar para a música anterior.")
    async def back_legacy(self, ctx: CustomContext):
        await self.back.callback(self=self, inter=ctx)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(
        name=disnake.Localized("back", data={disnake.Locale.pt_BR: "voltar"}),
        description=f"{desc_prefix}Voltar para a música anterior."
    )
    async def back(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if not len(player.played) and not len(player.queue):
            await player.seek(0)
            await self.interaction_message(inter, "voltou para o início da música.", emoji="⏪")
            return

        try:
            track = player.played.pop()
        except:
            track = player.queue.pop()
            player.last_track = None
            player.queue.appendleft(player.current)
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

            await self.interaction_message(inter, txt, emoji="⏮️")

        if player.loop == "current":
            player.loop = False
        if not player.current:
            await player.process_next()
        else:
            player.is_previows_music = True
            await player.stop()

    @check_voice()
    @has_source()
    @commands.slash_command(
        name=disnake.Localized("voteskip", data={disnake.Locale.pt_BR: "votar"}),
        description=f"{desc_prefix}Votar para pular a música atual."
    )
    async def voteskip(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        embed = disnake.Embed()

        if inter.author in player.votes:
            raise GenericError("**Você já votou para pular a música atual.**")

        embed.colour = self.bot.get_color(inter.guild.me)

        txt = [
            f"votou para pular a música atual (votos: {len(player.votes) + 1}/{self.bot.config['VOTE_SKIP_AMOUNT']}).",
            f"{inter.author.mention} votou para pular a música atual (votos: {len(player.votes) + 1}/{self.bot.config['VOTE_SKIP_AMOUNT']}).",
        ]

        if len(player.votes) < self.bot.config.get('VOTE_SKIP_AMOUNT', 3):
            embed.description = txt
            player.votes.add(inter.author)
            await self.interaction_message(inter, txt, update=True, emoji="✋")
            return

        await self.interaction_message(inter, txt, emoji="✋")
        await player.stop()

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(1, 5), commands.BucketType.member)
    @commands.command(name="volume", description="Ajustar volume da música.", aliases=["vol", "v"])
    async def volume_legacy(self, ctx: CustomContext, level: str = None):

        if not level:
            raise GenericError("**Você não informou o volume (entre 5-150).**")

        if not level.isdigit() or len(level) > 3:
            raise GenericError("**Volume inválido! escolha entre 5 a 150**", self_delete=7)

        await self.volume.callback(self=self, inter=ctx, value=int(level))

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(1, 5), commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Ajustar volume da música.")
    async def volume(
            self,
            inter: disnake.AppCmdInter, *,
            value: int = commands.Param(name="nível", description="nível entre 5 a 150", min_value=5.0, max_value=150.0)
    ):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        embed = disnake.Embed(color=disnake.Colour.red())

        update = False

        if value is None:

            view = VolumeInteraction(inter)

            embed.colour = self.bot.get_color(inter.guild.me)
            embed.description = "**Selecione o nível do volume abaixo:**"
            await inter.send(embed=embed, ephemeral=await self.is_request_channel(inter), view=view)
            await view.wait()
            if view.volume is None:
                return

            value = view.volume
            update = True

        elif not 4 < value < 151:
            raise GenericError("O volume deve estar entre **5** a **150**.")

        await player.set_volume(value)

        txt = [f"ajustou o volume para **{value}%**", f"🔊 **⠂{inter.author.mention} ajustou o volume para {value}%**"]
        await self.interaction_message(inter, txt, update=update, emoji="🔊")

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.command(name="pause", aliases=["pausar"], description="Pausar a música.")
    async def pause_legacy(self, ctx: CustomContext):
        await self.pause.callback(self=self, inter=ctx)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("pause", data={disnake.Locale.pt_BR: "pausar"}),
        description=f"{desc_prefix}Pausar a música."
    )
    async def pause(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if player.paused:
            raise GenericError("**A música já está pausada.**")

        await player.set_pause(True)

        txt = ["pausou a música.", f"⏸️ **⠂{inter.author.mention} pausou a musica.**"]

        await self.interaction_message(inter, txt, rpc_update=True, emoji="⏸️")

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.command(name="resume", aliases=["unpause"], description="Retomar/Despausar a música.")
    async def resume_legacy(self, ctx: CustomContext):
        await self.resume.callback(self=self, inter=ctx)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("resume", data={disnake.Locale.pt_BR: "despausar"}),
        description=f"{desc_prefix}Retomar/Despausar a música."
    )
    async def resume(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if not player.paused:
            raise GenericError("**A música não está pausada.**")

        await player.set_pause(False)

        txt = ["retomou a música.", f"▶️ **⠂{inter.author.mention} despausou a música.**"]
        await self.interaction_message(inter, txt, rpc_update=True, emoji="▶️")

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="seek", aliases=["sk"], description="Avançar/Retomar a música para um tempo específico.")
    async def seek_legacy(self, ctx: CustomContext, *, position: str = None):

        if not position:
            raise GenericError("**Você não informou o tempo para avançar/voltar (ex: 1:55 | 33 | 0:45).**")

        await self.seek.callback(self=self, inter=ctx, position=position)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("seek", data={disnake.Locale.pt_BR: "avançar"}),
        description=f"{desc_prefix}Avançar/Retomar a música para um tempo específico."
    )
    async def seek(
            self,
            inter: disnake.AppCmdInter,
            position: str = commands.Param(name="tempo", description="Tempo para avançar/voltar (ex: 1:45 / 40 / 0:30)",
                                           autocomplete=seek_suggestions)
    ):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

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

        await player.seek(milliseconds)

        if player.paused:
            await player.set_pause(False)

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

        await self.interaction_message(inter, txt, emoji=emoji)

        await asyncio.sleep(2)
        self.bot.loop.create_task(player.process_rpc())

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(description=f"Selecionar modo de repetição entre: música atual / fila / desativar / quantidade (usando números).")
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

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("loop_mode", data={disnake.Locale.pt_BR: "repetição"}),
        description=f"{desc_prefix}Selecionar modo de repetição entre: atual / fila ou desativar."
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

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

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

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("loop_amount", data={disnake.Locale.pt_BR: "repetição_quantidade"}),
        description=f"{desc_prefix}Definir quantidade de repetições da música atual."
    )
    async def loop_amount(
            self,
            inter: disnake.AppCmdInter,
            value: int = commands.Param(name="valor", description="número de repetições.")
    ):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        player.current.info["extra"]["track_loops"] = value

        txt = [
            f"definiu a quantidade de repetições da música "
            f"[`{(fix_characters(player.current.title, 25))}`]({player.current.uri}) para **{value}**.",
            f"🔄 **⠂{inter.author.mention} definiu a quantidade de repetições da música para [{value}]:**\n"
            f"╰[`{player.current.title}`]({player.current.uri})"
        ]

        await self.interaction_message(inter, txt, rpc_update=True, emoji="🔄")

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="remove", aliases=["r", "del"], description="Remover uma música específica da fila.")
    async def remove_legacy(self, ctx: CustomContext, *, query: str = None):

        if not query:
            raise GenericError("**Você não adicionou um nome ou posição de uma música.**")

        await self.remove.callback(self=self, inter=ctx, query=query)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.slash_command(
        name=disnake.Localized("remove", data={disnake.Locale.pt_BR: "remover"}),
        description=f"{desc_prefix}Remover uma música específica da fila."
    )
    async def remove(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        try:
            index = queue_track_index(inter, query)[0][0]
        except IndexError:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        track = player.queue[index]

        player.queue.remove(track)

        txt = [
            f"removeu a música [`{(fix_characters(track.title, 25))}`]({track.uri}) da fila.",
            f"♻️ **⠂{inter.author.mention} removeu a música da fila:**\n╰[`{track.title}`]({track.uri})"
        ]

        await self.interaction_message(inter, txt, emoji="♻️")

        await player.update_message()

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.guild)
    @commands.command(name="readd", aliases=["readicionar", "rdd"],
                      description="Readicionar as músicas tocadas na fila.")
    async def readd_legacy(self, ctx: CustomContext):
        await self.readd.callback(self=self, inter=ctx)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.guild)
    @commands.slash_command(
        name=disnake.Localized("readd", data={disnake.Locale.pt_BR: "readicionar"}),
        description=f"{desc_prefix}Readicionar as músicas tocadas na fila."
    )
    async def readd(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

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

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="skipto", aliases=["skt", "pularpara"], description="Pular para a música especificada.")
    async def skipto_legacy(self, ctx: CustomContext, *, query: str = None):

        if not query:
            raise GenericError("**Você não adicionou um nome ou posição de uma música.**")

        await self.skipto.callback(self=self, inter=ctx, query=query)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(
        name=disnake.Localized("skipto", data={disnake.Locale.pt_BR: "pular_para"}),
        description=f"{desc_prefix}Pular para a música especificada."
    )
    async def skipto(
            self,
            inter: disnake.AppCmdInter, *,
            query: str = commands.Param(
                name="nome",
                description="Nome da música completo.",
                autocomplete=queue_tracks
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
            )
    ):

        try:
            index = queue_track_index(inter, query)[0][0]
        except IndexError:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

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

        await self.interaction_message(inter, txt, emoji="⤵️")

        await player.stop()

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="move", aliases=["mv", "mover"],
                      description="Mover uma música para a posição especificada da fila.")
    async def move_legacy(self, ctx: CustomContext, position: Optional[int], *, query: str = None):

        if not position:
            raise GenericError("**Você não informou uma posição da fila.**")

        if not query:
            raise GenericError("**Você não adicionou o nome da música.**")

        if query.endswith(" --all"):
            query = query[:-5]
            search_all = True
        else:
            search_all = False

        await self.move.callback(self=self, inter=ctx, position=position, query=query, search_all=search_all)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.slash_command(
        name=disnake.Localized("move", data={disnake.Locale.pt_BR: "mover"}),
        description=f"{desc_prefix}Mover uma música para a posição especificada da fila."
    )
    async def move(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks),
            position: int = commands.Param(name="posição", description="Posição de destino na fila.", default=1),
            search_all: bool = commands.Param(
                name="mover_vários", default=False,
                description="Incluir todas as músicas da fila com o nome especificado."
            )
    ):

        if position < 1:
            raise GenericError(f"**Você usou uma posição inválida: {position}**.")

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        indexes = queue_track_index(inter, query, check_all=search_all)

        if not indexes:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        for index, track in reversed(indexes):
            player.queue.remove(track)

            player.queue.insert(int(position) - 1, track)

        embed = disnake.Embed(color=self.bot.get_color(inter.guild.me))

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

            embed.description = f"↪️ **⠂{inter.author.mention} moveu [{i_size}] músicas com o nome \"{query}\" para " \
                                f"a posição [{position}] da fila:**\n\n{tracklist}"
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

            await inter.send(embed=embed, ephemeral=ephemeral)

        await player.update_message()

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="rotate", aliases=["rt", "rotacionar"],
                      description="Rotacionar a fila para a música especificada.")
    async def rotate_legacy(self, ctx: CustomContext, *, query: str = None):

        if not query:
            raise GenericError("**Você não adicionou um nome ou posição de uma música.**")

        await self.rotate.callback(self=self, inter=ctx, query=query)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.guild)
    @commands.slash_command(
        name=disnake.Localized("rotate", data={disnake.Locale.pt_BR: "rotacionar"}),
        description=f"{desc_prefix}Rotacionar a fila para a música especificada."
    )
    async def rotate(
            self,
            inter: disnake.AppCmdInter,
            query: str = commands.Param(
                name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        index = queue_track_index(inter, query)

        if not index:
            raise GenericError(f"**Não há músicas na fila com o nome: {query}**")

        index = index[0][0]

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

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

    @check_voice()
    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.command(name="nightcore", aliases=["nc"],
                      description="Ativar/Desativar o efeito nightcore (Música acelerada com tom mais agudo).")
    async def nightcore_legacy(self, ctx: CustomContext):

        await self.nightcore.callback(self=self, inter=ctx)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @commands.slash_command(
        description=f"{desc_prefix}Ativar/Desativar o efeito nightcore (Música acelerada com tom mais agudo).")
    async def nightcore(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

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

    @has_source()
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.command(name="nowplaying", aliases=["np"], description="Reenvia a mensagem do player com a música atual.")
    async def nowplaying_legacy(self, ctx: CustomContext):
        await self.nowplaying.callback(self=self, inter=ctx)

    @check_voice()
    @has_source()
    @commands.cooldown(1, 10, commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Reenvia a mensagem do player com a música atual.")
    async def nowplaying(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if player.static:
            raise GenericError("Esse comando não pode ser usado no modo fixo do player.")

        if player.has_thread:
            raise GenericError("**Esse comando não pode ser usado com uma conversa ativa na "
                               f"[mensagem]({player.message.jump_url}) do player.**")

        await inter.response.defer(ephemeral=True)

        if inter.channel != player.text_channel:

            await is_dj().predicate(inter)

            try:

                player.set_command_log(
                    text=f"{inter.author.mention} moveu o player-controller para o canal {inter.channel.mention}.",
                    emoji="💠"
                )

                await player.text_channel.send(
                    embed=disnake.Embed(
                        description=f"💠 **⠂{inter.author.mention} moveu o player-controller para o canal:** {inter.channel.mention}",
                        color=self.bot.get_color(inter.guild.me)
                    )
                )
            except:
                pass

        await player.destroy_message()

        player.text_channel = inter.channel

        await player.invoke_np()

        if not isinstance(inter, CustomContext):
            await inter.edit_original_message("**Player reenviado com sucesso!**")

    @has_player()
    @is_dj()
    @commands.user_command(name=disnake.Localized("Add DJ", data={disnake.Locale.pt_BR: "Adicionar DJ"}))
    async def adddj_u(self, inter: disnake.UserCommandInteraction):
        await self.add_dj(inter, user=inter.target)

    @has_player()
    @is_dj()
    @commands.command(name="adddj", aliases=["adj"],
                      description="Adicionar um membro à lista de DJ's na sessão atual do player.")
    async def add_dj_legacy(self, ctx: CustomContext, user: Optional[disnake.Member] = None):

        if not user:
            raise GenericError(f"**Você não informou um membro (ID, menção, nome, etc).**")

        await self.add_dj.callback(self=self, inter=ctx, user=user)

    @has_player()
    @is_dj()
    @commands.slash_command(
        name=disnake.Localized("add_dj", data={disnake.Locale.pt_BR: "adicionar_dj"}),
        description=f"{desc_prefix}Adicionar um membro à lista de DJ's na sessão atual do player."
    )
    async def add_dj(
            self,
            inter: disnake.AppCmdInter, *,
            user: disnake.User = commands.Param(name="membro", description="Membro a ser adicionado.")
    ):

        error_text = None

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if user == inter.author:
            error_text = "Você não pode adicionar a si mesmo na lista de DJ's."
        elif user.guild_permissions.manage_channels:
            error_text = f"você não pode adicionar o membro {user.mention} na lista de DJ's (ele(a) possui permissão de **gerenciar canais**)."
        elif user.id in player.dj:
            error_text = f"O membro {user.mention} já está na lista de DJ's"

        if error_text:
            raise GenericError(error_text)

        player.dj.add(user.id)
        text = [f"adicionou {user.mention} à lista de DJ's.", f"{user.mention} foi adicionado à lista de DJ's."]

        if (player.static and inter.channel == player.text_channel) or isinstance(inter.application_command,
                                                                                  commands.InvokableApplicationCommand):
            await inter.send(f"{inter.target.mention} adicionado à lista de DJ's!{player.controller_link}")

        await self.interaction_message(inter, txt=text, update=True, emoji="🇳")

    @check_voice()
    @has_player()
    @is_dj()
    @commands.command(name="stop", aliases=["leave", "parar"],
                      description="Parar o player e me desconectar do canal de voz.")
    async def stop_legacy(self, ctx: CustomContext):
        await self.stop.callback(self=self, inter=ctx)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.slash_command(
        name=disnake.Localized("stop", data={disnake.Locale.pt_BR: "parar"}),
        description=f"{desc_prefix}Parar o player e me desconectar do canal de voz."
    )
    async def stop(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]
        player.command_log = f"{inter.author.mention} **parou o player!**"

        if isinstance(inter, disnake.MessageInteraction):
            await player.destroy(inter=inter)
        else:
            await inter.send(
                embed=disnake.Embed(
                    color=self.bot.get_color(inter.guild.me),
                    description=f"🛑 **⠂{inter.author.mention} parou o player.**"
                ),
                components=[
                    disnake.ui.Button(label="Pedir uma música", emoji="🎶", custom_id=PlayerControls.add_song),
                    disnake.ui.Button(label="Tocar favorito", emoji="⭐", custom_id=PlayerControls.enqueue_fav)
                ],
                ephemeral=player.static and player.text_channel == inter.channel
            )
            await player.destroy()

    @has_player()
    @commands.slash_command(name=disnake.Localized("queue", data={disnake.Locale.pt_BR: "fila"}),)
    async def q(self, inter):
        pass

    @check_voice()
    @has_player()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.command(name="shuffle", aliases=["sf", "shf", "sff", "misturar"],
                      description="Misturar as músicas da fila")
    async def shuffle_legacy(self, ctx: CustomContext):
        await self.shuffle_.callback(self, inter=ctx)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @q.sub_command(
        name=disnake.Localized("shuffle", data={disnake.Locale.pt_BR: "misturar"}),
        description=f"{desc_prefix}Misturar as músicas da fila")
    async def shuffle_(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if len(player.queue) < 3:
            raise GenericError("**A fila tem que ter no mínimo 3 músicas para ser misturada.**")

        shuffle(player.queue)

        await self.interaction_message(
            inter,
            ["misturou as músicas da fila.",
             f"🔀 **⠂{inter.author.mention} misturou as músicas da fila.**"],
            emoji="🔀"
        )

    @check_voice()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(1, 5), commands.BucketType.guild)
    @commands.command(name="reverse", aliases=["invert", "inverter", "rv"],
                      description="Inverter a ordem das músicas na fila")
    async def reverse_legacy(self, ctx: CustomContext):
        await self.reverse.callback(self=self, inter=ctx)

    @check_voice()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(1, 5), commands.BucketType.guild)
    @q.sub_command(
        name=disnake.Localized("reverse", data={disnake.Locale.pt_BR: "inverter"}),
        description=f"{desc_prefix}Inverter a ordem das músicas na fila"
    )
    async def reverse(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if len(player.queue) < 2:
            raise GenericError("**A fila tem que ter no mínimo 2 músicas para inverter a ordem.**")

        player.queue.reverse()
        await self.interaction_message(
            inter,
            txt=["inverteu a ordem das músicas na fila.",
                 f"🔄 **⠂{inter.author.mention} inverteu a ordem das músicas na fila.**"],
            update=True,
            emoji="🔄"
        )

    @commands.command(name="queue", aliases=["q", "fila"], description="Exibir as músicas que estão na fila.")
    @commands.max_concurrency(1, commands.BucketType.member)
    async def queue_show_legacy(self, ctx: CustomContext):
        await self.show.callback(self=self, inter=ctx)

    @commands.max_concurrency(1, commands.BucketType.member)
    @q.sub_command(
        name=disnake.Localized("show", data={disnake.Locale.pt_BR: "mostrar"}),
        description=f"{desc_prefix}Exibir as músicas que estão na fila."
    )
    async def show(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if not player.queue:
            raise GenericError("**Não há músicas na fila.**")

        view = QueueInteraction(player, inter.author)
        embed = view.embed

        await inter.send(embed=embed, view=view, ephemeral=await self.is_request_channel(inter))

        await view.wait()

    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.command(name="clear", aliases=["limpar"], description="Limpar a fila de música.")
    async def clear_legacy(self, ctx: CustomContext, *, range_track: str = None):

        try:
            range_start, range_end = range_track.split("-")
            range_start = int(range_start)
            range_end = int(range_end) + 1
        except:
            range_start = None
            range_end = None

        await self.clear.callback(self=self, inter=ctx, song_name=None, song_author=None, user=None, playlist=None,
                                  time_below=None, time_above=None, range_start=range_start, range_end=range_end,
                                  absent_members=False)

    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("clear_queue", data={disnake.Locale.pt_BR: "limpar_fila"}),
        description=f"{desc_prefix}Limpar a fila de música."
    )
    async def clear(
            self,
            inter: disnake.AppCmdInter,
            song_name: str = commands.Param(name="nome_da_música", description="incluir nome que tiver na música.",
                                            default=None),
            song_author: str = commands.Param(name="nome_do_autor",
                                              description="Incluir nome que tiver no autor da música.",
                                              autocomplete=queue_author, default=None),
            user: disnake.Member = commands.Param(name='usuário',
                                                  description="Incluir músicas pedidas pelo usuário selecionado.",
                                                  default=None),
            playlist: str = commands.Param(description="Incluir nome que tiver na playlist.",
                                           autocomplete=queue_playlist, default=None),
            time_below: str = commands.Param(name="duração_abaixo_de",
                                             description="incluir músicas com duração abaixo do tempo definido (ex. 1:23).",
                                             default=None),
            time_above: str = commands.Param(name="duração_acima_de",
                                             description="incluir músicas com duração acima do tempo definido (ex. 1:45).",
                                             default=None),
            range_start: int = commands.Param(name="pos_inicial",
                                              description="incluir músicas da fila a partir de uma posição específica "
                                                          "da fila.",
                                              min_value=1.0, max_value=500.0, default=None),
            range_end: int = commands.Param(name="pos_final",
                                            description="incluir músicas da fila até uma posição específica da fila.",
                                            min_value=1.0, max_value=500.0, default=None),
            absent_members: bool = commands.Param(name="membros_ausentes",
                                                  description="Incluir músicas adicionads por membros fora do canal",
                                                  default=False)
    ):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if not player.queue:
            raise GenericError("**Não há musicas na fila.**")

        filters = []

        if song_name:
            filters.append('song_name')
        if song_author:
            filters.append('song_author')
        if user:
            filters.append('user')
        if playlist:
            filters.append('playlist')
        if absent_members:
            filters.append('absent_members')

        if time_below and time_above:
            raise GenericError(
                "Você deve escolher apenas uma das opções: **duração_abaixo_de** ou **duração_acima_de**.")

        if time_below:
            filters.append('time_below')
            time_below = string_to_seconds(time_below) * 1000
        if time_above:
            filters.append('time_above')
            time_above = string_to_seconds(time_above) * 1000

        if not filters and not range_start and not range_end:
            player.queue.clear()
            txt = ['limpou a fila de música.', f'♻️ **⠂{inter.author.mention} limpou a fila de música.**']

        else:

            if range_start and range_end:

                if range_start >= range_end:
                    raise GenericError("**A posição final deve ser maior que a posição inicial!**")

                song_list = list(player.queue)[range_start - 1: range_end - 1]

            elif range_start:
                song_list = list(player.queue)[range_start - 1:]
            elif range_end:
                song_list = list(player.queue)[:range_end - 1]
            else:
                song_list = list(player.queue)

            deleted_tracks = 0

            for t in song_list:

                temp_filter = list(filters)

                if 'time_below' in temp_filter and t.duration <= time_below:
                    temp_filter.remove('time_below')

                elif 'time_above' in temp_filter and t.duration >= time_above:
                    temp_filter.remove('time_above')

                if 'song_name' in temp_filter and song_name.lower() in t.title.lower():
                    temp_filter.remove('song_name')

                if 'song_author' in temp_filter and song_author.lower() in t.author.lower():
                    temp_filter.remove('song_author')

                if 'user' in temp_filter and user.id == t.requester:
                    temp_filter.remove('user')

                elif 'absent_members' in temp_filter and t.requester not in player.guild.me.voice.channel.voice_states:
                    temp_filter.remove('absent_members')

                if 'playlist' in temp_filter and playlist == t.playlist_name:
                    temp_filter.remove('playlist')

                if not temp_filter:
                    player.queue.remove(t)
                    deleted_tracks += 1

            if not deleted_tracks:
                await inter.send("Nenhuma música encontrada!", ephemeral=True)
                return

            txt = [f"removeu {deleted_tracks} música(s) da fila via clear.",
                   f"♻️ **⠂{inter.author.mention} removeu {deleted_tracks} música(s) da fila.**"]

        await self.interaction_message(inter, txt, emoji="♻️")

    @has_player()
    @is_dj()
    @commands.cooldown(2, 5, commands.BucketType.member)
    @commands.command(name="restrict", aliases=["rstc", "restrito"],
                      description="Ativar/Desativar o modo restrito de comandos que requer DJ/Staff.")
    async def restrict_mode_legacy(self, ctx: CustomContext):

        await self.restrict_mode.callback(self=self, inter=ctx)

    @has_player()
    @is_dj()
    @commands.cooldown(2, 5, commands.BucketType.member)
    @commands.slash_command(
        name=disnake.Localized("restrict_mode", data={disnake.Locale.pt_BR: "modo_restrito"}),
        description=f"{desc_prefix}Ativar/Desativar o modo restrito de comandos que requer DJ/Staff.")
    async def restrict_mode(self, inter: disnake.AppCmdInter):

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        player.restrict_mode = not player.restrict_mode

        msg = ["ativou", "🔐"] if player.restrict_mode else ["desativou", "🔓"]

        text = [
            f"{msg[0]} o modo restrito de comandos do player (que requer DJ/Staff).",
            f"{msg[1]} **⠂{inter.author.mention} {msg[0]} o modo restrito de comandos do player (que requer DJ/Staff).**"
        ]

        await self.interaction_message(inter, text, emoji=msg[1])

    @check_voice()
    @has_player()
    @is_dj()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.slash_command(
        name=disnake.Localized("change_node", data={disnake.Locale.pt_BR: "mudar_server"}),
        description=f"{desc_prefix}Migrar o player para outro servidor de música."
    )
    async def change_node(
            self,
            inter: disnake.AppCmdInter,
            node: str = commands.Param(name="servidor", description="Servidor de música", autocomplete=node_suggestions)
    ):

        if node not in self.bot.music.nodes:
            raise GenericError(f"O servidor de música **{node}** não foi encontrado.")

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        if node == player.node.identifier:
            raise GenericError(f"O player já está no servidor de música **{node}**.")

        await player.change_node(node)

        await self.interaction_message(
            inter,
            [f"Migrou o player para o servidor de música **{node}**",
             f"**O player foi migrado para o servidor de música:** `{node}`"],
            emoji="🌎"
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

                await player.connect(player.channel_id)
            except:
                traceback.print_exc()

    async def is_request_channel(self, ctx: Union[disnake.AppCmdInter, disnake.MessageInteraction, CustomContext], *,
                                 data: dict = None, ignore_thread=False) -> bool:

        if isinstance(ctx, CustomContext):
            return False

        if isinstance(ctx, disnake.MessageInteraction):
            return True

        try:
            player: LavalinkPlayer = self.bot.music.players[ctx.guild.id]

            if not player.static:
                return False

            try:
                if isinstance(ctx.channel.parent, disnake.ForumChannel):
                    return True
            except AttributeError:
                pass

            if isinstance(ctx.channel, disnake.Thread) and player.text_channel == ctx.channel.parent:
                return not ignore_thread

            return player.text_channel == ctx.channel

        except KeyError:

            guild_data = data or await self.bot.get_data(ctx.guild.id, db_name=DBModel.guilds)

            try:
                channel = self.bot.get_channel(int(guild_data["player_controller"]["channel"]))
            except:
                channel = None

            if not channel:
                return False

            if isinstance(ctx.channel, disnake.Thread) and channel == ctx.channel.parent:
                return not ignore_thread

            return channel.id == ctx.channel.id

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
            player: LavalinkPlayer = self.bot.music.players[interaction.guild.id]
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

        guild_data = await self.bot.get_data(interaction.guild.id, db_name=DBModel.guilds)

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
            "hide_playlist": False,
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
                    "hide_playlist": False,
                    "server": None,
                    "force_play": "no"
                }

                cmd = self.bot.get_slash_command("play")

            else:

                try:
                    player: LavalinkPlayer = self.bot.music.players[interaction.guild.id]
                except KeyError:
                    await interaction.send("Não há player ativo no servidor...", ephemeral=True)
                    await send_idle_embed(interaction.message, bot=self.bot)
                    return

                if interaction.message != player.message:
                    return

                if player.interaction_cooldown:
                    raise GenericError("O player está em cooldown, tente novamente em instantes.")

                vc = self.bot.get_channel(player.channel_id)

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

                if control == PlayerControls.volume:
                    kwargs = {"value": None}

                elif control == PlayerControls.queue:
                    cmd = self.bot.get_slash_command("queue").children.get("show")

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
                    position = int(position) - 1

                kwargs = {
                    "query": query,
                    "position": position or 0,
                    "options": False,
                    "manual_selection": True,
                    "source": "ytsearch",
                    "repeat_amount": 0,
                    "hide_playlist": False,
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

        if ctx.command:
            return

        if message.author.bot:

            if message.flags.ephemeral:
                return

            try:
                player: LavalinkPlayer = self.bot.music.players[message.guild.id]
            except KeyError:
                return

            if message.channel != player.text_channel:
                return

            player.last_message_id = message.id
            return

        try:
            data = await self.bot.get_data(message.guild.id, db_name=DBModel.guilds)
        except AttributeError:
            return

        try:
            player: Optional[LavalinkPlayer] = self.bot.music.players[message.guild.id]
            if player.text_channel == message.channel:
                player.last_message_id = message.id
        except (AttributeError, KeyError):
            player: Optional[LavalinkPlayer] = None

        if player and isinstance(message.channel, disnake.Thread) and not player.static:

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

                try:
                    await message.delete()
                except:
                    pass

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

        if not message.content:

            try:
                if message.type.thread_starter_message:
                    return
            except AttributeError:
                return
            await message.delete()
            await message.channel.send(f"{message.author.mention} você deve enviar um link/nome da música.",
                                       delete_after=9)
            return

        try:
            await self.song_request_concurrency.acquire(message)
        except:
            await message.delete()
            await message.channel.send(
                f"{message.author.mention} você deve aguardar seu pedido de música anterior carregar...",
                delete_after=10)
            return

        message.content = message.content.strip("<>")

        msg = None

        error = None

        try:

            if not URL_REG.match(message.content):
                message.content = f"ytsearch:{message.content}"

            elif "&list=" in message.content:

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

            if isinstance(message.channel, disnake.Thread) and \
                    not isinstance(message.channel.parent, disnake.ForumChannel):
                return
            else:
                await message.delete()
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

            if msg:
                await msg.edit(content=error, embed=None, view=None, delete_after=7)
            else:
                await message.channel.send(error, delete_after=7)
            await message.delete()

        await self.song_request_concurrency.release(message)

    async def parse_song_request(self, message, text_channel, data, *, response=None):

        if not message.author.voice:
            raise GenericError("Você deve entrar em um canal de voz para pedir uma música.")

        can_connect(
            channel=message.author.voice.channel,
            check_other_bots_in_vc=data["check_other_bots_in_vc"]
        )

        try:
            if message.guild.me.voice.channel != message.author.voice.channel:
                raise GenericError(
                    f"Você deve entrar no canal <#{message.guild.me.voice.channel.id}> para pedir uma música.")
        except AttributeError:
            pass

        tracks, node = await self.get_tracks(message.content, message.author)

        player: LavalinkPlayer = self.bot.music.get_player(
            guild_id=message.guild.id,
            cls=LavalinkPlayer,
            player_creator=message.author,
            guild=message.guild,
            channel=text_channel,
            keep_connected=data["keep_connected"],
            static=True,
            skin=data["player_controller"]["skin"],
            node_id=node.identifier
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
            if isinstance(message.channel, disnake.Thread) and not isinstance(message.channel.parent, disnake.ForumChannel):
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
            player.queue.append(tracks[0])
            if isinstance(message.channel, disnake.Thread) and not isinstance(message.channel.parent, disnake.ForumChannel):
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

    async def cog_before_message_command_invoke(self, inter):
        await self.cog_before_slash_command_invoke(inter)

    async def cog_before_user_command_invoke(self, inter):
        await self.cog_before_slash_command_invoke(inter)

    async def interaction_message(self, inter: Union[disnake.Interaction, CustomContext], txt, update=False, emoji="✅",
                                  rpc_update=False):

        try:
            txt, txt_ephemeral = txt
        except:
            txt_ephemeral = False

        player: LavalinkPlayer = self.bot.music.players[inter.guild.id]

        component_interaction = isinstance(inter, disnake.MessageInteraction)

        ephemeral = await self.is_request_channel(inter)

        if ephemeral:
            player.set_command_log(text=f"{inter.author.mention} {txt}", emoji=emoji)

        await player.update_message(interaction=False if (update or not component_interaction) else inter,
                                    rpc_update=rpc_update)

        if isinstance(inter, CustomContext):
            embed = disnake.Embed(color=self.bot.get_color(inter.guild.me),
                                  description=f"{txt_ephemeral or txt}{player.controller_link}")
            try:
                await inter.store_message.edit(embed=embed, view=None, content=None)
            except AttributeError:
                await inter.send(embed=embed)

        elif not component_interaction:

            if not inter.response.is_done():
                embed = disnake.Embed(color=self.bot.get_color(inter.guild.me),
                                      description=(
                                                          txt_ephemeral or f"{inter.author.mention} **{txt}**") + player.controller_link)

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

            for player in list(node.players.values()):

                try:

                    try:
                        new_node: wavelink.Node = self.get_best_node()
                    except:
                        try:
                            await player.text_channel.send("O player foi finalizado por falta de servidores de música...",
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

        if not node.restarting:
            print(f"{self.bot.user} - [{node.identifier}] Conexão perdida - reconectando em {int(backoff)} segundos.")

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
        print(f"guild: {player.guild.name} | canal: {player.channel_id}")
        print(f"server: {payload.player.node.identifier} | ")
        print(f"reason: {payload.reason} | code: {payload.code}")
        print("-" * 15)

        if player.is_closing:
            return

        if payload.code == 4014:

            if player.guild.me.voice:
                if player.controller_mode:
                    player.update = True
                return

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

        if payload.code in (
                4000,  # internal error
                1006,
                1001,
                #4016,  # Connection started elsewhere
                4005   # Already authenticated.
        ):
            await asyncio.sleep(3)

            await player.connect(player.channel_id)
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
        else:
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
                    await player.invoke_np()
                except:
                    traceback.print_exc()
                    continue

    @commands.Cog.listener('on_wavelink_track_start')
    async def track_start(self, node, payload: wavelink.TrackStart):

        player: LavalinkPlayer = payload.player

        if not player.text_channel.permissions_for(player.guild.me).send_messages:
            try:
                print(f"{player.guild.name} [{player.guild.id}] - Desligando player por falta de permissão para enviar "
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

        await player.process_next()

    async def connect_node(self, data: dict):

        if data["identifier"] in self.bot.music.nodes:
            return

        data['rest_uri'] = ("https" if data.get('secure') else "http") + f"://{data['host']}:{data['port']}"
        data['user_agent'] = u_agent
        search = data.pop("search", True)
        max_retries = data.pop('retries', 0)
        node_website = data.pop('website', '')

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

        node = await self.bot.music.initiate_node(auto_reconnect=False, **data)
        node.search = search
        node.website = node_website

    async def get_tracks(
            self, query: str, user: disnake.Member, node: wavelink.Node = None,
            track_loops=0, hide_playlist=False, use_cache=True):

        if not node:
            node = self.get_best_node()

        tracks = await process_spotify(self.bot, user.id, query, hide_playlist=hide_playlist)

        if not tracks:

            if use_cache:
                try:
                    cached_tracks = self.bot.pool.playlist_cache[query]
                except KeyError:
                    pass
                else:
                    tracks = wavelink.TrackPlaylist(
                        {
                            'loadType': 'PLAYLIST_LOADED',
                            'playlistInfo': {
                                'name': cached_tracks[0]["info"]["extra"]["playlist"]["name"],
                                'selectedTrack': -1
                            },
                            'tracks': cached_tracks
                        }
                    )

            if not tracks:

                if node.search:
                    node_search = node
                else:
                    try:
                        node_search = \
                            sorted(
                                [n for n in self.bot.music.nodes.values() if n.search and n.available and n.is_available],
                                key=lambda n: len(n.players))[0]
                    except IndexError:
                        node_search = node

                tracks = await node_search.get_tracks(query)

        if not tracks:
            raise GenericError("Não houve resultados para sua busca.")

        if isinstance(tracks, list):

            if isinstance(tracks[0], wavelink.Track):
                tracks = [LavalinkTrack(track.id, track.info, requester=user.id, track_loops=track_loops) for track in
                          tracks]

        else:

            if not isinstance(tracks, SpotifyPlaylist):

                try:
                    if tracks.tracks[0].info.get("class") == "YoutubeAudioTrack":
                        query = "https://www.youtube.com/playlist?list=" \
                                f"{parse.parse_qs(parse.urlparse(query).query)['list'][0]}"
                except IndexError:
                    pass

                playlist = {
                    "name": tracks.data['playlistInfo']['name'],
                    "url": query
                } if not hide_playlist else {}

                tracks.tracks = [LavalinkTrack(t.id, t.info, requester=user.id, playlist=playlist) for t in
                                 tracks.tracks]

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

        if member.bot and member.id != self.bot.user.id:  # ignorar outros bots
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

        if player.guild.me.voice:

            if self.bot.intents.members:
                check = any(m for m in player.guild.me.voice.channel.members if not m.bot)
            else:
                check = any(m for m in member.guild.me.voice.channel.voice_states if m != self.bot.user.id)

            if not check:
                player.members_timeout_task = self.bot.loop.create_task(player.members_timeout())
            elif not player.can_process_next:
                player.can_process_next = True
                if not player.current:
                    await player.process_next()

        # rich presence stuff

        if player.is_closing or member.bot:
            return

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

                self.bot.loop.create_task(player.process_rpc(vc, users=[member.id], close=True))
                self.bot.loop.create_task(
                    player.process_rpc(vc, users=[m for m in vc.voice_states if (m != member.id or m != self.bot.user.id)]))

    async def reset_controller_db(self, guild_id: int, data: dict, inter: disnake.AppCmdInter = None):

        data['player_controller']['channel'] = None
        data['player_controller']['message_id'] = None
        try:
            player: LavalinkPlayer = self.bot.music.players[guild_id]
            player.static = False
            try:
                if isinstance(inter.channel.parent, disnake.TextChannel):
                    player.text_channel = inter.channel.parent
                else:
                    player.text_channel = inter.channel
            except AttributeError:
                player.text_channel = inter.channel

        except KeyError:
            pass
        await self.bot.update_data(guild_id, data, db_name=DBModel.guilds)

    def get_best_node(self):

        try:
            return sorted(
                [n for n in self.bot.music.nodes.values() if n.stats and n.is_available and n.available],
                key=lambda n: n.stats.players
            )[0]
        except IndexError:
            raise GenericError("**Não há servidores de música disponível.**")


def setup(bot: BotCore):
    bot.add_cog(Music(bot))
