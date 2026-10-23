import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchModelProfiles, fetchModels } from '../api/agent'
import { useT } from '../i18n'
import { loadRecentModels, rememberModel } from '../utils/recentModels'
import { FALLBACK_MODELS } from './modelFallbacks'

interface ModelPickerProps {
  isOpen: boolean
  current: string
  /** Button bounds — panel opens just above (⋮-style), no full-screen modal. */
  anchor: DOMRect | null
  onClose: () => void
  onSelect: (model: string, profileId?: string | null) => void
  /** Session binding, so two profiles that share a model id stay distinct. */
  currentProfileId?: string | null
}

interface PickerEntry {
  id: string
  label: string
  /** Set when this row is one profile's default model. */
  profileId?: string
  /** Saved from prior use / custom id, not from profiles/gateway */
  fromRecent?: boolean
}

const PANEL =
  'rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] shadow-[0_8px_28px_rgba(0,0,0,0.45),0_0_0_1px_rgba(255,255,255,0.05)]'

function entryKey(entry: PickerEntry): string {
  return entry.profileId ? `p:${entry.profileId}` : `m:${entry.id}`
}

function resolveModelRow(
  catalog: PickerEntry[],
  modelId: string,
  preferProfileId?: string | null,
): PickerEntry {
  const hits = catalog.filter((entry) => entry.id === modelId)
  if (preferProfileId) {
    const bound = hits.find((entry) => entry.profileId === preferProfileId)
    if (bound) return bound
  }
  if (hits.length === 1) return hits[0]
  return { id: modelId, label: modelId, fromRecent: true }
}

function mergeDisplay(
  catalog: PickerEntry[],
  recent: string[],
  current: string,
  currentProfileId?: string | null,
): PickerEntry[] {
  const out: PickerEntry[] = []
  const seen = new Set<string>()

  const push = (entry: PickerEntry) => {
    const key = entryKey(entry)
    if (seen.has(key)) return
    seen.add(key)
    out.push(entry)
  }

  const trimmed = current.trim()
  if (trimmed) push(resolveModelRow(catalog, trimmed, currentProfileId))
  for (const id of recent) {
    if (id === trimmed) continue
    push(resolveModelRow(catalog, id))
  }
  for (const entry of catalog) push(entry)
  return out
}

export function ModelPicker({
  isOpen,
  current,
  anchor,
  onClose,
  onSelect,
  currentProfileId,
}: ModelPickerProps) {
  const t = useT()
  const [models, setModels] = useState<PickerEntry[]>([])
  const [recent, setRecent] = useState<string[]>(() => loadRecentModels())
  const [source, setSource] = useState<string>('fallback')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [customId, setCustomId] = useState('')
  const menuRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })

  useEffect(() => {
    if (!isOpen) return
    setRecent(loadRecentModels())
    setCustomId('')
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([fetchModelProfiles().catch(() => null), fetchModels().catch(() => null)])
      .then(([profiles, gateway]) => {
        if (cancelled) return
        const enabled = (profiles?.profiles ?? []).filter((p) => p.enabled)
        if (enabled.length > 0) {
          const modelIds = enabled.map((p) => p.model_id)
          const dupes = new Set(modelIds.filter((id, i) => modelIds.indexOf(id) !== i))
          setModels(
            enabled.map((p) => ({
              id: p.model_id,
              profileId: p.id,
              label: dupes.has(p.model_id) ? `${p.label} · ${p.model_id}` : p.model_id,
            })),
          )
          setSource('profiles')
          return
        }
        if (gateway && gateway.models.length > 0) {
          setModels(gateway.models.map((m) => ({ id: m.id, label: m.id })).filter((m) => m.id))
          setSource(gateway.source)
          return
        }
        setModels(FALLBACK_MODELS.map((id) => ({ id, label: id })))
        setSource('fallback')
      })
      .catch((err) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : t('model.loadFailed'))
        setModels(FALLBACK_MODELS.map((id) => ({ id, label: id })))
        setSource('fallback')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, t])

  const display = mergeDisplay(models, recent, current, currentProfileId)

  useLayoutEffect(() => {
    if (!isOpen || !anchor || !menuRef.current) return
    const menu = menuRef.current.getBoundingClientRect()
    const gap = 6
    let top = anchor.top - menu.height - gap
    let left = anchor.right - menu.width
    if (top < 8) top = Math.min(anchor.bottom + gap, window.innerHeight - menu.height - 8)
    if (left < 8) left = 8
    if (left + menu.width > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - menu.width - 8)
    }
    if (top + menu.height > window.innerHeight - 8) {
      top = Math.max(8, window.innerHeight - menu.height - 8)
    }
    setPos({ top, left })
  }, [isOpen, anchor, display.length, loading, error, customId])

  useEffect(() => {
    if (!isOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onPointer = (e: MouseEvent) => {
      const t = e.target as Node
      if (menuRef.current?.contains(t)) return
      if (t instanceof Element && t.closest('[data-model-picker-anchor]')) return
      onClose()
    }
    const tid = window.setTimeout(() => {
      window.addEventListener('keydown', onKey)
      window.addEventListener('mousedown', onPointer)
    }, 0)
    return () => {
      window.clearTimeout(tid)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onPointer)
    }
  }, [isOpen, onClose])

  const choose = (id: string, profileId?: string | null) => {
    const trimmed = id.trim()
    if (!trimmed) return
    let bound = profileId
    if (!bound) {
      const hits = models.filter((entry) => entry.id === trimmed && entry.profileId)
      if (hits.length === 1) bound = hits[0].profileId
    }
    setRecent(rememberModel(trimmed))
    onSelect(trimmed, bound)
    onClose()
  }

  const applyCustom = () => {
    choose(customId)
  }

  if (!isOpen || !anchor) return null

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      aria-label={t('model.pickerAria')}
      style={{ top: pos.top, left: pos.left }}
      className={`fixed z-[80] w-[min(280px,calc(100vw-16px))] overflow-hidden ${PANEL}`}
    >
      <div className="border-b border-[var(--border-subtle)] px-2.5 py-2">
        <div className="text-[12.5px] font-semibold leading-5 text-[var(--text-h)]">{t('model.pickerTitle')}</div>
        <p className="text-[11px] leading-4 text-[var(--text-muted)]">
          {loading
            ? t('model.loading')
            : source === 'profiles'
              ? t('model.sourceProfiles')
              : source === 'provider'
                ? t('model.sourceProvider')
                : t('model.sourceFallback')}
        </p>
      </div>
      {error && (
        <div className="border-b border-[var(--border-subtle)] px-2.5 py-1.5 text-[11px] text-amber-400">
          {error}
        </div>
      )}
      <div className="max-h-[min(280px,45vh)] overflow-y-auto px-1 py-1">
        {display.map((entry) => {
          const sameModel = entry.id === current.trim()
          const active = !sameModel
            ? false
            : currentProfileId
              ? entry.profileId
                ? entry.profileId === currentProfileId
                : !display.some(
                    (other) => other.profileId === currentProfileId && other.id === entry.id,
                  )
              : entry.profileId
                ? display.filter((other) => other.id === entry.id && other.profileId).length === 1
                : true
          return (
            <button
              key={entryKey(entry)}
              type="button"
              role="menuitem"
              onClick={() => choose(entry.id, entry.profileId)}
              className={[
                'mb-0.5 flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] leading-5 tracking-[0.01em] transition-colors duration-75',
                active
                  ? 'bg-[var(--surface-hover)] text-[var(--text-h)]'
                  : 'text-[var(--text-h)] hover:bg-[var(--surface-hover)]',
              ].join(' ')}
            >
              <span className="min-w-0 truncate font-medium">{entry.label}</span>
              <span className="shrink-0 text-[10px] text-[var(--text-dim)]">
                {active ? t('model.current') : ''}
              </span>
            </button>
          )
        })}
      </div>
      <div className="border-t border-[var(--border-subtle)] px-2 py-2">
        <p className="mb-1 text-[10.5px] leading-4 text-[var(--text-muted)]">{t('model.customHint')}</p>
        <div className="flex gap-1.5">
          <input
            type="text"
            value={customId}
            onChange={(e) => setCustomId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                applyCustom()
              }
            }}
            placeholder={t('model.customPlaceholder')}
            className="min-w-0 flex-1 rounded-md border border-[var(--border)] bg-[var(--bg)] px-2 py-1.5 text-[12.5px] text-[var(--text-h)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--accent)]"
          />
          <button
            type="button"
            onClick={applyCustom}
            disabled={!customId.trim()}
            className="shrink-0 rounded-md bg-[var(--accent-bg)] px-2.5 py-1.5 text-[12.5px] font-medium text-[var(--text-h)] disabled:opacity-40"
          >
            {t('model.use')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

/** @deprecated use FALLBACK_MODELS */
export const MODELS = FALLBACK_MODELS
