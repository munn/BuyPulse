"""Periodic job: check monitored ASINs for price drops → notify users.

Runs every 5 minutes via JobQueue. For each product with active monitors:
1. Get latest price from price_summary
2. Compare against each monitor's target_price
3. If current <= target AND cooldown expired → send price alert
"""
import structlog
from sqlalchemy import distinct, select
from telegram.error import Forbidden
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_buy_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates
from cps.db.models import PriceMonitor, PriceSummary, Product, TelegramUser
from cps.db.session import get_session
from cps.services.affiliate import build_product_link
from cps.services.monitor_service import MonitorService
from cps.services.notification_service import NotificationService
from cps.services.price_service import format_price
from cps.services.user_service import UserService

log = structlog.get_logger()


async def price_checker_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every 5 minutes."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        # Get all products with active monitors
        result = await session.execute(
            select(distinct(PriceMonitor.product_id)).where(
                PriceMonitor.is_active == True,  # noqa: E712
                PriceMonitor.target_price.isnot(None),
            )
        )
        product_ids = [row[0] for row in result.all()]

        for product_id in product_ids:
            try:
                await _check_product_monitors(
                    session, context.bot, product_id, settings
                )
            except Exception as exc:
                log.error("price_check_error", product_id=product_id, error=str(exc))

        await session.commit()

    log.info("price_checker_complete", products_checked=len(product_ids))


async def _check_product_monitors(session, bot, product_id, settings):
    """Check all monitors for a single product."""
    # Get current price
    ps_result = await session.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product_id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = ps_result.scalar_one_or_none()
    if summary is None or summary.current_price is None:
        return

    current_price = summary.current_price

    # Get product info
    product = await session.get(Product, product_id)
    if product is None:
        return

    # Get all active monitors with target at or above current price
    mon_result = await session.execute(
        select(PriceMonitor).where(
            PriceMonitor.product_id == product_id,
            PriceMonitor.is_active == True,  # noqa: E712
            PriceMonitor.target_price >= current_price,
        )
    )
    monitors = list(mon_result.scalars().all())

    mon_svc = MonitorService(session)
    notification_svc = NotificationService(bot, session)

    # All-time low bypasses cooldown
    is_all_time_low = current_price <= (summary.lowest_price or current_price)

    for monitor in monitors:
        if MonitorService.is_cooldown_active(monitor.last_notified_at) and not is_all_time_low:
            continue

        # Get user
        user = await session.get(TelegramUser, monitor.user_id)
        if user is None or user.notification_state == "blocked":
            continue

        # Build alert message
        templates = MessageTemplates(user.language)
        is_all_time = current_price <= (summary.lowest_price or current_price)
        msg = templates.price_alert(
            title=product.title or product.asin,
            current=format_price(current_price),
            target=format_price(monitor.target_price),
            historical_low=format_price(summary.lowest_price or current_price),
            is_all_time=is_all_time,
        )

        buy_url = build_product_link(product.asin, settings.affiliate_tag)
        kb = to_telegram_markup(build_buy_keyboard(buy_url))

        try:
            await notification_svc.send(
                telegram_id=user.telegram_id,
                text=msg,
                notification_type="price_alert",
                user_id=user.id,
                reply_markup=kb,
                product_id=product_id,
                affiliate_tag=settings.affiliate_tag,
            )
            await mon_svc.mark_notified(monitor)
        except Forbidden:
            user_svc = UserService(session)
            await user_svc.mark_blocked(user)
            log.warning("user_blocked", telegram_id=user.telegram_id)
