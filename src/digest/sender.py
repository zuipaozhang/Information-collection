"""
Email sender via Resend HTTP API.

Uses Resend's HTTP API (not SMTP) for email delivery.
No domain verification needed — works immediately with any verified sender.
"""

import asyncio
import logging
from email.utils import make_msgid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds


class EmailDeliveryError(Exception):
    """Raised when email delivery fails after all retries."""
    pass


class EmailSender:
    """Sends digest emails via Resend HTTP API."""

    def __init__(
        self,
        api_key: str,
        from_addr: str = "",
    ):
        self.api_key = api_key
        self.from_addr = from_addr

    async def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
        message_id: str | None = None,
    ) -> str:
        """
        Send a digest email via Resend API.

        Returns: The Resend email ID string
        """
        if not message_id:
            message_id = make_msgid(domain="ai-digest.local")

        payload: dict[str, Any] = {
            "from": self.from_addr,
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body,
            "headers": {
                "Message-ID": str(message_id),
                "List-Unsubscribe": f"<mailto:{self.from_addr}?subject=unsubscribe>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.post(
                        f"{RESEND_API_URL}/emails",
                        json=payload,
                        headers=headers,
                    )

                if response.status_code == 200:
                    data = response.json()
                    resend_id = data.get("id", str(message_id))
                    logger.info(f"Email sent via Resend: {resend_id} — {subject[:50]}... to {to}")
                    return resend_id
                else:
                    error_text = response.text[:300]
                    raise EmailDeliveryError(
                        f"Resend API returned {response.status_code}: {error_text}"
                    )

            except EmailDeliveryError:
                raise
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY ** attempt
                    logger.warning(
                        f"Resend attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Resend failed after {MAX_RETRIES} attempts: {e}")

        raise EmailDeliveryError(
            f"Failed to send email to {to} after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    async def send_test(self, to: str) -> str:
        """Send a test email to verify configuration."""
        from datetime import datetime

        subject = "AI 信息聚合 — 测试邮件"
        html = f"""<html><body>
          <h2>Resend API 配置测试成功</h2>
          <p>由: {self.from_addr}</p>
          <p>发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body></html>"""
        text = "Resend API 配置测试成功！"

        return await self.send(to, subject, html, text)
