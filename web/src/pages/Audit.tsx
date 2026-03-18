import { Col, Row, Select, Table, Typography } from 'antd'
import { useCallback, useState } from 'react'
import { getAuditLog } from '../api/endpoints'
import { usePolling } from '../hooks/usePolling'
import type { AuditLogItem } from '../types'

export default function Audit() {
  const [logs, setLogs] = useState<AuditLogItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [action, setAction] = useState<string | undefined>(undefined)
  const [resourceType, setResourceType] = useState<string | undefined>(
    undefined
  )

  const fetchLogs = useCallback(() => {
    const params: Record<string, unknown> = { page, page_size: pageSize }
    if (action) params.action = action
    if (resourceType) params.resource_type = resourceType
    getAuditLog(params).then((r) => {
      setLogs(r.data.items)
      setTotal(r.data.total)
    })
  }, [page, pageSize, action, resourceType])

  usePolling(fetchLogs, 30_000)

  const truncateJson = (obj: Record<string, unknown> | null) => {
    if (!obj) return '-'
    const str = JSON.stringify(obj)
    return str.length > 80 ? str.slice(0, 80) + '...' : str
  }

  return (
    <div>
      <Typography.Title level={4}>Audit Log</Typography.Title>

      <Row gutter={8} style={{ marginBottom: 16 }}>
        <Col>
          <Select
            placeholder="Action"
            allowClear
            style={{ width: 160 }}
            onChange={(v) => {
              setAction(v)
              setPage(1)
            }}
            options={[
              { value: 'login', label: 'Login' },
              { value: 'logout', label: 'Logout' },
              { value: 'create', label: 'Create' },
              { value: 'update', label: 'Update' },
              { value: 'delete', label: 'Delete' },
              { value: 'import', label: 'Import' },
              { value: 'trigger', label: 'Trigger' },
              { value: 'retry', label: 'Retry' },
            ]}
          />
        </Col>
        <Col>
          <Select
            placeholder="Resource Type"
            allowClear
            style={{ width: 160 }}
            onChange={(v) => {
              setResourceType(v)
              setPage(1)
            }}
            options={[
              { value: 'session', label: 'Session' },
              { value: 'product', label: 'Product' },
              { value: 'crawl_task', label: 'Crawl Task' },
              { value: 'import_job', label: 'Import Job' },
            ]}
          />
        </Col>
      </Row>

      <Table
        dataSource={logs}
        rowKey="id"
        size="small"
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
          },
        }}
        columns={[
          { title: 'Action', dataIndex: 'action', width: 90 },
          { title: 'Resource', dataIndex: 'resource_type', width: 110 },
          {
            title: 'Resource ID',
            dataIndex: 'resource_id',
            width: 100,
            render: (v: string | null) => v || '-',
          },
          {
            title: 'Details',
            dataIndex: 'details',
            ellipsis: true,
            render: (v: Record<string, unknown> | null) => truncateJson(v),
          },
          { title: 'IP', dataIndex: 'ip_address', width: 120 },
          {
            title: 'Time',
            dataIndex: 'created_at',
            width: 160,
            render: (d: string) => new Date(d).toLocaleString(),
          },
        ]}
      />
    </div>
  )
}
