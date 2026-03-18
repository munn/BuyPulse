import { Col, Row, Select, Table, Typography } from 'antd'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getAuditLog } from '../api/endpoints'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime } from '../utils/format'
import type { AuditLogItem } from '../types'

export default function Audit() {
  const { t, i18n } = useTranslation()
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
    }).catch(() => {})
  }, [page, pageSize, action, resourceType])

  usePolling(fetchLogs, 30_000)

  const truncateJson = (obj: Record<string, unknown> | null) => {
    if (!obj) return '-'
    const str = JSON.stringify(obj)
    return str.length > 80 ? str.slice(0, 80) + '...' : str
  }

  return (
    <div>
      <Typography.Title level={4}>{t('audit.title')}</Typography.Title>

      <Row gutter={8} style={{ marginBottom: 16 }}>
        <Col>
          <Select
            placeholder={t('audit.filterAction')}
            allowClear
            style={{ width: 160 }}
            onChange={(v) => {
              setAction(v)
              setPage(1)
            }}
            options={[
              { value: 'login', label: t('audit.action_login') },
              { value: 'logout', label: t('audit.action_logout') },
              { value: 'create', label: t('audit.action_create') },
              { value: 'update', label: t('audit.action_update') },
              { value: 'delete', label: t('audit.action_delete') },
              { value: 'import', label: t('audit.action_import') },
              { value: 'trigger', label: t('audit.action_trigger') },
              { value: 'retry', label: t('audit.action_retry') },
              { value: 'update_locale', label: t('audit.action_update_locale') },
            ]}
          />
        </Col>
        <Col>
          <Select
            placeholder={t('audit.filterResourceType')}
            allowClear
            style={{ width: 160 }}
            onChange={(v) => {
              setResourceType(v)
              setPage(1)
            }}
            options={[
              { value: 'session', label: t('audit.resource_session') },
              { value: 'product', label: t('audit.resource_product') },
              { value: 'crawl_task', label: t('audit.resource_crawlTask') },
              { value: 'import', label: t('audit.resource_import') },
              { value: 'user', label: t('audit.resource_user') },
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
          { title: t('audit.action'), dataIndex: 'action', width: 90 },
          { title: t('audit.resource'), dataIndex: 'resource_type', width: 110 },
          {
            title: t('audit.resourceId'),
            dataIndex: 'resource_id',
            width: 100,
            render: (v: string | null) => v || '-',
          },
          {
            title: t('audit.details'),
            dataIndex: 'details',
            ellipsis: true,
            render: (v: Record<string, unknown> | null) => truncateJson(v),
          },
          { title: t('audit.ip'), dataIndex: 'ip_address', width: 120 },
          {
            title: t('audit.time'),
            dataIndex: 'created_at',
            width: 160,
            render: (d: string) => formatDateTime(d, i18n.language),
          },
        ]}
      />
    </div>
  )
}
