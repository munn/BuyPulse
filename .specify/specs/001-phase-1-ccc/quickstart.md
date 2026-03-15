# Integration Test Scenarios

**Feature**: Phase 1 — CCC Chart Price Data Collection
**Purpose**: Key user journeys as integration test scenarios

## Scenario 1: Seed Import → Queue Creation

```
Setup:  Empty database
Action: Import file with 10 ASINs (2 duplicates within file)
Verify:
  - 8 products created in products table
  - 8 crawl_tasks created with status='pending', priority=5
  - CLI output shows: "10 total, 8 added, 2 duplicates skipped"

Action: Import another file with 5 ASINs (3 overlap with first import)
Verify:
  - 2 new products created (total now 10)
  - 2 new crawl_tasks created
  - CLI output shows: "5 total, 2 added, 3 duplicates skipped"
```

## Scenario 2: Download + Extract + Store (Happy Path)

```
Setup:  5 products with pending crawl_tasks
Mock:   respx returns sample_chart_normal.png for all 5 ASINs
Action: Run crawl with --limit 5
Verify:
  - 5 PNG files saved to data/charts/{prefix}/{ASIN}/{date}.png
  - 5 extraction_runs created with status='success'
  - price_history populated (multiple rows per product)
  - price_summary populated (up to 3 rows per product)
  - crawl_tasks updated: status='completed', next_crawl_at set
  - CLI output shows batch summary with success count
```

## Scenario 3: Re-crawl Deduplication

```
Setup:  1 product already crawled (has price_history data)
Mock:   respx returns same chart image
Action: Re-crawl the same ASIN
Verify:
  - New extraction_run created (extraction history preserved)
  - price_history: existing rows updated, no duplicates
  - price_summary: overwritten with latest values
  - crawl_tasks.total_crawls incremented
```

## Scenario 4: Rate Limiter Behavior

```
Action: Send 5 requests in rapid succession
Verify:
  - First request goes through immediately
  - Subsequent requests are spaced ≥1 second apart
  - Total elapsed time ≥4 seconds for 5 requests

Action: Simulate HTTP 429 response
Verify:
  - Rate limiter pauses for cooldown period (60s)
  - Subsequent requests resume at normal rate after cooldown
```

## Scenario 5: Retry Logic

```
Setup:  3 products with pending crawl_tasks
Mock:   Product 1: returns 500 first time, 200 second time
        Product 2: returns 403 always
        Product 3: returns 200

Action: Run crawl with --limit 3
Verify:
  - Product 1: retry_count=1, status='completed' (retried and succeeded)
  - Product 2: status='failed', error_message contains '403', no retry
  - Product 3: status='completed'
  - extraction_runs reflect actual attempts
```

## Scenario 6: Cross-Validation

```
Setup:  1 product with downloaded chart
Mock:   Pixel analysis returns lowest=$29.99
        OCR legend reads lowest=$28.99 (3.3% deviation, within ±5%)
Action: Run extraction
Verify:
  - extraction_runs.validation_passed = true
  - Data stored normally

Setup:  1 product with downloaded chart
Mock:   Pixel analysis returns lowest=$29.99
        OCR legend reads lowest=$19.99 (33% deviation, exceeds ±5%)
Action: Run extraction
Verify:
  - extraction_runs.validation_passed = false
  - extraction_runs.status = 'low_confidence'
  - Data stored but flagged
```

## Scenario 7: Auto-Recovery State Machine

```
Setup:  100 products with pending crawl_tasks
Mock:   All requests return HTTP 500

Action: Run crawl with --limit 100
Verify:
  - After 50 consecutive failures: system auto-pauses
  - Email alert sent (CRITICAL: consecutive failures)
  - System waits 1 hour (mocked/accelerated in test)
  - Resumes at half speed
  - If still failing: waits 6 hours, retries
  - If still failing: waits 24 hours, retries
  - After 3 failed rounds: stops permanently
  - Final email alert sent
  - Each state transition logged
```

## Scenario 8: Crash Recovery

```
Setup:  3 crawl_tasks with status='in_progress', started_at=2 hours ago
Action: System startup / initialization
Verify:
  - All 3 tasks reset to status='pending'
  - retry_count preserved (not reset)
  - Log message indicates recovery
```

## Scenario 9: Status and Stats Commands

```
Setup:  Database with mixed data:
        - 100 products (30 hot, 50 standard, 20 long-tail)
        - 80 completed crawl_tasks, 15 pending, 5 failed
        - Various extraction quality scores
Action: Run `cps crawl status`
Verify:
  - Shows product counts by status
  - Shows crawl throughput
  - Shows extraction quality rate

Action: Run `cps seed stats`
Verify:
  - Shows counts by priority tier: hot=30, standard=50, long-tail=20

Action: Run `cps db stats`
Verify:
  - Shows row counts per table
  - Shows disk usage breakdown
```

## Scenario 10: Email Alert Rate Limiting

```
Setup:  Alert conditions triggered rapidly
Action: Trigger same alert type 5 times within 10 minutes
Verify:
  - Only 1 email sent (rate limited to 1 per type per hour)
  - Subsequent triggers logged but not emailed

Action: Wait 1+ hour, trigger same alert again
Verify:
  - Email sent (rate limit window expired)
```
