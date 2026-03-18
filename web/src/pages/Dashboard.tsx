import { Card, Col, Row, Table, Typography } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  getOverview,
  getRecentFailures,
  getThroughput,
  getWorkers,
} from '../api/endpoints'
import StatsCard from '../components/StatsCard'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime } from '../utils/format'
import type {
  OverviewStats,
  RecentFailure,
  ThroughputBucket,
  WorkerStatus,
} from '../types'

export default function Dashboard() {
  const { t, i18n } = useTranslation()
  const [stats, setStats] = useState<OverviewStats | null>(null)
  const [throughput, setThroughput] = useState<ThroughputBucket[]>([])
  const [workers, setWorkers] = useState<WorkerStatus[]>([])
  const [failures, setFailures] = useState<RecentFailure[]>([])

  const fetchAll = useCallback(() => {
    getOverview().then((r) => setStats(r.data)).catch(() => {})
    getThroughput().then((r) => setThroughput(r.data)).catch(() => {})
    getWorkers().then((r) => setWorkers(r.data)).catch(() => {})
    getRecentFailures().then((r) => setFailures(r.data)).catch(() => {})
  }, [])

  usePolling(fetchAll, 30_000)

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
