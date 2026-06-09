import logging

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.config import get_settings

logger = logging.getLogger(__name__)

def get_email_config() -> ConnectionConfig:
    settings = get_settings()
    
    # Using defaults if they are missing so it doesn't crash on startup if .env is missing
    return ConnectionConfig(
        MAIL_USERNAME=settings.email_host_user or "missing_user@gmail.com",
        MAIL_PASSWORD=settings.email_host_password or "missing_password",
        MAIL_FROM=settings.default_from_email or "noreply@cinema-events.com",
        MAIL_PORT=settings.email_port or 587,
        MAIL_SERVER=settings.email_host or "smtp.gmail.com",
        MAIL_STARTTLS=settings.email_use_tls,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True
    )

async def send_verification_email(email: str, token: str) -> None:
    settings = get_settings()
    if not settings.email_host_user or not settings.email_host_password:
        logger.warning(f"[MOCK EMAIL] Missing SMTP config. Would have sent verification email to {email}. Token: {token}")
        return
        
    try:
        conf = get_email_config()
        message = MessageSchema(
            subject="Verify your account - Cinema Events",
            recipients=[email],
            body=f"""
            <h1>Welcome to Cinema Events!</h1>
            <p>Please verify your email using this token:</p>
            <p><strong>{token}</strong></p>
            <p>If you have a frontend, you would normally click this link: <a href="{settings.frontend_url}/verify-email?token={token}">Verify Email</a></p>
            """,
            subtype=MessageType.html
        )

        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Successfully sent verification email to {email}")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")

async def send_password_reset_email(email: str, token: str) -> None:
    settings = get_settings()
    if not settings.email_host_user or not settings.email_host_password:
        logger.warning(f"[MOCK EMAIL] Missing SMTP config. Would have sent reset email to {email}. Token: {token}")
        return

    try:
        conf = get_email_config()
        message = MessageSchema(
            subject="Password Reset Request - Cinema Events",
            recipients=[email],
            body=f"""
            <h1>Password Reset</h1>
            <p>You requested a password reset. Use this token:</p>
            <p><strong>{token}</strong></p>
            <p>If you did not request this, please ignore this email.</p>
            """,
            subtype=MessageType.html
        )

        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Successfully sent password reset email to {email}")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
