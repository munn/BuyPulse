"""/monitors command — list all active monitors with current prices."""
import structlog
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_monitor_item_keyboard, to_telegram_markup
from cps.db.models import PriceSummary
from cps.db.session import get_session
from cps.services.monitor_service import MonitorService
from cps.services.price_service import format_price
from cps.services.user_service import UserService

log = structlog.get_logger()


async def monitors_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List user's active monitors with prices and [Remove] buttons."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        user_svc = UserService(session)
        user = await user_svc.get_or_create(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
        )
        await user_svc.record_interaction(user)

        mon_svc = MonitorService(session)
        monitors = await mon_svc.list_active(user.id)
        count = len(monitors)

        if count == 0:
            await update.message.reply_text(
                "You have no active monitors. Send me an Amazon link to start tracking!"
                if user.language == "en" else
                "No tienes monitores activos. ¡Envíame un enlace de Amazon para empezar!"
            )
            await session.commit()
            return

        header = f"Your monitors ({count}/{user.monitor_limit}):\n"
        lines = [header]

        for i, mon in enumerate(monitors, 1):
            product = mon.product
            title = product.title or product.asin if product else "Unknown"

            # Get current price
            ps_result = await session.execute(
                select(PriceSummary).where(
                    PriceSummary.product_id == mon.product_id,
                    PriceSummary.price_type == "amazon",
                )
            )
            summary = ps_result.scalar_one_or_none()
            price_str = format_price(summary.current_price) if summary and summary.current_price else "N/A"
            target_str = f" (target: {format_price(mon.target_price)})" if mon.target_price else " (no target)"

            lines.append(f"{i}. {title} — {price_str}{target_str}")

        msg = "\n".join(lines)
        await update.message.reply_text(msg)

        # Send individual remove buttons
        for mon in monitors:
            product = mon.product
            asin = product.asin if product else "?"
            kb = to_telegram_markup(build_monitor_item_keyboard(asin))
            title = product.title or asin if product else "?"
            await update.message.reply_text(f"  {title}", reply_markup=kb)

        await session.commit()
