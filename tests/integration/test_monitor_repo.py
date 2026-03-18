"""Integration tests for monitor DB operations."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import Product, TelegramUser
from cps.services.monitor_service import MonitorService
from cps.services.user_service import UserService


class TestMonitorService:
    async def _setup_user_and_product(self, session: AsyncSession):
        user_svc = UserService(session)
        user = await user_svc.get_or_create(telegram_id=88888)
        product = Product(platform_id="B0TESTMON1")
        session.add(product)
        await session.flush()
        return user, product

    async def test_create_monitor(self, db_session: AsyncSession):
        user, product = await self._setup_user_and_product(db_session)
        svc = MonitorService(db_session)
        monitor = await svc.create_monitor(user.id, product.id, target_price=16900)
        assert monitor is not None
        assert monitor.target_price == 16900

    async def test_20_limit_enforcement(self, db_session: AsyncSession):
        user_svc = UserService(db_session)
        user = await user_svc.get_or_create(telegram_id=88887)
        svc = MonitorService(db_session)

        # Create 20 products + monitors
        for i in range(20):
            p = Product(platform_id=f"B0LMT{i:05d}")
            db_session.add(p)
            await db_session.flush()
            await svc.create_monitor(user.id, p.id)

        # 21st should fail
        extra = Product(platform_id="B0LMTEXTRA")
        db_session.add(extra)
        await db_session.flush()
        result = await svc.create_monitor(user.id, extra.id)
        assert result is None

    async def test_remove_monitor(self, db_session: AsyncSession):
        user, product = await self._setup_user_and_product(db_session)
        svc = MonitorService(db_session)
        await svc.create_monitor(user.id, product.id)
        assert await svc.remove_monitor(user.id, product.id) is True
        assert await svc.count_active(user.id) == 0

    async def test_duplicate_monitor_reactivates(self, db_session: AsyncSession):
        user, product = await self._setup_user_and_product(db_session)
        svc = MonitorService(db_session)
        m1 = await svc.create_monitor(user.id, product.id, target_price=100)
        await svc.remove_monitor(user.id, product.id)
        m2 = await svc.create_monitor(user.id, product.id, target_price=200)
        assert m2.is_active is True
        assert m2.target_price == 200
