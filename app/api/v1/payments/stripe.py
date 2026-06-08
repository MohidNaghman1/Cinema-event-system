from decimal import Decimal
from uuid import UUID

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Request, Response
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.db.mongodb import get_database
from app.models.payment import PaymentStatus
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.repositories.event_repo import EventRepository
from app.repositories.payment_repo import PaymentRepository
from app.repositories.user_repo import UserRepository
from app.repositories.venue_repo import VenueRepository
from app.services.booking_service import BookingService
from app.services.seat_service import SeatService
from app.services.stripe_service import StripeService
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/api/v1/payments/stripe", tags=["Payments"], responses={    401: {"description": "Unauthorized - Invalid or missing authentication token."},    403: {"description": "Forbidden - You do not have the required role permissions."},    422: {"description": "Unprocessable Entity - Schema validation error on the request payload."}})


def get_services(db: AsyncIOMotorDatabase = Depends(get_database)):
    payment_repo = PaymentRepository(db)
    booking_repo = BookingRepository(db)
    event_repo = EventRepository(db)
    venue_repo = VenueRepository(db)
    user_repo = UserRepository(db)

    seat_service = SeatService(event_repo)
    ticket_service = TicketService(booking_repo, event_repo, venue_repo, user_repo)
    booking_service = BookingService(
        booking_repo, event_repo, venue_repo, seat_service, ticket_service
    )
    stripe_service = StripeService(payment_repo)

    return stripe_service, booking_service, payment_repo, user_repo


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    stripe_signature: str = Header(None),
    services: tuple = Depends(get_services),
):
    settings = get_settings()
    stripe_service, booking_service, payment_repo, user_repo = services

    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return Response(status_code=400)

    try:
        if event.type == "payment_intent.succeeded":
            payment_intent = event.data.object
            payment_dict = await payment_repo.get_by_gateway_id(payment_intent.id)

            if payment_dict and payment_dict["status"] != PaymentStatus.SUCCEEDED.value:
                await stripe_service.confirm_payment(payment_intent.id)

                booking_id = UUID(payment_dict["booking_id"])
                user_dict = await user_repo.get_by_id(payment_dict["user_id"])
                if user_dict:
                    await booking_service.confirm_booking(
                        booking_id,
                        payment_dict["_id"],
                        user_dict["email"],
                        background_tasks,
                    )

        elif event.type == "payment_intent.payment_failed":
            payment_intent = event.data.object
            payment_dict = await payment_repo.get_by_gateway_id(payment_intent.id)

            if payment_dict and payment_dict["status"] != PaymentStatus.FAILED.value:
                await payment_repo.update(
                    payment_dict["_id"], {"status": PaymentStatus.FAILED.value}
                )

                booking_id = UUID(payment_dict["booking_id"])
                user_dict = await user_repo.get_by_id(payment_dict["user_id"])
                if user_dict:
                    user = User(**user_dict)
                    await booking_service.cancel_booking(booking_id, user, "Payment Failed")

        elif event.type == "charge.refunded":
            charge = event.data.object
            payment_intent_id = charge.payment_intent
            payment_dict = await payment_repo.get_by_gateway_id(payment_intent_id)

            if payment_dict:
                amount_refunded = Decimal(charge.amount_refunded) / Decimal("100.00")
                
                current_refund = payment_dict["refund_amount"].to_decimal() if hasattr(payment_dict["refund_amount"], "to_decimal") else payment_dict["refund_amount"]
                current_amount = payment_dict["amount"].to_decimal() if hasattr(payment_dict["amount"], "to_decimal") else payment_dict["amount"]
                
                new_refund = current_refund + amount_refunded

                status = (
                    PaymentStatus.REFUNDED.value
                    if new_refund >= current_amount
                    else PaymentStatus.PARTIALLY_REFUNDED.value
                )
                await payment_repo.update(
                    payment_dict["_id"], {"status": status, "refund_amount": new_refund}
                )

    except Exception as e:
        print(f"Webhook processing error: {e}")

    # Always return 200 to Stripe even on processing errors per idempotency guidelines
    return Response(status_code=200)
