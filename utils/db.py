from __future__ import annotations
import asyncio
import collections.abc
import json
import os
import disnake
from disnake.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Literal, TYPE_CHECKING
if TYPE_CHECKING:
    from .client import BotCore


db_models = {
      "guilds": {
        "ver": 1.4,
        "prefix": "",
        "player_controller": {
            "channel": None,
            "message_id": None,
            "skin": None
        },
        "check_other_bots_in_vc": False,
        "djroles": []
    },
    "users": {
        "ver": 1.0,
        "fav_links": {},
    }
}


async def guild_prefix(bot: BotCore, message: disnake.Message):

    if not message.guild:
        prefix = bot.default_prefix

    else:

        data = await bot.db.get_data(message.guild.id, db_name="guilds")

        prefix = data.get("prefix") or bot.default_prefix

    return commands.when_mentioned_or(*(prefix, ))(bot, message)


class BaseDB:

    def __init__(self, bot: BotCore):
        self.bot = bot
        self.db_models = dict(db_models)
        self.db_models["prefix"] = bot.default_prefix
        self.data = {
            'guilds': {},
            'users': {}
        }


class LocalDatabase(BaseDB):

    def __init__(self, bot: BotCore, rename_db: bool = False):
        super().__init__(bot)

        self.file_update = 0
        self.data_update = 0

        if not os.path.isdir("./local_dbs"):
            os.makedirs("local_dbs")

        # Medida temporária para evitar perca de dados do método antigo durante a migração para a nova versão...
        if rename_db:
            os.rename("./database.json", f"./local_dbs/{bot.user.id}.json")

        if not os.path.isfile(f'./local_dbs/{bot.user.id}.json'):
            with open(f'./local_dbs/{bot.user.id}.json', 'w') as f:
                json.dump(self.data, f)

        else:
            with open(f'./local_dbs/{bot.user.id}.json') as f:
                self.data = json.load(f)

        self.json_task = self.bot.loop.create_task(self.write_json_task())

    async def write_json_task(self):

        while True:

            if self.file_update != self.data_update:

                with open(f'./local_dbs/{self.bot.user.id}.json', 'w') as f:
                    f.write(json.dumps(self.data))

                self.file_update += 1

            await asyncio.sleep(3)

    async def get_data(self, id_: int, *, db_name: Literal['users', 'guilds']):

        id_ = str(id_)

        try:
            data = self.data[db_name][id_]
        except KeyError:
            return dict(self.db_models[db_name])

        if data["ver"] < self.db_models[db_name]["ver"]:

            data = update_values(dict(self.db_models[db_name]), data)
            data["ver"] = self.db_models[db_name]["ver"]

            await self.update_data(id_, data, db_name=db_name)

        return data


    async def update_data(self, id_: int, data: dict, *, db_name: Literal['users', 'guilds']):

        id_ = str(id_)

        self.data[db_name][id_] = data

        self.data_update += 1


class MongoDatabase(BaseDB):

    def __init__(self, bot: BotCore, token: str, name: str):
        super().__init__(bot)
        self._connect = AsyncIOMotorClient(token, connectTimeoutMS=30000)
        self._database = self._connect[name]
        self.name = name
        print(f"{bot.user} - MongoDB conectado.")

    async def push_data(self, data, db_name: Literal['users', 'guilds']):

        db = self._database[db_name]
        await db.insert_one(data)

    async def update_from_json(self):

        with open(f"./local_dbs/{self.bot.user.id}.json") as f:
            json_data = json.load(f)

        for db_name, db_data in json_data.items():

            if not db_data:
                continue

            for id_, data in db_data.items():

                if data == self.db_models["guilds"]:
                    continue

                await self.update_data(id_=id_, data=data, db_name=db_name)

    async def get_data(self, id_: int, *, db_name: Literal['users', 'guilds']):

        id_ = str(id_)

        try:
            return self.data[db_name][id_]

        except KeyError:

            data = await self._database[db_name].find_one({"_id": id_})

            if not data:
                return dict(self.db_models[db_name])

            elif data["ver"] < self.db_models[db_name]["ver"]:
                data = update_values(dict(self.db_models[db_name]), data)
                data["ver"] = self.db_models[db_name]["ver"]

                await self.update_data(id_, data, db_name=db_name)

            self.data[db_name][id_] = data

            return data


    async def update_data(self, id_, data: dict, *, db_name: Literal['users', 'guilds']):

        db = self._database[db_name]

        id_ = str(id_)

        d = await db.update_one({'_id': id_}, {'$set': data}, upsert=True)
        self.data[db_name][id_] = data
        return d


def update_values(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update_values(d.get(k, {}), v)
        elif not isinstance(v, list):
            d[k] = v
    return d