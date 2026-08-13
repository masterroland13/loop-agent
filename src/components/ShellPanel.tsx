import { useState } from 'react'
import type { PendingShell } from '../types'

interface ShellPanelProps {
  shells: PendingShell[]
  onApply: (id: string) => void
  onReject: (id: string) => void
  onRetry?: (id: string) => void
  busyId?: string | null
}

export function ShellPanel({ shells, onApply, onReject, onRetry, busyId }: ShellPanelProps) {
  const cards = shells.filter((s) => s.status !== 'cancelled')
  if (cards.length === 0) return null

  return (
    <div className="mx-auto mb-3 w-full max-w-3xl space-y-3">
      {cards.map((shell) => (
        <ShellCard
          key={shell.id}
          shell={shell}
          busy={busyId === shell.id || shell.status === 'running'}
          onApply={() => onApply(shell.id)}
          onReject={() => onReject(shell.id)}
          onRetry={onRetry ? () => onRetry(shell.id) : undefined}
        />
      ))}
    </div>
  )
}

function ShellCard({
  shell,
  busy,
  onApply,
  onReject,
  onRetry,
}: {
  shell: PendingShell
  busy: boolean
  onApply: () => void
  onReject: () => void
  onRetry?: () => void
}) {
  const pending = shell.status === 'pending'
  const rejected = shell.status === 'rejected'
  const failed = shell.status === 'failed' || shell.status === 'timeout'
  const retryable = failed || rejected
  const [expanded, setExpanded] = useState(pending || shell.status === 'running' || failed || rejected)
  const output = [shell.stdout, shell.stderr].filter(Boolean).join('\n').slice(0, 4000)
  const statusLabel =
    shell.status === 'done'
      ? `exit ${shell.exit_code ?? '?'}`
      : shell.status === 'running'
        ? '运行中'
        : shell.status === 'failed'
          ? '失败'
          : shell.status === 'timeout'
            ? '超时'
            : rejected
              ? '已拒绝'
              : '待运行'

  return (
    <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)]">
      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-w-0 flex-1 text-left"
        >
          <div className="truncate font-mono text-xs text-[var(--text-h)]">
            <span className="mr-1 text-[var(--text-dim)]">{expanded ? '▾' : '▸'}</span>$ {shell.command}
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--text-dim)]">
            <span>cwd: {shell.cwd}</span>
            <span
              className={[
                'rounded px-1.5 py-0.5 text-[10px]',
                shell.status === 'done' && (shell.exit_code ?? 1) === 0
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : shell.status === 'failed' ||
                      shell.status === 'timeout' ||
                      (shell.status === 'done' && (shell.exit_code ?? 0) !== 0)
                    ? 'bg-red-500/15 text-red-300'
                    : rejected
                      ? 'bg-amber-500/15 text-amber-300'
                      : shell.status === 'running'
                        ? 'bg-sky-500/15 text-sky-300'
                        : 'bg-[var(--surface)] text-[var(--text-muted)]',
              ].join(' ')}
            >
              {statusLabel}
            </span>
          </div>
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
                {busy ? '…' : 'Run'}
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
      {expanded && (output || shell.error) && (
        <pre className="max-h-48 overflow-auto px-3 py-2 font-mono text-[11px] leading-5 text-[var(--text-muted)]">
          {shell.error ? <div className="text-red-400">{shell.error}</div> : null}
          {output || null}
        </pre>
      )}
    </div>
  )
}
