import { useEffect, useMemo, useState } from 'react'
import { getSessionBlob } from '../api/agent'
import type { ToolTraceItem } from '../types'
import { isFileRef } from '../utils/turnTrace'
import { ChevronIcon } from './ChevronIcon'

interface ToolTimelineProps {
  items: ToolTraceItem[]
  isStreaming?: boolean
  sessionId?: string | null
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

function StepStatusIcon({
  status,
  failed,
}: {
  status: ToolTraceItem['status']
  failed: boolean
}) {
  const kind = status === 'running' ? 'running' : failed ? 'error' : 'ok'
  const color =
    kind === 'running'
      ? 'text-[var(--status-run)] bg-[var(--status-run-bg)]'
      : kind === 'error'
        ? 'text-[var(--status-err)] bg-[var(--status-err-bg)]'
        : 'text-[var(--status-ok)] bg-[var(--status-ok-bg)]'

  return (
    <span
      className={[
        'flex h-2.5 w-2.5 shrink-0 items-center justify-center overflow-hidden rounded-full leading-none',
        color,
      ].join(' ')}
      aria-hidden
    >
      {kind === 'running' ? (
        <svg
          viewBox="0 0 16 16"
          className="block h-[7px] w-[7px] animate-spin"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
        >
          <path d="M8 2.5a5.5 5.5 0 1 1-4.6 2.5" />
        </svg>
      ) : kind === 'error' ? (
        <svg
          viewBox="0 0 16 16"
          className="block h-[7px] w-[7px]"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
        >
          <path d="M5 5l6 6M11 5l-6 6" />
        </svg>
      ) : (
        <svg
          viewBox="0 0 16 16"
          className="block h-[7px] w-[7px]"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3.5 8.2l3 3 6-6.5" />
        </svg>
      )}
    </span>
  )
}

export function ToolTimeline({ items, isStreaming, sessionId, onRetryStep }: ToolTimelineProps) {
  const [expanded, setExpanded] = useState(false)
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  const [fullByRef, setFullByRef] = useState<Record<string, string>>({})
  const [loadingRef, setLoadingRef] = useState<string | null>(null)
  const [loadErrorByRef, setLoadErrorByRef] = useState<Record<string, string>>({})

  const runningCount = useMemo(
    () => items.filter((t) => t.status === 'running').length,
    [items],
  )
  const errorCount = useMemo(
    () => items.filter((t) => t.status === 'error' || isErrorDetail(t.detail)).length,
    [items],
  )

  useEffect(() => {
    setOpenIdx(null)
  }, [items])

  useEffect(() => {
    if (openIdx === null) return
    const item = items[openIdx]
    const ref = item?.fullRef
    if (!ref || !isFileRef(ref) || !sessionId) return
    if (fullByRef[ref] || loadingRef === ref) return

    let cancelled = false
    setLoadingRef(ref)
    getSessionBlob(sessionId, ref)
      .then((text) => {
        if (cancelled) return
        setFullByRef((prev) => ({ ...prev, [ref]: text }))
        setLoadErrorByRef((prev) => {
          const next = { ...prev }
          delete next[ref]
          return next
        })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const msg = err instanceof Error ? err.message : '加载失败'
        setLoadErrorByRef((prev) => ({ ...prev, [ref]: msg }))
      })
      .finally(() => {
        if (!cancelled) setLoadingRef((cur) => (cur === ref ? null : cur))
      })

    return () => {
      cancelled = true
    }
  }, [openIdx, items, sessionId, fullByRef, loadingRef])

  if (items.length === 0) return null

  const summary = runningCount
    ? `运行中 ${runningCount}/${items.length}`
    : errorCount
      ? `${items.length} 步 · ${errorCount} 失败`
      : `${items.length} 步工具`

  return (
    <div className="mb-3 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)]/60">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-[13px] leading-5 text-[var(--text-muted)] hover:bg-[var(--surface-hover)]"
      >
        <ChevronIcon open={expanded} className="text-[var(--text-muted)]" />
        <span className="font-medium text-[var(--text-h)]">工具轨迹</span>
        <span className="truncate text-[var(--text-muted)]">{summary}</span>
        {isStreaming && runningCount > 0 && (
          <span className="ml-auto inline-flex gap-0.5">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-muted)]" />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-muted)] [animation-delay:120ms]" />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-muted)] [animation-delay:240ms]" />
          </span>
        )}
      </button>

      {expanded && (
        <ol className="border-t border-[var(--border)] px-2 py-1.5">
          {items.map((t, i) => {
            const failed = t.status === 'error' || isErrorDetail(t.detail)
            const summaryText = summarizeDetail(t.name, t.detail)
            const isOpen = openIdx === i
            const showRetry = Boolean(onRetryStep) && canRetryStep(t) && !isStreaming
            const ref = t.fullRef
            const fullText = ref ? fullByRef[ref] : undefined
            const displayBody = fullText ?? t.detail
            const needsFetch = Boolean(ref && isFileRef(ref) && !fullText)
            return (
              <li key={`${t.name}-${i}`} className="px-1">
                <div className="flex items-center gap-2">
                  <StepStatusIcon status={t.status} failed={failed} />
                  <button
                    type="button"
                    onClick={() => setOpenIdx(isOpen ? null : i)}
                    className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-[var(--surface-hover)]"
                  >
                    <span className="shrink-0 font-mono text-[13px] font-normal leading-5 text-[var(--text-h)]">
                      {t.name}
                    </span>
                    <span
                      className={[
                        'min-w-0 flex-1 truncate text-[12px] leading-5',
                        failed ? 'text-[var(--status-err)]' : 'text-[var(--text-muted)]',
                      ].join(' ')}
                    >
                      {t.status === 'running'
                        ? '执行中…'
                        : t.truncated || needsFetch
                          ? `${summaryText || '大输出'} · 可展开全量`
                          : summaryText || '—'}
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
                      className="shrink-0 rounded-md px-2 py-0.5 text-[12px] font-medium text-[var(--status-warn)] hover:bg-[var(--status-warn-bg)]"
                    >
                      重试
                    </button>
                  )}
                </div>
                {isOpen && (
                  <div className="mb-1.5 ml-6">
                    {ref && loadingRef === ref && (
                      <div className="px-2 py-1 text-[12px] text-[var(--text-muted)]">加载全量…</div>
                    )}
                    {ref && loadErrorByRef[ref] && (
                      <div className="px-2 py-1 text-[12px] text-[var(--status-err)]">
                        {loadErrorByRef[ref]}
                      </div>
                    )}
                    {displayBody && (
                      <pre className="max-h-64 overflow-auto rounded-md bg-[var(--bg)] px-2 py-1.5 font-mono text-[12px] leading-5 text-[var(--text)]">
                        {displayBody}
                      </pre>
                    )}
                    {!displayBody && !(ref && loadingRef === ref) && (
                      <div className="px-2 py-1 text-[12px] text-[var(--text-muted)]">无详情</div>
                    )}
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
