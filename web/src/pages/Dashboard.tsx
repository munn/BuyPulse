import { Card, Col, Row, Table, Typography } from 'antd'
import ReactECharts from 'echarts-for-react'
import { useCallback, useState } from 'react'
import {
  getOverview,
  getRecentFailures,
  getThroughput,
  getWorkers,
} from '../api/endpoints'
import StatsCard from '../components/StatsCard'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import type {
  OverviewStats,
  RecentFailure,
  ThroughputBucket,
  WorkerStatus,
} from '../types'

export default function Dashboard() {
  const [stats, setStats] = useState<OverviewStats | null>(null)
  const [throughput, setThroughput] = useState<ThroughputBucket[]>([])
  const [workers, setWorkers] = useState<WorkerStatus[]>([])
  const [failures, setFailures] = useState<RecentFailure[]>([])

  const fetchAll = useCallback(() => {
    getOverview().then((r) => setStats(r.data))
    getThroughput().then((r) => setThroughput(r.data))
    getWorkers().then((r) => setWorkers(r.data))
    getRecentFailures().then((r) => setFailures(r.data))
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
        name: 'Completed',
        type: 'bar',
        data: throughput.map((b) => b.count),
        itemStyle: { color: '#1890ff' },
      },
    ],
  }

  return (
    <div>
      <Typography.Title level={4}>Dashboard</Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title="Products"
            value={stats?.products_total ?? '-'}
            today={stats?.products_today}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title="Crawled"
            value={stats?.crawled_total ?? '-'}
            today={stats?.crawled_today}
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title="Success Rate (24h)"
            value={
              stats ? `${(stats.success_rate_24h * 100).toFixed(1)}%` : '-'
            }
          />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatsCard
            title="Price Records"
            value={stats?.price_records_total ?? '-'}
          />
        </Col>
      </Row>

      <Card title="Throughput (24h)" style={{ marginBottom: 24 }}>
        {throughput.length > 0 ? (
          <ReactECharts option={throughputOption} style={{ height: 250 }} />
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
            No throughput data
          </div>
        )}
      </Card>

      <Typography.Title level={5}>Workers</Typography.Title>
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
                Platform: {w.platform} | Tasks: {w.tasks_completed} | Last
                heartbeat: {new Date(w.last_heartbeat).toLocaleTimeString()}
              </Typography.Text>
            </Card>
          </Col>
        ))}
        {workers.length === 0 && (
          <Col span={24}>
            <Typography.Text type="secondary">
              No workers registered
            </Typography.Text>
          </Col>
        )}
      </Row>

      <Typography.Title level={5}>Recent Failures</Typography.Title>
      <Table
        dataSource={failures}
        rowKey="task_id"
        size="small"
        pagination={false}
        columns={[
          { title: 'Platform ID', dataIndex: 'platform_id' },
          { title: 'Platform', dataIndex: 'platform' },
          {
            title: 'Error',
            dataIndex: 'error_message',
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: 'Time',
            dataIndex: 'updated_at',
            render: (d: string) => new Date(d).toLocaleString(),
          },
        ]}
      />
    </div>
  )
}
