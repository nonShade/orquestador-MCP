# db/ensure_indexes.py
from db.mongo import get_db
import asyncio
import os
import sys
import logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Create all necessary indexes for the MongoDB collections"""
    try:
        db = await get_db()

        logger.info("Creating indexes for access_logs collection...")
        await db.access_logs.create_index([("ts", -1)])
        await db.access_logs.create_index([("user.type", 1), ("ts", -1)])
        await db.access_logs.create_index([("route", 1), ("ts", -1)])
        await db.access_logs.create_index([("decision", 1), ("ts", -1)])
        await db.access_logs.create_index([("request_id", 1)], unique=True)

        logger.info("Creating indexes for service_logs collection...")
        await db.service_logs.create_index([("service_name", 1), ("ts", -1)])
        await db.service_logs.create_index([("service_type", 1), ("ts", -1)])
        await db.service_logs.create_index([("status_code", 1), ("ts", -1)])
        await db.service_logs.create_index([("request_id", 1)])

        logger.info("Creating indexes for users collection...")
        await db.users.create_index([("user_id", 1)], unique=True)
        await db.users.create_index([("user_type", 1)])

        logger.info("Creating indexes for config collection...")
        await db.config.create_index([("name", 1)], unique=True)
        await db.config.create_index([("active", 1)])

        logger.info("Creating TTL index for image hashes...")
        await db.access_logs.create_index("input.image_hash_ts", expireAfterSeconds=604800)

        logger.info("All indexes created successfully!")

    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise

if __name__ == "__main__":
    # Load environment variables from .env file
    if os.path.exists(".env"):
        with open(".env") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value
    
    asyncio.run(main())
