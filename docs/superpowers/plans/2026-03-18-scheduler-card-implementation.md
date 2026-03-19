# Scheduler Card 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Admin Dashboard 页面新增 Scheduler 管理区域，展示进程状态和 Job 列表，提供 Trigger/Pause/Resume 操作。

**Architecture:** 纯前端变更。在 Dashboard.tsx 的 Workers 和 Recent Failures 之间插入 Scheduler Card，复用现有 usePolling(30s)、StatusBadge、i18n 模式。新增 4 个 API 函数、3 个 TypeScript 接口、1 个工具函数、3 语言约 15 key。

**Tech Stack:** React 19, Ant Design 6, TypeScript, Axios, i18next

**Spec:** `docs/superpowers/specs/2026-03-18-scheduler-card-design.md`

---

### Task 1: TypeScript 类型定义

**Files:**
- Modify: `web/src/types/index.ts`

- [ ] **Step 1: 在 `types/index.ts` 末尾新增 3 个接口**

```typescript
export interface SchedulerProcessStatus {
  status: string
  uptime_seconds: number
  last_heartbeat: string | null
}

export interface SchedulerJobStatus {
  name: string
  status: string
  interval_seconds: number
  last_run_at: string | null
  next_run_at: string | null
  last_result: string | null
  error_count: number
}

export interface SchedulerStatusResponse {
  process: SchedulerProcessStatus
  jobs: SchedulerJobStatus[]
}
```

- [ ] **Step 2: 验证 TypeScript 编译无误**

Run: `cd web && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add web/src/types/index.ts
git commit -m "feat(scheduler-card): add TypeScript interfaces for scheduler status"
```

---

### Task 2: API 端点函数

**Files:**
- Modify: `web/src/api/endpoints.ts`

- [ ] **Step 1: 在 `endpoints.ts` 顶部 import 区域追加类型导入**

在现有 import 块中追加 `SchedulerStatusResponse`：

```typescript
import type {
  // ... existing imports ...
  SchedulerStatusResponse,
} from '../types'
```

- [ ] **Step 2: 在文件末尾新增 4 个函数**

```typescript
export const getSchedulerStatus = () =>
  api.get<SchedulerStatusResponse>('/scheduler/status')

export const triggerSchedulerJob = (name: string) =>
  api.post<{ detail: string }>(`/scheduler/jobs/${name}/trigger`)

export const pauseSchedulerJob = (name: string) =>
  api.post<{ detail: string }>(`/scheduler/jobs/${name}/pause`)

export const resumeSchedulerJob = (name: string) =>
  api.post<{ detail: string }>(`/scheduler/jobs/${name}/resume`)
```

- [ ] **Step 3: 验证 TypeScript 编译无误**

Run: `cd web && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add web/src/api/endpoints.ts
git commit -m "feat(scheduler-card): add scheduler API endpoint functions"
```

---

### Task 3: StatusBadge 颜色扩展

**Files:**
- Modify: `web/src/components/StatusBadge.tsx`

- [ ] **Step 1: 在 `colorMap` 中新增 2 个条目**

在 `success: 'green',` 之后追加：

```typescript
  paused: 'gold',
  dead: 'red',
```

- [ ] **Step 2: 验证 TypeScript 编译无误**

Run: `cd web && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add web/src/components/StatusBadge.tsx
git commit -m "feat(scheduler-card): add paused/dead colors to StatusBadge"
```

---

### Task 4: formatInterval 工具函数

**Files:**
- Modify: `web/src/utils/format.ts`

- [ ] **Step 1: 在 `format.ts` 末尾新增 `formatInterval` 函数**

```typescript
export function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}
```

- [ ] **Step 2: 验证 TypeScript 编译无误**

Run: `cd web && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 3: Commit**

```bash
git add web/src/utils/format.ts
git commit -m "feat(scheduler-card): add formatInterval utility function"
```

---

### Task 5: i18n 翻译 Key（三语言）

**Files:**
- Modify: `web/src/i18n/locales/zh-CN.json`
- Modify: `web/src/i18n/locales/en-US.json`
- Modify: `web/src/i18n/locales/es-ES.json`

- [ ] **Step 1: 在 `zh-CN.json` 的 `"lang.esES"` 行之前新增 scheduler keys**

```json
  "scheduler.title": "调度器",
  "scheduler.process": "进程",
  "scheduler.uptime": "运行时间",
  "scheduler.lastHeartbeat": "上次心跳",
  "scheduler.interval": "间隔",
  "scheduler.lastRun": "上次运行",
  "scheduler.nextRun": "下次运行",
  "scheduler.errors": "错误数",
  "scheduler.trigger": "触发",
  "scheduler.pause": "暂停",
  "scheduler.resume": "恢复",
  "scheduler.confirmTrigger": "立即触发此任务？",
  "scheduler.confirmPause": "暂停此任务？",
  "scheduler.confirmResume": "恢复此任务？",
  "scheduler.processOffline": "调度器进程已离线",
  "scheduler.jobName": "名称",
  "status.paused": "已暂停",
  "status.dead": "已失联",
  "audit.action_pause": "暂停",
  "audit.action_resume": "恢复",
  "audit.resource_schedulerJob": "调度任务",
```

- [ ] **Step 2: 在 `en-US.json` 的 `"lang.esES"` 行之前新增对应 keys**

```json
  "scheduler.title": "Scheduler",
  "scheduler.process": "Process",
  "scheduler.uptime": "Uptime",
  "scheduler.lastHeartbeat": "Last Heartbeat",
  "scheduler.interval": "Interval",
  "scheduler.lastRun": "Last Run",
  "scheduler.nextRun": "Next Run",
  "scheduler.errors": "Errors",
  "scheduler.trigger": "Trigger",
  "scheduler.pause": "Pause",
  "scheduler.resume": "Resume",
  "scheduler.confirmTrigger": "Trigger this job now?",
  "scheduler.confirmPause": "Pause this job?",
  "scheduler.confirmResume": "Resume this job?",
  "scheduler.processOffline": "Scheduler process is offline",
  "scheduler.jobName": "Name",
  "status.paused": "Paused",
  "status.dead": "Dead",
  "audit.action_pause": "Pause",
  "audit.action_resume": "Resume",
  "audit.resource_schedulerJob": "Scheduler Job",
```

- [ ] **Step 3: 在 `es-ES.json` 的 `"lang.esES"` 行之前新增对应 keys**

```json
  "scheduler.title": "Programador",
  "scheduler.process": "Proceso",
  "scheduler.uptime": "Tiempo activo",
  "scheduler.lastHeartbeat": "Último latido",
  "scheduler.interval": "Intervalo",
  "scheduler.lastRun": "Última ejecución",
  "scheduler.nextRun": "Próxima ejecución",
  "scheduler.errors": "Errores",
  "scheduler.trigger": "Activar",
  "scheduler.pause": "Pausar",
  "scheduler.resume": "Reanudar",
  "scheduler.confirmTrigger": "¿Activar este trabajo ahora?",
  "scheduler.confirmPause": "¿Pausar este trabajo?",
  "scheduler.confirmResume": "¿Reanudar este trabajo?",
  "scheduler.processOffline": "El proceso del programador está fuera de línea",
  "scheduler.jobName": "Nombre",
  "status.paused": "Pausado",
  "status.dead": "Inactivo",
  "audit.action_pause": "Pausar",
  "audit.action_resume": "Reanudar",
  "audit.resource_schedulerJob": "Trabajo programado",
```

- [ ] **Step 4: 验证 JSON 格式正确**

Run: `cd web && node -e "['zh-CN','en-US','es-ES'].forEach(l => { JSON.parse(require('fs').readFileSync('src/i18n/locales/'+l+'.json','utf8')); console.log(l+' OK') })"`
Expected: 三个都输出 OK

- [ ] **Step 5: Commit**

```bash
git add web/src/i18n/locales/
git commit -m "feat(scheduler-card): add i18n keys for scheduler card (3 languages)"
```

---

### Task 6: Dashboard.tsx 集成 Scheduler Card

**Files:**
- Modify: `web/src/pages/Dashboard.tsx`

**依赖:** Task 1-5 全部完成

- [ ] **Step 1: 追加 import**

在文件顶部追加必要的导入：

```typescript
import { Button, Card, Col, message, Modal, Row, Table, Tag, Tooltip, Typography } from 'antd'
```
（替换现有的 `import { Card, Col, Row, Table, Typography } from 'antd'`）

追加 API 函数导入：
```typescript
import {
  getOverview,
  getRecentFailures,
  getSchedulerStatus,
  getThroughput,
  getWorkers,
  pauseSchedulerJob,
  triggerSchedulerJob,
  resumeSchedulerJob,
} from '../api/endpoints'
```
（替换现有的 4 个函数导入）

追加类型导入：
```typescript
import type {
  OverviewStats,
  RecentFailure,
  SchedulerStatusResponse,
  ThroughputBucket,
  WorkerStatus,
} from '../types'
```
（替换现有的 4 个类型导入）

追加工具函数导入：
```typescript
import { formatDateTime, formatInterval } from '../utils/format'
```
（替换现有的 `import { formatDateTime } from '../utils/format'`）

- [ ] **Step 2: 在 Dashboard 组件中新增 scheduler state**

在现有 `failures` state 之后追加：

```typescript
const [scheduler, setScheduler] = useState<SchedulerStatusResponse | null>(null)
```

- [ ] **Step 3: 在 fetchAll 中新增 getSchedulerStatus 调用**

在 `getRecentFailures` 调用之后追加：

```typescript
getSchedulerStatus().then((r) => setScheduler(r.data)).catch(() => {})
```

- [ ] **Step 4: 新增 scheduler 操作处理函数**

在 `usePolling(fetchAll, 30_000)` 之后、`throughputOption` 之前插入：

```typescript
const isSchedulerOnline = scheduler?.process.status === 'running'

const handleSchedulerAction = useCallback(
  (action: 'trigger' | 'pause' | 'resume', jobName: string) => {
    const confirmKey = `scheduler.confirm${action.charAt(0).toUpperCase() + action.slice(1)}` as const
    Modal.confirm({
      title: t(confirmKey),
      onOk: async () => {
        try {
          const fn = { trigger: triggerSchedulerJob, pause: pauseSchedulerJob, resume: resumeSchedulerJob }[action]
          const res = await fn(jobName)
          message.success(res.data.detail)
          fetchAll()
        } catch (e: unknown) {
          const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          message.error(detail || t('common.error'))
        }
      },
    })
  },
  [t, fetchAll]
)
```

- [ ] **Step 5: 在 Workers 区域之后、Recent Failures 之前插入 Scheduler Card JSX**

在 Workers 区域的 `</Row>` 之后、`<Typography.Title level={5}>{t('dashboard.recentFailures')}` 之前插入：

```tsx
<Typography.Title level={5} style={{ marginTop: 24 }}>
  {t('scheduler.title')}
</Typography.Title>
<Card
  size="small"
  style={{ marginBottom: 24 }}
  title={
    <span>
      {t('scheduler.process')}{' '}
      <Tag color={isSchedulerOnline ? 'green' : 'red'}>
        {isSchedulerOnline ? t('status.running') : t('status.offline')}
      </Tag>
      {scheduler && isSchedulerOnline && (
        <Typography.Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
          {t('scheduler.uptime')}: {formatInterval(scheduler.process.uptime_seconds)}
          {' | '}
          {t('scheduler.lastHeartbeat')}: {scheduler.process.last_heartbeat ? formatDateTime(scheduler.process.last_heartbeat, i18n.language) : '-'}
        </Typography.Text>
      )}
    </span>
  }
>
  <Table
    dataSource={scheduler?.jobs ?? []}
    rowKey="name"
    size="small"
    pagination={false}
    columns={[
      { title: t('scheduler.jobName'), dataIndex: 'name', width: 100 },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 100,
        render: (s: string) => <StatusBadge status={s} />,
      },
      {
        title: t('scheduler.interval'),
        dataIndex: 'interval_seconds',
        width: 100,
        render: (v: number) => formatInterval(v),
      },
      {
        title: t('scheduler.lastRun'),
        dataIndex: 'last_run_at',
        render: (v: string | null) => v ? formatDateTime(v, i18n.language) : '-',
      },
      {
        title: t('scheduler.nextRun'),
        dataIndex: 'next_run_at',
        render: (v: string | null) => v ? formatDateTime(v, i18n.language) : '-',
      },
      {
        title: t('scheduler.errors'),
        dataIndex: 'error_count',
        width: 80,
        render: (v: number) => (
          <span style={v > 0 ? { color: '#ff4d4f', fontWeight: 600 } : undefined}>{v}</span>
        ),
      },
      {
        title: t('common.action'),
        width: 160,
        render: (_: unknown, record: { name: string; status: string }) => (
          <span>
            {record.status !== 'paused' ? (
              <>
                <Tooltip title={!isSchedulerOnline ? t('scheduler.processOffline') : undefined}>
                  <Button
                    size="small"
                    disabled={!isSchedulerOnline}
                    onClick={() => handleSchedulerAction('trigger', record.name)}
                  >
                    {t('scheduler.trigger')}
                  </Button>
                </Tooltip>{' '}
                <Tooltip title={!isSchedulerOnline ? t('scheduler.processOffline') : undefined}>
                  <Button
                    size="small"
                    danger
                    disabled={!isSchedulerOnline}
                    onClick={() => handleSchedulerAction('pause', record.name)}
                  >
                    {t('scheduler.pause')}
                  </Button>
                </Tooltip>
              </>
            ) : (
              <Tooltip title={!isSchedulerOnline ? t('scheduler.processOffline') : undefined}>
                <Button
                  size="small"
                  type="primary"
                  disabled={!isSchedulerOnline}
                  onClick={() => handleSchedulerAction('resume', record.name)}
                >
                  {t('scheduler.resume')}
                </Button>
              </Tooltip>
            )}
          </span>
        ),
      },
    ]}
  />
</Card>
```

- [ ] **Step 6: 验证 TypeScript 编译无误**

Run: `cd web && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 7: 验证 Vite 开发构建无误**

Run: `cd web && npx vite build`
Expected: 构建成功

- [ ] **Step 8: Commit**

```bash
git add web/src/pages/Dashboard.tsx
git commit -m "feat(scheduler-card): integrate scheduler card into Dashboard page"
```

---

### Task 7: 冒烟验证

- [ ] **Step 1: 全量构建前端**

Run: `cd web && npm run build`
Expected: 构建成功，无报错

- [ ] **Step 2: 验证所有 JSON locale 文件 key 数量一致**

Run: `cd web && node -e "const fs=require('fs'); ['zh-CN','en-US','es-ES'].forEach(l => { const keys=Object.keys(JSON.parse(fs.readFileSync('src/i18n/locales/'+l+'.json','utf8'))); console.log(l+': '+keys.length+' keys') })"`
Expected: 三个文件 key 数量相同

- [ ] **Step 3: Commit 最终状态（如有修正）**

如果 Step 1-2 发现问题并修正，提交修正。
