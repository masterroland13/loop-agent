import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  SIDEBAR_WIDTH_MAX,
  SIDEBAR_WIDTH_MIN,
  UNBOUND_PROJECT_ID,
  type Project,
} from '../hooks/useWorkspaces'
import { formatRelativeTime } from '../utils/time'
import { ChevronIcon } from './ChevronIcon'
import { ContextMenu, type ContextMenuItem } from './ContextMenu'
import {
  MenuBellIcon,
  MenuCopyIcon,
  MenuHashIcon,
  MenuPencilIcon,
  MenuPinIcon,
  MenuSidebarRemoveIcon,
  MenuTranscriptIcon,
  MenuTrashIcon,
  SessionPinIcon,
  UnreadDot,
} from './ContextMenuIcons'
import { OpenWorkspaceMenu } from './OpenWorkspaceMenu'

interface ChatSession {
  id: string
  title: string
  updatedAt?: string
  isActive?: boolean
  isPinned?: boolean
  isUnread?: boolean
  showUnreadDot?: boolean
}

interface SidebarProps {
  projects: Project[]
  activeProjectId: string
  /** All sessions; Sidebar groups by projectIdForSession. */
  sessions: ChatSession[]
  projectIdForSession: (sessionId: string) => string
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
  onOpenFavorites: () => void
  onActivateProject: (projectId: string) => void
  onSwitchSession: (id: string) => void
  /** Create a chat in the given project (defaults to active). */
  onNewSession: (projectId?: string) => void
  onDeleteSession: (id: string) => void
  onRenameSession: (id: string, newTitle: string) => void | Promise<void>
  /** Open the full This PC directory browser (WorkspacePicker). */
  onBrowseThisPc: () => void
  onRemoveProject?: (projectId: string) => void
  onTogglePin?: (sessionId: string) => void
  onMarkRead?: (sessionId: string) => void
  onMarkUnread?: (sessionId: string) => void
  onCopySessionId?: (sessionId: string) => void
  onCopyTranscript?: (sessionId: string) => void | Promise<void>
}

export function Sidebar({
  projects,
  activeProjectId,
  sessions,
  projectIdForSession,
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
  onOpenFavorites,
  onActivateProject,
  onSwitchSession,
  onNewSession,
  onDeleteSession,
  onRenameSession,
  onBrowseThisPc,
  onRemoveProject,
  onTogglePin,
  onMarkRead,
  onMarkUnread,
  onCopySessionId,
  onCopyTranscript,
}: SidebarProps) {
  const [openWorkspaceMenu, setOpenWorkspaceMenu] = useState(false)
  const openWorkspaceBtnRef = useRef<HTMLButtonElement>(null)
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    items: ContextMenuItem[]
  } | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    for (const p of projects) {
      init[p.id] = p.id === activeProjectId
    }
    return init
  })
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [isResizing, setIsResizing] = useState(false)
  const dragStartX = useRef(0)
  const dragStartWidth = useRef(width)

  // Keep newly seen projects expanded when they become active.
  useEffect(() => {
    setExpanded((prev) => {
      const next = { ...prev }
      let changed = false
      for (const p of projects) {
        if (next[p.id] === undefined) {
          next[p.id] = p.id === activeProjectId
          changed = true
        }
      }
      if (activeProjectId && !next[activeProjectId]) {
        next[activeProjectId] = true
        changed = true
      }
      return changed ? next : prev
    })
  }, [projects, activeProjectId])

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

  const sessionsByProject = useMemo(() => {
    const map: Record<string, ChatSession[]> = {}
    for (const p of projects) map[p.id] = []
    for (const s of sessions) {
      const pid = projectIdForSession(s.id)
      if (!map[pid]) map[pid] = []
      map[pid].push(s)
    }
    for (const pid of Object.keys(map)) {
      map[pid].sort((a, b) => {
        const aPinned = a.isPinned ? 1 : 0
        const bPinned = b.isPinned ? 1 : 0
        if (aPinned !== bPinned) return bPinned - aPinned
        const ta = a.updatedAt || ''
        const tb = b.updatedAt || ''
        return tb.localeCompare(ta)
      })
    }
    return map
  }, [projects, sessions, projectIdForSession])

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const beginRename = (id: string, title: string) => {
    setConfirmDeleteId(null)
    setRenamingId(id)
    setRenameDraft(title)
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

  const openProjectContextMenu = (e: React.MouseEvent, project: Project) => {
    e.preventDefault()
    if (!onRemoveProject) return
    const items: ContextMenuItem[] = [
      {
        type: 'item',
        id: 'remove',
        label: 'Remove from Sidebar',
        icon: <MenuSidebarRemoveIcon />,
        disabled: project.id === UNBOUND_PROJECT_ID || !project.root,
        onClick: () => onRemoveProject(project.id),
      },
    ]
    setContextMenu({ x: e.clientX, y: e.clientY, items })
  }

  const openSessionContextMenu = (e: React.MouseEvent, chat: ChatSession) => {
    e.preventDefault()
    const unread = chat.isUnread ?? false
    const items: ContextMenuItem[] = [
      ...(onTogglePin
        ? [
            {
              type: 'item' as const,
              id: 'pin',
              label: chat.isPinned ? 'Unpin' : 'Pin',
              icon: <MenuPinIcon />,
              onClick: () => onTogglePin(chat.id),
            },
          ]
        : []),
      {
        type: 'item',
        id: 'rename',
        label: 'Rename',
        icon: <MenuPencilIcon />,
        onClick: () => beginRename(chat.id, chat.title),
      },
      ...(onMarkRead && onMarkUnread
        ? [
            {
              type: 'item' as const,
              id: 'read-state',
              label: unread ? 'Mark as Read' : 'Mark as Unread',
              icon: <MenuBellIcon withDot={!unread} />,
              onClick: () => (unread ? onMarkRead(chat.id) : onMarkUnread(chat.id)),
            },
          ]
        : []),
      { type: 'separator' },
      ...(onCopySessionId || onCopyTranscript
        ? [
            {
              type: 'submenu' as const,
              id: 'copy',
              label: 'Copy',
              icon: <MenuCopyIcon />,
              children: [
                ...(onCopySessionId
                  ? [
                      {
                        type: 'item' as const,
                        id: 'copy-id',
                        label: 'Copy Agent ID',
                        icon: <MenuHashIcon />,
                        onClick: () => onCopySessionId(chat.id),
                      },
                    ]
                  : []),
                ...(onCopyTranscript
                  ? [
                      {
                        type: 'item' as const,
                        id: 'copy-transcript',
                        label: 'Copy Transcript',
                        icon: <MenuTranscriptIcon />,
                        onClick: () => {
                          void onCopyTranscript(chat.id)
                        },
                      },
                    ]
                  : []),
              ],
            },
            { type: 'separator' as const },
          ]
        : []),
      {
        type: 'item',
        id: 'delete',
        label: 'Delete',
        icon: <MenuTrashIcon />,
        danger: true,
        disabled: isStreaming,
        onClick: () => setConfirmDeleteId(chat.id),
      },
    ]
    setContextMenu({ x: e.clientX, y: e.clientY, items })
  }

  if (collapsed) {
    return (
      <aside className="flex h-dvh w-12 shrink-0 flex-col items-center border-r border-[var(--sidebar-border)] bg-[var(--sidebar-bg)] py-3">
        <button
          type="button"
          onClick={() => onNewSession()}
          disabled={isLoading || isStreaming}
          title="New Chat"
          className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)] disabled:opacity-40"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
        <div className="mt-auto flex flex-col items-center gap-1">
          <FooterIconButton title={isDark ? '切换浅色模式' : '切换深色模式'} onClick={onToggleTheme}>
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
      <div className="px-3 pt-3">
        <button
          type="button"
          onClick={() => onNewSession()}
          disabled={isLoading || isStreaming}
          className="flex w-full items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--surface-hover)] px-3 py-2 text-[15px] font-medium tracking-[0.02em] text-[var(--sidebar-text)] transition-colors hover:bg-[var(--surface-active)] disabled:opacity-40"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New Chat
        </button>
      </div>

      <nav className="mt-2 flex flex-col gap-0.5 px-2">
        <NavItem icon="search" label="Search" onClick={onOpenSearch} />
        <NavItem
          icon="star"
          label="收藏内容"
          badge={favoriteCount > 0 ? favoriteCount : undefined}
          onClick={onOpenFavorites}
        />
      </nav>

      <div className="mt-3 flex items-center gap-1 px-2">
        <div className="min-w-0 flex-1 px-1 text-[13.5px] font-medium tracking-[0.01em] text-[var(--sidebar-text)]">
          Workspaces
        </div>
        <button
          ref={openWorkspaceBtnRef}
          type="button"
          title="Open Workspace"
          aria-label="Open Workspace"
          aria-expanded={openWorkspaceMenu}
          onClick={() => setOpenWorkspaceMenu((v) => !v)}
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-[var(--sidebar-muted)] transition-colors hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]"
        >
          <FolderPlusIcon />
        </button>
      </div>

      <OpenWorkspaceMenu
        open={openWorkspaceMenu}
        onClose={() => setOpenWorkspaceMenu(false)}
        recents={projects.filter((p) => !!p.root)}
        anchorRef={openWorkspaceBtnRef}
        onSelectRecent={(id) => onActivateProject(id)}
        onBrowseThisPc={onBrowseThisPc}
      />

      <div className="mt-1 flex-1 overflow-y-auto px-2 pb-2">
        {projects.map((project) => {
          const isOpen = expanded[project.id] ?? false
          const isActive = project.id === activeProjectId
          const folderSessions = sessionsByProject[project.id] ?? []

          return (
            <div key={project.id} className="mb-0.5">
              <div
                className={[
                  'group flex w-full items-center gap-1 rounded-md px-1.5 py-1 transition-colors',
                  isActive
                    ? 'text-[var(--sidebar-text)]'
                    : 'text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]',
                ].join(' ')}
                onContextMenu={(e) => openProjectContextMenu(e, project)}
              >
                <button
                  type="button"
                  title={isOpen ? '收起' : '展开'}
                  onClick={() => toggleExpand(project.id)}
                  className="flex h-6 w-5 shrink-0 items-center justify-center rounded text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]"
                >
                  <ChevronIcon open={isOpen} />
                </button>
                <button
                  type="button"
                  title={project.root || '未绑定本地目录'}
                  onClick={() => {
                    onActivateProject(project.id)
                    setExpanded((prev) => ({ ...prev, [project.id]: true }))
                  }}
                  className="flex min-w-0 flex-1 items-center gap-1.5 rounded px-0.5 py-0.5 text-left"
                >
                  <FolderIcon open={isOpen} />
                  <span className="min-w-0 truncate text-[13.5px] font-medium tracking-[0.01em]">
                    {project.name}
                  </span>
                </button>
                <button
                  type="button"
                  title={`在「${project.name}」下新建对话`}
                  disabled={isLoading || isStreaming}
                  onClick={(e) => {
                    e.stopPropagation()
                    onActivateProject(project.id)
                    setExpanded((prev) => ({ ...prev, [project.id]: true }))
                    onNewSession(project.id)
                  }}
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded opacity-0 transition-opacity hover:bg-[var(--sidebar-hover)] group-hover:opacity-100 disabled:opacity-30"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5">
                    <path d="M12 5v14M5 12h14" />
                  </svg>
                </button>
              </div>

              {isOpen && (
                <div className="ml-5 mt-0.5 flex flex-col gap-0.5">
                  {isLoading ? (
                    <span className="px-2 py-1 text-[13.5px] text-[var(--sidebar-muted)]">加载中...</span>
                  ) : folderSessions.length === 0 ? (
                    <span className="px-2 py-1 text-[13.5px] text-[var(--sidebar-muted)]">暂无对话</span>
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
                              className="min-w-0 flex-1 rounded-md border border-[var(--input-border)] bg-[var(--input-bg)] px-2 py-1 text-[13px] text-[var(--sidebar-text)] shadow-sm outline-none ring-1 ring-transparent transition-[border-color,box-shadow] focus:border-[var(--input-focus)] focus:ring-[var(--accent-bg)]"
                              aria-label="重命名对话"
                            />
                          </div>
                        )
                      }

                      if (isConfirmingDelete) {
                        return (
                          <div
                            key={chat.id}
                            className="flex w-full items-center gap-2 rounded-md border border-red-500/20 bg-red-500/[0.06] px-2 py-1.5"
                          >
                            <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--sidebar-text)]">
                              Delete「{chat.title}」?
                            </span>
                            <button
                              type="button"
                              className="shrink-0 rounded-md px-2 py-0.5 text-[11px] text-[var(--sidebar-muted)] transition-colors hover:bg-[var(--sidebar-hover)]"
                              onClick={(e) => {
                                e.stopPropagation()
                                setConfirmDeleteId(null)
                              }}
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              disabled={isStreaming}
                              className="shrink-0 rounded-md bg-red-500/15 px-2 py-0.5 text-[11px] font-medium text-red-400 transition-colors hover:bg-red-500/25 disabled:opacity-40"
                              onClick={(e) => {
                                e.stopPropagation()
                                setConfirmDeleteId(null)
                                onDeleteSession(chat.id)
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        )
                      }

                      const showDot = chat.showUnreadDot
                      return (
                        <div
                          key={chat.id}
                          className={[
                            'group/session flex w-full items-center gap-1 rounded-md py-[5px] pl-1.5 pr-2 transition-colors duration-100',
                            chat.isActive
                              ? 'bg-[var(--sidebar-active)] text-[var(--sidebar-text)]'
                              : 'text-[var(--sidebar-muted)] hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]',
                          ].join(' ')}
                          onContextMenu={(e) => openSessionContextMenu(e, chat)}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setConfirmDeleteId(null)
                              onActivateProject(project.id)
                              onSwitchSession(chat.id)
                            }}
                            onDoubleClick={() => beginRename(chat.id, chat.title)}
                            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                            title={chat.title}
                          >
                            <span className="flex h-4 w-2.5 shrink-0 items-center justify-center">
                              {showDot ? <UnreadDot /> : null}
                            </span>
                            <span
                              className={[
                                'min-w-0 flex-1 truncate text-[13px] leading-snug tracking-[0.01em]',
                                showDot ? 'font-[550] text-[var(--sidebar-text)]' : 'font-[450]',
                              ].join(' ')}
                            >
                              {chat.title}
                            </span>
                          </button>
                          <div className="flex shrink-0 items-center gap-1.5 pl-1">
                            {chat.isPinned && <SessionPinIcon />}
                            {chat.updatedAt && (
                              <span className="text-[11px] tabular-nums text-[var(--text-dim)] opacity-80 group-hover/session:opacity-100">
                                {formatRelativeTime(chat.updatedAt)}
                              </span>
                            )}
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

        {projects.every((p) => !p.root) && (
          <p className="px-2 py-3 text-xs leading-relaxed text-[var(--sidebar-muted)]">
            用 This PC 绑定本地目录后，会在这里显示为项目文件夹。
          </p>
        )}
      </div>

      <div className="border-t border-[var(--sidebar-border)] p-3">
        <div className="flex items-center gap-1">
          <FooterIconButton title={isDark ? '切换浅色模式' : '切换深色模式'} onClick={onToggleTheme}>
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

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenu.items}
          onClose={() => setContextMenu(null)}
        />
      )}
    </aside>
  )
}

/** Folder with plus — Open Workspace. */
/** Open Workspace — 16×16 grid keeps strokes crisp at sidebar size. */
function FolderPlusIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4"
      aria-hidden
    >
      <path d="M2 5.25A1.25 1.25 0 0 1 3.25 4h3.05l1.1 1.2h5.35A1.25 1.25 0 0 1 14 6.45v6.3A1.25 1.25 0 0 1 12.75 14h-9.5A1.25 1.25 0 0 1 2 12.75v-7.5Z" />
      <path d="M8 8v3.5M6.25 9.75h3.5" />
    </svg>
  )
}

/** Lucide-style folder; open/closed crossfade via opacity. */
function FolderIcon({ open }: { open: boolean }) {
  const base =
    'absolute inset-0 h-4 w-4 transition-opacity duration-200 ease-out'
  return (
    <span className="relative h-4 w-4 shrink-0 text-[var(--sidebar-muted)] opacity-90">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={[base, open ? 'opacity-0' : 'opacity-100'].join(' ')}
        aria-hidden
      >
        <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
      </svg>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={[base, open ? 'opacity-100' : 'opacity-0'].join(' ')}
        aria-hidden
      >
        <path d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />
      </svg>
    </span>
  )
}

function FooterIconButton({
  title,
  onClick,
  children,
}: {
  title: string
  onClick: () => void
  children: ReactNode
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
      className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-[14px] font-[500] tracking-[0.02em] text-[var(--sidebar-muted)] transition-colors hover:bg-[var(--sidebar-hover)] hover:text-[var(--sidebar-text)]"
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
