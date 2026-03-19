# Scheduler Card Design — Dashboard Integration

## Overview

Add a Scheduler management section to the existing Admin Dashboard page, positioned between Workers and Recent Failures. Displays scheduler process status, job list with metadata, and provides Trigger/Pause/Resume controls.

## Motivation

The scheduler backend (4 API endpoints) was implemented in CPS20 but has no frontend UI. Admins currently have no visibility into scheduler status or control without CLI/API calls.

## Scope

- Frontend-only changes (zero backend modifications)
- ~6 files modified, no new component files
- Reuses existing patterns: StatusBadge, usePolling, i18n, Ant Design Card/Table

## Architecture

### Position in Dashboard

```
Dashboard.tsx layout:
  1. StatsCards (4x row)
  2. Throughput Chart (Card)
  3. Workers (Title + Card grid)
  4. >>> Scheduler Card (NEW) <<<
  5. Recent Failures (Title + Table)
```

Rationale: Workers = "who is working", Scheduler = "who dispatches work", Failures = "what went wrong" — natural information flow.

### Data Flow

```
usePolling(30s) → fetchAll()
  ├─ getOverview()
  ├─ getThroughput()
  ├─ getWorkers()
  ├─ getSchedulerStatus()    ← NEW
  └─ getRecentFailures()
```

Scheduler status is fetched alongside existing Dashboard data in the same 30s polling cycle.

## UI Layout

```
┌─ Scheduler ───────────────────────────────────────────────┐
│  Process: [Tag: Running/Stopped]  Uptime: 2h 35m          │
│  Last heartbeat: 2026-03-18 14:30:22                       │
│                                                            │
│  ┌─ Jobs Table ──────────────────────────────────────────┐ │
│  │ Name   │ Status │ Interval │ Last Run │ Next Run │ Errors │ Actions    │ │
│  │ crawl  │ [idle] │ 5 min    │ 14:30   │ 14:35   │ 0      │ [Trigger][Pause] │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### Card Header

- Title: translated `scheduler.title`
- Process status Tag: green "Running" or red "Stopped"
- Uptime: formatted as `Xh Ym` (from `uptime_seconds`); when `process.status === "stopped"`, display `-` instead of `0 min`
- Last heartbeat: `last_heartbeat ? formatDateTime(last_heartbeat) : '-'`

### Jobs Table Columns

| Column | Source | Display |
|--------|--------|---------|
| Name | `job.name` | Plain text |
| Status | `job.status` | StatusBadge (idle/running/paused) |
| Interval | `job.interval_seconds` | Human-readable: `300` → `5 min` |
| Last Run | `job.last_run_at` | Null guard in render: `v ? formatDateTime(v) : '-'` |
| Next Run | `job.next_run_at` | Null guard in render: `v ? formatDateTime(v) : '-'` |
| Errors | `job.error_count` | Number, red text if > 0 |
| Actions | — | Buttons (see below) |

### Action Buttons

| Job Status | Buttons Shown |
|------------|---------------|
| `idle` or `running` | [Trigger] [Pause] |
| `paused` | [Resume] |

- All buttons use `Modal.confirm()` before executing
- All buttons disabled when `process.status !== "running"` (scheduler offline)
- Success: `message.success()` + immediate data refresh
- Error: `message.error()` with API error detail

### Process Offline State

When `process.status` is not `"running"`:
- Card title Tag shows red "Stopped"
- All action buttons are disabled (greyed out)
- Tooltip on disabled buttons: "Scheduler process is offline"

## TypeScript Types

```typescript
// Add to types/index.ts

interface SchedulerProcessStatus {
  status: string           // "running" | "stopped"
  uptime_seconds: number
  last_heartbeat: string | null
}

interface SchedulerJobStatus {
  name: string
  status: string           // "idle" | "running" | "paused"
  interval_seconds: number
  last_run_at: string | null
  next_run_at: string | null
  last_result: string | null
  error_count: number
}

interface SchedulerStatusResponse {
  process: SchedulerProcessStatus
  jobs: SchedulerJobStatus[]
}
```

## API Endpoints (Frontend Functions)

```typescript
// Add to api/endpoints.ts

getSchedulerStatus()                → GET  /scheduler/status  → SchedulerStatusResponse
triggerSchedulerJob(name: string)   → POST /scheduler/jobs/{name}/trigger  → { detail: string }
pauseSchedulerJob(name: string)     → POST /scheduler/jobs/{name}/pause    → { detail: string }
resumeSchedulerJob(name: string)    → POST /scheduler/jobs/{name}/resume   → { detail: string }
```

## StatusBadge Extensions

Add to `colorMap`:
- `paused` → `'gold'` (distinct from `idle` which is already `'orange'`)
- `stopped` → `'red'`

## i18n Keys (~15 per language)

```
scheduler.title             — "Scheduler" / "调度器" / "Programador"
scheduler.process           — "Process" / "进程" / "Proceso"
scheduler.uptime            — "Uptime" / "运行时间" / "Tiempo activo"
scheduler.lastHeartbeat     — "Last heartbeat" / "上次心跳" / "Ultimo latido"
scheduler.jobs              — "Jobs" / "任务" / "Trabajos"
scheduler.interval          — "Interval" / "间隔" / "Intervalo"
scheduler.lastRun           — "Last run" / "上次运行" / "Ultima ejecucion"
scheduler.nextRun           — "Next run" / "下次运行" / "Proxima ejecucion"
scheduler.errors            — "Errors" / "错误数" / "Errores"
scheduler.trigger           — "Trigger" / "触发" / "Activar"
scheduler.pause             — "Pause" / "暂停" / "Pausar"
scheduler.resume            — "Resume" / "恢复" / "Reanudar"
scheduler.confirmTrigger    — "Trigger this job now?" / "立即触发此任务？" / "Activar ahora?"
scheduler.confirmPause      — "Pause this job?" / "暂停此任务？" / "Pausar este trabajo?"
scheduler.confirmResume     — "Resume this job?" / "恢复此任务？" / "Reanudar este trabajo?"
scheduler.processOffline    — "Scheduler process is offline" / "调度器进程已离线" / "Proceso offline"
status.paused               — "Paused" / "已暂停" / "Pausado"
status.stopped              — "Stopped" / "已停止" / "Detenido"
```

Note: Reuses existing `status.idle` and `status.running` keys via StatusBadge — no new keys needed for those statuses.

## Files Changed

| File | Change |
|------|--------|
| `web/src/types/index.ts` | +3 interfaces |
| `web/src/api/endpoints.ts` | +4 functions |
| `web/src/pages/Dashboard.tsx` | +scheduler state, fetchAll call, Scheduler Card section |
| `web/src/components/StatusBadge.tsx` | +2 colorMap entries |
| `web/src/i18n/locales/zh-CN.json` | +~15 keys |
| `web/src/i18n/locales/en-US.json` | +~15 keys |
| `web/src/utils/format.ts` | +`formatInterval()` utility function |
| `web/src/i18n/locales/es-ES.json` | +~15 keys |

## Design Decisions

1. **Inline in Dashboard.tsx** — No separate component file. Currently only 1 job, data is minimal. Extract to component later if job count grows.
2. **Modal.confirm for all actions** — Low operation frequency, high cost of accidental Pause. Safety over speed.
3. **Disable buttons when process offline** — Prevents confusing UX where user triggers an action but nothing happens.
4. **30s polling (shared)** — Matches existing Dashboard polling cycle. No separate polling needed.
5. **Human-readable interval** — `formatInterval(seconds)` utility: `300` → `5 min`, `3600` → `1h`.
