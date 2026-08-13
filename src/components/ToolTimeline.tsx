import { useMemo, useState } from 'react'
import type { ToolTraceItem } from '../types'

interface ToolTimelineProps {
  items: ToolTraceItem[]
  isStreaming?: boolean
  onRetryStep?: (item: ToolTraceItem, index: number) => void
}

function summarizeDetail(name: string, detail?: string): string {
  if (!detail) return ''
  const trimmed = detail.trim()
  try {
    const data = JSON.parse(trimmed) as Record<string, unknown>
    if (typeof data.error === 'string') return data.error
    if (data.status) return String(data.status)
    if (typeof data.path === 'string') return data.path
    if (typeof data.command === 'string') return String(data.command)
    if (Array.isArray(data.entries)) return `${data.entries.length} entries`
    if (typeof data.match_count === 'number') return `${data.match_count} matches`
    if (typeof data.content === 'string') {
      const lines = data.content.split('\n').length
      return `${lines} lines`
    }
  } catch {
    // not json
  }
  if (name === 'propose_edit' || name === 'propose_shell') {
    return trimmed.slice(0, 80)
  }
  // arguments often long JSON
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    return trimmed.slice(0, 72) + (trimmed.length > 72 ? '…' : '')
  }
  return trimmed.slice(0, 100) + (trimmed.length > 100 ? '…' : '')
}

function isErrorDetail(detail?: string): boolean {
  if (!detail) return false
  try {
    const data = JSON.parse(detail) as Record<string, unknown>
    return (
      Boolean(data.error) ||
      data.status === 'failed' ||
      data.status === 'timeout' ||
      data.status === 'rejected'
    )
  } catch {
    return /error|failed|失败|拒绝/i.test(detail)
  }
}

function canRetryStep(item: ToolTraceItem): boolean {
  if (item.status === 'running') return false
  if (item.status === 'error' || isErrorDetail(item.detail)) return true
  return false
}

export function ToolTimeline({ items, isStreaming, onRetryStep }: ToolTimelineProps) {
  const [expanded, setExpanded] = useState(true)
  const [openIdx, setOpenIdx] = useState<number | null>(null)

  const runningCount = useMemo(
    () => items.filter((t) => t.status === 'running').length,
    [items],
  )
  const errorCount = useMemo(
    () => items.filter((t) => t.status === 'error' || isErrorDetail(t.detail)).length,
    [items],
  )

  if (items.length === 0) return null

  const summary = runningCount
    ? `运行中 ${runningCount}/${items.length}`
    : errorCount
      ? `${items.length} 步 · ${errorCount} 失败`
      : `${items.length} 步工具`

  return (
    <div className="mb-3 overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)]/40">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-[var(--text-muted)] hover:bg-[var(--surface-hover)]"
      >
        <span className="text-[var(--text-dim)]">{expanded ? '▾' : '▸'}</span>
        <span className="font-medium text-[var(--text-h)]">工具轨迹</span>
        <span className="truncate opacity-80">{summary}</span>
        {isStreaming && runningCount > 0 && (
          <span className="ml-auto inline-flex gap-0.5">
            <span className="h-1 w-1 animate-pulse rounded-full bg-[var(--text-muted)]" />
            <span className="h-1 w-1 animate-pulse rounded-full bg-[var(--text-muted)] [animation-delay:120ms]" />
            <span className="h-1 w-1 animate-pulse rounded-full bg-[var(--text-muted)] [animation-delay:240ms]" />
          </span>
        )}
      </button>

      {expanded && (
        <ol className="border-t border-[var(--border-subtle)] px-2 py-1.5">
          {items.map((t, i) => {
            const failed = t.status === 'error' || isErrorDetail(t.detail)
            const summaryText = summarizeDetail(t.name, t.detail)
            const isOpen = openIdx === i
            const showRetry = Boolean(onRetryStep) && canRetryStep(t) && !isStreaming
            return (
              <li key={`${t.name}-${i}`} className="relative pl-5">
                {i < items.length - 1 && (
                  <span className="absolute left-[9px] top-5 bottom-0 w-px bg-[var(--border-subtle)]" />
                )}
                <span
                  className={[
                    'absolute left-1 top-2 flex h-3.5 w-3.5 items-center justify-center rounded-full text-[9px]',
                    t.status === 'running'
                      ? 'bg-sky-500/20 text-sky-300'
                      : failed
                        ? 'bg-red-500/20 text-red-300'
                        : 'bg-emerald-500/15 text-emerald-300',
                  ].join(' ')}
                >
                  {t.status === 'running' ? '·' : failed ? '!' : '✓'}
                </span>
                <div className="flex items-start gap-1">
                  <button
                    type="button"
                    onClick={() => setOpenIdx(isOpen ? null : i)}
                    className="flex min-w-0 flex-1 items-start gap-2 rounded-md px-1.5 py-1.5 text-left hover:bg-[var(--surface-hover)]"
                  >
                    <span className="shrink-0 font-mono text-[12px] text-[var(--text-h)]">{t.name}</span>
                    <span
                      className={[
                        'min-w-0 flex-1 truncate text-[11px]',
                        failed ? 'text-red-300/90' : 'text-[var(--text-dim)]',
                      ].join(' ')}
                    >
                      {t.status === 'running' ? '执行中…' : summaryText || '—'}
                    </span>
                  </button>
                  {showRetry && (
                    <button
                      type="button"
                      title="重试此步"
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        onRetryStep?.(t, i)
                      }}
                      className="mt-1 shrink-0 rounded-md px-1.5 py-0.5 text-[10px] text-amber-300/90 hover:bg-amber-500/15"
                    >
                      重试
                    </button>
                  )}
                </div>
                {isOpen && t.detail && (
                  <pre className="mb-1.5 ml-1 max-h-40 overflow-auto rounded-md bg-[var(--bg)] px-2 py-1.5 font-mono text-[10px] leading-4 text-[var(--text-muted)]">
                    {t.detail.slice(0, 2500)}
                    {t.detail.length > 2500 ? '\n…' : ''}
                  </pre>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
