"""Periodic job: notify users when their on-demand crawl request fails.

Runs every 10 minutes. Checks for failed crawl tasks with a requesting user.
"""
import structlog
from sqlalchemy import select
from telegram.error import Forbidden
from telegram.ext import ContextTypes

from cps.bot.messages import MessageTemplates
from cps.db.models import CrawlTask, Product, TelegramUser
from cps.db.session import get_session
from cps.services.notification_service import NotificationService
from cps.services.user_service import UserService

log = structlog.get_logger()


async def crawl_failure_notifier_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check for failed on-demand crawls and notify requesting users."""
    session_factory = context.bot_data["session_factory"]

    async with get_session(session_factory) as session:
        result = await session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "failed",
                CrawlTask.requested_by_user_id.isnot(None),
            )
        )
        failed_tasks = list(result.scalars().all())

        notification_svc = NotificationService(context.bot, session)

        for task in failed_tasks:
            user = await session.get(TelegramUser, task.requested_by_user_id)
            product = await session.get(Product, task.product_id)
            if user is None or product is None:
                continue
            if user.notification_state == "blocked":
                continue

            templates = MessageTemplates(user.language)
            try:
                await notification_svc.send(
                    telegram_id=user.telegram_id,
                    text=templates.crawl_failed(product.asin),
                    notification_type="system",
                    user_id=user.id,
                )
            except Forbidden:
                user_svc = UserService(session)
                await user_svc.mark_blocked(user)

            # Clear requested_by so we don't notify again
            task.requested_by_user_id = None

        await session.commit()
