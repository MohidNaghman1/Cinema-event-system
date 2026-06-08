from typing import Any, Optional
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.base_repository import BaseRepository
from app.models.payment import Payment


class PaymentRepository(BaseRepository[Payment]):
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        super().__init__(model_class=Payment, database=database)

    async def get_by_booking_id(self, booking_id: UUID) -> Optional[dict[str, Any]]:
        return await self.collection.find_one(
            {"booking_id": booking_id, "is_deleted": False}
        )

    async def get_by_gateway_id(self, gateway_payment_id: str) -> Optional[dict[str, Any]]:
        return await self.collection.find_one(
            {"gateway_payment_id": gateway_payment_id, "is_deleted": False}
        )

    async def get_user_payment_history(
        self, user_id: UUID, skip: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]:
        filters: dict[str, Any] = {"user_id": user_id, "is_deleted": False}

        cursor = self.collection.find(filters).sort("created_at", -1)
        total = await self.collection.count_documents(filters)
        items = await cursor.skip(skip).limit(limit).to_list(length=limit)

        return items, total
