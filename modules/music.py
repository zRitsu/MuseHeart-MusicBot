import disnake
from disnake.ext import commands
import traceback
import wavelink
import asyncio
from fake_useragent import UserAgent
import sys
from random import shuffle
from aiohttp import ClientSession
from typing import Literal, Union
import humanize
from utils.client import BotCore

from utils.music.errors import GenericError
from utils.music.spotify import SpotifyTrack, SpotifyPlaylist, process_spotify
from utils.music.checks import check_voice, user_cooldown, has_player, has_source, is_requester, is_dj, require_database
from utils.music.models import CustomPlayer, CustomTrack
from utils.music.converters import time_format, fix_characters, string_to_seconds, get_track_index, URL_REG, YOUTUBE_VIDEO_REG, search_suggestions, queue_tracks, seek_suggestions, queue_author, queue_playlist
from utils.music.interactions import VolumeInteraction, QueueInteraction, send_message, SongSelect

try:
    from test import Tests
except:
    pass

# Caso tennha servidores do lavalink externo, habilite as linhas abaiuxo e adicione/modifique de acordo. (não recomendo adicionar isso  na replit)
lavalink_servers = [

    # {
    #    'host': '127.0.0.1', # ip ou link (não inclua http:// ou https://)
    #    'port': 2333,
    #    'password': 'senhadoteulavalink',
    #    'identifier': 'SERVER 1',
    #    'region': 'us_central',
    #    'secure': False,
    # },

    # {
    #    'host': 'lavalink.freyacodes.com',
    #    'port': 80,
    #    'password': 'senha',
    #    'identifier': 'SERVER 2',
    #    'region': 'us_central',
    #    'secure': False,
    # },

]

PlayOpts = commands.option_enum({"Misturar Playlist": "shuffle", "Inverter Playlist": "reversed"})
SearchSource = commands.option_enum({"Youtube": "ytsearch", "Soundcloud": "scsearch"})


class Music(commands.Cog, wavelink.WavelinkMixin):

    def __init__(self, bot: BotCore):

        self.bot = bot

        self.msg_ad = bot.config.get("link")

        self.bot.loop.create_task(self.process_nodes())

        self.song_request_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.member, wait=False)

        try:
            if not hasattr(bot, 'tests') or not bot.tests:
                bot.tests = Tests()
        except:
            bot.tests = None

    @check_voice()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
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

        await self.play(inter, query=query, position=0, source="ytsearch", search=False)

    @check_voice()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.message_command(name="add to queue")
    async def message_play(self, inter: disnake.MessageInteraction):

        if not inter.target.content:
            emb = disnake.Embed(description=f"Não há texto na [mensagem]({inter.target.jump_url}) selecionada...", color=disnake.Colour.red())
            await inter.response.send_message(embed=emb, ephemeral=True)
            return

        await self.play(inter, query=inter.target.content, position=0, source="ytsearch", search=False)

    @check_voice()
    @commands.dynamic_cooldown(user_cooldown(2, 5), commands.BucketType.member)
    @commands.slash_command(name="play", description="Tocar música em um canal de voz.")
    async def play(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="busca", desc="Nome ou link da música.", autocomplete=search_suggestions), *,
            position: int = commands.Param(name="posição", description="Colocar a música em uma posição específica", default=0),
            options: PlayOpts = commands.Param(name="opções" ,description="Opções para processar playlist", default=False),
            search: bool = commands.Param(name="selecionar", description="Escolher uma música manualmente entre os resultados encontrados", default=False),
            process_all: bool = commands.Param(name="carregar_todos", description="Carregar todas as músicas do link (útil caso seja video com playlist).", default=False),
            source: SearchSource = commands.Param(name="fonte", description="Selecionar site para busca de músicas (não links)", default="ytsearch"),
    ):

        try:
            static_player = inter.guild_data['player_controller']
        except:
            static_player = None
        ephemeral = False
        channel = inter.channel

        if (inter.player and isinstance(inter.application_command, (commands.InvokableUserCommand, commands.InvokableMessageCommand))) or \
                (inter.guild_data and str(inter.channel.id) == static_player['channel']):
            ephemeral = True

        await inter.response.defer(ephemeral=ephemeral)

        try:
            tracks, node = await self.get_tracks(query, inter.user, source=source, process_all=process_all)
        except Exception as e:
            await inter.edit_original_message(content=f"**Ocorreu um erro:** ```py\n{e}```")
            return

        player: CustomPlayer = self.bot.wavelink.get_player(guild_id=inter.guild.id, cls=CustomPlayer, requester=inter.author, guild=inter.guild, channel=channel,
                                                            node_id=node.identifier, cog=self, static=True if (static_player and static_player['channel']) else False)

        if static_player and not player.message:
            try:
                channel = inter.bot.get_channel(int(static_player['channel']))
                if not channel:
                    inter.guild_data['player_controller']['channel'] = None
                    inter.guild_data['player_controller']['message_id'] = None
                    await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name='guilds')
                    player.static = False
                else:
                    try:
                        message = await channel.fetch_message(int(static_player.get('message_id')))
                    except:
                        message = await self.send_idle_embed(inter.channel)
                        inter.guild_data['player_controller']['message_id'] = str(message.id)
                        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name='guilds')
                    player.message = message
                    if isinstance(inter.channel, disnake.Thread):
                        player.text_channel = inter.channel.parent
            except Exception:
                pass

            if str(inter.channel.id) == static_player["channel"]:
                ephemeral = True

        pos_txt = ""

        embed = disnake.Embed(color=disnake.Colour.red())

        embed.colour = inter.guild.me.color

        position-=1

        if isinstance(tracks, list):

            if search and len(tracks) > 1:

                embed.description=f"**Selecione uma música abaixo**"
                view = SongSelect(tracks)
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

            if ephemeral:
                player.command_log = f"{inter.author.mention} adicionou [`{fix_characters(track.title, 20)}`]({track.uri}){pos_txt} `({duration})`."

            embed.description = f"**Música adicionada{pos_txt}:\n[`{track.title}`]({track.uri})**\n\n`{track.author}` | `{duration}`"
            embed.set_thumbnail(url=track.thumb)

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

                pos_txt = f" na posição {position + 1} da fila"

            if ephemeral:
                player.command_log = f"{inter.author.mention} adicionou a playlist [`{fix_characters(tracks.data['playlistInfo']['name'], 20)}`]({query}){pos_txt} `({len(tracks.tracks)})`."

            embed.description = f"**Playlist adicionada{pos_txt}:**\n[`{tracks.data['playlistInfo']['name']}`]({query})\n\n`[{len(tracks.tracks)}] Música(s)`"
            embed.set_thumbnail(url=tracks.tracks[0].thumb)

        if self.msg_ad:
            embed.description += f" | {self.msg_ad}"

        if not search:
            await inter.edit_original_message(embed=embed)

        if not player.is_connected:
            await player.connect(inter.author.voice.channel.id)

        if not player.current:
            await player.process_next()
        else:
            await player.update_message()

    @check_voice()
    @has_source()
    @is_requester()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(description="Pular a música atual que está tocando.")
    async def skip(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        if not len(player.queue):
            await send_message(inter, embed=disnake.Embed(description="**Não há músicas na fila...**",
                                                             color=disnake.Colour.red()), ephemeral=True)
            return

        if inter.type.name != "application_command":
            player.command_log = f"{inter.author.mention} pulou a música."
            await inter.response.defer()
        else:
            if player.static and player.text_channel == inter.channel:
                player.command_log = f"{inter.author.mention} pulou a música."
                ephemeral = True
            else:
                ephemeral = False
            embed = disnake.Embed(description=f"⏭️** ┃ Música pulada:** [`{fix_characters(player.current.title, 30)}`]({player.current.uri})", color=inter.guild.me.color)
            await inter.response.send_message(embed=embed, ephemeral=ephemeral)


        if player.loop == "current":
            player.loop = False

        await player.stop()

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(description="Voltar para a música anterior (ou para o início da música caso não tenha músicas tocadas/na fila).")
    async def back(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        if not len(player.played) and not len(player.queue):
            await player.seek(0)
            await self.interaction_message(inter, "voltou para o início da música.")
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
            if player.static and player.text_channel == inter.channel:
                player.command_log = f"{inter.author.mention} voltou para a música atual."
                await inter.response.send_message("voltado com sucesso.", ephemeral=True)
            else:
                embed = disnake.Embed(description=f"⏮️** ┃ Voltou para a música:** [`{fix_characters(track.title, 30)}`]({track.uri})",
                                      color=inter.guild.me.color)
                await inter.response.send_message(embed=embed)

        if player.loop == "current":
            player.loop = False
        player.is_previows_music = True
        if not player.current:
            await player.process_next()
        else:
            await player.stop()

    @check_voice()
    @has_source()
    @commands.slash_command(description=f"Votar para pular a música atual.")
    async def voteskip(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        embed = disnake.Embed()

        if inter.author in player.votes:
            embed.colour = disnake.Colour.red()
            embed.description = f"{inter.author.mention} **você já votou para pular a música atual.**"
            await send_message(inter, embed=embed, ephemeral=True)
            return

        embed.colour = disnake.Colour.green()

        txt = f"{inter.author.mention} **votou para pular a música atual (votos: {len(player.votes) + 1}/{self.bot.config.get('vote_skip_amount', 3)}).**"

        ephemeral = True if (player.static and player.text_channel == inter.channel) else False

        if len(player.votes) < self.bot.config.get('vote_skip_amount', 3):
            embed.description = txt
            player.votes.add(inter.author)
            if ephemeral:
                player.command_log = txt
                await inter.response.send_message("voto adicionado!", ephemeral=True)
                await player.update_message()
            else:
                await send_message(inter, embed=embed, ephemeral=ephemeral)
            return

        if ephemeral:
            player.command_log = f"{txt}\n**A anterior foi pulada imediatamente.**"
            await inter.response.send_message("voto adicionado!", ephemeral=True)
        else:
            embed.description = f"{txt}\n**A música atual será pulada imediatamente.**"
            await send_message(inter, embed=embed)
        await player.stop()

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(1, 5), commands.BucketType.member)
    @commands.slash_command(description="Ajustar volume da música.")
    async def volume(
            self,
            inter: disnake.ApplicationCommandInteraction, *,
            value: int = commands.Param(name="nível", description="nível entre 5 a 150", min_value=5.0, max_value=150.0)
    ):

        player: CustomPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        update = False

        if value is None:

            view = VolumeInteraction(inter)

            embed.colour = inter.guild.me.colour
            embed.description = "**Selecione o nível do volume abaixo:**"
            await inter.response.send_message(embed=embed, ephemeral=True, view=view)
            await view.wait()
            if view.volume is None:
                return

            value = view.volume
            update = True

        elif not 4 < value < 151:
            embed.description = "O volume deve estar entre **5** a **150**."
            return await inter.response.send_message(embed=embed, ephemeral=True)

        await player.set_volume(value)

        txt = [f"ajustou o volume para **{value}%**", f"Volume ajustado para **{value}**"]
        await self.interaction_message(inter, txt, update=update)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.slash_command(description="Pausar a música.")
    async def pause(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        if player.paused:
            ephemeral = True if (player.static and player.text_channel == inter.channel) else False
            await send_message(inter, embed=embed, ephemeral=ephemeral)
            return

        await player.set_pause(True)

        txt = ["pausou a música.", "Musica pausada."]

        await self.interaction_message(inter, txt)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.slash_command(description="Retomar/Despausar a música.")
    async def resume(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        if not player.paused:
            embed.description = "A música não está pausada."
            ephemeral = True if (player.static and player.text_channel == inter.channel) else False
            await send_message(inter, embed=embed, ephemeral=ephemeral)
            return

        await player.set_pause(False)

        txt = ["retomou a música.", "Música retomada"]
        await self.interaction_message(inter, txt)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.member)
    @commands.max_concurrency(1, commands.BucketType.member)
    @commands.slash_command(description="Avançar/Retomar a música para um tempo específico.")
    async def seek(
            self,
            inter: disnake.ApplicationCommandInteraction,
            position: str = commands.Param(name="tempo", description="Tempo para avançar/voltar (ex: 1:45 / 40 / 0:30)", autocomplete=seek_suggestions)
    ):

        embed = disnake.Embed(color=disnake.Colour.red())

        player: CustomPlayer = inter.player

        if player.current.is_stream:
            embed.description = "Você não pode usar este comando em uma livestream."
            await send_message(inter, embed=embed, ephemeral=True)
            return

        position = position.split(" | ")[0]

        seconds = string_to_seconds(position)

        if seconds is None:
            embed.description = "Você usou um tempo inválido! Use segundos (1 ou 2 digitos) ou no formato (minutos):(segundos)"
            return await send_message(inter, embed=embed, ephemeral=True)

        update = False

        milliseconds = seconds * 1000

        if milliseconds < 0:
            milliseconds = 0

        try:
            await player.seek(milliseconds)
        except Exception as e:
            embed.description = f"Ocorreu um erro no comando\n```py\n{repr(e)}```."
            await send_message(inter, embed=embed, ephemeral=True)
            return

        txt = [
            f"{'avançou' if milliseconds > player.position else 'voltou'} o tempo da música para: {time_format(milliseconds)}",
            f"O tempo da música foi {'avançada' if milliseconds > player.position else 'retornada'} para: {time_format(milliseconds)}"
        ]
        await self.interaction_message(inter, txt, update=update)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.slash_command(name="shuffle", description="Misturar as músicas da fila")
    async def shuffle_(self, inter: disnake.ApplicationCommandInteraction):

        player = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        if len(player.queue) < 3:
            embed.description = "A fila tem que ter no mínimo 3 músicas para ser misturada."
            await send_message(inter, embed=embed, ephemeral=True)
            return

        shuffle(player.queue)

        txt = [f"misturou as músicas da fila.", "músicas misturadas com sucesso."]

        await self.interaction_message(inter, txt)

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(3, 5), commands.BucketType.member)
    @commands.slash_command(description="Ativar/Desativar a repetição.")
    async def loop(
            self,
            inter: disnake.ApplicationCommandInteraction,
            mode: Literal['current', 'queue', 'off'] = commands.Param(name="modo",
                description="current = Música atual / queue = fila / off = desativar",
                default=lambda inter: 'off' if inter.player.loop else 'current'
            )
    ):

        player = inter.player

        if mode == 'off':
            mode = False

        if mode == player.loop:
            await self.interaction_message(inter, "Não teve alteração no modo de repetição atual.", ephemeral=True)
            return

        if mode:
            txt = [f"ativou a repetição da {'música' if mode == 'current' else 'fila'}.", f"Repetição da {'música' if mode == 'current' else 'fila'} ativada com sucesso."]
        else:
            txt = ['desativou a repetição.', "Repetição desativada."]

        player.loop = mode

        await self.interaction_message(inter, txt)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.slash_command(description="Remover uma música específica da fila.")
    async def remove(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        embed = disnake.Embed(color=disnake.Colour.red())

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.response.send_message(embed=embed, ephemeral=True)
            return

        player: CustomPlayer = inter.player

        track = player.queue[index]

        player.queue.remove(track)

        embed = disnake.Embed(color=disnake.Colour.green())

        txt = f"{inter.author.mention} removeu a música [`{(tname:=fix_characters(track.title, 25))}`]({track.uri}) da fila."

        if player.static and player.text_channel == inter.channel:
            player.command_log = txt
            embed.description=f"música removida: [`{tname}`]({track.uri})"
            await inter.response.send_message(embed=embed, ephemeral=True)
        else:
            embed.description = txt
            await inter.response.send_message(embed=embed)

        await player.update_message()

    @check_voice()
    @has_player()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.guild)
    @commands.slash_command(description="Readicionar as músicas tocadas na fila.")
    async def readd(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        if not player.played:
            embed.description = f"{inter.author.mention} **não há músicas tocadas.**"
            await inter.response.send_message(embed=embed, ephemeral=True)
            return

        embed.colour = disnake.Colour.green()
        txt = f"{inter.author.mention} **readicionou [{(qsize:=len(player.played))}] música(s) tocada(s) na fila.**"

        player.played.reverse()
        player.queue.extend(player.played)
        player.played.clear()

        if player.static and player.text_channel == inter.channel:
            player.command_log = txt
            embed.description = f"**você readicionou {qsize} música(s).**"
            await inter.response.send_message(embed=embed, ephemeral=True)
            await player.update_message()
        else:
            embed.description = txt
            await inter.response.send_message(embed=embed)

        if not player.current:
            await player.process_next()
        else:
            await player.update_message()

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 8), commands.BucketType.guild)
    @commands.slash_command(description="Pular para a música especificada.")
    async def skipto(
            self,
            inter: disnake.ApplicationCommandInteraction, *,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        embed = disnake.Embed(color=disnake.Colour.red())

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.response.send_message(embed=embed, ephemeral=True)
            return

        player: CustomPlayer = inter.player

        track = player.queue[index]

        player.queue.append(player.last_track)
        player.last_track = None

        if player.loop == "current":
            player.loop = False

        if index > 0:
            player.queue.rotate(0 - (index))

        embed.colour = disnake.Colour.green()

        track_title = fix_characters(track.title, limit=30)

        if player.static and player.text_channel == inter.channel:
            player.command_log = f"{inter.author.mention} pulou para a música atual"
            embed.description = f"**você pulou para a música:** [{track_title}]({track.uri})"
            await inter.response.send_message(embed=embed, ephemeral=True)

        else:
            embed.description = f"{inter.author.mention} **pulou para a música:** [`{track_title}`]({track.uri})"
            embed.colour = disnake.Colour.green()
            await inter.response.send_message(embed=embed)

        await player.stop()

    @check_voice()
    @has_source()
    @is_dj()
    @commands.slash_command(description="Move uma música para a posição especificada da fila.")
    async def move(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks),
            position: int = commands.Param(name="posição", description="Posição de destino na fila.")
    ):

        embed = disnake.Embed(colour=disnake.Colour.red())

        if position < 1:
            embed.description = f"{inter.author.mention}, {position} não é uma posição válida."
            await send_message(inter, embed=embed, ephemeral=True)
            return

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.response.send_message(embed=embed, ephemeral=True)
            return

        player: CustomPlayer = inter.player

        track = player.queue[index]

        player.queue.remove(track)

        player.queue.insert(int(position) - 1, track)

        txt = f"{inter.author.mention} moveu a música [`{fix_characters(track.title, limit=25)}`]({track.uri}) para a posição **[{position}]** da fila."

        embed = disnake.Embed(color=disnake.Colour.green())

        if player.static and player.text_channel == inter.channel:
            embed.description = f"música [`{fix_characters(track.title, limit=25)}`]({track.uri}) movida para a posição **[{position}]** da fila."
            player.command_log = txt
            await inter.response.send_message(embed=embed, ephemeral=True)
        else:
            embed.description = txt
            await inter.response.send_message(embed=embed)

        await player.update_message()

    @check_voice()
    @has_source()
    @is_dj()
    @commands.dynamic_cooldown(user_cooldown(2, 10), commands.BucketType.guild)
    @commands.slash_command(description="Rotacionar a fila para a música especificada.")
    async def rotate(
            self,
            inter: disnake.ApplicationCommandInteraction,
            query: str = commands.Param(name="nome", description="Nome da música completo.", autocomplete=queue_tracks)
    ):

        embed = disnake.Embed(colour=disnake.Colour.red())

        index = get_track_index(inter, query)

        if index is None:
            embed.description = f"{inter.author.mention} **não há músicas na fila com o nome: {query}**"
            await inter.response.send_message(embed=embed, ephemeral=True)
            return

        player: CustomPlayer = inter.player

        track = player.queue[index]

        if index <= 0:
            embed.description = f"{inter.author.mention} **a música **[`{track.title}`]({track.uri}) já é a próxima da fila."
            await inter.response.send_message(embed=embed, ephemeral=True)
            return

        player.queue.rotate(0 - (index))

        embed.colour=disnake.Colour.green()

        txt = f"{inter.author.mention} rotacionou a fila para a música [`{(tname:=fix_characters(track.title, limit=25))}`]({track.uri})."

        if player.static and player.text_channel == inter.channel:
            embed.description = f"Fila rotacionada para a música [`{tname}`]({track.uri})."
            player.command_log = txt
            await inter.response.send_message(embed=embed, ephemeral=True)
        else:
            embed.description = txt
            await inter.response.send_message(embed=embed)

        await player.update_message()

    @check_voice()
    @has_source()
    @is_dj()
    @commands.cooldown(1, 5, commands.BucketType.guild)
    @commands.slash_command(description="Ativar/Desativar o efeito nightcore (Música acelerada com tom mais agudo).")
    async def nightcore(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

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

        await self.interaction_message(inter, txt)

    @has_source()
    @commands.slash_command(description="Reenvia a mensagem do player com a música atual.")
    async def nowplaying(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        if player.static:
            await inter.response.send_message("este comando não pode ser usado no modo fixo do player.", ephemeral=True)
            return

        await player.destroy_message()
        await player.invoke_np()

        await inter.response.send_message("Player reenviado com sucesso!", ephemeral=True)

    @has_player()
    @is_dj()
    @commands.user_command(name="add dj")
    async def adddj_u(self, inter: disnake.UserCommandInteraction):
        await self.add_dj(inter, user=inter.target)

    @has_player()
    @is_dj()
    @commands.slash_command(description="Adicionar um membro à lista de DJ's na sessão atual do player.")
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
            await send_message(inter, embed=embed, ephemeral=True)
            return

        inter.player.dj.append(user)
        text = [f"adicionou {user.mention} à lista de DJ's.", f"{user.mention} foi adicionado à lista de DJ's."]

        if (inter.player.static and inter.channel == inter.player.text_channel) or isinstance(inter.application_command, commands.InvokableApplicationCommand):
            await inter.response.send_message(f"{inter.target.mention} adicionado à lista de DJ's!", ephemeral=True)

        await self.interaction_message(inter, txt=text, update=True)

    @check_voice()
    @has_player()
    @is_dj()
    @commands.slash_command(description="Parar o player e me desconectar do canal de voz.")
    async def stop(self, inter: disnake.Interaction):

        player: CustomPlayer = inter.player

        embed = disnake.Embed(color=disnake.Colour.red())

        player.command_log = f"{inter.author.mention} **parou o player!**"
        embed.description = f"**{inter.author.mention} parou o player!**"
        await inter.response.send_message(embed=embed, ephemeral=inter.guild_data and inter.guild_data["player_controller"]["channel"] == str(inter.channel.id))

        await player.destroy()

    @has_player()
    @commands.slash_command(name="queue", description="Mostrar as músicas que estão da fila.")
    @commands.max_concurrency(1, commands.BucketType.member)
    async def q(self, inter: disnake.ApplicationCommandInteraction):

        player: CustomPlayer = inter.player

        if not player.queue:
            embedvc = disnake.Embed(
                colour=disnake.Colour.red(),
                description='Não existe músicas na fila no momento.'
            )
            await send_message(inter, embed=embedvc)
            return

        view = QueueInteraction(player, inter.author)
        embed = view.embed

        await inter.response.send_message(embed=embed, view=view, ephemeral=True)

        await view.wait()

    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.slash_command(description="Ver informações dos servidores de música.")
    async def nodeinfo(self, inter: disnake.ApplicationCommandInteraction):

        em = disnake.Embed(color=inter.guild.me.color, title="Servidores de música:")

        if not self.bot.wavelink.nodes:
            em.description = "**Não há servidores.**"
            await inter.response.send_message(embed=em)
            return

        for identifier, node in self.bot.wavelink.nodes.items():
            if not node.available: continue

            txt = f"Região: `{node.region.title()}`\n"

            current_player = True if node.players.get(inter.guild.id) else False

            if node.stats:
                used = humanize.naturalsize(node.stats.memory_used)
                total = humanize.naturalsize(node.stats.memory_allocated)
                free = humanize.naturalsize(node.stats.memory_free)
                cpu_cores = node.stats.cpu_cores
                cpu_usage = f"{node.stats.lavalink_load * 100:.2f}"
                started = node.stats.players

                ram_txt = f'RAM: `{used}/{free} ({total})`'

                txt += f'{ram_txt}\n' \
                       f'CPU Cores: `{cpu_cores}`\n' \
                       f'Uso de CPU: `{cpu_usage}%`\n' \
                       f'Uptime: `{time_format(node.stats.uptime)}`'

                if started:
                    txt += "\nPlayers: "
                    players = node.stats.playing_players
                    idle = started - players
                    if players:
                        txt += f'`[▶️{players}]`' + (" " if idle else "")
                    if idle:
                        txt += f'`[💤{idle}]`'

            if current_player:
                status = "🌟"
            else:
                status = "✅" if node.is_available else '❌'

            em.add_field(name=f'**{identifier}** `{status}`', value=txt)

        await inter.response.send_message(embed=em, ephemeral=True)

    @has_player()
    @is_dj()
    @commands.max_concurrency(1, commands.BucketType.guild)
    @commands.cooldown(1, 5, commands.BucketType.member)
    @commands.slash_command(description="Limpar a fila de música (ou apenas algumas músicas usando filtros personalizados).")
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
            await inter.response.send_message("Não há musicas na fila.", ephemeral=True)
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
            txt = ['limpou a fila de música.', 'Fila limpa com sucesso.']

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
                await inter.response.send_message("Nenhuma música encontrada!", ephemeral=True)
                return

            txt = [f"removeu {deleted_tracks} música(s) da fila via clear.",
                   f"{deleted_tracks} música(s) removidas da fila com sucesso."]

        await self.interaction_message(inter, txt)

    @require_database()
    @commands.has_guild_permissions(administrator=True)
    @commands.bot_has_guild_permissions(manage_channels=True, create_public_threads=True)
    @commands.dynamic_cooldown(user_cooldown(1,30), commands.BucketType.guild)
    @commands.slash_command(description="Criar um canal dedicado para pedir músicas e deixar player fixo.")
    async def setupplayer(self, inter: disnake.ApplicationCommandInteraction):

        target = inter.channel.category or inter.guild
        channel = await target.create_text_channel(f"{inter.guild.me.name} song requests")

        player: CustomPlayer = self.bot.wavelink.players.get(inter.guild_id)

        if player:
            player.text_channel = channel
            await player.destroy_message()
            player.static = True
            await player.invoke_np()
            message = player.message

        else:
            message = await self.send_idle_embed(channel)

        await message.create_thread(name="song requests")

        inter.guild_data['player_controller']['channel'] = str(channel.id)
        inter.guild_data['player_controller']['message_id'] = str(message.id)
        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name='guilds')

        embed = disnake.Embed(description=f"**Canal criado: {channel.mention}**\n\nObs: Caso queira reverter esta configuração, apenas delete o canal {channel.mention}", color=inter.guild.me.color)
        await inter.response.send_message(embed=embed, ephemeral=True)

    @require_database()
    @commands.has_guild_permissions(administrator=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.slash_command(description="Adicionar um cargo para a lista de DJ's do servidor.")
    async def add_dj_role(
            self,
            inter: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="cargo", description="Cargo")
    ):

        if role == inter.guild.default_role:
            await inter.response.send_message("Você não pode adicionar este cargo.", ephemeral=True)
            return

        if str(role.id) in inter.guild_data['djroles']:
            await inter.response.send_message("Este cargo já está na lista de DJ's", ephemeral=True)
            return

        inter.guild_data['djroles'].append(str(role.id))

        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name="guilds")

        await inter.response.send_message(f"O cargo {role.mention} foi adicionado à lista de DJ's", ephemeral=True)

    @require_database()
    @commands.has_guild_permissions(administrator=True)
    @commands.dynamic_cooldown(user_cooldown(1, 7), commands.BucketType.guild)
    @commands.slash_command(description="Remover um cargo para a lista de DJ's do servidor.")
    async def remove_dj_role(
            self,
            inter: disnake.ApplicationCommandInteraction,
            role: disnake.Role = commands.Param(name="cargo", description="Cargo")
    ):

        if not inter.guild_data['djroles']:

            await inter.response.send_message("Não há cargos na lista de DJ's.", ephemeral=True)
            return

        if str(role.id) not in inter.guild_data['djroles']:
            await inter.response.send_message("Este cargo não está na lista de DJ's\n\n" + "Cargos:\n" +
                                              " ".join(f"<#{r}>" for r in inter.guild_data['djroles']), ephemeral=True)
            return

        inter.guild_data['djroles'].remove(str(role.id))

        await self.bot.db.update_data(inter.guild.id, inter.guild_data, db_name="guilds")

        await inter.response.send_message(f"O cargo {role.mention} foi removido da lista de DJ's", ephemeral=True)

    @commands.Cog.listener("on_message")
    async def song_requests(self, message: disnake.Message):

        if message.author.bot:
            return

        try:
            data = await self.bot.db.get_data(message.guild.id, db_name='guilds')
        except AttributeError:
            return

        static_player = data['player_controller']

        channel_id = static_player['channel']

        if not channel_id or (static_player['message_id'] != str(message.channel.id) and str(message.channel.id) != channel_id):
            return

        text_channel = self.bot.get_channel(int(channel_id))

        if not text_channel or not text_channel.permissions_for(message.guild.me).send_messages:
            return

        try:
            await self.song_request_concurrency.acquire(message)
        except:
            await message.delete()
            await message.channel.send(f"{message.author.mention} você deve aguardar seu pedido de música anterior carregar...", delete_after=10)
            return

        try:
            await self.parse_song_request(message, text_channel, data)
        except Exception as e:
            await message.channel.send(f"{message.author.mention} **ocorreu um erro ao tentar obter resultados para sua busca:** ```py\n{e}```", delete_after=15)

        try:
            await message.delete()
        except:
            pass
        await self.song_request_concurrency.release(message)

    async def parse_song_request(self, message, text_channel, data):

        if not message.author.voice:
            await message.channel.send(f"{message.author.mention} você deve entrar em um canal de voz para pedir uma música.", delete_after=15)
            return

        try:
            if message.guild.me.voice.channel != message.author.voice.channel:
                await message.channel.send(f"{message.author.mention} você deve entrar no canal <{message.guild.me.voice.channel.id}> para pedir uma música.", delete_after=15)
                return
        except AttributeError:
            pass

        tracks, node = await self.get_tracks(message.content, message.author)

        player: CustomPlayer = self.bot.wavelink.get_player(
            guild_id=message.guild.id,
            cls=CustomPlayer,
            requester=message.author,
            guild=message.guild,
            channel=text_channel,
            static=True,
            cog=self
        )

        if not player.message:
            try:
                cached_message = await text_channel.fetch_message(int(data['player_controller']['message_id']))
            except:
                cached_message = await self.send_idle_embed(message)
                data['player_controller']['message_id'] = str(cached_message.id)
                await self.bot.db.update_data(message.guild.id, data, db_name='guilds')

            player.message = cached_message

        embed = disnake.Embed(color=message.guild.me.color)

        try:
            player.queue.extend(tracks.tracks)
            if isinstance(message.channel, disnake.Thread):
                embed.description = f"**Playlist adicionada:**\n[`{tracks.data['playlistInfo']['name']}`]({message.content})" \
                                    f"\n\n`[{len(tracks.tracks)}] Música(s)`"
                embed.set_thumbnail(url=tracks.tracks[0].thumb)
                if self.msg_ad:
                    embed.description += f" | {self.msg_ad}"
                await message.channel.send(embed=embed)

        except AttributeError:
            player.queue.append(tracks[0])
            if isinstance(message.channel, disnake.Thread):
                embed.description = f"**Música adicionada:\n[`{tracks[0].title}`]({tracks[0].uri})**" \
                                    f"\n\n`{tracks[0].author}` | `{time_format(tracks[0].duration) if not tracks[0].is_stream else '🔴 Livestream'}`"
                embed.set_thumbnail(url=tracks[0].thumb)
                if self.msg_ad:
                    embed.description += f" | {self.msg_ad}"
                await message.channel.send(embed=embed)

        if not player.is_connected:
            await player.connect(message.author.voice.channel.id)

        if not player.current:
            await player.process_next()
        else:
            await player.update_message()

        await asyncio.sleep(1)

    def cog_unload(self):
        try:
            self.bot.test.exit_test()
        except:
            pass

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
            inter.player = self.bot.wavelink.players.get(inter.guild.id)

    async def interaction_message(self, inter: disnake.Interaction, txt, ephemeral=False, update=False):

        try:
            txt, txt_ephemeral = txt
        except:
            txt_ephemeral = False

        if update or (inter.player.static and inter.player.text_channel == inter.channel) \
                or not isinstance(inter, disnake.ApplicationCommandInteraction):
            txt = f"{inter.author.mention} {txt}"
            inter.player.command_log = txt
            if not (component_interaction:=isinstance(inter, disnake.MessageInteraction)) and inter.player.static and not inter.response.is_done():
                await inter.response.send_message(txt_ephemeral or txt, ephemeral=True)
            await inter.player.update_message(interaction=False if (update or not component_interaction) else inter)
            return

        txt = f"{inter.author.mention} **{txt}**"
        embed = disnake.Embed(color=disnake.Colour.green(), description=txt_ephemeral or txt)
        await inter.player.update_message()
        if not inter.response.is_done():
            await inter.response.send_message(embed=embed, ephemeral=ephemeral)
        else:
            await inter.channel.send(embed=embed)

    async def process_nodes(self):

        await self.bot.wait_until_ready()

        if not hasattr(self.bot, 'session') or not self.bot.session:
            self.bot.session = ClientSession()

        for node in lavalink_servers:
            self.bot.loop.create_task(self.connect_node(node))

        if self.bot.config.get('start_local_lavalink', True):
            self.bot.loop.create_task(self.connect_local_lavalink())

    async def connect_node(self, data: dict):

        data['rest_uri'] = ("https" if data.get('secure') else "http") + f"://{data['host']}:{data['port']}"

        data['user_agent'] = UserAgent().random

        max_retries = data.pop('retries', 0)

        if max_retries:

            backoff = 7
            retries = 1

            while not self.bot.is_closed():
                if retries >= max_retries:
                    print(f"Todas as tentativas de conectar ao servidor [{data['identifier']}] falharam.")
                    return
                else:
                    try:
                        async with self.bot.session.get(data['rest_uri'], timeout=10) as r:
                            break
                    except Exception:
                        backoff += 2
                        print(f'Falha ao conectar no servidor [{data["identifier"]}], nova tentativa [{retries}/{max_retries}] em {backoff} segundos.')
                        await asyncio.sleep(backoff)
                        retries += 1
                        continue

        await self.bot.wavelink.initiate_node(**data)

    @wavelink.WavelinkMixin.listener("on_websocket_closed")
    async def node_ws_voice_closed(self, node, payload: wavelink.events.WebsocketClosed):

        if payload.code == 1000:
            return

        player: CustomPlayer = payload.player

        if payload.code == 4014:

            if player.guild.me.voice:
                return
            vc = player.bot.get_channel(player.channel_id)
            if vc:
                vcname = f" **{vc.name}**"
            else:
                vcname = ""
            channel = player.text_channel
            embed = disnake.Embed(color=player.guild.me.color)
            embed.description = f"Conexão perdida com o canal de voz{vcname}..."
            embed.description += "\nO player será finalizado..."
            self.bot.loop.create_task(channel.send(embed=embed, delete_after=15))
            await player.destroy()
            return

        # fix para dpy 2x (erro ocasionado ao mudar o bot de canal)
        if payload.code == 4006:

            await player.connect(player.channel_id)
            return

        print(f"Erro no canal de voz! server: {player.guild.name} reason: {payload.reason} | code: {payload.code}")

    @wavelink.WavelinkMixin.listener('on_track_exception')
    async def wavelink_track_error(self, node, payload: wavelink.TrackException):
        player: CustomPlayer = payload.player
        track = player.last_track
        embed = disnake.Embed(
            description=f"**Falha ao reproduzir música:\n[{track.title}]({track.uri})** ```java\n{payload.error}\n```",
            color=disnake.Colour.red())
        await player.text_channel.send(embed=embed, delete_after=10 if player.static else None)

        if player.locked:
            return

        player.current = None
        if payload.error == "This IP address has been blocked by YouTube (429)":
            player.queue.appendleft(player.last_track)
        else:
            player.played.append(player.last_track)

        player.locked = True
        await asyncio.sleep(6)
        player.locked = False
        await player.process_next()

    @wavelink.WavelinkMixin.listener()
    async def on_node_ready(self, node: wavelink.Node):
        print(f'Servidor de música: [{node.identifier}] está pronto para uso!')

    @wavelink.WavelinkMixin.listener('on_track_start')
    async def track_start(self, node, payload: wavelink.TrackStart):

        player: CustomPlayer = payload.player
        await player.invoke_np(force=True if (not player.loop or not player.is_last_message()) else False)
        player.command_log = ""

    @wavelink.WavelinkMixin.listener()
    async def on_track_end(self, node: wavelink.Node, payload: wavelink.TrackEnd):

        player: CustomPlayer = payload.player

        if player.locked:
            return

        if payload.reason == "FINISHED":
            player.command_log = ""
        elif payload.reason == "STOPPED":
            pass
        else:
            return

        player.votes.clear()

        player.locked = True

        await asyncio.sleep(0.5)

        if player.last_track:

            if player.loop == "queue":
                if player.is_previows_music:
                    player.queue.insert(1, player.last_track)
                    player.is_previows_music = False
                else:
                    player.queue.append(player.last_track)
            elif player.loop == "current":
                player.queue.appendleft(player.last_track)
            elif player.is_previows_music:
                player.queue.insert(1, player.last_track)
                player.is_previows_music = False
            else:
                player.played.append(player.last_track)

        elif player.is_previows_music:
            player.is_previows_music = False

        try:
            player.updating_message.cancel()
        except:
            pass

        player.locked = False

        await player.process_next()


    async def get_tracks(self, query: str, user: disnake.Member, source="ytsearch", process_all=False):

        query = query.strip("<>")

        if not URL_REG.match(query):
            query = f"{source}:{query}"
        if not process_all and (url_regex := YOUTUBE_VIDEO_REG.match(query)):
            query = url_regex.group()

        node = self.bot.wavelink.get_best_node()
        if not node:
            raise Exception("Não há servidores de música disponível.")

        tracks = await process_spotify(self.bot, user, query)

        if not tracks:
            tracks = await node.get_tracks(query)

        if not tracks:
            raise Exception("Não houve resultados para sua busca.")

        if isinstance(tracks, list):

            if not isinstance(tracks[0], SpotifyTrack):
                tracks = [CustomTrack(track.id, track.info, requester=user) for track in tracks]

        else:

            if not isinstance(tracks, SpotifyPlaylist):
                playlist = {
                    "name": tracks.data['playlistInfo']['name'],
                    "url": query
                }
                tracks.tracks = [CustomTrack(t.id, t.info, requester=user, playlist=playlist) for t in tracks.tracks]

            if (selected := tracks.data['playlistInfo']['selectedTrack']) > 0:
                tracks.tracks = tracks.tracks[selected:] + tracks.tracks[:selected]

        return tracks, node

    async def send_idle_embed(self, target: Union[disnake.Message, disnake.TextChannel, disnake.Thread], text=""):

        embed = disnake.Embed(description="**Entre em um canal de voz e peça uma música aqui**\n\n"
                                          "**FORMATOS SUPORTADOS (nome, link):** "
                                          "```\nYoutube, Soundcloud, Spotify, Twitch```", color=target.guild.me.color)

        if text:
            embed.description += f"\n__**Última ação:**__ {text}"

        try:
            avatar = target.guild.me.avatar.url
        except:
            avatar = target.guild.me.default_avatar.url
        embed.set_thumbnail(avatar)

        if isinstance(target, disnake.Message):
            if target.author == target.guild.me:
                await target.edit(embed=embed, content=None, view=None)
                message = target
            else:
                message = await target.channel.send(embed=embed)
        else:
            message = await target.send(embed=embed)

        return message

    async def connect_local_lavalink(self):

        if 'LOCAL' not in self.bot.wavelink.nodes:
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

    @commands.Cog.listener("on_thread_join")
    async def join_thread_request(self, thread: disnake.Thread):

        try:

            data = await self.bot.db.get_data(thread.guild.id, db_name="guilds")

            if data["player_controller"]["message_id"] != (thread.id):
                return

        except AttributeError:
            return

        if thread.guild.me.id in thread._members:
            return

        await thread.join()

def setup(bot: BotCore):
    bot.add_cog(Music(bot))
