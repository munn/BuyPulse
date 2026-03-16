"""Handle text messages: classify as URL/ASIN/NLP → dispatch to price lookup or search.

Per spec Section 2.2: URL regex → ASIN regex → natural language.
"""
import structlog
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_buy_keyboard, build_price_report_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates, render_price_report
from cps.bot.rate_limiter import check_rate_limit
from cps.db.models import PriceHistory, PriceSummary, Product
from cps.db.session import get_session
from cps.services.affiliate import build_product_link
from cps.services.asin_parser import InputType, parse_input
from cps.services.crawl_service import upsert_crawl_task
from cps.services.price_service import Density, analyze_price
from cps.services.search_service import SearchService
from cps.services.user_service import UserService

log = structlog.get_logger()


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main message handler — dispatch based on input type."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]
    text = update.message.text.strip()

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
        )
        await user_svc.record_interaction(user)

        # Rate limit check
        rate_state = context.bot_data.setdefault("_rate_limit_state", {})
        import time
        from cps.bot.rate_limiter import RateLimitResult
        rl_result = check_rate_limit(rate_state, update.effective_user.id, time.time())
        if rl_result != RateLimitResult.ALLOWED:
            templates = MessageTemplates(user.language)
            await update.message.reply_text(templates.rate_limited())
            await session.commit()
            return

        # Auto-detect language on first text message
        if user.last_interaction_at is None:
            ai_client = context.bot_data["ai_client"]
            detected = await ai_client.detect_language(text)
            if detected != user.language:
                await user_svc.update_language(user, detected)

        parsed = parse_input(text)

        if parsed.input_type in (InputType.URL, InputType.ASIN):
            await _handle_asin_lookup(update, context, session, user, parsed.asin, settings)
        else:
            await _handle_nlp_search(update, context, session, user, parsed.query, settings)

        await session.commit()


async def _handle_asin_lookup(update, context, session, user, asin, settings):
    """Look up product by ASIN → show price report or trigger on-demand crawl."""
    result = await session.execute(
        select(Product).where(Product.asin == asin)
    )
    product = result.scalar_one_or_none()

    if product is None:
        # Create product + trigger on-demand crawl
        product = Product(asin=asin)
        session.add(product)
        await session.flush()
        await upsert_crawl_task(session, product.id, priority=1)
        templates = MessageTemplates(user.language)
        await update.message.reply_text(templates.fetching_price())
        return

    await _send_price_report(update, session, user, product, settings)


async def _handle_nlp_search(update, context, session, user, query, settings):
    """Use AI to extract search intent → search waterfall."""
    ai_client = context.bot_data["ai_client"]
    search_query = await ai_client.extract_search_intent(query)

    search_svc = SearchService(session, settings.affiliate_tag)
    result = await search_svc.search(search_query)

    if result.product is not None:
        await _send_price_report(update, session, user, result.product, settings)
    elif result.fallback_url:
        msg = (
            "I couldn't find that exact product. "
            "Here's an Amazon search link — send me the product link from there."
            if user.language == "en" else
            "No encontré ese producto exacto. "
            "Aquí tienes un enlace de búsqueda — envíame el enlace del producto."
        )
        kb = to_telegram_markup(build_buy_keyboard(result.fallback_url))
        await update.message.reply_text(msg, reply_markup=kb)


async def _send_price_report(update, session, user, product, settings, density_override=None):
    """Build and send price report for a product."""
    # Load price summary
    ps_result = await session.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product.id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = ps_result.scalar_one_or_none()

    if summary is None or summary.current_price is None:
        # No price data — trigger crawl
        await upsert_crawl_task(session, product.id, priority=1)
        templates = MessageTemplates(user.language)
        await update.message.reply_text(templates.fetching_price())
        return

    # Load full price history for percentile calculation
    ph_result = await session.execute(
        select(PriceHistory.price_cents).where(
            PriceHistory.product_id == product.id,
            PriceHistory.price_type == "amazon",
        )
    )
    all_prices = [row[0] for row in ph_result.all()]

    # Build history tuples for trend calculation
    ph_full = await session.execute(
        select(PriceHistory.recorded_date, PriceHistory.price_cents).where(
            PriceHistory.product_id == product.id,
            PriceHistory.price_type == "amazon",
        ).order_by(PriceHistory.recorded_date)
    )
    history = [(row[0], row[1]) for row in ph_full.all()]

    analysis = analyze_price(
        current_price=summary.current_price,
        price_history=history,
        lowest_price=summary.lowest_price or summary.current_price,
        lowest_date=summary.lowest_date,
        highest_price=summary.highest_price or summary.current_price,
        highest_date=summary.highest_date,
    )

    density = Density(density_override) if density_override else Density(user.density_preference)
    msg = render_price_report(
        title=product.title or product.asin,
        analysis=analysis,
        density=density,
        language=user.language,
    )

    buy_url = build_product_link(product.asin, settings.affiliate_tag)
    kb = to_telegram_markup(
        build_price_report_keyboard(buy_url, product.asin, density.value)
    )
    await update.message.reply_text(msg, reply_markup=kb)
