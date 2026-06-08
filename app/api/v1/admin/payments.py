from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.dependencies import get_db, require_role
from app.models.payment import Payment, PaymentStatus
from app.models.user import Role
from app.repositories.booking_repo import BookingRepository
from app.repositories.payment_repo import PaymentRepository
from app.schemas.booking import BookingRead, PaginatedResponse
from app.schemas.payment import PaymentRead, RefundRequest
from app.services.stripe_service import StripeService

router = APIRouter(prefix="/api/v1/admin/payments", tags=["Admin — Payments"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_stripe_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> StripeService:
    return StripeService(PaymentRepository(db))


@router.get(
    "",
    response_model=PaginatedResponse[PaymentRead],
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def list_payments(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[UUID] = None,
    gateway: Optional[str] = None,
    status: Optional[PaymentStatus] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PaginatedResponse[PaymentRead]:
    payment_repo = PaymentRepository(db)
    filters: dict[str, Any] = {}
    if user_id:
        filters["user_id"] = user_id
    if gateway:
        filters["gateway"] = gateway
    if status:
        filters["status"] = status.value

    if from_date or to_date:
        date_filter: dict[str, Any] = {}
        if from_date:
            date_filter["$gte"] = from_date
        if to_date:
            date_filter["$lte"] = to_date
        filters["created_at"] = date_filter

    cursor = payment_repo.collection.find(filters).sort("created_at", -1)
    total = await payment_repo.collection.count_documents(filters)
    items_dict = await cursor.skip(skip).limit(limit).to_list(length=limit)

    items = []
    for item in items_dict:
        if hasattr(item["amount"], "to_decimal"):
            item["amount"] = item["amount"].to_decimal()
        if hasattr(item["refund_amount"], "to_decimal"):
            item["refund_amount"] = item["refund_amount"].to_decimal()
        items.append(PaymentRead.model_validate(Payment(**item)))

    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


class PaymentStats(BaseModel):
    total_revenue: float
    total_refunded: float
    net_revenue: float
    payment_count: int


@router.get(
    "/stats",
    response_model=PaymentStats,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_payment_stats(
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PaymentStats:
    payment_repo = PaymentRepository(db)

    filters: dict[str, Any] = {"status": PaymentStatus.SUCCEEDED.value}
    if from_date or to_date:
        date_filter: dict[str, Any] = {}
        if from_date:
            date_filter["$gte"] = from_date
        if to_date:
            date_filter["$lte"] = to_date
        filters["created_at"] = date_filter

    pipeline = [
        {"$match": filters},
        {
            "$group": {
                "_id": None,
                "total_revenue": {"$sum": "$amount"},
                "total_refunded": {"$sum": "$refund_amount"},
                "payment_count": {"$sum": 1},
            }
        },
    ]

    cursor = payment_repo.collection.aggregate(pipeline)
    result = await cursor.to_list(length=1)

    if not result:
        return PaymentStats(
            total_revenue=0.0, total_refunded=0.0, net_revenue=0.0, payment_count=0
        )

    total_rev = float(
        result[0]["total_revenue"].to_decimal()
        if hasattr(result[0]["total_revenue"], "to_decimal")
        else result[0]["total_revenue"]
    )
    total_ref = float(
        result[0]["total_refunded"].to_decimal()
        if hasattr(result[0]["total_refunded"], "to_decimal")
        else result[0]["total_refunded"]
    )

    return PaymentStats(
        total_revenue=total_rev,
        total_refunded=total_ref,
        net_revenue=total_rev - total_ref,
        payment_count=result[0]["payment_count"],
    )


class PaymentDetailRead(PaymentRead):
    booking: Optional[BookingRead] = None


@router.get(
    "/{id}",
    response_model=PaymentDetailRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_payment_detail(
    id: UUID, db: AsyncIOMotorDatabase = Depends(get_db)
) -> PaymentDetailRead:
    payment_repo = PaymentRepository(db)
    booking_repo = BookingRepository(db)

    payment_dict = await payment_repo.get_by_id(id)
    if not payment_dict:
        raise HTTPException(status_code=404, detail="Payment not found")

    booking_dict = await booking_repo.get_by_id(payment_dict["booking_id"])
    booking_info = None
    if booking_dict:
        from app.models.booking import Booking

        if hasattr(booking_dict["total_amount"], "to_decimal"):
            booking_dict["total_amount"] = booking_dict["total_amount"].to_decimal()
        booking_info = BookingRead.model_validate(Booking(**booking_dict))

    if hasattr(payment_dict["amount"], "to_decimal"):
        payment_dict["amount"] = payment_dict["amount"].to_decimal()
    if hasattr(payment_dict["refund_amount"], "to_decimal"):
        payment_dict["refund_amount"] = payment_dict["refund_amount"].to_decimal()

    payment = Payment(**payment_dict)
    return PaymentDetailRead(**payment.model_dump(), booking=booking_info)


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

    if hasattr(payment_dict["amount"], "to_decimal"):
        payment_dict["amount"] = payment_dict["amount"].to_decimal()
    if hasattr(payment_dict["refund_amount"], "to_decimal"):
        payment_dict["refund_amount"] = payment_dict["refund_amount"].to_decimal()

    payment = Payment(**payment_dict)
    return PaymentRead.model_validate(payment)
