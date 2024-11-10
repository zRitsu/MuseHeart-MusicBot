# Nota: Code incompleto (provavelmente não será finalizado).
# * Há uma chance dos serviços de ia começar a impor limites (não terá suporte garantido, portanto recomendo não fazer
#   alterações que permita ignorar o cooldown implementado no code do comando caso queira ajudar a evitar que isso aconteça).
# * Nos modelos atuais que não há delay e possibilita uso sem api-keys etc pode ter uma base de dados limitada
#   (máximo até 2021, qualquer info solicitada que seja após o ano citado pode vir resultados não esperado).

from __future__ import annotations

import asyncio
import re

from async_timeout import timeout

from copy import deepcopy
from typing import TYPE_CHECKING

import disnake
from aiohttp import ClientSession
from disnake.ext import commands
import g4f

import wavelink
from utils.music.audio_sources.deezer import deezer_regex
from utils.music.audio_sources.spotify import spotify_regex
from utils.music.checks import can_send_message_check, can_connect, check_voice, check_player_perm
from utils.music.converters import URL_REG, YOUTUBE_VIDEO_REG
from utils.music.errors import GenericError
from utils.music.models import PartialTrack, LavalinkPlayer
from utils.others import pool_command, CustomContext

if TYPE_CHECKING:
    from utils.client import BotCore


music_list_regex = re.compile(r'(?<!\d\.)\s*([^\n-]+)\s*-\s*(.*)')

class AiMusic(commands.Cog):

    emoji = "🎶"
    name = "Música"
    desc_prefix = f"[{emoji} {name}] | "

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.default_prompt_template = (
            "Recomende 5 ou mais músicas de acordo com essa característica: {prompt}.\n"
            "Observações:\n"
            "* Liste as músicas dessa forma: artista - música"
            "* deixe cada música em uma linha separada, sem numerar e sem começar com caracteres como hifens etc)."
            "* Se a característica solicitar músicas semelhantes sugira tanto músicas de outros artistas quanto do artista citado.\n"
            "* Dê uma breve explicação da escolha após a lista (em pt-br e comentando com emojis na explicação)\n"
            "* Inclua na descrição informações sobre as músicas como gênero etc.")
        try:
            with open("ai_prompt.txt") as f:
                prompt = f.read()
            if "{prompt}" in prompt:
                self.default_prompt_template = prompt
        except:
            pass

        if not hasattr(bot.pool, 'ai_client'):
            bot.pool.ai_client = g4f.client.Client()

        self.ai_client = bot.pool.ai_client

    music_rec_cd = commands.CooldownMapping.from_cooldown(2, 120, commands.BucketType.member)
    music_rec_mc = commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=False)

    @can_send_message_check()
    @check_voice()
    @pool_command(name="musicrecomendations", aliases=["musicrecs", "mscr", "recommend",
                                                        "recomende", "indique", "indicações", "recomendações",
                                                        "recommendations"],
                  usage="{prefix}{cmd} [descrição]\n\n"
                        "Ex 1: {prefix}{cmd} músicas parecidas com David Getta - She Wolf\n\n"
                        "Ex 2: {prefix}{cmd} músicas eletrônicas de baladas\n\n"
                        "Ex 3: {prefix}{cmd} kawaii EDM",
                  description="Gerar/tocar uma lista de músicas recomendadas por inteligência artificial de acordo com o pedido do usuário (além de ser feito um pequeno comentário sobre a seleção de músicas).\n\n"
                              "Nota: Esse comando ainda está em fase alpha (sujeito a erros).",
                  check_player=False, max_concurrency=music_rec_mc, cooldown=music_rec_cd)
    async def musicrecommendations_legacy(self, ctx: CustomContext, *, prompt: str):
        await self.musicrecommendations.callback(self=self, inter=ctx, prompt=prompt)


    @can_send_message_check()
    @check_voice()
    @commands.slash_command(name="recommendations", extras={"check_player": False}, dm_permission=False,
                            max_concurrency=music_rec_mc, cooldown=music_rec_cd,
                            description=f"{desc_prefix}Tocar recomendações de músicas por IA de acordo com o pedido/prompt.")
    async def musicrecommendations(
            self,
            inter: disnake.AppCmdInter,
            prompt: str = commands.Param(name=disnake.Localized("query", data={disnake.Locale.pt_BR: "descrição"}),
                                         desc="Descreva o pedido.")
    ):

        try:
            bot = inter.music_bot
            guild = inter.music_guild
        except AttributeError:
            bot = inter.bot
            guild = inter.guild

        try:
            if not prompt:
                raise GenericError("**Você deve incluir um pedido/descrição de músicas.**")

            prompt = prompt.strip("<>")

            can_connect(channel=inter.author.voice.channel, guild=guild)
            await check_player_perm(inter=inter, bot=bot, channel=inter.channel)

            node: wavelink.Node = bot.music.get_best_node()

            if not node:
                raise GenericError("**Não há servidores de música disponível!**")

        except Exception as e:
            try:
                inter.application_command.reset_cooldown(inter)
            except:
                try:
                    inter.command.reset_cooldown(inter)
                except:
                    pass
            raise e

        channel_id = inter.author.voice.channel.id

        txt = str(self.default_prompt_template)

        original_prompt = deepcopy(prompt)

        if ":" in prompt:
            prompt = prompt.replace(":", "-> ").strip()

        try:
            async with timeout(1.5):
                ephemeral = await bot.get_cog("Music").is_request_channel(inter, ignore_thread=True)
        except asyncio.TimeoutError:
            ephemeral = True

        await inter.response.defer(ephemeral=ephemeral, with_message=True)

        url_search = None

        original_search = None

        if matches:=URL_REG.search(prompt):

            if len(matches.groups()) > 1:
                raise GenericError("Você pode usar apenas 1 link no seu pedido.")

            url_search = matches.group()

            original_search = str(url_search)

            url_search = None

            if matches:=YOUTUBE_VIDEO_REG.search(original_search):
                url_search = matches.group()

            elif matches:=spotify_regex.match(original_search):

                url_type, url_id = matches.groups()

                if url_type != "track":
                    raise GenericError("**Você só pode usar links de músicas caso seja informado links do spotify.**")

                url_search = f"https://open.spotify.com/track/{url_id}"

            if original_search.startswith("https://deezer.page.link/"):
                async with ClientSession() as session:
                    async with session.get(url_search, allow_redirects=False) as r:
                        if 'location' not in r.headers:
                            raise GenericError("**Falha ao obter resultado para o link informado...**")
                        url_search = str(r.headers["location"])

            if matches:=deezer_regex.match(original_search):

                url_type, url_id = matches.groups()[-2:]

                if url_type != "track":
                    raise GenericError("**Você só pode usar links de músicas caso seja informado links do deezer.**")

                url_search = f"https://www.deezer.com/track/{url_id}"

            if not url_search:
                raise GenericError("**No momento não há suporte para o link informado...**")

        if url_search:

            cog = self.bot.get_cog("Music")
            search_result, node = await cog.get_tracks(url_search, inter, user=inter.author, source=False)

            if not search_result:
                raise GenericError("**Não houve resultados para o link informado no pedido...**")

            try:
                search_result = search_result.tracks
            except:
                pass

            track = search_result[0]

            title = f"{track.author} - {track.single_title}".lower() if (track.info["sourceName"] not in ("youtube", "soundcloud") or len(track.title) < 12) else track.title.lower()

            prompt = prompt.replace(original_search, title)
            original_prompt = original_prompt.replace(original_search, title)

        response = await self.ai_client.chat.completions.async_create(
            model=g4f.models.claude_3_5_sonnet,
            # model=g4f.models.gpt_4_turbo,
            ignored=["Blackbox"],
            messages=[{"role": "user", "content": txt.replace("{prompt}", prompt)}],
        )

        lines = response.choices[0].message.content.split("\n")

        cleaned_list = music_list_regex.findall("\n".join(lines))

        tracklist = []

        try:
            for a, t in cleaned_list:

                a = a.replace('"', "")
                t = t.replace('"', "")

                if len(t) > 40 or len(a) > 50 or a.endswith(":") or t.endswith(":"):
                    continue

                track = PartialTrack(
                    title=t.strip(), author=a.split(",")[0].strip(), requester=inter.author.id, source_name="last.fm"
                )

                track.info["extra"]["authors"] = [i.strip() for i in a.split(",")]

                tracklist.append(track)
        except:
            tracklist = []

        if len(tracklist) < 2:
            print(f"Falha ao processar pedido de música via IA: {original_prompt}\n{response}")
            raise GenericError("**Infelizmente não encontrei nada relacionado ao seu pedido...**\n"
                               "-# Lembrando que esse recurso está em beta (sujeito a várias falhas).")

        player: LavalinkPlayer = await bot.get_cog("Music").create_player(
            inter=inter, bot=bot, guild=guild, channel=inter.channel
        )

        player.queue.extend(tracklist)

        connected = False

        if guild.me.id not in inter.author.voice.channel.voice_states:
            await player.connect(inter.author.voice.channel.id)
            connected = True

        txt = f"**{inter.author.mention} aqui está uma lista de músicas recomendadas de acordo com o seu pedido:** ```\n{prompt}```\n"

        for n, t in enumerate(tracklist):
            txt += f"[`{t.authors_string} - {t.single_title}`](<{t.uri}>)\n"

        if len(last_line:=lines[-1]) > 40:
            txt += f"\n{last_line}\n"

        txt += f"\nElas serão tocadas no canal de voz: <#{channel_id}>\n-# AI Music Recommendations (Alpha / Experimental)."

        if isinstance(inter, CustomContext):
            await inter.send(embed=disnake.Embed(description=txt, color=guild.me.color))
        else:
            await inter.edit_original_message(embed=disnake.Embed(description=txt, color=guild.me.color))

        if not player.current:
            await player.process_next()

        if connected and isinstance(inter.author.voice.channel, disnake.StageChannel):

            retries = 3

            while retries > 0:

                await asyncio.sleep(1)

                if not guild.me.voice:
                    retries -= 1
                    continue

                if guild.me not in inter.author.voice.channel.speakers:
                    stage_perms = inter.author.voice.channel.permissions_for(guild.me)
                    if stage_perms.manage_permissions:
                        await guild.me.edit(suppress=False)

                break

def setup(bot):
    bot.add_cog(AiMusic(bot))
