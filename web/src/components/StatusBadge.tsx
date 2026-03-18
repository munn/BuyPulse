import { Tag } from 'antd'

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
  return <Tag color={colorMap[status] || 'default'}>{status}</Tag>
}
