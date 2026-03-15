"""ASIN seed import and management."""

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


def _validate_asin(asin: str) -> None:
    """Validate ASIN format: 10-11 alphanumeric characters."""
    if not ASIN_PATTERN.match(asin):
        msg = f"Invalid ASIN format: '{asin}'. Must be 10-11 alphanumeric characters."
        raise ValueError(msg)


class SeedManager:
    """Import and manage ASIN seeds in the database."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def import_from_file(self, file_path: Path) -> ImportResult:
        """Import ASINs from a text file (one per line).

        Skips blank lines, strips whitespace, deduplicates within file,
        and skips ASINs already in the database.
        """
        raw_lines = file_path.read_text().splitlines()

        # Parse and validate lines
        asins: list[str] = []
        for line in raw_lines:
            asin = line.strip()
            if not asin:
                continue
            _validate_asin(asin)
            asins.append(asin)

        total = len(asins)
        unique_asins = list(dict.fromkeys(asins))

        # Find existing ASINs in DB
        if unique_asins:
            result = await self._session.execute(
                select(Product.asin).where(Product.asin.in_(unique_asins))
            )
            scalars = await _resolve(result.scalars())
            all_vals = await _resolve(scalars.all())
            existing = set(all_vals)
        else:
            existing = set()

        # Create new products and crawl tasks
        added = 0
        skipped = total - len(unique_asins)  # duplicates within file

        for asin in unique_asins:
            if asin in existing:
                skipped += 1
                continue

            product = Product(asin=asin)
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

    async def add_single(self, asin: str) -> bool:
        """Add a single ASIN. Returns True if added, False if duplicate."""
        _validate_asin(asin)

        result = await self._session.execute(
            select(Product).where(Product.asin == asin)
        )
        existing = await _resolve(result.scalar_one_or_none())
        if existing is not None:
            return False

        product = Product(asin=asin)
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
