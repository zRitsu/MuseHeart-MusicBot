from __future__ import annotations
import disnake
from .converters import time_format, fix_characters
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..client import BotCore


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

    async def callback(self, interaction: disnake.MessageInteraction):
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
        self.embed = disnake.Embed(color=player.bot.get_color(user.guild.me))
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
                       (f" - `Repetições: {t.track_loops}`" if t.track_loops else  "") + f" - {t.requester.mention}\n`---------`\n"

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

    def __init__(self, items, bot: BotCore):
        super().__init__(timeout=30)
        self.tracks = items
        self.message = None
        self.track = None
        self.bot = bot

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
            description=f"> 🎵 **┃ Selecionado:** [`{self.track.title}`]({self.track.uri})\n" \
                        f"> 💠 **┃ Uploader:** `{self.track.author}`\n" \
                        f"> ✋ **┃ Pedido por:** {interaction.author.mention}\n" \
                        f"> ⌛ **┃ Duração:** `{time_format(self.track.duration) if not self.track.is_stream else '🔴 Livestream'}` ",
            color=self.bot.get_color(interaction.guild.me)
        ).set_thumbnail(self.track.thumb)
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()


class SelectInteraction(disnake.ui.View):

    def __init__(self, user: disnake.Member, opts: List[disnake.SelectOption], *, timeout=180):
        super().__init__(timeout=timeout)
        self.user = user
        self.selected = opts[0].value
        select_menu = disnake.ui.Select(placeholder='Selecione uma opção:', options=opts)
        select_menu.callback = self.callback
        self.add_item(select_menu)
        self.inter = None

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:

        if interaction.user == self.user:
            return True

        await interaction.send(f"Apenas {self.user} pode interagir aqui.", ephemeral = True)

    async def callback(self, interaction: disnake.Interaction):
        self.selected = interaction.data.values[0]
        self.inter = interaction
        self.stop()
