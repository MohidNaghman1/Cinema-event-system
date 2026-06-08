from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from app.dependencies import get_current_user, get_db
from app.models.booking import SeatHold
from app.models.user import User
from app.repositories.event_repo import EventRepository
from app.services.seat_service import SeatService, SeatUnavailableError

router = APIRouter(prefix="/api/v1/bookings/hold", tags=["Bookings"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_seat_service(db: AsyncIOMotorDatabase = Depends(get_db)) -> SeatService:
    event_repo = EventRepository(db)
    return SeatService(event_repo)


class SeatHoldRequest(BaseModel):
    event_id: UUID
    seat_ids: list[str]


class SeatHoldResponse(BaseModel):
    hold_token: UUID
    message: str


@router.post("", response_model=SeatHoldResponse)
async def hold_seats(
    data: SeatHoldRequest,
    current_user: User = Depends(get_current_user),
    seat_service: SeatService = Depends(get_seat_service),
) -> Any:
    """Hold selected seats via Redis distributed lock."""
    if not data.seat_ids:
        raise HTTPException(status_code=400, detail="No seats requested")

    try:
        hold_token = await seat_service.hold_seats(
            event_id=data.event_id,
            seat_ids=data.seat_ids,
            user_id=current_user.id,
            ttl=600,
        )
    except SeatUnavailableError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {"hold_token": hold_token, "message": "Seats held successfully"}


@router.delete("/{hold_token}", status_code=status.HTTP_204_NO_CONTENT)
async def release_hold(
    hold_token: UUID,
    current_user: User = Depends(get_current_user),
    seat_service: SeatService = Depends(get_seat_service),
) -> None:
    """Release hold manually."""
    hold = await SeatHold.get(hold_token)
    if not hold or hold.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Hold not found")

    await seat_service.release_seats(hold_token)
