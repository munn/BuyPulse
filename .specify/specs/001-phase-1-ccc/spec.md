# Feature Specification: Phase 1 — CCC Chart Price Data Collection System

**Feature Branch**: `001-phase-1-ccc`
**Created**: 2026-03-14
**Status**: Draft

## Overview

Build an automated system that downloads CamelCamelCamel (CCC) price chart images for Amazon products, extracts complete historical price data from those images, and stores it in a structured database. This creates a self-owned Amazon price history database — the foundation for the entire AI shopping assistant product.

The system serves a single operator (the project owner) who manages which products to track, monitors data quality, and receives alerts when things go wrong. There is no end-user interface in this phase.

## User Scenarios & Acceptance Criteria

### Scenario 1: Import Product Seeds

The operator has a list of Amazon product identifiers (ASINs) and wants to add them to the tracking system.

**Acceptance Criteria:**
1. **Given** a text file containing ASINs (one per line), **When** the operator runs the import command, **Then** new products are created and each is queued for data collection
2. **Given** an ASIN that already exists in the system, **When** it appears in an import file, **Then** it is silently skipped (no duplicate created)
3. **Given** a single ASIN, **When** the operator runs the add command, **Then** that one product is created and queued
4. **Given** a set of imported ASINs, **When** import completes, **Then** the operator sees a summary: total in file, newly added, duplicates skipped

### Scenario 2: Collect Price Data for a Batch of Products

The operator triggers a data collection run for a batch of queued products.

**Acceptance Criteria:**
1. **Given** products queued for collection, **When** a collection run starts with a batch size (e.g., 100), **Then** the system processes up to that many products in priority order
2. **Given** a product being processed, **When** the chart image is downloaded, **Then** the original image file is saved to disk before any analysis
3. **Given** a downloaded chart image, **When** analysis completes, **Then** the system extracts a complete price time series — every price change point on the curve, not just summary values
4. **Given** extracted price data, **When** the same product is collected again later, **Then** existing data points are updated (not duplicated) and new data points are added
5. **Given** a collection run, **When** it completes, **Then** the operator sees a status report: processed count, success count, failure count, average data points per product

### Scenario 3: Cross-Validate Extraction Quality

Every extraction must be validated to catch errors in the image analysis process.

**Acceptance Criteria:**
1. **Given** a chart image with legend text showing min/max/current prices, **When** the system extracts both the full curve data and the legend text, **Then** it compares them: extracted curve values must match legend values within ±5%
2. **Given** an extraction where curve-vs-legend deviation exceeds 5%, **When** validation runs, **Then** the data is stored but flagged as low-confidence and excluded from downstream queries
3. **Given** a chart image where no price curves can be detected, **When** extraction runs, **Then** it is marked as failed with a descriptive error message
4. **Given** a batch of extractions, **When** the operator checks quality stats, **Then** they see: total extractions, pass rate, fail rate, average confidence score

### Scenario 4: Monitor System Health

The operator needs to know when something goes wrong without constantly checking.

**Acceptance Criteria:**
1. **Given** more than 50 consecutive products fail during collection, **When** the failure threshold is hit, **Then** collection auto-pauses, the operator receives an email alert, and the system enters progressive auto-recovery: wait 1 hour → resume at half speed → if still failing, wait 6 hours → retry → if still failing, wait 24 hours → retry → after 3 failed recovery rounds, stop and send a final email
2. **Given** the failure rate exceeds 10% of a batch, **When** the batch completes, **Then** the operator receives a warning email
3. **Given** disk usage exceeds 80%, **When** the system checks disk space, **Then** the operator receives a critical email alert
4. **Given** no collection progress for 24 hours, **When** the stall is detected, **Then** the operator receives a warning email
5. **Given** the extraction quality pass rate drops below 80%, **When** the quality drop is detected, **Then** the operator receives a warning email
6. **Given** multiple alerts of the same type, **When** they fire within one hour, **Then** only the first email is sent (rate-limited to prevent inbox flooding)

### Scenario 5: Re-collect and Update Data

Products need periodic re-collection to keep price data current.

**Acceptance Criteria:**
1. **Given** a product with priority tier "hot" (top 10K), **When** its next collection time arrives, **Then** it is re-queued automatically for daily collection
2. **Given** a product with priority tier "standard" (10K–100K), **When** its next collection time arrives, **Then** it is re-queued for weekly collection
3. **Given** a product with priority tier "long tail" (100K+), **When** the operator or a user query requests it, **Then** it is re-queued on demand
4. **Given** a re-collection produces new data, **When** stored, **Then** it merges with existing history (upsert, no duplicates)

### Scenario 6: Retry Failed Collections

Transient failures should be retried automatically; permanent failures should not.

**Acceptance Criteria:**
1. **Given** a product fails due to rate limiting (HTTP 429), **When** the system detects it, **Then** it waits for the cooldown period and resumes at a reduced rate
2. **Given** a product fails due to server error (HTTP 5xx), **When** the failure occurs, **Then** it is retried with exponential backoff, up to 3 attempts
3. **Given** a product fails due to being blocked (HTTP 403), **When** the failure occurs, **Then** it is skipped (no retry) and logged
4. **Given** a product that has been retried the maximum number of times, **When** all retries are exhausted, **Then** it is marked as permanently failed for this cycle

### Scenario 7: Observe System Status

The operator needs visibility into what the system is doing and how much resource it consumes.

**Acceptance Criteria:**
1. **Given** the system is running, **When** the operator checks status, **Then** they see: total products tracked, pending/completed/failed counts, disk usage breakdown (database / images / free), crawl throughput (products/day), extraction quality rate
2. **Given** the operator wants to know seed composition, **When** they check seed stats, **Then** they see counts by priority tier

### Edge Cases

- What happens when a chart image has no data (product not tracked by CCC)? → Mark as "no data available", do not retry until operator re-triggers
- What happens when the chart image format changes? → Extraction fails, alert fires, operator investigates. Raw images are preserved for re-analysis after code updates
- What happens when disk runs out mid-collection? → Collection pauses, critical alert fires, operator must free space or upgrade before resuming
- What happens if the system crashes mid-batch? → On restart, incomplete tasks are detected (started but not finished within 1 hour) and reset to pending for re-processing
- What happens when a product has only 1 or 2 of the 3 possible price curves? → Extract whatever curves exist; having fewer curves is normal, not an error

## Functional Requirements

### Data Collection
- **FR-001**: System MUST download chart images via HTTP and save the original image file to disk before any processing
- **FR-002**: System MUST extract a complete price time series from chart images — every inflection point, not just summary statistics
- **FR-003**: System MUST extract three independent price series where available: Amazon-sold, third-party new, third-party used
- **FR-004**: System MUST extract legend text (lowest/highest/current prices with dates) for validation purposes

### Data Quality
- **FR-005**: System MUST cross-validate pixel-extracted prices against legend-extracted prices, with a ±5% tolerance threshold
- **FR-006**: System MUST flag extractions that fail validation as low-confidence and exclude them from downstream queries until reviewed
- **FR-007**: System MUST store all prices as whole-number cents (no floating-point currency values)

### Rate Limiting & Compliance
- **FR-008**: System MUST NOT exceed 1 request per second per IP address when downloading chart images
- **FR-009**: System MUST use its real HTTP client identifier — never impersonate a browser
- **FR-010**: System MUST immediately pause when receiving rate-limit responses (HTTP 429) and respect cooldown periods
- **FR-011**: System MUST NOT display or redistribute original chart images to end users in any phase

### Scheduling & Retry
- **FR-012**: System MUST process products in priority order (highest priority first)
- **FR-013**: System MUST retry transient failures (HTTP 5xx, timeouts) with exponential backoff, up to a configurable maximum
- **FR-014**: System MUST NOT retry permanent failures (HTTP 403, no data available)
- **FR-015**: System MUST detect and recover from incomplete tasks on restart (stale in-progress items older than 1 hour reset to pending)
- **FR-016**: When batch failure threshold is hit (>50 consecutive), system MUST auto-pause, then progressively auto-recover: wait 1 hour at half speed → wait 6 hours → wait 24 hours. After 3 failed recovery rounds, stop permanently and alert

### Alerting
- **FR-017**: System MUST send email alerts for: consecutive failures >50, batch failure rate >10%, disk usage >80%, stalled collection >24h, quality drop below 80%, and auto-recovery status (each round start/result)
- **FR-018**: System MUST rate-limit alerts to at most 1 email per alert type per hour

### Seed Management
- **FR-019**: System MUST support bulk import of product identifiers from text files with automatic deduplication
- **FR-020**: System MUST support adding a single product identifier interactively
- **FR-021**: System MUST assign priority tiers to products: hot (daily), standard (weekly), long-tail (on-demand)

### Observability
- **FR-022**: System MUST provide a status command showing: product counts, queue status, disk usage breakdown, throughput, and extraction quality metrics
- **FR-023**: System MUST provide seed statistics by priority tier

### Scale Targets
- **FR-024**: System MUST support at least 500,000 tracked products
- **FR-025**: System MUST handle at least 100,000,000 individual price data points
- **FR-026**: System MUST operate within a 40GB disk budget (OS + database + images + headroom)

### Pilot Validation
- **FR-027**: Before scaling beyond 100 products, the system MUST demonstrate: ≥90% extraction pass rate (within ±5% of legend values), ≥95% axis label read accuracy, and no systematic bias in price extraction

### Key Entities

- **Product**: An Amazon item identified by ASIN. Has a priority tier (hot/standard/long-tail), category, and first-seen timestamp
- **Price History**: Time series of prices for a product. Each record has a date, price in cents, price type (amazon/new/used), and data source
- **Price Summary**: Quick-reference snapshot of lowest/highest/current prices per product per price type, extracted from chart legends
- **Extraction Run**: Metadata about one attempt to extract data from a chart image — tracks success/failure, quality score, error details
- **Crawl Task**: Scheduling record for a product — tracks queue status, priority, retry count, next scheduled collection time
- **Daily Snapshot** *(Phase 2 placeholder)*: Future table for prices collected daily via official API — created now but remains empty

## Review Checklist
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
