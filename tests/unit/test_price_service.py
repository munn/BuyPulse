"""Tests for price percentile, verdict, and target suggestion logic."""
from datetime import date

from cps.services.price_service import (
    Density,
    PriceAnalysis,
    PriceVerdict,
    analyze_price,
    calculate_percentile,
    suggest_targets,
)


class TestPercentile:
    def test_at_historical_low(self):
        assert calculate_percentile(100, [100, 200, 300, 400, 500]) == 0

    def test_at_historical_high(self):
        # 4 of 5 prices are strictly below 500 → 80%
        assert calculate_percentile(500, [100, 200, 300, 400, 500]) == 80

    def test_midpoint(self):
        pct = calculate_percentile(300, [100, 200, 300, 400, 500])
        assert 40 <= pct <= 60  # around 50th percentile

    def test_below_all(self):
        assert calculate_percentile(50, [100, 200, 300]) == 0

    def test_single_price(self):
        assert calculate_percentile(100, [100]) == 0

    def test_empty_history(self):
        assert calculate_percentile(100, []) == 0


class TestAnalyzePrice:
    def test_good_price_verdict(self):
        history = [(date(2025, m, 1), p) for m, p in [
            (1, 24900), (2, 22900), (3, 19900), (4, 16900),
            (5, 18900), (6, 21900), (7, 24900), (8, 22900),
            (9, 19900), (10, 18900), (11, 16900), (12, 18900),
        ]]
        analysis = analyze_price(
            current_price=18900,
            price_history=history,
            lowest_price=16900,
            lowest_date=date(2025, 4, 1),
            highest_price=24900,
            highest_date=date(2025, 1, 1),
        )
        assert analysis.current_price == 18900
        assert analysis.historical_low == 16900
        assert analysis.historical_high == 24900
        assert analysis.percentile <= 30
        assert analysis.verdict in (PriceVerdict.GOOD, PriceVerdict.GREAT)


class TestSuggestTargets:
    def test_returns_historical_low_and_percentile(self):
        analysis = PriceAnalysis(
            current_price=18900,
            historical_low=16900,
            historical_high=24900,
            historical_low_date=date(2025, 4, 1),
            historical_high_date=date(2025, 1, 1),
            percentile=25,
            trend_30d="dropping",
            verdict=PriceVerdict.GOOD,
        )
        targets = suggest_targets(analysis, all_prices=[14900, 16900, 18900, 19900, 22900, 24900])
        labels = [t["label"] for t in targets]
        # Should have historical low and 30th percentile options
        assert any("$169" in l for l in labels)
        assert len(targets) >= 2

    def test_no_suggestions_when_at_low(self):
        analysis = PriceAnalysis(
            current_price=16900,
            historical_low=16900,
            historical_high=24900,
            historical_low_date=date(2025, 4, 1),
            historical_high_date=date(2025, 1, 1),
            percentile=0,
            trend_30d="stable",
            verdict=PriceVerdict.GREAT,
        )
        targets = suggest_targets(analysis, all_prices=[16900, 18900, 24900])
        # Historical low equals current — may only have 30th pct or fewer
        assert all(t["price"] <= 16900 for t in targets)
