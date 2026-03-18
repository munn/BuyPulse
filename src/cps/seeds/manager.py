"""Product seed import and management."""

import inspect
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import CrawlTask, Product

ASIN_PATTERN = re.compile(r"^[A-Za-z0-9]{10,11}$")
DEFAULT_PRIORITY = 5


async def _resolve(value):
    """Resolve a potentially awaitable value (handles AsyncMock compatibility)."""
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass
class ImportResult:
    """Summary of a seed import operation."""

    total: int
    added: int
    skipped: int


def _validate_platform_id(platform_id: str) -> None:
    """Validate platform_id format: 10-11 alphanumeric characters."""
    if not ASIN_PATTERN.match(platform_id):
        msg = f"Invalid platform_id format: '{platform_id}'. Must be 10-11 alphanumeric characters."
        raise ValueError(msg)


class SeedManager:
    """Import and manage product seeds in the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def import_from_file(self, file_path: Path) -> ImportResult:
        """Import platform_ids from a text file (one per line).

        Skips blank lines, strips whitespace, deduplicates within file,
        and skips platform_ids already in the database.
        """
        raw_lines = file_path.read_text().splitlines()

        # Parse and validate lines
        platform_ids: list[str] = []
        for line in raw_lines:
            platform_id = line.strip()
            if not platform_id:
                continue
            _validate_platform_id(platform_id)
            platform_ids.append(platform_id)

        total = len(platform_ids)
        unique_ids = list(dict.fromkeys(platform_ids))

        # Find existing platform_ids in DB
        if unique_ids:
            result = await self._session.execute(
                select(Product.platform_id).where(Product.platform_id.in_(unique_ids))
            )
            scalars = await _resolve(result.scalars())
            all_vals = await _resolve(scalars.all())
            existing = set(all_vals)
        else:
            existing = set()

        # Create new products and crawl tasks
        added = 0
        skipped = total - len(unique_ids)  # duplicates within file

        for platform_id in unique_ids:
            if platform_id in existing:
                skipped += 1
                continue

            product = Product(platform_id=platform_id)
            self._session.add(product)
            await self._session.flush()

            task = CrawlTask(
                product_id=product.id,
                priority=DEFAULT_PRIORITY,
                status="pending",
            )
            self._session.add(task)
            added += 1

        await self._session.flush()

        return ImportResult(total=total, added=added, skipped=skipped)

    async def add_single(self, platform_id: str) -> bool:
        """Add a single platform_id. Returns True if added, False if duplicate."""
        _validate_platform_id(platform_id)

        result = await self._session.execute(
            select(Product).where(Product.platform_id == platform_id)
        )
        existing = await _resolve(result.scalar_one_or_none())
        if existing is not None:
            return False

        product = Product(platform_id=platform_id)
        self._session.add(product)
        await self._session.flush()

        task = CrawlTask(
            product_id=product.id,
            priority=DEFAULT_PRIORITY,
            status="pending",
        )
        self._session.add(task)
        await self._session.flush()

        return True
