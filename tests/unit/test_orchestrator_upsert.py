"""Tests for PriceSummary upsert and CrawlTask on-demand upsert logic."""
from cps.services.crawl_service import upsert_crawl_task
from cps.pipeline.result_store import _build_price_summary_upsert


def test_upsert_sql_contains_on_conflict():
    """PriceSummary save should use ON CONFLICT ... DO UPDATE."""
    from sqlalchemy.dialects import postgresql
    stmt = _build_price_summary_upsert(
        product_id=1,
        price_type="amazon",
        lowest_price=16900,
        lowest_date=None,
        highest_price=24900,
        highest_date=None,
        current_price=18900,
        current_date=None,
        extraction_id=1,
    )
    compiled = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "ON CONFLICT" in compiled.upper() or "on conflict" in compiled.lower()


def test_crawl_task_upsert_importable():
    """Verify the on-demand crawl upsert helper exists."""
    assert callable(upsert_crawl_task)
