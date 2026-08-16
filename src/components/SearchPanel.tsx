import { useMemo, useState } from 'react'

interface SearchPanelProps {
  isOpen: boolean
  sessions: Array<{ id: string; title: string }>
  pairs: Array<{ id: string; user: { content: string }; assistant: { content: string } }>
  onClose: () => void
  onSelectSession: (id: string) => void
  onSelectPair: (pairId: string) => void
}

export function SearchPanel({
  isOpen,
  sessions,
  pairs,
  onClose,
  onSelectSession,
  onSelectPair,
}: SearchPanelProps) {
  const [query, setQuery] = useState('')

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return { sessions: sessions.slice(0, 8), pairs: pairs.slice(0, 8) }
    return {
      sessions: sessions.filter((s) => s.title.toLowerCase().includes(q)).slice(0, 8),
      pairs: pairs
        .filter(
          (p) =>
            p.user.content.toLowerCase().includes(q) ||
            p.assistant.content.toLowerCase().includes(q),
        )
        .slice(0, 8),
    }
  }, [query, sessions, pairs])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-xl">
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-3">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4 text-[var(--text-muted)]">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose()
            }}
            placeholder="搜索会话或消息..."
            className="flex-1 bg-transparent text-sm text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)]"
          />
        </div>

        <div className="max-h-[50vh] overflow-y-auto p-2">
          {results.sessions.length === 0 && results.pairs.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-[var(--text-muted)]">无匹配结果</div>
          ) : (
            <>
              {results.sessions.length > 0 && (
                <div className="mb-2">
                  <div className="px-3 py-1 text-[11px] uppercase tracking-wider text-[var(--text-dim)]">会话</div>
                  {results.sessions.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      onClick={() => {
                        onSelectSession(s.id)
                        onClose()
                      }}
                      className="flex w-full rounded-lg px-3 py-2 text-left text-sm text-[var(--text-h)] hover:bg-[var(--surface-hover)]"
                    >
                      {s.title}
                    </button>
                  ))}
                </div>
              )}
              {results.pairs.length > 0 && (
                <div>
                  <div className="px-3 py-1 text-[11px] uppercase tracking-wider text-[var(--text-dim)]">当前会话消息</div>
                  {results.pairs.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => {
                        onSelectPair(p.id)
                        onClose()
                      }}
                      className="flex w-full flex-col rounded-lg px-3 py-2 text-left hover:bg-[var(--surface-hover)]"
                    >
                      <span className="truncate text-sm text-[var(--text-h)]">{p.user.content}</span>
                      <span className="truncate text-xs text-[var(--text-muted)]">{p.assistant.content}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
