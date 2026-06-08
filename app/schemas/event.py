from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.event import EventCategory, EventStatus


class EventBase(BaseModel):
    title: str
    description: str
    category: EventCategory
    venue_id: UUID
    start_datetime: datetime
    end_datetime: datetime
    poster_image: Optional[str] = None
    tags: list[str] = []
    base_price: Decimal
    total_seats: int


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[EventCategory] = None
    venue_id: Optional[UUID] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    poster_image: Optional[str] = None
    tags: Optional[list[str]] = None
    base_price: Optional[Decimal] = None
    total_seats: Optional[int] = None
    status: Optional[EventStatus] = None


class EventFilter(BaseModel):
    category: Optional[EventCategory] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    city: Optional[str] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    search: Optional[str] = None
    is_published: Optional[bool] = None


class EventRead(EventBase):
    id: UUID
    organizer_id: UUID
    is_published: bool
    available_seats: int
    status: EventStatus
    is_soldout: bool

    model_config = ConfigDict(from_attributes=True)
