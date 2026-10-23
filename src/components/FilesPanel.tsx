import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  copyWorkspaceEntry,
  deleteWorkspaceEntry,
  fetchWorkspaceTreeStats,
  listWorkspaceFiles,
  mkdirWorkspaceDirectory,
  readWorkspaceFile,
  renameWorkspaceEntry,
  revealWorkspaceEntry,
  writeWorkspaceFile,
  type WorkspaceFileEncoding,
  type WorkspaceFileEntry,
} from '../api/agent'
import { useT } from '../i18n'
import { isMarkdownFilePath } from '../utils/filesEditorPreferences'
import { ContextMenu, type ContextMenuItem } from './ContextMenu'
import {
  MenuChatAddIcon,
  MenuCopyIcon,
  MenuCutIcon,
  MenuFolderIcon,
  MenuNewFileIcon,
  MenuPencilIcon,
  MenuRevealIcon,
  MenuTrashIcon,
} from './ContextMenuIcons'
import { Markdown } from './Markdown'

interface FilesPanelProps {
  workspaceConfigured: boolean
  workspaceName?: string | null
  workspaceRoot?: string | null
  onOpenWorkspace?: () => void
  onClose: () => void
  /** Insert `@relative/path` into the active composer. */
  onAddToChat?: (relativePath: string) => void
}

type FileTreeClipboard = {
  mode: 'copy' | 'cut'
  paths: string[]
}

function isConflictSaveError(error: string, conflictMessage: string): boolean {
  return (
    error === conflictMessage ||
    error.includes('file changed on disk') ||
    error.includes('已被其他程序修改')
  )
}

const MIN_TREE_W = 148
const MIN_EDITOR_W = 240
const DEFAULT_TREE_W = 188

type MdViewMode = 'preview' | 'source'

type FileTab = {
  path: string
  content: string
  /** Snapshot at open / last successful save — used for optimistic-lock fallback. */
  baseContent: string
  mtimeNs: string | null
  encoding: WorkspaceFileEncoding
  dirty: boolean
  mdView: MdViewMode
}

/** Prompt when closing a dirty tab (or before discard/delete). */
type ClosePrompt = {
  path: string
  intent: 'close' | 'delete'
}

type DeletePrompt = {
  path: string
  type: 'file' | 'dir'
  fileCount?: number
  dirCount?: number
}

type TreeContextMenu = {
  x: number
  y: number
  items: ContextMenuItem[]
}

function absolutePath(root: string | null | undefined, rel: string): string {
  if (!root) return rel
  const normRoot = root.replace(/\\/g, '/').replace(/\/+$/, '')
  const normRel = rel.replace(/^\/+/, '')
  return `${normRoot}/${normRel}`
}

function isValidEntryName(name: string): boolean {
  const trimmed = name.trim()
  return Boolean(trimmed) && !trimmed.includes('/') && !trimmed.includes('\\') && !trimmed.includes('..')
}

function pathIsUnderPrefix(path: string, prefix: string): boolean {
  return path === prefix || path.startsWith(`${prefix}/`)
}

function fileName(path: string): string {
  const norm = path.replace(/\\/g, '/')
  const i = norm.lastIndexOf('/')
  return i >= 0 ? norm.slice(i + 1) : norm
}

function parentDir(path: string): string {
  const norm = path.replace(/\\/g, '/').replace(/\/+$/, '')
  const i = norm.lastIndexOf('/')
  if (i < 0) return '.'
  return norm.slice(0, i) || '.'
}

function joinPath(dir: string, name: string): string {
  const d = dir.replace(/\\/g, '/').replace(/\/+$/, '')
  const n = name.replace(/\\/g, '/').replace(/^\/+/, '')
  if (!d || d === '.') return n
  return `${d}/${n}`
}

function isMarkdownPath(path: string): boolean {
  return isMarkdownFilePath(path)
}

function tabSupportsPreview(tab: FileTab): boolean {
  return isMarkdownPath(tab.path) || tab.encoding === 'docx-html'
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      className={['h-3.5 w-3.5 transition-transform duration-150', open ? 'rotate-90' : ''].join(' ')}
      aria-hidden
    >
      <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function FolderGlyph({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      className="h-4 w-4 shrink-0 opacity-80"
      aria-hidden
    >
      {open ? (
        <path
          d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ) : (
        <path
          d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  )
}

function FileGlyph() {
  // Light stroke + faint fill — stays readable on light themes without looking heavy.
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 16 16"
      fill="none"
      className="h-4 w-4 shrink-0 text-[var(--text-dim)]"
      aria-hidden
    >
      <path
        d="M3.75 2.25h5.2L12.25 5.55v8.2a1.25 1.25 0 0 1-1.25 1.25h-7.25A1.25 1.25 0 0 1 2.5 13.75v-10.25A1.25 1.25 0 0 1 3.75 2.25Z"
        fill="currentColor"
        fillOpacity={0.06}
        stroke="currentColor"
        strokeWidth={1}
        strokeLinejoin="round"
      />
      <path
        d="M8.95 2.25v2.85c0 .41.34.75.75.75h2.55"
        stroke="currentColor"
        strokeWidth={1}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function NewFileGlyph() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 16 16"
      fill="none"
      className="h-4 w-4 shrink-0 text-[var(--text-dim)]"
      aria-hidden
    >
      <path
        d="M3.75 2.25h5.2L12.25 5.55v8.2a1.25 1.25 0 0 1-1.25 1.25h-7.25A1.25 1.25 0 0 1 2.5 13.75v-10.25A1.25 1.25 0 0 1 3.75 2.25Z"
        fill="currentColor"
        fillOpacity={0.06}
        stroke="currentColor"
        strokeWidth={1}
        strokeLinejoin="round"
      />
      <path
        d="M8.95 2.25v2.85c0 .41.34.75.75.75h2.55"
        stroke="currentColor"
        strokeWidth={1}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M5.5 10.25h4M7.5 8.25v4" stroke="currentColor" strokeWidth={1.1} strokeLinecap="round" />
    </svg>
  )
}

function SearchIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={className} aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3-3" strokeLinecap="round" />
    </svg>
  )
}

/** Open / close the Files side panel (right dock) — same chevron language as Sidebar. */
export function FilesPanelToggleIcon({ expanded }: { expanded: boolean }) {
  // One path + flip keeps open/closed glyphs the same optical size.
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      className={['h-4 w-4', expanded ? '-scale-x-100' : ''].join(' ')}
      aria-hidden
    >
      <path d="M11 17l-5-5 5-5M19 17l-5-5 5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function TabCloseIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5" aria-hidden>
      <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
    </svg>
  )
}

type ChildrenCache = Record<string, WorkspaceFileEntry[]>

export function FilesPanel({
  workspaceConfigured,
  workspaceName,
  workspaceRoot,
  onOpenWorkspace,
  onClose: _onClose,
  onAddToChat,
}: FilesPanelProps) {
  void _onClose
  const t = useT()
  const [childrenByDir, setChildrenByDir] = useState<ChildrenCache>({})
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [loadingDirs, setLoadingDirs] = useState<Record<string, boolean>>({})
  const [query, setQuery] = useState('')
  const [searchMode, setSearchMode] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [targetDir, setTargetDir] = useState('.')

  const [tabs, setTabs] = useState<FileTab[]>([])
  const [activePath, setActivePath] = useState<string | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [diskStalePath, setDiskStalePath] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [closePrompt, setClosePrompt] = useState<ClosePrompt | null>(null)
  const [deletePrompt, setDeletePrompt] = useState<DeletePrompt | null>(null)
  const [treeContextMenu, setTreeContextMenu] = useState<TreeContextMenu | null>(null)
  const [renamingPath, setRenamingPath] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const [mkdirDraft, setMkdirDraft] = useState<{ parent: string; name: string } | null>(null)
  const [clipboard, setClipboard] = useState<FileTreeClipboard | null>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const [treeCollapsed, setTreeCollapsed] = useState(false)
  const [treeWidth, setTreeWidth] = useState(DEFAULT_TREE_W)
  const splitDragging = useRef(false)
  const shellRef = useRef<HTMLDivElement>(null)

  const tabsRef = useRef(tabs)
  tabsRef.current = tabs
  const activePathRef = useRef(activePath)
  activePathRef.current = activePath

  const activeTab = useMemo(
    () => (activePath ? tabs.find((t) => t.path === activePath) ?? null : null),
    [tabs, activePath],
  )

  const patchTab = useCallback((path: string, patch: Partial<FileTab>) => {
    setTabs((prev) => prev.map((t) => (t.path === path ? { ...t, ...patch } : t)))
  }, [])

  const loadDir = useCallback(async (path: string) => {
    setLoadingDirs((prev) => ({ ...prev, [path]: true }))
    setError(null)
    try {
      const data = await listWorkspaceFiles(path)
      const key = data.path || path
      setChildrenByDir((prev) => ({ ...prev, [key]: data.entries, [path]: data.entries }))
    } catch (e) {
      setError(e instanceof Error ? e.message : t('files.errListDir'))
    } finally {
      setLoadingDirs((prev) => ({ ...prev, [path]: false }))
    }
  }, [t])

  useEffect(() => {
    if (!workspaceConfigured) return
    void loadDir('.')
  }, [workspaceConfigured, loadDir])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!splitDragging.current || !shellRef.current) return
      const rect = shellRef.current.getBoundingClientRect()
      const fromRight = rect.right - e.clientX
      const maxTree = Math.max(MIN_TREE_W, rect.width - MIN_EDITOR_W)
      setTreeWidth(Math.min(maxTree, Math.max(MIN_TREE_W, fromRight)))
    }
    const onUp = () => {
      splitDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  useEffect(() => {
    const el = shellRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      const w = el.getBoundingClientRect().width
      const maxTree = Math.max(MIN_TREE_W, w - MIN_EDITOR_W)
      setTreeWidth((prev) => Math.min(prev, maxTree))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const removeTab = useCallback((path: string) => {
    setTabs((prev) => {
      const next = prev.filter((t) => t.path !== path)
      setActivePath((cur) => {
        if (cur !== path) return cur
        const idx = prev.findIndex((t) => t.path === path)
        const neighbor = next[Math.min(idx, next.length - 1)]
        return neighbor?.path ?? null
      })
      return next
    })
    setClosePrompt((p) => (p?.path === path ? null : p))
  }, [])

  const removeTabsUnder = useCallback((path: string) => {
    setTabs((prev) => {
      const next = prev.filter((t) => !pathIsUnderPrefix(t.path, path))
      setActivePath((cur) => {
        if (!cur || !pathIsUnderPrefix(cur, path)) return cur
        const idx = prev.findIndex((t) => t.path === cur)
        const neighbor = next[Math.min(idx, next.length - 1)]
        return neighbor?.path ?? null
      })
      return next
    })
    setClosePrompt((p) => (p && pathIsUnderPrefix(p.path, path) ? null : p))
  }, [])

  const saveTab = useCallback(async (path: string): Promise<boolean> => {
    const tab = tabsRef.current.find((t) => t.path === path)
    if (!tab) return true
    if (!tab.dirty) return true
    if (tab.mtimeNs == null) {
      setError(t('files.errSaveMissingVersion'))
      return false
    }
    setSaving(true)
    setError(null)
    try {
      const result = await writeWorkspaceFile(
        path,
        tab.content,
        tab.mtimeNs,
        tab.baseContent,
        tab.encoding,
      )
      patchTab(path, {
        mtimeNs: result.mtime_ns,
        dirty: false,
        baseContent: tab.content,
      })
      setDiskStalePath((p) => (p === path ? null : p))
      setSearchMode(false)
      setActivePath(path)
      return true
    } catch (e) {
      const raw = e instanceof Error ? e.message : t('files.errSaveFailed')
      const isConflict =
        raw.includes('file changed on disk') || raw.includes('abort')
      if (isConflict) {
        try {
          const fresh = await readWorkspaceFile(path)
          if (fresh.content === tab.baseContent) {
            const enc =
              fresh.encoding === 'docx-html' ? 'docx-html' : tab.encoding
            const result = await writeWorkspaceFile(
              path,
              tab.content,
              fresh.mtime_ns,
              tab.baseContent,
              enc,
            )
            patchTab(path, {
              mtimeNs: result.mtime_ns,
              dirty: false,
              baseContent: tab.content,
              encoding: enc,
            })
            setDiskStalePath((p) => (p === path ? null : p))
            setSearchMode(false)
            setActivePath(path)
            return true
          }
        } catch {
          // fall through to conflict message
        }
        setError(t('files.conflictSaveMessage'))
        return false
      }
      setError(raw)
      return false
    } finally {
      setSaving(false)
    }
  }, [patchTab, t])

  useEffect(() => {
    if (activePath || tabs.length === 0) return
    setActivePath(tabs[tabs.length - 1].path)
  }, [activePath, tabs])

  useEffect(() => {
    const path = activePath
    if (!path) return
    const tick = async () => {
      const tab = tabsRef.current.find((t) => t.path === path)
      if (!tab || tab.mtimeNs == null) return
      try {
        const fresh = await readWorkspaceFile(path)
        if (fresh.mtime_ns === tab.mtimeNs) {
          setDiskStalePath((p) => (p === path ? null : p))
          return
        }
        const diskUnchangedFromOpen = fresh.content === tab.baseContent
        const diskMatchesEditor = fresh.content === tab.content
        if (!tab.dirty && !diskMatchesEditor) {
          setDiskStalePath(path)
        } else if (tab.dirty && !diskUnchangedFromOpen) {
          setDiskStalePath(path)
        }
      } catch {
        // ignore poll errors
      }
    }
    void tick()
    const id = window.setInterval(() => void tick(), 5000)
    const onFocus = () => void tick()
    window.addEventListener('focus', onFocus)
    return () => {
      window.clearInterval(id)
      window.removeEventListener('focus', onFocus)
    }
  }, [activePath])

  const reloadTabFromDisk = async (path: string) => {
    setSaving(true)
    setError(null)
    try {
      const fresh = await readWorkspaceFile(path)
      const encoding: WorkspaceFileEncoding =
        fresh.encoding === 'docx-html' ? 'docx-html' : 'utf-8'
      patchTab(path, {
        content: fresh.content,
        baseContent: fresh.content,
        mtimeNs: fresh.mtime_ns,
        encoding,
        dirty: false,
      })
      setDiskStalePath((p) => (p === path ? null : p))
      setClosePrompt(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('files.errReloadFailed'))
    } finally {
      setSaving(false)
    }
  }

  const requestCloseTab = (path: string) => {
    const tab = tabsRef.current.find((t) => t.path === path)
    if (!tab) return
    if (tab.dirty) {
      setActivePath(path)
      setClosePrompt({ path, intent: 'close' })
      return
    }
    removeTab(path)
  }

  const invalidateDirCache = useCallback((dirPath: string) => {
    setChildrenByDir((prev) => {
      const next = { ...prev }
      delete next[dirPath]
      return next
    })
  }, [])

  const refreshBranch = useCallback(
    async (path: string) => {
      const parent = parentDir(path)
      invalidateDirCache(parent)
      await loadDir(parent)
    },
    [invalidateDirCache, loadDir],
  )

  const copyRelativePath = useCallback(async (path: string) => {
    try {
      await navigator.clipboard.writeText(path)
    } catch {
      setError(t('files.errCopyFailed'))
    }
  }, [t])

  const copyAbsolutePath = useCallback(
    async (path: string) => {
      try {
        await navigator.clipboard.writeText(absolutePath(workspaceRoot, path))
      } catch {
        setError(t('files.errCopyFailed'))
      }
    },
    [workspaceRoot, t],
  )

  const beginRenameEntry = useCallback((entry: WorkspaceFileEntry) => {
    setMkdirDraft(null)
    setRenamingPath(entry.path)
    setRenameDraft(entry.name)
  }, [])

  const cancelRenameEntry = useCallback(() => {
    setRenamingPath(null)
    setRenameDraft('')
  }, [])

  const remapPathPrefix = useCallback((path: string, from: string, to: string) => {
    if (path === from) return to
    if (path.startsWith(`${from}/`)) return `${to}${path.slice(from.length)}`
    return path
  }, [])

  const applyRenamedPaths = useCallback(
    (from: string, to: string) => {
      setChildrenByDir((prev) => {
        const next: ChildrenCache = {}
        for (const [key, value] of Object.entries(prev)) {
          next[remapPathPrefix(key, from, to)] = value
        }
        return next
      })
      setExpanded((prev) => {
        const next = { ...prev }
        for (const [key, open] of Object.entries(prev)) {
          const mapped = remapPathPrefix(key, from, to)
          if (mapped !== key) {
            next[mapped] = open
            delete next[key]
          }
        }
        return next
      })
      setTabs((prev) =>
        prev.map((tab) => {
          const mapped = remapPathPrefix(tab.path, from, to)
          return mapped === tab.path ? tab : { ...tab, path: mapped }
        }),
      )
      setActivePath((cur) => (cur ? remapPathPrefix(cur, from, to) : cur))
      setRenamingPath((cur) => (cur ? remapPathPrefix(cur, from, to) : cur))
    },
    [remapPathPrefix],
  )

  const commitRenameEntry = useCallback(async () => {
    if (!renamingPath) return
    const fromPath = renamingPath
    const nextName = renameDraft.trim()
    const currentName = fileName(fromPath)
    setRenamingPath(null)
    setRenameDraft('')
    if (!isValidEntryName(nextName) || nextName === currentName) {
      if (nextName && nextName !== currentName) setError(t('files.errInvalidName'))
      return
    }
    const toPath = joinPath(parentDir(fromPath), nextName)
    setError(null)
    try {
      await renameWorkspaceEntry(fromPath, toPath)
      applyRenamedPaths(fromPath, toPath)
      await refreshBranch(toPath)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('files.errRenameFailed'))
    }
  }, [applyRenamedPaths, refreshBranch, renameDraft, renamingPath, t])

  const beginMkdirIn = useCallback((dirPath: string) => {
    setRenamingPath(null)
    setMkdirDraft({ parent: dirPath, name: '' })
    setExpanded((prev) => ({ ...prev, [dirPath]: true }))
    void loadDir(dirPath)
  }, [loadDir])

  const cancelMkdir = useCallback(() => {
    setMkdirDraft(null)
  }, [])

  const commitMkdir = useCallback(async () => {
    if (!mkdirDraft) return
    const parent = mkdirDraft.parent
    const name = mkdirDraft.name.trim()
    if (!isValidEntryName(name)) {
      setError(t('files.errInvalidFolderName'))
      return
    }
    const path = joinPath(parent, name)
    setError(null)
    try {
      await mkdirWorkspaceDirectory(path)
      setMkdirDraft(null)
      invalidateDirCache(parent)
      await loadDir(parent)
      setExpanded((prev) => ({ ...prev, [parent]: true, [path]: false }))
    } catch (e) {
      setError(e instanceof Error ? e.message : t('files.errMkdirFailed'))
    }
  }, [invalidateDirCache, loadDir, mkdirDraft, t])

  const hasDirtyTabsUnder = useCallback((path: string) => {
    return tabsRef.current.some((t) => pathIsUnderPrefix(t.path, path) && t.dirty)
  }, [])

  const beginDeleteEntry = useCallback(
    (entry: WorkspaceFileEntry) => {
      if (entry.type === 'dir' && hasDirtyTabsUnder(entry.path)) {
        setError(t('files.errDirtyBeforeDelete'))
        return
      }
      if (entry.type === 'file') {
        const tab = tabsRef.current.find((t) => t.path === entry.path)
        if (tab?.dirty) {
          setActivePath(entry.path)
          setClosePrompt({ path: entry.path, intent: 'delete' })
          return
        }
        setDeletePrompt({ path: entry.path, type: 'file' })
        return
      }
      void (async () => {
        setError(null)
        try {
          const stats = await fetchWorkspaceTreeStats(entry.path)
          setDeletePrompt({
            path: entry.path,
            type: 'dir',
            fileCount: stats.file_count,
            dirCount: stats.dir_count,
          })
        } catch (err) {
          setError(err instanceof Error ? err.message : t('files.errReadFolderStats'))
        }
      })()
    },
    [hasDirtyTabsUnder, t],
  )

  const purgeDirCachesUnder = useCallback((path: string) => {
    setChildrenByDir((prev) => {
      const next: ChildrenCache = {}
      for (const [key, value] of Object.entries(prev)) {
        if (!pathIsUnderPrefix(key, path) && key !== path) {
          next[key] = value
        }
      }
      return next
    })
    setExpanded((prev) => {
      const next = { ...prev }
      for (const key of Object.keys(prev)) {
        if (pathIsUnderPrefix(key, path)) delete next[key]
      }
      return next
    })
  }, [])

  const performDelete = useCallback(
    async (path: string, isDir = false) => {
      setError(null)
      try {
        await deleteWorkspaceEntry(path, isDir)
        removeTabsUnder(path)
        invalidateDirCache(path)
        purgeDirCachesUnder(path)
        await refreshBranch(path)
        setDeletePrompt(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : t('files.errDeleteFailed'))
      }
    },
    [invalidateDirCache, purgeDirCachesUnder, refreshBranch, removeTabsUnder, t],
  )

  const cutEntry = useCallback((entry: WorkspaceFileEntry) => {
    setClipboard({ mode: 'cut', paths: [entry.path] })
  }, [])

  const copyEntryToClipboard = useCallback((entry: WorkspaceFileEntry) => {
    setClipboard({ mode: 'copy', paths: [entry.path] })
  }, [])

  const pasteIntoDir = useCallback(
    async (targetDir: string) => {
      if (!clipboard || clipboard.paths.length === 0) return
      const src = clipboard.paths[0]
      const dest = joinPath(targetDir, fileName(src))
      if (pathIsUnderPrefix(targetDir, src) && clipboard.mode === 'cut') {
        setError(t('files.errMoveIntoSelf'))
        return
      }
      setError(null)
      try {
        if (clipboard.mode === 'cut') {
          if (src !== dest) {
            await renameWorkspaceEntry(src, dest)
            applyRenamedPaths(src, dest)
            invalidateDirCache(parentDir(src))
          }
          setClipboard(null)
        } else {
          await copyWorkspaceEntry(src, dest)
        }
        invalidateDirCache(targetDir)
        await loadDir(targetDir)
        setExpanded((prev) => ({ ...prev, [targetDir]: true }))
      } catch (e) {
        setError(e instanceof Error ? e.message : t('files.errPasteFailed'))
      }
    },
    [applyRenamedPaths, clipboard, invalidateDirCache, loadDir, t],
  )

  const revealEntry = useCallback(async (path: string) => {
    setError(null)
    try {
      await revealWorkspaceEntry(path)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('files.errRevealFailed'))
    }
  }, [t])

  const openTreeContextMenu = useCallback(
    (e: React.MouseEvent, entry: WorkspaceFileEntry) => {
      e.preventDefault()
      e.stopPropagation()

      const chatItems: ContextMenuItem[] = onAddToChat
        ? [
            {
              type: 'item',
              id: 'add-chat',
              label: t('files.menuAddToChat'),
              icon: <MenuChatAddIcon />,
              onClick: () => onAddToChat(entry.path),
            },
          ]
        : []

      const revealItems: ContextMenuItem[] = [
        {
          type: 'item',
          id: 'reveal',
          label: t('files.menuReveal'),
          icon: <MenuRevealIcon />,
          onClick: () => void revealEntry(entry.path),
        },
      ]

      const createItems: ContextMenuItem[] =
        entry.type === 'dir'
          ? [
              {
                type: 'item',
                id: 'new-file',
                label: t('files.newFile'),
                icon: <MenuNewFileIcon />,
                onClick: () => {
                  setCreating(true)
                  setSearchMode(false)
                  setNewName('')
                  setTargetDir(entry.path)
                },
              },
              {
                type: 'item',
                id: 'new-folder',
                label: t('files.newFolder'),
                icon: <MenuFolderIcon />,
                onClick: () => beginMkdirIn(entry.path),
              },
            ]
          : []

      const clipboardItems: ContextMenuItem[] = [
        {
          type: 'item',
          id: 'cut',
          label: t('files.menuCut'),
          icon: <MenuCutIcon />,
          onClick: () => cutEntry(entry),
        },
        {
          type: 'item',
          id: 'copy',
          label: t('files.menuCopy'),
          icon: <MenuCopyIcon />,
          onClick: () => copyEntryToClipboard(entry),
        },
        ...(entry.type === 'dir' && clipboard
          ? [
              {
                type: 'item' as const,
                id: 'paste',
                label: t('files.menuPaste'),
                icon: <MenuCopyIcon />,
                onClick: () => void pasteIntoDir(entry.path),
              },
            ]
          : []),
      ]

      const pathItems: ContextMenuItem[] = [
        {
          type: 'item',
          id: 'copy-abs',
          label: t('files.menuCopyPath'),
          icon: <MenuCopyIcon />,
          onClick: () => void copyAbsolutePath(entry.path),
        },
        {
          type: 'item',
          id: 'copy-rel',
          label: t('files.menuCopyRelativePath'),
          icon: <MenuCopyIcon />,
          onClick: () => void copyRelativePath(entry.path),
        },
      ]

      const tailItems: ContextMenuItem[] = [
        {
          type: 'item',
          id: 'rename',
          label: t('files.menuRename'),
          icon: <MenuPencilIcon />,
          onClick: () => beginRenameEntry(entry),
        },
        {
          type: 'item',
          id: 'delete',
          label: t('files.menuDelete'),
          icon: <MenuTrashIcon />,
          danger: true,
          onClick: () => beginDeleteEntry(entry),
        },
      ]

      const items: ContextMenuItem[] = [
        ...chatItems,
        ...revealItems,
        ...(chatItems.length || revealItems.length ? [{ type: 'separator' as const }] : []),
        ...createItems,
        ...(createItems.length ? [{ type: 'separator' as const }] : []),
        ...clipboardItems,
        { type: 'separator' },
        ...pathItems,
        { type: 'separator' },
        ...tailItems,
      ]

      setTreeContextMenu({ x: e.clientX, y: e.clientY, items })
    },
    [
      beginDeleteEntry,
      beginMkdirIn,
      beginRenameEntry,
      clipboard,
      copyAbsolutePath,
      copyEntryToClipboard,
      copyRelativePath,
      cutEntry,
      onAddToChat,
      pasteIntoDir,
      revealEntry,
      t,
    ],
  )

  const openFile = async (path: string) => {
    const existing = tabsRef.current.find((t) => t.path === path)
    if (existing) {
      setActivePath(path)
      setCreating(false)
      setSearchMode(false)
      setQuery('')
      setTargetDir(parentDir(path))
      return
    }
    setFileLoading(true)
    setError(null)
    setCreating(false)
    setSearchMode(false)
    setQuery('')
    try {
      const data = await readWorkspaceFile(path)
      const content =
        typeof data.content === 'string' ? data.content : String(data.content ?? '')
      const encoding: WorkspaceFileEncoding =
        data.encoding === 'docx-html' ? 'docx-html' : 'utf-8'
      const tab: FileTab = {
        path: data.path,
        content,
        baseContent: content,
        mtimeNs: data.mtime_ns,
        encoding,
        dirty: false,
        mdView:
          encoding === 'docx-html'
            ? 'preview'
            : isMarkdownPath(data.path)
              ? 'source'
              : 'source',
      }
      setTabs((prev) => (prev.some((t) => t.path === tab.path) ? prev : [...prev, tab]))
      setActivePath(tab.path)
      setTargetDir(parentDir(tab.path))
    } catch (e) {
      setError(e instanceof Error ? e.message : t('files.errReadFailed'))
    } finally {
      setFileLoading(false)
    }
  }

  const toggleDir = async (path: string) => {
    const willOpen = !expanded[path]
    setExpanded((prev) => ({ ...prev, [path]: willOpen }))
    setTargetDir(path)
    if (willOpen && !childrenByDir[path]) {
      await loadDir(path)
    }
  }

  const startNewFile = () => {
    setCreating(true)
    setSearchMode(false)
    setNewName('')
  }

  const toggleSearch = () => {
    setCreating(false)
    if (searchMode) {
      // Second click while searching: leave search and restore the open file view.
      setSearchMode(false)
      setQuery('')
      return
    }
    setSearchMode(true)
    // Keep open tabs/buffers; only switch left pane to search.
    window.setTimeout(() => searchInputRef.current?.focus(), 0)
  }

  const confirmNewFile = async () => {
    const name = newName.trim().replace(/\\/g, '/')
    if (!name || name.includes('..') || name.startsWith('/')) {
      setError(t('files.errInvalidFileName'))
      return
    }
    const path = joinPath(targetDir, name)
    setError(null)
    try {
      const result = await writeWorkspaceFile(path, '')
      const parent = parentDir(path)
      await loadDir(parent === path ? '.' : parent)
      if (parent !== '.') {
        setExpanded((prev) => ({ ...prev, [parent]: true }))
      }
      setCreating(false)
      setNewName('')
      setQuery('')
      const tab: FileTab = {
        path: result.path,
        content: '',
        baseContent: '',
        mtimeNs: result.mtime_ns,
        encoding: 'utf-8',
        dirty: false,
        mdView: 'source',
      }
      setTabs((prev) => (prev.some((t) => t.path === tab.path) ? prev : [...prev, tab]))
      setActivePath(tab.path)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('files.errCreateFailed'))
    }
  }

  const searchHits = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return [] as WorkspaceFileEntry[]
    const hits: WorkspaceFileEntry[] = []
    const seen = new Set<string>()
    for (const entries of Object.values(childrenByDir)) {
      for (const e of entries) {
        if (e.type !== 'file') continue
        if (!e.name.toLowerCase().includes(q) && !e.path.toLowerCase().includes(q)) continue
        if (seen.has(e.path)) continue
        seen.add(e.path)
        hits.push(e)
      }
    }
    hits.sort((a, b) => a.path.localeCompare(b.path))
    return hits.slice(0, 80)
  }, [query, childrenByDir])

  if (!workspaceConfigured) {
    return (
      <div className="flex h-full flex-col">
        <PanelChrome
          tabs={[]}
          activePath={null}
          toolbarTitle={null}
          treeCollapsed
          searchActive={false}
          onSelectTab={() => {}}
          onCloseTab={() => {}}
          onNewFile={() => {}}
          onToggleTree={() => {}}
          onSearch={() => {}}
        />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
          <p className="text-[13px] text-[var(--text-muted)]">{t('files.noWorkspace')}</p>
          {onOpenWorkspace ? (
            <button
              type="button"
              onClick={onOpenWorkspace}
              className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-[13px] text-[var(--text-h)] hover:opacity-90"
            >
              {t('sidebar.openWorkspace')}
            </button>
          ) : null}
        </div>
      </div>
    )
  }

  const rootEntries = childrenByDir['.'] ?? []
  const showSearchPanel =
    !creating && (searchMode || (tabs.length === 0 && !activeTab))
  const showEditor = Boolean(activeTab) && !creating && !searchMode

  return (
    <div ref={shellRef} className="relative flex h-full min-h-0 flex-col">
      <PanelChrome
        tabs={tabs}
        activePath={activePath}
        toolbarTitle={activeTab?.path ?? null}
        treeCollapsed={treeCollapsed}
        searchActive={searchMode}
        editorToolbar={
          showEditor && activeTab
            ? (
                <FileEditorToolbar
                  dirty={activeTab.dirty}
                  saving={saving}
                  hasPreview={tabSupportsPreview(activeTab)}
                  previewLabel={activeTab.encoding === 'docx-html' ? 'Word' : 'Markdown'}
                  viewMode={activeTab.mdView}
                  onViewModeChange={(mode) => patchTab(activeTab.path, { mdView: mode })}
                  onSave={() => void saveTab(activeTab.path)}
                />
              )
            : null
        }
        onSelectTab={(p) => {
          setSearchMode(false)
          setActivePath(p)
        }}
        onCloseTab={requestCloseTab}
        onNewFile={startNewFile}
        onToggleTree={() => setTreeCollapsed((c) => !c)}
        onSearch={toggleSearch}
      />

      {error ? (
        <div className="shrink-0 border-b border-amber-900/40 bg-amber-950/20 px-3 py-1.5 text-[11px] text-amber-400">
          {error}
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-[var(--bg)]">
          {creating ? (
            <div className="flex min-h-0 flex-1 flex-col items-center px-5 pt-10">
              <div className="w-full max-w-[300px]">
                <p className="mb-2 text-[12px] text-[var(--text-dim)]">
                  {t('files.createAt')}{' '}
                  <span className="font-mono text-[var(--text-muted)]">
                    {targetDir === '.' ? '/' : targetDir}
                  </span>
                </p>
                <input
                  autoFocus
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      void confirmNewFile()
                    }
                    if (e.key === 'Escape') setCreating(false)
                  }}
                  placeholder={t('files.newFileNamePlaceholder')}
                  className="w-full rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-3.5 py-2.5 font-mono text-[13px] leading-snug text-[var(--text-h)] outline-none transition-colors placeholder:text-[var(--text-dim)] focus:border-[var(--border)]"
                />
                <div className="mt-3 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void confirmNewFile()}
                    className="rounded-lg bg-[var(--accent-bg)] px-3 py-1.5 text-[13px] font-[450] text-[var(--text-h)] hover:opacity-90"
                  >
                    {t('files.create')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setCreating(false)}
                    className="rounded-lg px-3 py-1.5 text-[13px] font-[450] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
                  >
                    {t('common.cancel')}
                  </button>
                </div>
              </div>
            </div>
          ) : showSearchPanel ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex shrink-0 flex-col items-center px-5 pt-10">
                <div className="w-full max-w-[300px]">
                  <label className="flex items-center gap-2.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated)]/70 px-3.5 py-2.5 transition-colors focus-within:border-[var(--border)] focus-within:bg-[var(--bg-elevated)]">
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center text-[var(--text-dim)]">
                      <SearchIcon className="h-[15px] w-[15px]" />
                    </span>
                    <input
                      ref={searchInputRef}
                      type="search"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') {
                          e.preventDefault()
                          setQuery('')
                          setSearchMode(false)
                        }
                      }}
                      placeholder={t('files.searchWidePlaceholder')}
                      className="min-w-0 flex-1 bg-transparent text-[13px] leading-snug tracking-[0.01em] text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)]"
                    />
                  </label>
                  {!query.trim() ? (
                    <button
                      type="button"
                      onClick={startNewFile}
                      className="mt-3 flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-[13px] font-[450] leading-snug tracking-[0.01em] text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
                    >
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                        <NewFileGlyph />
                      </span>
                      <span>{t('files.newFileShort')}</span>
                    </button>
                  ) : null}
                </div>
              </div>
              {query.trim() ? (
                <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3 pt-2">
                  {searchHits.length === 0 ? (
                    <p className="px-4 py-6 text-center text-[12px] text-[var(--text-dim)]">
                      {t('files.noSearchMatches')}
                    </p>
                  ) : (
                    searchHits.map((hit) => (
                      <button
                        key={hit.path}
                        type="button"
                        onClick={() => void openFile(hit.path)}
                        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] font-[450] leading-snug tracking-[0.01em] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
                      >
                        <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                          <FileGlyph />
                        </span>
                        <span className="min-w-0 flex-1 truncate">{hit.name}</span>
                        <span className="max-w-[40%] truncate font-mono text-[11px] text-[var(--text-dim)]">
                          {parentDir(hit.path)}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              ) : null}
            </div>
          ) : showEditor && activeTab ? (
            <div className="relative min-h-0 flex-1">
              {fileLoading ? (
                <p className="absolute inset-0 flex items-center justify-center text-[12px] text-[var(--text-dim)]">
                  {t('files.loadingFile')}
                </p>
              ) : (
                <>
                  {diskStalePath === activeTab.path ? (
                    <div
                      className="absolute left-0 right-0 top-0 z-[2] flex flex-wrap items-center gap-2 border-b border-amber-900/40 bg-amber-950/90 px-3 py-1 text-[11px] text-amber-300"
                    >
                      <span>{t('files.diskUpdated')}</span>
                      <button
                        type="button"
                        className="rounded px-1.5 py-0.5 hover:bg-amber-900/30"
                        onClick={() => void reloadTabFromDisk(activeTab.path)}
                      >
                        {t('files.reload')}
                      </button>
                      {activeTab.dirty ? (
                        <button
                          type="button"
                          className="rounded px-1.5 py-0.5 hover:bg-amber-900/30"
                          onClick={() => void saveTab(activeTab.path)}
                        >
                          {t('files.saveLocalAnyway')}
                        </button>
                      ) : null}
                    </div>
                  ) : null}

                  {(() => {
                    const editorPad = [
                      'px-4 py-3',
                      diskStalePath === activeTab.path ? 'pt-9' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')
                    const onContentChange = (value: string) => {
                      patchTab(activeTab.path, { content: value, dirty: true })
                      setDiskStalePath((p) => (p === activeTab.path ? null : p))
                    }
                    const onKeySave = (e: React.KeyboardEvent) => {
                      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
                        e.preventDefault()
                        if (!saving) void saveTab(activeTab.path)
                      }
                    }
                    const inPreview =
                      tabSupportsPreview(activeTab) && activeTab.mdView === 'preview'

                    if (inPreview && activeTab.encoding === 'docx-html') {
                      return (
                        <DocHtmlEditor
                          key={`${activeTab.path}:${activeTab.mtimeNs ?? 'new'}`}
                          className={[
                            'absolute inset-0 overflow-y-auto',
                            editorPad,
                          ].join(' ')}
                          html={activeTab.content}
                          onChange={onContentChange}
                          onKeyDown={onKeySave}
                        />
                      )
                    }

                    if (inPreview && isMarkdownPath(activeTab.path)) {
                      return (
                        <div className="absolute inset-0 flex min-h-0 flex-col">
                          <div
                            className={[
                              'min-h-0 flex-1 overflow-y-auto border-b border-[var(--border-subtle)]',
                              editorPad,
                            ].join(' ')}
                          >
                            <Markdown
                              content={
                                activeTab.content || `_${t('files.emptyFile')}_`
                              }
                            />
                          </div>
                          <textarea
                            value={activeTab.content}
                            onChange={(e) => onContentChange(e.target.value)}
                            onKeyDown={onKeySave}
                            spellCheck={false}
                            aria-label={t('files.markdownEditAria', { path: activeTab.path })}
                            className="h-[min(38%,200px)] min-h-[100px] shrink-0 resize-y border-0 bg-[var(--bg)] px-4 py-2.5 font-mono text-[12.5px] leading-6 text-[var(--text-h)] outline-none"
                          />
                        </div>
                      )
                    }

                    return (
                      <textarea
                        value={activeTab.content}
                        onChange={(e) => onContentChange(e.target.value)}
                        onKeyDown={onKeySave}
                        spellCheck={false}
                        aria-label={activeTab.path}
                        className={[
                          'absolute inset-0 h-full w-full resize-none border-0 bg-[var(--bg)] font-mono text-[12.5px] leading-6 text-[var(--text-h)] outline-none',
                          editorPad,
                          activeTab.encoding === 'docx-html' ? 'text-[12px]' : '',
                        ].join(' ')}
                      />
                    )
                  })()}
                </>
              )}
            </div>
          ) : null}
        </div>

        {!treeCollapsed ? (
          <>
            <div
              role="separator"
              aria-orientation="vertical"
              title={t('files.resizeTreeTitle')}
              onMouseDown={(e) => {
                e.preventDefault()
                splitDragging.current = true
                document.body.style.cursor = 'col-resize'
                document.body.style.userSelect = 'none'
              }}
              className="relative z-[1] w-px shrink-0 cursor-col-resize bg-[var(--border-subtle)] before:absolute before:inset-y-0 before:-left-1 before:w-2 before:content-['']"
            />
            <div
              style={{ width: treeWidth }}
              className="flex min-h-0 shrink-0 flex-col bg-[var(--bg-elevated)]"
            >
              <div className="flex h-9 shrink-0 items-center gap-1.5 px-2.5">
                <FolderGlyph open />
                <span
                  className="min-w-0 flex-1 truncate text-[13px] font-[450] leading-snug tracking-[0.01em] text-[var(--text-muted)]"
                  title={workspaceName || undefined}
                >
                  {workspaceName || 'workspace'}
                </span>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto pb-1">
                {loadingDirs['.'] && rootEntries.length === 0 ? (
                  <p className="px-3 py-2 text-[12px] text-[var(--text-dim)]">{t('files.loading')}</p>
                ) : (
                  <TreeLevel
                    entries={rootEntries}
                    depth={0}
                    expanded={expanded}
                    childrenByDir={childrenByDir}
                    loadingDirs={loadingDirs}
                    openPath={activePath}
                    renamingPath={renamingPath}
                    renameDraft={renameDraft}
                    mkdirDraft={mkdirDraft}
                    onToggleDir={(p) => void toggleDir(p)}
                    onOpenFile={(p) => void openFile(p)}
                    onContextMenu={openTreeContextMenu}
                    onRenameDraftChange={setRenameDraft}
                    onRenameCommit={() => void commitRenameEntry()}
                    onRenameCancel={cancelRenameEntry}
                    onMkdirDraftChange={(name) =>
                      setMkdirDraft((draft) => (draft ? { ...draft, name } : draft))
                    }
                    onMkdirCommit={() => void commitMkdir()}
                    onMkdirCancel={cancelMkdir}
                  />
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>

      {closePrompt ? (
        <DirtyCloseDialog
          fileLabel={fileName(closePrompt.path)}
          busy={saving}
          intent={closePrompt.intent}
          error={error}
          conflictMessage={t('files.conflictSaveMessage')}
          onSave={async () => {
            const { path, intent } = closePrompt
            setError(null)
            const ok = await saveTab(path)
            if (!ok) return
            setClosePrompt(null)
            if (intent === 'delete') {
              await performDelete(path, false)
              return
            }
            removeTab(path)
          }}
          onDiscard={async () => {
            const { path, intent } = closePrompt
            setClosePrompt(null)
            setError(null)
            if (intent === 'delete') {
              await performDelete(path, false)
              return
            }
            removeTab(path)
          }}
          onCancel={() => {
            setClosePrompt(null)
            setError(null)
          }}
          onReloadFromDisk={() => void reloadTabFromDisk(closePrompt.path)}
        />
      ) : null}

      {deletePrompt ? (
        <DeleteEntryDialog
          label={fileName(deletePrompt.path)}
          isDir={deletePrompt.type === 'dir'}
          fileCount={deletePrompt.fileCount}
          dirCount={deletePrompt.dirCount}
          onConfirm={() => void performDelete(deletePrompt.path, deletePrompt.type === 'dir')}
          onCancel={() => setDeletePrompt(null)}
        />
      ) : null}

      {treeContextMenu ? (
        <ContextMenu
          x={treeContextMenu.x}
          y={treeContextMenu.y}
          items={treeContextMenu.items}
          onClose={() => setTreeContextMenu(null)}
        />
      ) : null}
    </div>
  )
}

function DocHtmlEditor({
  html,
  onChange,
  onKeyDown,
  className,
}: {
  html: string
  onChange: (html: string) => void
  onKeyDown: (e: React.KeyboardEvent) => void
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    el.innerHTML = html.trim() ? html : '<p><br></p>'
    // Only on mount (parent sets key=path so remount reloads disk content).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      ref={ref}
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-multiline
      onInput={() => onChange(ref.current?.innerHTML ?? '')}
      onKeyDown={onKeyDown}
      className={[
        'markdown-body docx-preview max-w-none text-[var(--text-h)] outline-none focus:outline-none',
        className ?? '',
      ].join(' ')}
    />
  )
}

function FileEditorToolbar({
  dirty,
  saving,
  hasPreview,
  previewLabel,
  viewMode,
  onViewModeChange,
  onSave,
}: {
  dirty: boolean
  saving: boolean
  hasPreview: boolean
  previewLabel: string
  viewMode: MdViewMode
  onViewModeChange: (mode: MdViewMode) => void
  onSave: () => void
}) {
  const t = useT()
  const chip = (active: boolean) =>
    [
      'inline-flex h-[18px] items-center rounded-full px-2 text-[11px] font-[450] leading-none tracking-[0.02em] transition-colors duration-75',
      active
        ? 'files-editor-toolbar-btn--raised bg-[var(--bg-elevated)] text-[var(--text-h)]'
        : 'text-[var(--text-muted)] hover:text-[var(--text-h)]',
    ].join(' ')

  return (
    <div
      className="files-editor-toolbar inline-flex h-[22px] shrink-0 items-center gap-[2px] rounded-full p-[2px]"
      role="toolbar"
      aria-label={t('files.editorToolbarAria')}
    >
      {hasPreview ? (
        <div
          className="flex items-center gap-[1px]"
          role="group"
          aria-label={t('files.viewModeAria', { label: previewLabel })}
        >
          <button
            type="button"
            aria-pressed={viewMode === 'preview'}
            onClick={() => onViewModeChange('preview')}
            className={chip(viewMode === 'preview')}
          >
            {t('files.preview')}
          </button>
          <button
            type="button"
            aria-pressed={viewMode === 'source'}
            onClick={() => onViewModeChange('source')}
            className={chip(viewMode === 'source')}
          >
            {t('files.source')}
          </button>
        </div>
      ) : null}
      {hasPreview ? (
        <span className="h-2.5 w-px shrink-0 bg-[var(--border-subtle)]/80" aria-hidden />
      ) : null}
      <button
        type="button"
        disabled={!dirty || saving}
        title="Ctrl+S"
        onClick={onSave}
        className={[
          'inline-flex h-[18px] shrink-0 items-center rounded-full px-2 text-[11px] font-[450] leading-none tracking-[0.02em] transition-colors duration-75 disabled:cursor-default disabled:opacity-40',
          dirty && !saving
            ? 'files-editor-toolbar-btn--raised bg-[var(--accent-bg)] text-[var(--text-h)]'
            : 'text-[var(--text-dim)]',
        ].join(' ')}
      >
        {saving ? '…' : t('files.save')}
      </button>
    </div>
  )
}

function DirtyCloseDialog({
  fileLabel,
  busy,
  intent,
  error,
  conflictMessage,
  onSave,
  onDiscard,
  onCancel,
  onReloadFromDisk,
}: {
  fileLabel: string
  busy: boolean
  intent: 'close' | 'delete'
  error: string | null
  conflictMessage: string
  onSave: () => void
  onDiscard: () => void
  onCancel: () => void
  onReloadFromDisk: () => void
}) {
  const t = useT()
  const deleting = intent === 'delete'
  const showReload = Boolean(error) && isConflictSaveError(error!, conflictMessage)
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/45 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="files-dirty-title"
        className="w-full max-w-[320px] rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4 shadow-xl"
      >
        <h2 id="files-dirty-title" className="text-[14px] font-medium text-[var(--text-h)]">
          {deleting
            ? t('files.dirtyCloseDeleteTitle', { name: fileLabel })
            : t('files.dirtyCloseTitle', { name: fileLabel })}
        </h2>
        <p className="mt-1.5 text-[12px] leading-5 text-[var(--text-muted)]">
          {deleting ? t('files.dirtyCloseDeleteBody') : t('files.dirtyCloseBody')}
        </p>
        {error ? (
          <p className="mt-2 text-[12px] leading-5 text-amber-400">{error}</p>
        ) : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          {showReload ? (
            <button
              type="button"
              disabled={busy}
              onClick={onReloadFromDisk}
              className="mr-auto rounded-md px-2.5 py-1.5 text-[12.5px] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
            >
              {t('files.reload')}
            </button>
          ) : null}
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="rounded-md px-2.5 py-1.5 text-[12.5px] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onDiscard}
            className="rounded-md px-2.5 py-1.5 text-[12.5px] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
          >
            {deleting ? t('files.discardDelete') : t('files.discard')}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onSave}
            className="rounded-md bg-[var(--accent-bg)] px-2.5 py-1.5 text-[12.5px] text-[var(--text-h)] hover:opacity-90 disabled:opacity-60"
          >
            {busy ? t('files.saving') : deleting ? t('files.saveAndDelete') : t('files.save')}
          </button>
        </div>
      </div>
    </div>
  )
}

function DeleteEntryDialog({
  label,
  isDir,
  fileCount,
  dirCount,
  onConfirm,
  onCancel,
}: {
  label: string
  isDir: boolean
  fileCount?: number
  dirCount?: number
  onConfirm: () => void
  onCancel: () => void
}) {
  const t = useT()
  const dirDetail =
    isDir && fileCount !== undefined && dirCount !== undefined
      ? t('files.deleteDirStats', { fileCount, dirCount })
      : isDir
        ? t('files.deleteDirAll')
        : null

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/45 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="files-delete-title"
        className="w-full max-w-[320px] rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] p-4 shadow-xl"
      >
        <h2 id="files-delete-title" className="text-[14px] font-medium text-[var(--text-h)]">
          {isDir
            ? t('files.deleteTitleDir', { name: label })
            : t('files.deleteTitleFile', { name: label })}
        </h2>
        <p className="mt-1.5 text-[12px] leading-5 text-[var(--text-muted)]">
          {dirDetail ?? t('files.deleteIrreversible')}
        </p>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md px-2.5 py-1.5 text-[12.5px] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-md bg-red-500/15 px-2.5 py-1.5 text-[12.5px] text-red-400 hover:bg-red-500/25"
          >
            {t('files.menuDelete')}
          </button>
        </div>
      </div>
    </div>
  )
}

function IconBtn({
  title,
  onClick,
  disabled,
  pressed,
  children,
}: {
  title: string
  onClick?: () => void
  disabled?: boolean
  pressed?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={[
        'flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors',
        disabled
          ? 'cursor-default text-[var(--text-dim)] opacity-45'
          : pressed
            ? 'bg-[var(--surface-hover)] text-[var(--text-h)]'
            : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
      ].join(' ')}
    >
      {children}
    </button>
  )
}

function MoreIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4" aria-hidden>
      <circle cx="6" cy="12" r="1.5" />
      <circle cx="12" cy="12" r="1.5" />
      <circle cx="18" cy="12" r="1.5" />
    </svg>
  )
}

function NavBackIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-4 w-4" aria-hidden>
      <path d="M15 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function NavForwardIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-4 w-4" aria-hidden>
      <path d="M9 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function OutlineListIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-4 w-4" aria-hidden>
      <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" strokeLinecap="round" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-4 w-4" aria-hidden>
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  )
}

/**
 * Row 1: tabs (multi) + <<
 * Row 2: always-on file toolbar (nav, title, … 🔍 tree)
 */
function PanelChrome({
  tabs,
  activePath,
  toolbarTitle,
  treeCollapsed,
  searchActive,
  editorToolbar,
  onSelectTab,
  onCloseTab,
  onNewFile,
  onToggleTree,
  onSearch,
}: {
  tabs: FileTab[]
  activePath: string | null
  toolbarTitle: string | null
  treeCollapsed: boolean
  searchActive: boolean
  editorToolbar?: ReactNode
  onSelectTab: (path: string) => void
  onCloseTab: (path: string) => void
  onNewFile: () => void
  onToggleTree: () => void
  onSearch: () => void
}) {
  const t = useT()
  return (
    <div className="shrink-0 bg-[var(--bg-elevated)]">
      {/* Tab row — Cursor-style: full-height tabs, active bottom indicator on the separator */}
      <div className="flex h-10 items-center gap-0.5 border-b border-[var(--border-subtle)] px-1">
        <div className="flex h-full min-w-0 flex-1 items-center gap-0 overflow-x-auto overflow-y-hidden">
          {tabs.length === 0 ? (
            <span className="flex items-center px-2.5 text-[13px] font-medium tracking-tight text-[var(--text-h)]">
              {t('files.title')}
            </span>
          ) : (
            tabs.map((tab) => {
              const active = tab.path === activePath
              return (
                <div
                  key={tab.path}
                  className={[
                    'group relative -mb-px flex h-full max-w-[160px] shrink-0 items-center gap-1 border-b-2 px-2.5 text-[12.5px] transition-colors',
                    active
                      ? 'border-[var(--text-h)] bg-[var(--surface-hover)]/40 text-[var(--text-h)]'
                      : 'border-transparent text-[var(--text-muted)] hover:bg-[var(--surface-hover)]/30 hover:text-[var(--text-h)]',
                  ].join(' ')}
                >
                  <button
                    type="button"
                    title={tab.path}
                    onClick={() => onSelectTab(tab.path)}
                    className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  >
                    <FileGlyph />
                    <span className="min-w-0 truncate">
                      {fileName(tab.path)}
                      {tab.dirty ? (
                        <span
                          className="ml-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400/90"
                          title={t('files.unsaved')}
                          aria-hidden
                        />
                      ) : null}
                    </span>
                  </button>
                  <button
                    type="button"
                    title={t('files.closeTab')}
                    onClick={(e) => {
                      e.stopPropagation()
                      onCloseTab(tab.path)
                    }}
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[var(--text-dim)] hover:bg-[var(--surface-active)] hover:text-[var(--text-h)]"
                  >
                    <TabCloseIcon />
                  </button>
                </div>
              )
            })
          )}
          <IconBtn title={t('files.newFile')} onClick={onNewFile}>
            <PlusIcon />
          </IconBtn>
        </div>
      </div>

      {/* Always-visible file toolbar */}
      <div className="flex h-9 items-center gap-0.5 px-1.5">
        <IconBtn title={t('files.navBackSoon')} disabled>
          <NavBackIcon />
        </IconBtn>
        <IconBtn title={t('files.navForwardSoon')} disabled>
          <NavForwardIcon />
        </IconBtn>
        <span
          className={[
            'ml-0.5 min-w-0 flex-1 truncate text-[12.5px]',
            toolbarTitle ? 'text-[var(--text-h)]' : 'text-[var(--text-dim)]',
          ].join(' ')}
          title={toolbarTitle || undefined}
        >
          {toolbarTitle ? fileName(toolbarTitle) : t('files.noFileOpen')}
        </span>

        {editorToolbar ? <span className="shrink-0">{editorToolbar}</span> : null}

        <IconBtn title={t('files.moreSoon')} disabled>
          <MoreIcon />
        </IconBtn>
        <IconBtn title={t('files.searchFiles')} pressed={searchActive} onClick={onSearch}>
          <SearchIcon className="h-3.5 w-3.5" />
        </IconBtn>
        <IconBtn
          title={treeCollapsed ? t('files.showTree') : t('files.hideTree')}
          pressed={!treeCollapsed}
          onClick={onToggleTree}
        >
          <OutlineListIcon />
        </IconBtn>
      </div>
    </div>
  )
}

function TreeLevel({
  entries,
  depth,
  expanded,
  childrenByDir,
  loadingDirs,
  openPath,
  renamingPath,
  renameDraft,
  mkdirDraft,
  onToggleDir,
  onOpenFile,
  onContextMenu,
  onRenameDraftChange,
  onRenameCommit,
  onRenameCancel,
  onMkdirDraftChange,
  onMkdirCommit,
  onMkdirCancel,
}: {
  entries: WorkspaceFileEntry[]
  depth: number
  expanded: Record<string, boolean>
  childrenByDir: ChildrenCache
  loadingDirs: Record<string, boolean>
  openPath: string | null
  renamingPath: string | null
  renameDraft: string
  mkdirDraft: { parent: string; name: string } | null
  onToggleDir: (path: string) => void
  onOpenFile: (path: string) => void
  onContextMenu: (e: React.MouseEvent, entry: WorkspaceFileEntry) => void
  onRenameDraftChange: (value: string) => void
  onRenameCommit: () => void
  onRenameCancel: () => void
  onMkdirDraftChange: (value: string) => void
  onMkdirCommit: () => void
  onMkdirCancel: () => void
}) {
  const t = useT()
  const pad = 8 + depth * 12
  const rowText = 'text-[13px] font-[450] leading-snug tracking-[0.01em]'

  const renderRenameInput = (_indent: number) => (
    <input
      autoFocus
      value={renameDraft}
      onChange={(e) => onRenameDraftChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault()
          onRenameCommit()
        }
        if (e.key === 'Escape') onRenameCancel()
      }}
      onBlur={onRenameCommit}
      className="min-w-0 flex-1 rounded border border-[var(--border)] bg-[var(--bg)] px-1.5 py-0.5 font-mono text-[12.5px] text-[var(--text-h)] outline-none focus:border-[var(--input-focus)]"
    />
  )

  const renderMkdirRow = (indent: number) => (
    <li>
      <div
        className="flex items-center gap-1.5 py-[3px] pr-2"
        style={{ paddingLeft: indent }}
      >
        <FolderGlyph open={false} />
        <input
          autoFocus
          value={mkdirDraft?.name ?? ''}
          onChange={(e) => onMkdirDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              onMkdirCommit()
            }
            if (e.key === 'Escape') onMkdirCancel()
          }}
          onBlur={onMkdirCommit}
          placeholder={t('files.newFolderPlaceholder')}
          className="min-w-0 flex-1 rounded border border-[var(--border)] bg-[var(--bg)] px-1.5 py-0.5 font-mono text-[12.5px] text-[var(--text-h)] outline-none focus:border-[var(--input-focus)]"
        />
      </div>
    </li>
  )

  return (
    <ul>
      {entries.map((entry) => {
        if (entry.type === 'dir') {
          const isOpen = Boolean(expanded[entry.path])
          const kids = childrenByDir[entry.path]
          const isRenaming = renamingPath === entry.path
          return (
            <li key={entry.path}>
              <div
                className="group flex w-full items-center gap-0.5 py-[3px] pr-1 text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
                style={{ paddingLeft: pad }}
                onContextMenu={(e) => onContextMenu(e, entry)}
              >
                <button
                  type="button"
                  title={isOpen ? t('files.collapseDir') : t('files.expandDir')}
                  onClick={() => onToggleDir(entry.path)}
                  className="flex h-6 w-5 shrink-0 items-center justify-center rounded hover:bg-[var(--surface-active)]"
                >
                  <ChevronIcon open={isOpen} />
                </button>
                {isRenaming ? (
                  <div className="flex min-w-0 flex-1 items-center gap-1.5 pr-1">
                    <FolderGlyph open={isOpen} />
                    {renderRenameInput(0)}
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => onToggleDir(entry.path)}
                    className="flex min-w-0 flex-1 items-center gap-1.5 rounded text-left"
                  >
                    <FolderGlyph open={isOpen} />
                    <span className={['min-w-0 truncate', rowText].join(' ')}>{entry.name}</span>
                  </button>
                )}
              </div>
              {isOpen ? (
                <div>
                  {mkdirDraft?.parent === entry.path ? renderMkdirRow(pad + 20) : null}
                  {loadingDirs[entry.path] && !kids ? (
                    <p className="py-1 text-[12px] text-[var(--text-dim)]" style={{ paddingLeft: pad + 20 }}>
                      {t('files.loading')}
                    </p>
                  ) : kids && kids.length === 0 && mkdirDraft?.parent !== entry.path ? (
                    <p className="py-1 text-[12px] text-[var(--text-dim)]" style={{ paddingLeft: pad + 20 }}>
                      {t('files.emptyDir')}
                    </p>
                  ) : kids ? (
                    <TreeLevel
                      entries={kids}
                      depth={depth + 1}
                      expanded={expanded}
                      childrenByDir={childrenByDir}
                      loadingDirs={loadingDirs}
                      openPath={openPath}
                      renamingPath={renamingPath}
                      renameDraft={renameDraft}
                      mkdirDraft={mkdirDraft}
                      onToggleDir={onToggleDir}
                      onOpenFile={onOpenFile}
                      onContextMenu={onContextMenu}
                      onRenameDraftChange={onRenameDraftChange}
                      onRenameCommit={onRenameCommit}
                      onRenameCancel={onRenameCancel}
                      onMkdirDraftChange={onMkdirDraftChange}
                      onMkdirCommit={onMkdirCommit}
                      onMkdirCancel={onMkdirCancel}
                    />
                  ) : null}
                </div>
              ) : null}
            </li>
          )
        }

        const active = openPath === entry.path
        const isRenaming = renamingPath === entry.path
        return (
          <li key={entry.path}>
            {isRenaming ? (
              <div
                className="flex items-center gap-1.5 py-[3px] pr-2"
                style={{ paddingLeft: pad + 20 }}
                onContextMenu={(e) => onContextMenu(e, entry)}
              >
                <FileGlyph />
                {renderRenameInput(0)}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => onOpenFile(entry.path)}
                onContextMenu={(e) => onContextMenu(e, entry)}
                className={[
                  'flex w-full items-center gap-1.5 py-[3px] pr-2 text-left',
                  rowText,
                  active
                    ? 'bg-[var(--surface-hover)] text-[var(--text-h)]'
                    : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
                ].join(' ')}
                style={{ paddingLeft: pad + 20 }}
              >
                <FileGlyph />
                <span className="min-w-0 truncate">{entry.name}</span>
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}
