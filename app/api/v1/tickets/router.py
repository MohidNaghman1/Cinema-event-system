import io
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.user_repo import UserRepository
from app.repositories.venue_repo import VenueRepository
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_ticket_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> TicketService:
    return TicketService(
        booking_repo=BookingRepository(db),
        event_repo=EventRepository(db),
        venue_repo=VenueRepository(db),
        user_repo=UserRepository(db),
    )


@router.get("/{booking_id}")
async def download_ticket_pdf(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> StreamingResponse:
    pdf_bytes = await ticket_service.get_ticket(booking_id, current_user)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=ticket_{booking_id}.pdf"},
    )


@router.get("/{booking_id}/qr")
async def get_ticket_qr(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    ticket_service: TicketService = Depends(get_ticket_service),
) -> StreamingResponse:
    qr_bytes = await ticket_service.get_qr_code(booking_id, current_user)

    return StreamingResponse(io.BytesIO(qr_bytes), media_type="image/png")
