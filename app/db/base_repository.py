from typing import Generic, TypeVar, Any
from bson import ObjectId
from beanie import Document
from motor.motor_asyncio import AsyncIOMotorDatabase

T = TypeVar("T", bound=Document)

class BaseRepository(Generic[T]):
    def __init__(self, model_class: type[T], database: AsyncIOMotorDatabase) -> None:
        self.model_class = model_class
        collection_name = getattr(model_class.Settings, "name", model_class.__name__.lower()) if hasattr(model_class, "Settings") else model_class.__name__.lower()
        self.collection = database[collection_name]

    def _get_object_id(self, id: str | ObjectId) -> ObjectId:
        if isinstance(id, str):
            try:
                return ObjectId(id)
            except Exception:
                return id
        return id

    async def create(self, doc: T | dict[str, Any]) -> Any:
        if isinstance(doc, Document):
            await doc.insert()
            return doc.id
        else:
            result = await self.collection.insert_one(doc)
            return result.inserted_id

    async def get_by_id(self, id: str | ObjectId) -> dict[str, Any] | None:
        doc_id = self._get_object_id(id)
        return await self.collection.find_one({"_id": doc_id})

    async def update(self, id: str | ObjectId, data: dict[str, Any]) -> int:
        doc_id = self._get_object_id(id)
        result = await self.collection.update_one({"_id": doc_id}, {"$set": data})
        return result.modified_count

    async def delete(self, id: str | ObjectId) -> int:
        doc_id = self._get_object_id(id)
        result = await self.collection.delete_one({"_id": doc_id})
        return result.deleted_count

    async def list(self, skip: int = 0, limit: int = 100, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        cursor = self.collection.find(filters).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)
