import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.models.booking import HoldStatus, SeatHold
from app.repositories.event_repo import EventRepository

class SeatUnavailableError(Exception):
    pass

_seat_locks: dict[str, asyncio.Lock] = {}
_held_seats: dict[str, dict] = {}

class SeatService:
    def __init__(self, event_repo: EventRepository) -> None:
        self.event_repo = event_repo

    async def hold_seats(self, event_id: UUID, seat_ids: list[str], user_id: UUID, ttl: int = 600) -> UUID:
        acquired_locks = []
        user_id_str = str(user_id)
        event_id_str = str(event_id)
        hold_token = uuid4()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl)
        
        try:
            for seat_id in seat_ids:
                lock_key = f"{event_id_str}:{seat_id}"
                
                if lock_key not in _seat_locks:
                    _seat_locks[lock_key] = asyncio.Lock()
                lock = _seat_locks[lock_key]
                
                await lock.acquire()
                acquired_locks.append(lock_key)
                
                if lock_key in _held_seats:
                    held_info = _held_seats[lock_key]
                    if held_info["expires_at"] > now:
                        raise SeatUnavailableError(f"Seat {seat_id} is already reserved or held.")
                
                _held_seats[lock_key] = {
                    "held_by": user_id_str,
                    "hold_token": str(hold_token),
                    "expires_at": expires_at
                }
        except SeatUnavailableError:
            for key in acquired_locks:
                _held_seats.pop(key, None)
                _seat_locks[key].release()
            raise

        success = await self.event_repo.increment_available_seats(event_id, -len(seat_ids))
        if not success:
            for key in acquired_locks:
                _held_seats.pop(key, None)
                _seat_locks[key].release()
            raise SeatUnavailableError("Not enough available seats for this event.")
            
        for key in acquired_locks:
            _seat_locks[key].release()

        hold = SeatHold(
            id=hold_token,
            event_id=event_id,
            user_id=user_id,
            seat_ids=seat_ids,
            expires_at=expires_at
        )
        await hold.insert()
        
        return hold_token

    async def confirm_seats(self, hold_token: UUID) -> None:
        hold = await SeatHold.get(hold_token)
        if not hold:
            raise HTTPException(status_code=404, detail="Hold not found")
            
        if hold.status != HoldStatus.HELD:
            raise HTTPException(status_code=400, detail=f"Hold cannot be confirmed (current status: {hold.status})")
            
        hold.status = HoldStatus.CONFIRMED
        await hold.save()
        
        hold_token_str = str(hold_token)
        event_id_str = str(hold.event_id)
        for seat_id in hold.seat_ids:
            key = f"{event_id_str}:{seat_id}"
            if key in _seat_locks:
                async with _seat_locks[key]:
                    if key in _held_seats and _held_seats[key].get("hold_token") == hold_token_str:
                        del _held_seats[key]

    async def release_seats(self, hold_token: UUID) -> None:
        hold = await SeatHold.get(hold_token)
        if not hold:
            raise HTTPException(status_code=404, detail="Hold not found")
            
        if hold.status != HoldStatus.HELD:
            raise HTTPException(status_code=400, detail="Only HELD reservations can be released manually")
            
        hold.status = HoldStatus.CANCELLED
        await hold.save()
        
        await self.event_repo.increment_available_seats(hold.event_id, len(hold.seat_ids))
        
        hold_token_str = str(hold_token)
        event_id_str = str(hold.event_id)
        for seat_id in hold.seat_ids:
            key = f"{event_id_str}:{seat_id}"
            if key in _seat_locks:
                async with _seat_locks[key]:
                    if key in _held_seats and _held_seats[key].get("hold_token") == hold_token_str:
                        del _held_seats[key]
