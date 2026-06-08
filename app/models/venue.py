from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from beanie import Document
from pydantic import BaseModel, Field


class SeatCategory(str, Enum):
    STANDARD = "STANDARD"
    VIP = "VIP"
    PREMIUM = "PREMIUM"


class Seat(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    row: int
    column: int
    category: SeatCategory = SeatCategory.STANDARD
    price_multiplier: float = 1.0
    is_available: bool = True


class SeatMap(BaseModel):
    rows: int
    columns: int
    seats: list[Seat] = Field(default_factory=list)


class Venue(Document):
    id: UUID = Field(default_factory=uuid4)
    name: str
    address: str
    city: str
    country: str
    capacity: int
    amenities: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    seat_map: Optional[SeatMap] = None
    is_deleted: bool = False

    class Settings:
        name = "venues"
        use_state_management = True
