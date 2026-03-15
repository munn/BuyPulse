"""Integration tests for email alert rate limiting — quickstart scenario 10 (T022).

Tests that alert rate limiting works correctly across time boundaries.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from cps.alerts.email import AlertService


@pytest.fixture
def alert_service():
    """Create an AlertService with mock API key."""
    return AlertService(
        api_key="re_test_key_123",
        email_to="test@example.com",
        email_from="alerts@cps.local",
    )


class TestAlertRateLimiting:
    async def test_first_alert_always_sent(self, alert_service):
        """First alert of any type is always sent."""
        with patch("cps.alerts.email.resend") as mock_resend:
            mock_resend.Emails.send = AsyncMock(return_value={"id": "123"})
            result = await alert_service.send_alert(
                severity="CRITICAL",
                title="Test Alert",
                body="Something happened",
            )
            assert result is True

    async def test_duplicate_alert_within_hour_suppressed(self, alert_service):
        """Same alert type within 1 hour → only first sent."""
        with patch("cps.alerts.email.resend") as mock_resend:
            mock_resend.Emails.send = AsyncMock(return_value={"id": "123"})

            # First send — should succeed
            r1 = await alert_service.send_alert(
                severity="CRITICAL",
                title="Test Alert",
                body="First occurrence",
            )
            assert r1 is True

            # Rapid-fire same alert 4 more times
            results = []
            for i in range(4):
                r = await alert_service.send_alert(
                    severity="CRITICAL",
                    title="Test Alert",
                    body=f"Occurrence {i + 2}",
                )
                results.append(r)

            # All 4 should be suppressed
            assert all(r is False for r in results)

            # Only 1 actual email sent
            assert mock_resend.Emails.send.call_count == 1

    async def test_different_alert_types_not_suppressed(self, alert_service):
        """Different alert types (different severity or title) → all sent."""
        with patch("cps.alerts.email.resend") as mock_resend:
            mock_resend.Emails.send = AsyncMock(return_value={"id": "123"})

            await alert_service.send_alert("CRITICAL", "Alert A", "body")
            await alert_service.send_alert("WARNING", "Alert B", "body")
            await alert_service.send_alert("CRITICAL", "Alert C", "body")

            assert mock_resend.Emails.send.call_count == 3

    async def test_alert_sent_after_rate_limit_expires(self, alert_service):
        """After rate limit window expires, same alert type can be sent again."""
        with patch("cps.alerts.email.resend") as mock_resend:
            mock_resend.Emails.send = AsyncMock(return_value={"id": "123"})

            # Send first alert
            await alert_service.send_alert("CRITICAL", "Test", "body")

            # Manually expire the rate limit (simulate time passing)
            # Override the internal timestamp to 2 hours ago
            for key in alert_service._last_sent:
                alert_service._last_sent[key] = time.monotonic() - 7200

            # Same alert should now succeed
            result = await alert_service.send_alert("CRITICAL", "Test", "body")
            assert result is True
            assert mock_resend.Emails.send.call_count == 2
