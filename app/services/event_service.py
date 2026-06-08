from typing import Any
from uuid import UUID

from bson import Decimal128
from fastapi import BackgroundTasks, HTTPException

from app.models.event import Event
from app.models.user import User
from app.repositories.event_repo import EventRepository
from app.repositories.venue_repo import VenueRepository
from app.schemas.event import EventCreate, EventFilter, EventUpdate


async def send_event_published_notification(event_id: UUID) -> None:
    print(f"[BACKGROUND] Notifying subscribers about event {event_id} being published")


class EventService:
    def __init__(self, event_repo: EventRepository, venue_repo: VenueRepository) -> None:
        self.event_repo = event_repo
        self.venue_repo = venue_repo

    async def create_event(self, data: EventCreate, organizer: User) -> Event:
        venue_dict = await self.venue_repo.get_by_id(data.venue_id)
        if not venue_dict or venue_dict.get("is_deleted"):
            raise HTTPException(status_code=400, detail="Invalid venue ID")

        event = Event(
            **data.model_dump(),
            organizer_id=organizer.id,
            available_seats=data.total_seats,
        )
        await self.event_repo.create(event)
        return event

    async def update_event(self, event_id: UUID, data: EventUpdate) -> dict[str, Any]:
        event_dict = await self.event_repo.get_by_id(event_id)
        if not event_dict or event_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="Event not found")

        update_data = data.model_dump(exclude_unset=True)
        if "venue_id" in update_data:
            venue_dict = await self.venue_repo.get_by_id(update_data["venue_id"])
            if not venue_dict or venue_dict.get("is_deleted"):
                raise HTTPException(status_code=400, detail="Invalid venue ID")

        if "total_seats" in update_data:
            diff = update_data["total_seats"] - event_dict["total_seats"]
            update_data["available_seats"] = event_dict["available_seats"] + diff

        if "base_price" in update_data:
            update_data["base_price"] = Decimal128(str(update_data["base_price"]))

        if update_data:
            await self.event_repo.update(event_id, update_data)
            event_dict.update(update_data)

        return event_dict

    async def delete_event(self, event_id: UUID) -> None:
        event_dict = await self.event_repo.get_by_id(event_id)
        if not event_dict or event_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="Event not found")

        await self.event_repo.update(event_id, {"is_deleted": True})

    async def publish_event(
        self, event_id: UUID, background_tasks: BackgroundTasks
    ) -> dict[str, Any]:
        event_dict = await self.event_repo.get_by_id(event_id)
        if not event_dict or event_dict.get("is_deleted"):
            raise HTTPException(status_code=404, detail="Event not found")

        if event_dict.get("is_published"):
            return event_dict

        await self.event_repo.update(event_id, {"is_published": True})
        event_dict["is_published"] = True

        background_tasks.add_task(send_event_published_notification, event_id)
        return event_dict

    async def get_events(
        self, filters: EventFilter, skip: int, limit: int
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"is_deleted": False}

        if filters.category:
            query["category"] = filters.category.value

        if filters.is_published is not None:
            query["is_published"] = filters.is_published

        if filters.date_from or filters.date_to:
            date_query: dict[str, Any] = {}
            if filters.date_from:
                date_query["$gte"] = filters.date_from
            if filters.date_to:
                date_query["$lte"] = filters.date_to
            query["start_datetime"] = date_query

        if filters.min_price is not None or filters.max_price is not None:
            price_query: dict[str, Any] = {}
            if filters.min_price is not None:
                price_query["$gte"] = Decimal128(str(filters.min_price))
            if filters.max_price is not None:
                price_query["$lte"] = Decimal128(str(filters.max_price))
            query["base_price"] = price_query

        if filters.search:
            query["$or"] = [
                {"title": {"$regex": filters.search, "$options": "i"}},
                {"tags": {"$regex": filters.search, "$options": "i"}},
            ]

        if filters.city:
            venues = await self.venue_repo.list(
                limit=1000,
                filters={"city": {"$regex": filters.city, "$options": "i"}, "is_deleted": False},
            )
            venue_ids = [v["_id"] for v in venues]
            if not venue_ids:
                return []
            query["venue_id"] = {"$in": venue_ids}

        return await self.event_repo.get_filtered(query, skip, limit)
