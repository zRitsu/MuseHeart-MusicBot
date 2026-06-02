# -*- coding: utf-8 -*-
from __future__ import annotations

import collections.abc
import asyncio
import json
import os
import platform
import subprocess
import shutil
import tarfile
import time
import traceback
import zipfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Union
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

import disnake
import requests
from cachetools import TTLCache
from disnake.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

if TYPE_CHECKING:
    from utils.client import BotCore

class DBModel:
    guilds = "guilds"
    users = "users"
    default = "default"


db_models = {
    DBModel.guilds: {
        "ver": 1.10,
        "player_controller": {
            "channel": None,
            "message_id": None,
            "skin": None,
            "static_skin": None,
            "fav_links": {},
        },
        "autoplay": False,
        "check_other_bots_in_vc": False,
        "enable_restrict_mode": False,
        "default_player_volume": 100,
        "enable_prefixed_commands": True,
        "djroles": []
    },
    DBModel.users: {
        "ver": 1.0,
        "fav_links": {},
    }
}

scrobble_model = {
    DBModel.users: {
        "ver": 1.0,
        "tracks": []
    }
}

global_db_models = {
    DBModel.users: {
        "ver": 1.6,
        "fav_links": {},
        "integration_links": {},
        "token": "",
        "custom_prefix": "",
        "last_tracks": [],
        "lastfm": {
            "username": "",
            "sessionkey": "",
            "scrobble": False,
        }
    },
    DBModel.guilds: {
        "ver": 1.4,
        "prefix": "",
        "global_skin": False,
        "player_skin": None,
        "player_skin_static": None,
        "voice_channel_status": "",
        "custom_skins": {},
        "custom_skins_static": {},
        "listen_along_invites": {},
    },
    DBModel.default: {
        "ver": 1.0,
        "extra_tokens": {}
    }
}


async def get_prefix(bot: BotCore, message: disnake.Message):

    content = str(message.content)

    # ── Menção deste bot como prefixo ────────────────────────────────────────
    if content.startswith((f"<@!{bot.user.id}> ", f"<@{bot.user.id}> ")):
        return commands.when_mentioned(bot, message)

    # ── Menção de OUTRO bot do pool: este bot deve ignorar completamente ──────
    # Sem isso, todos os bots entram em disputa quando qualquer um é mencionado.
    if message.guild and content.startswith(("<@!", "<@")):
        for other in bot.pool.get_guild_bots(message.guild.id):
            if other.user.id == bot.user.id:
                continue
            if content.startswith((f"<@!{other.user.id}> ", f"<@{other.user.id}> ")):
                return "\x00"

    try:
        user_prefix = bot.pool.user_prefix_cache[message.author.id]
    except KeyError:
        user_data = await bot.get_global_data(message.author.id, db_name=DBModel.users)
        bot.pool.user_prefix_cache[message.author.id] = user_data["custom_prefix"]
        user_prefix = user_data["custom_prefix"]

    if user_prefix and content.startswith(user_prefix):
        return user_prefix

    if not message.guild:
        return commands.when_mentioned_or(bot.default_prefix)(bot, message)

    try:
        guild_prefix = bot.pool.guild_prefix_cache[message.guild.id]
    except KeyError:
        data = await bot.get_global_data(message.guild.id, db_name=DBModel.guilds)
        guild_prefix = data.get("prefix") or ""
        bot.pool.guild_prefix_cache[message.guild.id] = guild_prefix

    if not guild_prefix:
        guild_prefix = bot.config.get("DEFAULT_PREFIX") or "!!"

    return guild_prefix


class BaseDB:

    def __init__(self, cache_maxsize: int = 1000, cache_ttl=300):
        self.cache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl)

    def get_default(self, collection: str, db_name: Union[DBModel.guilds, DBModel.users]):
        if collection == "global":
            return deepcopy(global_db_models[db_name])
        return deepcopy(db_models[db_name])


class LocalMongoController:

    WINDOWS_ARCHIVE_TEMPLATE = "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-{version}.zip"
    MACOS_ARCHIVE_TEMPLATE = "https://fastdl.mongodb.org/osx/mongodb-macos-{arch}-{version}.tgz"
    LINUX_ARCHIVE_TEMPLATE = "https://fastdl.mongodb.org/linux/mongodb-linux-{arch}-{target}-{version}.tgz"

    def __init__(
        self,
        base_dir: str,
        version: str = "8.2.3",
        port: int = 27018,
        start_timeout: int = 45,
        download_url: str = "",
    ):
        self.base_dir = Path(base_dir).resolve()
        self.version = str(version).strip() or "8.2.3"
        self.port = int(port)
        self.start_timeout = int(start_timeout)
        self.download_url = (download_url or "").strip()
        self.mongo_root = self.base_dir / ".mongodb_portable"
        self.install_root = self.mongo_root / "install"
        self.download_root = self.mongo_root / "downloads"
        self.data_root = self.mongo_root / "data"
        self.log_root = self.mongo_root / "logs"
        self.log_path = self.log_root / "mongod.log"
        self.migration_backup_root = self.mongo_root / "tinymongo_backup"
        self.migration_marker = self.mongo_root / "tinymongo_migration_v1.json"
        self.process: subprocess.Popen | None = None

    @property
    def uri(self) -> str:
        return f"mongodb://127.0.0.1:{self.port}/"

    def ensure_server(self):
        if self._can_connect():
            return

        mongod_path = self._resolve_mongod_path()

        if not mongod_path:
            mongod_path = self._download_and_install_mongod()

        self._start_mongod(mongod_path)

    def _resolve_mongod_path(self) -> str | None:
        env_mongod = os.environ.get("LOCAL_MONGO_BINARY", "").strip()

        if env_mongod and os.path.isfile(env_mongod):
            return env_mongod

        local_binary = self._get_local_binary_path()

        if local_binary and os.path.isfile(local_binary):
            return local_binary

        system_binary = shutil.which("mongod")

        if system_binary:
            return system_binary

        return None

    def _get_local_binary_path(self) -> str | None:
        binary_name = "mongod.exe" if os.name == "nt" else "mongod"
        matches = sorted(self.install_root.glob(f"**/bin/{binary_name}"))

        if matches:
            return str(matches[0])

        return None

    def _download_and_install_mongod(self) -> str:
        url = self.download_url or self._resolve_download_url()
        archive_name = os.path.basename(urlparse(url).path)

        self.install_root.mkdir(parents=True, exist_ok=True)
        self.download_root.mkdir(parents=True, exist_ok=True)

        archive_path = self.download_root / archive_name
        temp_archive_path = archive_path.with_suffix(archive_path.suffix + ".part")

        if not archive_path.exists():
            with requests.get(url, stream=True, timeout=120) as response:
                response.raise_for_status()

                with temp_archive_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            file.write(chunk)

            temp_archive_path.replace(archive_path)

        mongod_path = Path(self._get_local_binary_path() or "")

        if not mongod_path.exists():
            self._extract_archive(archive_path)

            mongod_path = Path(self._get_local_binary_path() or "")

        if not mongod_path.exists():
            raise FileNotFoundError(f"Não foi possível localizar o mongod extraído em: {mongod_path}")

        return str(mongod_path)

    def _resolve_download_url(self) -> str:
        system_name = platform.system().lower()
        arch = self._normalize_architecture()

        if system_name == "windows":
            if arch != "x86_64":
                raise RuntimeError(f"Arquitetura do Windows não suportada para auto-download do MongoDB: {arch}")

            return self.WINDOWS_ARCHIVE_TEMPLATE.format(version=self.version)

        if system_name == "darwin":
            if arch not in {"x86_64", "arm64"}:
                raise RuntimeError(f"Arquitetura do macOS não suportada para auto-download do MongoDB: {arch}")

            return self.MACOS_ARCHIVE_TEMPLATE.format(arch=arch, version=self.version)

        if system_name == "linux":
            candidates = [
                self.LINUX_ARCHIVE_TEMPLATE.format(arch=arch, target=target, version=self.version)
                for target in self._get_linux_target_candidates(arch)
            ]

            for candidate in candidates:
                if self._url_exists(candidate):
                    return candidate

            raise RuntimeError(
                "Não foi possível encontrar um pacote oficial compatível do MongoDB para este Linux. "
                f"Arquitetura detectada: {arch}. Tente definir LOCAL_MONGO_DOWNLOAD_URL manualmente."
            )

        raise RuntimeError(
            "Sistema operacional sem suporte automático para download do MongoDB portable. "
            "Defina LOCAL_MONGO_BINARY ou LOCAL_MONGO_DOWNLOAD_URL."
        )

    def _extract_archive(self, archive_path: Path):
        suffixes = archive_path.suffixes

        if archive_path.suffix == ".zip":
            with zipfile.ZipFile(archive_path) as zip_file:
                zip_file.extractall(self.install_root)
            return

        if suffixes[-2:] == [".tar", ".gz"] or archive_path.suffix == ".tgz":
            with tarfile.open(archive_path, "r:gz") as tar_file:
                tar_file.extractall(self.install_root)
            return

        raise RuntimeError(f"Formato de arquivo não suportado para extração automática: {archive_path.name}")

    def _normalize_architecture(self) -> str:
        machine = platform.machine().lower()

        if machine in {"x86_64", "amd64"}:
            return "x86_64"

        if machine in {"aarch64", "arm64"}:
            return "arm64" if platform.system().lower() == "darwin" else "aarch64"

        raise RuntimeError(f"Arquitetura não suportada para MongoDB local portable: {machine}")

    def _get_linux_target_candidates(self, arch: str) -> list[str]:
        distro_info = self._read_linux_release_info()
        distro_id = distro_info.get("id", "")
        version_id = distro_info.get("version_id", "")

        candidates: list[str] = []

        if distro_id == "ubuntu":
            if version_id.startswith("24.04"):
                candidates.append("ubuntu2404")
            if version_id.startswith("22.04"):
                candidates.append("ubuntu2204")
            if version_id.startswith("20.04"):
                candidates.append("ubuntu2004")
            candidates.extend(["ubuntu2404", "ubuntu2204", "ubuntu2004"])

        elif distro_id == "debian":
            if version_id.startswith("12"):
                candidates.append("debian12")
            if version_id.startswith("11"):
                candidates.append("debian11")
            candidates.extend(["debian12", "debian11"])

        elif distro_id in {"amzn", "amazon"}:
            candidates.append("amazon2023")

        elif distro_id in {"rhel", "centos", "rocky", "almalinux", "ol"}:
            if arch == "aarch64":
                candidates.extend(["rhel93", "rhel8"])
            else:
                candidates.extend(["rhel93", "rhel8", "rhel70"])

        elif distro_id in {"sles", "opensuse-leap", "opensuse", "suse"} and arch == "x86_64":
            candidates.append("suse15")

        if arch == "x86_64":
            candidates.extend(["ubuntu2204", "debian12", "rhel93", "amazon2023", "ubuntu2004"])
        else:
            candidates.extend(["ubuntu2204", "ubuntu2404", "rhel93", "amazon2023", "rhel8"])

        deduped_candidates = []

        for candidate in candidates:
            if candidate not in deduped_candidates:
                deduped_candidates.append(candidate)

        return deduped_candidates

    def _read_linux_release_info(self) -> dict[str, str]:
        release_file = Path("/etc/os-release")

        if not release_file.exists():
            return {}

        release_info = {}

        try:
            for line in release_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "=" not in line:
                    continue

                key, value = line.split("=", 1)
                release_info[key.strip().lower()] = value.strip().strip('"')
        except OSError:
            return {}

        return release_info

    def _url_exists(self, url: str) -> bool:
        try:
            response = requests.head(url, allow_redirects=True, timeout=20)
            return response.ok
        except requests.RequestException:
            return False

    def _start_mongod(self, mongod_path: str):
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.log_root.mkdir(parents=True, exist_ok=True)

        args = [
            mongod_path,
            "--dbpath", str(self.data_root),
            "--bind_ip", "127.0.0.1",
            "--port", str(self.port),
            "--logpath", str(self.log_path),
            "--wiredTigerCacheSizeGB", "0.25",
        ]

        kwargs = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }

        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            kwargs["start_new_session"] = True

        self.process = subprocess.Popen(args, **kwargs)

    def wait_until_available(self):
        deadline = datetime.utcnow().timestamp() + self.start_timeout
        last_error = None

        while datetime.utcnow().timestamp() < deadline:
            try:
                if self._can_connect():
                    return
            except Exception as e:
                last_error = e

            if self.process and self.process.poll() is not None:
                break

            time.sleep(0.5)

        log_tail = ""

        if self.log_path.exists():
            try:
                log_tail = self.log_path.read_text(encoding="utf-8", errors="ignore")[-2000:]
            except Exception:
                pass

        raise RuntimeError(
            "Não foi possível iniciar o MongoDB local portable. "
            f"URI: {self.uri} | Último erro: {last_error!r}\n{log_tail}"
        )

    def _can_connect(self) -> bool:
        client = MongoClient(self.uri, serverSelectionTimeoutMS=1500, connectTimeoutMS=1500)

        try:
            client.admin.command("ping")
            return True
        except ServerSelectionTimeoutError:
            return False
        finally:
            client.close()


class LocalDatabase(BaseDB):

    def __init__(self, dir_="./local_database", cache_maxsize=1000, cache_ttl=300, config: dict | None = None):
        super().__init__(cache_maxsize=cache_maxsize, cache_ttl=cache_ttl)

        self.base_dir = os.path.abspath(dir_)
        os.makedirs(self.base_dir, exist_ok=True)
        self._config = config or {}
        self._controller = LocalMongoController(
            base_dir=self.base_dir,
            version=self._config.get("LOCAL_MONGO_VERSION", "8.2.3"),
            port=self._config.get("LOCAL_MONGO_PORT", 27018),
            start_timeout=self._config.get("LOCAL_MONGO_START_TIMEOUT", 45),
            download_url=self._config.get("LOCAL_MONGO_DOWNLOAD_URL", ""),
        )
        self._connect = AsyncIOMotorClient(
            self._controller.uri,
            connectTimeoutMS=int(self._config.get("MONGO_TIMEOUT", 30)) * 1000,
            serverSelectionTimeoutMS=5000,
        )
        self._bootstrap_lock = asyncio.Lock()
        self._ready = False

    async def ensure_ready(self):
        if self._ready:
            return

        async with self._bootstrap_lock:
            if self._ready:
                return

            await asyncio.to_thread(self._controller.ensure_server)
            await asyncio.to_thread(self._controller.wait_until_available)
            await self._migrate_legacy_tinymongo_data()
            self._ready = True

    async def _migrate_legacy_tinymongo_data(self):
        self._controller.mongo_root.mkdir(parents=True, exist_ok=True)

        if self._controller.migration_marker.exists():
            return

        migrated_files = []
        migration_timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_dir = self._controller.migration_backup_root / migration_timestamp
        archived_source_dir = backup_dir / "archived_source"
        snapshot_dir = backup_dir / "snapshot_before_migration"
        archived_source_dir.mkdir(parents=True, exist_ok=True)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        legacy_files = []

        for file_path in sorted(Path(self.base_dir).glob("*.json")):
            parsed_data = self._parse_legacy_collection_file(file_path)

            if not parsed_data:
                continue

            legacy_files.append((file_path, parsed_data))

        if not legacy_files:
            self._controller.migration_marker.write_text(
                json.dumps(
                    {
                        "migrated_at": datetime.utcnow().isoformat(),
                        "files": migrated_files,
                        "mongo_uri": self._controller.uri,
                        "backup_dir": str(backup_dir),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return

        for file_path, _ in legacy_files:
            shutil.copy2(str(file_path), str(snapshot_dir / file_path.name))

        for file_path, parsed_data in legacy_files:
            collection_name, collections = parsed_data

            for db_name, entries in collections.items():
                target_collection = self._connect[collection_name][db_name]

                for raw_doc in entries.values():
                    if not isinstance(raw_doc, dict):
                        continue

                    doc = deepcopy(raw_doc)
                    doc_id = str(doc.get("_id") or "")

                    if not doc_id:
                        continue

                    doc.pop("_id", None)
                    await target_collection.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)

            shutil.move(str(file_path), str(archived_source_dir / file_path.name))
            migrated_files.append(file_path.name)

        self._controller.migration_marker.write_text(
            json.dumps(
                {
                    "migrated_at": datetime.utcnow().isoformat(),
                    "files": migrated_files,
                    "mongo_uri": self._controller.uri,
                    "backup_dir": str(backup_dir),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _parse_legacy_collection_file(self, file_path: Path) -> tuple[str, dict] | None:
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(raw, dict) or not raw:
            return None

        valid_db_names = {DBModel.users, DBModel.guilds, DBModel.default}
        found_db_names = {key for key, value in raw.items() if key in valid_db_names and isinstance(value, dict)}

        if not found_db_names:
            return None

        return file_path.stem, {key: raw[key] for key in found_db_names}

    async def get_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users],
                       collection: str, default_model: dict = None):
        await self.ensure_ready()

        if not default_model:
            default_model = db_models

        id_ = str(id_)

        if (cached_result := self.cache.get(f"{collection}:{db_name}:{id_}")) is not None:
            return cached_result

        data = await self._connect[collection][db_name].find_one({"_id": id_})

        if not data:
            data = deepcopy(default_model[db_name])
            data["_id"] = str(id_)
            await self._connect[collection][db_name].insert_one(deepcopy(data))

        elif data["ver"] != default_model[db_name]["ver"]:
            data = update_values(deepcopy(default_model[db_name]), data)
            data["ver"] = default_model[db_name]["ver"]

            await self.update_data(id_, data, db_name=db_name, collection=collection)

        return data

    async def update_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users],
                          collection: str, default_model: dict = None):
        await self.ensure_ready()

        id_ = str(id_)
        data["_id"] = id_

        try:
            safe_data = deepcopy(data)
            safe_data.pop("_id", None)
            await self._connect[collection][db_name].update_one({'_id': id_}, {'$set': safe_data}, upsert=True)
        except Exception:
            traceback.print_exc()

        self.cache[f"{collection}:{db_name}:{id_}"] = data

        return data

    async def query_data(self, db_name: str, collection: str, filter: dict = None, limit=500) -> list:
        await self.ensure_ready()

        cursor = self._connect[collection][db_name].find(filter or {})

        if limit:
            cursor = cursor.limit(limit)

        return [d async for d in cursor]

    async def delete_data(self, id_, db_name: str, collection: str):
        await self.ensure_ready()

        try:
            await self._connect[collection][db_name].delete_one({'_id': str(id_)})
        except TypeError:
            return

        try:
            self.cache.pop(f"{collection}:{db_name}:{id_}")
        except KeyError:
            pass


class MongoDatabase(BaseDB):

    def __init__(self, token: str, timeout=30, cache_maxsize=1000, cache_ttl=300):
        super().__init__(cache_maxsize=cache_maxsize, cache_ttl=cache_ttl)

        fix_ssl = os.environ.get("MONGO_SSL_FIX") or os.environ.get("REPL_SLUG")

        if fix_ssl:
            parse_result = urlparse(token)
            parameters = parse_qs(parse_result.query)

            parameters.update(
                {
                    'ssl': ['true'],
                    'tlsAllowInvalidCertificates': ['true']
                }
            )

            token = urlunparse(parse_result._replace(query=urlencode(parameters, doseq=True)))

        self._connect = AsyncIOMotorClient(token.strip("<>"), connectTimeoutMS=timeout*1000)

    async def push_data(self, data, *, db_name: Union[DBModel.guilds, DBModel.users], collection: str):
        await self._connect[collection][db_name].insert_one(data)

    async def update_from_json(self):

        if not os.path.isdir("./local_dbs/backups"):
            os.makedirs("./local_dbs/backups")

        for f in os.listdir("./local_dbs"):

            if not f.endswith(".json"):
                continue

            with open(f'./local_dbs/{f}') as file:
                data = json.load(file)

            for db_name, db_data in data.items():

                if not db_data:
                    continue

                for id_, data in db_data.items():
                    await self.update_data(id_=id_, data=data, db_name=db_name, collection=f[:-5])

                try:
                    shutil.move(f"./local_dbs/{f}", f"./local_dbs/backups/{f}")
                except:
                    traceback.print_exc()

    async def get_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users],
                       collection: str, default_model: dict = None):

        if not default_model:
            default_model = db_models

        id_ = str(id_)

        if (cached_result := self.cache.get(f"{collection}:{db_name}:{id_}")) is not None:
            return cached_result

        data = await self._connect[collection][db_name].find_one({"_id": id_})

        if not data:
            return deepcopy(default_model[db_name])

        elif data["ver"] != default_model[db_name]["ver"]:
            data = update_values(deepcopy(default_model[db_name]), data)
            data["ver"] = default_model[db_name]["ver"]
            await self.update_data(id_, data, db_name=db_name, collection=collection)

        return data

    async def update_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users, str],
                          collection: str, default_model: dict = None):

        self.cache[f"{collection}:{db_name}:{id_}"] = data

        try:
            del data["_id"]
        except KeyError:
            pass

        await self._connect[collection][db_name].update_one({'_id': str(id_)}, {'$set': data}, upsert=True)
        return data

    async def query_data(self, db_name: str, collection: str, filter: dict = None, limit=100) -> list:
        return [d async for d in self._connect[collection][db_name].find(filter or {})]

    async def delete_data(self, id_, db_name: str, collection: str):
        try:
            self.cache.pop(f"{collection}:{db_name}:{id_}")
        except KeyError:
            pass
        return await self._connect[collection][db_name].delete_one({'_id': str(id_)})


def update_values(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update_values(d.get(k, {}), v)
        elif not isinstance(v, list):
            d[k] = v
    return d
