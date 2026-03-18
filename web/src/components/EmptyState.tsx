import { Empty, Typography } from 'antd'

export default function EmptyState({
  description = 'No data',
}: {
  description?: string
}) {
  return (
    <Empty
      description={
        <Typography.Text type="secondary">{description}</Typography.Text>
      }
    />
  )
}
