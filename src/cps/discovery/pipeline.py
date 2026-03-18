"""ASIN discovery validation pipeline."""

import inspect
import re
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask, FetchRun, Product

log = structlog.get_logger()


async def _resolve(value):
    """Resolve a potentially awaitable value (handles AsyncMock compatibility)."""
    if inspect.isawaitable(value):
        return await value
    return value


_PLATFORM_VALIDATORS = {
    "amazon": re.compile(r"^[A-Z0-9]{10}$"),
}


def validate_platform_id(platform_id: str, platform: str) -> bool:
    """Validate a platform_id against platform-specific rules."""
    pattern = _PLATFORM_VALIDATORS.get(platform)
    if pattern is None:
        raise ValueError(f"Unknown platform: {platform}")
    return bool(pattern.match(platform_id))


@dataclass
class SubmitResult:
    """Summary of candidate submission."""
    submitted: int
    skipped: int
    total: int


class DiscoveryPipeline:
    """Manages product discovery: submit candidates and validate via crawl."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit_candidates(
        self,
        platform_ids: list[str],
        platform: str = "amazon",
        priority: int = 2,
    ) -> SubmitResult:
        """Import candidate platform_ids for validation crawling."""
        total = len(platform_ids)
        skipped = 0

        valid_ids: list[str] = []
        for pid in platform_ids:
            if validate_platform_id(pid, platform):
                valid_ids.append(pid)
            else:
                skipped += 1
                log.debug("invalid_platform_id", platform_id=pid, platform=platform)

        unique_ids = list(dict.fromkeys(valid_ids))
        skipped += len(valid_ids) - len(unique_ids)

        if unique_ids:
            result = await self._session.execute(
                select(Product.platform_id).where(
                    Product.platform == platform,
                    Product.platform_id.in_(unique_ids),
                )
            )
            scalars = await _resolve(result.scalars())
            all_vals = await _resolve(scalars.all())
            existing = set(all_vals)
        else:
            existing = set()

        submitted = 0
        for pid in unique_ids:
            if pid in existing:
                skipped += 1
                continue

            product = Product(platform_id=pid, platform=platform)
            self._session.add(product)
            await self._session.flush()

            task = CrawlTask(
                product_id=product.id,
                platform=platform,
                priority=priority,
                status="pending",
            )
            self._session.add(task)
            submitted += 1

        await self._session.flush()

        log.info("discovery_submitted", platform=platform, submitted=submitted, skipped=skipped, total=total)
        return SubmitResult(submitted=submitted, skipped=skipped, total=total)

    async def deactivate_no_data_products(self, platform: str = "amazon") -> int:
        """Deactivate products whose latest FetchRun has 0 points extracted."""
        stmt = (
            select(Product)
            .join(CrawlTask, CrawlTask.product_id == Product.id)
            .join(FetchRun, FetchRun.product_id == Product.id)
            .where(
                Product.platform == platform,
                Product.is_active == True,  # noqa: E712
                CrawlTask.status == "completed",
                FetchRun.points_extracted == 0,
            )
        )
        result = await self._session.execute(stmt)
        scalars = await _resolve(result.scalars())
        all_vals = await _resolve(scalars.all())
        products = list(all_vals)

        for product in products:
            product.is_active = False
            log.info("product_deactivated", platform_id=product.platform_id, reason="no_data")

        if products:
            await self._session.flush()

        return len(products)
