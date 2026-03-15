"""Email alerting via Resend API with rate limiting."""

import time

import resend


class AlertService:
    """Send email alerts via Resend with per-type rate limiting."""

    def __init__(self, api_key: str, email_to: str, email_from: str) -> None:
        if not api_key:
            raise ValueError("Resend API key must not be empty")

        self._api_key = api_key
        self._email_to = email_to
        self._email_from = email_from
        self._last_sent: dict[str, float] = {}
        self._rate_limit_secs = 3600.0  # 1 hour

        resend.api_key = api_key

    async def send_alert(
        self, severity: str, title: str, body: str
    ) -> bool:
        """Send an email alert, respecting per-type rate limits.

        Returns True if sent, False if rate-limited or failed.
        """
        alert_key = f"{severity}:{title}"

        # Check rate limit
        now = time.monotonic()
        if alert_key in self._last_sent:
            elapsed = now - self._last_sent[alert_key]
            if elapsed < self._rate_limit_secs:
                return False

        # Send email
        subject = f"[CPS Alert] {severity}: {title}"
        try:
            resend.Emails.send({
                "from": self._email_from,
                "to": self._email_to,
                "subject": subject,
                "html": body,
            })
            self._last_sent[alert_key] = now
            return True
        except Exception:
            return False
