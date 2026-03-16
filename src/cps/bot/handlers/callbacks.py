"""Handle all inline button callbacks.

Callback data format: "action:param1:param2"
Actions: density, alert, target, target_custom, remove_monitor,
         dismiss_cat, dismiss_asin, reengage, downgrade, clicked
"""
import structlog
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from cps.db.models import DealDismissal, NotificationLog, Product
from cps.db.session import get_session
from cps.services.monitor_service import MonitorService
from cps.services.user_service import NotificationState, UserService

log = structlog.get_logger()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries to appropriate handlers."""
    query = update.callback_query
    await query.answer()

    data = query.data
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        if data.startswith("density:"):
            await _handle_density_toggle(update, context, session, data, settings)
        elif data.startswith("alert:"):
            await _handle_alert_setup(update, context, session, data, settings)
        elif data.startswith("target:"):
            await _handle_target_selection(update, context, session, data, settings)
        elif data.startswith("target_custom:"):
            await _handle_custom_target(update, context, session, data)
        elif data.startswith("remove_monitor:"):
            await _handle_remove_monitor(update, context, session, data)
        elif data.startswith("dismiss_cat:") or data.startswith("dismiss_asin:"):
            await _handle_dismiss(update, context, session, data)
        elif data.startswith("reengage:"):
            await _handle_reengagement(update, context, session, data)
        elif data.startswith("downgrade:"):
            await _handle_downgrade_response(update, context, session, data)
        elif data.startswith("clicked:"):
            await _handle_click_tracking(session, data, update.effective_user.id)

        await session.commit()


async def _handle_density_toggle(update, context, session, data, settings):
    """Toggle price report density for current message."""
    parts = data.split(":")
    density = parts[1]
    asin = parts[2]

    from cps.bot.handlers.price_check import _send_price_report

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    # Temporarily override density for this render
    original_density = user.density_preference
    user.density_preference = density
    await _send_price_report(update.callback_query, session, user, product, settings)
    user.density_preference = original_density


async def _handle_alert_setup(update, context, session, data, settings):
    """Show target price selection buttons."""
    asin = data.split(":")[1]

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    from cps.bot.keyboards import build_target_keyboard, to_telegram_markup
    from cps.db.models import PriceHistory, PriceSummary
    from cps.services.price_service import analyze_price, suggest_targets

    ps_result = await session.execute(
        select(PriceSummary).where(
            PriceSummary.product_id == product.id,
            PriceSummary.price_type == "amazon",
        )
    )
    summary = ps_result.scalar_one_or_none()
    if summary is None:
        return

    ph_result = await session.execute(
        select(PriceHistory.price_cents).where(
            PriceHistory.product_id == product.id,
            PriceHistory.price_type == "amazon",
        )
    )
    all_prices = [row[0] for row in ph_result.all()]

    analysis = analyze_price(
        current_price=summary.current_price or 0,
        price_history=[],
        lowest_price=summary.lowest_price or 0,
        lowest_date=summary.lowest_date,
        highest_price=summary.highest_price or 0,
        highest_date=summary.highest_date,
    )
    targets = suggest_targets(analysis, all_prices)
    title = product.title or asin

    kb = to_telegram_markup(build_target_keyboard(asin, targets))
    msg = f"Set a price alert for {title}:"
    await update.callback_query.message.reply_text(msg, reply_markup=kb)


async def _handle_target_selection(update, context, session, data, settings):
    """User tapped a target price button → create monitor immediately."""
    parts = data.split(":")
    asin = parts[1]
    price_str = parts[2]

    target_price = None if price_str == "skip" else int(price_str)

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    mon_svc = MonitorService(session)
    monitor = await mon_svc.create_monitor(
        user_id=user.id,
        product_id=product.id,
        monitor_limit=user.monitor_limit,
        target_price=target_price,
    )

    if monitor is None:
        from cps.bot.messages import MessageTemplates
        templates = MessageTemplates(user.language)
        count = await mon_svc.count_active(user.id)
        await update.callback_query.message.reply_text(
            templates.monitor_limit_reached(count, user.monitor_limit)
        )
        return

    if target_price:
        from cps.services.price_service import format_price
        await update.callback_query.message.reply_text(
            f"Monitoring {product.title or asin} — alert at {format_price(target_price)}"
        )
    else:
        await update.callback_query.message.reply_text(
            f"Monitoring {product.title or asin} — no target price set"
        )


async def _handle_custom_target(update, context, session, data):
    """Prompt user to type a custom price."""
    await update.callback_query.message.reply_text(
        "Type your target price in dollars (e.g., 159.99):"
    )


async def _handle_remove_monitor(update, context, session, data):
    """Remove a monitor from /monitors list."""
    asin = data.split(":")[1]

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    result = await session.execute(select(Product).where(Product.asin == asin))
    product = result.scalar_one_or_none()
    if product is None:
        return

    mon_svc = MonitorService(session)
    removed = await mon_svc.remove_monitor(user.id, product.id)
    if removed:
        await update.callback_query.message.reply_text(f"Removed monitor for {product.title or asin}.")
    else:
        await update.callback_query.message.reply_text("Monitor not found.")


async def _handle_dismiss(update, context, session, data):
    """Dismiss deal suggestions by category or ASIN (spec Section 4.2)."""
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    if data.startswith("dismiss_cat:"):
        category = data.split(":", 1)[1]
        dismissal = DealDismissal(user_id=user.id, dismissed_category=category)
    else:
        asin = data.split(":", 1)[1]
        dismissal = DealDismissal(user_id=user.id, dismissed_asin=asin)

    session.add(dismissal)
    await session.flush()
    await update.callback_query.message.reply_text("Got it — you won't see suggestions like this again.")


async def _handle_reengagement(update, context, session, data):
    """Handle re-engagement response (spec Section 4.4)."""
    choice = data.split(":")[1]
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    if choice == "yes":
        await user_svc.transition_state(user, NotificationState.ACTIVE)
        await update.callback_query.message.reply_text("Deal alerts reactivated!")
    else:
        await update.callback_query.message.reply_text("No problem — your price monitors are still active.")


async def _handle_downgrade_response(update, context, session, data):
    """Handle downgrade notification response."""
    choice = data.split(":")[1]
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(update.effective_user.id)
    if user is None:
        return

    if choice == "keep":
        await user_svc.transition_state(user, NotificationState.ACTIVE)
        await update.callback_query.message.reply_text("Keeping daily deal alerts.")


async def _handle_click_tracking(session, data, telegram_user_id):
    """Track affiliate link clicks."""
    notification_id = data.split(":")[1]
    try:
        nid = int(notification_id)
        result = await session.execute(
            select(NotificationLog).where(NotificationLog.id == nid)
        )
        notification = result.scalar_one_or_none()
        if notification:
            notification.clicked = True
    except (ValueError, IndexError):
        pass
