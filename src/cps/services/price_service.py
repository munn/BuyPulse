"""Price analysis: percentile, verdict, trend, and target suggestions.

All prices in cents. Percentile uses full historical data (not windowed).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class PriceVerdict(str, Enum):
    GREAT = "great"        # <15th percentile
    GOOD = "good"          # 15-30th
    FAIR = "fair"          # 30-60th
    HIGH = "high"          # 60-85th
    VERY_HIGH = "very_high"  # >85th


class Density(str, Enum):
    COMPACT = "compact"
    STANDARD = "standard"
    DETAILED = "detailed"


@dataclass(frozen=True)
class PriceAnalysis:
    current_price: int
    historical_low: int
    historical_high: int
    historical_low_date: date | None
    historical_high_date: date | None
    percentile: int  # 0-100
    trend_30d: str   # "dropping", "rising", "stable"
    verdict: PriceVerdict


def calculate_percentile(current: int, history: list[int]) -> int:
    """What percentage of historical prices are below `current`."""
    if not history:
        return 0
    below = sum(1 for p in history if p < current)
    return round(below / len(history) * 100)


def _compute_trend(history: list[tuple[date, int]]) -> str:
    """Simple 30-day trend from most recent data points."""
    if len(history) < 2:
        return "stable"
    cutoff = history[-1][0] - timedelta(days=30)
    recent = [p for d, p in history if d >= cutoff]
    if len(recent) < 2:
        return "stable"
    first_half = sum(recent[: len(recent) // 2]) / max(len(recent) // 2, 1)
    second_half = sum(recent[len(recent) // 2 :]) / max(len(recent) - len(recent) // 2, 1)
    ratio = second_half / first_half if first_half else 1.0
    if ratio < 0.95:
        return "dropping"
    if ratio > 1.05:
        return "rising"
    return "stable"


def _verdict_from_percentile(pct: int) -> PriceVerdict:
    if pct < 15:
        return PriceVerdict.GREAT
    if pct < 30:
        return PriceVerdict.GOOD
    if pct < 60:
        return PriceVerdict.FAIR
    if pct < 85:
        return PriceVerdict.HIGH
    return PriceVerdict.VERY_HIGH


def analyze_price(
    current_price: int,
    price_history: list[tuple[date, int]],
    lowest_price: int,
    lowest_date: date | None,
    highest_price: int,
    highest_date: date | None,
) -> PriceAnalysis:
    """Build full price analysis from current price + historical data."""
    all_prices = [p for _, p in price_history]
    pct = calculate_percentile(current_price, all_prices)
    trend = _compute_trend(price_history)
    return PriceAnalysis(
        current_price=current_price,
        historical_low=lowest_price,
        historical_high=highest_price,
        historical_low_date=lowest_date,
        historical_high_date=highest_date,
        percentile=pct,
        trend_30d=trend,
        verdict=_verdict_from_percentile(pct),
    )


def suggest_targets(
    analysis: PriceAnalysis, all_prices: list[int]
) -> list[dict]:
    """Generate smart target price suggestions (spec Section 3.1).

    Returns list of {"label": str, "price": int} dicts.
    Only includes targets that are below or equal to current price.
    """
    targets: list[dict] = []

    # Historical low
    if analysis.historical_low <= analysis.current_price:
        dollars = analysis.historical_low / 100
        targets.append({
            "label": f"Historical low: ${dollars:,.0f}",
            "price": analysis.historical_low,
        })

    # 30th percentile
    if all_prices:
        sorted_prices = sorted(all_prices)
        idx = max(0, int(len(sorted_prices) * 0.30) - 1)
        p30 = sorted_prices[idx]
        if p30 <= analysis.current_price and p30 != analysis.historical_low:
            dollars = p30 / 100
            targets.append({
                "label": f"30th pct: ${dollars:,.0f}",
                "price": p30,
            })

    return targets


def format_price(cents: int) -> str:
    """Format cents as dollar string: 18900 → '$189'."""
    dollars = cents / 100
    if dollars == int(dollars):
        return f"${int(dollars)}"
    return f"${dollars:,.2f}"
