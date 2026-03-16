# BuyPulse Product Design — AI Shopping Assistant

**Date**: 2026-03-16
**Status**: Approved (MVP scope)

## Product Overview

**Name**: BuyPulse
**Tagline**: Tell us what you want to buy. We'll tell you when to buy it.
**Target Market**: US consumers, English + Spanish
**Channel**: Telegram Bot (private chat first, group chat in V2)
**Revenue**: Affiliate commissions (primary), subscription as backup if needed

## Value Proposition

The gap between ChatGPT and CamelCamelCamel:
- ChatGPT understands natural language needs but has no real-time price data
- CamelCamelCamel has price data but requires users to know exact products, set their own target prices, and interpret charts
- **BuyPulse bridges the gap**: understands what you want + knows price history + actively monitors and notifies

## V1 (MVP) Scope

### Core Features

1. **Price monitoring via private chat**
   - User sends Amazon product link or ASIN
   - Bot returns: historical price range, current price position
   - User sets target price → Bot monitors and notifies on price drop
   - Notifications include affiliate link

2. **Deal push (subscription-based)**
   - Users subscribe to product categories they care about
   - When deals appear in subscribed categories, Bot proactively pushes to relevant users
   - Each push includes affiliate link

3. **Multi-language support**
   - English + Spanish from Day 1
   - AI-powered language detection and response (near-zero extra cost)

4. **Free tier**
   - 20 monitored items per user (generous to drive adoption)

### Deliberately Deferred to V2

- Group chat functionality (Bot in Telegram groups, @mention + active mode)
- Natural language product search ("I want a robot vacuum under $300")
- AI purchase advisor (seasonal analysis, alternative recommendations, fake deal detection)
- "Good price" AI judgment (V1 TBD — may use simple rules like percentile ranking)

## User Interaction (V1)

### Setting up monitoring
```
User: [sends Amazon link]
Bot: "Roborock Q7 Max Robot Vacuum
      Current: $319
      Historical: $249 - $429
      This price is in the lower 30% of its range.
      Set a target price to get notified?"
User: "$280"
Bot: "Done! Watching Roborock Q7 Max.
      I'll notify you when it drops to $280 or below."
```

### Receiving alerts
```
Bot: "🔔 Price drop! Roborock Q7 Max is now $269
      Your target: $280 ✅
      Historical low: $249
      [Buy on Amazon →]"
```

### Deal push (subscribed category)
```
Bot: "🏷️ Deal in Electronics:
      Sony WH-1000XM5 dropped to $228 (was $349)
      Lowest in 4 months
      [Buy on Amazon →]"
```

## Data Architecture

### Layer 1: Price Data (existing from Phase 1)
- CCC historical data bootstrap via pixel analysis
- PostgreSQL: products, price_history, price_summary tables
- Future: Creators API daily snapshots (after cold start solved)

### Layer 2: Product Knowledge (new, V1)
- Product info: name, category tags, specs
- Pre-built popular category → ASIN mappings
- Source: manual curation + CCC data enrichment

### Layer 3: User Data (new, V1)
- Users: Telegram user_id, language preference, timezone
- Monitor list: user_id, ASIN, target_price
- Category subscriptions: user_id, categories
- Notification history: tracking clicks and conversions

### Data Flow
```
Price change detected
    → Match against user monitor lists
    → Price ≤ target? → Push notification + affiliate link

New deal detected in category
    → Find users subscribed to that category
    → Push deal notification + affiliate link
```

## Key Risks & Open Questions

### CRITICAL: Creators API Cold Start
- Need 10 shipped sales in 30 days to get API access
- Without API: no real-time current prices
- Options: manual sales, friends & family, PA-API bridge (expires May 2026), Keepa as stopgap
- **Must have a concrete plan before Phase 2 development**

### HIGH: CCC Data Source Reliability
- Cloudflare could upgrade protection at any time
- curl_cffi bypass verified (20/20 success, endurance test pending)
- Mitigation: CCC is bootstrap only, transition to self-built daily snapshots ASAP

### MEDIUM: Telegram US Penetration
- Telegram is not mainstream in US (vs iMessage, WhatsApp)
- Target audience may skew tech-savvy
- V2 consideration: expand to web app for SEO-driven growth

### OPEN: "Good Price" Definition
- How to determine if a price is worth alerting beyond target price match
- V1: TBD — may use simple percentile rules or defer to user-set targets only
- V2: AI-powered analysis with seasonal patterns

### OPEN: First 100 Users Acquisition
- Reddit r/deals, r/frugal, r/amazondeals
- Product Hunt launch
- Twitter/X presence
- Landing page with waitlist

## Cost Structure (Estimated)

| Item | Monthly Cost |
|------|-------------|
| VPS (Hetzner CPX22) | $8-10 |
| AI API (Haiku for 90% of calls) | $10-30 |
| Domain + misc | $5 |
| **Total** | **~$25-45/month** |

## Growth Strategy

### V1: Prove value (private chat)
Users find Bot → monitor products → get alerts → buy via affiliate link → revenue

### V2: Viral growth (group chat)
Private user → adds Bot to group → group members see value → add Bot privately → more groups

### V2+: AI differentiation
Natural language search → AI purchase advisor → proactive smart recommendations

## Technical Stack

- **Backend**: Python (existing Phase 1 codebase)
- **Database**: PostgreSQL (existing)
- **Bot Framework**: python-telegram-bot
- **AI**: Claude API (Haiku 4.5 for most calls, Sonnet for complex queries)
- **Hosting**: Hetzner VPS
- **Price Data**: CCC bootstrap + Creators API (post cold start)

## Success Metrics (MVP)

- 100 users in first month
- 20% weekly active rate
- 5% click-through on affiliate links
- 10 shipped sales (Creators API unlock)
