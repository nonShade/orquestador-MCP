# db/mongo.py
import motor.motor_asyncio
from os import getenv

_client = None


async def get_db():
    global _client
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(getenv("MONGO_URI"))
    return _client[getenv("DB_NAME", "ufro_master")]
