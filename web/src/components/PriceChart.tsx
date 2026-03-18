import ReactECharts from 'echarts-for-react'
import { useTranslation } from 'react-i18next'
import { formatPrice } from '../utils/format'
import type { PricePoint } from '../types'

const COLORS: Record<string, string> = {
  amazon: '#1890ff',
  new: '#52c41a',
  used: '#fa8c16',
}

interface Props {
  data: PricePoint[]
}

export default function PriceChart({ data }: Props) {
  const { t, i18n } = useTranslation()

  if (data.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
        {t('chart.noData')}
      </div>
    )
  }

  const labelMap: Record<string, string> = {
    amazon: t('chart.amazon'),
    new: t('chart.new'),
    used: t('chart.used'),
  }

  const grouped: Record<string, { dates: string[]; prices: number[] }> = {}
  for (const p of data) {
    if (!grouped[p.price_type]) grouped[p.price_type] = { dates: [], prices: [] }
    grouped[p.price_type].dates.push(p.recorded_date)
    grouped[p.price_type].prices.push(p.price_cents / 100)
  }

  const firstKey = Object.keys(grouped)[0]
  const option = {
    tooltip: { trigger: 'axis' as const },
    xAxis: {
      type: 'category' as const,
      data: firstKey ? grouped[firstKey].dates : [],
    },
    yAxis: {
      type: 'value' as const,
      axisLabel: { formatter: (v: number) => formatPrice(v * 100, i18n.language) },
    },
    series: Object.entries(grouped).map(([type, d]) => ({
      name: labelMap[type] ?? type,
      type: 'line',
      data: d.prices,
      smooth: true,
      lineStyle: { color: COLORS[type] || '#999' },
      itemStyle: { color: COLORS[type] || '#999' },
    })),
    legend: { data: Object.keys(grouped).map((k) => labelMap[k] ?? k) },
  }

  return <ReactECharts option={option} style={{ height: 300 }} />
}
