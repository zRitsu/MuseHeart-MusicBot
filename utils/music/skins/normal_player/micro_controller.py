from utils.music.models import LavalinkPlayer
import disnake
from utils.music.converters import fix_characters, get_button_style
from utils.others import PlayerControls


class MicroController:

    __slots__ = ("name", "preview")

    def __init__(self):
        self.name = "micro_controller"
        self.preview = "https://media.discordapp.net/attachments/554468640942981147/1050285454186000464/micro_controller.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = True
        player.auto_update = 0
        player.hint_rate = player.bot.config["HINT_RATE"]
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": [],
        }

        embed_color = player.bot.get_color(player.guild.me)

        embed = disnake.Embed(
            color=embed_color,
            description=f"[`{fix_characters(player.current.single_title, 25)}`]({player.current.uri}) "
                        f"[`{fix_characters(player.current.author, 12)}`] <@{player.current.requester}>"
        )

        embed.set_author(
            name="Tocando Agora:",
            icon_url="https://media.discordapp.net/attachments/480195401543188483/987633257178882108/Equalizer.gif"
        )

        if player.command_log:
            embed.description += f"\n\n{player.command_log_emoji} ⠂**Última Interação:** {player.command_log}"

        if player.current_hint:
            embed_hint = disnake.Embed(colour=embed_color)
            embed_hint.set_footer(text=f"💡 Dica: {player.current_hint}")
            data["embeds"].append(embed_hint)

        data["embeds"].append(embed)

        data["components"] = [
            disnake.ui.Button(label="Despausar" if player.paused else "Pausar", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(label="Voltar", custom_id=PlayerControls.back),
            disnake.ui.Button(label="Parar", custom_id=PlayerControls.stop, style=disnake.ButtonStyle.red),
            disnake.ui.Button(label="Pular", custom_id=PlayerControls.skip),
            disnake.ui.Button(label="Fila", custom_id=PlayerControls.queue)
        ]

        return data

def load():
    return MicroController()
