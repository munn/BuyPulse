"""Onboarding handler: /start → demo product → immediate value.

Per spec Section 1: one message, real data, affiliate link, privacy notice.
"""
import structlog
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_buy_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates, render_price_report
from cps.db.models import PriceSummary, Product
from cps.db.session import get_session
from cps.services.affiliate import build_product_link
from cps.services.price_service import Density, analyze_price
from cps.services.user_service import UserService

log = structlog.get_logger()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — onboarding with demo product."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]
    tg_user = update.effective_user

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        await user_svc.record_interaction(user)

        # Auto-detect language from Telegram client language
        tg_lang = (tg_user.language_code or "")[:2].lower()
        if tg_lang in ("es",) and user.language == "en":
            await user_svc.update_language(user, "es")

        # Try to load demo product
        templates = MessageTemplates(user.language)
        demo_asin = settings.demo_asin

        result = await session.execute(
            select(Product).where(Product.platform_id == demo_asin)
        )
        product = result.scalar_one_or_none()

        if product is not None:
            # Load price summary
            ps_result = await session.execute(
                select(PriceSummary).where(
                    PriceSummary.product_id == product.id,
                    PriceSummary.price_type == "amazon",
                )
            )
            summary = ps_result.scalar_one_or_none()

            if summary and summary.current_price:
                analysis = analyze_price(
                    current_price=summary.current_price,
                    price_history=[],  # simplified for onboarding
                    lowest_price=summary.lowest_price or summary.current_price,
                    lowest_date=summary.lowest_date,
                    highest_price=summary.highest_price or summary.current_price,
                    highest_date=summary.highest_date,
                )
                price_report = render_price_report(
                    title=product.title or demo_asin,
                    analysis=analysis,
                    density=Density.STANDARD,
                    language=user.language,
                )
                buy_url = build_product_link(demo_asin, settings.affiliate_tag)
                kb = to_telegram_markup(build_buy_keyboard(buy_url))
                msg = templates.onboarding(title=product.title or demo_asin, price_report=price_report)
                await update.message.reply_text(msg, reply_markup=kb)
                await session.commit()
                return

        # Fallback: no demo data available
        msg = templates.onboarding(
            title="",
            price_report="Send me any Amazon link or tell me what you want to buy.",
        )
        await update.message.reply_text(msg)
        await session.commit()
