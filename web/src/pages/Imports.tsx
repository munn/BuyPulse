import { Progress, Table, Typography } from 'antd'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getImports } from '../api/endpoints'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime } from '../utils/format'
import type { ImportJobItem } from '../types'

export default function Imports() {
  const { t, i18n } = useTranslation()
  const [jobs, setJobs] = useState<ImportJobItem[]>([])

  const hasRunning = jobs.some((j) => j.status === 'running')

  const fetchJobs = useCallback(() => {
    getImports().then((r) => setJobs(r.data)).catch(() => {})
  }, [])

  usePolling(fetchJobs, hasRunning ? 5_000 : 30_000)

  return (
    <div>
      <Typography.Title level={4}>{t('imports.title')}</Typography.Title>

      <Table
        dataSource={jobs}
        rowKey="id"
        size="small"
        pagination={{ pageSize: 20 }}
        columns={[
          { title: t('imports.filename'), dataIndex: 'filename', ellipsis: true },
          {
            title: t('common.status'),
            dataIndex: 'status',
            width: 160,
            render: (status: string, record: ImportJobItem) => {
              if (status === 'running' && record.total > 0) {
                const pct = Math.round(
                  (record.processed / record.total) * 100
                )
                return <Progress percent={pct} size="small" />
              }
              return <StatusBadge status={status} />
            },
          },
          { title: t('imports.total'), dataIndex: 'total', width: 80 },
          { title: t('imports.added'), dataIndex: 'added', width: 80 },
          { title: t('imports.skipped'), dataIndex: 'skipped', width: 80 },
          {
            title: t('imports.error'),
            dataIndex: 'error_message',
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: t('imports.created'),
            dataIndex: 'created_at',
            width: 160,
            render: (d: string) => formatDateTime(d, i18n.language),
          },
        ]}
      />
    </div>
  )
}
