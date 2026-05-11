import os
import shutil
from pathlib import Path

LOCAL_AUDIO_ROOT = Path("local_audio")
LOCAL_NODE_DIRNAME_PREFIX = "node-"
LEGACY_LOCAL_AUDIO_ITEMS = (
    "node-v23.7.0-win-x64",
    "yt-cipher",
    "NodeLink",
    "Lavalink.jar",
    "application.yml",
    "config.js",
    "config.js.bak",
    "config.default.js",
    "lavalink.ini",
    "auto_lavalink.ini",
)


def ensure_local_audio_root() -> Path:
    LOCAL_AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
    return LOCAL_AUDIO_ROOT


def get_local_audio_root() -> Path:
    return ensure_local_audio_root()


def local_audio_path(*parts: str) -> Path:
    return ensure_local_audio_root().joinpath(*parts)


def local_audio_abspath(*parts: str) -> str:
    return str(local_audio_path(*parts).resolve())


def get_node_portable_dir() -> Path:
    root = ensure_local_audio_root()
    for child in root.iterdir():
        if child.is_dir() and child.name.startswith(LOCAL_NODE_DIRNAME_PREFIX):
            return child
    return root


def get_node_portable_file(*parts: str) -> str:
    return str(get_node_portable_dir().joinpath(*parts).resolve())


def get_nodelink_dir() -> str:
    return local_audio_abspath("NodeLink")


def get_yt_cipher_dir() -> str:
    return local_audio_abspath("yt-cipher")


def get_lavalink_jar_path() -> str:
    return local_audio_abspath("Lavalink.jar")


def get_application_yml_path() -> str:
    return local_audio_abspath("application.yml")


def get_lavalink_ini_path() -> str:
    return local_audio_abspath("lavalink.ini")


def get_auto_lavalink_ini_path() -> str:
    return local_audio_abspath("auto_lavalink.ini")


def get_config_js_path() -> str:
    return local_audio_abspath("config.js")


def get_config_default_js_path() -> str:
    return local_audio_abspath("config.default.js")


def get_config_js_backup_path() -> str:
    return local_audio_abspath("config.js.bak")


def get_yt_cookie_path() -> str:
    preferred = local_audio_abspath(".ytcookie")
    legacy = str(Path(".ytdl_cookie").resolve())
    if os.path.isfile(preferred):
        return preferred
    if os.path.isfile(legacy):
        return legacy
    return preferred


def migrate_legacy_local_audio_files() -> list[str]:
    root = Path.cwd()
    target_root = ensure_local_audio_root()
    moved_items = []

    for item_name in LEGACY_LOCAL_AUDIO_ITEMS:
        source = root / item_name
        target = target_root / item_name

        if not source.exists() or source.resolve() == target.resolve():
            continue

        if target.exists():
            continue

        shutil.move(str(source), str(target))
        moved_items.append(item_name)

    legacy_cookie = root / ".ytdl_cookie"
    target_cookie = target_root / ".ytcookie"
    if legacy_cookie.exists() and not target_cookie.exists():
        shutil.move(str(legacy_cookie), str(target_cookie))
        moved_items.append(".ytdl_cookie -> .ytcookie")

    legacy_cookie_txt = root / ".ytcookie.txt"
    if legacy_cookie_txt.exists() and not target_cookie.exists():
        shutil.move(str(legacy_cookie_txt), str(target_cookie))
        moved_items.append(".ytcookie.txt -> .ytcookie")

    if moved_items:
        print(
            "📦 - Arquivos locais migrados para local_audio: "
            + ", ".join(moved_items)
        )

    return moved_items
