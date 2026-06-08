from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.dependencies import get_current_user, get_db, require_role
from app.models.booking import Booking, BookingStatus
from app.models.user import Role, User
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.venue_repo import VenueRepository
from app.schemas.booking import BookingRead, PaginatedResponse
from app.services.booking_service import BookingService
from app.services.seat_service import SeatService
from app.services.stripe_service import StripeService
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/api/v1/admin/bookings", tags=["Admin — Bookings"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_booking_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> BookingService:
    booking_repo = BookingRepository(db)
    event_repo = EventRepository(db)
    venue_repo = VenueRepository(db)
    user_repo = UserRepository(db)
    seat_service = SeatService(event_repo)
    ticket_service = TicketService(booking_repo, event_repo, venue_repo, user_repo)
    return BookingService(
        booking_repo, event_repo, venue_repo, seat_service, ticket_service
    )


@router.get(
    "",
    response_model=PaginatedResponse[BookingRead],
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def list_bookings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[UUID] = None,
    event_id: Optional[UUID] = None,
    status: Optional[BookingStatus] = None,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> PaginatedResponse[BookingRead]:
    booking_repo = BookingRepository(db)
    filters: dict[str, Any] = {}
    if user_id:
        filters["user_id"] = user_id
    if event_id:
        filters["event_id"] = event_id
    if status:
        filters["status"] = status.value

    cursor = booking_repo.collection.find(filters).sort("booked_at", -1)
    total = await booking_repo.collection.count_documents(filters)
    items_dict = await cursor.skip(skip).limit(limit).to_list(length=limit)

    items = []
    for item in items_dict:
        if hasattr(item["total_amount"], "to_decimal"):
            item["total_amount"] = item["total_amount"].to_decimal()
        items.append(BookingRead.model_validate(Booking(**item)))

    return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)


@router.patch(
    "/{id}/confirm",
    response_model=BookingRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def force_confirm_booking(
    id: UUID,
    background_tasks: BackgroundTasks,
    booking_service: BookingService = Depends(get_booking_service),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> BookingRead:
    booking_dict = await booking_service.booking_repo.get_by_id(id)
    if not booking_dict:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking = Booking(**booking_dict)
    if booking.status != BookingStatus.PENDING_PAYMENT:
        raise HTTPException(
            status_code=400, detail=f"Cannot confirm booking in {booking.status} state"
        )

    user_repo = UserRepository(db)
    user_dict = await user_repo.get_by_id(booking.user_id)
    user_email = user_dict["email"] if user_dict else "unknown@example.com"

    booking = await booking_service.confirm_booking(
        id, None, user_email, background_tasks
    )

    if hasattr(booking.total_amount, "to_decimal"):
        booking.total_amount = booking.total_amount.to_decimal()

    return BookingRead.model_validate(booking)


class ForceCancelRequest(BaseModel):
    reason: str


@router.patch(
    "/{id}/cancel",
    response_model=BookingRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def force_cancel_booking(
    id: UUID,
    data: ForceCancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> BookingRead:
    booking_repo = BookingRepository(db)
    booking_dict = await booking_repo.get_by_id(id)
    if not booking_dict:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking_dict["status"] in (
        BookingStatus.CANCELLED.value,
        BookingStatus.REFUNDED.value,
    ):
        raise HTTPException(status_code=400, detail="Already cancelled")

    booking = Booking(**booking_dict)

    event_repo = EventRepository(db)
    await event_repo.increment_available_seats(booking.event_id, len(booking.seat_ids))

    await booking_repo.update(
        id,
        {
            "status": BookingStatus.CANCELLED.value,
            "cancellation_reason": data.reason,
            "cancelled_at": datetime.now(timezone.utc),
        },
    )

    payment_repo = PaymentRepository(db)
    stripe_service = StripeService(payment_repo)
    payment_dict = await payment_repo.get_by_booking_id(id)

    if payment_dict and payment_dict["status"] in ("SUCCEEDED", "PARTIALLY_REFUNDED"):
        try:
            amount = payment_dict["amount"].to_decimal() if hasattr(payment_dict["amount"], "to_decimal") else payment_dict["amount"]
            amount_cents = int(amount * 100)
            await stripe_service.create_refund(
                payment_dict["_id"], amount_cents, "requested_by_customer"
            )
        except Exception as e:
            print(f"[ERROR] Failed to refund booking {id}: {e}")

    updated_dict = await booking_repo.get_by_id(id)
    if hasattr(updated_dict["total_amount"], "to_decimal"):
        updated_dict["total_amount"] = updated_dict["total_amount"].to_decimal()

    return BookingRead.model_validate(Booking(**updated_dict))


class BookingDetailRead(BookingRead):
    payment_info: Optional[dict] = None


@router.get(
    "/{id}",
    response_model=BookingDetailRead,
    dependencies=[Depends(require_role(Role.ADMIN, Role.SUPER_ADMIN))],
)
async def get_booking_detail(
    id: UUID, db: AsyncIOMotorDatabase = Depends(get_db)
) -> BookingDetailRead:
    booking_repo = BookingRepository(db)
    payment_repo = PaymentRepository(db)

    booking_dict = await booking_repo.get_by_id(id)
    if not booking_dict:
        raise HTTPException(status_code=404, detail="Booking not found")

    payment_dict = await payment_repo.get_by_booking_id(id)
    payment_info = None
    if payment_dict:
        if hasattr(payment_dict["amount"], "to_decimal"):
            payment_dict["amount"] = float(payment_dict["amount"].to_decimal())
        if hasattr(payment_dict["refund_amount"], "to_decimal"):
            payment_dict["refund_amount"] = float(payment_dict["refund_amount"].to_decimal())
        payment_dict["id"] = str(payment_dict["_id"])
        del payment_dict["_id"]
        payment_info = payment_dict

    if hasattr(booking_dict["total_amount"], "to_decimal"):
        booking_dict["total_amount"] = booking_dict["total_amount"].to_decimal()

    booking = Booking(**booking_dict)

    return BookingDetailRead(**booking.model_dump(), payment_info=payment_info)
