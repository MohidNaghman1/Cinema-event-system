import asyncio
import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import aiosmtplib
from jinja2 import Environment, FileSystemLoader

from app.config import get_settings

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    def render_template(self, template_name: str, context: dict[str, Any]) -> str:
        """Renders a Jinja2 template and injects dynamic context."""
        context["frontend_url"] = self.settings.frontend_url
        template = self.env.get_template(template_name)
        return template.render(**context)

    async def send_email(
        self, to: str, subject: str, html_body: str, plain_text_fallback: str = ""
    ) -> bool:
        """
        Asynchronously sends an email matching the configured provider.
        Utilizes 3-attempt exponential backoff retry logic to handle transient network errors.
        """
        for attempt in range(1, 4):
            try:
                if self.settings.mail_provider.upper() == "SENDGRID":
                    await self._send_via_sendgrid(to, subject, html_body, plain_text_fallback)
                else:
                    await self._send_via_smtp(to, subject, html_body, plain_text_fallback)
                return True
            except Exception as e:
                logger.error(f"Email sending failed on attempt {attempt}: {e}")
                if attempt == 3:
                    return False
                await asyncio.sleep(2**attempt)
        return False

    async def _send_via_smtp(
        self, to: str, subject: str, html_body: str, plain_text_fallback: str
    ) -> None:
        message = EmailMessage()
        message["From"] = self.settings.default_from_email
        message["To"] = to
        message["Subject"] = subject
        
        # Set plain text as primary, then attach HTML as alternative
        message.set_content(plain_text_fallback or "Please enable HTML to view this email.")
        message.add_alternative(html_body, subtype="html")

        if not self.settings.email_host:
            logger.warning("SMTP host not configured. Simulating email send.")
            return

        await aiosmtplib.send(
            message,
            hostname=self.settings.email_host,
            port=self.settings.email_port,
            username=self.settings.email_host_user,
            password=self.settings.email_host_password,
            use_tls=False,
            start_tls=self.settings.email_use_tls,
        )

    async def _send_via_sendgrid(
        self, to: str, subject: str, html_body: str, plain_text_fallback: str
    ) -> None:
        """
        SendGrid fallback layer utilizing the standard HTTP v3 API.
        This bypasses the sendgrid python package overhead allowing purely async HTTP delivery.
        """
        import httpx

        if not self.settings.sendgrid_api_key:
            logger.warning("SendGrid API key not configured. Simulating email send.")
            return

        headers = {
            "Authorization": f"Bearer {self.settings.sendgrid_api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self.settings.default_from_email},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": plain_text_fallback or "Please enable HTML."},
                {"type": "text/html", "value": html_body},
            ],
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send", headers=headers, json=payload
            )
            response.raise_for_status()

# Singleton accessor
email_service = EmailService()
