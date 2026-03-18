import { Descriptions, Drawer, Table, Tabs } from 'antd'
import { useEffect, useState } from 'react'
import { getFetchRuns, getPriceHistory, getProduct } from '../api/endpoints'
import type { FetchRunItem, PricePoint, ProductDetail } from '../types'
import PriceChart from './PriceChart'
import StatusBadge from './StatusBadge'

interface Props {
  productId: number | null
  onClose: () => void
}

export default function ProductDrawer({ productId, onClose }: Props) {
  const [detail, setDetail] = useState<ProductDetail | null>(null)
  const [prices, setPrices] = useState<PricePoint[]>([])
  const [runs, setRuns] = useState<FetchRunItem[]>([])

  useEffect(() => {
    if (!productId) return
    getProduct(productId).then((r) => setDetail(r.data))
    getPriceHistory(productId).then((r) => setPrices(r.data))
    getFetchRuns(productId).then((r) => setRuns(r.data))
  }, [productId])

  const formatPrice = (cents: number | null) =>
    cents != null ? `$${(cents / 100).toFixed(2)}` : '-'

  return (
    <Drawer
      title={detail?.platform_id || 'Product'}
      open={!!productId}
      onClose={onClose}
      width={640}
    >
      <Tabs
        items={[
          {
            key: 'price',
            label: 'Price History',
            children: <PriceChart data={prices} />,
          },
          {
            key: 'runs',
            label: 'Crawl Runs',
            children: (
              <Table
                dataSource={runs}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 10 }}
                columns={[
                  {
                    title: 'Status',
                    dataIndex: 'status',
                    render: (s: string) => <StatusBadge status={s} />,
                  },
                  { title: 'Points', dataIndex: 'points_extracted' },
                  {
                    title: 'Confidence',
                    dataIndex: 'ocr_confidence',
                    render: (v: number | null) =>
                      v ? `${(v * 100).toFixed(0)}%` : '-',
                  },
                  {
                    title: 'Date',
                    dataIndex: 'created_at',
                    render: (d: string) => new Date(d).toLocaleString(),
                  },
                ]}
              />
            ),
          },
          {
            key: 'info',
            label: 'Info',
            children: detail ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="Platform">
                  {detail.platform}
                </Descriptions.Item>
                <Descriptions.Item label="Platform ID">
                  {detail.platform_id}
                </Descriptions.Item>
                <Descriptions.Item label="Title">
                  {detail.title || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="Category">
                  {detail.category || '-'}
                </Descriptions.Item>
                <Descriptions.Item label="Status">
                  {detail.is_active ? 'Active' : 'Inactive'}
                </Descriptions.Item>
                <Descriptions.Item label="Lowest">
                  {formatPrice(detail.lowest_price)}
                </Descriptions.Item>
                <Descriptions.Item label="Highest">
                  {formatPrice(detail.highest_price)}
                </Descriptions.Item>
                <Descriptions.Item label="Current">
                  {formatPrice(detail.current_price)}
                </Descriptions.Item>
                <Descriptions.Item label="First Seen">
                  {new Date(detail.first_seen).toLocaleDateString()}
                </Descriptions.Item>
              </Descriptions>
            ) : null,
          },
        ]}
      />
    </Drawer>
  )
}
