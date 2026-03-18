import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'
import esES from './locales/es-ES.json'
import { getSafeLocale } from './useLocale'

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('locale') : null

i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zhCN },
    'en-US': { translation: enUS },
    'es-ES': { translation: esES },
  },
  lng: getSafeLocale(stored),
  fallbackLng: 'zh-CN',
  interpolation: { escapeValue: true },
  returnNull: false,
})

export default i18n
