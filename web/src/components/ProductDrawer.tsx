import { Descriptions, Drawer, Table, Tabs } from 'antd'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getFetchRuns, getPriceHistory, getProduct } from '../api/endpoints'
import { formatDateTime, formatPrice } from '../utils/format'
import type { FetchRunItem, PricePoint, ProductDetail } from '../types'
import PriceChart from './PriceChart'
import StatusBadge from './StatusBadge'

interface Props {
  productId: number | null
  onClose: () => void
}

export default function ProductDrawer({ productId, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const [detail, setDetail] = useState<ProductDetail | null>(null)
  const [prices, setPrices] = useState<PricePoint[]>([])
  const [runs, setRuns] = useState<FetchRunItem[]>([])

  useEffect(() => {
    if (!productId) return
    setDetail(null)
    setPrices([])
    setRuns([])
    getProduct(productId).then((r) => setDetail(r.data))
    getPriceHistory(productId).then((r) => setPrices(r.data))
    getFetchRuns(productId).then((r) => setRuns(r.data))
  }, [productId])

  return (
    <Drawer
      title={detail?.platform_id || t('common.noData')}
      open={!!productId}
      onClose={onClose}
      width={640}
    >
      <Tabs
        items={[
          {
            key: 'price',
            label: t('drawer.priceHistory'),
            children: <PriceChart data={prices} />,
          },
          {
            key: 'runs',
            label: t('drawer.crawlRuns'),
            children: (
              <Table
                dataSource={runs}
                rowKey="id"
                size="small"
                pagination={{ pageSize: 10 }}
                columns={[
                  {
                    title: t('common.status'),
                    dataIndex: 'status',
                    render: (s: string) => <StatusBadge status={s} />,
                  },
                  { title: t('drawer.points'), dataIndex: 'points_extracted' },
                  {
                    title: t('drawer.confidence'),
                    dataIndex: 'ocr_confidence',
                    render: (v: number | null) =>
                      v ? `${(v * 100).toFixed(0)}%` : '-',
                  },
                  {
                    title: t('drawer.date'),
                    dataIndex: 'created_at',
                    render: (d: string) => formatDateTime(d, i18n.language),
                  },
                ]}
              />
            ),
          },
          {
            key: 'info',
            label: t('drawer.info'),
            children: detail ? (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label={t('common.platform')}>
                  {detail.platform}
                </Descriptions.Item>
                <Descriptions.Item label={t('common.platformId')}>
                  {detail.platform_id}
                </Descriptions.Item>
                <Descriptions.Item label={t('products.title_col')}>
                  {detail.title || '-'}
                </Descriptions.Item>
                <Descriptions.Item label={t('drawer.category')}>
                  {detail.category || '-'}
                </Descriptions.Item>
                <Descriptions.Item label={t('common.status')}>
                  {detail.is_active ? t('status.active') : t('status.inactive')}
                </Descriptions.Item>
                <Descriptions.Item label={t('drawer.lowest')}>
                  {formatPrice(detail.lowest_price, i18n.language)}
                </Descriptions.Item>
                <Descriptions.Item label={t('drawer.highest')}>
                  {formatPrice(detail.highest_price, i18n.language)}
                </Descriptions.Item>
                <Descriptions.Item label={t('drawer.current')}>
                  {formatPrice(detail.current_price, i18n.language)}
                </Descriptions.Item>
                <Descriptions.Item label={t('drawer.firstSeen')}>
                  {formatDateTime(detail.first_seen, i18n.language)}
                </Descriptions.Item>
              </Descriptions>
            ) : null,
          },
        ]}
      />
    </Drawer>
  )
}
