"""Tests for inline keyboard structure — no Telegram runtime needed."""
from cps.bot.keyboards import (
    build_buy_keyboard,
    build_price_report_keyboard,
    build_target_keyboard,
    build_monitor_item_keyboard,
    build_deal_push_keyboard,
    build_reengagement_keyboard,
    build_downgrade_keyboard,
)


class TestBuyKeyboard:
    def test_contains_buy_button(self):
        kb = build_buy_keyboard("https://amazon.com/dp/B08N5WRWNW?tag=foo")
        assert len(kb) >= 1
        assert any("Buy" in btn["text"] or "Amazon" in btn["text"] for row in kb for btn in row)

    def test_buy_button_is_url(self):
        kb = build_buy_keyboard("https://amazon.com/dp/B08N5WRWNW?tag=foo")
        buy_btn = kb[0][0]
        assert "url" in buy_btn


class TestPriceReportKeyboard:
    def test_standard_has_buy_and_alert(self):
        kb = build_price_report_keyboard(
            buy_url="https://amazon.com/dp/B08N5WRWNW?tag=foo",
            platform_id="B08N5WRWNW",
            density="standard",
        )
        texts = [btn["text"] for row in kb for btn in row]
        assert any("Buy" in t or "Amazon" in t for t in texts)
        assert any("alert" in t.lower() or "set" in t.lower() for t in texts)

    def test_compact_has_detail_expand(self):
        kb = build_price_report_keyboard(
            buy_url="https://amazon.com/dp/B08N5WRWNW?tag=foo",
            platform_id="B08N5WRWNW",
            density="compact",
        )
        texts = [btn["text"] for row in kb for btn in row]
        assert any("▼" in t or "detail" in t.lower() for t in texts)


class TestTargetKeyboard:
    def test_includes_suggestions_and_custom(self):
        targets = [
            {"label": "Historical low: $169", "price": 16900},
            {"label": "30th pct: $189", "price": 18900},
        ]
        kb = build_target_keyboard("B08N5WRWNW", targets)
        texts = [btn["text"] for row in kb for btn in row]
        assert any("$169" in t for t in texts)
        assert any("Custom" in t or "custom" in t for t in texts)
        assert any("Skip" in t or "skip" in t.lower() for t in texts)


class TestDealPushKeyboard:
    def test_has_buy_and_dismiss(self):
        kb = build_deal_push_keyboard(
            buy_url="https://amazon.com/dp/B08N5WRWNW?tag=foo",
            platform_id="B08N5WRWNW",
            category="Electronics",
        )
        texts = [btn["text"] for row in kb for btn in row]
        assert any("Buy" in t or "Amazon" in t for t in texts)
        assert any("Stop" in t or "stop" in t.lower() for t in texts)
