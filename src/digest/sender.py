"""
Email sender.

Sends digest emails via SMTP (Resend, SendGrid, or any SMTP provider).
Uses aiosmtplib for async SMTP with exponential backoff retry.
Generates MIME multipart/alternative messages with HTML + plain text.
"""

import asyncio
import logging
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid

import aiosmtplib

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds


class EmailDeliveryError(Exception):
    """Raised when email delivery fails after all retries."""
    pass


class EmailSender:
    """Sends digest emails via SMTP."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        username: str = "",
        password: str = "",
        from_addr: str = "",
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.use_tls = use_tls

    async def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
        message_id: str | None = None,
    ) -> str:
        """
        Send a digest email.

        Args:
            to: Recipient email address
            subject: Email subject
            html_body: HTML email body
            text_body: Plain text email body
            message_id: Optional custom message ID

        Returns:
            The sent message ID string

        Raises:
            EmailDeliveryError: If delivery fails after all retries
        """
        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = Header(subject, "utf-8")

        if message_id:
            msg["Message-ID"] = message_id
        else:
            msg["Message-ID"] = make_msgid(domain="ai-digest.local")

        # RFC 8058: One-click unsubscribe
        msg["List-Unsubscribe"] = f"<mailto:{self.from_addr}?subject=unsubscribe>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        message_id_str = str(msg["Message-ID"])

        # Send with retry
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await self._deliver(msg)
                logger.info(f"Email sent: {subject[:50]}... to {to}")
                return message_id_str
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY ** attempt
                    logger.warning(
                        f"SMTP attempt {attempt}/{MAX_RETRIES} failed: {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"SMTP failed after {MAX_RETRIES} attempts: {e}"
                    )

        raise EmailDeliveryError(
            f"Failed to send email to {to} after {MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    async def _deliver(self, msg: MIMEMultipart) -> None:
        """Deliver a single message via SMTP."""
        kwargs: dict = {
            "hostname": self.smtp_host,
            "port": self.smtp_port,
            "use_tls": False,
        }

        if self.username and self.password:
            kwargs["username"] = self.username
            kwargs["password"] = self.password
            kwargs["use_tls"] = True

        async with aiosmtplib.SMTP(**kwargs) as smtp:
            await smtp.send_message(msg)

    async def send_test(self, to: str) -> str:
        """Send a test email to verify SMTP configuration."""
        subject = "✅ AI 信息聚合 — 测试邮件"
        html = f"""
        <html><body>
          <h2>SMTP 配置测试成功</h2>
          <p>如果您收到这封邮件，说明邮件发送配置正确。</p>
          <p>发送时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
          <p>SMTP 服务器: {self.smtp_host}:{self.smtp_port}</p>
        </body></html>
        """
        text = "SMTP 配置测试成功！如果您收到这封邮件，说明邮件发送配置正确。"

        return await self.send(to, subject, html, text)
