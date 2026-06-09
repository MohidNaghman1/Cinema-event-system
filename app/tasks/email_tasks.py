from typing import Any
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.core.email import email_service
from app.models.booking import Booking, BookingStatus
from app.models.event import Event
from app.models.user import User
from app.models.venue import Venue
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.venue_repo import VenueRepository

settings = get_settings()


async def _get_db() -> Any:
    client = AsyncIOMotorClient(settings.mongo_uri)
    return client[settings.mongo_db_name]


async def send_booking_confirmation_email(booking_id: "UUID") -> None:
    db = await _get_db()
    booking_repo = BookingRepository(db)
    user_repo = UserRepository(db)
    event_repo = EventRepository(db)
    venue_repo = VenueRepository(db)

    booking_dict = await booking_repo.get_by_id(booking_id)
    if not booking_dict:
        return

    booking = Booking(**booking_dict)
    user_dict = await user_repo.get_by_id(booking.user_id)
    event_dict = await event_repo.get_by_id(booking.event_id)
    venue_dict = await venue_repo.get_by_id(booking.venue_id)

    if not all([user_dict, event_dict, venue_dict]):
        return

    user = User(**user_dict)
    event = Event(**event_dict)
    venue = Venue(**venue_dict)

    context = {"user": user, "event": event, "venue": venue, "booking": booking, "seats": booking.seat_ids}

    html_body = email_service.render_template("booking_confirmation.html", context)
    plain_text = f"Booking Confirmed for {event.title}. Reference: {booking.id}"

    await email_service.send_email(user.email, f"Booking Confirmation: {event.title}", html_body, plain_text)


async def send_cancellation_email(booking_id: "UUID") -> None:
    db = await _get_db()
    booking_repo = BookingRepository(db)
    user_repo = UserRepository(db)
    event_repo = EventRepository(db)
    payment_repo = PaymentRepository(db)

    booking_dict = await booking_repo.get_by_id(booking_id)
    if not booking_dict:
        return

    booking = Booking(**booking_dict)
    user_dict = await user_repo.get_by_id(booking.user_id)
    event_dict = await event_repo.get_by_id(booking.event_id)
    payment_dict = await payment_repo.get_by_booking_id(booking_id)

    if not user_dict or not event_dict:
        return

    user = User(**user_dict)
    event = Event(**event_dict)

    refund_amount = 0.0
    if payment_dict and hasattr(payment_dict.get("refund_amount"), "to_decimal"):
        refund_amount = float(payment_dict["refund_amount"].to_decimal())
    elif payment_dict:
        refund_amount = float(payment_dict.get("refund_amount", 0.0))

    context = {"user": user, "event": event, "booking": booking, "refund_amount": refund_amount}

    template = "event_cancelled.html" if booking.cancellation_reason == "Event Cancelled" else "booking_cancellation.html"

    html_body = email_service.render_template(template, context)
    plain_text = f"Booking Cancelled for {event.title}."

    await email_service.send_email(user.email, f"Booking Cancellation: {event.title}", html_body, plain_text)


async def send_event_reminder_email(event_id: "UUID") -> None:
    db = await _get_db()
    booking_repo = BookingRepository(db)
    user_repo = UserRepository(db)
    event_repo = EventRepository(db)
    venue_repo = VenueRepository(db)

    event_dict = await event_repo.get_by_id(event_id)
    if not event_dict:
        return

    event = Event(**event_dict)
    venue_dict = await venue_repo.get_by_id(event.venue_id)
    if not venue_dict:
        return
    venue = Venue(**venue_dict)

    cursor = booking_repo.collection.find(
        {"event_id": event_id, "status": BookingStatus.CONFIRMED.value}
    )

    async for b in cursor:
        booking = Booking(**b)
        user_dict = await user_repo.get_by_id(booking.user_id)
        if not user_dict:
            continue

        user = User(**user_dict)
        context = {"user": user, "event": event, "venue": venue}

        html_body = email_service.render_template("event_reminder.html", context)
        plain_text = f"Reminder: {event.title} is happening soon!"

        await email_service.send_email(user.email, f"Reminder: {event.title}", html_body, plain_text)
