# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import contextlib
import traceback
from typing import Union, Optional, TYPE_CHECKING

import disnake
from disnake.ext import commands

import wavelink
from utils.db import DBModel
from utils.music.converters import time_format
from utils.music.errors import NoVoice, NoPlayer, NoSource, NotRequester, NotDJorStaff, \
    GenericError, MissingVoicePerms, DiffVoiceChannel, PoolException
from utils.others import CustomContext

if TYPE_CHECKING:
    from utils.music.models import LavalinkPlayer
    from utils.client import BotCore, BotPool


def can_send_message(
        channel: Union[disnake.TextChannel, disnake.VoiceChannel, disnake.Thread],
        bot: Union[disnake.ClientUser, disnake.Member]
):

    if isinstance(channel, disnake.Thread):
        send_message_perm = channel.parent.permissions_for(channel.guild.me).send_messages_in_threads
    else:
        send_message_perm = channel.permissions_for(channel.guild.me).send_messages

    if not send_message_perm:
        raise GenericError(f"**{bot.mention} não possui permissão de enviar mensagens no canal:** {channel.mention}")

    if not channel.permissions_for(channel.guild.me).embed_links:
        raise GenericError(f"**{bot.mention} não possui permissão de inserir links no canal: {channel.mention}**")

    return True


async def check_requester_channel(ctx: CustomContext):

    error_msg = "**No momento você só pode usar comandos de barra (/) nesse canal!**"

    guild_data = await ctx.bot.get_data(ctx.guild_id, db_name=DBModel.guilds)

    if guild_data['player_controller']["channel"] == str(ctx.channel.id):

        try:
            parent = ctx.channel.parent
        except AttributeError:
            return True

        if isinstance(parent, disnake.ForumChannel):

            if ctx.channel.owner_id == ctx.bot.user.id:

                try:
                    vc = ctx.author.voice.channel
                except AttributeError:
                    raise PoolException()
                if ctx.bot.user.id not in vc.voice_states:
                    raise PoolException()
            else:
                raise PoolException()

        raise GenericError(error_msg, self_delete=True, delete_original=15)

    for bot in ctx.bot.pool.get_guild_bots(ctx.guild_id):

        if bot == ctx.bot:
            continue

        data = await bot.get_data(ctx.guild_id, db_name=DBModel.guilds)

        if data['player_controller']["channel"] == str(ctx.channel.id):
            raise GenericError(error_msg, self_delete=True, delete_original=15)

    return True


def check_forum(inter, bot):

    if not bot.check_bot_forum_post(inter.channel, raise_error=False):

        if inter.channel.owner_id == bot.user.id:
            inter.music_bot = bot
            inter.music_guild = inter.guild
            return True
        else:
            raise PoolException()


def update_attr(inter, bot: BotCore, guild: disnake.Guild):
    with contextlib.suppress(AttributeError):
        inter.music_bot = bot
        inter.music_guild = guild
    return bot, guild


# ─────────────────────────────────────────────────────────────────────────────
# Pontuação de bot livre — critério musical (modelo Jockie)
#
# Prioridade:
#   +100  bot tem player ativo no guild (idle/pausado mas já está "em casa")
#   +10   bot com menos players ativos no total (mais disponível globalmente)
#          — invertido e normalizado para 0–10
#   Desempate final: identifier lexicográfico (estável entre reinicializações)
# ─────────────────────────────────────────────────────────────────────────────

def _score_free_bot(bot: BotCore, guild: disnake.Guild) -> int:
    score = 0

    try:
        if guild.id in bot.music.players:
            score += 100
    except AttributeError:
        pass

    try:
        score += max(0, 10 - len(bot.music.players))
    except AttributeError:
        pass

    return score


# ─────────────────────────────────────────────────────────────────────────────
# Coordenação de mensagens entre bots (comando prefix, mesmo prefixo)
#
# Problema original:
#   message_ids[msg_id] era apenas um sinalizador de "já registrado".
#   Bots que chegavam depois entravam no wait_for("pool_dispatch") de forma
#   independente. Se Bot A disparasse apenas um evento, somente um dos
#   demais acordava — os outros ficavam travados 10s até o timeout.
#
# Solução — asyncio.Event compartilhado no pool:
#   • Primeiro bot a ver msg_id registra e cria um Event no pool.
#   • Os demais aguardam esse Event (acordam todos ao mesmo tempo).
#   • Quando o vencedor é definido, seta o Event e grava o ID vencedor.
#   • Cada bot aguardante checa se é ele o vencedor; se não for, PoolException.
# ─────────────────────────────────────────────────────────────────────────────

def _get_dispatch_event(pool, msg_id: str) -> tuple[asyncio.Event, bool]:
    """
    Retorna (event, is_first_bot).
    is_first_bot=True  → este bot registrou a mensagem; deve processar e depois
                         setar o event.
    is_first_bot=False → outro bot já registrou; deve aguardar o event.
    """
    try:
        return pool._msg_events[msg_id], False
    except (AttributeError, KeyError):
        pass

    if not hasattr(pool, "_msg_events"):
        pool._msg_events = {}
        pool._msg_winner = {}

    event = asyncio.Event()
    pool._msg_events[msg_id] = event
    pool._msg_winner[msg_id] = None
    return event, True


def _resolve_dispatch(pool, msg_id: str, winner_bot_id: Optional[int]):
    """Seta o vencedor e libera todos os bots aguardantes."""
    try:
        pool._msg_winner[msg_id] = winner_bot_id
        pool._msg_events[msg_id].set()
    except (AttributeError, KeyError):
        pass


def _cleanup_dispatch(pool, msg_id: str):
    """Remove entradas após uso (o TTLCache de message_ids cuida do tempo)."""
    try:
        pool._msg_events.pop(msg_id, None)
        pool._msg_winner.pop(msg_id, None)
    except AttributeError:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# check_pool_bots — versão revisada para modelo multibot tipo Jockie
# ─────────────────────────────────────────────────────────────────────────────

async def check_pool_bots(
    inter,
    only_voiced: bool = False,
    check_player: bool = True,
    return_first: bool = False,
    bypass_prefix: bool = False,
    bypass_attribute: bool = False,
):
    # ── Atalho: atributo já resolvido em etapa anterior ──────────────────────
    if not bypass_attribute:
        try:
            inter.music_bot
            return inter.music_bot, inter.music_guild
        except AttributeError:
            pass

        if isinstance(inter, disnake.ModalInteraction):
            return update_attr(inter, inter.bot, inter.guild)

    # ── Single-bot: sem disputa ───────────────────────────────────────────────
    guild_bots: list[BotCore] = inter.bot.pool.get_guild_bots(inter.guild_id)

    if len(guild_bots) < 2 and inter.guild:
        return update_attr(inter, inter.bot, inter.guild)

    if not inter.guild_id:
        raise GenericError("**Esse comando não pode ser usado nas mensagens privada.**")

    # ── Bot atual já está no canal de voz do usuário: retorno imediato ────────
    try:
        if inter.bot.user.id in inter.author.voice.channel.voice_states:
            return update_attr(inter, inter.bot, inter.guild)
    except AttributeError:
        pass

    # ══════════════════════════════════════════════════════════════════════════
    # BLOCO PREFIX
    # ══════════════════════════════════════════════════════════════════════════
    mention_prefixed = False
    user_vc = False
    msg_id = None

    if isinstance(inter, CustomContext) and not bypass_prefix:

        is_forum = check_forum(inter, inter.bot)
        if is_forum:
            return update_attr(inter, inter.bot, inter.guild)

        mention_prefixed = inter.message.content.startswith(tuple(inter.bot.pool.bot_mentions))

        if not mention_prefixed:
            # ── Coordenação via Event: apenas um bot processa por mensagem ────
            msg_id = f"{inter.guild_id}-{inter.channel.id}-{inter.message.id}"
            pool = inter.bot.pool

            event, is_first = _get_dispatch_event(pool, msg_id)

            if not is_first:
                # Este bot chegou depois: aguarda o vencedor ser definido.
                # Todos os perdedores acordam juntos quando o Event for setado.
                try:
                    await asyncio.wait_for(event.wait(), timeout=10)
                except asyncio.TimeoutError:
                    raise PoolException()

                winner = pool._msg_winner.get(msg_id)
                if winner != inter.bot.user.id:
                    raise PoolException()

                return update_attr(inter, inter.bot, inter.guild)

            # Primeiro bot: continua o processamento normalmente.
            # O Event será setado ao final quando o vencedor for determinado.

        else:
            # ── Menção direta: o bot mencionado é dono da interação ───────────
            # Se este bot não foi o mencionado, ele não deve competir.
            # A checagem já é feita naturalmente: bot_mentions inclui todos,
            # mas a varredura abaixo filtra com `bot.user.id == inter.bot.user.id
            # and mention_prefixed` — mantemos o comportamento original aqui.

            if not check_player and not only_voiced:
                if inter.author.voice:
                    user_vc = True
                else:
                    return update_attr(inter, inter.bot, inter.guild)
            elif not inter.author.voice:
                if return_first:
                    return update_attr(inter, inter.bot, inter.guild)
                raise NoVoice()
            else:
                user_vc = True

            if inter.bot.user.id in inter.author.voice.channel.voice_states:
                return update_attr(inter, inter.bot, inter.guild)

            # Bot mencionado não está no canal do usuário mas também não está em
            # outro canal de voz no guild → pode assumir (retorno logo abaixo
            # na varredura). Se estiver em outro canal, cai na lógica de bot livre.
            if not only_voiced and not inter.guild.me.voice:
                return update_attr(inter, inter.bot, inter.guild)

    # ══════════════════════════════════════════════════════════════════════════
    # VARREDURA DE BOTS DO GUILD
    # Constrói listas: bots no canal do usuário, bots livres, bots ocupados.
    # ══════════════════════════════════════════════════════════════════════════
    # (bot, guild, score)
    free_bot: list[tuple[BotCore, disnake.Guild, int]] = []
    bot_missing_perms: list[BotCore] = []
    voice_channels: list[str] = []
    extra_bots_counter = 0
    bot_in_guild = False

    for bot in sorted(guild_bots, key=lambda b: b.identifier):

        if not bot.bot_ready:
            continue

        if not (guild := bot.get_guild(inter.guild_id)):
            if bot.user.id != inter.bot.user.id:
                extra_bots_counter += 1
            continue

        bot_in_guild = True

        # Quando a interação veio por menção, o bot atual (que recebeu a
        # mensagem) não compete contra si mesmo na varredura de outros bots.
        if bot.user.id == inter.bot.user.id and mention_prefixed:
            continue

        if not (author := guild.get_member(inter.author.id)):
            continue

        inter.author = author

        if not author.voice:
            inter.bot.dispatch("pool_dispatch", inter, None)

            if return_first:
                score = _score_free_bot(bot, guild)
                free_bot.append((bot, guild, score))
                continue

            # Se havia um Event aguardando, resolve com None (sem vencedor útil)
            if msg_id:
                _resolve_dispatch(inter.bot.pool, msg_id, None)
                _cleanup_dispatch(inter.bot.pool, msg_id)

            raise NoVoice()

        user_vc = True

        # ── Bot já está no canal do usuário → seleção imediata ────────────────
        if bot.user.id in author.voice.channel.voice_states:

            update_attr(inter, bot, guild)

            if (
                isinstance(inter, CustomContext)
                and not mention_prefixed
                and msg_id
                and bot.user.id != inter.bot.user.id
            ):
                # Informa todos os bots aguardantes que este é o vencedor
                _resolve_dispatch(inter.bot.pool, msg_id, bot.user.id)
                _cleanup_dispatch(inter.bot.pool, msg_id)
                raise PoolException()

            # É o próprio bot ou menção direta: resolve e retorna
            if msg_id:
                _resolve_dispatch(inter.bot.pool, msg_id, bot.user.id)
                _cleanup_dispatch(inter.bot.pool, msg_id)

            return bot, guild

        # ── only_voiced: só interessa bots que já estão no canal ──────────────
        # não abortamos a varredura completa — continuamos buscando
        # bots livres para o caso de nenhum estar no canal. A flag only_voiced
        # filtra a *preferência*, não impede selecionar um bot livre.
        if only_voiced:
            continue

        # ── Verifica permissão de envio no canal de texto ─────────────────────
        if not (channel := bot.get_channel(inter.channel.id)):
            continue

        if isinstance(channel, disnake.Thread):
            send_perm = channel.parent.permissions_for(channel.guild.me).send_messages_in_threads
        else:
            send_perm = channel.permissions_for(channel.guild.me).send_messages

        if not send_perm:
            if not guild.me.voice:
                bot_missing_perms.append(bot)
            continue

        # ── Bot livre (sem voice) → candidato ────────────────────────────────
        if not guild.me.voice:
            score = _score_free_bot(bot, guild)
            free_bot.append((bot, guild, score))
        else:
            # Bot ocupado em outro canal de voz
            voice_channels.append(guild.me.voice.channel.mention)

    # ══════════════════════════════════════════════════════════════════════════
    # SLASH COMMANDS: só chega aqui se nenhum bot estava no canal do usuário.
    # CORREÇÃO: não fazemos early-return para o próprio bot antes de verificar
    # a lista de bots livres. O early-return original causava o bot atual ser
    # escolhido mesmo quando já ocupado em outro canal.
    # ══════════════════════════════════════════════════════════════════════════
    is_slash = not isinstance(inter, CustomContext)

    if is_slash and not inter.guild.voice_client and not free_bot:
        # Nenhum bot livre encontrado e o bot atual também está livre
        # (sem voice_client) → usa o próprio bot normalmente.
        if only_voiced:
            inter.bot.dispatch("pool_dispatch", None, None)
            raise NoPlayer()

        inter.bot.dispatch("pool_dispatch", inter, None)
        return update_attr(inter, inter.bot, inter.guild)

    # ══════════════════════════════════════════════════════════════════════════
    # Seleção do melhor bot livre
    # ══════════════════════════════════════════════════════════════════════════
    if free_bot:
        # Ordena: maior score primeiro; empate → identifier lexicográfico
        free_bot.sort(key=lambda t: (-t[2], t[0].identifier))
        best_bot, best_guild, _ = free_bot[0]

        update_attr(inter, best_bot, best_guild)

        if (
            isinstance(inter, CustomContext)
            and not mention_prefixed
            and not bypass_prefix
            and msg_id
            and inter.music_bot.user.id != inter.bot.user.id
        ):
            # Sinaliza o vencedor para todos os bots aguardantes
            _resolve_dispatch(inter.bot.pool, msg_id, inter.music_bot.user.id)
            _cleanup_dispatch(inter.bot.pool, msg_id)
            raise PoolException()

        if msg_id:
            _resolve_dispatch(inter.bot.pool, msg_id, inter.music_bot.user.id)
            _cleanup_dispatch(inter.bot.pool, msg_id)

        return best_bot, best_guild

    elif check_player:
        inter.bot.dispatch("pool_dispatch", inter, None)

        if msg_id:
            _resolve_dispatch(inter.bot.pool, msg_id, None)
            _cleanup_dispatch(inter.bot.pool, msg_id)

        if return_first:
            return update_attr(inter, inter.bot, inter.guild)

        raise NoPlayer()

    # ══════════════════════════════════════════════════════════════════════════
    # Nenhum bot disponível — mensagem de erro detalhada
    # ══════════════════════════════════════════════════════════════════════════
    if msg_id:
        _resolve_dispatch(inter.bot.pool, msg_id, None)
        _cleanup_dispatch(inter.bot.pool, msg_id)

    components = []

    if not user_vc:
        raise NoVoice()

    if not bot_in_guild:
        msg = "**Não há bots de música compatíveis no servidor...**"
        if extra_bots_counter:
            msg += f"\n\nVocê terá que adicionar pelo menos um bot compatível clicando no botão abaixo:"
            components = [disnake.ui.Button(custom_id="bot_invite", label=f"Adicionar bot{'s'[:extra_bots_counter^1]}.")]
    else:
        if bot_missing_perms:
            msg = (
                f"**Há bots de música disponíveis no servidor mas estão sem permissão de enviar mensagens"
                f" no canal <#{inter.channel_id}>**:\n\n"
                + ", ".join(b.user.mention for b in bot_missing_perms)
            )
        else:
            msg = (
                "**Todos os bots estão em uso no momento...**\n\n"
                "**Você pode conectar em um dos canais abaixo onde há sessões ativas:**\n"
                + ", ".join(voice_channels)
            )

        if extra_bots_counter:
            if inter.author.guild_permissions.manage_guild:
                msg += "\n\n**Ou se preferir, você pode adicionar mais bots de música no servidor atual clicando no botão abaixo:**"
            else:
                msg += (
                    "\n\n**Ou, se preferir, você pode pedir para um administrador/manager do servidor para clicar"
                    " no botão abaixo para adicionar mais bots de música no servidor atual.**"
                )
            components = [disnake.ui.Button(custom_id="bot_invite", label="Adicione mais bots de música clicando aqui")]

    inter.bot.dispatch("pool_dispatch", inter, None)
    await inter.send(embed=disnake.Embed(description=msg, color=inter.bot.get_color()), components=components)
    raise PoolException()


# ─────────────────────────────────────────────────────────────────────────────
# Demais funções — sem alteração de comportamento
# ─────────────────────────────────────────────────────────────────────────────
# NOTA: substitua também get_prefix em utils/db.py pela versão em db.py gerado.

def has_player(check_node=True):

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if check_node and not player.node.is_available:
            raise wavelink.ZeroConnectedNodes()

        return True

    return commands.check(predicate)


def is_dj():

    async def predicate(inter):
        if not await has_perm(inter):
            raise NotDJorStaff()
        return True

    return commands.check(predicate)


def can_send_message_check():

    async def predicate(inter):

        if not inter.guild:
            if inter.guild_id:
                return True
            raise GenericError("**Este comando deve ser usado em um servidor...**")

        try:
            bot = inter.music_bot
        except Exception:
            bot = inter.bot

        if isinstance(inter.channel, disnake.PartialMessageable):
            try:
                await inter.response.defer(ephemeral=True)
                inter.channel = await bot.fetch_channel(inter.channel_id)
                thread_kw = {}
                if inter.channel.locked and inter.channel.parent.permissions_for(inter.channel.guild.me).manage_threads:
                    thread_kw.update({"locked": False, "archived": False})
                elif inter.channel.archived and inter.channel.owner_id == bot.user.id:
                    thread_kw["archived"] = False
                if thread_kw:
                    await inter.channel.edit(**thread_kw)
            except Exception:
                pass

        can_send_message(inter.channel, inter.guild.me)
        return True

    return commands.check(predicate)


def is_requester():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player: LavalinkPlayer = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if not player.current:
            raise NoSource()

        if player.current.requester == inter.author.id:
            return True

        try:
            if await has_perm(inter):
                return True
        except NotDJorStaff:
            pass

        raise NotRequester()

    return commands.check(predicate)


def check_voice():

    async def predicate(inter):

        try:
            guild = inter.music_guild
        except AttributeError:
            guild = inter.guild

        try:
            if not inter.author.voice:
                raise NoVoice()
        except AttributeError:
            pass

        if not guild.me.voice:
            perms = inter.author.voice.channel.permissions_for(guild.me)
            if not perms.connect:
                raise MissingVoicePerms(inter.author.voice.channel)

        try:
            if inter.author.id not in guild.me.voice.channel.voice_states:
                raise DiffVoiceChannel()
        except AttributeError:
            pass

        return True

    return commands.check(predicate)


def has_source():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if not player.current:
            raise NoSource()

        return True

    return commands.check(predicate)


def check_queue_loading():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if player.locked:
            raise GenericError(
                "**Não é possível executar essa ação com o processamento da música em andamento "
                "(por favor aguarde mais alguns segundos e tente novamente).**"
            )

        return True

    return commands.check(predicate)


def check_stage_topic():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player: LavalinkPlayer = bot.music.players[inter.guild_id]
        except KeyError:
            raise NoPlayer()

        if not player.guild.me.voice:
            raise NoPlayer()

        time_limit = 30 if isinstance(player.guild.me.voice.channel, disnake.VoiceChannel) else 120

        if player.stage_title_event and (
            time_ := int((disnake.utils.utcnow() - player.start_time).total_seconds())
        ) < time_limit and not (await bot.is_owner(inter.author)):
            raise GenericError(
                f"**Você terá que aguardar {time_format((time_limit - time_) * 1000, use_names=True)} para usar essa função "
                f"com o anúncio automático do palco ativo...**"
            )

        return True

    return commands.check(predicate)


def check_yt_cooldown():

    async def predicate(inter):

        try:
            bot = inter.music_bot
        except AttributeError:
            bot = inter.bot

        try:
            player: LavalinkPlayer = bot.music.players[inter.guild_id]
        except KeyError:
            return True

        if player.current and player.current.info["sourceName"] == "youtube" and (
            remaining := (disnake.utils.utcnow() - player.start_time).total_seconds()
        ) < bot.config["YOUTUBE_TRACK_COOLDOWN"]:
            if not await bot.is_owner(inter.author):
                raise GenericError(
                    "**{}, você só pode pular a música atual do youtube em {}**.\n"
                    "-# Isso é uma forma de ajudar a evitar possíveis bloqueios do youtube na reprodução da música".format(
                        inter.author.mention,
                        time_format(
                            (bot.config["YOUTUBE_TRACK_COOLDOWN"] - int(remaining)) * 1000,
                            use_names=True,
                        ),
                    )
                )

        return True

    return commands.check(predicate)


def user_cooldown(rate: int, per: int):
    def custom_cooldown(inter: disnake.Interaction):
        return commands.Cooldown(rate, per)
    return custom_cooldown


def get_available_bots_info(pool: BotPool, guild_id: int, member: disnake.Member):

    extra_bot_counter = 0
    available_bots = set()
    voice_channels = set()

    for b in pool.get_guild_bots(guild_id):

        if not b.bot_ready:
            continue

        try:
            p = b.music.players[guild_id]
        except KeyError:
            if not b.get_guild(guild_id):
                extra_bot_counter += 1
                continue
            available_bots.add(b.user.mention)
        else:
            if p.keep_connected or p.restrict_mode or not p.last_channel or not p.last_channel.permissions_for(member).connect:
                continue
            voice_channels.add(p.last_channel.mention)

    txts = []
    components = []

    if available_bots:
        abcount = len(available_bots)
        s = 's'[:abcount ^ 1]
        txts.append(
            f"Você pode usar outro{s} bot{s} de música disponíve{'is'[:abcount^1] or 'l'} no servidor "
            f"para usar em outro canal de voz: " + " ".join(available_bots)
        )
    else:
        t = ""
        if voice_channels:
            t += "Você pode se juntar em um dos canais com sessões ativas no servidor: " + " ".join(voice_channels)
        if extra_bot_counter:
            t += "\n\n" + ("Ou se preferir, você pode" if t else "Você pode")
            if not member.guild_permissions.manage_guild:
                t += "solicitar para um administrador do server "
            t += "adicionar mais bots de música clicando no botão abaixo."
            components = [disnake.ui.Button(custom_id="bot_invite", label="Adicione mais bots de música clicando aqui")]
        if t:
            txts.append(t)

    return "\n\n".join(txts), components


async def check_player_perm(inter, bot: BotCore, channel, guild_data: dict = None):

    try:
        guild_id = inter.guild_id
    except AttributeError:
        guild_id = inter.guild.id

    try:
        player: LavalinkPlayer = bot.music.players[guild_id]
    except KeyError:
        return True

    try:
        vc = player.guild.me.voice.channel
    except AttributeError:
        vc = player.last_channel

    if not isinstance(inter.guild, disnake.Guild):
        inter.author = player.guild.get_member(inter.author.id)

    if inter.author.guild_permissions.manage_channels:
        return True

    if player.keep_connected:
        txt, components = get_available_bots_info(bot.pool, player.guild_id, inter.author)
        raise GenericError(
            "Apenas membros com a permissão de **gerenciar canais** "
            f"podem usar esse comando/botão com o **modo 24/7 ativo** no canal <#{player.channel_id}>...\n\n" + txt,
            components=components,
        )

    if inter.author.id == player.player_creator or inter.author.id in player.dj:
        return True

    try:
        if vc.permissions_for(inter.author).move_members:
            return True
    except AttributeError:
        pass

    user_roles = [r.id for r in inter.author.roles]

    if not guild_data:
        guild_data = await bot.get_data(inter.guild_id, db_name=DBModel.guilds)

    if [r for r in guild_data['djroles'] if int(r) in user_roles]:
        return True

    if player.restrict_mode:
        txt, components = get_available_bots_info(bot.pool, player.guild_id, inter.author)
        raise GenericError(
            "Apenas DJ's ou membros com a permissão de **mover membros** "
            "podem usar este comando/botão com o **modo restrito ativo**...\n\n" + txt,
            components=components,
        )

    if not vc and inter.author.voice:
        player.dj.add(inter.author.id)

    elif not [
        m for m in vc.members
        if not m.bot and (
            vc.permissions_for(m).move_members
            or (m.id in player.dj)
            or m.id == player.player_creator
        )
    ]:
        player.dj.add(inter.author.id)
        await channel.send(
            embed=disnake.Embed(
                description=f"{inter.author.mention} foi adicionado à lista de DJ's por não haver um no canal <#{vc.id}>.",
                color=player.bot.get_color(),
            ),
            delete_after=10,
        )

    return True


async def has_perm(inter):

    try:
        bot = inter.music_bot
        channel = bot.get_channel(inter.channel.id)
    except AttributeError:
        bot = inter.bot
        channel = inter.channel

    await check_player_perm(inter=inter, bot=bot, channel=channel)
    return True


def check_channel_limit(member: disnake.Member, channel: Union[disnake.VoiceChannel, disnake.StageChannel]):

    if not channel.user_limit:
        return True
    if member.guild_permissions.move_members:
        return True
    if member.id in channel.voice_states:
        return True
    if (channel.user_limit - len(channel.voice_states)) > 0:
        return True


def can_connect(
        channel: Union[disnake.VoiceChannel, disnake.StageChannel],
        guild: disnake.Guild,
        check_other_bots_in_vc: bool = False,
        bot: Optional[BotCore] = None,
):
    perms = channel.permissions_for(guild.me)

    if not perms.connect:
        raise GenericError(f"**Não tenho permissão para conectar no canal {channel.mention}**")

    if not isinstance(channel, disnake.StageChannel):
        if not perms.speak:
            raise GenericError(f"**Não tenho permissão para falar no canal {channel.mention}**")
        if not guild.voice_client and not check_channel_limit(guild.me, channel):
            raise GenericError(f"**O canal {channel.mention} está lotado!**")

    if bot:
        for b in bot.pool.get_guild_bots(channel.guild.id):
            if b == bot:
                continue
            if b.bot_ready and b.user.id in channel.voice_states:
                raise PoolException()

    if check_other_bots_in_vc and any(m for m in channel.members if m.bot and m.id != guild.me.id):
        raise GenericError(f"**Há outro bot conectado no canal:** <#{channel.id}>")


async def check_deafen(me: disnake.Member = None):

    if me.voice.deaf:
        return True
    elif me.guild_permissions.deafen_members:
        try:
            await me.edit(deafen=True)
            return True
        except Exception:
            traceback.print_exc()
