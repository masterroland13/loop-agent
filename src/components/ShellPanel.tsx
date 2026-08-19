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
  const [copied, setCopied] = useState(false)
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
    <div
      className={[
        'overflow-hidden rounded-xl border bg-[var(--bg-elevated)] transition-shadow',
        pending
          ? 'border-[var(--border)] border-l-2 border-l-[var(--accent-solid)] shadow-[0_0_28px_rgba(134,59,255,0.12)]'
          : 'border-[var(--border)]',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-w-0 flex-1 text-left"
        >
          <div className="truncate font-mono text-xs text-[var(--text-h)]">
            <span className="mr-1 text-[var(--text-dim)]">{expanded ? '▾' : '▸'}</span>$ {shell.command}
            <button
              type="button"
              title="复制命令"
              onClick={(e) => {
                e.stopPropagation()
                navigator.clipboard.writeText(shell.command).then(() => {
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
                })
              }}
              className="ml-1.5 inline-flex items-center text-[var(--text-dim)] hover:text-[var(--text-h)]"
            >
              {copied ? (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3 w-3 text-emerald-400">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3 w-3">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
              )}
            </button>
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
                className="rounded-md bg-[var(--accent-solid)] px-2.5 py-1 text-xs font-medium text-white transition-all hover:brightness-110 active:scale-[0.96] disabled:opacity-40"
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
