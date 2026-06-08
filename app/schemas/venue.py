from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.venue import SeatMap


class VenueBase(BaseModel):
    name: str
    address: str
    city: str
    country: str
    capacity: int
    amenities: list[str] = []
    images: list[str] = []


class VenueCreate(VenueBase):
    seat_map: Optional[SeatMap] = None


class VenueUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    capacity: Optional[int] = None
    amenities: Optional[list[str]] = None
    images: Optional[list[str]] = None
    seat_map: Optional[SeatMap] = None


class VenueRead(VenueBase):
    id: UUID
    seat_map: Optional[SeatMap] = None

    model_config = ConfigDict(from_attributes=True)


class VenueList(VenueBase):
    id: UUID
    # Excludes seat_map for lighter list payload

    model_config = ConfigDict(from_attributes=True)
