import { Select } from 'antd'
import { useTranslation } from 'react-i18next'
import { useLocaleContext, SUPPORTED_LOCALES, type SupportedLocale } from '../i18n/useLocale'

export default function LangSwitcher() {
  const { t } = useTranslation()
  const { locale, changeLocale } = useLocaleContext()

  const labelMap: Record<SupportedLocale, string> = {
    'zh-CN': t('lang.zhCN'),
    'en-US': t('lang.enUS'),
    'es-ES': t('lang.esES'),
  }

  return (
    <Select
      value={locale}
      onChange={changeLocale}
      options={SUPPORTED_LOCALES.map(l => ({ value: l, label: labelMap[l] }))}
      variant="borderless"
      style={{ width: 100 }}
      popupMatchSelectWidth={false}
    />
  )
}
