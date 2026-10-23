import { useEffect, useLayoutEffect, useState } from 'react'
import { useT } from '../i18n'
import type { PendingPatch } from '../types'

interface DiffPanelProps {
  patches: PendingPatch[]
  onApply: (id: string) => void
  onReject: (id: string) => void
  onApplyPartial?: (id: string, hunkIds: number[]) => void
  onRetry?: (id: string) => void
  busyId?: string | null
  /** Activity timeline focus — scroll + highlight matching card. */
  focusId?: string | null
}

function isActionablePatch(status: PendingPatch['status']) {
  return (
    status === 'pending' ||
    status === 'rejected' ||
    status === 'failed' ||
    status === 'timeout' ||
    status === 'partial'
  )
}

export function DiffPanel({
  patches,
  onApply,
  onReject,
  onApplyPartial,
  onRetry,
  busyId,
  focusId,
}: DiffPanelProps) {
  const t = useT()
  const visible = patches.filter((p) => p.status !== 'cancelled')
  const actionable = visible.filter((p) => isActionablePatch(p.status))
  const applied = visible.filter((p) => p.status === 'applied')
  const [showApplied, setShowApplied] = useState(false)
  const [highlightId, setHighlightId] = useState<string | null>(null)

  useLayoutEffect(() => {
    if (!focusId) return
    const patch = patches.find((p) => p.id === focusId && p.status !== 'cancelled')
    if (!patch) return
    if (patch.status === 'applied') setShowApplied(true)
  }, [focusId, patches])

  useEffect(() => {
    if (!focusId) return
    if (!patches.some((p) => p.id === focusId && p.status !== 'cancelled')) return
    const timer = window.setTimeout(() => {
      const el = document.getElementById(`gate-patch-${focusId}`)
      el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      setHighlightId(focusId)
    }, 30)
    const clear = window.setTimeout(() => setHighlightId(null), 2200)
    return () => {
      window.clearTimeout(timer)
      window.clearTimeout(clear)
    }
  }, [focusId, showApplied, patches])

  if (visible.length === 0) return null

  const renderCard = (patch: PendingPatch) => (
    <DiffCard
      key={patch.id}
      patch={patch}
      busy={busyId === patch.id}
      highlighted={highlightId === patch.id}
      onApply={() => onApply(patch.id)}
      onReject={() => onReject(patch.id)}
      onApplyPartial={onApplyPartial ? (ids) => onApplyPartial(patch.id, ids) : undefined}
      onRetry={onRetry ? () => onRetry(patch.id) : undefined}
    />
  )

  return (
    <div className="mx-auto mb-3 w-full max-w-3xl">
      <div className="max-h-[min(36vh,280px)] space-y-2 overflow-y-auto overflow-x-hidden overscroll-contain pr-0.5">
        {actionable.map(renderCard)}
        {applied.length > 0 && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)]">
            <button
              type="button"
              onClick={() => setShowApplied((v) => !v)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[var(--text-muted)] hover:text-[var(--text-h)]"
            >
              <span className="text-[var(--text-dim)]">{showApplied ? '▾' : '▸'}</span>
              <span>{t('gate.appliedCount', { n: applied.length })}</span>
            </button>
            {showApplied && (
              <div className="space-y-2 border-t border-[var(--border-subtle)] px-2 pb-2 pt-2">
                {applied.map(renderCard)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

interface DiffHunk {
  index: number
  header: string
  lines: string[]
}

function parseHunks(unifiedDiff: string): DiffHunk[] {
  const lines = unifiedDiff.split('\n')
  const hunks: DiffHunk[] = []
  let current: DiffHunk | null = null
  let idx = 0
  for (const line of lines) {
    if (line.startsWith('@@')) {
      current = { index: idx, header: line, lines: [] }
      hunks.push(current)
      idx++
      continue
    }
    if (current) current.lines.push(line)
  }
  return hunks
}

function DiffCard({
  patch,
  busy,
  highlighted,
  onApply,
  onReject,
  onApplyPartial,
  onRetry,
}: {
  patch: PendingPatch
  busy: boolean
  highlighted?: boolean
  onApply: () => void
  onReject: () => void
  onApplyPartial?: (hunkIds: number[]) => void
  onRetry?: () => void
}) {
  const t = useT()
  const pending = patch.status === 'pending'
  const rejected = patch.status === 'rejected'
  const failed = patch.status === 'failed' || patch.status === 'timeout'
  const partial = patch.status === 'partial'
  const retryable = failed || rejected
  const [expanded, setExpanded] = useState(pending || failed || rejected || partial)
  const [selectedHunks, setSelectedHunks] = useState<Set<number>>(() => {
    const count = patch.hunk_count ?? 0
    return new Set(Array.from({ length: count }, (_, i) => i))
  })
  const hunks = parseHunks(patch.unified_diff || '')
  const hasHunks = hunks.length > 0
  const allSelected = selectedHunks.size === hunks.length
  const noneSelected = selectedHunks.size === 0

  useEffect(() => {
    if (highlighted) setExpanded(true)
  }, [highlighted])

  const statusLabel =
    patch.status === 'applied'
      ? t('gate.applied')
      : partial
        ? t('gate.partial')
        : patch.status === 'failed'
          ? t('gate.failed')
          : patch.status === 'timeout'
            ? t('gate.timeout')
            : rejected
              ? t('gate.rejected')
              : pending
                ? t('gate.pending')
                : patch.status

  const toggleHunk = (idx: number) => {
    setSelectedHunks((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const toggleAll = () => {
    if (allSelected) {
      setSelectedHunks(new Set())
    } else {
      setSelectedHunks(new Set(hunks.map((h) => h.index)))
    }
  }

  return (
    <div
      id={`gate-patch-${patch.id}`}
      data-gate-kind="patch"
      data-gate-id={patch.id}
      className={[
        'overflow-hidden rounded-xl border bg-[var(--bg-elevated)] transition-[box-shadow,border-color] duration-300',
        highlighted
          ? 'border-[var(--accent)] shadow-[0_0_0_2px_var(--accent-bg),0_0_28px_rgba(134,59,255,0.25)]'
          : 'border-[var(--border)]',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-w-0 flex-1 truncate text-left font-mono text-xs text-[var(--text-h)]"
        >
          <span className="mr-1 text-[var(--text-dim)]">{expanded ? '▾' : '▸'}</span>
          {patch.is_new_file ? `${t('gate.newFile')} ` : `${t('gate.modify')} `}
          {patch.path}
          <span
            className={[
              'ml-2 rounded px-1.5 py-0.5 text-[10px] font-sans',
              patch.status === 'applied'
                ? 'bg-emerald-500/15 text-emerald-300'
                : patch.status === 'failed' || patch.status === 'timeout'
                  ? 'bg-red-500/15 text-red-300'
                  : partial
                    ? 'bg-sky-500/15 text-sky-300'
                    : rejected
                      ? 'bg-amber-500/15 text-amber-300'
                      : 'bg-[var(--surface)] text-[var(--text-muted)]',
            ].join(' ')}
          >
            {statusLabel}
          </span>
        </button>
        <div className="flex shrink-0 gap-1.5">
          {pending && (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={onReject}
                className="rounded-md px-2.5 py-1 text-xs text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)] disabled:opacity-40"
              >
                {t('common.reject')}
              </button>
              {hasHunks && onApplyPartial && !allSelected && !noneSelected && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onApplyPartial([...selectedHunks].sort())}
                  className="rounded-md bg-sky-500/20 px-2.5 py-1 text-xs font-medium text-sky-300 hover:bg-sky-500/30 disabled:opacity-40"
                >
                  {busy
                    ? '…'
                    : t('gate.applySelected', { n: selectedHunks.size, total: hunks.length })}
                </button>
              )}
              <button
                type="button"
                disabled={busy || (hasHunks && noneSelected)}
                onClick={hasHunks && !allSelected && onApplyPartial ? () => onApplyPartial([...selectedHunks].sort()) : onApply}
                className="rounded-md bg-[var(--accent-solid)] px-2.5 py-1 text-xs font-medium text-white transition-all hover:brightness-110 active:scale-[0.96] disabled:opacity-40"
              >
                {busy ? '…' : t('common.apply')}
              </button>
            </>
          )}
          {retryable && onRetry && (
            <button
              type="button"
              disabled={busy}
              onClick={onRetry}
              className="rounded-md bg-amber-500/20 px-2.5 py-1 text-xs font-medium text-amber-300 hover:bg-amber-500/30 disabled:opacity-40"
            >
              {busy ? '…' : t('common.retry')}
            </button>
          )}
        </div>
      </div>
      {expanded && (
        <div>
          {hasHunks && pending && (
            <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-1.5">
              <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="h-3 w-3 rounded accent-[var(--accent)]"
                />
                {t('gate.selectAll')}
              </label>
              <span className="text-[10px] text-[var(--text-dim)]">
                {t('gate.hunkCount', { n: selectedHunks.size, total: hunks.length })}
              </span>
            </div>
          )}
          <pre className="max-h-64 overflow-auto px-3 py-2 font-mono text-[11px] leading-5">
            {patch.error && <div className="mb-1 text-red-400">{patch.error}</div>}
            {hasHunks ? (
              hunks.map((hunk) => (
                <div key={hunk.index}>
                  <div
                    className="flex items-center gap-1.5 text-sky-400"
                  >
                    {pending && (
                      <input
                        type="checkbox"
                        checked={selectedHunks.has(hunk.index)}
                        onChange={() => toggleHunk(hunk.index)}
                        className="h-3 w-3 shrink-0 rounded accent-[var(--accent)]"
                      />
                    )}
                    <span>{hunk.header}</span>
                  </div>
                  {hunk.lines.map((line, i) => (
                    <div
                      key={i}
                      className={
                        line.startsWith('+') && !line.startsWith('+++')
                          ? 'bg-emerald-500/10 text-emerald-300'
                          : line.startsWith('-') && !line.startsWith('---')
                            ? 'bg-red-500/10 text-red-300'
                            : 'text-[var(--text-muted)]'
                      }
                    >
                      {line || ' '}
                    </div>
                  ))}
                </div>
              ))
            ) : (
              (patch.unified_diff || '').split('\n').slice(0, 200).map((line, i) => (
                <div
                  key={i}
                  className={
                    line.startsWith('+') && !line.startsWith('+++')
                      ? 'bg-emerald-500/10 text-emerald-300'
                      : line.startsWith('-') && !line.startsWith('---')
                        ? 'bg-red-500/10 text-red-300'
                        : line.startsWith('@@')
                          ? 'text-sky-400'
                          : 'text-[var(--text-muted)]'
                  }
                >
                  {line || ' '}
                </div>
              ))
            )}
          </pre>
        </div>
      )}
    </div>
  )
}
