import { useEffect, useState } from 'react'
import { fetchModels } from '../api/agent'

/** Offline fallback — must match gateway aliases (no stale kimi-k2p6). */
export const FALLBACK_MODELS = [
  'kimi-k3',
  'kimi-k3-256k',
  'kimi-for-coding',
  'kimi-for-coding-highspeed',
  'bailian-kimi-k2.7-code',
]

interface ModelPickerProps {
  isOpen: boolean
  current: string
  onClose: () => void
  onSelect: (model: string) => void
}

export function ModelPicker({ isOpen, current, onClose, onSelect }: ModelPickerProps) {
  const [models, setModels] = useState<string[]>(FALLBACK_MODELS)
  const [source, setSource] = useState<string>('fallback')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchModels()
      .then((res) => {
        if (cancelled) return
        const ids = res.models.map((m) => m.id).filter(Boolean)
        if (ids.length > 0) {
          setModels(ids)
          setSource(res.source)
        }
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载模型列表失败')
        setModels(FALLBACK_MODELS)
        setSource('fallback')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  if (!isOpen) return null

  const display = models.includes(current) ? models : [current, ...models]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full max-w-sm overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-xl">
        <div className="border-b border-[var(--border-subtle)] px-4 py-3">
          <h3 className="text-sm font-semibold text-[var(--text-h)]">选择模型</h3>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            {loading
              ? '正在从网关拉取…'
              : source === 'provider'
                ? '来自 LiteLLM 可用列表'
                : '本地备用列表（网关不可达时）'}
          </p>
        </div>
        {error && (
          <div className="border-b border-[var(--border-subtle)] px-4 py-2 text-xs text-amber-400">
            {error}
          </div>
        )}
        <div className="max-h-[50vh] overflow-y-auto p-2">
          {display.map((model) => {
            const active = model === current
            const unavailable = !models.includes(model)
            return (
              <button
                key={model}
                type="button"
                onClick={() => {
                  onSelect(model)
                  onClose()
                }}
                className={[
                  'mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition-colors',
                  active
                    ? 'bg-[var(--accent-bg)] text-[var(--text-h)]'
                    : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
                ].join(' ')}
              >
                <span className="font-medium">{model}</span>
                <span className="text-xs text-[var(--text-dim)]">
                  {unavailable ? '不可用' : active ? '当前' : ''}
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** @deprecated use FALLBACK_MODELS */
export const MODELS = FALLBACK_MODELS
