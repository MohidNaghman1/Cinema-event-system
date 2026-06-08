from datetime import datetime, timedelta, timezone
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.models.booking import Booking, BookingStatus, HoldStatus, SeatHold
from app.models.payment import PaymentStatus
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.user_repo import UserRepository
from app.services.stripe_service import StripeService


async def cleanup_expired_holds() -> int:
    """Iterates _held_seats dict, removes entries where expires_at < datetime.utcnow(), increments available_seats in MongoDB."""
    from app.services.seat_service import _held_seats, _seat_locks
    
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]
    event_repo = EventRepository(db)
    
    now = datetime.now(timezone.utc)
    expired_keys = []
    
    # Safely find expired keys in dictionary
    for key, info in _held_seats.items():
        if info["expires_at"] < now:
            expired_keys.append(key)
            
    count = 0
    for key in expired_keys:
        if key in _seat_locks:
            async with _seat_locks[key]:
                # Re-verify inside lock to ensure no race conditions
                if key in _held_seats and _held_seats[key]["expires_at"] < now:
                    event_id_str = key.split(":")[0]
                    event_id = UUID(event_id_str)
                    
                    # Refund the seat inventory to MongoDB
                    await event_repo.increment_available_seats(event_id, 1)
                    
                    del _held_seats[key]
                    count += 1
    
    return count


async def bulk_cancel_event_bookings(event_id: "UUID") -> int:
    """Fetches all CONFIRMED bookings for event, cancels and refunds each, sends email."""
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    booking_repo = BookingRepository(db)
    payment_repo = PaymentRepository(db)
    stripe_service = StripeService(payment_repo)
    user_repo = UserRepository(db)

    cursor = booking_repo.collection.find(
        {"event_id": event_id, "status": BookingStatus.CONFIRMED.value}
    )

    count = 0
    async for b in cursor:
        booking = Booking(**b)

        payment_dict = await payment_repo.get_by_booking_id(booking.id)
        if payment_dict and payment_dict["status"] in (
            PaymentStatus.SUCCEEDED.value,
            PaymentStatus.PARTIALLY_REFUNDED.value,
        ):
            amount = payment_dict["amount"].to_decimal() if hasattr(payment_dict["amount"], "to_decimal") else payment_dict["amount"]
            amount_cents = int(amount * 100)
            try:
                await stripe_service.create_refund(
                    payment_dict["_id"], amount_cents, "requested_by_customer"
                )
            except Exception as e:
                print(f"[ERROR] Auto-refund failed for {booking.id}: {e}")

        await booking_repo.update(
            booking.id,
            {
                "status": BookingStatus.CANCELLED.value,
                "cancellation_reason": "Event Cancelled",
            },
        )

        user_dict = await user_repo.get_by_id(booking.user_id)
        if user_dict:
            print(
                f"[BACKGROUND] Email to {user_dict['email']}: Event Cancelled - "
                f"Your booking for event {event_id} has been cancelled and refunded."
            )

        count += 1

    return count


async def expire_pending_bookings() -> int:
    """Finds bookings in PENDING_PAYMENT older than 15min, cancels them and releases seats."""
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]
    
    booking_repo = BookingRepository(db)
    event_repo = EventRepository(db)
    
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(minutes=15)
    
    cursor = booking_repo.collection.find({
        "status": BookingStatus.PENDING_PAYMENT.value,
        "created_at": {"$lt": threshold}
    })
    
    count = 0
    async for b in cursor:
        await booking_repo.update(b["_id"], {
            "status": BookingStatus.CANCELLED.value,
            "cancellation_reason": "Payment timeout",
            "cancelled_at": now
        })
        await event_repo.increment_available_seats(b["event_id"], len(b["seat_ids"]))
        count += 1
        
    return count
