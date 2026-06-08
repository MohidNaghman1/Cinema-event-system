from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.dependencies import get_current_user, get_db
from app.models.booking import Booking, BookingStatus
from app.models.user import Role, User
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.venue_repo import VenueRepository
from app.schemas.booking import BookingCreateRequest, BookingRead, PaginatedResponse
from app.services.booking_service import BookingService
from app.services.seat_service import SeatService
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/api/v1/bookings", tags=["Bookings"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_booking_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> BookingService:
    booking_repo = BookingRepository(db)
    event_repo = EventRepository(db)
    venue_repo = VenueRepository(db)
    seat_service = SeatService(event_repo)
    ticket_service = TicketService()
    return BookingService(
        booking_repo, event_repo, venue_repo, seat_service, ticket_service
    )


async def get_booking_and_verify_ownership(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> Booking:
    """Dependency that fetches a booking and asserts ownership or admin access."""
    booking_repo = BookingRepository(db)
    booking_dict = await booking_repo.get_by_id(id)
    if not booking_dict:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking = Booking(**booking_dict)

    if current_user.role not in (Role.ADMIN, Role.SUPER_ADMIN):
        if str(booking.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this resource",
            )

    return booking


@router.post("", response_model=BookingRead)
async def create_booking(
    data: BookingCreateRequest,
    current_user: User = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingRead:
    booking = await booking_service.create_booking(
        current_user, data.event_id, data.seat_ids, data.hold_token
    )
    
    # Motor returns Decimal128, convert to Decimal for Pydantic
    if hasattr(booking.total_amount, "to_decimal"):
        booking.total_amount = booking.total_amount.to_decimal()
        
    return BookingRead.model_validate(booking)


@router.get("", response_model=PaginatedResponse[BookingRead])
async def list_user_bookings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status_filter: Optional[BookingStatus] = None,
    current_user: User = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> PaginatedResponse[BookingRead]:
    return await booking_service.get_user_booking_history(
        current_user.id, skip, limit, status_filter
    )


@router.get("/{id}", response_model=BookingRead)
async def get_booking(
    booking: Booking = Depends(get_booking_and_verify_ownership),
) -> BookingRead:
    if hasattr(booking.total_amount, "to_decimal"):
        booking.total_amount = booking.total_amount.to_decimal()
    return BookingRead.model_validate(booking)


class CancelRequest(BaseModel):
    reason: str


@router.delete("/{id}", response_model=BookingRead)
async def cancel_booking(
    data: CancelRequest,
    booking: Booking = Depends(get_booking_and_verify_ownership),
    current_user: User = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
) -> BookingRead:
    cancelled_booking = await booking_service.cancel_booking(
        booking.id, current_user, data.reason
    )
    
    if hasattr(cancelled_booking.total_amount, "to_decimal"):
        cancelled_booking.total_amount = cancelled_booking.total_amount.to_decimal()
        
    return BookingRead.model_validate(cancelled_booking)
