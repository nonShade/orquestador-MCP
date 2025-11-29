# db/mongo.py
import motor.motor_asyncio
import asyncio
from os import getenv
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
_db = None


async def get_db():
    global _client, _db
    if _client is None:
        mongo_uri = getenv("MONGO_URI", "mongodb://localhost:27017")
        db_name = getenv("DB_NAME", "ufro_master")

        _client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
        _db = _client[db_name]

        try:
            await _client.admin.command('ping')
            logger.info(f"Connected to MongoDB at {mongo_uri}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    return _db


async def close_db():
    global _client
    if _client:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed")


async def check_connection():
    """Health check for MongoDB connection"""
    try:
        db = await get_db()
        await db.command('ping')
        return True
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return False
