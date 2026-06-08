from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.payment import PaymentStatus


class PaymentIntentCreate(BaseModel):
    booking_id: UUID
    currency: str = "USD"


class PaymentIntentRead(BaseModel):
    client_secret: str
    payment_id: UUID
    amount: Decimal
    currency: str
    status: PaymentStatus


class PaymentConfirm(BaseModel):
    payment_intent_id: str


class RefundRequest(BaseModel):
    amount: Decimal
    reason: str


class PaymentRead(BaseModel):
    id: UUID
    booking_id: UUID
    user_id: UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    refund_amount: Decimal

    model_config = ConfigDict(from_attributes=True)
