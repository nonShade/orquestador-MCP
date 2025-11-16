# db/ensure_indexes.py
import asyncio
from db.mongo import get_db


async def main():
    db = await get_db()
    await db.access_logs.create_index([("ts", -1)])
    await db.access_logs.create_index([("user.type", 1), ("ts", -1)])
    await db.access_logs.create_index([("route", 1), ("ts", -1)])
    await db.access_logs.create_index([("decision", 1), ("ts", -1)])
    await db.service_logs.create_index([("service_name", 1), ("ts", -1)])
    # TTL opcional si guardas image_hash_ts
    # await db.access_logs.create_index("input.image_hash_ts", expireAfterSeconds=604800)

if __name__ == "__main__":
    asyncio.run(main())
