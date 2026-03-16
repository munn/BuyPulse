"""Track user interactions for behavior inference (spec Section 4.1 layer 3).

Records: button clicks, messages, search queries.
Queries: repeated search patterns → infer product interest.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import UserInteraction


class InteractionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        user_id: int,
        interaction_type: str,
        payload: str | None = None,
    ) -> None:
        interaction = UserInteraction(
            user_id=user_id,
            interaction_type=interaction_type,
            payload=payload,
        )
        self._session.add(interaction)
        await self._session.flush()

    async def get_repeated_searches(
        self,
        user_id: int,
        min_count: int = 3,
        days: int = 7,
    ) -> list[tuple[str, int]]:
        """Find search queries repeated >= min_count times within N days.

        Returns list of (query_text, count) tuples ordered by count desc.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self._session.execute(
            select(
                UserInteraction.payload,
                func.count().label("cnt"),
            )
            .where(
                UserInteraction.user_id == user_id,
                UserInteraction.interaction_type == "search",
                UserInteraction.payload.isnot(None),
                UserInteraction.created_at >= cutoff,
            )
            .group_by(UserInteraction.payload)
            .having(func.count() >= min_count)
            .order_by(func.count().desc())
        )
        return [(row[0], row[1]) for row in result.all()]
