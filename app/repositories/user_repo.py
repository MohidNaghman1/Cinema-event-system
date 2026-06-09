from typing import Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.base_repository import BaseRepository
from app.models.user import User, Role


class UserRepository(BaseRepository[User]):
    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        super().__init__(model_class=User, database=database)

    async def get_by_email(self, email: str) -> User | None:
        return await User.find_one(User.email == email)

    async def get_by_oauth(self, provider: str, provider_user_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one({
            "oauth_accounts": {
                "$elemMatch": {
                    "provider": provider,
                    "provider_user_id": provider_user_id
                }
            }
        })

    async def get_paginated_admin(
        self, skip: int, limit: int, search: Optional[str] = None, role_filter: Optional[str] = None, is_active: Optional[bool] = None, sort_by: str = "created_at"
    ) -> tuple[list[dict[str, Any]], int]:
        filters: dict[str, Any] = {"is_deleted": {"$ne": True}}
        
        if search:
            filters["$or"] = [
                {"email": {"$regex": search, "$options": "i"}},
                {"full_name": {"$regex": search, "$options": "i"}}
            ]
            
        if role_filter:
            filters["role"] = role_filter

        if is_active is not None:
            filters["is_active"] = is_active
            
        sort_direction = -1 if sort_by == "created_at" else 1

        cursor = self.collection.find(filters).sort(sort_by, sort_direction)
        total = await self.collection.count_documents(filters)
        items = await cursor.skip(skip).limit(limit).to_list(length=limit)
        return items, total
