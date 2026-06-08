import os
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from app.models.booking import Booking
from app.models.user import Role, User
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.user_repo import UserRepository
from app.repositories.venue_repo import VenueRepository
from app.utils.pdf import generate_ticket_pdf
from app.utils.qr_code import generate_qr

# Ensure tickets directory exists
TICKETS_DIR = Path(__file__).parent.parent.parent / "storage" / "tickets"
os.makedirs(TICKETS_DIR, exist_ok=True)


class TicketService:
    def __init__(
        self,
        booking_repo: BookingRepository,
        event_repo: EventRepository,
        venue_repo: VenueRepository,
        user_repo: UserRepository,
    ) -> None:
        self.booking_repo = booking_repo
        self.event_repo = event_repo
        self.venue_repo = venue_repo
        self.user_repo = user_repo

    async def generate_ticket(self, booking: Booking) -> str:
        """Generates and stores the PDF, returns file path."""
        event_dict = await self.event_repo.get_by_id(booking.event_id)
        venue_dict = await self.venue_repo.get_by_id(booking.venue_id)
        user_dict = await self.user_repo.get_by_id(booking.user_id)

        from app.models.event import Event
        from app.models.venue import Venue

        event = Event(**event_dict)
        venue = Venue(**venue_dict)
        user = User(**user_dict)

        qr_bytes = generate_qr(
            str(booking.id), str(event.id), booking.seat_ids, str(user.id)
        )
        pdf_bytes = generate_ticket_pdf(booking, event, venue, user, qr_bytes)

        file_path = TICKETS_DIR / f"{booking.id}.pdf"
        with open(file_path, "wb") as f:
            f.write(pdf_bytes)

        return str(file_path)

    async def get_ticket(self, booking_id: UUID, user: User) -> bytes:
        """Fetches PDF bytes from storage, enforces ownership constraints."""
        booking_dict = await self.booking_repo.get_by_id(booking_id)
        if not booking_dict:
            raise HTTPException(status_code=404, detail="Booking not found")

        booking = Booking(**booking_dict)

        if user.role not in (Role.ADMIN, Role.SUPER_ADMIN):
            if str(booking.user_id) != str(user.id):
                raise HTTPException(
                    status_code=403, detail="Not authorized to access this ticket"
                )

        file_path = TICKETS_DIR / f"{booking.id}.pdf"
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Ticket file not found")

        with open(file_path, "rb") as f:
            return f.read()

    async def get_qr_code(self, booking_id: UUID, user: User) -> bytes:
        """Returns the isolated QR PNG representing the ticket for mobile presentation."""
        booking_dict = await self.booking_repo.get_by_id(booking_id)
        if not booking_dict:
            raise HTTPException(status_code=404, detail="Booking not found")

        booking = Booking(**booking_dict)

        if user.role not in (Role.ADMIN, Role.SUPER_ADMIN):
            if str(booking.user_id) != str(user.id):
                raise HTTPException(
                    status_code=403, detail="Not authorized to access this ticket"
                )

        return generate_qr(
            str(booking.id), str(booking.event_id), booking.seat_ids, str(booking.user_id)
        )
