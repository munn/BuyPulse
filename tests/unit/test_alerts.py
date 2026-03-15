"""T018: Unit tests for cps.alerts.email — email alerting via Resend API.

These tests verify:
- Sends email via Resend API
- Subject format is [CPS Alert] {severity}: {title}
- Rate limiting: same alert within 1 hour → only first sent
- Different alert types → all sent
- Body text included in email
- Empty API key → raises ValueError or returns False
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cps.alerts.email import AlertService


class TestAlertServiceInit:
    """AlertService requires API key and email configuration."""

    def test_creates_with_valid_config(self):
        service = AlertService(
            api_key="re_test_key_123",
            email_to="admin@example.com",
            email_from="alerts@cps.example.com",
        )
        assert service is not None

    def test_empty_api_key_raises_value_error(self):
        """Empty API key should raise ValueError at init."""
        with pytest.raises(ValueError):
            AlertService(
                api_key="",
                email_to="admin@example.com",
                email_from="alerts@cps.example.com",
            )


class TestSendAlert:
    """send_alert sends emails via Resend and returns success status."""

    @pytest.fixture
    def alert_service(self):
        return AlertService(
            api_key="re_test_key_123",
            email_to="admin@example.com",
            email_from="alerts@cps.example.com",
        )

    @patch("cps.alerts.email.resend")
    async def test_sends_email_via_resend(self, mock_resend, alert_service):
        """Successful send returns True."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        result = await alert_service.send_alert(
            severity="CRITICAL",
            title="High failure rate",
            body="50 consecutive ASINs failed extraction.",
        )

        assert result is True
        mock_resend.Emails.send.assert_called_once()

    @patch("cps.alerts.email.resend")
    async def test_subject_format(self, mock_resend, alert_service):
        """Subject line follows [CPS Alert] {severity}: {title} format."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        await alert_service.send_alert(
            severity="WARNING",
            title="Disk usage high",
            body="Disk usage at 85%.",
        )

        call_args = mock_resend.Emails.send.call_args
        # The send call should include the formatted subject
        sent_params = call_args[1] if call_args[1] else call_args[0][0]
        assert sent_params["subject"] == "[CPS Alert] WARNING: Disk usage high"

    @patch("cps.alerts.email.resend")
    async def test_includes_body_text(self, mock_resend, alert_service):
        """Email body contains the provided body text."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        body_text = "50 consecutive ASINs failed. Pipeline paused."
        await alert_service.send_alert(
            severity="CRITICAL",
            title="Pipeline failure",
            body=body_text,
        )

        call_args = mock_resend.Emails.send.call_args
        sent_params = call_args[1] if call_args[1] else call_args[0][0]
        # Body should be in either 'html' or 'text' field
        body_value = sent_params.get("html", sent_params.get("text", ""))
        assert body_text in body_value

    @patch("cps.alerts.email.resend")
    async def test_uses_configured_email_addresses(self, mock_resend, alert_service):
        """Email uses the configured from/to addresses."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        await alert_service.send_alert(
            severity="WARNING",
            title="Test",
            body="Test body",
        )

        call_args = mock_resend.Emails.send.call_args
        sent_params = call_args[1] if call_args[1] else call_args[0][0]
        assert sent_params["to"] == "admin@example.com"
        assert sent_params["from"] == "alerts@cps.example.com"


class TestRateLimiting:
    """Same alert type within 1 hour should be suppressed."""

    @pytest.fixture
    def alert_service(self):
        return AlertService(
            api_key="re_test_key_123",
            email_to="admin@example.com",
            email_from="alerts@cps.example.com",
        )

    @patch("cps.alerts.email.resend")
    async def test_first_alert_sent(self, mock_resend, alert_service):
        """First alert of a given type is always sent."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        result = await alert_service.send_alert(
            severity="CRITICAL",
            title="High failure rate",
            body="Details here.",
        )

        assert result is True

    @patch("cps.alerts.email.resend")
    async def test_duplicate_alert_within_hour_skipped(self, mock_resend, alert_service):
        """Same severity+title combo within 1 hour → second call returns False."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        first = await alert_service.send_alert(
            severity="CRITICAL",
            title="High failure rate",
            body="First alert.",
        )
        second = await alert_service.send_alert(
            severity="CRITICAL",
            title="High failure rate",
            body="Second alert, same type.",
        )

        assert first is True
        assert second is False
        # Resend API should only be called once
        assert mock_resend.Emails.send.call_count == 1

    @patch("cps.alerts.email.resend")
    async def test_different_severity_not_rate_limited(self, mock_resend, alert_service):
        """Different severity → treated as different alert type → both sent."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        first = await alert_service.send_alert(
            severity="CRITICAL",
            title="High failure rate",
            body="Critical alert.",
        )
        second = await alert_service.send_alert(
            severity="WARNING",
            title="High failure rate",
            body="Warning alert.",
        )

        assert first is True
        assert second is True
        assert mock_resend.Emails.send.call_count == 2

    @patch("cps.alerts.email.resend")
    async def test_different_title_not_rate_limited(self, mock_resend, alert_service):
        """Different title → treated as different alert type → both sent."""
        mock_resend.Emails.send.return_value = {"id": "email_123"}

        first = await alert_service.send_alert(
            severity="CRITICAL",
            title="High failure rate",
            body="Alert one.",
        )
        second = await alert_service.send_alert(
            severity="CRITICAL",
            title="Disk usage high",
            body="Alert two.",
        )

        assert first is True
        assert second is True
        assert mock_resend.Emails.send.call_count == 2

    @patch("cps.alerts.email.resend")
    async def test_alert_allowed_after_rate_limit_expires(
        self, mock_resend, alert_service
    ):
        """After 1 hour, same alert type should be sendable again."""
        from unittest.mock import PropertyMock

        mock_resend.Emails.send.return_value = {"id": "email_123"}

        # Send first alert
        first = await alert_service.send_alert(
            severity="CRITICAL",
            title="High failure rate",
            body="First alert.",
        )
        assert first is True

        # Simulate time passing by manipulating the internal rate limit tracker.
        # The exact mechanism depends on implementation, but we patch time.
        import time

        with patch("cps.alerts.email.time") as mock_time:
            # Simulate current time being 1 hour + 1 second in the future
            mock_time.monotonic.return_value = time.monotonic() + 3601

            third = await alert_service.send_alert(
                severity="CRITICAL",
                title="High failure rate",
                body="After rate limit expired.",
            )

        assert third is True


class TestSendAlertErrorHandling:
    """Error scenarios when sending alerts."""

    @patch("cps.alerts.email.resend")
    async def test_resend_api_failure_returns_false(self, mock_resend):
        """If Resend API raises an exception, send_alert returns False."""
        mock_resend.Emails.send.side_effect = Exception("API error")

        service = AlertService(
            api_key="re_test_key_123",
            email_to="admin@example.com",
            email_from="alerts@cps.example.com",
        )

        result = await service.send_alert(
            severity="CRITICAL",
            title="Test",
            body="Test body",
        )

        assert result is False

    async def test_empty_api_key_does_not_send(self):
        """Empty API key at construction time → ValueError, no send attempt."""
        with pytest.raises(ValueError):
            AlertService(
                api_key="",
                email_to="admin@example.com",
                email_from="alerts@cps.example.com",
            )
