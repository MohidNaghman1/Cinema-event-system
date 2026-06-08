from decimal import Decimal
from typing import Any
from uuid import UUID

import stripe
from fastapi import HTTPException

from app.config import get_settings
from app.models.payment import Payment, PaymentStatus
from app.repositories.payment_repo import PaymentRepository

settings = get_settings()
if settings.stripe_api_key:
    stripe.api_key = settings.stripe_api_key


class PaymentError(HTTPException):
    pass


class StripeService:
    def __init__(self, payment_repo: PaymentRepository):
        self.payment_repo = payment_repo

    async def create_payment_intent(
        self, booking_id: UUID, user_id: UUID, amount_cents: int, currency: str, metadata: dict
    ) -> dict[str, Any]:
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents, currency=currency.lower(), metadata=metadata
            )

            payment = Payment(
                booking_id=booking_id,
                user_id=user_id,
                gateway_payment_id=intent.id,
                amount=Decimal(amount_cents) / Decimal("100.00"),
                currency=currency.upper(),
                status=PaymentStatus.CREATED,
                metadata=metadata,
            )
            await self.payment_repo.create(payment)
            return intent

        except stripe.StripeError as e:
            raise PaymentError(status_code=400, detail=str(e))

    async def confirm_payment(self, payment_intent_id: str) -> Payment:
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            payment_dict = await self.payment_repo.get_by_gateway_id(payment_intent_id)
            if not payment_dict:
                raise PaymentError(status_code=404, detail="Payment record not found")

            payment = Payment(**payment_dict)

            if intent.status == "succeeded":
                payment.status = PaymentStatus.SUCCEEDED
                if intent.latest_charge:
                    payment.gateway_charge_id = intent.latest_charge
            elif intent.status == "processing":
                payment.status = PaymentStatus.PENDING
            elif intent.status in ("requires_payment_method", "requires_action"):
                pass  # Client 3DS or action still needed
            elif intent.status == "canceled":
                payment.status = PaymentStatus.FAILED

            await self.payment_repo.update(
                payment.id,
                {"status": payment.status.value, "gateway_charge_id": payment.gateway_charge_id},
            )
            return payment

        except stripe.StripeError as e:
            raise PaymentError(status_code=400, detail=str(e))

    async def create_refund(
        self, payment_id: UUID, amount_cents: int, reason: str
    ) -> dict[str, Any]:
        try:
            payment_dict = await self.payment_repo.get_by_id(payment_id)
            if not payment_dict:
                raise PaymentError(status_code=404, detail="Payment record not found")

            payment = Payment(**payment_dict)

            if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
                raise PaymentError(
                    status_code=400, detail=f"Cannot refund payment in {payment.status} state"
                )

            valid_reasons = ["duplicate", "fraudulent", "requested_by_customer"]
            stripe_reason = reason if reason in valid_reasons else "requested_by_customer"

            refund = stripe.Refund.create(
                payment_intent=payment.gateway_payment_id,
                amount=amount_cents,
                reason=stripe_reason,
            )

            refunded_amount = Decimal(amount_cents) / Decimal("100.00")
            
            # Using to_decimal for Decimal128 safety
            current_refund = payment.refund_amount.to_decimal() if hasattr(payment.refund_amount, "to_decimal") else payment.refund_amount
            current_amount = payment.amount.to_decimal() if hasattr(payment.amount, "to_decimal") else payment.amount
            
            new_refund_total = current_refund + refunded_amount

            new_status = (
                PaymentStatus.REFUNDED
                if new_refund_total >= current_amount
                else PaymentStatus.PARTIALLY_REFUNDED
            )

            await self.payment_repo.update(
                payment_id, {"status": new_status.value, "refund_amount": new_refund_total}
            )

            payment.status = new_status
            payment.refund_amount = new_refund_total
            return refund

        except stripe.StripeError as e:
            raise PaymentError(status_code=400, detail=str(e))

    async def retrieve_intent(self, gateway_payment_id: str) -> dict[str, Any]:
        try:
            return stripe.PaymentIntent.retrieve(gateway_payment_id)
        except stripe.StripeError as e:
            raise PaymentError(status_code=400, detail=str(e))
