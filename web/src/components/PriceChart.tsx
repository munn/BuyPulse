import ReactECharts from 'echarts-for-react'
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
  if (data.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
        No price data
      </div>
    )
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
      axisLabel: { formatter: '${value}' },
    },
    series: Object.entries(grouped).map(([type, d]) => ({
      name: type,
      type: 'line',
      data: d.prices,
      smooth: true,
      lineStyle: { color: COLORS[type] || '#999' },
      itemStyle: { color: COLORS[type] || '#999' },
    })),
    legend: { data: Object.keys(grouped) },
  }

  return <ReactECharts option={option} style={{ height: 300 }} />
}
