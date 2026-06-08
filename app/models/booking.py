from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class HoldStatus(str, Enum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SeatHold(Document):
    id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    user_id: UUID
    seat_ids: list[str]
    status: HoldStatus = HoldStatus.HELD
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "seat_holds"
        use_state_management = True


class BookingStatus(str, Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class Booking(Document):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    event_id: UUID
    venue_id: UUID
    seat_ids: list[str]
    hold_token: UUID
    total_amount: Decimal = Field(decimal_places=2)
    currency: str = "USD"
    status: BookingStatus = BookingStatus.PENDING_PAYMENT
    payment_id: Optional[UUID] = None
    booked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    is_deleted: bool = False

    class Settings:
        name = "bookings"
        use_state_management = True
        indexes = [
            IndexModel([("user_id", ASCENDING), ("status", ASCENDING)]),
            "event_id",
            "booked_at",
        ]
