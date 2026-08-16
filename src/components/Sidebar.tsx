import { useEffect, useRef, useState } from 'react'
import {
  SIDEBAR_WIDTH_MAX,
  SIDEBAR_WIDTH_MIN,
  type Workspace,
} from '../hooks/useWorkspaces'
import { formatRelativeTime } from '../utils/time'

interface ChatSession {
  id: string
  title: string
  updatedAt?: string
  isActive?: boolean
}

interface SidebarProps {
  workspaces: Workspace[]
  activeWorkspaceId: string
  sessions: ChatSession[]
  favoriteCount: number
  collapsed: boolean
  width: number
  isLoading: boolean
  isStreaming: boolean
  isDark: boolean
  onToggleCollapsed: () => void
  onWidthChange: (width: number) => void
  onToggleTheme: () => void
  onOpenSettings: () => void
  onOpenSearch: () => void
  onSwitchWorkspace: (id: string) => void
  onOpenFavorites: () => void
  onSwitchSession: (id: string) => void
  onNewSession: () => void
  onDeleteSession: (id: string) => void
  onRenameSession: (id: string, newTitle: string) => void | Promise<void>
}

export function Sidebar({
  workspaces,
  activeWorkspaceId,
  sessions,
  favoriteCount,
  collapsed,
  width,
  isLoading,
  isStreaming,
  isDark,
  onToggleCollapsed,
  onWidthChange,
  onToggleTheme,
  onOpenSettings,
  onOpenSearch,
  onSwitchWorkspace,
  onOpenFavorites,
  onSwitchSession,
  onNewSession,
  onDeleteSession,
  onRenameSession,
}: SidebarProps) {
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(workspaces.map((w) => [w.id, w.id === activeWorkspaceId])),
  )
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [isResizing, setIsResizing] = useState(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(width)

  useEffect(() => {
    if (!isResizing) return

    const onMove = (e: MouseEvent) => {
      const next = dragStartWidth.current + (e.clientX - dragStartX.current)
      onWidthChange(Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, next)))
    }
    const onUp = () => setIsResizing(false)

    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [isResizing, onWidthChange])

  const beginRename = (id: string, currentTitle: string) => {
    setConfirmDeleteId(null)
    setRenamingId(id)
    setRenameDraft(currentTitle)
  }

  const commitRename = async () => {
    if (!renamingId) return
    const next = renameDraft.trim()
    const current = sessions.find((s) => s.id === renamingId)?.title
    setRenamingId(null)
    if (!next || next === current) return
    await onRenameSession(renamingId, next)
  }

  const cancelRename = () => {
    setRenamingId(null)
    setRenameDraft('')
  }

  const toggleFolder = (id: string) => {
    setExpandedFolders((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  if (collapsed) {
    return (
      <aside className="flex h-dvh w-12 shrink-0 flex-col items-center border-r border-[var(--sidebar-border)] bg-[var(--sidebar-bg)] py-3">
        <button
          type="button"
          onClick={onNewSession}
          disabled={isLoading || isStreaming}
          title="New Agent"
          className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)] disabled:opacity-40"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
        <div className="mt-auto flex flex-col items-center gap-1">
          <FooterIconButton
            title={isDark ? '切换浅色模式' : '切换深色模式'}
            onClick={onToggleTheme}
          >
            {isDark ? <SunIcon /> : <MoonIcon />}
          </FooterIconButton>
          <FooterIconButton title="设置" onClick={onOpenSettings}>
            <SettingsIcon />
          </FooterIconButton>
          <FooterIconButton title="展开" onClick={onToggleCollapsed}>
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
              <path d="M13 5l7 7-7 7M5 5l7 7-7 7" />
            </svg>
          </FooterIconButton>
        </div>
      </aside>
    )
  }

  return (
    <aside
      className="relative flex h-dvh shrink-0 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar-bg)]"
      style={{ width }}
    >
      {/* New Agent */}
      <div className="px-3 pt-3">
        <button
          type="button"
          onClick={onNewSession}
          disabled={isLoading || isStreaming}
          className="flex w-full items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--surface-hover)] px-3 py-2 text-sm text-[var(--sidebar-text)] transition-colors hover:bg-[var(--surface-active)] disabled:opacity-40"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5M2 12l10 5 10-5" />
          </svg>
          New Agent
        </button>
      </div>

      {/* Nav items */}
      <nav className="mt-2 flex flex-col gap-0.5 px-2">
        <NavItem icon="search" label="Search" onClick={onOpenSearch} />
        <NavItem icon="star" label="收藏内容" badge={favoriteCount > 0 ? favoriteCount : undefined} onClick={onOpenFavorites} />
      </nav>

      {/* Session folders */}
      <div className="mt-4 flex-1 overflow-y-auto px-2">
        {workspaces.map((workspace) => {
          const isExpanded = expandedFolders[workspace.id] ?? false
          const isActive = workspace.id === activeWorkspaceId
          const folderSessions = isActive ? sessions : []

          return (
            <div key={workspace.id} className="mb-1">
              <button
                type="button"
                onClick={() => {
                  onSwitchWorkspace(workspace.id)
                  toggleFolder(workspace.id)
                }}
                className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm text-[var(--sidebar-muted)] transition-colors hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  className={['h-3 w-3 shrink-0 transition-transform', isExpanded ? 'rotate-90' : ''].join(' ')}
                >
                  <path d="M9 18l6-6-6-6" />
                </svg>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5 shrink-0 opacity-60">
                  <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                <span className="truncate">{workspace.name}</span>
              </button>

              {isExpanded && isActive && (
                <div className="ml-4 mt-0.5 flex flex-col gap-0.5 border-l border-[var(--border-subtle)] pl-2">
                  {isLoading ? (
                    <span className="px-2 py-1 text-xs text-[var(--sidebar-muted)]">加载中...</span>
                  ) : folderSessions.length === 0 ? (
                    <span className="px-2 py-1 text-xs text-[var(--sidebar-muted)]">暂无对话</span>
                  ) : (
                    folderSessions.map((chat) => {
                      const isRenaming = renamingId === chat.id
                      const isConfirmingDelete = confirmDeleteId === chat.id

                      if (isRenaming) {
                        return (
                          <div
                            key={chat.id}
                            className="flex w-full items-center gap-1 rounded-md bg-[var(--sidebar-active)] px-1.5 py-1"
                          >
                            <input
                              autoFocus
                              value={renameDraft}
                              onChange={(e) => setRenameDraft(e.target.value)}
                              onFocus={(e) => e.target.select()}
                              onBlur={() => {
                                void commitRename()
                              }}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  e.preventDefault()
                                  e.currentTarget.blur()
                                } else if (e.key === 'Escape') {
                                  e.preventDefault()
                                  cancelRename()
                                }
                              }}
                              className="min-w-0 flex-1 rounded-md border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-1 text-[13px] text-[var(--sidebar-text)] outline-none focus:border-[var(--input-focus)]"
                              aria-label="重命名对话"
                            />
                          </div>
                        )
                      }

                      if (isConfirmingDelete) {
                        return (
                          <div
                            key={chat.id}
                            className="flex w-full items-center gap-1 rounded-md bg-[var(--sidebar-active)] px-2 py-1"
                          >
                            <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--sidebar-text)]">
                              删除「{chat.title}」？
                            </span>
                            <button
                              type="button"
                              className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]"
                              onClick={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                                setConfirmDeleteId(null)
                              }}
                            >
                              取消
                            </button>
                            <button
                              type="button"
                              disabled={isStreaming}
                              className="shrink-0 rounded px-1.5 py-0.5 text-[11px] text-red-400 hover:bg-red-500/15 disabled:opacity-40"
                              onClick={(e) => {
                                e.preventDefault()
                                e.stopPropagation()
                                setConfirmDeleteId(null)
                                onDeleteSession(chat.id)
                              }}
                            >
                              删除
                            </button>
                          </div>
                        )
                      }

                      return (
                        <div
                          key={chat.id}
                          className={[
                            'group flex w-full items-center gap-1 rounded-md px-2 py-1 transition-colors',
                            chat.isActive
                              ? 'bg-[var(--sidebar-active)] text-[var(--sidebar-text)]'
                              : 'text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]',
                          ].join(' ')}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setConfirmDeleteId(null)
                              onSwitchSession(chat.id)
                            }}
                            onDoubleClick={() => beginRename(chat.id, chat.title)}
                            className="min-w-0 flex-1 truncate py-0.5 text-left text-[13px]"
                            title="双击重命名"
                          >
                            {chat.title}
                          </button>

                          <div className="relative flex h-6 w-[52px] shrink-0 items-center justify-end">
                            {chat.updatedAt && (
                              <span className="text-[11px] text-[var(--text-dim)] transition-opacity group-hover:pointer-events-none group-hover:opacity-0 group-focus-within:pointer-events-none group-focus-within:opacity-0">
                                {formatRelativeTime(chat.updatedAt)}
                              </span>
                            )}
                            <div className="absolute inset-y-0 right-0 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                              <IconBtn title="重命名" onClick={() => beginRename(chat.id, chat.title)}>
                                <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                              </IconBtn>
                              <IconBtn
                                title="删除"
                                disabled={isStreaming}
                                onClick={() => setConfirmDeleteId(chat.id)}
                              >
                                <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                              </IconBtn>
                            </div>
                          </div>
                        </div>
                      )
                    })
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer actions */}
      <div className="border-t border-[var(--sidebar-border)] p-3">
        <div className="flex items-center gap-1">
          <FooterIconButton
            title={isDark ? '切换浅色模式' : '切换深色模式'}
            onClick={onToggleTheme}
          >
            {isDark ? <SunIcon /> : <MoonIcon />}
          </FooterIconButton>
          <FooterIconButton title="设置" onClick={onOpenSettings}>
            <SettingsIcon />
          </FooterIconButton>
          <div className="flex-1" />
          <FooterIconButton title="折叠侧边栏" onClick={onToggleCollapsed}>
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
              <path d="M11 17l-5-5 5-5M19 17l-5-5 5-5" />
            </svg>
          </FooterIconButton>
        </div>
      </div>

      {/* Right-edge resize handle */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="调整侧边栏宽度"
        title="拖动调整宽度"
        onMouseDown={(e) => {
          e.preventDefault()
          dragStartX.current = e.clientX
          dragStartWidth.current = width
          setIsResizing(true)
        }}
        onDoubleClick={() => onWidthChange(260)}
        className={[
          'absolute top-0 right-0 z-20 h-full w-1.5 cursor-col-resize touch-none',
          'after:absolute after:inset-y-0 after:right-0 after:w-px after:bg-transparent after:transition-colors',
          'hover:after:bg-[var(--text-dim)]',
          isResizing ? 'after:bg-[var(--text-muted)]' : '',
        ].join(' ')}
      />
    </aside>
  )
}

function FooterIconButton({
  title,
  onClick,
  children,
}: {
  title: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--sidebar-muted)] transition-colors hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]"
    >
      {children}
    </button>
  )
}

function SunIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
      <path d="M21 14.5A8.5 8.5 0 119.5 3a7 7 0 0011.5 11.5z" />
    </svg>
  )
}

function SettingsIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
      <path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function NavItem({
  icon,
  label,
  badge,
  onClick,
}: {
  icon: 'search' | 'star'
  label: string
  badge?: number
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm text-[var(--sidebar-muted)] transition-colors hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]"
    >
      {icon === 'search' ? (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
      ) : (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill={badge ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={2} className="h-4 w-4">
          <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
        </svg>
      )}
      <span className="flex-1 truncate">{label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="rounded-full bg-[var(--surface-hover)] px-1.5 text-[11px]">{badge}</span>
      )}
    </button>
  )
}

function IconBtn({
  title,
  onClick,
  disabled,
  children,
}: {
  title: string
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onPointerDown={(e) => {
        e.stopPropagation()
      }}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        if (!disabled) onClick()
      }}
      className="flex h-6 w-6 items-center justify-center rounded text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)] disabled:opacity-40"
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3 w-3">
        {children}
      </svg>
    </button>
  )
}
