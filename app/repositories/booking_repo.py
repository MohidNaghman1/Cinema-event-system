from typing import Any, Optional
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.base_repository import BaseRepository
from app.models.booking import Booking


class BookingRepository(BaseRepository[Booking]):
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        super().__init__(model_class=Booking, database=database)

    async def get_user_bookings(
        self, user_id: UUID, skip: int, limit: int, status: Optional[str] = None
    ) -> tuple[list[dict[str, Any]], int]:
        filters: dict[str, Any] = {"user_id": user_id, "is_deleted": False}
        if status:
            filters["status"] = status

        cursor = self.collection.find(filters).sort("booked_at", -1)
        total = await self.collection.count_documents(filters)
        items = await cursor.skip(skip).limit(limit).to_list(length=limit)

        return items, total
