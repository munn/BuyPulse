import { PlusOutlined, UploadOutlined } from '@ant-design/icons'
import { Button, Col, Input, Modal, Row, Select, Space, Table, Typography, Upload, message } from 'antd'
import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { addProduct, batchUpdateProducts, getProducts, importProducts } from '../api/endpoints'
import ProductDrawer from '../components/ProductDrawer'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import { formatDateTime, formatPrice } from '../utils/format'
import type { ProductItem } from '../types'

export default function Products() {
  const { t, i18n } = useTranslation()
  const [data, setData] = useState<ProductItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [search, setSearch] = useState('')
  const [platform, setPlatform] = useState<string | undefined>(undefined)
  const [status, setStatus] = useState<string | undefined>(undefined)
  const [category, setCategory] = useState<string | undefined>(undefined)
  const [drawerId, setDrawerId] = useState<number | null>(null)
  const [addModal, setAddModal] = useState(false)
  const [addValue, setAddValue] = useState('')
  const [addLoading, setAddLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])

  const fetchProducts = useCallback(() => {
    const params: Record<string, unknown> = { page, page_size: pageSize }
    if (search) params.search = search
    if (platform) params.platform = platform
    if (status) params.status = status
    if (category) params.category = category
    getProducts(params).then((r) => {
      setData(r.data.items)
      setTotal(r.data.total)
    }).catch(() => {})
  }, [page, pageSize, search, platform, status, category])

  usePolling(fetchProducts, 30_000)

  const handleAdd = async () => {
    if (!addValue.trim()) return
    setAddLoading(true)
    try {
      await addProduct(addValue.trim())
      message.success(t('products.added', { value: addValue.trim() }))
      setAddModal(false)
      setAddValue('')
      fetchProducts()
    } catch {
      message.error(t('products.addFailed'))
    } finally {
      setAddLoading(false)
    }
  }

  const handleImport = async (file: File) => {
    try {
      await importProducts(file)
      message.success(t('products.importStarted'))
      fetchProducts()
    } catch {
      message.error(t('products.importFailed'))
    }
  }

  const handleBatchUpdate = async (action: string) => {
    if (selectedRowKeys.length === 0) return
    try {
      await batchUpdateProducts(selectedRowKeys, action)
      const actionLabel = action === 'activate' ? t('products.activate') : t('products.deactivate')
      message.success(t('products.batchDone', { action: actionLabel, count: selectedRowKeys.length }))
      setSelectedRowKeys([])
      fetchProducts()
    } catch {
      message.error(t('products.batchFailed'))
    }
  }

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys as number[]),
  }

  return (
    <div>
      <Typography.Title level={4}>{t('products.title')}</Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }} align="middle">
        <Col flex="auto">
          <Row gutter={8}>
            <Col>
              <Input.Search
                placeholder={t('products.search')}
                onSearch={(v) => {
                  setSearch(v)
                  setPage(1)
                }}
                allowClear
                style={{ width: 260 }}
              />
            </Col>
            <Col>
              <Select
                placeholder={t('common.platform')}
                allowClear
                style={{ width: 130 }}
                onChange={(v) => {
                  setPlatform(v)
                  setPage(1)
                }}
                options={[
                  { value: 'amazon', label: 'Amazon' },
                  { value: 'bestbuy', label: 'Best Buy' },
                  { value: 'walmart', label: 'Walmart' },
                ]}
              />
            </Col>
            <Col>
              <Select
                placeholder={t('common.status')}
                allowClear
                style={{ width: 120 }}
                onChange={(v) => {
                  setStatus(v)
                  setPage(1)
                }}
                options={[
                  { value: 'active', label: t('status.active') },
                  { value: 'inactive', label: t('status.inactive') },
                ]}
              />
            </Col>
            <Col>
              <Select
                placeholder="Category"
                allowClear
                style={{ width: 160 }}
                onChange={(v) => {
                  setCategory(v)
                  setPage(1)
                }}
                options={[
                  { value: 'electronics', label: t('products.category.electronics') },
                  { value: 'home', label: t('products.category.home') },
                  { value: 'clothing', label: t('products.category.clothing') },
                  { value: 'sports', label: t('products.category.sports') },
                  { value: 'toys', label: t('products.category.toys') },
                  { value: 'books', label: t('products.category.books') },
                  { value: 'other', label: t('products.category.other') },
                ]}
              />
            </Col>
          </Row>
        </Col>
        <Col>
          <Row gutter={8}>
            <Col>
              <Button
                icon={<PlusOutlined />}
                type="primary"
                onClick={() => setAddModal(true)}
              >
                {t('products.addAsin')}
              </Button>
            </Col>
            <Col>
              <Upload
                accept=".csv,.txt"
                showUploadList={false}
                beforeUpload={(file) => {
                  handleImport(file)
                  return false
                }}
              >
                <Button icon={<UploadOutlined />}>{t('products.import')}</Button>
              </Upload>
            </Col>
          </Row>
        </Col>
      </Row>

      {selectedRowKeys.length > 0 && (
        <div
          style={{
            marginBottom: 12,
            padding: '8px 16px',
            background: '#e6f7ff',
            border: '1px solid #91d5ff',
            borderRadius: 4,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <Typography.Text>
            {t('products.selected', { count: selectedRowKeys.length })}
          </Typography.Text>
          <Space>
            <Button
              size="small"
              type="primary"
              onClick={() => handleBatchUpdate('activate')}
            >
              {t('products.activate')}
            </Button>
            <Button
              size="small"
              danger
              onClick={() => handleBatchUpdate('deactivate')}
            >
              {t('products.deactivate')}
            </Button>
            <Button
              size="small"
              onClick={() => setSelectedRowKeys([])}
            >
              {t('products.clear')}
            </Button>
          </Space>
        </div>
      )}

      <Table
        dataSource={data}
        rowKey="id"
        size="small"
        rowSelection={rowSelection}
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
        onRow={(record) => ({
          onClick: () => setDrawerId(record.id),
          style: { cursor: 'pointer' },
        })}
        columns={[
          { title: t('common.platformId'), dataIndex: 'platform_id', width: 140 },
          { title: t('products.title_col'), dataIndex: 'title', ellipsis: true, render: (v: string | null) => v || '-' },
          { title: t('common.platform'), dataIndex: 'platform', width: 100 },
          {
            title: t('common.status'),
            dataIndex: 'is_active',
            width: 90,
            render: (active: boolean) => (
              <StatusBadge status={active ? 'active' : 'inactive'} />
            ),
          },
          {
            title: t('products.price'),
            dataIndex: 'current_price',
            width: 90,
            render: (v: number | null) => formatPrice(v, i18n.language),
          },
          {
            title: t('common.updated'),
            dataIndex: 'updated_at',
            width: 160,
            render: (d: string) => formatDateTime(d, i18n.language),
          },
        ]}
      />

      <Modal
        title={t('products.addAsin')}
        open={addModal}
        onOk={handleAdd}
        onCancel={() => {
          setAddModal(false)
          setAddValue('')
        }}
        confirmLoading={addLoading}
      >
        <Input
          placeholder={t('products.enterAsin')}
          value={addValue}
          onChange={(e) => setAddValue(e.target.value)}
          onPressEnter={handleAdd}
        />
      </Modal>

      <ProductDrawer
        productId={drawerId}
        onClose={() => setDrawerId(null)}
      />
    </div>
  )
}
