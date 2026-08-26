import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  fetchAudit,
  fetchAuditSessions,
  type AuditEvent,
  type AuditSessionSummary,
} from '../api/agent'

interface SessionOption {
  id: string
  title: string
}

interface AuditPanelProps {
  activeSessionId?: string | null
  sessions?: SessionOption[]
  onOpenSession?: (sessionId: string) => void
}

const LIMIT = 100

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function payloadPreview(payload: Record<string, unknown>): string {
  const keys = Object.keys(payload || {})
  if (keys.length === 0) return '—'
  const bits: string[] = []
  for (const key of ['goal', 'model', 'path', 'command', 'message', 'code', 'status', 'id']) {
    if (payload[key] != null && payload[key] !== '') {
      bits.push(`${key}=${String(payload[key]).slice(0, 48)}`)
    }
    if (bits.length >= 2) break
  }
  if (bits.length === 0) bits.push(keys.slice(0, 3).join(', '))
  return bits.join(' · ')
}

function eventTone(eventType: string): string {
  if (eventType.includes('reject') || eventType.includes('fail') || eventType.includes('error')) {
    return 'text-red-300/90'
  }
  if (eventType.includes('complete') || eventType.includes('apply') || eventType.includes('write')) {
    return 'text-emerald-300/90'
  }
  if (eventType.startsWith('turn.') || eventType.includes('goal')) {
    return 'text-sky-300/90'
  }
  return 'text-[var(--text-h)]'
}

export function AuditPanel({ activeSessionId, sessions = [], onOpenSession }: AuditPanelProps) {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [auditSessions, setAuditSessions] = useState<AuditSessionSummary[]>([])
  const [sessionFilter, setSessionFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const titleById = useMemo(() => {
    const map = new Map<string, string>()
    for (const s of sessions) map.set(s.id, s.title)
    return map
  }, [sessions])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const sessionId =
        sessionFilter === 'all'
          ? undefined
          : sessionFilter === 'current'
            ? activeSessionId || undefined
            : sessionFilter
      const [evs, summaries] = await Promise.all([
        fetchAudit(LIMIT, sessionId),
        fetchAuditSessions(50),
      ])
      setEvents(evs)
      setAuditSessions(summaries)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载审计失败')
    } finally {
      setLoading(false)
    }
  }, [sessionFilter, activeSessionId])

  useEffect(() => {
    void load()
  }, [load])

  const typeOptions = useMemo(() => {
    const set = new Set<string>()
    for (const ev of events) set.add(ev.event_type)
    return Array.from(set).sort()
  }, [events])

  const filtered = useMemo(() => {
    if (typeFilter === 'all') return events
    if (typeFilter.endsWith('.')) {
      return events.filter((e) => e.event_type.startsWith(typeFilter))
    }
    return events.filter((e) => e.event_type === typeFilter)
  }, [events, typeFilter])

  const exportJson = () => {
    const payload = JSON.stringify(
      {
        exportedAt: new Date().toISOString(),
        sessionFilter,
        typeFilter,
        count: filtered.length,
        events: filtered,
      },
      null,
      2,
    )
    const blob = new Blob([payload], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `hal-audit-${sessionFilter}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-[9rem] flex-1 flex-col gap-1 text-[11px] text-[var(--text-muted)]">
          会话
          <select
            value={sessionFilter}
            onChange={(e) => setSessionFilter(e.target.value)}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface)] px-2 py-1.5 text-xs text-[var(--text-h)]"
          >
            <option value="all">全部会话</option>
            {activeSessionId ? <option value="current">当前会话</option> : null}
            {auditSessions.map((s) => (
              <option key={s.session_id} value={s.session_id}>
                {(titleById.get(s.session_id) || s.session_id.slice(0, 8)) + ` · ${s.event_count} 条`}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-[8rem] flex-1 flex-col gap-1 text-[11px] text-[var(--text-muted)]">
          类型
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--surface)] px-2 py-1.5 text-xs text-[var(--text-h)]"
          >
            <option value="all">全部类型</option>
            <option value="turn.">turn.*</option>
            <option value="patch.">patch.*</option>
            <option value="shell.">shell.*</option>
            <option value="memory.">memory.*</option>
            {typeOptions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-xs text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-50"
        >
          {loading ? '加载中…' : '刷新'}
        </button>
        <button
          type="button"
          onClick={exportJson}
          disabled={filtered.length === 0}
          className="rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-xs text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-50"
        >
          导出 JSON
        </button>
      </div>

      <p className="text-[11px] text-[var(--text-dim)]">
        按会话回放审计事件（审批、压缩、turn 完成等）。展开可看 payload；有 session_id 时可跳转该对话。
      </p>

      {error && <p className="text-xs text-red-300/90">{error}</p>}

      {filtered.length === 0 && !loading ? (
        <p className="text-xs text-[var(--text-muted)]">暂无事件</p>
      ) : (
        <ul className="max-h-[28rem] space-y-1 overflow-y-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)]/50 px-2 py-2">
          {filtered.map((ev) => {
            const open = expandedId === ev.id
            const sessionTitle = ev.session_id
              ? titleById.get(ev.session_id) || ev.session_id.slice(0, 10)
              : null
            return (
              <li
                key={ev.id}
                className="rounded-md border border-transparent px-2 py-1.5 hover:border-[var(--border-subtle)] hover:bg-[var(--surface-hover)]/40"
              >
                <button
                  type="button"
                  onClick={() => setExpandedId(open ? null : ev.id)}
                  className="flex w-full items-start gap-2 text-left"
                >
                  <span className="mt-0.5 text-[10px] text-[var(--text-dim)]">{open ? '▾' : '▸'}</span>
                  <span className="min-w-0 flex-1">
                    <span className={`font-mono text-[11px] ${eventTone(ev.event_type)}`}>
                      {ev.event_type}
                    </span>
                    <span className="mt-0.5 block truncate text-[10px] text-[var(--text-dim)]">
                      {payloadPreview(ev.payload)}
                    </span>
                  </span>
                  <span className="shrink-0 text-right text-[10px] text-[var(--text-dim)]">
                    <span className="block">{formatTime(ev.created_at)}</span>
                    {sessionTitle ? (
                      <span className="mt-0.5 block max-w-[7rem] truncate opacity-80">{sessionTitle}</span>
                    ) : (
                      <span className="mt-0.5 block opacity-50">无会话</span>
                    )}
                  </span>
                </button>
                {open && (
                  <div className="mt-2 space-y-2 border-t border-[var(--border-subtle)] pt-2">
                    {ev.session_id && onOpenSession ? (
                      <button
                        type="button"
                        onClick={() => onOpenSession(ev.session_id!)}
                        className="rounded-md bg-[var(--accent-bg)] px-2 py-1 text-[10px] text-[var(--text-h)] hover:bg-[var(--surface-hover)]"
                      >
                        打开此会话回放
                      </button>
                    ) : null}
                    <pre className="max-h-48 overflow-auto rounded-md bg-[var(--bg)] px-2 py-1.5 font-mono text-[10px] leading-4 text-[var(--text-muted)]">
                      {JSON.stringify(
                        {
                          id: ev.id,
                          session_id: ev.session_id,
                          event_type: ev.event_type,
                          created_at: ev.created_at,
                          payload: ev.payload,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}

      <div className="text-[10px] text-[var(--text-dim)]">
        显示 {filtered.length} / {events.length} 条（上限 {LIMIT}）
      </div>
    </div>
  )
}
