import en from './en.json'
import fa from './fa.json'

const translations: Record<string, any> = { en, fa }

export function t(lang: string, key: string, params?: Record<string, any>): string {
  const keys = key.split('.')
  let value: any = translations[lang] || translations['en']
  for (const k of keys) {
    value = value?.[k]
    if (!value) break
  }
  if (typeof value !== 'string') return key
  if (params) {
    return Object.entries(params).reduce((acc, [pk, pv]) => acc.replace(`{${pk}}`, String(pv)), value)
  }
  return value
}
