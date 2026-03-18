"""i18n message templates for BuyPulse Telegram bot.

Two languages: EN, ES. Three density levels: compact, standard, detailed.
All templates are plain functions — no Telegram dependency.
"""
from cps.services.price_service import Density, PriceAnalysis, PriceVerdict, format_price

_VERDICT_EN = {
    PriceVerdict.GREAT: "excellent price",
    PriceVerdict.GOOD: "good price",
    PriceVerdict.FAIR: "fair price",
    PriceVerdict.HIGH: "above average",
    PriceVerdict.VERY_HIGH: "near highest",
}

_VERDICT_ES = {
    PriceVerdict.GREAT: "precio excelente",
    PriceVerdict.GOOD: "buen precio",
    PriceVerdict.FAIR: "precio justo",
    PriceVerdict.HIGH: "por encima del promedio",
    PriceVerdict.VERY_HIGH: "cerca del máximo",
}

_TREND_SYMBOL = {"dropping": "▼", "rising": "▲", "stable": "→"}


def render_price_report(
    title: str,
    analysis: PriceAnalysis,
    density: Density,
    language: str = "en",
) -> str:
    """Render price report at the requested density level."""
    cur = format_price(analysis.current_price)
    low = format_price(analysis.historical_low)
    high = format_price(analysis.historical_high)
    verdict_map = _VERDICT_ES if language == "es" else _VERDICT_EN
    verdict = verdict_map[analysis.verdict]

    if density == Density.COMPACT:
        return (
            f"{title} — {cur} ({verdict})\n"
            f"Historical: {low} - {high}"
        )

    if density == Density.STANDARD:
        pct_label = f"lower {analysis.percentile}%" if analysis.percentile <= 50 else f"upper {100 - analysis.percentile}%"
        return (
            f"{title}\n"
            f"Current: {cur}\n"
            f"Historical: {low} - {high}\n"
            f"This price is in the {pct_label} of its range ({verdict})."
        )

    # Detailed
    low_date = analysis.historical_low_date.strftime("%Y-%m-%d") if analysis.historical_low_date else "N/A"
    high_date = analysis.historical_high_date.strftime("%Y-%m-%d") if analysis.historical_high_date else "N/A"
    trend_sym = _TREND_SYMBOL.get(analysis.trend_30d, "→")
    return (
        f"{title}\n"
        f"Current: {cur}\n"
        f"Historical low: {low} ({low_date})\n"
        f"Historical high: {high} ({high_date})\n"
        f"Percentile: {analysis.percentile}%\n"
        f"30-day trend: {trend_sym} {analysis.trend_30d}\n"
        f"Verdict: {verdict.capitalize()}."
    )


class MessageTemplates:
    """Template factory for a specific language."""

    def __init__(self, language: str = "en") -> None:
        self.lang = language

    def onboarding(self, title: str, price_report: str) -> str:
        if self.lang == "es":
            return (
                f"¡Hola! Soy BuyPulse. Déjame mostrarte lo que hago.\n\n"
                f"{title}\n{price_report}\n\n"
                f"Eso es todo. Envíame cualquier enlace de Amazon o dime qué quieres comprar.\n\n"
                f"Al usar BuyPulse, aceptas nuestra Política de Privacidad."
            )
        return (
            f"Hey! I'm BuyPulse. Let me show you what I do.\n\n"
            f"{title}\n{price_report}\n\n"
            f"That's it. Send me any Amazon link or just tell me "
            f"what you want to buy. I'll track the price for you.\n\n"
            f"By using BuyPulse, you agree to our Privacy Policy."
        )

    def monitor_limit_reached(self, current: int, limit: int) -> str:
        if self.lang == "es":
            return f"Tienes {current}/{limit} monitores. Elimina uno desde /monitors para añadir otro."
        return f"You're at {current}/{limit} monitors. Remove one from /monitors to add a new one."

    def welcome_back(self, monitor_count: int) -> str:
        if self.lang == "es":
            return (
                f"¡Bienvenido de vuelta! Tienes {monitor_count} monitores activos.\n"
                f"Las alertas de ofertas estaban pausadas — ¿quieres reactivarlas?"
            )
        return (
            f"Welcome back! You have {monitor_count} active price monitors.\n"
            f"Deal alerts were paused — want to turn them back on?"
        )

    def fetching_price(self) -> str:
        if self.lang == "es":
            return "No tengo historial de precios para esto aún. Lo estoy buscando — vuelve en unos minutos."
        return "I don't have price history for this yet. I'm fetching it now — check back in a few minutes."

    def crawl_failed(self, platform_id: str) -> str:
        if self.lang == "es":
            return f"Lo siento, no pude obtener datos de precios para {platform_id}. Puedes intentar más tarde."
        return f"Sorry, I couldn't fetch price data for {platform_id}. You can try again later."

    def rate_limited(self) -> str:
        if self.lang == "es":
            return "¡Más despacio! Puedes consultar hasta 50 productos por día."
        return "Slow down! You can check up to 50 products per day."

    def price_alert(
        self, title: str, current: str, target: str, historical_low: str, is_all_time: bool,
    ) -> str:
        atl_note = " — this matches it!" if is_all_time else ""
        if self.lang == "es":
            atl_note_es = " — ¡es el mínimo histórico!" if is_all_time else ""
            return (
                f"¡Bajó de precio! {title} ahora está a {current}\n"
                f"Tu objetivo: {target} ✅\n"
                f"Mínimo histórico: {historical_low}{atl_note_es}"
            )
        return (
            f"Price drop! {title} is now {current}\n"
            f"Your target: {target} ✅\n"
            f"Historical low: {historical_low}{atl_note}"
        )

    def deal_push(self, title: str, current: str, original: str, context: str) -> str:
        if self.lang == "es":
            return f"{title} bajó a {current} (era {original})\n{context}"
        return f"{title} dropped to {current} (was {original})\n{context}"

    def downgrade_notice(self, new_frequency: str) -> str:
        freq_en = {"weekly": "weekly", "monthly": "monthly"}
        freq_es = {"weekly": "semanalmente", "monthly": "mensualmente"}
        f = freq_es.get(new_frequency, new_frequency) if self.lang == "es" else freq_en.get(new_frequency, new_frequency)
        if self.lang == "es":
            return f"Te enviaremos ofertas {f} en lugar de diariamente."
        return f"We'll send you deals {f} instead of daily."
