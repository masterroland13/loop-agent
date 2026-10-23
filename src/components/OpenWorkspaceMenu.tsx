import { useEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import type { Project } from '../hooks/useWorkspaces'
import { useT } from '../i18n'

interface OpenWorkspaceMenuProps {
  open: boolean
  onClose: () => void
  /** Projects with a real disk root (shown under Recents). */
  recents: Project[]
  anchorRef: RefObject<HTMLElement | null>
  onSelectRecent: (projectId: string) => void
  /** Open the full This PC directory browser. */
  onBrowseThisPc: () => void
}

export function OpenWorkspaceMenu({
  open,
  onClose,
  recents,
  anchorRef,
  onSelectRecent,
  onBrowseThisPc,
}: OpenWorkspaceMenuProps) {
  const t = useT()
  const panelRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [pos, setPos] = useState({ top: 0, left: 0 })

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return recents
    return recents.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        (p.root || '').toLowerCase().includes(q),
    )
  }, [recents, query])

  useEffect(() => {
    if (!open) {
      setQuery('')
      return
    }
    const anchor = anchorRef.current
    if (anchor) {
      const rect = anchor.getBoundingClientRect()
      const width = 320
      let left = rect.left
      if (left + width > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - width - 8)
      }
      setPos({ top: rect.bottom + 6, left })
    }
    const t = window.setTimeout(() => inputRef.current?.focus(), 0)
    return () => window.clearTimeout(t)
  }, [open, anchorRef])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onPointer = (e: MouseEvent) => {
      const target = e.target as Node
      if (panelRef.current?.contains(target)) return
      if (anchorRef.current?.contains(target)) return
      onClose()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('mousedown', onPointer)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onPointer)
    }
  }, [open, onClose, anchorRef])

  if (!open) return null

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-label={t('workspace.openMenuAria')}
      style={{ top: pos.top, left: pos.left }}
      className="fixed z-[60] flex w-[320px] max-h-[min(420px,70vh)] flex-col overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-[0_12px_40px_rgba(0,0,0,0.45)]"
    >
      <div className="border-b border-[var(--border-subtle)] px-3 py-2.5">
        <div className="flex items-center gap-2 rounded-lg bg-[var(--surface)] px-2.5 py-1.5">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            className="h-3.5 w-3.5 shrink-0 text-[var(--text-dim)]"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('workspace.searchFoldersPlaceholder')}
            className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)]"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        <SectionLabel>{t('workspace.recents')}</SectionLabel>
        {filtered.length === 0 ? (
          <p className="px-3 py-2 text-[12px] text-[var(--text-dim)]">
            {query.trim() ? t('workspace.noMatch') : t('workspace.noRecents')}
          </p>
        ) : (
          filtered.map((p) => (
            <MenuRow
              key={p.id}
              icon={<FolderOutlineIcon />}
              label={p.name}
              hint={p.root || undefined}
              onClick={() => {
                onSelectRecent(p.id)
                onClose()
              }}
            />
          ))
        )}

        <SectionLabel className="mt-2">{t('workspace.repos')}</SectionLabel>
        <MenuRow
          icon={<MonitorIcon />}
          label={t('workspace.onThisPc')}
          chevron
          onClick={() => {
            onClose()
            onBrowseThisPc()
          }}
        />
        <MenuRow
          icon={<FolderOutlineIcon />}
          label={t('workspace.useExisting')}
          chevron
          onClick={() => {
            onClose()
            onBrowseThisPc()
          }}
        />
      </div>
    </div>
  )
}

function SectionLabel({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`px-3 pb-1 pt-1 text-[11px] font-medium text-[var(--text-dim)] ${className}`}
    >
      {children}
    </div>
  )
}

function MenuRow({
  icon,
  label,
  hint,
  chevron,
  onClick,
}: {
  icon: ReactNode
  label: string
  hint?: string
  chevron?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint || label}
      className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[13px] text-[var(--text-h)] transition-colors hover:bg-[var(--surface-hover)]"
    >
      <span className="flex h-5 w-5 shrink-0 items-center justify-center text-[var(--text-muted)]">
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {chevron && (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className="h-3.5 w-3.5 shrink-0 text-[var(--text-dim)]"
        >
          <path d="M9 18l6-6-6-6" />
        </svg>
      )}
    </button>
  )
}

function FolderOutlineIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
      <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
    </svg>
  )
}

function MonitorIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  )
}
