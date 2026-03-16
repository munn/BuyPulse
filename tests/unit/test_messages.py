"""Tests for message template rendering — EN/ES, 3 density levels."""
from datetime import date

from cps.bot.messages import MessageTemplates, render_price_report
from cps.services.price_service import Density, PriceAnalysis, PriceVerdict


class TestPriceReport:
    ANALYSIS = PriceAnalysis(
        current_price=18900,
        historical_low=16900,
        historical_high=24900,
        historical_low_date=date(2025, 4, 1),
        historical_high_date=date(2025, 1, 1),
        percentile=25,
        trend_30d="dropping",
        verdict=PriceVerdict.GOOD,
    )

    def test_compact_en(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.COMPACT,
            language="en",
        )
        assert "$189" in msg
        assert "$169" in msg
        assert "$249" in msg
        lines = [l for l in msg.strip().split("\n") if l.strip()]
        assert len(lines) <= 4  # compact is 3-4 lines

    def test_standard_en(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.STANDARD,
            language="en",
        )
        assert "AirPods Pro 2" in msg
        assert "$189" in msg
        assert "lower" in msg.lower() or "good" in msg.lower()

    def test_detailed_en(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.DETAILED,
            language="en",
        )
        assert "Percentile" in msg or "25%" in msg
        assert "dropping" in msg.lower() or "▼" in msg

    def test_spanish_compact(self):
        msg = render_price_report(
            title="AirPods Pro 2",
            analysis=self.ANALYSIS,
            density=Density.COMPACT,
            language="es",
        )
        assert "$189" in msg  # prices same in any language
        # Should contain Spanish text
        assert any(w in msg.lower() for w in ["buen", "precio", "bajo"])


class TestTemplates:
    def test_onboarding_en(self):
        t = MessageTemplates("en")
        msg = t.onboarding(
            title="AirPods Pro 2 (USB-C)",
            price_report="Current: $189\nHistorical: $169 - $249",
        )
        assert "BuyPulse" in msg
        assert "Privacy Policy" in msg

    def test_onboarding_es(self):
        t = MessageTemplates("es")
        msg = t.onboarding(
            title="AirPods Pro 2 (USB-C)",
            price_report="Current: $189",
        )
        assert "BuyPulse" in msg

    def test_monitor_limit_reached(self):
        t = MessageTemplates("en")
        msg = t.monitor_limit_reached(current=20, limit=20)
        assert "20/20" in msg

    def test_welcome_back(self):
        t = MessageTemplates("en")
        msg = t.welcome_back(monitor_count=3)
        assert "3" in msg
        assert "Welcome back" in msg or "welcome back" in msg
