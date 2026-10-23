import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from 'react'
import { en } from './en'
import { formatMessage, lookup, normalizeLocale, type Locale, type MessageTree } from './types'
import { zh } from './zh'

const catalogs: Record<Locale, MessageTree> = { zh, en }

type TranslateFn = (key: string, vars?: Record<string, string | number>) => string

type I18nValue = {
  locale: Locale
  t: TranslateFn
}

const I18nContext = createContext<I18nValue | null>(null)

export function translate(
  locale: Locale,
  key: string,
  vars?: Record<string, string | number>,
): string {
  const primary = lookup(catalogs[locale], key)
  const fallback = locale === 'zh' ? undefined : lookup(catalogs.zh, key)
  return formatMessage(primary ?? fallback ?? key, vars)
}

export function applyDocumentLang(locale: Locale) {
  document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
}

export function I18nProvider({
  locale,
  children,
}: {
  locale: Locale
  children: ReactNode
}) {
  const normalized = normalizeLocale(locale)
  useEffect(() => {
    applyDocumentLang(normalized)
  }, [normalized])

  const t = useCallback<TranslateFn>(
    (key, vars) => translate(normalized, key, vars),
    [normalized],
  )

  const value = useMemo(() => ({ locale: normalized, t }), [normalized, t])
  return createElement(I18nContext.Provider, { value }, children)
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext)
  if (!ctx) {
    // Safe fallback before provider mounts (should be rare).
    return {
      locale: 'zh',
      t: (key, vars) => translate('zh', key, vars),
    }
  }
  return ctx
}

export function useT(): TranslateFn {
  return useI18n().t
}

export type { Locale }
export { normalizeLocale }
