import disnake
from disnake.ext import commands
from utils.client import BotCore

class Misc(commands.Cog):

    def __init__(self, bot: BotCore):
        self.bot = bot

    @commands.slash_command(description="Exibir meu link de convite para você me adicionar no seu servidor.")
    async def invite(self, inter: disnake.ApplicationCommandInteraction):

        await inter.send(
            embed = disnake.Embed(
                colour=inter.me.color,
                description=f"[**Clique aqui**](https://discord.com/api/oauth2/authorize?client_id={self.bot.user.id}&permissions=0&scope=bot%20applications.commands) "
                            f"para me adicionar no seu servidor."
            ),
            ephemeral=True
        )

    @commands.user_command(name="avatar")
    async def avatar(self, inter: disnake.UserCommandInteraction):

        embeds = []

        assets = {}

        user = await self.bot.fetch_user(inter.target.id) if not inter.target.bot else self.bot.get_user(
            inter.target.id)

        if inter.target.guild_avatar:
            assets["Avatar (Server)"] = inter.target.guild_avatar.with_static_format("png")
        assets["Avatar (User)"] = user.avatar.with_static_format("png")
        if user.banner:
            assets["Banner"] = user.banner.with_static_format("png")

        for name, asset in assets.items():
            embed = disnake.Embed(description=f"{inter.target.mention} **[{name}]({asset.with_size(2048).url})**",
                                  color=inter.guild.me.color)
            embed.set_image(asset.with_size(256).url)
            embeds.append(embed)

        await inter.response.send_message(embeds=embeds, ephemeral=True)


def setup(bot: BotCore):
    bot.add_cog(Misc(bot))