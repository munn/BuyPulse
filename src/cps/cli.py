"""CPS CLI entry point — Typer commands for seed, crawl, extract, and db operations."""

import asyncio
import logging
import sys
from pathlib import Path

import structlog
import typer

from cps.config import get_settings

app = typer.Typer(name="cps", help="CPS — Amazon price monitoring via CCC chart analysis")
seed_app = typer.Typer(help="ASIN seed management")
crawl_app = typer.Typer(help="CCC chart crawling")
extract_app = typer.Typer(help="Chart data extraction")
db_app = typer.Typer(help="Database operations")

bot_app = typer.Typer(help="Telegram bot operations")

app.add_typer(seed_app, name="seed")
app.add_typer(crawl_app, name="crawl")
app.add_typer(extract_app, name="extract")
app.add_typer(db_app, name="db")
app.add_typer(bot_app, name="bot")


def _configure_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structlog output."""
    if log_format == "console":
        structlog.configure(
            processors=[
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper(), logging.INFO)
            ),
        )
    else:
        structlog.configure(
            processors=[
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper(), logging.INFO)
            ),
        )


def _run_async(coro):
    """Run an async coroutine from sync CLI context."""
    return asyncio.run(coro)


# --- Seed commands ---

@seed_app.command("import")
def seed_import(
    file: Path = typer.Option(..., "--file", "-f", help="Path to text file with ASINs"),
) -> None:
    """Bulk import ASINs from a text file."""
    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    async def _do():
        from cps.db.session import create_session_factory
        from cps.seeds.manager import SeedManager

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            manager = SeedManager(session)
            result = await manager.import_from_file(file)
            await session.commit()
        typer.echo(f"{result.total} total, {result.added} added, {result.skipped} duplicates skipped")

    _run_async(_do())


@seed_app.command("add")
def seed_add(
    asin: str = typer.Argument(help="Single ASIN to add"),
) -> None:
    """Add a single ASIN."""
    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    async def _do():
        from cps.db.session import create_session_factory
        from cps.seeds.manager import SeedManager

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            manager = SeedManager(session)
            added = await manager.add_single(asin)
            await session.commit()
        if added:
            typer.echo(f"Added {asin}")
        else:
            typer.echo(f"Skipped {asin} (already exists)")

    _run_async(_do())


@seed_app.command("stats")
def seed_stats() -> None:
    """Show ASIN counts by priority tier."""
    settings = get_settings()

    async def _do():
        from sqlalchemy import func, select

        from cps.db.models import CrawlTask
        from cps.db.session import create_session_factory

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            result = await session.execute(
                select(CrawlTask.priority, func.count())
                .group_by(CrawlTask.priority)
                .order_by(CrawlTask.priority)
            )
            rows = result.all()

        typer.echo("Priority | Count")
        typer.echo("---------|------")
        for priority, count in rows:
            typer.echo(f"       {priority} | {count}")

    _run_async(_do())


# --- Crawl commands ---

@crawl_app.command("run")
def crawl_run(
    limit: int = typer.Option(10, "--limit", "-n", help="Max ASINs to crawl"),
) -> None:
    """Crawl next N pending ASINs."""
    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    async def _do():
        from cps.db.session import create_session_factory
        from cps.pipeline.orchestrator import PipelineOrchestrator

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            # Crash recovery first
            recovered = await PipelineOrchestrator.recover_stale_tasks(session)
            if recovered:
                typer.echo(f"Recovered {recovered} stale tasks")

            orchestrator = PipelineOrchestrator(
                session=session,
                data_dir=settings.data_dir,
                base_url=settings.ccc_base_url,
                rate_limit=settings.ccc_rate_limit,
            )
            summary = await orchestrator.run(limit=limit)
            await session.commit()

        typer.echo(
            f"Crawl complete: {summary['succeeded']} succeeded, "
            f"{summary['failed']} failed, {summary['total']} total"
        )

    _run_async(_do())


@crawl_app.command("status")
def crawl_status() -> None:
    """Show crawl progress report (T036)."""
    settings = get_settings()

    async def _do():
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import func, select

        from cps.db.models import CrawlTask, ExtractionRun, Product
        from cps.db.session import create_session_factory

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            total = await session.scalar(select(func.count()).select_from(Product))
            status_counts = await session.execute(
                select(CrawlTask.status, func.count())
                .group_by(CrawlTask.status)
            )
            rows = status_counts.all()

            # Throughput: completed in last 24h
            cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
            throughput = await session.scalar(
                select(func.count()).select_from(CrawlTask)
                .where(
                    CrawlTask.status == "completed",
                    CrawlTask.completed_at >= cutoff_24h,
                )
            )

            # Extraction quality rate
            total_runs = await session.scalar(
                select(func.count()).select_from(ExtractionRun)
            )
            passed_runs = await session.scalar(
                select(func.count()).select_from(ExtractionRun)
                .where(ExtractionRun.validation_passed == True)  # noqa: E712
            )

        typer.echo(f"Total products: {total}")
        typer.echo("")
        typer.echo("Status      | Count")
        typer.echo("------------|------")
        for status, count in rows:
            typer.echo(f"{status:12s}| {count}")

        typer.echo("")
        typer.echo(f"Throughput (24h): {throughput or 0} completed")
        if total_runs and total_runs > 0:
            quality = (passed_runs or 0) / total_runs * 100
            typer.echo(f"Extraction quality: {quality:.1f}% ({passed_runs}/{total_runs})")
        else:
            typer.echo("Extraction quality: N/A (no extractions yet)")

    _run_async(_do())


@crawl_app.command("retry-failed")
def crawl_retry_failed() -> None:
    """Reset failed tasks to pending for retry."""
    settings = get_settings()

    async def _do():
        from sqlalchemy import update

        from cps.db.models import CrawlTask
        from cps.db.session import create_session_factory

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            result = await session.execute(
                update(CrawlTask)
                .where(CrawlTask.status == "failed")
                .values(status="pending", error_message=None, retry_count=0)
            )
            await session.commit()

        typer.echo(f"Reset {result.rowcount} failed tasks to pending")

    _run_async(_do())


# --- Extract commands ---

@extract_app.command("run")
def extract_run(
    asin: str = typer.Option(..., "--asin", help="ASIN to re-extract"),
) -> None:
    """Re-extract data from stored PNG for a single ASIN."""
    typer.echo(f"Re-extracting data for {asin}...")
    typer.echo("(Re-extraction from stored PNGs — not yet implemented)")


@extract_app.command("batch")
def extract_batch(
    limit: int = typer.Option(10, "--limit", "-n", help="Max ASINs to re-extract"),
) -> None:
    """Batch re-extract from stored PNGs."""
    typer.echo(f"Batch re-extracting up to {limit} ASINs...")
    typer.echo("(Batch re-extraction — not yet implemented)")


# --- DB commands ---

@db_app.command("init")
def db_init() -> None:
    """Run Alembic migrations."""
    import subprocess

    typer.echo("Running database migrations...")
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        typer.echo("Migrations complete")
    else:
        typer.echo(f"Migration failed: {result.stderr}", err=True)
        raise typer.Exit(1)


@db_app.command("stats")
def db_stats() -> None:
    """Show row counts and disk usage (T037)."""
    settings = get_settings()

    async def _do():
        from sqlalchemy import func, select, text

        from cps.db.models import (
            CrawlTask,
            DailySnapshot,
            ExtractionRun,
            PriceHistory,
            PriceSummary,
            Product,
        )
        from cps.db.session import create_session_factory

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            tables = [
                ("products", Product),
                ("extraction_runs", ExtractionRun),
                ("price_history", PriceHistory),
                ("price_summary", PriceSummary),
                ("daily_snapshots", DailySnapshot),
                ("crawl_tasks", CrawlTask),
            ]

            typer.echo("Table             | Rows")
            typer.echo("------------------|----------")
            for name, model in tables:
                try:
                    count = await session.scalar(
                        select(func.count()).select_from(model)
                    )
                    typer.echo(f"{name:18s}| {count or 0:>8}")
                except Exception:
                    typer.echo(f"{name:18s}| (error)")

            # DB disk usage
            try:
                result = await session.execute(
                    text("SELECT pg_database_size(current_database())")
                )
                db_size_bytes = result.scalar()
                db_size_mb = (db_size_bytes or 0) / (1024 * 1024)
                typer.echo(f"\nDatabase size: {db_size_mb:.1f} MB")
            except Exception:
                typer.echo("\nDatabase size: (unable to query)")

        # PNG storage size
        data_dir = settings.data_dir / "charts"
        if data_dir.exists():
            png_size = sum(f.stat().st_size for f in data_dir.rglob("*.png"))
            png_mb = png_size / (1024 * 1024)
            typer.echo(f"PNG storage: {png_mb:.1f} MB")
        else:
            typer.echo("PNG storage: 0.0 MB (no charts yet)")

    _run_async(_do())


@db_app.command("check-partitions")
def db_check_partitions() -> None:
    """Check if current year partitions exist (T038)."""
    settings = get_settings()
    import datetime

    current_year = datetime.date.today().year

    async def _do():
        from sqlalchemy import text

        from cps.db.session import create_session_factory

        factory = create_session_factory(settings.database_url)
        async with factory() as session:
            missing = []
            for table_base in ["price_history", "daily_snapshots"]:
                partition_name = f"{table_base}_{current_year}"
                result = await session.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_name = :name"
                    ),
                    {"name": partition_name},
                )
                if result.scalar() is None:
                    missing.append(partition_name)

        if missing:
            typer.echo("WARNING: Missing partitions for current year!", err=True)
            for name in missing:
                typer.echo(f"  - {name}", err=True)
            typer.echo(
                f"\nCreate them via: alembic revision -m 'add {current_year} partitions'",
                err=True,
            )
            raise typer.Exit(1)
        else:
            typer.echo(f"All partitions for {current_year} are present.")

    _run_async(_do())


@bot_app.command()
def run():
    """Start the Telegram bot (long-running process)."""
    from cps.bot.app import create_bot_app

    settings = get_settings()
    _configure_logging(settings.log_level, settings.log_format)

    if not settings.telegram_bot_token:
        typer.echo("Error: TELEGRAM_BOT_TOKEN not set", err=True)
        raise typer.Exit(1)

    application = create_bot_app(settings)
    application.run_polling()


if __name__ == "__main__":
    app()
