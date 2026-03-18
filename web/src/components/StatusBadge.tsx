import { Tag } from 'antd'
import { useTranslation } from 'react-i18next'

const colorMap: Record<string, string> = {
  online: 'green',
  idle: 'orange',
  offline: 'red',
  pending: 'blue',
  running: 'processing',
  completed: 'green',
  failed: 'red',
  active: 'green',
  inactive: 'default',
  success: 'green',
}

export default function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  return <Tag color={colorMap[status] || 'default'}>{t(`status.${status}`, status)}</Tag>
}
