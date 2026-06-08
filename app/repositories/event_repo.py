from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.base_repository import BaseRepository
from app.models.event import Event


class EventRepository(BaseRepository[Event]):
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        super().__init__(model_class=Event, database=database)

    async def get_filtered(self, filters: dict[str, Any], skip: int, limit: int) -> list[dict[str, Any]]:
        cursor = self.collection.find(filters).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def increment_available_seats(self, event_id: UUID, amount: int) -> bool:
        """Atomically increment or decrement available seats using MongoDB $inc."""
        result = await self.collection.update_one(
            {
                "_id": event_id, 
                "available_seats": {"$gte": -amount} # Prevent available_seats from dropping below zero if amount is negative
            },
            {"$inc": {"available_seats": amount}}
        )
        return result.modified_count > 0
