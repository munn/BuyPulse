import { Button, Card, Col, message, Modal, Row, Table, Tag, Tooltip, Typography } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getOverview,
  getRecentFailures,
  getSchedulerStatus,
  getThroughput,
  getWorkers,
  pauseSchedulerJob,
  resumeSchedulerJob,
  triggerSchedulerJob,
} from '../api/endpoints'
import StatsCard from '../components/StatsCard'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime, formatInterval } from '../utils/format'
import type {
  OverviewStats,
  RecentFailure,
  SchedulerStatusResponse,
  ThroughputBucket,
  WorkerStatus,
} from '../types'

export default function Dashboard() {
  const { t, i18n } = useTranslation()
  const [stats, setStats] = useState<OverviewStats | null>(null)
  const [throughput, setThroughput] = useState<ThroughputBucket[]>([])
  const [workers, setWorkers] = useState<WorkerStatus[]>([])
  const [failures, setFailures] = useState<RecentFailure[]>([])
  const [scheduler, setScheduler] = useState<SchedulerStatusResponse | null>(null)

  const fetchAll = useCallback(() => {
    getOverview().then((r) => setStats(r.data)).catch(() => {})
    getThroughput().then((r) => setThroughput(r.data)).catch(() => {})
    getWorkers().then((r) => setWorkers(r.data)).catch(() => {})
    getRecentFailures().then((r) => setFailures(r.data)).catch(() => {})
    getSchedulerStatus().then((r) => setScheduler(r.data)).catch(() => {})
  }, [])

  usePolling(fetchAll, 30_000)

  const isSchedulerOnline = scheduler?.process.status === 'running'

  const confirmKeys = {
    trigger: 'scheduler.confirmTrigger',
    pause: 'scheduler.confirmPause',
    resume: 'scheduler.confirmResume',
  } as const

  const handleSchedulerAction = useCallback(
    (action: 'trigger' | 'pause' | 'resume', jobName: string) => {
      Modal.confirm({
        title: t(confirmKeys[action]),
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

  const throughputOption = {
    tooltip: { trigger: 'axis' as const },
    xAxis: {
      type: 'category' as const,
      data: throughput.map((b) => b.hour),
      axisLabel: { rotate: 45 },
    },
    yAxis: { type: 'value' as const },
    series: [
      {
        name: t('dashboard.seriesCompleted'),
        type: 'bar',
        data: throughput.map((b) => b.count),
        itemStyle: { color: '#1890ff' },
      },
    ],
  }

  return (
    <div>
      <Typography.Title level={4}>{t('dashboard.title')}</Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title={t('dashboard.products')}
            value={stats?.products_total ?? '-'}
            today={stats?.products_today}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title={t('dashboard.crawled')}
            value={stats?.crawled_total ?? '-'}
            today={stats?.crawled_today}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title={t('dashboard.successRate')}
            value={
              stats ? `${stats.success_rate_24h.toFixed(1)}%` : '-'
            }
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title={t('dashboard.priceRecords')}
            value={stats?.price_records_total ?? '-'}
          />
        </Col>
      </Row>

      <Card title={t('dashboard.throughput')} style={{ marginBottom: 24 }}>
        {throughput.length > 0 ? (
          <ReactECharts option={throughputOption} style={{ height: 250 }} />
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
            {t('dashboard.noThroughput')}
          </div>
        )}
      </Card>

      <Typography.Title level={5}>{t('dashboard.workers')}</Typography.Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {workers.map((w) => (
          <Col xs={24} sm={12} lg={8} key={w.worker_id}>
            <Card size="small">
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <Typography.Text strong>{w.worker_id}</Typography.Text>
                <StatusBadge status={w.status} />
              </div>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <span>{t('dashboard.workerPlatform')} {w.platform}</span>
                {' | '}
                <span>{t('dashboard.workerTasks')} {w.tasks_completed}</span>
                {' | '}
                <span>{t('dashboard.lastHeartbeat')}: {formatDateTime(w.last_heartbeat, i18n.language)}</span>
              </Typography.Text>
            </Card>
          </Col>
        ))}
        {workers.length === 0 && (
          <Col span={24}>
            <Typography.Text type="secondary">
              {t('dashboard.noWorkers')}
            </Typography.Text>
          </Col>
        )}
      </Row>

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

      <Typography.Title level={5}>{t('dashboard.recentFailures')}</Typography.Title>
      <Table
        dataSource={failures}
        rowKey="task_id"
        size="small"
        pagination={false}
        columns={[
          { title: t('common.platformId'), dataIndex: 'platform_id' },
          { title: t('common.platform'), dataIndex: 'platform' },
          {
            title: t('common.error'),
            dataIndex: 'error_message',
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: t('common.updated'),
            dataIndex: 'updated_at',
            render: (d: string) => formatDateTime(d, i18n.language),
          },
        ]}
      />
    </div>
  )
}
