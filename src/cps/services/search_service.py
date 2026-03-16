"""Three-tier search waterfall (spec Section 2.3).

Tier 1: DB fuzzy match on products.title — zero cost, instant
Tier 2: Amazon Creators API — skipped in V1 (cold-start, not yet available)
Tier 3: Fallback Amazon search link with affiliate tag
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import Product
from cps.services.affiliate import build_search_link


@dataclass(frozen=True)
class SearchResult:
    product: object | None = None  # Product ORM object or None
    source: str = ""               # "db", "api", "fallback"
    fallback_url: str | None = None


class SearchService:
    def __init__(self, session: AsyncSession, affiliate_tag: str) -> None:
        self._session = session
        self._affiliate_tag = affiliate_tag

    async def search(self, query: str) -> SearchResult:
        """Execute three-tier search waterfall."""
        # Tier 1: DB fuzzy match
        product = await self._search_db(query)
        if product is not None:
            return SearchResult(product=product, source="db")

        # Tier 2: Amazon API (V1: skip — cold-start period)

        # Tier 3: Fallback search link
        return SearchResult(
            source="fallback",
            fallback_url=build_search_link(query, self._affiliate_tag),
        )

    async def _search_db(self, query: str) -> object | None:
        """Case-insensitive ILIKE search on products.title."""
        pattern = f"%{query}%"
        result = await self._session.execute(
            select(Product)
            .where(Product.title.ilike(pattern))
            .limit(1)
        )
        return result.scalars().first()
