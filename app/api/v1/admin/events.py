from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.dependencies import get_db, require_role
from app.models.event import Event, EventStatus
from app.models.user import Role
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.venue_repo import VenueRepository
from app.schemas.booking import BookingRead, PaginatedResponse
from app.schemas.event import EventRead
from app.services.event_service import EventService
from app.tasks.cleanup_tasks import bulk_cancel_event_bookings

router = APIRouter(prefix="/api/v1/admin/events", tags=["Admin — Events"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_event_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> EventService:
    return EventService(EventRepository(db), VenueRepository(db))


def get_booking_repo(db: AsyncIOMotorDatabase = Depends(get_db)) -> BookingRepository:
    return BookingRepository(db)


@router.get(
    "",
    response_model=PaginatedResponse[EventRead],
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def list_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[EventStatus] = None,
    event_service: EventService = Depends(get_event_service),
) -> PaginatedResponse[EventRead]:
    filters: dict[str, Any] = {"is_deleted": False}
    if search:
        filters["title"] = {"$regex": search, "$options": "i"}
    if category:
        filters["category"] = category
    if status:
        filters["status"] = status.value

    cursor = event_service.event_repo.collection.find(filters).sort("start_datetime", -1)
    total = await event_service.event_repo.collection.count_documents(filters)
    items_dict = await cursor.skip(skip).limit(limit).to_list(length=limit)

    items = []
    for item in items_dict:
        if hasattr(item["base_price"], "to_decimal"):
            item["base_price"] = item["base_price"].to_decimal()
        items.append(EventRead.model_validate(Event(**item)))

    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.patch(
    "/{id}/publish",
    response_model=EventRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def publish_event(
    id: UUID, event_service: EventService = Depends(get_event_service)
) -> EventRead:
    event_dict = await event_service.event_repo.get_by_id(id)
    if not event_dict:
        raise HTTPException(status_code=404, detail="Event not found")

    await event_service.event_repo.update(id, {"is_published": True})
    event_dict["is_published"] = True

    if hasattr(event_dict["base_price"], "to_decimal"):
        event_dict["base_price"] = event_dict["base_price"].to_decimal()

    return EventRead.model_validate(Event(**event_dict))


@router.patch(
    "/{id}/unpublish",
    response_model=EventRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def unpublish_event(
    id: UUID, event_service: EventService = Depends(get_event_service)
) -> EventRead:
    event_dict = await event_service.event_repo.get_by_id(id)
    if not event_dict:
        raise HTTPException(status_code=404, detail="Event not found")

    await event_service.event_repo.update(id, {"is_published": False})
    event_dict["is_published"] = False

    if hasattr(event_dict["base_price"], "to_decimal"):
        event_dict["base_price"] = event_dict["base_price"].to_decimal()

    return EventRead.model_validate(Event(**event_dict))


@router.patch(
    "/{id}/cancel",
    response_model=EventRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def cancel_event(
    id: UUID,
    background_tasks: BackgroundTasks,
    event_service: EventService = Depends(get_event_service),
) -> EventRead:
    event_dict = await event_service.event_repo.get_by_id(id)
    if not event_dict:
        raise HTTPException(status_code=404, detail="Event not found")

    await event_service.event_repo.update(
        id, {"status": EventStatus.CANCELLED.value, "is_published": False}
    )
    event_dict["status"] = EventStatus.CANCELLED.value
    event_dict["is_published"] = False

    background_tasks.add_task(bulk_cancel_event_bookings, id)

    if hasattr(event_dict["base_price"], "to_decimal"):
        event_dict["base_price"] = event_dict["base_price"].to_decimal()

    return EventRead.model_validate(Event(**event_dict))


@router.get(
    "/{id}/bookings",
    response_model=PaginatedResponse[BookingRead],
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_event_bookings(
    id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    booking_repo: BookingRepository = Depends(get_booking_repo),
) -> PaginatedResponse[BookingRead]:
    filters = {"event_id": id}
    cursor = booking_repo.collection.find(filters).sort("booked_at", -1)
    total = await booking_repo.collection.count_documents(filters)
    items_dict = await cursor.skip(skip).limit(limit).to_list(length=limit)

    from app.models.booking import Booking

    items = []
    for item in items_dict:
        if hasattr(item["total_amount"], "to_decimal"):
            item["total_amount"] = item["total_amount"].to_decimal()
        items.append(BookingRead.model_validate(Booking(**item)))

    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


class EventStats(BaseModel):
    total_bookings: int
    revenue: float
    available_seats: int
    occupancy_rate: float


@router.get(
    "/{id}/stats",
    response_model=EventStats,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_event_stats(
    id: UUID,
    event_service: EventService = Depends(get_event_service),
    booking_repo: BookingRepository = Depends(get_booking_repo),
) -> EventStats:
    event_dict = await event_service.event_repo.get_by_id(id)
    if not event_dict:
        raise HTTPException(status_code=404, detail="Event not found")

    from app.models.booking import BookingStatus

    filters = {"event_id": id, "status": BookingStatus.CONFIRMED.value}
    bookings = await booking_repo.collection.find(filters).to_list(length=None)

    total_bookings = len(bookings)
    revenue = sum(
        float(b["total_amount"].to_decimal() if hasattr(b["total_amount"], "to_decimal") else b["total_amount"])
        for b in bookings
    )
    available_seats = event_dict["available_seats"]
    total_seats = event_dict["total_seats"]

    occupancy_rate = 0.0
    if total_seats > 0:
        occupancy_rate = round(((total_seats - available_seats) / total_seats) * 100, 2)

    return EventStats(
        total_bookings=total_bookings,
        revenue=revenue,
        available_seats=available_seats,
        occupancy_rate=occupancy_rate,
    )
