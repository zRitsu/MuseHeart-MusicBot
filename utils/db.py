import collections.abc
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Literal

guild_model = {
    "ver": 1.0,
    "player_controller": {
        "channel": None,
        "message_id": None
    },
    "djroles": []
}

class Database:

    def __init__(self, token, name):
        self._connect = AsyncIOMotorClient(token, connectTimeoutMS=30000)
        self._database = self._connect[name]
        self.name = name
        self.cache = {
            'guilds': {},
            'users': {}
        }

    async def push_data(self, data, db_name: Literal['users', 'guilds']):

        db = self._database[db_name]
        await db.insert_one(data)

    async def get_data(self, id_: int, *, db_name: Literal['users', 'guilds']):

        db = self._database[db_name]

        id_ = str(id_)

        data = self.cache[db_name].get(id_)

        if not data:
            data = await db.find_one({"_id": id_})

            if not data:
                data = dict(guild_model)
                data['_id'] = id_
                await self.push_data(data, db_name)

            self.cache[db_name][id_] = data

        return data


    async def update_data(self, id_, data: dict, *, db_name: Literal['users', 'guilds']):

        db = self._database[db_name]

        id_ = str(id_)

        d = await db.update_one({'_id': id_}, {'$set': data}, upsert=False)
        self.cache[db_name][id_] = data
        return d


def update_values(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update_values(d.get(k, {}), v)
        elif not isinstance(v, list):
            d[k] = v
    return d
