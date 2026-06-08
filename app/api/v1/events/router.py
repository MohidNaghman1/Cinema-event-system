from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_db, require_role
from app.models.event import Event, EventCategory
from app.models.user import Role, User
from app.repositories.event_repo import EventRepository
from app.repositories.venue_repo import VenueRepository
from app.schemas.event import EventCreate, EventFilter, EventRead, EventUpdate
from app.services.event_service import EventService

router = APIRouter(prefix="/api/v1/events", tags=["Events"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_event_repo(db: AsyncIOMotorDatabase = Depends(get_db)) -> EventRepository:
    return EventRepository(db)


def get_venue_repo(db: AsyncIOMotorDatabase = Depends(get_db)) -> VenueRepository:
    return VenueRepository(db)


def get_event_service(
    event_repo: EventRepository = Depends(get_event_repo),
    venue_repo: VenueRepository = Depends(get_venue_repo),
) -> EventService:
    return EventService(event_repo, venue_repo)


@router.get("", response_model=list[EventRead])
async def list_events(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[EventCategory] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    city: Optional[str] = None,
    min_price: Optional[Decimal] = None,
    max_price: Optional[Decimal] = None,
    search: Optional[str] = None,
    is_published: Optional[bool] = None,
    event_service: EventService = Depends(get_event_service),
) -> list[EventRead]:
    filters = EventFilter(
        category=category,
        date_from=date_from,
        date_to=date_to,
        city=city,
        min_price=min_price,
        max_price=max_price,
        search=search,
        is_published=is_published,
    )
    events = await event_service.get_events(filters, skip, limit)
    
    # Motor returns Decimal128, convert to Decimal for Pydantic
    for e in events:
        if "base_price" in e and hasattr(e["base_price"], "to_decimal"):
            e["base_price"] = e["base_price"].to_decimal()

    return [EventRead.model_validate(Event(**e)) for e in events]


@router.get("/{id}", response_model=EventRead)
async def get_event(
    id: UUID, event_repo: EventRepository = Depends(get_event_repo)
) -> EventRead:
    event = await event_repo.get_by_id(id)
    if not event or event.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Event not found")

    if "base_price" in event and hasattr(event["base_price"], "to_decimal"):
        event["base_price"] = event["base_price"].to_decimal()

    return EventRead.model_validate(Event(**event))


@router.post("", response_model=EventRead, dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))])
async def create_event(
    data: EventCreate,
    current_user: User = Depends(get_current_user),
    event_service: EventService = Depends(get_event_service),
) -> EventRead:
    event = await event_service.create_event(data, current_user)
    return EventRead.model_validate(event)


@router.put("/{id}", response_model=EventRead, dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))])
async def update_event(
    id: UUID,
    data: EventUpdate,
    event_service: EventService = Depends(get_event_service),
) -> EventRead:
    event_dict = await event_service.update_event(id, data)
    
    if "base_price" in event_dict and hasattr(event_dict["base_price"], "to_decimal"):
        event_dict["base_price"] = event_dict["base_price"].to_decimal()
        
    return EventRead.model_validate(Event(**event_dict))


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))])
async def delete_event(
    id: UUID, event_service: EventService = Depends(get_event_service)
) -> None:
    await event_service.delete_event(id)


@router.post("/{id}/publish", response_model=EventRead, dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))])
async def publish_event(
    id: UUID,
    background_tasks: BackgroundTasks,
    event_service: EventService = Depends(get_event_service),
) -> EventRead:
    event_dict = await event_service.publish_event(id, background_tasks)
    
    if "base_price" in event_dict and hasattr(event_dict["base_price"], "to_decimal"):
        event_dict["base_price"] = event_dict["base_price"].to_decimal()
        
    return EventRead.model_validate(Event(**event_dict))
