# -*- coding: utf-8 -*-
from __future__ import annotations

import collections.abc
import json
import os
import shutil
import traceback
from copy import deepcopy
from datetime import datetime
from typing import TYPE_CHECKING, Union
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode

import disnake
from cachetools import TTLCache
from disnake.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from tinydb_serialization import Serializer, SerializationMiddleware
from tinymongo import TinyMongoClient
from tinymongo.serializers import DateTimeSerializer

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

    if str(message.content).startswith((f"<@!{bot.user.id}> ", f"<@{bot.user.id}> ")):
        return commands.when_mentioned(bot, message)

    try:
        user_prefix = bot.pool.user_prefix_cache[message.author.id]
    except KeyError:
        user_data = await bot.get_global_data(message.author.id, db_name=DBModel.users)
        bot.pool.user_prefix_cache[message.author.id] = user_data["custom_prefix"]
        user_prefix = user_data["custom_prefix"]

    if user_prefix and message.content.startswith(user_prefix):
        return user_prefix

    if not message.guild:
        return commands.when_mentioned_or(bot.default_prefix)

    try:
        guild_prefix = bot.pool.guild_prefix_cache[message.guild.id]
    except KeyError:
        data = await bot.get_global_data(message.guild.id, db_name=DBModel.guilds)
        guild_prefix = data.get("prefix")

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


class DatetimeSerializer(Serializer):
    OBJ_CLASS = datetime

    def __init__(self, format='%Y-%m-%dT%H:%M:%S', *args, **kwargs):
        super(DatetimeSerializer, self).__init__(*args, **kwargs)
        self._format = format

    def encode(self, obj):
        return obj.strftime(self._format)

    def decode(self, s):
        return datetime.strptime(s, self._format)

class CustomTinyMongoClient(TinyMongoClient):

    @property
    def _storage(self):
        serialization = SerializationMiddleware()
        serialization.register_serializer(DateTimeSerializer(), 'TinyDate')
        return serialization


class LocalDatabase(BaseDB):

    def __init__(self, dir_="./local_database", cache_maxsize=1000, cache_ttl=300):
        super().__init__(cache_maxsize=cache_maxsize, cache_ttl=cache_ttl)

        if not os.path.isdir(dir_):
            os.makedirs(dir_)

        self._connect = CustomTinyMongoClient(dir_)

    async def get_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users],
                       collection: str, default_model: dict = None):

        if not default_model:
            default_model = db_models

        id_ = str(id_)

        if (cached_result := self.cache.get(f"{collection}:{db_name}:{id_}")) is not None:
            return cached_result

        data = self._connect[collection][db_name].find_one({"_id": id_})

        if not data:
            data = deepcopy(default_model[db_name])
            data["_id"] = str(id_)
            self._connect[collection][db_name].insert_one(data)

        elif data["ver"] != default_model[db_name]["ver"]:
            data = update_values(deepcopy(default_model[db_name]), data)
            data["ver"] = default_model[db_name]["ver"]

            await self.update_data(id_, data, db_name=db_name, collection=collection)

        return data

    async def update_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users],
                          collection: str, default_model: dict = None):

        id_ = str(id_)
        data["_id"] = id_

        try:
            if not self._connect[collection][db_name].update_one({'_id': id_}, {'$set': data}).raw_result:
                self._connect[collection][db_name].insert_one(data)
        except:
            traceback.print_exc()

        self.cache[f"{collection}:{db_name}:{id_}"] = data

        return data

    async def query_data(self, db_name: str, collection: str, filter: dict = None, limit=500) -> list:
        return self._connect[collection][db_name].find(filter or {})

    async def delete_data(self, id_, db_name: str, collection: str):
        try:
            self._connect[collection][db_name].delete_one({'_id': str(id_)})
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
