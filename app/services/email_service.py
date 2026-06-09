import logging

from app.core.email import email_service

logger = logging.getLogger(__name__)


async def send_verification_email(email: str, token: str) -> None:
    html_body = email_service.render_template("verify_email.html", {"token": token})
    plain_text = f"Verify your account using this link or token: {token}"

    success = await email_service.send_email(
        email,
        "Verify your account - Cinema Events",
        html_body,
        plain_text,
    )
    if not success:
        logger.error("Failed to send verification email to %s", email)


async def send_password_reset_email(email: str, token: str) -> None:
    html_body = email_service.render_template("password_reset.html", {"reset_token": token})
    plain_text = f"Reset your password using this token: {token}"

    success = await email_service.send_email(
        email,
        "Password Reset Request - Cinema Events",
        html_body,
        plain_text,
    )
    if not success:
        logger.error("Failed to send password reset email to %s", email)
