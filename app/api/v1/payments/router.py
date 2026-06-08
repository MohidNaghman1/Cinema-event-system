from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_db, require_role
from app.models.payment import Payment
from app.models.user import Role, User
from app.repositories.booking_repo import BookingRepository
from app.repositories.payment_repo import PaymentRepository
from app.schemas.booking import PaginatedResponse
from app.schemas.payment import (
    PaymentConfirm,
    PaymentIntentCreate,
    PaymentIntentRead,
    PaymentRead,
    RefundRequest,
)
from app.services.stripe_service import StripeService

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_stripe_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> StripeService:
    return StripeService(PaymentRepository(db))


@router.post("/stripe/create-intent", response_model=PaymentIntentRead)
async def create_intent(
    data: PaymentIntentCreate,
    current_user: User = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PaymentIntentRead:
    booking_repo = BookingRepository(db)
    booking_dict = await booking_repo.get_by_id(data.booking_id)

    if not booking_dict or str(booking_dict["user_id"]) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Booking not found or unauthorized")

    amount = (
        booking_dict["total_amount"].to_decimal()
        if hasattr(booking_dict["total_amount"], "to_decimal")
        else booking_dict["total_amount"]
    )
    amount_cents = int(amount * Decimal("100"))

    metadata = {"booking_id": str(data.booking_id), "user_id": str(current_user.id)}

    intent = await stripe_service.create_payment_intent(
        booking_id=data.booking_id,
        user_id=current_user.id,
        amount_cents=amount_cents,
        currency=data.currency,
        metadata=metadata,
    )

    payment_repo = PaymentRepository(db)
    payment_dict = await payment_repo.get_by_gateway_id(intent.id)

    return PaymentIntentRead(
        client_secret=intent.client_secret,
        payment_id=payment_dict["_id"],
        amount=amount,
        currency=data.currency,
        status=payment_dict["status"],
    )


@router.post("/stripe/confirm", response_model=PaymentRead)
async def confirm_payment(
    data: PaymentConfirm,
    current_user: User = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PaymentRead:
    payment = await stripe_service.confirm_payment(data.payment_intent_id)

    if hasattr(payment.amount, "to_decimal"):
        payment.amount = payment.amount.to_decimal()
    if hasattr(payment.refund_amount, "to_decimal"):
        payment.refund_amount = payment.refund_amount.to_decimal()

    return PaymentRead.model_validate(payment)


@router.post(
    "/{id}/refund",
    response_model=PaymentRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def refund_payment(
    id: UUID,
    data: RefundRequest,
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PaymentRead:
    amount_cents = int(data.amount * Decimal("100"))
    await stripe_service.create_refund(id, amount_cents, data.reason)

    payment_repo = stripe_service.payment_repo
    payment_dict = await payment_repo.get_by_id(id)

    payment = Payment(**payment_dict)

    if hasattr(payment.amount, "to_decimal"):
        payment.amount = payment.amount.to_decimal()
    if hasattr(payment.refund_amount, "to_decimal"):
        payment.refund_amount = payment.refund_amount.to_decimal()

    return PaymentRead.model_validate(payment)


@router.get("/history", response_model=PaginatedResponse[PaymentRead])
async def get_payment_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    stripe_service: StripeService = Depends(get_stripe_service),
) -> PaginatedResponse[PaymentRead]:
    items_dict, total = await stripe_service.payment_repo.get_user_payment_history(
        current_user.id, skip, limit
    )

    for item in items_dict:
        if "amount" in item and hasattr(item["amount"], "to_decimal"):
            item["amount"] = item["amount"].to_decimal()
        if "refund_amount" in item and hasattr(item["refund_amount"], "to_decimal"):
            item["refund_amount"] = item["refund_amount"].to_decimal()

    items = [PaymentRead.model_validate(Payment(**item)) for item in items_dict]

    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)
