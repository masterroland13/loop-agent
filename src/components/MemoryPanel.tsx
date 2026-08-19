import { useState } from 'react'
import type { PendingMemory } from '../types'

interface MemoryPanelProps {
  memories: PendingMemory[]
  onApply: (id: string) => void
  onReject: (id: string) => void
  busyId?: string | null
}

export function MemoryPanel({ memories, onApply, onReject, busyId }: MemoryPanelProps) {
  const visible = memories.filter((m) => m.status !== 'cancelled')
  if (visible.length === 0) return null

  return (
    <div className="mx-auto mb-3 w-full max-w-3xl space-y-3">
      {visible.map((memory) => (
        <MemoryCard
          key={memory.id}
          memory={memory}
          busy={busyId === memory.id}
          onApply={() => onApply(memory.id)}
          onReject={() => onReject(memory.id)}
        />
      ))}
    </div>
  )
}

function MemoryCard({
  memory,
  busy,
  onApply,
  onReject,
}: {
  memory: PendingMemory
  busy: boolean
  onApply: () => void
  onReject: () => void
}) {
  const pending = memory.status === 'pending'
  const rejected = memory.status === 'rejected'
  const [expanded, setExpanded] = useState(pending || rejected)
  const statusLabel =
    memory.status === 'applied'
      ? '已写入'
      : memory.status === 'failed'
        ? '失败'
        : memory.status === 'timeout'
          ? '超时'
          : rejected
            ? '已拒绝'
            : pending
              ? '待确认'
              : memory.status

  return (
    <div
      className={[
        'overflow-hidden rounded-xl border bg-[var(--bg-elevated)] transition-shadow',
        pending
          ? 'border-[var(--border)] border-l-2 border-l-[var(--accent-solid)] shadow-[0_0_28px_rgba(134,59,255,0.12)]'
          : 'border-[var(--border)]',
      ].join(' ')}
    >      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-w-0 flex-1 truncate text-left text-xs text-[var(--text-h)]"
        >
          <span className="mr-1 text-[var(--text-dim)]">{expanded ? '▾' : '▸'}</span>
          记忆 USER.md
          <span className="ml-1.5 font-mono text-[var(--text-muted)]">
            ({memory.mode === 'append' ? '追加' : '替换'})
          </span>
          <span
            className={[
              'ml-2 rounded px-1.5 py-0.5 text-[10px] font-sans',
              memory.status === 'applied'
                ? 'bg-emerald-500/15 text-emerald-300'
                : memory.status === 'failed' || memory.status === 'timeout'
                  ? 'bg-red-500/15 text-red-300'
                  : rejected
                    ? 'bg-amber-500/15 text-amber-300'
                    : 'bg-[var(--surface)] text-[var(--text-muted)]',
            ].join(' ')}
          >
            {statusLabel}
          </span>
        </button>
        {pending && (
          <div className="flex shrink-0 gap-1.5">
            <button
              type="button"
              disabled={busy}
              onClick={onApply}
              className="rounded-md bg-[var(--accent-solid)] px-2.5 py-1 text-xs font-medium text-white transition-all hover:brightness-110 active:scale-[0.96] disabled:opacity-50"
            >
              {busy ? '…' : 'Apply'}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onReject}
              className="rounded-md border border-[var(--border)] px-2.5 py-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-h)] disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        )}
      </div>
      {expanded && (
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-[11px] leading-relaxed text-[var(--text-muted)]">
          {memory.preview || memory.content}
        </pre>
      )}
      {memory.error && (
        <div className="border-t border-[var(--border-subtle)] px-3 py-2 text-xs text-red-400">
          {memory.error}
        </div>
      )}
    </div>
  )
}
