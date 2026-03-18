import { RedoOutlined, SendOutlined } from '@ant-design/icons'
import {
  Button,
  Card,
  Col,
  Input,
  Modal,
  Row,
  Table,
  Tabs,
  Typography,
  message,
} from 'antd'
import { useCallback, useState } from 'react'
import {
  enqueueAsins,
  getCrawlerStats,
  getCrawlerTasks,
  getWorkers,
  retryAllFailed,
  retryTask,
} from '../api/endpoints'
import StatsCard from '../components/StatsCard'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import type { CrawlStats, CrawlTaskItem, WorkerStatus } from '../types'

export default function Crawler() {
  const [stats, setStats] = useState<CrawlStats | null>(null)
  const [workers, setWorkers] = useState<WorkerStatus[]>([])
  const [tasks, setTasks] = useState<CrawlTaskItem[]>([])
  const [tasksTotal, setTasksTotal] = useState(0)
  const [tabKey, setTabKey] = useState('failed')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [enqueueModal, setEnqueueModal] = useState(false)
  const [enqueueValue, setEnqueueValue] = useState('')
  const [enqueueLoading, setEnqueueLoading] = useState(false)

  const fetchAll = useCallback(() => {
    getCrawlerStats().then((r) => setStats(r.data)).catch(() => {})
    getWorkers().then((r) => setWorkers(r.data)).catch(() => {})
    getCrawlerTasks({ status: tabKey, page, page_size: pageSize }).then(
      (r) => {
        setTasks(r.data.items)
        setTasksTotal(r.data.total)
      }
    ).catch(() => {})
  }, [tabKey, page, pageSize])

  usePolling(fetchAll, 10_000)

  const handleEnqueue = async () => {
    const ids = enqueueValue
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (ids.length === 0) return
    setEnqueueLoading(true)
    try {
      const r = await enqueueAsins(ids)
      message.success(`Enqueued ${(r.data as { enqueued: number }).enqueued} tasks`)
      setEnqueueModal(false)
      setEnqueueValue('')
      fetchAll()
    } catch {
      message.error('Failed to enqueue')
    } finally {
      setEnqueueLoading(false)
    }
  }

  const handleRetryAll = async () => {
    try {
      const r = await retryAllFailed()
      message.success(`Retried ${(r.data as { retried: number }).retried} tasks`)
      fetchAll()
    } catch {
      message.error('Retry failed')
    }
  }

  const handleRetryOne = async (id: number) => {
    try {
      await retryTask(id)
      message.success('Task retried')
      fetchAll()
    } catch {
      message.error('Retry failed')
    }
  }

  return (
    <div>
      <Typography.Title level={4}>Crawler</Typography.Title>

      <Row gutter={8} style={{ marginBottom: 16 }}>
        <Col>
          <Button
            icon={<SendOutlined />}
            type="primary"
            onClick={() => setEnqueueModal(true)}
          >
            Enqueue ASINs
          </Button>
        </Col>
        <Col>
          <Button icon={<RedoOutlined />} onClick={handleRetryAll}>
            Retry All Failed
          </Button>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title="Pending" value={stats?.pending ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title="Running" value={stats?.running ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title="Completed" value={stats?.completed ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title="Failed" value={stats?.failed ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard
            title="Speed"
            value={stats?.speed_per_hour ?? '-'}
            suffix="/hr"
          />
        </Col>
      </Row>

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
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                {w.current_task_id
                  ? `Task #${w.current_task_id}`
                  : 'No active task'}{' '}
                | Heartbeat: {new Date(w.last_heartbeat).toLocaleTimeString()}
              </div>
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

      <Typography.Title level={5}>Task Queue</Typography.Title>
      <Tabs
        activeKey={tabKey}
        onChange={(k) => {
          setTabKey(k)
          setPage(1)
        }}
        items={['failed', 'pending', 'running', 'completed'].map((s) => ({
          key: s,
          label: s.charAt(0).toUpperCase() + s.slice(1),
        }))}
      />
      <Table
        dataSource={tasks}
        rowKey="id"
        size="small"
        pagination={{
          current: page,
          pageSize,
          total: tasksTotal,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
          },
        }}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 60 },
          { title: 'Platform ID', dataIndex: 'platform_id', width: 140 },
          { title: 'Platform', dataIndex: 'platform', width: 90 },
          {
            title: 'Status',
            dataIndex: 'status',
            width: 100,
            render: (s: string) => <StatusBadge status={s} />,
          },
          { title: 'Priority', dataIndex: 'priority', width: 70 },
          { title: 'Retries', dataIndex: 'retry_count', width: 70 },
          {
            title: 'Error',
            dataIndex: 'error_message',
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: 'Updated',
            dataIndex: 'updated_at',
            width: 160,
            render: (d: string) => new Date(d).toLocaleString(),
          },
          ...(tabKey === 'failed'
            ? [
                {
                  title: 'Action',
                  width: 80,
                  render: (_: unknown, record: CrawlTaskItem) => (
                    <Button
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleRetryOne(record.id)
                      }}
                    >
                      Retry
                    </Button>
                  ),
                },
              ]
            : []),
        ]}
      />

      <Modal
        title="Enqueue ASINs"
        open={enqueueModal}
        onOk={handleEnqueue}
        onCancel={() => {
          setEnqueueModal(false)
          setEnqueueValue('')
        }}
        confirmLoading={enqueueLoading}
      >
        <Input.TextArea
          rows={6}
          placeholder="Enter ASINs (one per line or comma-separated)"
          value={enqueueValue}
          onChange={(e) => setEnqueueValue(e.target.value)}
        />
      </Modal>
    </div>
  )
}
