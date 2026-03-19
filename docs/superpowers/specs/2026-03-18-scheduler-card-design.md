# Scheduler Card 设计 — Dashboard 集成

## 概述

在现有 Admin Dashboard 页面新增 Scheduler 管理区域，位于 Workers 和 Recent Failures 之间。展示调度器进程状态、Job 列表及元数据，提供 Trigger/Pause/Resume 操作控件。

## 动机

Scheduler 后端（4 个 API 端点）已在 CPS20 实现，但前端没有对应 UI。管理员目前无法在界面上查看调度器状态或进行控制，只能通过 CLI/API 操作。

## 范围

- 纯前端变更（零后端修改）
- 修改约 8 个文件，不新建组件文件
- 复用现有模式：StatusBadge、usePolling、i18n、Ant Design Card/Table

## 架构

### 在 Dashboard 中的位置

```
Dashboard.tsx 布局：
  1. StatsCards（4 卡片一行）
  2. 吞吐量图表（Card）
  3. Workers 工作进程（标题 + Card 网格）
  4. >>> Scheduler Card（新增）<<<
  5. 最近失败（标题 + Table）
```

理由：Workers = "谁在干活"，Scheduler = "谁在派活"，Failures = "出了什么问题" — 信息流自然顺畅。

### 数据流

```
usePolling(30s) → fetchAll()
  ├─ getOverview()
  ├─ getThroughput()
  ├─ getWorkers()
  ├─ getSchedulerStatus()    ← 新增
  └─ getRecentFailures()
```

Scheduler 状态与现有 Dashboard 数据共享同一个 30s 轮询周期。

## UI 布局

```
┌─ 调度器 ──────────────────────────────────────────────────┐
│  进程状态: [Tag: 运行中/已停止]  运行时间: 2h 35m          │
│  上次心跳: 2026-03-18 14:30:22                             │
│                                                            │
│  ┌─ Job 表格 ────────────────────────────────────────────┐ │
│  │ 名称  │ 状态  │ 间隔  │ 上次运行 │ 下次运行 │ 错误 │ 操作         │ │
│  │ crawl │ [空闲] │ 5 分钟 │ 14:30  │ 14:35  │  0  │ [触发][暂停] │ │
│  └───────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### Card 顶部

- 标题：翻译 key `scheduler.title`
- 进程状态 Tag：绿色"运行中"或红色"已停止"
- 运行时间：格式化为 `Xh Ym`（来自 `uptime_seconds`）；当 `process.status === "stopped"` 时显示 `-` 而不是 `0 min`
- 上次心跳：`last_heartbeat ? formatDateTime(last_heartbeat) : '-'`

### Job 表格列

| 列名 | 数据源 | 显示方式 |
|------|--------|----------|
| 名称 | `job.name` | 纯文本 |
| 状态 | `job.status` | StatusBadge（idle/running/paused） |
| 间隔 | `job.interval_seconds` | 人类可读：`300` → `5 min` |
| 上次运行 | `job.last_run_at` | render 中 null 检查：`v ? formatDateTime(v) : '-'` |
| 下次运行 | `job.next_run_at` | render 中 null 检查：`v ? formatDateTime(v) : '-'` |
| 错误数 | `job.error_count` | 数字，> 0 时红色文字 |
| 操作 | — | 按钮（见下方） |

### 操作按钮

| Job 状态 | 显示的按钮 |
|----------|-----------|
| `idle` 或 `running` | [触发] [暂停] |
| `paused` | [恢复] |

- 所有按钮执行前弹出 `Modal.confirm()` 确认
- 当 `process.status !== "running"`（调度器离线）时，所有按钮 disabled
- 成功：`message.success()` + 立即刷新数据
- 失败：`message.error()` 显示 API 返回的错误信息

### 进程离线状态

当 `process.status` 不是 `"running"` 时：
- Card 标题旁 Tag 显示红色"已停止"
- 所有操作按钮灰色禁用
- 禁用按钮 Tooltip："调度器进程已离线"

## TypeScript 类型

```typescript
// 添加到 types/index.ts

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

## API 端点（前端函数）

```typescript
// 添加到 api/endpoints.ts

getSchedulerStatus()                → GET  /scheduler/status  → SchedulerStatusResponse
triggerSchedulerJob(name: string)   → POST /scheduler/jobs/{name}/trigger  → { detail: string }
pauseSchedulerJob(name: string)     → POST /scheduler/jobs/{name}/pause    → { detail: string }
resumeSchedulerJob(name: string)    → POST /scheduler/jobs/{name}/resume   → { detail: string }
```

## StatusBadge 扩展

在 `colorMap` 中新增：
- `paused` → `'gold'`（与已有的 `idle: 'orange'` 区分）
- `stopped` → `'red'`

## i18n 翻译 Key（每语言约 15 个）

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

注：复用已有的 `status.idle` 和 `status.running` key（通过 StatusBadge 的 `t('status.${status}')` 模式），无需为这两个状态新增 key。

## 变更文件清单

| 文件 | 变更内容 |
|------|----------|
| `web/src/types/index.ts` | +3 个接口 |
| `web/src/api/endpoints.ts` | +4 个函数 |
| `web/src/pages/Dashboard.tsx` | +scheduler state、fetchAll 调用、Scheduler Card 区域 |
| `web/src/components/StatusBadge.tsx` | +2 个 colorMap 条目 |
| `web/src/utils/format.ts` | +`formatInterval()` 工具函数 |
| `web/src/i18n/locales/zh-CN.json` | +约 15 个 key |
| `web/src/i18n/locales/en-US.json` | +约 15 个 key |
| `web/src/i18n/locales/es-ES.json` | +约 15 个 key |

## 设计决策

1. **内联在 Dashboard.tsx** — 不单独抽组件文件。当前只有 1 个 job，数据量极小。未来 job 增多再抽取组件。
2. **所有操作加 Modal.confirm** — 操作频率低，误触 Pause 代价高。安全优先于效率。
3. **进程离线时禁用按钮** — 防止用户触发操作后无反馈的困惑体验。
4. **30s 轮询（共享）** — 与现有 Dashboard 轮询周期一致，无需单独轮询。
5. **人类可读间隔** — `formatInterval(seconds)` 工具函数：`300` → `5 min`，`3600` → `1h`。
