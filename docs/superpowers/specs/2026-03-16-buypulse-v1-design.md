# BuyPulse V1 Design Spec — Telegram Bot MVP

**Date**: 2026-03-16
**Status**: Draft
**Supersedes**: `2026-03-16-buypulse-product-design.md` (brainstorming-phase doc)

---

## Product Overview

**Name**: BuyPulse
**Tagline**: Tell us what you want to buy. We'll tell you when to buy it.
**Platform**: Telegram Bot (private chat, V1)
**Target**: US consumers, English + Spanish
**Revenue**: Amazon affiliate commissions on every price report and notification
**Future**: Expand to WhatsApp, iMessage, or standalone app based on US market traction

---

## 1. Onboarding: Demo-First

No tutorial walls. User sends `/start`, Bot immediately demonstrates value with a real product.

### Flow

```
User: /start

Bot: "Hey! I'm BuyPulse. Let me show you what I do.

      AirPods Pro 2 (USB-C)
      Current: $189
      Historical: $169 - $249
      This price is in the lower 25% — good time to buy.

      [Buy on Amazon →]

      That's it. Send me any Amazon link or just tell me
      what you want to buy. I'll track the price for you.

      By using BuyPulse, you agree to our Privacy Policy."
```

**Key points:**
- One message, real data, immediate value
- Affiliate link from the very first interaction
- Privacy policy mention (CCPA compliance)
- No multi-step tutorial, no "choose your language" gate (auto-detect)
- **Fallback:** If demo ASIN has no price data in DB (cold start), show a generic welcome without price data: "Send me any Amazon link or tell me what you want to buy." Pre-seed the demo ASIN during deployment.

---

## 2. Core Interaction: Price Check

### 2.1 Input Methods

Users can send three types of input:

| Input | Example | Handling |
|-------|---------|----------|
| Amazon URL | `https://amazon.com/dp/B08N5WRWNW` | Parse ASIN from URL |
| Plain ASIN | `B08N5WRWNW` | Direct lookup |
| Natural language | "How much are AirPods Pro?" | AI intent → 3-tier search |

### 2.2 Input Detection Order

When a user sends a message, classify it in this order:
1. **URL regex** — contains `amazon.com/dp/` or `amazon.com/gp/product/` → extract ASIN
2. **ASIN regex** — matches `B[A-Z0-9]{9}` standalone → direct ASIN lookup
3. **Everything else** → treat as natural language → send to AI (Haiku) for intent extraction

Example: `"B08N5WRWNW is it a good price?"` → ASIN regex matches first → lookup `B08N5WRWNW`, ignore the rest of the text.

### 2.3 Three-Tier Search Waterfall

When a product needs to be found (natural language or unknown ASIN):

1. **Our DB** — fuzzy match on `products.title`. Zero cost, instant.
2. **Amazon API** — Creators API search (when available). Accurate but requires API access.
3. **Fallback link** — "I couldn't find that exact product. Here's an Amazon search link — send me the product link from there."

Tier 2 auto-skips during Creators API cold-start period.

### 2.4 Price Report

Three density levels. User picks a global default; can toggle per-query.

**Compact (3 lines):**
```
AirPods Pro 2 — $189 (low 25%, good price)
Historical: $169 - $249
[Buy on Amazon →]
```

**Standard (default, 5 lines):**
```
AirPods Pro 2 (USB-C)
Current: $189
Historical: $169 - $249
This price is in the lower 25% of its range (good).
[Buy on Amazon →] [More detail ▼] [Set alert]
```

**Detailed (8+ lines):**
```
AirPods Pro 2 (USB-C)
Current: $189
Historical low: $169 (2025-11-24)
Historical high: $249 (2025-06-15)
Percentile: 25% (lower quarter)
30-day trend: ▼ dropping
Verdict: Good time to buy.
[Buy on Amazon →] [Less detail ▲] [Set alert]
```

**Rules:**
- Every price report includes an affiliate link (revenue on every interaction)
- Per-query toggle (`More detail ▼` / `Less detail ▲`) affects only that one message. Next query resets to global default. Not persisted.
- Global default changeable via `/settings`
- All price data uses `price_type='amazon'` (amazon-new) as primary source

---

## 3. Target Price & Monitoring

### 3.1 Smart Target Price Suggestions

After a price report, the `[Set alert]` button shows:

```
Set a price alert for AirPods Pro 2:
[Historical low: $169]  [30th pct: $189]  [Custom price]  [Skip]
```

- **Historical low** — all-time lowest from `price_summary` where `price_type='amazon'` (amazon-new). If no amazon type, fall back to any available type.
- **30th percentile** — calculated from all `price_history` data points for this product (full history, not windowed)
- **Custom price** — user types a number
- **Skip** — monitor without target (just watch, no alerts)

Tapping a preset button immediately creates the monitor. No extra confirmation.

### 3.2 Monitoring Rules

- **20 free monitors** per user. When full: "You're at 20/20 monitors. Remove one from /monitors to add a new one."
- **24h notification cooldown** — per (user, product) pair. `price_monitors.last_notified_at` is the clock. One user, one product = one `price_monitors` row (unique constraint).
- **Monitor expiry notification** — if a product is delisted or CCC data goes stale (no update in 30 days), notify: "AirPods Pro 2 monitoring paused — product appears unavailable. [Remove] [Keep watching]"
- **On-demand crawl failure** — if CCC crawl fails for a user-requested ASIN, notify within 1 hour: "Sorry, I couldn't fetch price data for [ASIN]. You can try again later." Do not silently fail.
- Price checks on monitored items happen via periodic CCC re-crawl (background job, runs every 5 minutes, processes pending crawl tasks in priority order)

### 3.3 Price Alert Notification

```
Bot: "Price drop! AirPods Pro 2 is now $169
      Your target: $189 ✅
      Historical low: $169 — this matches it!
      [Buy on Amazon →]"
```

- `[Buy on Amazon →]` — affiliate link
- Monitor stays active after notification (user can remove via `/monitors`)

---

## 4. Deal Push (Smart, No Categories)

Instead of manual category subscriptions, deal push is AI-driven with three layers:

### 4.1 Three-Layer Deal Detection

| Layer | Logic | Example |
|-------|-------|---------|
| **Related** | User monitors AirPods → find similar products at good prices | "Sony WH-1000XM5 just hit $228 — similar to your AirPods Pro" |
| **Global best** | All-time low across any popular product | "Today's best deal: Roborock Q7 Max at $249 (all-time low)" |
| **Behavior-inferred** | User searched for "robot vacuum" 3+ times in 7 days (from `user_interactions` where `interaction_type='search'`) → infer interest | "Still looking at robot vacuums? The Roomba j7 just dropped to $299" |

### 4.2 Cancel Button Rule

**Every deal push for a non-monitored item MUST include a dismiss button:**

```
Bot: "Sony WH-1000XM5 dropped to $228 (was $349)
      Near historical low — only 5% above all-time lowest.
      [Buy on Amazon →] [Stop suggestions like this]"
```

`[Stop suggestions like this]` → stores a dismissal record in `deal_dismissals` table with the product's `category` string (from `products.category`). Future deal pushes skip products in dismissed categories for this user. If the product has no category, dismiss by ASIN instead.

### 4.3 Adaptive Push Frequency

Push cadence auto-adjusts based on user engagement:

| Phase | Behavior | Downgrade trigger |
|-------|----------|-------------------|
| Day 1 | No extra push — onboarding demo serves as Day 1's deal exposure | — |
| Day 2-7 | 1 deal/day | — |
| **7 days no interaction** | → weekly digest | No clicks or replies for 7 days |
| **+14 days no interaction** | → monthly digest | Weekly ignored for 2 weeks |
| **+30 days no interaction** | → stop pushing | Monthly ignored |
| **Any time** | Historical all-time low → push immediately | Bypasses frequency limits |

**"Interaction" = tapped a button, clicked a link, or sent a message.** Telegram has no read receipts, so "saw but didn't act" counts as no interaction.

**Downgrade notification:** When downgrading, tell the user:
```
"We'll send you deals weekly instead of daily.
[Keep daily] [Weekly is fine]"
```

### 4.4 Re-engagement

When a stopped/downgraded user comes back (sends any message):
```
"Welcome back! You have 3 active price monitors.
Deal alerts were paused — want to turn them back on?
[Yes, restart deals] [No thanks]"
```

---

## 5. Management Commands

| Command | Function |
|---------|----------|
| `/monitors` | List all monitors with current prices + target + status. Each has a `[Remove]` button |
| `/settings` | Price report density (compact/standard/detailed), language (EN/ES), deal push frequency override |
| `/help` | One-screen help with examples |
| `/language` | Quick switch EN ↔ ES (shortcut for settings) |

### /monitors Display

```
Your monitors (3/20):

1. AirPods Pro 2 — $189 (target: $169) 📉
   [Remove]
2. Roborock Q7 Max — $319 (target: $280) →
   [Remove]
3. iPad Air M2 — $549 (no target) →
   [Remove]
```

Each item is tappable → shows full price report for that product.

---

## 6. Language Support

- **AI auto-detection**: First message from user → detect language → set default
- **Manual override**: `/language` or `/settings`
- **Supported**: English, Spanish (Español)
- **Implementation**: All message templates in both languages, AI (Haiku) for dynamic content

---

## 7. System Features

### 7.1 On-Demand Crawl

When a user queries an ASIN with no price data:
1. Create `Product` record if not exists
2. **Upsert** `CrawlTask`: if exists, update `status='pending', priority=1`; if not exists, create with `priority=1`. (Note: `crawl_tasks.product_id` has a unique constraint — must use upsert, not insert.)
3. Reply: "I don't have price history for this yet. I'm fetching it now — check back in a few minutes."
4. Background pipeline picks it up within the next 5-minute crawl cycle
5. If crawl fails after all retries, notify user within 1 hour (see Section 3.2)

**Note:** The existing pipeline's `PriceSummary` uses INSERT with duplicate-skip. For re-crawled ASINs, this must be changed to UPSERT to update `current_price` with fresh data.

### 7.2 Rate Limiting

| Limit | Value | Purpose |
|-------|-------|---------|
| Messages per minute per user | 10 | Prevent spam/abuse |
| Price queries per day per user | 50 | Control AI API cost |
| Global bot send rate | 30 msg/s | Telegram API limit |

Exceeded → friendly message: "Slow down! You can check up to 50 products per day."

### 7.3 Blocked User Handling

When `bot.send_message()` raises `Forbidden`:
- Mark user as `blocked` in DB
- Stop all sends to that user
- Do NOT auto-retry

### 7.4 Affiliate Link Strategy

| Touchpoint | Affiliate link? |
|------------|-----------------|
| Onboarding demo | Yes |
| Every price report | Yes |
| Price alert notification | Yes |
| Deal push | Yes |
| Fallback Amazon search link | Yes (tagged search URL) |

**Every user-facing Amazon URL carries the affiliate tag.** This is the core revenue mechanism.

### 7.5 Privacy

- `/start` message includes privacy notice
- Simple Privacy Policy page (static HTML hosted on VPS)
- User data: Telegram ID, username, language preference, monitor list, interaction history
- No data sold to third parties
- User can request data deletion via `/settings` → `[Delete my data]`

---

## 8. Data Architecture

### Existing (Phase 1)

| Table | Purpose |
|-------|---------|
| `products` | ASIN, title, category |
| `price_history` | Full price time series from CCC charts |
| `price_summary` | Latest low/high/current per product |
| `extraction_runs` | CCC chart extraction metadata |
| `crawl_tasks` | Crawl queue with priority + status |

### New (Phase 2 — this spec)

| Table | Purpose |
|-------|---------|
| `telegram_users` | telegram_id, username, language, density preference, monitor_limit, notification_state |
| `price_monitors` | user → product, target_price, is_active, last_notified_at (no separate `paused` field — V1 uses `is_active` only; pause/resume is V1.1) |
| `notification_log` | What was sent, when, affiliate_tag. `clicked` field tracks inline button taps only (e.g. `[Buy on Amazon →]` callback), NOT actual Amazon page visits (those are tracked by Amazon's affiliate dashboard). |
| `user_interactions` | Tracks: inline button clicks (callback_data), messages sent, search queries (text stored for behavior inference). Drives adaptive push. Each row: user_id, interaction_type, payload (search text / callback data), created_at. |
| `deal_dismissals` | user_id, dismissed_category (string from `products.category`) OR dismissed_asin. Used to filter future deal pushes. |

### Key Fields on `telegram_users`

| Field | Type | Purpose |
|-------|------|---------|
| `notification_state` | enum | `active` / `degraded_weekly` / `degraded_monthly` / `stopped` / `paused_by_user` / `blocked`. User enters `paused_by_user` via `/settings` → "Pause deal alerts". Differs from `stopped`: paused users get re-engagement prompt on any interaction; stopped users were auto-downgraded and need explicit opt-in. |
| `density_preference` | enum | `compact` / `standard` / `detailed` |
| `last_interaction_at` | timestamp | Drives adaptive push downgrade |

---

## 9. Tech Stack

| Component | Technology |
|-----------|------------|
| Bot framework | python-telegram-bot v21+ (async, includes job queue) |
| AI (NLP + language detection) | Claude Haiku 4.5 (90% of calls), Sonnet for complex |
| Database | PostgreSQL (existing) |
| ORM | SQLAlchemy 2.0 async (existing) |
| Background jobs | python-telegram-bot JobQueue (APScheduler) |
| Hosting | Hetzner VPS (existing) |
| Price data | CCC charts (existing pipeline) + Creators API (post cold-start) |

---

## 10. Success Metrics (MVP)

| Metric | Target |
|--------|--------|
| Users (first month) | 100 |
| Weekly active rate | 20% |
| Affiliate link CTR | 5% |
| Shipped sales (for Creators API unlock) | 10 |
| Price report → monitor conversion | 30% |

---

## 11. Out of Scope (V2+)

- Group chat functionality
- Web app / SEO-driven growth
- AI purchase advisor (seasonal analysis, fake deal detection)
- Paid subscription tier
- Full category subscription system
- Price history chart images (ASCII sparkline considered for V1.1)
- Monitor pause/resume (V1.1)
- "Wait for lower" button on alerts (V1.1)

---

## 12. Cost Estimate

| Item | Monthly Cost |
|------|-------------|
| VPS (Hetzner CPX22) | $8-10 |
| Claude API (Haiku for 90% of calls) | $10-30 |
| Domain + Privacy Policy hosting | $5 |
| **Total** | **~$25-45/month** |
