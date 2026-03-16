"""Three-layer deal detection (spec Section 4.1).

Layer 1: Related — products in same category as user's monitors at good prices
Layer 2: Global best — all-time lows across popular products
Layer 3: Behavior-inferred — products matching repeated search patterns
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import PriceMonitor, PriceSummary, Product


@dataclass(frozen=True)
class Deal:
    asin: str
    title: str
    category: str | None
    current: int     # cents
    was: int         # highest price, cents


class DealService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_related(self, user_id: int, limit: int = 5) -> list[Deal]:
        """Layer 1: Find deals in categories the user monitors."""
        # Get user's monitored categories
        mon_result = await self._session.execute(
            select(Product.category).join(PriceMonitor).where(
                PriceMonitor.user_id == user_id,
                PriceMonitor.is_active == True,  # noqa: E712
                Product.category.isnot(None),
            ).distinct()
        )
        categories = [row[0] for row in mon_result.all()]
        if not categories:
            return []

        # Get monitored product IDs to exclude
        mon_pids = await self._session.execute(
            select(PriceMonitor.product_id).where(
                PriceMonitor.user_id == user_id,
            )
        )
        exclude_ids = {row[0] for row in mon_pids.all()}

        # Find products in same categories near historical low
        result = await self._session.execute(
            select(Product, PriceSummary).join(PriceSummary).where(
                Product.category.in_(categories),
                PriceSummary.price_type == "amazon",
                PriceSummary.current_price.isnot(None),
                PriceSummary.lowest_price.isnot(None),
                ~Product.id.in_(exclude_ids) if exclude_ids else True,
            ).limit(limit)
        )
        deals = []
        for product, ps in result.all():
            if ps.current_price <= ps.lowest_price * 1.1:  # within 10% of low
                deals.append(Deal(
                    asin=product.asin,
                    title=product.title or product.asin,
                    category=product.category,
                    current=ps.current_price,
                    was=ps.highest_price or ps.current_price,
                ))
        return deals[:limit]

    async def find_global_best(self, limit: int = 5) -> list[Deal]:
        """Layer 2: All-time lows across any product."""
        result = await self._session.execute(
            select(Product, PriceSummary).join(PriceSummary).where(
                PriceSummary.price_type == "amazon",
                PriceSummary.current_price.isnot(None),
                PriceSummary.lowest_price.isnot(None),
                PriceSummary.current_price <= PriceSummary.lowest_price,
            ).limit(limit)
        )
        return [
            Deal(
                asin=p.asin, title=p.title or p.asin,
                category=p.category,
                current=ps.current_price, was=ps.highest_price or ps.current_price,
            )
            for p, ps in result.all()
        ]

    async def find_by_search_pattern(
        self, search_query: str, limit: int = 3,
    ) -> list[Deal]:
        """Layer 3: Find products matching a search pattern at good prices."""
        escaped = search_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        result = await self._session.execute(
            select(Product, PriceSummary).join(PriceSummary).where(
                Product.title.ilike(pattern),
                PriceSummary.price_type == "amazon",
                PriceSummary.current_price.isnot(None),
                PriceSummary.lowest_price.isnot(None),
            ).limit(limit)
        )
        deals = []
        for p, ps in result.all():
            if ps.current_price <= ps.lowest_price * 1.15:  # within 15% of low
                deals.append(Deal(
                    asin=p.asin, title=p.title or p.asin,
                    category=p.category,
                    current=ps.current_price,
                    was=ps.highest_price or ps.current_price,
                ))
        return deals[:limit]

    @staticmethod
    def filter_dismissed(
        deals: list[Deal],
        dismissed_categories: set[str] | None = None,
        dismissed_asins: set[str] | None = None,
    ) -> list[Deal]:
        """Remove deals the user has dismissed."""
        result = []
        for d in deals:
            if dismissed_categories and d.category in dismissed_categories:
                continue
            if dismissed_asins and d.asin in dismissed_asins:
                continue
            result.append(d)
        return result
