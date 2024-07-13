# -*- coding: utf-8 -*-
import os
import traceback
from typing import Union, Optional

import disnake
from disnake.ext import commands
from disnake.utils import escape_mentions
from pymongo.errors import ServerSelectionTimeoutError

from utils.music.converters import time_format, perms_translations
from wavelink import WavelinkException, TrackNotFound, MissingSessionID


class PoolException(commands.CheckFailure):
    pass

class ArgumentParsingError(commands.CommandError):
    def __init__(self, message):
        super().__init__(escape_mentions(message))

class GenericError(commands.CheckFailure):

    def __init__(self, text: str, *, self_delete: int = None, delete_original: Optional[int] = None, components: list = None, error: str = None):
        self.text = text
        self.self_delete = self_delete
        self.delete_original = delete_original
        self.components = components
        self.error = error


class EmptyFavIntegration(commands.CheckFailure):
    pass

class MissingSpotifyClient(commands.CheckFailure):
    pass


class NoPlayer(commands.CheckFailure):
    pass


class NoVoice(commands.CheckFailure):
    pass


class MissingVoicePerms(commands.CheckFailure):

    def __init__(self, voice_channel: Union[disnake.VoiceChannel, disnake.StageChannel]):
        self.voice_channel = voice_channel


class DiffVoiceChannel(commands.CheckFailure):
    pass


class NoSource(commands.CheckFailure):
    pass


class NotDJorStaff(commands.CheckFailure):
    pass


class NotRequester(commands.CheckFailure):
    pass


class YoutubeSourceDisabled(commands.CheckFailure):
    pass


def parse_error(
        ctx: Union[disnake.ApplicationCommandInteraction, commands.Context, disnake.MessageInteraction],
        error: Exception
):

    error_txt = None

    kill_process = False

    mention_author = False

    components = []

    send_error = False

    error = getattr(error, 'original', error)

    if isinstance(error, NotDJorStaff):
        error_txt = "**DJ listesinde olmanız veya **Üyeleri Taşıma**iznine sahip olmanız gerekir " \
                    "bu komutu kullanmak için.**"

    elif isinstance(error, MissingVoicePerms):
        error_txt = f"**Kanala bağlanma/konuşma iznim yok:** {error.voice_channel.mention}"

    elif isinstance(error, commands.NotOwner):
        error_txt = "**Bu komutu yalnızca geliştiricilerim kullanabilir.**"

    elif isinstance(error, commands.BotMissingPermissions):
        error_txt = "Bu komutu çalıştırmak için aşağıdaki izinlere sahip değilim: ```\n{}```" \
            .format(", ".join(perms_translations.get(perm, perm) for perm in error.missing_permissions))

    elif isinstance(error, commands.MissingPermissions):
        error_txt = "Bu komutu çalıştırmak için aşağıdaki izinlere sahip değilsiniz: ```\n{}```" \
            .format(", ".join(perms_translations.get(perm, perm) for perm in error.missing_permissions))

    elif isinstance(error, GenericError):
        error_txt = error.text
        components = error.components
        if error.text:
            send_error = True

    elif isinstance(error, NotRequester):
        error_txt = "**Geçerli şarkıyı talep etmiş olmanız veya DJ listesinde olmanız veya izin sahibi olmanız gerekir. " \
                    "**Şarkıları atlamak için kanalları yönetin**.**"

    elif isinstance(error, DiffVoiceChannel):
        error_txt = "**Bu komutu kullanabilmek için mevcut ses kanalımda olmanız gerekir.**"

    elif isinstance(error, NoSource):
        error_txt = "**Şu anda oynatıcıda şarkı yok.**"

    elif isinstance(error, NoVoice):
        error_txt = "**Bu komutu kullanmak için bir ses kanalına katılmalısınız.**"

    elif isinstance(error, NoPlayer):
        try:
            error_txt = f"**Kanalda aktif oyuncu yok {ctx.author.voice.channel.mention}.**"
        except AttributeError:
            error_txt = "**Sunucuda başlatılan oyuncu yok.**"

    elif isinstance(error, (commands.UserInputError, commands.MissingRequiredArgument)) and ctx.command.usage:

        error_txt = "### Komutu yanlış kullandınız.\n"

        if ctx.command.usage:

            prefix = ctx.prefix if str(ctx.me.id) not in ctx.prefix else f"@{ctx.me.display_name} "

            error_txt += f'📘 **⠂Nasıl kullanılır:** ```\n{ctx.command.usage.replace("{prefix}", prefix).replace("{cmd}", ctx.command.name).replace("{parent}", ctx.command.full_parent_name)}```\n' \
                        f"⚠️ **⠂Komutta bağımsız değişkenlerin kullanımına ilişkin notlar:** ```\n" \
                        f"[] = Zorunlu | <> = İsteğe bağlı```\n"

    elif isinstance(error, MissingSpotifyClient):
        error_txt = "**Spotify bağlantıları şu anda desteklenmiyor.**"

    elif isinstance(error, commands.NoPrivateMessage):
        error_txt = "Bu komut özel mesajlarda çalıştırılamaz."

    elif isinstance(error, MissingSessionID):
        error_txt = f"**{error.node.identifier} müzik sunucusunun bağlantısı kesildi, lütfen birkaç saniye bekleyip tekrar deneyin.**"

    elif isinstance(error, commands.CommandOnCooldown):
        remaing = int(error.retry_after)
        if remaing < 1:
            remaing = 1
        error_txt = "**Bu komutu kullanmak için {} beklemelisiniz.**".format(time_format(int(remaing) * 1000, use_names=True))

    elif isinstance(error, EmptyFavIntegration):

        if isinstance(ctx, disnake.MessageInteraction):
            error_txt = "**Favoriniz/entegrasyonunuz yok**\n\n" \
                        "`İsterseniz bunu kullanmak için favori veya entegrasyon ekleyebilirsiniz. " \
                        "bir dahaki sefere bu düğmeyi kullanın. Bunu yapmak için aşağıdaki düğmelerden birine tıklayabilirsiniz..`"
        else:
            error_txt = "**Komutu bir şarkının veya videonun adını veya bağlantısını eklemeden kullandınız ve " \
                        "Bu komutu doğrudan bu şekilde kullanmak için favoriler veya entegrasyonlar ...**\n\n" \
                        "`İsterseniz bunu kullanmak için favori veya entegrasyon ekleyebilirsiniz. " \
                        "bir ad veya bağlantı eklemeden komut. Bunu yapmak için aşağıdaki düğmelerden birine tıklayabilirsiniz..`"

        mention_author = True

        components = [
            disnake.ui.Button(label="Yer imi yöneticisini açın",
                              custom_id="musicplayer_fav_manager", emoji="⭐"),
            disnake.ui.Button(label="Entegrasyon yöneticisini açın",
                              custom_id="musicplayer_integration_manager", emoji="💠")
        ]

    elif isinstance(error, commands.MaxConcurrencyReached):
        txt = f"{error.number} vezes " if error.number > 1 else ''
        txt = {
            commands.BucketType.member: f"bu komutu {txt} sunucuda zaten kullandınız",
            commands.BucketType.guild: f"bu komut {txt} sunucuda zaten kullanıldı",
            commands.BucketType.user: f"bu komutu {txt} zaten kullandınız",
            commands.BucketType.channel: f"bu komut {txt} mevcut kanalda zaten kullanıldı",
            commands.BucketType.category: f"bu komut {txt} mevcut kanalın kategorisinde zaten kullanıldı",
            commands.BucketType.role: f"bu komut {txt} izin verilen role sahip bir üye tarafından zaten kullanıldı",
            commands.BucketType.default: f"bu komut {txt} birisi tarafından zaten kullanıldı"
        }

        error_txt = f"{ctx.author.mention} **{txt[error.per]} ve hala kullanımınız bitmemiş {' ' if error.number > 1 else ''} " \
                    f" {' ' if error.number > 1 else ''}  {' ' if error.number > 1 else ''}!**"

    elif isinstance(error, TrackNotFound):
        error_txt = "**Aramanıza ilişkin hiç sonuç bulunamadı...**"

    elif isinstance(error, YoutubeSourceDisabled):
        error_txt = "YouTube'un kendisinin aldığı güçlendirilmiş önlemler nedeniyle YouTube bağlantıları/arama desteği devre dışı bırakıldı " \
                     "bu, YouTube bağlantılarının yerel olarak çalışmasını engeller. Bununla ilgili YouTube yayınına göz atmak isterseniz şunları yapabilirsiniz: [buraya tıklayın](<https://support.google.com/youtube/thread/269521462/enforcement-on-third-party-apps?hl=en>)."

    if isinstance(error, ServerSelectionTimeoutError) and os.environ.get("REPL_SLUG"):
        error_txt = "Repl.it'te veritabanıma bağlanmamı engelleyen bir DNS hatası algılandı " \
                    "mongo/atlas'tan. Yeniden başlayacağım ve yakında tekrar müsait olacağım..."
        kill_process = True

    elif isinstance(error, WavelinkException):
        if "Unknown file format" in (wave_error := str(error)):
            error_txt = "**Belirtilen bağlantı desteklenmiyor...**"
        elif "No supported audio format" in wave_error:
            error_txt = "**Sağlanan bağlantı desteklenmiyor.**"
        elif "This video is not available" in wave_error:
            error_txt = "**Bu video kullanılamıyor veya özel...**"
        elif "This playlist type is unviewable" in wave_error:
            error_txt = "**Çalma listesi bağlantısı desteklenmeyen bir parametre/kimlik içeriyor...**"
        elif "The playlist does not exist" in wave_error:
            error_txt = "**Çalma listesi mevcut değil (veya gizli).**"
        elif "bu video ülkenizde kullanıma sunulmadı" in wave_error.lower() or \
                "ülkenizde telif hakkı gerekçesiyle kim engelledi" in wave_error.lower():
            error_txt = "**Bu bağlantının içeriği çalıştığım bölgede mevcut değil...**"

    full_error_txt = ""

    if not error_txt:
        full_error_txt = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        print(full_error_txt)
    elif send_error:
        full_error_txt = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    return error_txt, full_error_txt, kill_process, components, mention_author
