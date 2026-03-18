import { Empty, Typography } from 'antd'
import { useTranslation } from 'react-i18next'

export default function EmptyState({
  description,
}: {
  description?: string
}) {
  const { t } = useTranslation()
  return (
    <Empty
      description={
        <Typography.Text type="secondary">{description ?? t('common.noData')}</Typography.Text>
      }
    />
  )
}
