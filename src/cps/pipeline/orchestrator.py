"""Pipeline orchestrator — batch processing with auto-recovery state machine."""

import asyncio
import enum
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from cps.alerts.email import AlertService
from cps.crawler.downloader import (
    BlockedError,
    CccDownloader,
    DownloadError,
    RateLimitError,
    ServerError,
)
from cps.crawler.storage import PngStorage
from cps.db.models import CrawlTask, ExtractionRun, PriceHistory, PriceSummary, Product
from cps.extractor.ocr_reader import OcrReader
from cps.extractor.pixel_analyzer import PixelAnalyzer
from cps.pipeline.validator import Validator

log = structlog.get_logger()


class RecoveryState(enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    RECOVERING_1 = "recovering_1"
    PAUSED_2 = "paused_2"
    RECOVERING_2 = "recovering_2"
    PAUSED_3 = "paused_3"
    RECOVERING_3 = "recovering_3"
    STOPPED = "stopped"


# State transition: wait durations and next states
_RECOVERY_TRANSITIONS = {
    RecoveryState.PAUSED: (3600, RecoveryState.RECOVERING_1),        # 1h
    RecoveryState.PAUSED_2: (21600, RecoveryState.RECOVERING_2),     # 6h
    RecoveryState.PAUSED_3: (86400, RecoveryState.RECOVERING_3),     # 24h
}

_FAILURE_TRANSITIONS = {
    RecoveryState.RUNNING: RecoveryState.PAUSED,
    RecoveryState.RECOVERING_1: RecoveryState.PAUSED_2,
    RecoveryState.RECOVERING_2: RecoveryState.PAUSED_3,
    RecoveryState.RECOVERING_3: RecoveryState.STOPPED,
}

CONSECUTIVE_FAILURE_THRESHOLD = 50


def _build_price_summary_upsert(
    product_id: int,
    price_type: str,
    lowest_price: int | None,
    lowest_date: object | None,
    highest_price: int | None,
    highest_date: object | None,
    current_price: int | None,
    current_date: object | None,
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


class PipelineOrchestrator:
    """Batch-process CCC chart downloads with auto-recovery."""

    def __init__(
        self,
        session: AsyncSession,
        data_dir: Path,
        base_url: str,
        rate_limit: float = 1.0,
        alert_service: AlertService | None = None,
    ) -> None:
        self._session = session
        self._downloader = CccDownloader(base_url=base_url, rate_limit=rate_limit)
        self._storage = PngStorage(data_dir=data_dir)
        self._pixel_analyzer = PixelAnalyzer()
        self._ocr_reader = OcrReader()
        self._validator = Validator()
        self._alert_service = alert_service

        self._state = RecoveryState.RUNNING
        self._consecutive_failures = 0

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    async def run(self, limit: int = 10) -> dict:
        """Process up to `limit` pending crawl tasks.

        Returns summary dict with counts.
        """
        # Fetch pending tasks ordered by priority
        result = await self._session.execute(
            select(CrawlTask)
            .where(CrawlTask.status == "pending")
            .order_by(CrawlTask.priority, CrawlTask.scheduled_at)
            .limit(limit)
        )
        tasks = list(result.scalars().all())

        succeeded = 0
        failed = 0

        for task in tasks:
            if self._state == RecoveryState.STOPPED:
                log.warning("pipeline_stopped", remaining=len(tasks) - succeeded - failed)
                break

            # Check if we need to pause
            if self._state in _FAILURE_TRANSITIONS and self._consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
                await self._transition_to_failure()
                if self._state == RecoveryState.STOPPED:
                    break
                # Wait for recovery (in tests, this is mocked)
                wait_secs, next_state = _RECOVERY_TRANSITIONS[self._state]
                log.info("recovery_waiting", state=self._state.value, wait_secs=wait_secs)
                await asyncio.sleep(wait_secs)
                self._state = next_state
                self._consecutive_failures = 0
                log.info("recovery_resuming", state=self._state.value)

            success = await self._process_one(task)
            if success:
                succeeded += 1
                self._consecutive_failures = 0
                if self._state != RecoveryState.RUNNING:
                    self._state = RecoveryState.RUNNING
                    log.info("recovery_success", msg="Back to full speed")
            else:
                failed += 1
                self._consecutive_failures += 1

        return {"succeeded": succeeded, "failed": failed, "total": len(tasks)}

    async def _process_one(self, task: CrawlTask) -> bool:
        """Process a single crawl task. Returns True on success."""
        product = await self._session.get(Product, task.product_id)
        if product is None:
            log.error("product_not_found", product_id=task.product_id)
            return False

        asin = product.asin

        # Mark in progress
        task.status = "in_progress"
        task.started_at = datetime.now(timezone.utc)
        await self._session.flush()

        try:
            # Download chart
            png_bytes = await self._downloader.download(asin)

            # Save PNG
            chart_path = self._storage.save(asin, png_bytes)

            # Extract data
            pixel_data = self._pixel_analyzer.analyze(chart_path)
            ocr_result = self._ocr_reader.read(chart_path)

            # Count total data points
            total_points = sum(len(pts) for pts in pixel_data.values())

            # Build OCR comparison data for validation
            ocr_compare: dict[str, dict[str, int]] = {}
            for price_type, legend_vals in ocr_result.legend.items():
                ocr_compare[price_type] = {}
                for key, val in legend_vals.items():
                    if val and val.startswith("$"):
                        try:
                            cents = int(float(val.replace("$", "").replace(",", "")) * 100)
                            ocr_compare[price_type][key] = cents
                        except (ValueError, TypeError):
                            pass

            # Validate
            pixel_summary: dict[str, dict[str, int]] = {}
            for price_type, points in pixel_data.items():
                if points:
                    prices = [p for _, p in points]
                    pixel_summary[price_type] = {
                        "lowest": min(prices),
                        "highest": max(prices),
                        "current": prices[-1],
                    }

            validation = self._validator.validate(pixel_summary, ocr_compare)

            # Create extraction run
            run = ExtractionRun(
                product_id=product.id,
                chart_path=str(chart_path),
                status=validation.status,
                points_extracted=total_points,
                ocr_confidence=ocr_result.confidence,
                validation_passed=validation.passed,
            )
            self._session.add(run)
            await self._session.flush()

            # Store price history (skip duplicates via savepoint)
            for price_type, points in pixel_data.items():
                for recorded_date, price_cents in points:
                    try:
                        async with self._session.begin_nested():
                            ph = PriceHistory(
                                product_id=product.id,
                                price_type=price_type,
                                recorded_date=recorded_date,
                                price_cents=price_cents,
                                extraction_id=run.id,
                            )
                            self._session.add(ph)
                    except Exception:
                        pass  # duplicate — savepoint auto-rolled-back

            # Store price summary (UPSERT — update on re-crawl)
            for price_type, summary in pixel_summary.items():
                pts = pixel_data.get(price_type, [])
                dates = [d for d, _ in pts] if pts else []
                stmt = _build_price_summary_upsert(
                    product_id=product.id,
                    price_type=price_type,
                    lowest_price=summary.get("lowest"),
                    lowest_date=min(dates) if dates else None,
                    highest_price=summary.get("highest"),
                    highest_date=max(dates) if dates else None,
                    current_price=summary.get("current"),
                    current_date=dates[-1] if dates else None,
                    extraction_id=run.id,
                )
                await self._session.execute(stmt)

            # Update task
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            task.total_crawls += 1
            task.next_crawl_at = datetime.now(timezone.utc) + timedelta(days=7)
            await self._session.flush()

            log.info("crawl_success", asin=asin, points=total_points)
            return True

        except RateLimitError:
            task.status = "pending"
            task.error_message = "Rate limited (429)"
            await self._session.flush()
            log.warning("rate_limited", asin=asin)
            return False

        except BlockedError:
            task.status = "failed"
            task.error_message = "Blocked (403)"
            await self._session.flush()
            log.error("blocked", asin=asin)
            return False

        except (ServerError, DownloadError) as exc:
            task.retry_count += 1
            if task.retry_count >= task.max_retries:
                task.status = "failed"
            else:
                task.status = "pending"
            task.error_message = str(exc)
            await self._session.flush()
            log.error("download_error", asin=asin, error=str(exc))
            return False

        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)
            await self._session.flush()
            log.error("unexpected_error", asin=asin, error=str(exc))
            return False

    async def _transition_to_failure(self) -> None:
        """Transition to the next failure state."""
        next_state = _FAILURE_TRANSITIONS.get(self._state)
        if next_state is None:
            return

        old_state = self._state
        self._state = next_state
        self._consecutive_failures = 0

        log.warning(
            "state_transition",
            from_state=old_state.value,
            to_state=next_state.value,
        )

        if self._alert_service:
            severity = "CRITICAL" if next_state == RecoveryState.STOPPED else "WARNING"
            await self._alert_service.send_alert(
                severity=severity,
                title=f"Pipeline {next_state.value}",
                body=f"Auto-recovery: {old_state.value} → {next_state.value}. "
                f"Consecutive failures reached threshold.",
            )

    @staticmethod
    async def recover_stale_tasks(
        session: AsyncSession,
        stale_threshold_hours: int = 1,
    ) -> int:
        """Reset stale in_progress tasks to pending (crash recovery).

        Returns the number of tasks reset.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_threshold_hours)

        result = await session.execute(
            select(CrawlTask).where(
                CrawlTask.status == "in_progress",
                CrawlTask.started_at < cutoff,
            )
        )
        stale_tasks = list(result.scalars().all())

        for task in stale_tasks:
            task.status = "pending"
            task.started_at = None
            log.info(
                "stale_task_reset",
                task_id=task.id,
                retry_count=task.retry_count,
            )

        if stale_tasks:
            await session.flush()
            log.info("crash_recovery_complete", count=len(stale_tasks))

        return len(stale_tasks)
