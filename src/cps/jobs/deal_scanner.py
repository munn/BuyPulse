"""Periodic job: detect deals → push to eligible users.

Runs every hour. Respects adaptive push frequency and dismissals.
"""
import structlog
from sqlalchemy import select
from telegram.error import Forbidden
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_deal_push_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates
from cps.db.models import DealDismissal, TelegramUser
from cps.db.session import get_session
from cps.services.affiliate import build_product_link
from cps.services.deal_service import Deal, DealService
from cps.services.notification_service import NotificationService
from cps.services.price_service import format_price
from cps.services.user_service import NotificationState, UserService

log = structlog.get_logger()


async def deal_scanner_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every hour."""
    settings = context.bot_data["settings"]
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        deal_svc = DealService(session)

        # Find global best deals
        global_deals = await deal_svc.find_global_best(limit=10)

        # Get eligible users (pushable states)
        pushable_states = [s.value for s in NotificationState if s.is_pushable]
        user_result = await session.execute(
            select(TelegramUser).where(
                TelegramUser.notification_state.in_(pushable_states)
            )
        )
        users = list(user_result.scalars().all())

        notification_svc = NotificationService(context.bot, session)
        sent_count = 0

        for user in users:
            try:
                await _push_deals_to_user(
                    session, notification_svc, deal_svc,
                    user, global_deals, settings,
                )
                sent_count += 1
            except Forbidden:
                user_svc = UserService(session)
                await user_svc.mark_blocked(user)
            except Exception as exc:
                log.error("deal_push_error", user_id=user.id, error=str(exc))

        await session.commit()
    log.info("deal_scanner_complete", users=len(users), sent=sent_count)


async def _push_deals_to_user(session, notification_svc, deal_svc, user, global_deals, settings):
    """Push best deal to a single user, respecting dismissals."""
    # Get user's dismissed categories and ASINs
    dismiss_result = await session.execute(
        select(DealDismissal).where(DealDismissal.user_id == user.id)
    )
    dismissals = list(dismiss_result.scalars().all())
    dismissed_cats = {d.dismissed_category for d in dismissals if d.dismissed_category}
    dismissed_asins = {d.dismissed_asin for d in dismissals if d.dismissed_asin}

    # Try all three layers
    all_deals: list[Deal] = []

    # Layer 1: Related
    related = await deal_svc.find_related(user.id, limit=3)
    all_deals.extend(related)

    # Layer 2: Global best
    all_deals.extend(global_deals)

    # Filter dismissed
    filtered = DealService.filter_dismissed(all_deals, dismissed_cats, dismissed_asins)
    if not filtered:
        return

    # Pick the best deal (first one)
    deal = filtered[0]
    templates = MessageTemplates(user.language)
    buy_url = build_product_link(deal.asin, settings.affiliate_tag)

    pct = round((deal.current / deal.was - 1) * 100) if deal.was else 0
    context_msg = f"Near historical low — only {abs(pct)}% above." if pct < 0 else "At historical low!"
    msg = templates.deal_push(
        title=deal.title,
        current=format_price(deal.current),
        original=format_price(deal.was),
        context=context_msg,
    )
    kb = to_telegram_markup(
        build_deal_push_keyboard(buy_url, deal.asin, deal.category)
    )

    await notification_svc.send(
        telegram_id=user.telegram_id,
        text=msg,
        notification_type="deal_push",
        user_id=user.id,
        reply_markup=kb,
        affiliate_tag=settings.affiliate_tag,
    )
