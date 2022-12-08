from utils.music.models import LavalinkPlayer
import disnake
from utils.music.converters import fix_characters

class MicroNC:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = "micro_nc"
        self.preview = "https://media.discordapp.net/attachments/554468640942981147/1050275579766784051/micro_nc.png"

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        embed = disnake.Embed(
            color=player.bot.get_color(player.guild.me),
            description=f"🎶 **⠂[{fix_characters(player.current.title, 30)}]({player.current.uri})** `[{fix_characters(player.current.author, 12)}]`"
        )

        data["embeds"].append(embed)

        if player.current_hint:
            data["embeds"].append(disnake.Embed(color=player.bot.get_color(player.guild.me)).set_footer(text=f"💡 Dica: {player.current_hint}"))

        player.hint_rate = 9
        player.controller_mode = False
        player.mini_queue_feature = False

        return data

def load():
    return MicroNC()
