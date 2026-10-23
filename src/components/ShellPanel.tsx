import { useEffect, useLayoutEffect, useState } from 'react'
import { useT } from '../i18n'
import type { PendingShell } from '../types'

interface ShellPanelProps {
  shells: PendingShell[]
  onApply: (id: string) => void
  onReject: (id: string) => void
  onRetry?: (id: string) => void
  busyId?: string | null
  /** Activity timeline focus — scroll + highlight matching card. */
  focusId?: string | null
}

function isActionable(status: PendingShell['status']) {
  return (
    status === 'pending' ||
    status === 'running' ||
    status === 'failed' ||
    status === 'timeout' ||
    status === 'rejected'
  )
}

export function ShellPanel({
  shells,
  onApply,
  onReject,
  onRetry,
  busyId,
  focusId,
}: ShellPanelProps) {
  const t = useT()
  const cards = shells.filter((s) => s.status !== 'cancelled')
  const actionable = cards.filter((s) => isActionable(s.status))
  const done = cards.filter((s) => s.status === 'done')
  const [showDone, setShowDone] = useState(false)
  const [highlightId, setHighlightId] = useState<string | null>(null)

  useLayoutEffect(() => {
    if (!focusId) return
    const shell = shells.find((s) => s.id === focusId && s.status !== 'cancelled')
    if (!shell) return
    if (shell.status === 'done') setShowDone(true)
  }, [focusId, shells])

  useEffect(() => {
    if (!focusId) return
    if (!shells.some((s) => s.id === focusId && s.status !== 'cancelled')) return
    const timer = window.setTimeout(() => {
      const el = document.getElementById(`gate-shell-${focusId}`)
      el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      setHighlightId(focusId)
    }, 30)
    const clear = window.setTimeout(() => setHighlightId(null), 2200)
    return () => {
      window.clearTimeout(timer)
      window.clearTimeout(clear)
    }
  }, [focusId, showDone, shells])

  if (cards.length === 0) return null

  return (
    <div className="mx-auto mb-3 w-full max-w-3xl">
      <div className="max-h-[min(36vh,280px)] space-y-2 overflow-y-auto overflow-x-hidden overscroll-contain pr-0.5">
        {actionable.map((shell) => (
          <ShellCard
            key={shell.id}
            shell={shell}
            busy={busyId === shell.id || shell.status === 'running'}
            highlighted={highlightId === shell.id}
            onApply={() => onApply(shell.id)}
            onReject={() => onReject(shell.id)}
            onRetry={onRetry ? () => onRetry(shell.id) : undefined}
          />
        ))}
        {done.length > 0 && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)]">
            <button
              type="button"
              onClick={() => setShowDone((v) => !v)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[var(--text-muted)] hover:text-[var(--text-h)]"
            >
              <span className="text-[var(--text-dim)]">{showDone ? '▾' : '▸'}</span>
              <span>
                {t('gate.shellDoneCount', { n: done.length })}
                {!showDone && (
                  <span className="ml-1.5 text-[var(--text-dim)]">
                    {t('gate.shellExpandHint')}
                  </span>
                )}
              </span>
            </button>
            {showDone && (
              <div className="space-y-2 border-t border-[var(--border-subtle)] px-2 pb-2 pt-2">
                {done.map((shell) => (
                  <ShellCard
                    key={shell.id}
                    shell={shell}
                    busy={false}
                    highlighted={highlightId === shell.id}
                    onApply={() => onApply(shell.id)}
                    onReject={() => onReject(shell.id)}
                    onRetry={onRetry ? () => onRetry(shell.id) : undefined}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function ShellCard({
  shell,
  busy,
  highlighted,
  onApply,
  onReject,
  onRetry,
}: {
  shell: PendingShell
  busy: boolean
  highlighted?: boolean
  onApply: () => void
  onReject: () => void
  onRetry?: () => void
}) {
  const t = useT()
  const pending = shell.status === 'pending'
  const rejected = shell.status === 'rejected'
  const failed = shell.status === 'failed' || shell.status === 'timeout'
  const retryable = failed || rejected
  const wantsOpen = pending || shell.status === 'running' || failed || rejected
  const [expanded, setExpanded] = useState(wantsOpen)
  const [copied, setCopied] = useState(false)

  // Pending→done used to leave cards stuck open and flood the viewport.
  useEffect(() => {
    setExpanded(wantsOpen)
  }, [shell.status, wantsOpen])

  useEffect(() => {
    if (highlighted) setExpanded(true)
  }, [highlighted])

  const output = [shell.stdout, shell.stderr].filter(Boolean).join('\n').slice(0, 4000)
  const statusLabel =
    shell.status === 'done'
      ? `exit ${shell.exit_code ?? '?'}`
      : shell.status === 'running'
        ? t('gate.running')
        : shell.status === 'failed'
          ? t('gate.failed')
          : shell.status === 'timeout'
            ? t('gate.timeout')
            : rejected
              ? t('gate.rejected')
              : t('gate.pendingRun')

  return (
    <div
      id={`gate-shell-${shell.id}`}
      data-gate-kind="shell"
      data-gate-id={shell.id}
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
          className="min-w-0 flex-1 text-left"
        >
          <div className="truncate font-mono text-xs text-[var(--text-h)]">
            <span className="mr-1 text-[var(--text-dim)]">{expanded ? '▾' : '▸'}</span>$ {shell.command}
            <button
              type="button"
              title={t('gate.copyCommand')}
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
            <span className="truncate">cwd: {shell.cwd}</span>
            <span
              className={[
                'shrink-0 rounded px-1.5 py-0.5 text-[10px]',
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
                {t('common.reject')}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={onApply}
                className="rounded-md bg-[var(--accent-solid)] px-2.5 py-1 text-xs font-medium text-white transition-all hover:brightness-110 active:scale-[0.96] disabled:opacity-40"
              >
                {busy ? '…' : t('gate.run')}
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
      {expanded && (output || shell.error) && (
        <pre className="max-h-28 overflow-auto px-3 py-2 font-mono text-[11px] leading-5 text-[var(--text-muted)]">
          {shell.error ? <div className="text-red-400">{shell.error}</div> : null}
          {output || null}
        </pre>
      )}
    </div>
  )
}
