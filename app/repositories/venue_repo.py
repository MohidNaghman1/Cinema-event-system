from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.base_repository import BaseRepository
from app.models.venue import Venue


class VenueRepository(BaseRepository[Venue]):
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        super().__init__(model_class=Venue, database=database)

    async def get_paginated(
        self, skip: int, limit: int, city: Optional[str] = None, min_capacity: Optional[int] = None
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"is_deleted": False}
        if city:
            filters["city"] = {"$regex": city, "$options": "i"}
        if min_capacity is not None:
            filters["capacity"] = {"$gte": min_capacity}

        return await self.list(skip=skip, limit=limit, filters=filters)
