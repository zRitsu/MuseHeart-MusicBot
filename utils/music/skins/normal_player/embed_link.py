import datetime
import itertools
import re
import disnake
from utils.music.models import LavalinkPlayer
from utils.music.converters import time_format, fix_characters, get_button_style
from utils.others import PlayerControls


class EmbedLinkSkin:

    __slots__ = ("name", "preview")

    def __init__(self):

        self.name = "embed_link"
        self.preview = "https://cdn.discordapp.com/attachments/554468640942981147/1050297414986252308/embed_link.png"

    def setup_features(self, player: LavalinkPlayer):
        player.mini_queue_feature = False
        player.controller_mode = True
        player.auto_update = 0
        player.hint_rate = player.bot.config["HINT_RATE"]
        player.static = False

    def load(self, player: LavalinkPlayer) -> dict:

        data = {
            "content": None,
            "embeds": []
        }

        txt = ""

        if player.current_hint:
            txt += f"> `💡 Dica: {player.current_hint}`\n> \n"

        if player.current.is_stream:
            duration_txt = f"\n> 🔴 **⠂Duração:** `Livestream`"
        else:
            duration_txt = f"\n> ⏰ **⠂Duração:** `{time_format(player.current.duration)}`"

        if player.paused:
            txt += f"> ⏸️ **⠂Em Pausa:** {player.current.uri}{duration_txt}"

        else:
            txt += f"> ▶️ **⠂Tocando Agora:** {player.current.uri}{duration_txt}"
            if not player.current.is_stream:
                txt += f" `[`<t:{int((disnake.utils.utcnow() + datetime.timedelta(milliseconds=player.current.duration - player.position)).timestamp())}:R>`]`" \
                if not player.paused else ''

        txt += f" <@{player.current.requester}>\n"

        if player.command_log:

            log = re.sub(r"\[(.+)]\(.+\)", r"\1", player.command_log.replace("`", "")) # remover links do command_log p/ evitar gerar mais de uma preview.

            txt += f"> {player.command_log_emoji} **⠂Última Interação:** {log}\n"

        if qsize := len(player.queue):

            qtext = "**Músicas na fila:**\n```ansi\n" + \
                              "\n".join(
                                  f"[0;33m{(n + 1):02}[0m [0;34m[{time_format(t.duration) if not t.is_stream else '🔴 stream'}][0m [0;36m{fix_characters(t.title, 45)}[0m"
                                  for n, t in enumerate(
                                      itertools.islice(player.queue, 4)))

            if qsize  > 4:
                qtext += f"\n╚═ [0;37mE mais[0m [0;35m{qsize}[0m [0;37mmúsicas(s).[0m"

            txt = qtext + "```\n" + txt

        data["content"] = txt

        data["components"] = [
            disnake.ui.Button(emoji="⏯️", custom_id=PlayerControls.pause_resume, style=get_button_style(player.paused)),
            disnake.ui.Button(emoji="⏮️", custom_id=PlayerControls.back),
            disnake.ui.Button(emoji="⏹️", custom_id=PlayerControls.stop),
            disnake.ui.Button(emoji="⏭️", custom_id=PlayerControls.skip),
            disnake.ui.Button(emoji="📑", custom_id=PlayerControls.queue),
            disnake.ui.Select(
                placeholder="Mais opções:",
                custom_id="musicplayer_dropdown_inter",
                min_values=0, max_values=1,
                options=[
                    disnake.SelectOption(
                        label="Adicionar música", emoji="<:add_music:588172015760965654>",
                        value=PlayerControls.add_song,
                        description="Adicionar uma música/playlist na fila."
                    ),
                    disnake.SelectOption(
                        label="Adicionar favorito", emoji="⭐",
                        value=PlayerControls.enqueue_fav,
                        description="Adicionar um de seus favoritos na fila."
                    ),
                    disnake.SelectOption(
                        label="Tocar do inicio", emoji="⏪",
                        value=PlayerControls.seek_to_start,
                        description="Voltar o tempo da música atual para o inicio."
                    ),
                    disnake.SelectOption(
                        label="Volume", emoji="🔊",
                        value=PlayerControls.volume,
                        description="Ajustar volume."
                    ),
                    disnake.SelectOption(
                        label="Misturar", emoji="🔀",
                        value=PlayerControls.shuffle,
                        description="Misturar as músicas da fila."
                    ),
                    disnake.SelectOption(
                        label="Readicionar", emoji="🎶",
                        value=PlayerControls.readd,
                        description="Readicionar as músicas tocadas de volta na fila."
                    ),
                    disnake.SelectOption(
                        label="Repetição", emoji="🔁",
                        value=PlayerControls.loop_mode,
                        description="Ativar/Desativar repetição da música/fila."
                    ),
                    disnake.SelectOption(
                        label="Nightcore", emoji="🇳",
                        value=PlayerControls.nightcore,
                        description="Ativar/Desativar o efeito nightcore."
                    ),
                    disnake.SelectOption(
                        label="Ativar/Desativar modo restrito", emoji="🔐",
                        value=PlayerControls.restrict_mode,
                        description="Apenas DJ's/Staff's podem usar comandos restritos."
                    ),
                ]
            ),
        ]

        if player.mini_queue_feature:
            data["components"][5].options.append(
                disnake.SelectOption(
                    label="Mini-fila do player", emoji="<:music_queue:703761160679194734>",
                    value=PlayerControls.miniqueue,
                    description="Ativar/Desativar a mini-fila do player."
                )
            )

        return data

def load():
    return EmbedLinkSkin()