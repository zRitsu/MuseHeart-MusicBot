from utils.music.models import LavalinkPlayer
import disnake
from utils.music.converters import fix_characters, time_format


def load(player: LavalinkPlayer) -> dict:

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

    player.hint_rate = 9
    player.controller_mode = False

    return data
