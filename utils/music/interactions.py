from __future__ import annotations
import disnake
from disnake.ext import commands
import asyncio
from .converters import percentage, time_format, fix_characters
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .models import LavalinkPlayer, YTDLPlayer


async def send_message(
        inter: Union[disnake.Interaction, disnake.ApplicationCommandInteraction],
        text=None,
        *,
        embed: disnake.Embed = None,
):

    if inter.type.name != "application_command":
        ephemeral = True

    if inter.response.is_done():
        await inter.edit_original_message(content=text, embed=embed)
    else:
        await inter.send(text, embed=embed, ephemeral=True)


class VolumeInteraction(disnake.ui.View):

    def __init__(self, inter):
        self.inter = inter
        self.volume = None
        super().__init__(timeout=30)
        self.process_buttons()

    def process_buttons(self):

        opts = []

        for l in [5, 20, 40, 60, 80, 100, 120, 150]:

            if l > 100:
                description = "Acima de 100% o audio pode ficar bem ruim."
            else:
                description = None
            opts.append(disnake.SelectOption(label=f"{l}%", value=f"vol_{l}", description=description))

        select = disnake.ui.Select(placeholder='Nível:', options=opts)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: disnake.Interaction):
        await interaction.response.edit_message(content=f"Volume alterado!",embed=None, view=None)
        self.volume = int(interaction.data.values[0][4:])
        self.stop()


class QueueInteraction(disnake.ui.View):

    def __init__(self, player, user: disnake.Member, timeout=60):

        self.player = player
        self.user = user
        self.pages = []
        self.current = 0
        self.max_page = len(self.pages) - 1
        super().__init__(timeout=timeout)
        self.embed = disnake.Embed(color=user.guild.me.color)
        self.update_pages()
        self.update_embed()

    def update_pages(self):

        counter = 1

        entries = list(self.player.queue)

        self.pages = [entries[i:i + 8] for i in range(0, len(entries), 8)]

        for n, page in enumerate(self.pages):

            txt = "\n"
            for t in page:
                txt += f"`{counter})` [`{fix_characters(t.title, limit=50)}`]({t.uri})\n" \
                       f"`[{time_format(t.duration) if not t.is_stream else '🔴 Livestream'}]`" + \
                       (f" - `Repetições: {t.repeats}`" if t.repeats else  "") + f" - {t.requester.mention}\n`---------`\n"

                counter += 1

            self.pages[n] = txt

        self.current = 0
        self.max_page = len(self.pages) - 1

    def update_embed(self):
        self.embed.title = f"**Músicas da fila [{self.current+1} / {self.max_page+1}]**"
        self.embed.description = self.pages[self.current]

    @disnake.ui.button(emoji='⏮️', style=disnake.ButtonStyle.grey)
    async def first(self, button, interaction: disnake.MessageInteraction):

        self.current = 0
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed)

    @disnake.ui.button(emoji='⬅️', style=disnake.ButtonStyle.grey)
    async def back(self, button, interaction: disnake.MessageInteraction):

        if self.current == 0:
            self.current = self.max_page
        else:
            self.current -= 1
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed)

    @disnake.ui.button(emoji='➡️', style=disnake.ButtonStyle.grey)
    async def next(self, button, interaction: disnake.MessageInteraction):

        if self.current == self.max_page:
            self.current = 0
        else:
            self.current += 1
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed)

    @disnake.ui.button(emoji='⏭️', style=disnake.ButtonStyle.grey)
    async def last(self, button, interaction: disnake.MessageInteraction):

        self.current = self.max_page
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed)

    @disnake.ui.button(emoji='⏹️', style=disnake.ButtonStyle.grey)
    async def stop_interaction(self, button, interaction: disnake.MessageInteraction):

        await interaction.response.edit_message(content="Queue fechada", embed=None, view=None)
        self.stop()

    @disnake.ui.button(emoji='🔄', label="Refresh", style=disnake.ButtonStyle.grey)
    async def update_q(self, button, interaction: disnake.MessageInteraction):

        self.update_pages()
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed)


class SongSelect(disnake.ui.View):

    def __init__(self, items):
        super().__init__(timeout=30)
        self.tracks = items
        self.message = None
        self.track = None

        tracks = []

        for n, t in enumerate(items[:25]):
            tracks.append(disnake.SelectOption(label=t.title, value=str(n), description=f"{t.author} [{time_format(t.duration)}]"))

        select = disnake.ui.Select(placeholder='Resultados:', options=tracks)
        select.callback = self.callback
        self.add_item(select)

    async def on_timeout(self) -> None:
        await self.message.edit(content="Tempo esgotado!", embed=None, view=None)

    async def callback(self, interaction: disnake.Interaction):
        self.track = self.tracks[int(interaction.data.values[0])]
        embed = disnake.Embed(
            description=f"**Música selecionada:** [`{self.track.title}`]({self.track.uri})\n\n"
                        f"`{self.track.author}` | `{time_format(self.track.duration) if not self.track.is_stream else '🔴 Livestream'}`",
            color=interaction.guild.me.color
        ).set_thumbnail(self.track.thumb)
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class PlayerInteractions(disnake.ui.View):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: disnake.Interaction):

        player: Union[LavalinkPlayer, YTDLPlayer] = self.bot.music.players.get(interaction.guild.id)

        if player.interaction_cooldown:
            await interaction.response.send_message("O player está em cooldown, tente novamente em instantes.",
                                                    ephemeral=True)
            return

        vc = self.bot.get_channel(player.channel_id)

        if interaction.user not in vc.members:
            embed = disnake.Embed(
                description=f"Você deve estar no canal <#{vc.id}> para usar isto.",
                color=disnake.Colour.red()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        control = interaction.data.custom_id[12:]

        kwargs = {}

        if control == "help":

            embed = disnake.Embed(
                description=f"📘 **IFORMAÇÕES SOBRE OS BOTÕES** 📘\n\n"
                            f"⏯️ `= Pausar/Retomar a música.`\n"
                            f"⏮️ `= Voltar para a música tocada anteriormente.`\n"
                            f"⏭️ `= Pular para a próxima música.`\n"
                            f"🔀 `= Misturar as músicas da fila.`\n"
                            f"🇳 `= Ativar/Desativar o efeito Nightcore`\n"
                            f"⏹️ `= Parar o player e me desconectar do canal.`\n"
                            f"🔊 `= Ajustar volume.`\n"
                            f"🔁 `= Ativar/Desativar repetição.`\n"
                            f"📑 `= Exibir a fila de música.`\n",
                color=interaction.guild.me.color
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        elif control == "volume":
            kwargs = {"value": None}

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

        self.bot.get_slash_command(control)

        cmd = self.bot.get_slash_command(control)

        if not cmd:
            await interaction.response.send_message(f"comando {control} não encontrado/implementado.", ephemeral=True)
            return

        interaction.player = player

        try:

            bucket = cmd._buckets.get_bucket(interaction) # type: ignore
            if bucket:
                retry_after = bucket.update_rate_limit()
                if retry_after:
                    raise commands.CommandOnCooldown(cooldown=bucket, retry_after=retry_after, type=cmd._buckets.type)

            try:
                #interaction.user_data = await self.bot.db.get_data(interaction.author.id, db_name="users")
                interaction.guild_data = await self.bot.db.get_data(interaction.guild.id, db_name="guilds")
            except AttributeError:
                #interaction.user_data = None
                interaction.guild_data = None


            await cmd(interaction, **kwargs)

            player.interaction_cooldown = True
            await asyncio.sleep(1)
            player.interaction_cooldown = False

        except Exception as e:
            self.bot.dispatch('slash_command_error', interaction, e)
