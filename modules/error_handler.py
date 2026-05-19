# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import traceback
from typing import TYPE_CHECKING, Optional, Union

import disnake
from aiohttp import ClientSession
from disnake.ext import commands

from utils.music.converters import URL_REG
from utils.music.errors import parse_error, PoolException
from utils.others import send_message, CustomContext, string_to_file, paginator, check_cmd

if TYPE_CHECKING:
    from utils.client import BotCore


def _should_handle_error(pool, key: str) -> bool:
    try:
        pool.message_ids[key]
        return False
    except KeyError:
        pool.message_ids[key] = None
        return True


def _error_key(ctx_or_inter) -> Optional[str]:
    try:
        return f"err:{ctx_or_inter.guild_id}:{ctx_or_inter.id}"
    except AttributeError:
        pass
    try:
        return f"err:{ctx_or_inter.guild_id}:{ctx_or_inter.channel.id}:{ctx_or_inter.message.id}"
    except AttributeError:
        pass
    return None


class ErrorHandler(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.components = []
        self.webhook_max_concurrency = commands.MaxConcurrency(1, per=commands.BucketType.guild, wait=True)

        if not self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"] and self.bot.config["ERROR_REPORT_WEBHOOK"]:
            self.components.append(
                disnake.ui.Button(
                    label="Reporte esse erro",
                    custom_id="report_error",
                    emoji="⚠️"
                )
            )

        if self.bot.config["SUPPORT_SERVER"]:
            self.components.append(
                disnake.ui.Button(
                    label="Servidor de suporte",
                    url=self.bot.config["SUPPORT_SERVER"],
                    emoji="💻"
                )
            )

    @commands.Cog.listener('on_interaction_player_error')
    async def on_inter_player_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception):

        if not isinstance(error, commands.MaxConcurrencyReached):
            try:
                await inter.application_command._max_concurrency.release(inter)
            except:
                pass

        await self.process_interaction_error(inter=inter, error=error)

    @commands.Cog.listener('on_custom_error')
    async def custom_error_event(
        self,
        ctx: Union[disnake.ApplicationCommandInteraction, CustomContext],
        error: Exception,
        resp_msg=False,
        **kwargs,
    ):
        if isinstance(ctx, (CustomContext, disnake.Message)):
            await self.on_legacy_command_error(ctx=ctx, error=error, resp_msg=resp_msg)
        else:
            await self.process_interaction_error(inter=ctx, error=error, resp_msg=resp_msg, **kwargs)

    @commands.Cog.listener('on_custom_slash_command_error')
    @commands.Cog.listener('on_user_command_error')
    @commands.Cog.listener('on_message_command_error')
    @commands.Cog.listener('on_slash_command_error')
    async def on_interaction_command_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception, **kwargs):
        await self.process_interaction_error(inter=inter, error=error, **kwargs)

    def build_report_embed(self, ctx_or_inter) -> disnake.Embed:

        embed = disnake.Embed(
            color=disnake.Color.red(),
            title="Relatório de erro"
        )

        try:
            embed.description = (
                f"Servidor: `{ctx_or_inter.guild}` (`{ctx_or_inter.guild_id}`)\n"
                f"Canal: `{ctx_or_inter.channel}` (`{ctx_or_inter.channel.id}`)\n"
                f"Usuário: `{ctx_or_inter.author}` (`{ctx_or_inter.author.id}`)"
            )
        except AttributeError:
            embed.description = "Não foi possível coletar todos os metadados do contexto."

        try:
            if command := getattr(ctx_or_inter, "command", None):
                embed.add_field(name="Comando", value=f"`{getattr(command, 'qualified_name', command)}`", inline=False)
        except Exception:
            pass

        try:
            if message := getattr(ctx_or_inter, "message", None):
                jump_url = getattr(message, "jump_url", None)
                if jump_url:
                    embed.add_field(name="Mensagem", value=f"[Abrir mensagem]({jump_url})", inline=False)
        except Exception:
            pass

        return embed

    async def process_interaction_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception, resp_msg=True, **kwargs):

        if isinstance(error, PoolException):
            return

        if inter.guild_id and not self.bot.pool.single_bot:
            key = _error_key(inter)
            if key and not _should_handle_error(self.bot.pool, key):
                return

        error_msg, full_error_msg, kill_process, components, mention_author = parse_error(inter, error, **kwargs)

        if isinstance(error, disnake.NotFound) and str(error).endswith("Unknown Interaction"):
            return

        kwargs = {"text": ""}
        color = disnake.Color.red()
        send_webhook = False

        try:
            if inter.message.author.bot or mention_author:
                kwargs["text"] = inter.author.mention
        except AttributeError:
            pass

        if not error_msg:

            components = self.components

            kwargs["embed"] = disnake.Embed(
                color=color,
                title="Ocorreu um erro no comando:",
                description=f"```py\n{repr(error)[:2030].replace(self.bot.http.token, 'mytoken')}```"
            )

            if self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"]:
                send_webhook = True
                kwargs["embed"].description += " `Meu desenvolvedor será notificado sobre o problema.`"

        else:

            kwargs["embeds"] = []

            for p in paginator(error_msg):
                kwargs["embeds"].append(disnake.Embed(color=color, description=p))

        if resp_msg:
            try:
                await send_message(inter, components=components, **kwargs)
            except:
                print(("-" * 50) + f"\n{error_msg}\n" + ("-" * 50))
                traceback.print_exc()
        else:
            send_webhook = True

        if kill_process:
            await asyncio.create_subprocess_shell("kill 1")
            return

        if not send_webhook or not full_error_msg:
            return

        try:
            await self.webhook_max_concurrency.acquire(inter)

            await self.send_webhook(
                embed=self.build_report_embed(inter),
                file=string_to_file(full_error_msg, "error_traceback_interaction.txt")
            )

            await asyncio.sleep(20)

            await self.webhook_max_concurrency.release(inter)

        except:
            traceback.print_exc()

    async def do_playcmd(self, ctx: CustomContext):

        if not self.bot.pool.config["ENABLE_SONGREQUEST_MENTION"]:
            ctx.bot.dispatch("custom_message", ctx.message)
            return

        query = str(ctx.message.content)

        for m in ctx.message.mentions:
            query = query.replace(m.mention, "", 1)

        query = query.strip()

        if query:

            play_cmd = self.bot.get_slash_command("play")

            try:
                await check_cmd(play_cmd, ctx)
                await play_cmd.callback(
                    inter=ctx, query=query,
                    self=play_cmd.cog, position=0, options=False, force_play="no",
                    manual_selection=False, server=None
                )
            except commands.CommandNotFound:
                return
            except Exception as e:
                await self.on_legacy_command_error(ctx, e)

    @commands.Cog.listener("on_command_error")
    async def on_legacy_command_error(self, ctx: CustomContext, error: Exception, resp_msg=True):

        if isinstance(error, PoolException):
            return

        if isinstance(error, commands.CommandNotFound):
            if ctx.prefix.startswith(self.bot.user.mention):
                await self.do_playcmd(ctx)
            return

        if isinstance(error, commands.NotOwner):
            print(f"{ctx.author} [{ctx.author.id}] não é dono do bot para usar o comando: {ctx.command.name}")
            return

        try:
            bot = ctx.bot
        except AttributeError:
            bot = self.bot

        if isinstance(error, commands.MissingPermissions) and (await bot.is_owner(ctx.author)):
            try:
                await ctx.reinvoke()
            except Exception as e:
                await self.on_legacy_command_error(ctx, e)
            return

        if isinstance(error, commands.TooManyArguments):
            if ctx.prefix.startswith(self.bot.user.mention):
                await self.do_playcmd(ctx)
            else:
                if ctx.cog:
                    try:
                        ctx.args.remove(ctx.cog)
                    except:
                        pass
                try:
                    await ctx.command(*ctx.args, **ctx.kwargs)
                except Exception as e:
                    await self.on_legacy_command_error(ctx, e)
            return

        if ctx.guild and not self.bot.pool.single_bot:

            bot_specific_errors = (
                commands.BotMissingPermissions,
                commands.BotMissingRole,
            )

            if not isinstance(error, bot_specific_errors):
                key = _error_key(ctx)
                if key and not _should_handle_error(self.bot.pool, key):
                    return

        error_msg, full_error_msg, kill_process, components, mention_author = parse_error(ctx, error)
        kwargs = {"content": ""}
        send_webhook = False

        if ctx.author.bot or mention_author:
            kwargs["content"] = ctx.author.mention

        if not error_msg:

            components = self.components

            if ctx.channel.permissions_for(ctx.guild.me).embed_links:
                kwargs["embed"] = disnake.Embed(
                    color=disnake.Colour.red(),
                    title="Ocorreu um erro no comando:",
                    description=f"```py\n{repr(error)[:2030].replace(self.bot.http.token, 'mytoken')}```"
                )
                if self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"]:
                    send_webhook = True
                    kwargs["embed"].description += " `Meu desenvolvedor será notificado sobre o problema.`"
            else:
                kwargs["content"] += "\n**Ocorreu um erro no comando:**\n" \
                                     f"```py\n{repr(error)[:2030].replace(self.bot.http.token, 'mytoken')}```"

        else:

            if ctx.channel.permissions_for(ctx.guild.me).embed_links:
                kwargs["embed"] = disnake.Embed(color=disnake.Colour.red(), description=error_msg)
            else:
                kwargs["content"] += f"\n{error_msg}"

        try:
            kwargs["delete_after"] = error.delete_original
        except AttributeError:
            pass

        try:
            if error.self_delete and ctx.channel.permissions_for(ctx.guild.me).manage_messages:
                await ctx.message.delete()
        except:
            pass

        if resp_msg:

            if hasattr(ctx, "inter"):
                if ctx.inter.response.is_done():
                    func = ctx.inter.edit_original_message
                else:
                    func = ctx.inter.response.edit_message
                kwargs.pop("delete_after", None)
            else:
                try:
                    func = ctx.store_message.edit
                except:
                    func = ctx.send

            await func(components=components, **kwargs)

        else:
            send_webhook = True

        if kill_process:
            await asyncio.create_subprocess_shell("kill 1")
            return

        if not send_webhook or not full_error_msg:
            return

        try:
            await self.webhook_max_concurrency.acquire(ctx)

            await self.send_webhook(
                embed=self.build_report_embed(ctx),
                file=string_to_file(full_error_msg, "error_traceback_prefixed.txt")
            )

            await asyncio.sleep(20)

            await self.webhook_max_concurrency.release(ctx)

        except:
            traceback.print_exc()

    async def send_webhook(
        self,
        content: str = None,
        embed: Optional[disnake.Embed] = None,
        file: Optional[disnake.File] = None
    ):
        if not self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"]:
            return

        kwargs = {
            "username": self.bot.user.name,
            "avatar_url": self.bot.user.display_avatar.replace(static_format='png').url,
        }

        if content:
            kwargs["content"] = content
        if embed:
            kwargs["embed"] = embed
        if file:
            kwargs["file"] = file

        async with ClientSession() as session:
            webhook = disnake.Webhook.from_url(self.bot.config["AUTO_ERROR_REPORT_WEBHOOK"], session=session)
            await webhook.send(**kwargs)

def setup(bot: BotCore):
    bot.add_cog(ErrorHandler(bot))
