from __future__ import annotations
import asyncio
import collections.abc
import json
import os
import shutil
import traceback
import disnake
from disnake.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .client import BotCore


class DBModel:
    guilds = "guilds"
    users = "users"


db_models = {
    DBModel.guilds: {
        "ver": 1.6,
        "prefix": "",
        "player_controller": {
            "channel": None,
            "message_id": None,
            "skin": None,
            "fav_links": {}
        },
        "check_other_bots_in_vc": False,
        "enable_prefixed_commands": True,
        "djroles": []
    },
    DBModel.users: {
        "ver": 1.0,
        "fav_links": {},
    }
}

global_db_models = {
    DBModel.users: {
        "ver": 1.0,
        "fav_links": {}
    },
    DBModel.guilds: {
        "ver": 1.0,
        "prefix": ""
    }
}


async def guild_prefix(bot: BotCore, message: disnake.Message):

    if not message.guild:
        return commands.when_mentioned_or(bot.default_prefix)

    if str(message.content).startswith((f"<@!{bot.user.id}> ", f"<@{bot.user.id}> ")):
        return commands.when_mentioned(bot, message)

    if bot.config["GLOBAL_PREFIX"]:
        data = await bot.get_global_data(message.guild.id, db_name=DBModel.guilds)
        prefix = data.get("prefix") or bot.config.get("DEFAULT_PREFIX") or "!!"
    else:
        data = await bot.get_data(message.guild.id, db_name=DBModel.guilds)
        prefix = data.get("prefix") or bot.default_prefix

    return prefix
    #return commands.when_mentioned_or(*(prefix, ))(bot, message)


class BaseDB:

    def get_default(self, collection: str, db_name: Union[DBModel.guilds, DBModel.users]):
        if collection == "global":
            return dict(global_db_models[db_name])
        return dict(db_models[db_name])

    def start_task(self, loop):
        pass


class LocalDatabase(BaseDB):

    def __init__(self):
        super().__init__()
        self.data = {}
        self.to_update = set()

        if not os.path.isdir("./local_dbs"):
            os.makedirs("local_dbs")

        else:
            for f in os.listdir(f"./local_dbs"):

                if not f.endswith(".json"):
                    continue

                with open(f'./local_dbs/{f}') as file:
                    self.data[f[:-5]] = json.load(file)

    def start_task(self, loop):
        if not loop:
            loop = asyncio.get_event_loop()
        loop.create_task(self.write_json_task())

    async def write_json_task(self):

        while True:

            if self.to_update:

                for i in list(self.to_update):
                    with open(f'./local_dbs/{i}.json', 'w') as f:
                        f.write(json.dumps(self.data[i]))

                    self.to_update.remove(i)

            await asyncio.sleep(3)

    async def get_data(self, id_: int, *, db_name: Union[DBModel.guilds, DBModel.users],
                       collection: str, default_model: dict = None):

        id_ = str(id_)

        if not default_model:
            default_model = db_models

        try:
            data = self.data[collection][db_name][id_]
        except KeyError:
            return dict(default_model[db_name])

        if data["ver"] < default_model[db_name]["ver"]:
            data = update_values(dict(default_model[db_name]), data)
            data["ver"] = default_model[db_name]["ver"]

            await self.update_data(id_, data, db_name=db_name, collection=collection)

        return data

    async def update_data(self, id_: int, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users],
                          collection: str, default_model: dict = None):

        if not default_model:
            default_model = db_models

        id_ = str(id_)

        try:
            self.data[collection][db_name][id_] = data
        except KeyError:
            self.data[collection] = dict(default_model)
            self.data[collection][db_name][id_] = data

        self.to_update.add(collection)


class MongoDatabase(BaseDB):

    def __init__(self, token: str):
        super().__init__()
        self._connect = AsyncIOMotorClient(token, connectTimeoutMS=30000)

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

        data = await self._connect[collection][db_name].find_one({"_id": id_})

        if not data:
            return dict(default_model[db_name])

        elif data["ver"] < default_model[db_name]["ver"]:
            data = update_values(dict(default_model[db_name]), data)
            data["ver"] = default_model[db_name]["ver"]

            await self.update_data(id_, data, db_name=db_name, collection=collection)

        return data

    async def update_data(self, id_, data: dict, *, db_name: Union[DBModel.guilds, DBModel.users],
                          collection: str, default_model: dict = None):
        return await self._connect[collection][db_name].update_one({'_id': str(id_)}, {'$set': data}, upsert=True)


def update_values(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update_values(d.get(k, {}), v)
        elif not isinstance(v, list):
            d[k] = v
    return d
