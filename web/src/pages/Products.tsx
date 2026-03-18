import { PlusOutlined, UploadOutlined } from '@ant-design/icons'
import { Button, Col, Input, Modal, Row, Select, Space, Table, Typography, Upload, message } from 'antd'
import { useCallback, useState } from 'react'
import { addProduct, batchUpdateProducts, getProducts, importProducts } from '../api/endpoints'
import ProductDrawer from '../components/ProductDrawer'
import StatusBadge from '../components/StatusBadge'
import { usePolling } from '../hooks/usePolling'
import type { ProductItem } from '../types'

export default function Products() {
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
      message.success(`Added ${addValue.trim()}`)
      setAddModal(false)
      setAddValue('')
      fetchProducts()
    } catch {
      message.error('Failed to add product')
    } finally {
      setAddLoading(false)
    }
  }

  const handleImport = async (file: File) => {
    try {
      await importProducts(file)
      message.success('Import started')
      fetchProducts()
    } catch {
      message.error('Import failed')
    }
  }

  const handleBatchUpdate = async (action: string) => {
    if (selectedRowKeys.length === 0) return
    try {
      await batchUpdateProducts(selectedRowKeys, action)
      message.success(`${action === 'activate' ? 'Activated' : 'Deactivated'} ${selectedRowKeys.length} products`)
      setSelectedRowKeys([])
      fetchProducts()
    } catch {
      message.error('Batch update failed')
    }
  }

  const formatPrice = (cents: number | null) =>
    cents != null ? `$${(cents / 100).toFixed(2)}` : '-'

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys: React.Key[]) => setSelectedRowKeys(keys as number[]),
  }

  return (
    <div>
      <Typography.Title level={4}>Products</Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }} align="middle">
        <Col flex="auto">
          <Row gutter={8}>
            <Col>
              <Input.Search
                placeholder="Search platform ID or title"
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
                placeholder="Platform"
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
                placeholder="Status"
                allowClear
                style={{ width: 120 }}
                onChange={(v) => {
                  setStatus(v)
                  setPage(1)
                }}
                options={[
                  { value: 'active', label: 'Active' },
                  { value: 'inactive', label: 'Inactive' },
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
                  { value: 'electronics', label: 'Electronics' },
                  { value: 'home', label: 'Home & Garden' },
                  { value: 'clothing', label: 'Clothing' },
                  { value: 'sports', label: 'Sports' },
                  { value: 'toys', label: 'Toys' },
                  { value: 'books', label: 'Books' },
                  { value: 'other', label: 'Other' },
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
                Add ASIN
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
                <Button icon={<UploadOutlined />}>Import</Button>
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
            {selectedRowKeys.length} item(s) selected
          </Typography.Text>
          <Space>
            <Button
              size="small"
              type="primary"
              onClick={() => handleBatchUpdate('activate')}
            >
              Activate
            </Button>
            <Button
              size="small"
              danger
              onClick={() => handleBatchUpdate('deactivate')}
            >
              Deactivate
            </Button>
            <Button
              size="small"
              onClick={() => setSelectedRowKeys([])}
            >
              Clear
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
          { title: 'Platform ID', dataIndex: 'platform_id', width: 140 },
          { title: 'Title', dataIndex: 'title', ellipsis: true, render: (v: string | null) => v || '-' },
          { title: 'Platform', dataIndex: 'platform', width: 100 },
          {
            title: 'Status',
            dataIndex: 'is_active',
            width: 90,
            render: (active: boolean) => (
              <StatusBadge status={active ? 'active' : 'inactive'} />
            ),
          },
          {
            title: 'Price',
            dataIndex: 'current_price',
            width: 90,
            render: (v: number | null) => formatPrice(v),
          },
          {
            title: 'Updated',
            dataIndex: 'updated_at',
            width: 160,
            render: (d: string) => new Date(d).toLocaleString(),
          },
        ]}
      />

      <Modal
        title="Add ASIN"
        open={addModal}
        onOk={handleAdd}
        onCancel={() => {
          setAddModal(false)
          setAddValue('')
        }}
        confirmLoading={addLoading}
      >
        <Input
          placeholder="Enter ASIN (e.g. B09V3KXJPB)"
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
