from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import get_settings

class MongoDB:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

db_client = MongoDB()

async def connect_to_mongo() -> None:
    settings = get_settings()
    db_client.client = AsyncIOMotorClient(
        settings.mongo_uri,
        minPoolSize=5,
        maxPoolSize=20,
        uuidRepresentation="standard",
    )
    db_client.db = db_client.client[settings.mongo_db_name]
    try:
        await db_client.db.command("ping")
    except Exception as e:
        raise RuntimeError("Could not connect to MongoDB") from e

async def close_mongo_connection() -> None:
    if db_client.client:
        db_client.client.close()

def get_database() -> AsyncIOMotorDatabase:
    if db_client.db is None:
        raise RuntimeError("Database not initialized")
    return db_client.db
