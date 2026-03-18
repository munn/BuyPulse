"""Result storage — persists parse results to FetchRun, PriceHistory, PriceSummary.

Extracted from orchestrator.py to enable reuse by both PipelineOrchestrator
and the Worker entry point.
"""

from datetime import date

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cps.db.models import FetchRun, PriceHistory, PriceSummary
from cps.platforms.protocol import ParseResult


def _build_price_summary_upsert(
    product_id: int,
    price_type: str,
    lowest_price: int | None,
    lowest_date: date | None,
    highest_price: int | None,
    highest_date: date | None,
    current_price: int | None,
    current_date: date | None,
    extraction_id: int | None,
    source: str = "ccc_chart",
) -> object:
    """Build PostgreSQL INSERT ... ON CONFLICT DO UPDATE for PriceSummary."""
    stmt = pg_insert(PriceSummary).values(
        product_id=product_id,
        price_type=price_type,
        lowest_price=lowest_price,
        lowest_date=lowest_date,
        highest_price=highest_price,
        highest_date=highest_date,
        current_price=current_price,
        current_date=current_date,
        extraction_id=extraction_id,
        source=source,
    )
    return stmt.on_conflict_do_update(
        index_elements=["product_id", "price_type"],
        set_={
            "lowest_price": stmt.excluded.lowest_price,
            "lowest_date": stmt.excluded.lowest_date,
            "highest_price": stmt.excluded.highest_price,
            "highest_date": stmt.excluded.highest_date,
            "current_price": stmt.excluded.current_price,
            "current_date": stmt.excluded.current_date,
            "extraction_id": stmt.excluded.extraction_id,
            "source": stmt.excluded.source,
            "updated_at": func.now(),
        },
    )


async def store_results(
    session: AsyncSession,
    product_id: int,
    parse_result: ParseResult,
    chart_path: str | None = None,
    platform: str = "amazon",
) -> int:
    """Persist parse results: create FetchRun, insert PriceHistory, upsert PriceSummary.

    Returns the FetchRun ID.
    """
    run = FetchRun(
        product_id=product_id,
        chart_path=chart_path,
        status=parse_result.validation_status,
        points_extracted=parse_result.points_extracted,
        ocr_confidence=parse_result.confidence,
        validation_passed=parse_result.validation_passed,
        platform=platform,
    )
    session.add(run)
    await session.flush()

    # Store price history (skip duplicates via savepoint)
    for record in parse_result.records:
        try:
            async with session.begin_nested():
                ph = PriceHistory(
                    product_id=product_id,
                    price_type=record.price_type,
                    recorded_date=record.recorded_date,
                    price_cents=record.price_cents,
                    extraction_id=run.id,
                    source=record.source,
                )
                session.add(ph)
        except IntegrityError:
            pass  # duplicate — savepoint auto-rolled-back

    # Store price summaries (UPSERT)
    for summary in parse_result.summaries:
        stmt = _build_price_summary_upsert(
            product_id=product_id,
            price_type=summary.price_type,
            lowest_price=summary.lowest_price,
            lowest_date=summary.lowest_date,
            highest_price=summary.highest_price,
            highest_date=summary.highest_date,
            current_price=summary.current_price,
            current_date=summary.current_date,
            extraction_id=run.id,
        )
        await session.execute(stmt)

    return run.id
