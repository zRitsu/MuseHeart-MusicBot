import disnake
from disnake.ext import commands


class Test(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

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


def setup(bot):
    bot.add_cog(Test(bot))
