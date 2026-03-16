"""Monitor CRUD with 20-limit enforcement and 24h notification cooldown.

Per spec Section 3.2:
- 20 free monitors per user
- 24h notification cooldown per (user, product) pair
- last_notified_at is the cooldown clock
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import PriceMonitor

_COOLDOWN_HOURS = 24


class MonitorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_monitor(
        self,
        user_id: int,
        product_id: int,
        monitor_limit: int = 20,
        target_price: int | None = None,
    ) -> PriceMonitor | None:
        """Create a new monitor. Returns None if at limit or already exists."""
        # Check count
        count_result = await self._session.execute(
            select(func.count()).select_from(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
            )
        )
        if count_result.scalar_one() >= monitor_limit:
            return None

        # Check if already monitoring this product
        existing_result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.product_id == product_id,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            # Re-activate if was deactivated
            if not existing.is_active:
                existing.is_active = True
                existing.target_price = target_price
                await self._session.flush()
            return existing

        monitor = PriceMonitor(
            user_id=user_id,
            product_id=product_id,
            target_price=target_price,
        )
        self._session.add(monitor)
        await self._session.flush()
        return monitor

    async def remove_monitor(self, user_id: int, product_id: int) -> bool:
        """Deactivate a monitor. Returns False if not found."""
        result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.product_id == product_id,
            )
        )
        monitor = result.scalar_one_or_none()
        if monitor is None:
            return False
        monitor.is_active = False
        await self._session.flush()
        return True

    async def list_active(self, user_id: int) -> list[PriceMonitor]:
        result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
            ).order_by(PriceMonitor.created_at)
        )
        return list(result.scalars().all())

    async def count_active(self, user_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    async def get_monitors_for_product(self, product_id: int) -> list[PriceMonitor]:
        """All active monitors for a product (for price alert dispatch)."""
        result = await self._session.execute(
            select(PriceMonitor).where(
                PriceMonitor.product_id == product_id,
                PriceMonitor.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def is_cooldown_active(last_notified_at: datetime | None) -> bool:
        """Check if 24h notification cooldown is still active."""
        if last_notified_at is None:
            return False
        return datetime.now(timezone.utc) - last_notified_at < timedelta(hours=_COOLDOWN_HOURS)

    async def mark_notified(self, monitor: PriceMonitor) -> None:
        """Update last_notified_at after sending a price alert."""
        monitor.last_notified_at = datetime.now(timezone.utc)
        await self._session.flush()
