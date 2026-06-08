from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class PaymentGateway(str, Enum):
    STRIPE = "STRIPE"


class PaymentStatus(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class Payment(Document):
    id: UUID = Field(default_factory=uuid4)
    booking_id: UUID
    user_id: UUID
    gateway: PaymentGateway = PaymentGateway.STRIPE
    gateway_payment_id: Optional[str] = None
    gateway_charge_id: Optional[str] = None
    amount: Decimal = Field(decimal_places=2)
    currency: str = "USD"
    status: PaymentStatus = PaymentStatus.CREATED
    refund_amount: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_deleted: bool = False

    class Settings:
        name = "payments"
        use_state_management = True
        indexes = [
            IndexModel("booking_id", unique=True),
            "user_id",
            "status",
            "gateway_payment_id",
        ]
