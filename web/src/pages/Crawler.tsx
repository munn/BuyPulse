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
import { useTranslation } from 'react-i18next'
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
import { formatDateTime } from '../utils/format'
import type { CrawlStats, CrawlTaskItem, WorkerStatus } from '../types'

export default function Crawler() {
  const { t, i18n } = useTranslation()
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
      message.success(t('crawler.enqueueDone', { count: (r.data as { enqueued: number }).enqueued }))
      setEnqueueModal(false)
      setEnqueueValue('')
      fetchAll()
    } catch {
      message.error(t('crawler.enqueueFailed'))
    } finally {
      setEnqueueLoading(false)
    }
  }

  const handleRetryAll = async () => {
    try {
      const r = await retryAllFailed()
      message.success(t('crawler.retryDone', { count: (r.data as { retried: number }).retried }))
      fetchAll()
    } catch {
      message.error(t('crawler.retryFailed'))
    }
  }

  const handleRetryOne = async (id: number) => {
    try {
      await retryTask(id)
      message.success(t('crawler.taskRetried'))
      fetchAll()
    } catch {
      message.error(t('crawler.retryFailed'))
    }
  }

  return (
    <div>
      <Typography.Title level={4}>{t('crawler.title')}</Typography.Title>

      <Row gutter={8} style={{ marginBottom: 16 }}>
        <Col>
          <Button
            icon={<SendOutlined />}
            type="primary"
            onClick={() => setEnqueueModal(true)}
          >
            {t('crawler.enqueue')}
          </Button>
        </Col>
        <Col>
          <Button icon={<RedoOutlined />} onClick={handleRetryAll}>
            {t('crawler.retryAllFailed')}
          </Button>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title={t('crawler.pending')} value={stats?.pending ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title={t('crawler.running')} value={stats?.running ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title={t('crawler.completed')} value={stats?.completed ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard title={t('crawler.failed')} value={stats?.failed ?? '-'} />
        </Col>
        <Col xs={24} sm={12} lg={4}>
          <StatsCard
            title={t('crawler.speed')}
            value={stats?.speed_per_hour ?? '-'}
            suffix={t('crawler.perHour')}
          />
        </Col>
      </Row>

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
              <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
                {w.current_task_id
                  ? t('crawler.currentTask', { id: w.current_task_id })
                  : t('crawler.noActiveTask')}{' '}
                | {t('dashboard.lastHeartbeat')}: {formatDateTime(w.last_heartbeat, i18n.language)}
              </div>
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

      <Typography.Title level={5}>{t('crawler.taskQueue')}</Typography.Title>
      <Tabs
        activeKey={tabKey}
        onChange={(k) => {
          setTabKey(k)
          setPage(1)
        }}
        items={[
          { key: 'failed', label: t('crawler.failed') },
          { key: 'pending', label: t('crawler.pending') },
          { key: 'running', label: t('crawler.running') },
          { key: 'completed', label: t('crawler.completed') },
        ]}
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
          { title: t('crawler.id'), dataIndex: 'id', width: 60 },
          { title: t('common.platformId'), dataIndex: 'platform_id', width: 140 },
          { title: t('common.platform'), dataIndex: 'platform', width: 90 },
          {
            title: t('common.status'),
            dataIndex: 'status',
            width: 100,
            render: (s: string) => <StatusBadge status={s} />,
          },
          { title: t('crawler.priority'), dataIndex: 'priority', width: 70 },
          { title: t('crawler.retries'), dataIndex: 'retry_count', width: 70 },
          {
            title: t('common.error'),
            dataIndex: 'error_message',
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: t('common.updated'),
            dataIndex: 'updated_at',
            width: 160,
            render: (d: string) => formatDateTime(d, i18n.language),
          },
          ...(tabKey === 'failed'
            ? [
                {
                  title: t('common.action'),
                  width: 80,
                  render: (_: unknown, record: CrawlTaskItem) => (
                    <Button
                      size="small"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleRetryOne(record.id)
                      }}
                    >
                      {t('crawler.retry')}
                    </Button>
                  ),
                },
              ]
            : []),
        ]}
      />

      <Modal
        title={t('crawler.enqueue')}
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
          placeholder={t('crawler.enterAsins')}
          value={enqueueValue}
          onChange={(e) => setEnqueueValue(e.target.value)}
        />
      </Modal>
    </div>
  )
}
