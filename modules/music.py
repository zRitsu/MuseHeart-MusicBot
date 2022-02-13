import pprint

import disnake
from disnake.embeds import Embed
from disnake.ext import commands
import traceback
import wavelink
import asyncio
from fake_useragent import UserAgent
import sys
import json
from random import shuffle
from typing import Literal, Optional, Union
from urllib import parse
from utils.client import BotCore

from utils.music.errors import GenericError, MissingVoicePerms
from utils.music.spotify import SpotifyPlaylist, process_spotify
from utils.music.checks import check_voice, user_cooldown, has_player, has_source, is_requester, is_dj, can_send_message
from utils.music.models import LavalinkPlayer, LavalinkTrack
from utils.music.converters import time_format, fix_characters, string_to_seconds, get_track_index, URL_REG, \
    YOUTUBE_VIDEO_REG, search_suggestions, queue_tracks, seek_suggestions, queue_author, queue_playlist, \
    node_suggestions, fav_add_autocomplete
from utils.music.interactions import VolumeInteraction, QueueInteraction, send_message, SongSelect, SelectInteraction, \
    send_idle_embed, check_cmd

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


desc_prefix = "🎶 [Música] 🎶 | "


class Music(commands.Cog, wavelink.WavelinkMixin):

    def __init__(self, bot: BotCore):

        self.bot = bot

        self.bot.loop.create_task(self.process_nodes())

        self.song_request_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)


    @check_voice()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @can_send_message()
    @commands.user_command(name="enqueue presence track")
    async def user_play(self, inter: disnake.MessageInteraction):

        #inter.target.activities fica retornando None mesmo com intents.presences ativada.
        member = inter.guild.get_member(inter.target.id)

        query = ""

        for a in member.activities:
            if isinstance(a, disnake.activity.Spotify):
                query = f"{a.title} - {a.artists[0]}"
                break

            if not isinstance(a, disnake.Activity):
                continue

            ac = a.to_dict()

            if a.application_id == 463097721130188830:

                if not ac.get('buttons'):
                    continue

                query = a.details.split("|")[0]
                break

            if a.application_id == 367827983903490050:

                state = ac.get('state')

                detais = ac.get('details')

                if not state:
                    continue

                if state.lower() in ['afk', 'idle', 'looking for a game']:
                    raise GenericError(
                        f"{member.mention} está jogando **OSU!** mas no momento não está com uma música ativa...")

                if not detais:
                    raise GenericError(
                        f"{member.mention} está jogando **OSU!** mas no momento não está com uma música ativa...")

                query = "[".join(detais.split("[")[:-1])

                break

        if not query:
            raise GenericError(f"{member.mention} não está com status do spotify, OSU! ou youtube.")

        await self.play(
            inter,
            query=query,
            position=0,
            options="",
            manual_selection=False,
            source="ytsearch",
            repeat_amount=0,
        )


    @check_voice()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @can_send_message()
    @commands.message_command(name="add to queue")
    async def message_play(self, inter: disnake.MessageInteraction):

        if not inter.target.content:
            emb = disnake.Embed(description=f"Não há texto na [mensagem]({inter.target.jump_url}) selecionada...", color=disnake.Colour.red())
            await inter.send(embed=emb, ephemeral=True)
            return

        await self.play(
            inter,
            query=inter.target.content,
            position=0,
            options="",
            manual_selection=False,
            source="ytsearch",
            repeat_amount=0,
        )


    @check_voice()
    @can_send_message()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.slash_command(name="search", description=f"{desc_prefix}Buscar música e escolher uma entre os resultados para tocar.")
    async def search(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="busca", desc="Nome ou link da música.", autocomplete=search_suggestions), *,
            position: int = commands.Param(name="posição", description="Colocar a música em uma posição específica", default=0),
            options: PlayOpts = commands.Param(name="opções", description="Opções para processar playlist", default=False),
            source: SearchSource = commands.Param(name="fonte", description="Selecionar site para busca de músicas (não links)", default="ytsearch"),
            repeat_amount: int = commands.Param(name="repetições", description="definir quantidade de repetições.", default=0),
            hide_playlist: bool = commands.Param(description="Não incluir detalhes da playlist nas músicas.", default=False),
            server: str = commands.Param(name="server", desc="Usar um servidor de música específico na busca.", autocomplete=node_suggestions, default=None)
    ):

        await self.play(
            inter,
            query=query,
            position=position,
            options=options,
            manual_selection=True,
            source=source,
            repeat_amount=repeat_amount,
            hide_playlist=hide_playlist,
            server=server
        )

    @has_player()
    @is_dj()
    @commands.slash_command(description=f"{desc_prefix}Me conectar em um canal de voz (ou me mover para um).")
    async def connect(
            self,
            inter: disnake.ApplicationCommandInteraction,
            channel: Union[disnake.VoiceChannel, disnake.StageChannel] = commands.Param(name="canal", description="Canal para me conectar", default=None)
    ):

        player = inter.player

        if not channel:
            channel: Union[disnake.VoiceChannel, disnake.StageChannel] = inter.author.voice.channel

        if inter.guild_data["check_other_bots_in_vc"] and any(m for m in channel.members if m.bot and m != inter.guild.me):
            raise GenericError(f"**Há outro bot conectado no canal:** <#{inter.author.voice.channel.id}>")

        await player.connect(channel.id)

        try:
            player.members_timeout_task.cancel()
        except:
            pass

        if inter.application_command == self.connect:

            perms = channel.permissions_for(inter.guild.me)

            if not perms.connect or not perms.speak:
                raise MissingVoicePerms(channel)

            txt = [
                f"{'me moveu para o' if channel != inter.guild.me.voice and inter.guild.me.voice.channel else 'me reconectou no'}"
                f" canal <#{channel.id}>",
                f"**Conectei no canal** <#{channel.id}>."
            ]
            await self.interaction_message(inter, txt, rpc_update=True)

        if isinstance(channel, disnake.StageChannel):
            await asyncio.sleep(1)
            if inter.guild.me.guild_permissions.manage_guild:
                await inter.guild.me.edit(suppress=False)
            else:
                await inter.guild.me.request_to_speak()


    @check_voice()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.slash_command(name="play", description=f"{desc_prefix}Tocar música em um canal de voz.")
    async def play(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="busca", desc="Nome ou link da música.", autocomplete=fav_add_autocomplete), *,
            position: int = commands.Param(name="posição", description="Colocar a música em uma posição específica", default=0),
            options: PlayOpts = commands.Param(name="opções" ,description="Opções para processar playlist", default=False),
            manual_selection: bool = commands.Param(name="selecionar_manualmente", description="Escolher uma música manualmente entre os resultados encontrados", default=False),
            source: SearchSource = commands.Param(name="fonte", description="Selecionar site para busca de músicas (não links)", default="ytsearch"),
            repeat_amount: int = commands.Param(name="repetições", description="definir quantidade de repetições.", default=0),
            hide_playlist: bool = commands.Param(name="esconder_playlist", description="Não incluir detalhes da playlist nas músicas.", default=False),
            server: str = commands.Param(name="server", desc="Usar um servidor de música específico na busca.", autocomplete=node_suggestions, default=None)
    ):

        node = self.bot.music.get_node(server)

        if not node:
            node = self.bot.music.get_best_node()

        if not node:
            await inter.send(content="Não há servidores de música disponível.", ephemeral=True)
            return

        static_player = {}

        try:
            static_player = inter.guild_data['player_controller']
            channel = inter.guild.get_channel(int(static_player['channel'])) or inter.channel
        except (KeyError, TypeError):
            channel = inter.channel

        if not channel.permissions_for(inter.guild.me).send_messages:
            raise GenericError(f"Não tenho permissão para enviar mensagens no canal: {channel.mention}")

        if query.startswith("> fav:"):
            user_data = await self.bot.db.get_data(inter.author.id, db_name="users")
            query = user_data["fav_links"][query[7:]]

        else:

            query = query.strip("<>")

            if not URL_REG.match(query):
                query = f"{source}:{query}"

            elif "&list=" in query:

                view = SelectInteraction(
                    user=inter.author,
                    opts = [
                        disnake.SelectOption(label="Música", emoji="🎵", description="Carregar apenas a música do link.", value="music"),
                        disnake.SelectOption(label="Playlist", emoji="🎶", description="Carregar playlist com a música atual.", value="playlist"),
                    ], timeout=30)

                embed = disnake.Embed(
                    description="**O link contém vídeo com playlist.**\n`selecione uma opção em até 30 segundos para prosseguir.`",
                    color=self.bot.get_color(inter.guild.me)
                )

                await inter.send(embed=embed, view=view, ephemeral=True)

                await view.wait()

                if view.selected == "music":
                    query = YOUTUBE_VIDEO_REG.match(query).group()

                if view.inter.response:
                    inter.response = view.inter.response

        await inter.response.defer(ephemeral=hide_playlist or inter.guild_data['player_controller']["channel"] == str(inter.channel.id))

        tracks, node = await self.get_tracks(query, inter.user, node=node, track_loops=repeat_amount,
                                             hide_playlist=hide_playlist)

        try:
            skin = self.bot.check_skin(inter.guild_data["player_controller"]["skin"])
        except:
            skin = self.bot.default_skin

        player: LavalinkPlayer = self.bot.music.get_player(
            guild_id=inter.guild.id,
            cls=LavalinkPlayer,
            requester=inter.author,
            guild=inter.guild,
            channel=channel,
            node_id=node.identifier,
            cog=self,
            static=True if static_player.get('channel') else False,
            skin=skin
        )

        if static_player and not player.message:
            try:
                channel = inter.bot.get_channel(int(static_player['channel']))
            except TypeError:
                channel = None

            if not channel:
                await self.reset_controller_db(inter.guild_id, inter.guild_data, inter=inter)

            else:
                try:
                    message = await channel.fetch_message(int(static_player.get('message_id')))
                except TypeError:
                    await self.reset_controller_db(inter.guild_id, inter.guild_data, inter=inter)
                except:
                    message = await send_idle_embed(inter.channel, bot=self.bot)
                    inter.guild_data['player_controller']['message_id'] = str(message.id)
                    await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name='guilds')
                player.message = message

        pos_txt = ""

        embed = disnake.Embed(color=disnake.Colour.red())

        embed.colour = self.bot.get_color(inter.guild.me)

        position-=1

        if isinstance(tracks, list):

            if manual_selection and len(tracks) > 1:

                embed.description=f"**Selecione uma música abaixo**"
                view = SongSelect(tracks, self.bot)
                view.message = await inter.edit_original_message(embed=embed, view=view)
                await view.wait()
                if not view.track:
                    return

                track = view.track

            else:
                track = tracks[0]

            if position < 0:
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
            embed.description = f"`{len(tracks.tracks)} música(s)`**┃**`{time_format(total_duration)}`**┃**{inter.author.mention}"

        if not manual_selection:
            await inter.edit_original_message(embed=embed, view=None)

        if not player.is_connected:
            inter.player = player
            await self.connect(inter, channel=inter.author.voice.channel)

        if not player.current:
            await player.process_next()
        else:
            player.command_log = log_text
            await player.update_message()


    @check_voice()
    @has_source()
    @is_requester()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Pular a música atual que está tocando.")
    async def skip(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        if not len(player.queue):
            await send_message(inter, embed=disnake.Embed(description="**Não há músicas na fila...**", color=disnake.Colour.red()))
            return

        if inter.type.name != "application_command":
            player.command_log = f"{inter.author.mention} pulou a música."
            await inter.response.defer()
        else:
            player.command_log = f"{inter.author.mention} pulou a música."
            embed = disnake.Embed(description=f"⏭️** ┃ Música pulada:** [`{fix_characters(player.current.title, 30)}`]({player.current.uri})", color=self.bot.get_color(inter.guild.me))
            await inter.send(embed=embed, ephemeral=True)

        if player.loop == "current":
            player.loop = False

        player.current.track_loops = 0

        await player.stop()


    @check_voice()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Voltar para a música anterior.")
    async def back(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        if not len(player.played) and not len(player.queue):

            await player.seek(0)
            await self.interaction_message(inter, "voltou para o início da música.", rpc_update=True)
            return

        try:
            track = player.played.pop()
        except:
            track = player.queue.pop()
            player.last_track = None
            player.queue.appendleft(player.current)
        player.queue.appendleft(track)

        if inter.type.name != "application_command":
            player.command_log = f"{inter.author.mention} voltou para a música atual."
            await inter.response.defer()
        else:
            player.command_log = f"{inter.author.mention} voltou para a música atual."
            await inter.send("voltado com sucesso.", ephemeral=True)

        if player.loop == "current":
            player.loop = False
        player.is_previows_music = True
        if not player.current:
            await player.process_next()
        else:
            await player.stop()


    @check_voice()
    @has_source()
    @commands.slash_command(description=f"{desc_prefix}Votar para pular a música atual.")
    async def voteskip(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        embed = disnake.Embed()

        if inter.author in player.votes:
            embed.colour = disnake.Colour.red()
            embed.description = f"{inter.author.mention} **você já votou para pular a música atual.**"
            await send_message(inter, embed=embed)
            return

        embed.colour = disnake.Colour.green()

        txt = f"{inter.author.mention} **votou para pular a música atual (votos: {len(player.votes) + 1}/{self.bot.config.get('VOTE_SKIP_AMOUNT', 3)}).**"

        if len(player.votes) < self.bot.config.get('VOTE_SKIP_AMOUNT', 3):
            embed.description = txt
            player.votes.add(inter.author)
            player.command_log = txt
            await inter.send("voto adicionado!")
            await player.update_message()
            return

        player.command_log = f"{txt}\n**A anterior foi pulada imediatamente.**"
        await inter.send("voto adicionado!", ephemeral=True)
        await player.stop()


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(1, 5), commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Ajustar volume da música.")
    async def volume(
            self,
            inter: disnake.ApplicationCommandInteraction, *,
            value: int = commands.Param(name="nível", description="nível entre 5 a 150", min_value=5.0, max_value=150.0)
    ):

        player: LavalinkPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        update = False

        if value is None:

            view = VolumeInteraction(inter)

            embed.colour = self.bot.get_color(inter.guild.me)
            embed.description = "**Selecione o nível do volume abaixo:**"
            await inter.send(embed=embed, ephemeral=True, view=view)
            await view.wait()
            if view.volume is None:
                return

            value = view.volume
            update = True

        elif not 4 < value < 151:
            embed.description = "O volume deve estar entre **5** a **150**."
            return await inter.send(embed=embed, ephemeral=True)

        await player.set_volume(value)

        txt = [f"ajustou o volume para **{value}%**", f"Volume ajustado para **{value}**"]
        await self.interaction_message(inter, txt, update=update)


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Pausar a música.")
    async def pause(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        if player.paused:
            await send_message(inter, embed=embed)
            return

        await player.set_pause(True)

        txt = ["pausou a música.", "Musica pausada."]

        await self.interaction_message(inter, txt, rpc_update=True)


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Retomar/Despausar a música.")
    async def resume(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        if not player.paused:
            embed.description = "A música não está pausada."
            await send_message(inter, embed=embed)
            return

        await player.set_pause(False)

        txt = ["retomou a música.", "Música retomada"]
        await self.interaction_message(inter, txt, rpc_update=True)


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Avançar/Retomar a música para um tempo específico.")
    async def seek(
            self,
            inter: disnake.ApplicationCommandInteraction,
            position: str = commands.Param(name="tempo", description="Tempo para avançar/voltar (ex: 1:45 / 40 / 0:30)", autocomplete=seek_suggestions)
    ):

        embed = disnake.Embed(color=disnake.Colour.red())

        player: LavalinkPlayer = inter.player

        if player.current.is_stream:
            embed.description = "Você não pode usar este comando em uma livestream."
            await send_message(inter, embed=embed)
            return

        position = position.split(" | ")[0]

        seconds = string_to_seconds(position)

        if seconds is None:
            embed.description = "Você usou um tempo inválido! Use segundos (1 ou 2 digitos) ou no formato (minutos):(segundos)"
            return await send_message(inter, embed=embed)

        milliseconds = seconds * 1000

        if milliseconds < 0:
            milliseconds = 0

        try:
            await player.seek(milliseconds)

            if player.paused:
                await player.set_pause(False)

        except Exception as e:
            embed.description = f"Ocorreu um erro no comando\n```py\n{repr(e)}```."
            await send_message(inter, embed=embed)
            return

        txt = [
            f"{'avançou' if milliseconds > player.position else 'voltou'} o tempo da música para: {time_format(milliseconds)}",
            f"O tempo da música foi {'avançada' if milliseconds > player.position else 'retornada'} para: {time_format(milliseconds)}"
        ]
        await self.interaction_message(inter, txt, rpc_update=True)


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Selecionar modo de repetição entre: atual / fila ou desativar.")
    async def loop_mode(
            self,
            inter: disnake.ApplicationCommandInteraction,
            mode: Literal['current', 'queue', 'off'] = commands.Param(name="modo",
                description="current = Música atual / queue = fila / off = desativar"
            )
    ):

        player: LavalinkPlayer = inter.player

        if mode == player.loop:
            await self.interaction_message(inter, "Não teve alteração no modo de repetição atual.")
            return

        if mode == 'off':
            mode = False
            player.current.track_loops = 0

        elif mode == "current":
            player.current.track_loops = 0

        if mode:
            txt = [f"ativou a repetição da {'música' if mode == 'current' else 'fila'}.", f"Repetição da {'música' if mode == 'current' else 'fila'} ativada com sucesso."]
        else:
            txt = ['desativou a repetição.', "Repetição desativada."]

        player.loop = mode

        self.bot.loop.create_task(player.process_rpc())

        await self.interaction_message(inter, txt)


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Definir quantidade de repetições da música atual.")
    async def loop_amount(
            self,
            inter: disnake.ApplicationCommandInteraction,
            value: int = commands.Param(name="valor", description="número de repetições.")
    ):

        player: LavalinkPlayer = inter.player

        player.current.track_loops = value

        embed = disnake.Embed(color=self.bot.get_color(inter.guild.me))

        txt = f"{inter.author.mention} definiu a quantidade de repetições da música " \
              f"[`{(fix_characters(player.current.title, 25))}`]({player.current.uri}) para **{value}**."

        player.command_log = txt
        embed.description=f"**Quantidade de repetições [{value}] definida para a música:** [`{player.current.title}`]({player.current.uri})"
        embed.set_thumbnail(url=player.current.thumb)
        await inter.send(embed=embed, ephemeral=True)

        await player.update_message(rpc_update=True)


    @check_voice()
    @has_player()
    @is_dj()
    @commands.slash_command(description=f"{desc_prefix}Remover uma música específica da fila.")
    async def remove(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        embed = disnake.Embed(color=disnake.Colour.red())

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.send(embed=embed, ephemeral=True)
            return

        player: LavalinkPlayer = inter.player

        track = player.queue[index]

        player.queue.remove(track)

        embed = disnake.Embed(color=disnake.Colour.green())

        txt = f"{inter.author.mention} removeu a música [`{(fix_characters(track.title, 25))}`]({track.uri}) da fila."

        player.command_log = txt
        embed.description=f"**Música removida:** [`{track.title}`]({track.uri})"
        embed.set_thumbnail(url=track.thumb)
        await inter.send(embed=embed, ephemeral=True)

        await player.update_message()


    @check_voice()
    @has_player()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Readicionar as músicas tocadas na fila.")
    async def readd(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        if not player.played:
            embed.description = f"{inter.author.mention} **não há músicas tocadas.**"
            await inter.send(embed=embed, ephemeral=True)
            return

        embed.colour = disnake.Colour.green()
        txt = f"{inter.author.mention} **readicionou [{(qsize:=len(player.played))}] música(s) tocada(s) na fila.**"

        player.played.reverse()
        player.queue.extend(player.played)
        player.played.clear()

        player.command_log = txt
        embed.description = f"**você readicionou {qsize} música(s).**"
        await inter.send(embed=embed, ephemeral=True)
        await player.update_message()

        if not player.current:
            await player.process_next()
        else:
            await player.update_message()


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Pular para a música especificada.")
    async def skipto(
            self,
            inter: disnake.ApplicationCommandInteraction, *,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        embed = disnake.Embed(color=disnake.Colour.red())

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.send(embed=embed, ephemeral=True)
            return

        player: LavalinkPlayer = inter.player

        track = player.queue[index]

        player.queue.append(player.last_track)
        player.last_track = None

        if player.loop == "current":
            player.loop = False

        if index > 0:
            player.queue.rotate(0 - (index))

        embed.colour = disnake.Colour.green()

        player.command_log = f"{inter.author.mention} pulou para a música atual"
        embed.description = f"**Você pulou para a música:** [`{track.title}`]({track.uri})"
        embed.set_thumbnail(track.thumb)
        await inter.send(embed=embed, ephemeral=True)

        await player.stop()


    @check_voice()
    @has_source()
    @is_dj()
    @commands.slash_command(description=f"{desc_prefix}Move uma música para a posição especificada da fila.")
    async def move(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks),
            position: int = commands.Param(name="posição", description="Posição de destino na fila.", default=1)
    ):

        embed = disnake.Embed(colour=disnake.Colour.red())

        if position < 1:
            embed.description = f"{inter.author.mention}, {position} não é uma posição válida."
            await send_message(inter, embed=embed)
            return

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.send(embed=embed, ephemeral=True)
            return

        player: LavalinkPlayer = inter.player

        track = player.queue[index]

        player.queue.remove(track)

        player.queue.insert(int(position) - 1, track)

        txt = f"{inter.author.mention} moveu a música [`{fix_characters(track.title, limit=25)}`]({track.uri}) para a posição **[{position}]** da fila."

        embed = disnake.Embed(color=disnake.Colour.green())

        embed.description = f"**A música foi movida para a posição {position} da fila:** [`{fix_characters(track.title)}`]({track.uri})"
        embed.set_thumbnail(url=track.thumb)
        player.command_log = txt
        await inter.send(embed=embed, ephemeral=True)

        await player.update_message()


    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Rotacionar a fila para a música especificada.")
    async def rotate(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(
                name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        embed = disnake.Embed(colour=disnake.Colour.red())

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.send(embed=embed, ephemeral=True)
            return

        player: LavalinkPlayer = inter.player

        track = player.queue[index]

        if index <= 0:
            embed.description = f"{inter.author.mention} **a música **[`{track.title}`]({track.uri}) já é a próxima da fila."
            await inter.send(embed=embed, ephemeral=True)
            return

        player.queue.rotate(0 - (index))

        embed.colour = disnake.Colour.green()

        txt = f"{inter.author.mention} rotacionou a fila para a música [`{(fix_characters(track.title, limit=25))}`]({track.uri})."

        embed.description = f"**Fila rotacionada para a música:** [`{track.title}`]({track.uri})."
        embed.set_thumbnail(url=track.thumb)
        player.command_log = txt
        await inter.send(embed=embed, ephemeral=True)

        await player.update_message()


    @check_voice()
    @has_source()
    @is_dj()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Ativar/Desativar o efeito nightcore (Música acelerada com tom mais agudo).")
    async def nightcore(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        player.nightcore = not player.nightcore

        if player.nightcore:
            await player.set_timescale(pitch=1.2, speed=1.1)
            txt = ["ativou", "ativado"]
        else:
            try:
                del player.filters["timescale"]
            except:
                pass
            await player.update_filters()
            txt = ["desativou", "desativado"]

        txt = [f"{txt[0]} o efeito nightcore.", f"Efeito nightcore {txt[1]}."]

        await self.interaction_message(inter, txt, rpc_update=True)


    @has_source()
    @commands.slash_command(description=f"{desc_prefix}Reenvia a mensagem do player com a música atual.")
    async def nowplaying(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        if player.static:
            await inter.send("este comando não pode ser usado no modo fixo do player.", ephemeral=True)
            return
        
        if player.has_thread:
            embed = disnake.Embed(
                    color=self.bot.get_color(inter.guild.me),
                description=f"este comando não pode ser usado com uma conversa ativa na [mensagem]({player.message.jump_url}) do player."
                )
            await inter.send(embed=embed, ephemeral=True)
            return

        await player.destroy_message()
        await player.invoke_np()

        await inter.send("Player reenviado com sucesso!", ephemeral=True)


    @has_player()
    @is_dj()
    @commands.user_command(name="add dj")
    async def adddj_u(self, inter: disnake.UserCommandInteraction):
        await self.add_dj(inter, user=inter.target)


    @has_player()
    @is_dj()
    @commands.slash_command(description=f"{desc_prefix}Adicionar um membro à lista de DJ's na sessão atual do player.")
    async def add_dj(
            self,
            inter: disnake.ApplicationCommandInteraction, *,
            user: disnake.Member = commands.Param(name="membro", description="Membro a ser adicionado.")
    ):

        error_text = None

        if user == inter.author:
            error_text = "Você não pode adicionar a si mesmo na lista de DJ's."
        elif user.guild_permissions.manage_channels:
            error_text = f"você não pode adicionar o membro {user.mention} na lista de DJ's (ele(a) possui permissão de **gerenciar canais**)."
        elif user in inter.player.dj:
            error_text = f"O membro {user.mention} já está na lista de DJ's"

        if error_text:
            embed = disnake.Embed(color=disnake.Colour.red(), description=error_text)
            await send_message(inter, embed=embed)
            return

        inter.player.dj.add(user)
        text = [f"adicionou {user.mention} à lista de DJ's.", f"{user.mention} foi adicionado à lista de DJ's."]

        if (inter.player.static and inter.channel == inter.player.text_channel) or isinstance(inter.application_command, commands.InvokableApplicationCommand):
            await inter.send(f"{inter.target.mention} adicionado à lista de DJ's!")

        await self.interaction_message(inter, txt=text, update=True)


    @check_voice()
    @has_player()
    @is_dj()
    @commands.slash_command(description=f"{desc_prefix}Parar o player e me desconectar do canal de voz.")
    async def stop(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        player.command_log = f"{inter.author.mention} **parou o player!**"
        embed.description = f"**{inter.author.mention} parou o player!**"
        await inter.send(embed=embed, ephemeral=player.static or player.has_thread)

        await player.destroy()


    @has_player()
    @commands.slash_command(name="queue")
    async def q(self, inter):
        pass


    @check_voice()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @q.sub_command(name="shuffle", description=f"{desc_prefix}Misturar as músicas da fila")
    async def shuffle_(self, inter: disnake.ApplicationCommandInteraction):

        player = inter.player

        if len(player.queue) < 3:
            embed = disnake.Embed(color=disnake.Colour.red())
            embed.description = "A fila tem que ter no mínimo 3 músicas para ser misturada."
            await send_message(inter, embed=embed)
            return

        shuffle(player.queue)

        txt = [f"misturou as músicas da fila.",
               "músicas misturadas com sucesso."]

        await self.interaction_message(inter, txt)


    @check_voice()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(1, 5), commands.BucketType.guild)
    @q.sub_command(description=f"{desc_prefix}Inverter a ordem das músicas na fila")
    async def reverse(self, inter: disnake.ApplicationCommandInteraction):
        
        player: LavalinkPlayer = inter.player

        if len(player.queue) < 2:
            embed = disnake.Embed(colour=disnake.Colour.red())
            embed.description = "A fila tem que ter no mínimo 2 músicas para inverter a ordem."
            await send_message(inter, embed=Embed)
            return

        player.queue.reverse()

        text = [f"inverteu a ordem das músicas na fila.", "Fila invertida com sucesso!"]
        await self.interaction_message(inter, txt=text, update=True)


    @q.sub_command(description=f"{desc_prefix}Exibir as músicas que estão na fila.")
    @commands.max_concurrency(1, commands.BucketType.member)
    async def show(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        if not player.queue:
            embedvc = disnake.Embed(
                colour=disnake.Colour.red(),
                description='Não há músicas na fila no momento.'
            )
            await send_message(inter, embed=embedvc)
            return

        view = QueueInteraction(player, inter.author)
        embed = view.embed

        await inter.send(embed=embed, view=view, ephemeral=True)

        await view.wait()


    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.slash_command(description=f"{desc_prefix}Limpar a fila de música.")
    async def clear(
            self,
            inter: disnake.ApplicationCommandInteraction,
            song_name: str = commands.Param(name="nome_da_música",description="incluir nome que tiver na música.", default=None),
            song_author: str = commands.Param(name="nome_do_autor", description="Incluir nome que tiver no autor da música.", autocomplete=queue_author, default=None),
            user: disnake.Member = commands.Param(name='usuário', description="Incluir músicas pedidas pelo usuário selecionado.", default=None),
            playlist: str = commands.Param(description="Incluir nome que tiver na playlist.", autocomplete=queue_playlist, default=None),
            time_below: str = commands.Param(name="duração_abaixo_de", description="incluir músicas com duração abaixo do tempo definido (ex. 1:23).", default=None),
            time_above: str = commands.Param(name="duração_acima_de", description="incluir músicas com duração acima do tempo definido (ex. 1:45).", default=None)
    ):

        if not inter.player.queue:
            await inter.send("Não há musicas na fila.", ephemeral=True)
            return

        filters = []

        if song_name:
            filters.append('song_name')
        if song_author:
            filters.append('song_author')
        if user:
            filters.append('user')
        if playlist:
            filters.append('playlist')

        if time_below and time_above:
            raise GenericError("Você deve escolher apenas uma das opções: **duração_abaixo_de** ou **duração_acima_de**.")

        if time_below:
            filters.append('time_below')
            time_below = string_to_seconds(time_below) * 1000
        if time_above:
            filters.append('time_above')
            time_above = string_to_seconds(time_above) * 1000

        if not filters:
            inter.player.queue.clear()
            txt = ['limpou a fila de música.', '**Fila limpa com sucesso.**']

        else:

            deleted_tracks = 0

            for t in list(inter.player.queue):

                temp_filter = list(filters)

                if 'time_below' in temp_filter and t.duration <= time_below:
                    temp_filter.remove('time_below')

                elif 'time_above' in temp_filter and t.duration >= time_above:
                    temp_filter.remove('time_above')

                if 'song_name' in temp_filter and song_name.lower() in t.title.lower():
                    temp_filter.remove('song_name')

                if 'song_author' in temp_filter and song_author.lower() in t.author.lower():
                    temp_filter.remove('song_author')

                if 'user' in temp_filter and user == t.requester:
                    temp_filter.remove('user')

                try:
                    if 'playlist' in temp_filter and playlist == t.playlist['name']:
                        temp_filter.remove('playlist')
                except:
                    pass

                if not temp_filter:
                    inter.player.queue.remove(t)
                    deleted_tracks += 1

            if not deleted_tracks:
                await inter.send("Nenhuma música encontrada!", ephemeral=True)
                return

            txt = [f"removeu {deleted_tracks} música(s) da fila via clear.",
                   f"{deleted_tracks} música(s) removidas da fila com sucesso."]

        await self.interaction_message(inter, txt)


    @has_player()
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.has_guild_permissions(manage_guild=True)
    @commands.slash_command(description=f"{desc_prefix}Ativar/Desativar o modo interrupta do player (24/7).")
    async def nonstop(self, inter: disnake.ApplicationCommandInteraction):

        player: LavalinkPlayer = inter.player

        player.nonstop = not player.nonstop

        texts = ["ativou", "ativado"] if player.nonstop else ["desativou", "desativado"]

        text = [f"{texts[0]} o modo interrupto do player.", f"Modo interrupto {texts[1]} com sucesso!"]

        if not len(player.queue):
            player.queue.extend(player.played)
            player.played.clear()

        if player.current:
            await self.interaction_message(inter, txt=text, update=True)
            return

        await self.interaction_message(inter, text)

        await player.process_next()


    @check_voice()
    @has_player()
    @is_dj()
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.slash_command(description=f"{desc_prefix}Migrar o player para outro servidor de música.")
    async def change_node(
            self,
            inter: disnake.ApplicationCommandInteraction,
            node: str = commands.Param(name="servidor", description="Servidor de música", autocomplete=node_suggestions)
    ):

        if not node in self.bot.music.nodes:
            raise GenericError(f"O servidor de música **{node}** não foi encontrado.")

        if node == inter.player.node.identifier:
            raise GenericError(f"O player já está no servidor de música **{node}**.")

        await inter.player.change_node(node)

        txt = [f"Migrou o player para o servidor de música **{node}**",
               f"**O player foi migrado para o servidor de música:** `{node}`"]

        await self.interaction_message(inter, txt)


    @commands.Cog.listener("on_message_delete")
    async def player_message_delete(self, message: disnake.Message):

        if not message.guild:
            return

        player: LavalinkPlayer = self.bot.music.players.get(message.guild.id)

        try:
            if message.id != player.message.id:
                return
        except AttributeError:
            return

        thread = self.bot.get_channel(message.id)

        if not thread:
            return

        player.message = None
        await thread.edit(archived=True, locked=True, name=f"arquivado: {thread.name}")


    @commands.Cog.listener()
    async def on_ready(self):

        for player in self.bot.music.players.values():
            try:
                await player.connect(player.channel_id)
            except:
                traceback.print_exc()


    @commands.Cog.listener("on_button_click")
    async def player_controller(self, interaction: disnake.MessageInteraction):

        player: LavalinkPlayer = self.bot.music.players.get(interaction.guild.id)

        if not player or interaction.message != player.message:
            return

        if player.interaction_cooldown:
            await interaction.response.send_message("O player está em cooldown, tente novamente em instantes.",
                                                    ephemeral=True)
            return

        vc = self.bot.get_channel(player.channel_id)

        control = interaction.data.custom_id[12:]

        kwargs = {}

        if control == "help":
            embed = disnake.Embed(
                description="📘 **IFORMAÇÕES SOBRE OS BOTÕES** 📘\n\n"
                            "⏯️ `= Pausar/Retomar a música.`\n"
                            "⏮️ `= Voltar para a música tocada anteriormente.`\n"
                            "⏭️ `= Pular para a próxima música.`\n"
                            "🔀 `= Misturar as músicas da fila.`\n"
                            "🎶 `= Adicionar música.`\n"
                            # "🇳 `= Ativar/Desativar o efeito Nightcore`\n"
                            "⏹️ `= Parar o player e me desconectar do canal.`\n"
                            "🔊 `= Ajustar volume.`\n"
                            "🔁 `= Ativar/Desativar repetição.`\n"
                            "📑 `= Exibir a fila de música.`\n",
                color=self.bot.get_color(interaction.guild.me)
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        subcmd = None

        if control == "add_song":

            await interaction.response.send_modal(
                title="Adicionar música",
                custom_id="add_song",
                components=[
                    disnake.ui.TextInput(
                        style=disnake.TextInputStyle.short,
                        label="Nome/link da música.",
                        placeholder="Nome ou link do youtube/spotify/soundcloud etc.",
                        custom_id="song_input",
                        max_length=90,
                    )
                ],
            )

            try:

                modal_inter: disnake.ModalInteraction = await self.bot.wait_for(
                    "modal_submit", check=lambda i: i.author == interaction.author and i.custom_id == "add_song"
                )

                query = modal_inter.text_values["song_input"]

                control = "play"

                kwargs.update(
                    {
                        "query": query,
                        "position": 0,
                        "options": False,
                        "manual_selection": False,
                        "source": "ytsearch",
                        "repeat_amount": 0,
                        "hide_playlist": False,
                        "server": None
                    }
                )

                # TODO: Ver um método melhor de setar o interaction.player (ModalInteraction não dá pra setar)...
                interaction.token = modal_inter.token
                interaction.id = modal_inter.id
                interaction.response = modal_inter.response

            except asyncio.TimeoutError:
                return

        elif interaction.user not in vc.members:
            embed = disnake.Embed(
                description=f"Você deve estar no canal <#{vc.id}> para usar os botões do player.",
                color=disnake.Colour.red()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        elif control == "volume":
            kwargs = {"value": None}

        elif control == "queue":
            subcmd = "show"

        elif control == "shuffle":
            subcmd = "shuffle"
            control = "queue"

        elif control == "seek":
            kwargs = {"position": None}

        elif control == "playpause":
            control = "pause" if not player.paused else "resume"

        elif control == "loop_mode":

            if player.loop == "current":
                kwargs['mode'] = 'queue'
            elif player.loop == "queue":
                kwargs['mode'] = 'off'
            else:
                kwargs['mode'] = 'current'

        cmd = self.bot.get_slash_command(control)

        if not cmd:
            await interaction.response.send_message(f"comando {control} não encontrado/implementado.", ephemeral=True)
            return

        interaction.player = player

        try:

            await check_cmd(cmd, interaction)

            if subcmd:
                cmd = cmd.children.get(subcmd)
                await check_cmd(cmd, interaction)

            await cmd(interaction, **kwargs)

            player.interaction_cooldown = True
            await asyncio.sleep(1)
            player.interaction_cooldown = False

        except Exception as e:
            self.bot.dispatch('slash_command_error', interaction, e)


    @commands.Cog.listener("on_message")
    async def song_requests(self, message: disnake.Message):

        if message.is_system():
            return

        if message.author.bot:
            return

        try:
            data = await self.bot.db.get_data(message.guild.id, db_name='guilds')
        except AttributeError:
            return
        
        player: LavalinkPlayer = self.bot.music.players.get(message.guild.id)

        if player and isinstance(message.channel, disnake.Thread) and not player.static:

            text_channel = message.channel

        else:

            static_player = data['player_controller']

            channel_id = static_player['channel']

            if not channel_id or (static_player['message_id'] != str(message.channel.id) and str(message.channel.id) != channel_id):
                return

            text_channel = self.bot.get_channel(int(channel_id))

            if not text_channel or not text_channel.permissions_for(message.guild.me).send_messages:
                return

        if message.is_system():
            #correção temporária de uma possivel mensagem de sistema chegar até aqui ao iniciar uma thread.
            return

        if not message.content:
            await message.delete()
            await message.channel.send(f"{message.author.mention} você deve enviar um link/nome da música.", delete_after=9)
            return

        try:
            await self.song_request_concurrency.acquire(message)
        except:
            await message.delete()
            await message.channel.send(f"{message.author.mention} você deve aguardar seu pedido de música anterior carregar...", delete_after=10)
            return

        message.content = message.content.strip("<>")

        msg = None

        error = None

        try:

            if not URL_REG.match(message.content):
                message.content = f"ytsearch:{message.content}"

            elif "&list=" in message.content:

                view = SelectInteraction(
                    user = message.author,
                    opts = [
                        disnake.SelectOption(label="Música", emoji="🎵", description="Carregar apenas a música do link.", value="music"),
                        disnake.SelectOption(label="Playlist", emoji="🎶", description="Carregar playlist com a música atual.", value="playlist"),
                    ], timeout=30)

                embed = disnake.Embed(
                    description="**O link contém vídeo com playlist.**\n`selecione uma opção em até 30 segundos para prosseguir.`",
                    color=self.bot.get_color(message.guild.me)
                )

                msg = await message.channel.send(message.author.mention,embed=embed, view=view)

                await view.wait()

                try:
                    await view.inter.response.defer()
                except:
                    pass

                if view.selected == "music":
                    message.content = YOUTUBE_VIDEO_REG.match(message.content).group()

            await self.parse_song_request(message, text_channel, data, response=msg)

            if not isinstance(message.channel, disnake.Thread):
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
            raise GenericError(f"você deve entrar em um canal de voz para pedir uma música.")

        try:
            if message.guild.me.voice.channel != message.author.voice.channel:
                raise GenericError(f"Você deve entrar no canal <#{message.guild.me.voice.channel.id}> para pedir uma música.")
        except AttributeError:
            pass

        tracks, node = await self.get_tracks(message.content, message.author)

        player: LavalinkPlayer = self.bot.music.get_player(
            guild_id=message.guild.id,
            cls=LavalinkPlayer,
            requester=message.author,
            guild=message.guild,
            channel=text_channel,
            static=True,
            cog=self,
            skin=data["player_controller"]["skin"]
        )

        if not player.message:
            try:
                cached_message = await text_channel.fetch_message(int(data['player_controller']['message_id']))
            except:
                cached_message = await send_idle_embed(message, bot=self.bot)
                data['player_controller']['message_id'] = str(cached_message.id)
                await self.bot.db.update_data(message.guild.id, data, db_name='guilds')

            player.message = cached_message

        embed = disnake.Embed(color=self.bot.get_color(message.guild.me))

        try:
            player.queue.extend(tracks.tracks)
            if isinstance(message.channel, disnake.Thread):
                embed.description = f"> 🎶 **┃ Playlist adicionada:** [`{tracks.data['playlistInfo']['name']}`]({message.content})\n" \
                                    f"> ✋ **┃ Pedido por:** {message.author.mention}\n" \
                                    f"> 🎼 **┃ Música(s):** `[{len(tracks.tracks)}]`"
                embed.set_thumbnail(url=tracks.tracks[0].thumb)
                if response:
                    await response.edit(content=None, embed=embed, view=None)
                else:
                    await message.channel.send(embed=embed)

            else:
                player.command_log = f"{message.author.mention} adicionou a playlist " \
                                     f"[`{fix_characters(tracks.data['playlistInfo']['name'], 20)}`]({tracks.tracks[0].playlist['url']}) `({len(tracks.tracks)})`."


        except AttributeError:
            player.queue.append(tracks[0])
            if isinstance(message.channel, disnake.Thread):
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
                player.command_log = f"{message.author.mention} adicionou [`{fix_characters(tracks[0].title, 20)}`]({tracks[0].uri}) `({duration})`."

        if not player.is_connected:
            await player.connect(message.author.voice.channel.id)

        if not player.current:
            await player.process_next()
        else:
            await player.update_message()

        await asyncio.sleep(1)


    def cog_unload(self):

        for m in list(sys.modules):
            if m.startswith("utils.music"):
                del sys.modules[m]
    
    async def cog_before_message_command_invoke(self, inter):
        await self.cog_before_slash_command_invoke(inter)


    async def cog_before_user_command_invoke(self, inter):
        await self.cog_before_slash_command_invoke(inter)


    async def cog_before_slash_command_invoke(self, inter):

        try:
            inter.player
        except AttributeError:
            inter.player = self.bot.music.players.get(inter.guild.id)


    async def interaction_message(self, inter: disnake.Interaction, txt, update=False, rpc_update=False):

        try:
            txt, txt_ephemeral = txt
        except:
            txt_ephemeral = False

        component_interaction = isinstance(inter, disnake.MessageInteraction)

        inter.player.command_log = f"{inter.author.mention} {txt}"
        await inter.player.update_message(interaction=False if (update or not component_interaction) else inter, rpc_update=rpc_update)

        if not component_interaction:

            txt = f"{inter.author.mention} **{txt}**"

            embed = disnake.Embed(color=disnake.Colour.green(),
                                description=txt_ephemeral or txt)

            if not inter.response.is_done():
                await inter.send(embed=embed, ephemeral=True)


    async def process_nodes(self):

        await self.bot.wait_until_ready()

        for k,v in self.bot.config.items():

            if not k.lower().startswith("lavalink_node_"):
                continue
            try:
                self.bot.loop.create_task(self.connect_node(json.loads(v)))
            except Exception as e:
                print(f"Falha ao adicionar node: {k}, erro: {repr(e)}")

        if self.bot.config['START_LOCAL_LAVALINK'] is True:
            self.bot.loop.create_task(self.connect_local_lavalink())


    async def connect_node(self, data: dict):

        if data["identifier"] in self.bot.music.nodes:
            return

        data['rest_uri'] = ("https" if data.get('secure') else "http") + f"://{data['host']}:{data['port']}"
        data['user_agent'] = UserAgent().random
        search = data.pop("search", True)
        max_retries = data.pop('retries', 0)
        node_website = data.pop('website', '')

        if max_retries:

            backoff = 7
            retries = 1

            print(f"{self.bot.user} - Iniciando servidor de música: {data['identifier']}")

            while not self.bot.is_closed():
                if retries >= max_retries:
                    print(f"{self.bot.user} - Todas as tentativas de conectar ao servidor [{data['identifier']}] falharam.")
                    return
                else:
                    try:
                        async with self.bot.session.get(data['rest_uri'], timeout=10) as r:
                            break
                    except Exception:
                        backoff += 2
                        #print(f'{self.bot.user} - Falha ao conectar no servidor [{data["identifier"]}], nova tentativa [{retries}/{max_retries}] em {backoff} segundos.')
                        await asyncio.sleep(backoff)
                        retries += 1
                        continue

        node = await self.bot.music.initiate_node(auto_reconnect=False, **data)
        node.search = search
        node.website = node_website


    @wavelink.WavelinkMixin.listener("on_node_connection_closed")
    async def node_connection_closed(self, node: wavelink.Node):

        retries = 0
        backoff = 7

        for player in list(node.players.values()):

            try:

                new_node: wavelink.Node = self.bot.music.get_best_node()

                if not new_node:

                    try:
                        await player.text_channel.send("O player foi finalizado por falta de servidores de música...", delete_after=11)
                    except:
                        pass
                    await player.destroy()
                    continue

                await player.change_node(new_node.identifier)
                await player.update_message()

            except:

                traceback.print_exc()
                continue

        print(f"{self.bot.user} - [{node.identifier}] Conexão perdida - reconectando em {backoff} segundos.")

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
            print(f'{self.bot.user} - Falha ao reconectar no servidor [{node.identifier}] nova tentativa em {backoff} segundos. Erro: {error}')
            await asyncio.sleep(backoff)
            retries += 1
            continue


    @wavelink.WavelinkMixin.listener("on_websocket_closed")
    async def node_ws_voice_closed(self, node, payload: wavelink.events.WebsocketClosed):

        if payload.code == 1000:
            return

        player: LavalinkPlayer = payload.player

        if payload.code == 4014:

            if player.guild.me.voice:
                return

            if player.static:
                player.command_log = "O player foi desligado por perca de conexão com o canal de voz."
            else:
                embed = disnake.Embed(description="**Desligando player por perca de conexãoo com o canal de voz.**",
                                      color=self.bot.get_color(player.guild.me))
                self.bot.loop.create_task(player.text_channel.send(embed=embed, delete_after=7))
            await player.destroy()
            return

        if payload.code in [
            4000, # internal error
            1006,
            4005 # Already authenticated.
        ]:
            await asyncio.sleep(3)
            await player.connect(player.channel_id)
            return

        # fix para dpy 2x (erro ocasionado ao mudar o bot de canal)
        if payload.code == 4006:

            await player.connect(player.channel_id)
            return

        print(f"Erro no canal de voz! guild: {player.guild.name} | server: {payload.player.node.identifier} | reason: {payload.reason} | code: {payload.code}")


    @wavelink.WavelinkMixin.listener('on_track_exception')
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


    @wavelink.WavelinkMixin.listener()
    async def on_node_ready(self, node: wavelink.Node):
        print(f'{self.bot.user} - Servidor de música: [{node.identifier}] está pronto para uso!')


    @wavelink.WavelinkMixin.listener('on_track_start')
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

        await player.invoke_np(force=True if (not player.loop or not player.is_last_message()) else False, rpc_update=True)


    @wavelink.WavelinkMixin.listener()
    async def on_track_end(self, node: wavelink.Node, payload: wavelink.TrackEnd):

        player: LavalinkPlayer = payload.player

        if player.locked:
            return

        player.update_player = False

        if payload.reason == "FINISHED":
            player.command_log = ""
        elif payload.reason == "STOPPED":
            pass
        else:
            return

        await player.track_end()

        await player.process_next()


    async def get_tracks(
            self, query: str, user: disnake.Member, node: wavelink.Node=None,
            track_loops=0, hide_playlist=False):

        if not node:
            node = self.bot.music.get_best_node()

            if not node:
                raise GenericError("Não há servidores de música disponível.")

        tracks = await process_spotify(self.bot, user, query)

        if not tracks:

            if node.search:
                node_search = node
            else:
                try:
                    node_search = sorted([n for n in self.bot.music.nodes.values() if n.search and n.available], key=lambda n: len(n.players))[0]
                except IndexError:
                    node_search = node

            tracks = await node_search.get_tracks(query)

        if not tracks:
            raise GenericError("Não houve resultados para sua busca.")

        if isinstance(tracks, list):

            if isinstance(tracks[0], wavelink.Track):
                tracks = [LavalinkTrack(track.id, track.info, requester=user, track_loops=track_loops) for track in tracks]

        else:

            if not isinstance(tracks, SpotifyPlaylist):

                try:
                    if tracks.tracks[0].info.get("class") == "YoutubeAudioTrack":
                        query = f"https://www.youtube.com/playlist?list={parse.parse_qs(parse.urlparse(query).query)['list'][0]}"
                except IndexError:
                    pass

                playlist = {
                    "name": tracks.data['playlistInfo']['name'],
                    "url": query
                } if not hide_playlist else {}

                tracks.tracks = [LavalinkTrack(t.id, t.info, requester=user, playlist=playlist) for t in tracks.tracks]

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

        if player.exiting:
            return

        if thread.id != player.message.id:
            return


    @commands.Cog.listener("on_thread_join")
    async def join_thread_request(self, thread: disnake.Thread):

        player: LavalinkPlayer = self.bot.music.players.get(thread.guild.id)

        if not player or player.static or player.message.id != thread.id:
            return

        if thread.guild.me.id in thread._members:
            return

        embed = disnake.Embed(
            description="**Essa conversa será usada temporariamente para pedir músicas apenas enviando "
                        "o nome/link sem necessidade de usar comando.**",
            color=self.bot.get_color(thread.guild.me)
        )

        await thread.send(embed=embed)


    @commands.Cog.listener("on_voice_state_update")
    async def player_vc_disconnect(
            self,
            member: disnake.Member,
            before: disnake.VoiceState,
            after: disnake.VoiceState
    ):

        if member.bot: # ignorar bots
            return

        player: LavalinkPlayer = self.bot.music.players.get(member.guild.id)

        if not player:
            return

        try:
            player.members_timeout_task.cancel()
        except:
            pass

        if not player.nonstop and player.guild.me.voice and not any(
                m for m in player.guild.me.voice.channel.members if not m.bot):
            player.members_timeout_task = self.bot.loop.create_task(player.members_timeout())
        else:
            player.members_timeout_task = None

        # rich presence stuff

        if player.exiting:
            return

        if not after or before.channel != after.channel:

            try:
                vc = player.guild.me.voice.channel
            except AttributeError:
                vc = before.channel

            self.bot.loop.create_task(player.process_rpc(vc, users=[member], close=True))
            self.bot.loop.create_task(player.process_rpc(vc, users=[m for m in vc.members if m != member and not m.bot]))


    async def reset_controller_db(self, guild_id: int, data: dict, inter: disnake.ApplicationCommandInteraction = None):

        data['player_controller']['channel'] = None
        data['player_controller']['message_id'] = None
        player = self.bot.music.players.get(guild_id)
        if player:
            player.static = False
            player.text_channel = inter.channel.parent if isinstance(inter.channel, disnake.Thread) else inter.channel
        await self.bot.db.update_data(guild_id, data, db_name='guilds')

def setup(bot: BotCore):
    bot.add_cog(Music(bot))
