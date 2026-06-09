import io
from datetime import datetime, timezone

from jose import jwt
import qrcode

from app.config import get_settings


def generate_qr(
    booking_id: str, event_id: str, seat_ids: list[str], user_id: str
) -> bytes:
    """
    Generates a QR code PNG encoding a signed JWT containing ticket details.
    This prevents forgery and can be verified natively at the gate.
    """
    settings = get_settings()

    payload = {
        "booking_id": booking_id,
        "event_id": event_id,
        "seat_ids": seat_ids,
        "user_id": user_id,
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }

    # Encode details cryptographically
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    # Generate QR PNG
    img = qrcode.make(token)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    return buf.getvalue()
