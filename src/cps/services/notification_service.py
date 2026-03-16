"""Notification dispatch: send Telegram messages, log them, handle blocked users.

Per spec Section 7.3: Forbidden → mark blocked, stop all sends.
Concurrency limited to 30 concurrent sends (Telegram API limit).
"""
import asyncio

import structlog
from telegram import Bot, InlineKeyboardMarkup

from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import NotificationLog

log = structlog.get_logger()

# Lazy-initialized per event loop to avoid binding at import time
_send_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _send_semaphore
    if _send_semaphore is None:
        _send_semaphore = asyncio.Semaphore(30)
    return _send_semaphore


class NotificationService:
    def __init__(self, bot: Bot, session: AsyncSession) -> None:
        self._bot = bot
        self._session = session

    async def send(
        self,
        telegram_id: int,
        text: str,
        notification_type: str,
        user_id: int = 0,
        reply_markup: InlineKeyboardMarkup | None = None,
        product_id: int | None = None,
        affiliate_tag: str | None = None,
    ) -> bool:
        """Send a Telegram message and log it.

        Raises Forbidden if user blocked the bot (caller must handle).
        Returns True on success.
        """
        async with _get_semaphore():
            await self._bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=reply_markup,
            )

        # Log notification
        log_entry = NotificationLog(
            user_id=user_id,
            product_id=product_id,
            notification_type=notification_type,
            message_text=text[:1000],
            affiliate_tag=affiliate_tag,
        )
        self._session.add(log_entry)

        log.info("notification_sent", telegram_id=telegram_id, type=notification_type)
        return True
