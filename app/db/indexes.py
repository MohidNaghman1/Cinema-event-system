from motor.motor_asyncio import AsyncIOMotorDatabase
import pymongo

async def create_all_indexes(db: AsyncIOMotorDatabase) -> None:
    # Users indexes
    await db["users"].create_index("email", unique=True)
    
    # Events indexes
    await db["events"].create_index("date")
    await db["events"].create_index("category")
    
    # Bookings indexes
    await db["bookings"].create_index("user_id")
    await db["bookings"].create_index("event_id")
