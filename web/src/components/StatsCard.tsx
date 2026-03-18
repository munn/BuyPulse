import { Card, Statistic } from 'antd'

interface Props {
  title: string
  value: number | string
  suffix?: string
  today?: number
}

export default function StatsCard({ title, value, suffix, today }: Props) {
  return (
    <Card>
      <Statistic title={title} value={value} suffix={suffix} />
      {today !== undefined && (
        <span style={{ color: '#52c41a', fontSize: 12 }}>+{today} today</span>
      )}
    </Card>
  )
}
