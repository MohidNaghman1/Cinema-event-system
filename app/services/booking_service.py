from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from bson import Decimal128
from fastapi import BackgroundTasks, HTTPException

from app.models.booking import Booking, BookingStatus, HoldStatus, SeatHold
from app.models.event import Event
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.venue_repo import VenueRepository
from app.schemas.booking import BookingRead, PaginatedResponse
from app.services.seat_service import SeatService
from app.services.ticket_service import TicketService


async def send_booking_confirmation_email(user_email: str, booking_id: UUID) -> None:
    print(f"[BACKGROUND] Sending confirmation email to {user_email} for booking {booking_id}")


class BookingService:
    def __init__(
        self,
        booking_repo: BookingRepository,
        event_repo: EventRepository,
        venue_repo: VenueRepository,
        seat_service: SeatService,
        ticket_service: TicketService,
    ) -> None:
        self.booking_repo = booking_repo
        self.event_repo = event_repo
        self.venue_repo = venue_repo
        self.seat_service = seat_service
        self.ticket_service = ticket_service

    async def create_booking(
        self, user: User, event_id: UUID, seat_ids: list[str], hold_token: UUID
    ) -> Booking:
        hold = await SeatHold.get(hold_token)
        if not hold or hold.user_id != user.id:
            raise HTTPException(status_code=400, detail="Invalid hold token or unauthorized")
        if hold.status != HoldStatus.HELD:
            raise HTTPException(status_code=400, detail="Hold is no longer valid or has expired")

        if set(hold.seat_ids) != set(seat_ids):
            raise HTTPException(status_code=400, detail="Seat IDs do not match the reserved hold")

        event_dict = await self.event_repo.get_by_id(event_id)
        if not event_dict:
            raise HTTPException(status_code=404, detail="Event not found")
        event = Event(**event_dict)

        venue_dict = await self.venue_repo.get_by_id(event.venue_id)
        if not venue_dict:
            raise HTTPException(status_code=404, detail="Venue not found")

        seat_map = venue_dict.get("seat_map")
        if not seat_map:
            raise HTTPException(status_code=400, detail="Venue has no seat map configuration")

        total_amount = Decimal("0.00")
        base_price = (
            event.base_price.to_decimal()
            if hasattr(event.base_price, "to_decimal")
            else event.base_price
        )

        seat_dict = {seat["id"]: seat for seat in seat_map["seats"]}
        for seat_id in seat_ids:
            if seat_id not in seat_dict:
                raise HTTPException(status_code=400, detail=f"Seat {seat_id} is invalid")
            multiplier = Decimal(str(seat_dict[seat_id].get("price_multiplier", 1.0)))
            total_amount += base_price * multiplier

        booking = Booking(
            user_id=user.id,
            event_id=event_id,
            venue_id=event.venue_id,
            seat_ids=seat_ids,
            hold_token=hold_token,
            total_amount=total_amount,
            status=BookingStatus.PENDING_PAYMENT,
        )
        await self.booking_repo.create(booking)
        return booking

    async def confirm_booking(
        self, booking_id: UUID, payment_id: UUID, user_email: str, background_tasks: BackgroundTasks
    ) -> Booking:
        booking_dict = await self.booking_repo.get_by_id(booking_id)
        if not booking_dict:
            raise HTTPException(status_code=404, detail="Booking not found")

        booking = Booking(**booking_dict)
        if booking.status != BookingStatus.PENDING_PAYMENT:
            raise HTTPException(
                status_code=400, detail=f"Booking is in {booking.status} state, cannot confirm"
            )

        # Confirm the hold in seat service
        try:
            await self.seat_service.confirm_seats(booking.hold_token)
        except HTTPException as e:
            raise HTTPException(status_code=400, detail=f"Failed to confirm seats: {e.detail}")

        # Update booking
        update_data = {
            "status": BookingStatus.CONFIRMED.value,
            "payment_id": payment_id,
        }
        await self.booking_repo.update(booking_id, update_data)
        booking.status = BookingStatus.CONFIRMED
        booking.payment_id = payment_id

        await self.ticket_service.generate_ticket(booking)
        background_tasks.add_task(send_booking_confirmation_email, user_email, booking_id)

        return booking

    async def cancel_booking(self, booking_id: UUID, user: User, reason: str) -> Booking:
        booking_dict = await self.booking_repo.get_by_id(booking_id)
        if not booking_dict:
            raise HTTPException(status_code=404, detail="Booking not found")

        booking = Booking(**booking_dict)

        if booking.status not in (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED):
            raise HTTPException(
                status_code=400, detail=f"Booking cannot be cancelled from {booking.status} state"
            )

        if booking.status == BookingStatus.CONFIRMED:
            if datetime.now(timezone.utc) - booking.booked_at > timedelta(hours=24):
                raise HTTPException(
                    status_code=400,
                    detail="Confirmed bookings can only be cancelled within 24 hours of booking",
                )

        new_status = BookingStatus.CANCELLED
        if booking.payment_id:
            # Payment refund logic mock
            new_status = BookingStatus.REFUNDED
            print(f"[BACKGROUND] Refund triggered for payment {booking.payment_id}")

        # Release seats
        try:
            await self.seat_service.release_seats(booking.hold_token)
        except Exception as e:
            print(f"Warning: Could not release seats automatically for booking {booking_id}: {e}")

        update_data = {
            "status": new_status.value,
            "cancelled_at": datetime.now(timezone.utc),
            "cancellation_reason": reason,
        }
        await self.booking_repo.update(booking_id, update_data)

        booking.status = new_status
        booking.cancelled_at = update_data["cancelled_at"]
        booking.cancellation_reason = reason
        return booking

    async def get_user_booking_history(
        self, user_id: UUID, skip: int, limit: int, status_filter: Optional[BookingStatus] = None
    ) -> PaginatedResponse[BookingRead]:
        items_dict, total = await self.booking_repo.get_user_bookings(
            user_id, skip, limit, status_filter.value if status_filter else None
        )

        for item in items_dict:
            if "total_amount" in item and hasattr(item["total_amount"], "to_decimal"):
                item["total_amount"] = item["total_amount"].to_decimal()

        items = [BookingRead.model_validate(Booking(**item)) for item in items_dict]

        return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)
