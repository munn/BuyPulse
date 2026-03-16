"""Periodic job: manage adaptive push frequency (spec Section 4.3).

Runs every hour. Checks last_interaction_at for each active user:
- 7 days idle → degrade to weekly
- 21 days idle → degrade to monthly
- 51 days idle → stop pushing
"""
import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from telegram.error import Forbidden
from telegram.ext import ContextTypes

from cps.bot.keyboards import build_downgrade_keyboard, to_telegram_markup
from cps.bot.messages import MessageTemplates
from cps.db.models import TelegramUser
from cps.db.session import get_session
from cps.services.notification_service import NotificationService
from cps.services.user_service import NotificationState, UserService

log = structlog.get_logger()

_DEGRADE_TO_WEEKLY_DAYS = 7
_DEGRADE_TO_MONTHLY_DAYS = 21
_STOP_DAYS = 51


async def engagement_manager_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called by JobQueue every hour."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        now = datetime.now(timezone.utc)
        user_svc = UserService(session)
        notification_svc = NotificationService(context.bot, session)

        # Find users to potentially downgrade (ACTIVE or already DEGRADED)
        degradable_states = [
            NotificationState.ACTIVE.value,
            NotificationState.DEGRADED_WEEKLY.value,
            NotificationState.DEGRADED_MONTHLY.value,
        ]
        result = await session.execute(
            select(TelegramUser).where(
                TelegramUser.notification_state.in_(degradable_states),
                TelegramUser.last_interaction_at.isnot(None),
                TelegramUser.last_interaction_at < now - timedelta(days=_DEGRADE_TO_WEEKLY_DAYS),
            )
        )
        users_to_degrade = list(result.scalars().all())

        for user in users_to_degrade:
            idle_days = (now - user.last_interaction_at).days if user.last_interaction_at else 0
            current_state = NotificationState(user.notification_state)

            try:
                if idle_days >= _STOP_DAYS and current_state == NotificationState.DEGRADED_MONTHLY:
                    await user_svc.transition_state(user, NotificationState.STOPPED)
                    log.info("user_stopped", user_id=user.id, idle_days=idle_days)
                elif idle_days >= _DEGRADE_TO_MONTHLY_DAYS and current_state == NotificationState.DEGRADED_WEEKLY:
                    await user_svc.transition_state(user, NotificationState.DEGRADED_MONTHLY)
                    templates = MessageTemplates(user.language)
                    kb = to_telegram_markup(build_downgrade_keyboard("monthly"))
                    await notification_svc.send(
                        telegram_id=user.telegram_id,
                        text=templates.downgrade_notice("monthly"),
                        notification_type="system",
                        reply_markup=kb,
                        user_id=user.id,
                    )
                elif idle_days >= _DEGRADE_TO_WEEKLY_DAYS and current_state == NotificationState.ACTIVE:
                    await user_svc.transition_state(user, NotificationState.DEGRADED_WEEKLY)
                    templates = MessageTemplates(user.language)
                    kb = to_telegram_markup(build_downgrade_keyboard("weekly"))
                    await notification_svc.send(
                        telegram_id=user.telegram_id,
                        text=templates.downgrade_notice("weekly"),
                        notification_type="system",
                        reply_markup=kb,
                        user_id=user.id,
                    )
            except Forbidden:
                await user_svc.mark_blocked(user)
            except Exception as exc:
                log.error("engagement_error", user_id=user.id, error=str(exc))

        await session.commit()
    log.info("engagement_check_complete", checked=len(users_to_degrade))
