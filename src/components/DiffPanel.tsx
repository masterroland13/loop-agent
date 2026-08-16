import { useState } from 'react'
import type { PendingPatch } from '../types'

interface DiffPanelProps {
  patches: PendingPatch[]
  onApply: (id: string) => void
  onReject: (id: string) => void
  onRetry?: (id: string) => void
  busyId?: string | null
}

export function DiffPanel({ patches, onApply, onReject, onRetry, busyId }: DiffPanelProps) {
  // Keep rejected visible (Retry); hide only cancelled noise.
  const visible = patches.filter((p) => p.status !== 'cancelled')
  if (visible.length === 0) return null

  return (
    <div className="mx-auto mb-3 w-full max-w-3xl space-y-3">
      {visible.map((patch) => (
        <DiffCard
          key={patch.id}
          patch={patch}
          busy={busyId === patch.id}
          onApply={() => onApply(patch.id)}
          onReject={() => onReject(patch.id)}
          onRetry={onRetry ? () => onRetry(patch.id) : undefined}
        />
      ))}
    </div>
  )
}

function DiffCard({
  patch,
  busy,
  onApply,
  onReject,
  onRetry,
}: {
  patch: PendingPatch
  busy: boolean
  onApply: () => void
  onReject: () => void
  onRetry?: () => void
}) {
  const pending = patch.status === 'pending'
  const rejected = patch.status === 'rejected'
  const failed = patch.status === 'failed' || patch.status === 'timeout'
  const retryable = failed || rejected
  const [expanded, setExpanded] = useState(pending || failed || rejected)
  const lines = (patch.unified_diff || '').split('\n').slice(0, 200)
  const statusLabel =
    patch.status === 'applied'
      ? '已应用'
      : patch.status === 'failed'
        ? '失败'
        : patch.status === 'timeout'
          ? '超时'
          : rejected
            ? '已拒绝'
            : pending
              ? '待审批'
              : patch.status

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)]">
      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-w-0 flex-1 truncate text-left font-mono text-xs text-[var(--text-h)]"
        >
          <span className="mr-1 text-[var(--text-dim)]">{expanded ? '▾' : '▸'}</span>
          {patch.is_new_file ? '新建 ' : '修改 '}
          {patch.path}
          <span
            className={[
              'ml-2 rounded px-1.5 py-0.5 text-[10px] font-sans',
              patch.status === 'applied'
                ? 'bg-emerald-500/15 text-emerald-300'
                : patch.status === 'failed' || patch.status === 'timeout'
                  ? 'bg-red-500/15 text-red-300'
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
                Reject
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={onApply}
                className="rounded-md bg-[var(--text-h)] px-2.5 py-1 text-xs font-medium text-[var(--bg)] disabled:opacity-40"
              >
                {busy ? '…' : 'Apply'}
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
              {busy ? '…' : 'Retry'}
            </button>
          )}
        </div>
      </div>
      {expanded && (
        <pre className="max-h-64 overflow-auto px-3 py-2 font-mono text-[11px] leading-5">
          {patch.error && <div className="mb-1 text-red-400">{patch.error}</div>}
          {lines.map((line, i) => (
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
          ))}
        </pre>
      )}
    </div>
  )
}
