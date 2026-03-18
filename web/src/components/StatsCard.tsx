import { Card, Statistic } from 'antd'
import { useTranslation } from 'react-i18next'

interface Props {
  title: string
  value: number | string
  suffix?: string
  today?: number
}

export default function StatsCard({ title, value, suffix, today }: Props) {
  const { t } = useTranslation()
  return (
    <Card>
      <Statistic title={title} value={value} suffix={suffix} />
      {today !== undefined && (
        <span style={{ color: '#52c41a', fontSize: 12 }}>{t('stats.today', { count: today })}</span>
      )}
    </Card>
  )
}
