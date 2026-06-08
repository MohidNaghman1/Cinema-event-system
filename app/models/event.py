from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from beanie import Document
from pydantic import BaseModel, Field, computed_field


class EventCategory(str, Enum):
    CINEMA = "CINEMA"
    CONCERT = "CONCERT"
    THEATRE = "THEATRE"
    SPORTS = "SPORTS"


class EventStatus(str, Enum):
    UPCOMING = "UPCOMING"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Event(Document):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    category: EventCategory
    venue_id: UUID
    organizer_id: UUID
    start_datetime: datetime
    end_datetime: datetime
    poster_image: Optional[str] = None
    is_published: bool = False
    tags: list[str] = Field(default_factory=list)
    base_price: Decimal = Field(decimal_places=2)
    total_seats: int
    available_seats: int
    status: EventStatus = EventStatus.UPCOMING
    is_deleted: bool = False

    @computed_field
    @property
    def is_soldout(self) -> bool:
        return self.available_seats <= 0

    class Settings:
        name = "events"
        use_state_management = True
        indexes = [
            "start_datetime",
            "category",
            "is_published",
            "venue_id",
        ]
