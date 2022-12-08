from utils.music.models import LavalinkPlayer
import disnake
from utils.music.converters import fix_characters, time_format

class LiteSkin:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = "lite"
        self.preview = "https://cdn.discordapp.com/attachments/554468640942981147/1047184549425184888/skin_lite.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = False
        player.auto_update = 0
        player.hint_rate = 9
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        embed = disnake.Embed(color=player.bot.get_color(player.guild.me))

        duration = "`🔴 Livestream`" if player.current.is_stream else \
            time_format(player.current.duration)

        embed.description = f"> ▶️ **┃**[`{fix_characters(player.current.title, 45)}`]({player.current.uri})\n" \
                            f"> ℹ️ **┃**`{duration}`┃`{fix_characters(player.current.author, 18)}`┃<@{player.current.requester}>"

        if player.current.playlist_name:
            embed.description += f"\n> 🎼 **┃ Playlist:** [`{player.current.playlist_name}`]({player.current.playlist_url})"

        data["embeds"].append(embed)

        if player.current_hint:
            data["embeds"].append(disnake.Embed(color=player.bot.get_color(player.guild.me)).set_footer(text=f"💡 Dica: {player.current_hint}"))

        return data

def load():
    return LiteSkin()
