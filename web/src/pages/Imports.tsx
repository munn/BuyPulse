import { Progress, Table, Typography } from 'antd'
import { useCallback, useState } from 'react'
import { getImports } from '../api/endpoints'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import type { ImportJobItem } from '../types'

export default function Imports() {
  const [jobs, setJobs] = useState<ImportJobItem[]>([])

  const hasRunning = jobs.some((j) => j.status === 'running')

  const fetchJobs = useCallback(() => {
    getImports().then((r) => setJobs(r.data))
  }, [])

  usePolling(fetchJobs, hasRunning ? 5_000 : 30_000)

  return (
    <div>
      <Typography.Title level={4}>Imports</Typography.Title>

      <Table
        dataSource={jobs}
        rowKey="id"
        size="small"
        pagination={{ pageSize: 20 }}
        columns={[
          { title: 'Filename', dataIndex: 'filename', ellipsis: true },
          {
            title: 'Status',
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
          { title: 'Total', dataIndex: 'total', width: 80 },
          { title: 'Added', dataIndex: 'added', width: 80 },
          { title: 'Skipped', dataIndex: 'skipped', width: 80 },
          {
            title: 'Error',
            dataIndex: 'error_message',
            ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: 'Created',
            dataIndex: 'created_at',
            width: 160,
            render: (d: string) => new Date(d).toLocaleString(),
          },
        ]}
      />
    </div>
  )
}
