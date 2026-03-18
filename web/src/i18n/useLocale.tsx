import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import esES from 'antd/locale/es_ES'
import type { Locale } from 'antd/es/locale'
import { updateLocale as apiUpdateLocale } from '../api/endpoints'

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US', 'es-ES'] as const
export type SupportedLocale = typeof SUPPORTED_LOCALES[number]

const LOCALE_KEY = 'locale'

export function getSafeLocale(raw: string | null): SupportedLocale {
  return SUPPORTED_LOCALES.includes(raw as SupportedLocale)
    ? (raw as SupportedLocale)
    : 'zh-CN'
}

const antdLocaleMap: Record<SupportedLocale, Locale> = {
  'zh-CN': zhCN,
  'en-US': enUS,
  'es-ES': esES,
}

interface LocaleContextValue {
  locale: SupportedLocale
  antdLocale: Locale
  changeLocale: (l: SupportedLocale) => Promise<void>
  syncAfterLogin: (serverLocale: string) => Promise<void>
}

const LocaleContext = createContext<LocaleContextValue | null>(null)

export function LocaleProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation()
  const [locale, setLocale] = useState<SupportedLocale>(
    getSafeLocale(typeof localStorage !== 'undefined' ? localStorage.getItem(LOCALE_KEY) : null)
  )

  const antdLocale = antdLocaleMap[locale]

  const changeLocale = useCallback(async (newLocale: SupportedLocale) => {
    await i18n.changeLanguage(newLocale)
    setLocale(newLocale)
    localStorage.setItem(LOCALE_KEY, newLocale)
    // Always attempt server sync; 401 from unauthenticated requests is silently ignored
    apiUpdateLocale(newLocale).catch(() => {})
  }, [i18n])

  const syncAfterLogin = useCallback(async (serverLocale: string) => {
    const raw = localStorage.getItem(LOCALE_KEY)
    if (raw !== null) {
      apiUpdateLocale(getSafeLocale(raw)).catch(() => {})
    } else {
      const safe = getSafeLocale(serverLocale)
      await i18n.changeLanguage(safe)
      setLocale(safe)
      localStorage.setItem(LOCALE_KEY, safe)
    }
  }, [i18n])

  return (
    <LocaleContext value={{ locale, antdLocale, changeLocale, syncAfterLogin }}>
      {children}
    </LocaleContext>
  )
}

export function useLocaleContext() {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error('useLocaleContext must be used within LocaleProvider')
  return ctx
}
