from datetime import datetime
from decimal import Decimal
from typing import Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingStatus


class BookingCreateRequest(BaseModel):
    event_id: UUID
    seat_ids: list[str]
    hold_token: UUID


class BookingRead(BaseModel):
    id: UUID
    user_id: UUID
    event_id: UUID
    venue_id: UUID
    seat_ids: list[str]
    hold_token: UUID
    total_amount: Decimal
    currency: str
    status: BookingStatus
    payment_id: Optional[UUID] = None
    booked_at: datetime
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    skip: int
    limit: int
