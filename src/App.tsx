import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  emitAudit,
  fetchHealth,
  fetchModels,
  fetchRuntime,
  fetchWorkspace,
  getMessages,
  setWorkspace,
  toggleMessageFavorite,
  type FavoriteItem,
  type WorkspaceStatus,
} from './api/agent'
import { ChatInput } from './components/ChatInput'
import { DiffPanel } from './components/DiffPanel'
import { FavoritesPanel } from './components/FavoritesPanel'
import { MemoryPanel } from './components/MemoryPanel'
import { MessageList } from './components/MessageList'
import { MessageNavigator } from './components/MessageNavigator'
import { ModelPicker } from './components/ModelPicker'
import { FALLBACK_MODELS } from './components/modelFallbacks'
import { SearchPanel } from './components/SearchPanel'
import { SettingsPanel } from './components/SettingsPanel'
import { ShellPanel } from './components/ShellPanel'
import { Sidebar } from './components/Sidebar'
import { WorkspacePicker } from './components/WorkspacePicker'
import { useGlobalFavorites } from './hooks/useFavorites'
import { useMessagePairs } from './hooks/useMessagePairs'
import { applyFontSize, applyTheme, useSettings } from './hooks/useSettings'
import { useApiSessions } from './hooks/useSessions'
import { useSessionMeta } from './hooks/useSessionMeta'
import { uploadAttachment } from './api/agent'
import {
  canSendDraft,
  draftContentForSend,
  readyAttachmentIds,
  type ChatAttachment,
} from './utils/chatAttachment'
import { useTheme } from './hooks/useTheme'
import {
  normalizeRoot,
  projectIdFromRoot,
  useWorkspaces,
} from './hooks/useWorkspaces'

const MODEL_KEY = 'agent-chat:model'
const BOOT_KEY = 'agent-chat:boot_id'

function formatPreview(content: string, maxLength = 50): string {
  const trimmed = content.replace(/\s+/g, ' ').trim()
  if (trimmed.length <= maxLength) return trimmed
  return `${trimmed.slice(0, maxLength)}...`
}

function loadModel(): string {
  try {
    return localStorage.getItem(MODEL_KEY) || 'kimi-k3'
  } catch {
    return 'kimi-k3'
  }
}

function App() {
  const {
    projects,
    activeProjectId,
    sidebarCollapsed,
    sidebarWidth,
    switchProject,
    upsertProjectFromRoot,
    reclaimOrphanSessionsToProject,
    assignSessionToProject,
    syncSessionsFromServer,
    removeSessionFromProject,
    removeProjectFromSidebar,
    toggleSidebarCollapsed,
    setSidebarWidth,
    projectIdForSession,
  } = useWorkspaces()

  const { isDark, toggleTheme, setTheme } = useTheme()
  const { settings, update: updateSetting, toggleSkill: toggleActiveSkill } = useSettings()
  const [showSettings, setShowSettings] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showModelPicker, setShowModelPicker] = useState(false)
  const [modelName, setModelName] = useState(loadModel)
  const [toast, setToast] = useState<string | null>(null)
  const [pcMode, setPcMode] = useState(false)
  const [showWorkspacePicker, setShowWorkspacePicker] = useState(false)
  const [workspace, setWorkspaceState] = useState<WorkspaceStatus | null>(null)

  const {
    sessions,
    activeSessionId,
    isLoading,
    error: sessionError,
    createSession,
    switchSession,
    updateSessionTitle,
    renameSession,
    deleteSession,
  } = useApiSessions(assignSessionToProject, removeSessionFromProject)

  const {
    isPinned,
    togglePin,
    isUnread,
    isManuallyUnread,
    markRead,
    markUnread,
    sortSessions,
    touchSeen,
  } = useSessionMeta()

  const { favorites, refresh: refreshFavorites } = useGlobalFavorites()

  const {
    pairs,
    currentIndex,
    isStreaming,
    awaitingApproval,
    pendingPatches,
    pendingShells,
    pendingMemories,
    patchBusyId,
    shellBusyId,
    memoryBusyId,
    error: messageError,
    listRef,
    goPrevious,
    goNext,
    goToIndex,
    toggleFavorite,
    setItemRef,
    sendMessage,
    stopStreaming,
    setFavorite,
    applyPendingPatch,
    applyPartialPatch,
    rejectPendingPatch,
    retryPendingPatch,
    applyPendingShell,
    rejectPendingShell,
    retryPendingShell,
    applyPendingMemory,
    rejectPendingMemory,
    retryLastFailed,
    retryToolStep,
  } = useMessagePairs(activeSessionId, updateSessionTitle, refreshFavorites, modelName)

  const [showFavorites, setShowFavorites] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<ChatAttachment[]>([])
  const [expandedUser, setExpandedUser] = useState<{
    pairId: string
    draft: string
    attachedFiles: ChatAttachment[]
  } | null>(null)
  const fileUploadTargetRef = useRef<'bottom' | 'card'>('bottom')
  const draftBySessionRef = useRef(new Map<string, { text: string; attachments: ChatAttachment[] }>())
  const prevSessionIdRef = useRef<string | null>(null)
  const streamingSessionIdRef = useRef<string | null>(null)
  const wasStreamingRef = useRef(false)
  const inputValueRef = useRef('')
  const attachedFilesRef = useRef<ChatAttachment[]>([])
  inputValueRef.current = inputValue
  attachedFilesRef.current = attachedFiles
  const [providerAvailable, setProviderAvailable] = useState<boolean | null>(null)
  const [pendingFavoriteId, setPendingFavoriteId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const approvalAreaRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to approval cards when they appear
  useEffect(() => {
    if (awaitingApproval && approvalAreaRef.current) {
      approvalAreaRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [awaitingApproval])

  const favoriteIndexMap = useMemo(() => {
    const map = new Map<string, number>()
    pairs.forEach((pair, index) => {
      if (pair.isFavorite) map.set(pair.id, index)
    })
    return map
  }, [pairs])

  const isEmpty = pairs.length === 0 && !isStreaming
  const globalError = sessionError || messageError

  const showToast = useCallback((message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 2200)
  }, [])

  useEffect(() => {
    for (const s of sessions) {
      touchSeen(s.id, s.updated_at)
    }
  }, [sessions, touchSeen])

  const sidebarSessions = useMemo(() => {
    const mapped = sessions.map((s) => {
      const unread = isUnread(s.id, s.updated_at)
      const isActive = s.id === activeSessionId
      return {
        id: s.id,
        title: s.title,
        updatedAt: s.updated_at,
        isActive,
        isPinned: isPinned(s.id),
        isUnread: unread,
        showUnreadDot: unread && (!isActive || isManuallyUnread(s.id)),
      }
    })
    return sortSessions(mapped)
  }, [sessions, activeSessionId, isUnread, isManuallyUnread, isPinned, sortSessions])

  const activateProject = useCallback(
    async (projectId: string) => {
      switchProject(projectId)
      const project = projects.find((p) => p.id === projectId)
      if (project?.root) {
        try {
          const status = await setWorkspace(project.root)
          setWorkspaceState(status)
          setPcMode(status.configured)
        } catch {
          showToast('切换工作区失败')
        }
      }
    },
    [projects, switchProject, showToast],
  )

  const handleSwitchSession = useCallback(
    (id: string) => {
      const session = sessions.find((s) => s.id === id)
      markRead(id, session?.updated_at)
      switchSession(id)
      const root = (session?.workspace_root ?? '').trim()
      if (root) {
        void activateProject(projectIdFromRoot(normalizeRoot(root)))
      }
    },
    [sessions, markRead, switchSession, activateProject],
  )

  useEffect(() => {
    if (isStreaming && !wasStreamingRef.current) {
      streamingSessionIdRef.current = activeSessionId
    }
    if (!isStreaming && wasStreamingRef.current) {
      const streamId = streamingSessionIdRef.current
      if (streamId) {
        if (activeSessionId !== streamId) {
          markUnread(streamId)
        } else {
          const session = sessions.find((s) => s.id === streamId)
          markRead(streamId, session?.updated_at)
        }
      }
      streamingSessionIdRef.current = null
    }
    wasStreamingRef.current = isStreaming
  }, [isStreaming, activeSessionId, markUnread, markRead, sessions])

  const handleCopySessionId = useCallback(
    (sessionId: string) => {
      void navigator.clipboard.writeText(sessionId).then(
        () => showToast('已复制 Agent ID'),
        () => showToast(sessionId),
      )
    },
    [showToast],
  )

  const handleCopyTranscript = useCallback(
    async (sessionId: string) => {
      try {
        const messages = await getMessages(sessionId)
        const md = messages
          .map((m) => {
            const heading = m.role === 'user' ? 'User' : 'Assistant'
            return `### ${heading}\n\n${m.content}`
          })
          .join('\n\n')
        await navigator.clipboard.writeText(md)
        showToast('已复制对话记录')
      } catch {
        showToast('复制失败')
      }
    },
    [showToast],
  )

  useEffect(() => {
    applyTheme(settings.theme)
    applyFontSize(settings.fontSize)
    if (settings.theme === 'dark' || settings.theme === 'light') {
      setTheme(settings.theme)
    }
  }, [settings.theme, settings.fontSize, setTheme])

  useEffect(() => {
    fetchRuntime()
      .then((runtime) => {
        try {
          const prev = sessionStorage.getItem(BOOT_KEY)
          if (prev && prev !== runtime.boot_id) {
            showToast('后端已重启，待审批项已从服务端恢复')
          }
          sessionStorage.setItem(BOOT_KEY, runtime.boot_id)
        } catch {
          // ignore storage errors
        }
      })
      .catch(() => {
        // ignore
      })
    fetchHealth()
      .then((h) => setProviderAvailable(h.provider_available))
      .catch(() => setProviderAvailable(false))
    fetchWorkspace()
      .then((ws) => {
        setWorkspaceState(ws)
        setPcMode(ws.configured)
        if (ws.configured && ws.root) {
          const projectId = upsertProjectFromRoot(ws.root, ws.name || undefined, false)
          // Defer reclaim until sessions are loaded (effect below); stash id on ws via state.
          void projectId
        }
      })
      .catch(() => {
        setWorkspaceState(null)
        setPcMode(false)
      })
    fetchModels()
      .then((res) => {
        const ids = new Set(res.models.map((m) => m.id))
        const saved = loadModel()
        const staleFallback = FALLBACK_MODELS.includes(saved)
        if (ids.size > 0 && !ids.has(saved) && staleFallback) {
          const next = ids.has(res.default) ? res.default : res.models[0].id
          setModelName(next)
          try {
            localStorage.setItem(MODEL_KEY, next)
          } catch {
            // ignore
          }
          showToast(`模型「${saved}」不在新网关列表，已切换为 ${next}`)
        }
      })
      .catch(() => {
        // keep local selection
      })
  }, [showToast, upsertProjectFromRoot])

  // Remap orphan proj_* session map entries onto the current disk project (never sweep unbound).
  useEffect(() => {
    if (!workspace?.configured || !workspace.root) return
    const projectId = upsertProjectFromRoot(workspace.root, workspace.name || undefined, false)
    reclaimOrphanSessionsToProject(projectId)
  }, [
    workspace?.configured,
    workspace?.root,
    workspace?.name,
    upsertProjectFromRoot,
    reclaimOrphanSessionsToProject,
  ])

  // Hard-bind: upsert projects from server workspace_root and sync session map.
  useEffect(() => {
    for (const s of sessions) {
      if (s.workspace_root) upsertProjectFromRoot(s.workspace_root, undefined, false)
    }
    syncSessionsFromServer(sessions)
  }, [sessions, upsertProjectFromRoot, syncSessionsFromServer])

  useEffect(() => {
    if (!pendingFavoriteId) return
    const index = pairs.findIndex((p) => p.id === pendingFavoriteId)
    if (index >= 0) {
      goToIndex(index)
      setPendingFavoriteId(null)
      setShowFavorites(false)
    }
  }, [pendingFavoriteId, pairs, goToIndex])

  // Input drafts are per-session; new / switched chats must not inherit another session's text.
  useEffect(() => {
    const prev = prevSessionIdRef.current
    if (prev === activeSessionId) return

    if (prev) {
      draftBySessionRef.current.set(prev, {
        text: inputValueRef.current,
        attachments: attachedFilesRef.current,
      })
    }

    if (activeSessionId) {
      const draft = draftBySessionRef.current.get(activeSessionId)
      setInputValue(draft?.text ?? '')
      setAttachedFiles(draft?.attachments ?? [])
    } else {
      setInputValue('')
      setAttachedFiles([])
    }

    prevSessionIdRef.current = activeSessionId
  }, [activeSessionId])

  useEffect(() => {
    setExpandedUser(null)
  }, [activeSessionId])

  useEffect(() => {
    if (!expandedUser) return
    const onPointerDown = (e: MouseEvent) => {
      const el = e.target as Element
      if (el.closest('[data-expanded-user-card]')) return
      if (showModelPicker || showSettings || showSearch || showWorkspacePicker || showFavorites) return
      setExpandedUser(null)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [expandedUser, showModelPicker, showSettings, showSearch, showWorkspacePicker, showFavorites])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!settings.shortcuts) return
      const target = e.target as HTMLElement | null
      const typing =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault()
        if (!isLoading && !isStreaming) {
          const project = projects.find((p) => p.id === activeProjectId)
          void createSession('New Agent', activeProjectId, project?.root ?? null)
        }
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key === ',') {
        e.preventDefault()
        setShowSettings(true)
        return
      }
      if (e.key === 'Escape') {
        if (expandedUser) {
          e.preventDefault()
          setExpandedUser(null)
          return
        }
        if (isStreaming || awaitingApproval) {
          e.preventDefault()
          stopStreaming()
        }
        return
      }
      if (typing) return
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        goPrevious()
      } else if (e.key === 'ArrowDown') {
        e.preventDefault()
        goNext()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [
    settings.shortcuts,
    isLoading,
    isStreaming,
    awaitingApproval,
    createSession,
    activeProjectId,
    projects,
    stopStreaming,
    goPrevious,
    goNext,
    expandedUser,
  ])

  const handleSend = () => {
    if (isStreaming || awaitingApproval || expandedUser) return
    if (!canSendDraft(inputValue, attachedFiles)) return
    const content = draftContentForSend(inputValue)
    const ids = readyAttachmentIds(attachedFiles)
    const metas = attachedFiles
      .filter((a) => a.status === 'ready' && a.id)
      .map((a) => ({
        id: a.id as string,
        filename: a.name,
        size: a.size ?? 0,
        content_type: a.contentType,
        url: a.url || '',
      }))
    sendMessage(content, ids, metas)
    setInputValue('')
    setAttachedFiles([])
    if (activeSessionId) draftBySessionRef.current.delete(activeSessionId)
  }

  const handleExpandUser = useCallback((pairId: string, content: string) => {
    setExpandedUser({ pairId, draft: content, attachedFiles: [] })
  }, [])

  const handleExpandedSend = useCallback(() => {
    if (!expandedUser || isStreaming || awaitingApproval) return
    if (!canSendDraft(expandedUser.draft, expandedUser.attachedFiles)) return
    const content = draftContentForSend(expandedUser.draft)
    const ids = readyAttachmentIds(expandedUser.attachedFiles)
    const metas = expandedUser.attachedFiles
      .filter((a) => a.status === 'ready' && a.id)
      .map((a) => ({
        id: a.id as string,
        filename: a.name,
        size: a.size ?? 0,
        content_type: a.contentType,
        url: a.url || '',
      }))
    sendMessage(content, ids, metas)
    setExpandedUser(null)
  }, [expandedUser, isStreaming, awaitingApproval, sendMessage])

  const handleExpandedDraftChange = useCallback((value: string) => {
    setExpandedUser((prev) => (prev ? { ...prev, draft: value } : prev))
  }, [])

  const handleExpandedAttach = useCallback(() => {
    fileUploadTargetRef.current = 'card'
    fileInputRef.current?.click()
  }, [])

  const handleNewSession = async (projectId?: string) => {
    if (isLoading || isStreaming) return
    const target = projectId ?? activeProjectId
    await activateProject(target)
    const project = projects.find((p) => p.id === target)
    await createSession('New Agent', target, project?.root ?? null)
  }

  const handleUploadClick = () => {
    fileUploadTargetRef.current = 'bottom'
    fileInputRef.current?.click()
  }

  const upsertAttachment = useCallback((attachment: ChatAttachment, target: 'bottom' | 'card') => {
    const merge = (list: ChatAttachment[]) => {
      const idx = list.findIndex((a) => a.localKey === attachment.localKey)
      if (idx < 0) return [...list, attachment]
      const next = [...list]
      next[idx] = attachment
      return next
    }
    if (target === 'card') {
      setExpandedUser((prev) => (prev ? { ...prev, attachedFiles: merge(prev.attachedFiles) } : prev))
    } else {
      setAttachedFiles((prev) => merge(prev))
    }
  }, [])

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!activeSessionId) {
      showToast('请先选择会话再上传附件')
      return
    }

    const target = fileUploadTargetRef.current
    const localKey = `local-${Date.now()}-${file.name}`
    const pending: ChatAttachment = {
      localKey,
      name: file.name,
      kind: 'file',
      status: 'pending',
      size: file.size,
      contentType: file.type || undefined,
    }
    upsertAttachment(pending, target)

    try {
      const meta = await uploadAttachment(activeSessionId, file)
      upsertAttachment(
        {
          ...pending,
          id: meta.id,
          status: 'ready',
          size: meta.size,
          contentType: meta.content_type || undefined,
          url: meta.url,
        },
        target,
      )
      showToast(`已上传 ${file.name}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : '上传失败'
      upsertAttachment({ ...pending, status: 'error', error: message }, target)
      showToast(`上传失败：${file.name}`)
    }
  }

  const handleSelectFavorite = (item: FavoriteItem) => {
    if (item.session_id !== activeSessionId) {
      setPendingFavoriteId(item.id)
      handleSwitchSession(item.session_id)
      return
    }
    const index = favoriteIndexMap.get(item.id)
    if (index !== undefined) {
      goToIndex(index)
      setShowFavorites(false)
    }
  }

  const handleUnfavorite = async (item: FavoriteItem) => {
    await toggleMessageFavorite(item.id, false)
    if (item.session_id === activeSessionId) setFavorite(item.id, false)
    refreshFavorites()
  }

  const handlePlanIdea = () => {
    setInputValue(
      '帮我规划一个新想法：\n1. 目标\n2. 关键步骤\n3. 风险与备选方案\n\n我的想法是：',
    )
    showToast('已填入规划模板，补充想法后发送')
  }

  const handleMultitask = () => {
    setInputValue('请把下面任务拆成可并行的子任务，并给出优先级：\n- ')
    showToast('已填入多任务模板')
  }

  const handleThisPc = () => {
    setShowWorkspacePicker(true)
  }

  const handleWorkspaceSaved = (status: WorkspaceStatus) => {
    setWorkspaceState(status)
    setPcMode(status.configured)
    if (status.configured && status.root) {
      const projectId = upsertProjectFromRoot(status.root, status.name || undefined)
      if (activeSessionId) {
        assignSessionToProject(activeSessionId, projectId)
      }
    }
    showToast(
      status.configured
        ? `已绑定工作区：${status.name || status.root}`
        : '已清除工作区绑定',
    )
  }

  const handleModelSelect = (model: string) => {
    const prev = modelName
    setModelName(model)
    try {
      localStorage.setItem(MODEL_KEY, model)
    } catch {
      // ignore
    }
    if (model !== prev) {
      emitAudit('model.switch', { from: prev, to: model }, activeSessionId || undefined).catch(() => {})
    }
    showToast(`已切换模型：${model}`)
  }

  const handleSettingChange = <K extends keyof typeof settings>(key: K, value: (typeof settings)[K]) => {
    updateSetting(key, value)
    if (key === 'theme') {
      applyTheme(value as typeof settings.theme)
      if (value === 'dark' || value === 'light') setTheme(value)
    }
    if (key === 'fontSize') applyFontSize(value as typeof settings.fontSize)
  }

  // Keep Stop visible while Diff/Shell/Memory approval is open (stream may still be waiting).
  const inputBusy = isStreaming || awaitingApproval
  const userCardExpanded = expandedUser !== null

  const inputToolbar = {
    onModelClick: () => setShowModelPicker(true),
    onThisPc: handleThisPc,
    onRemoveAttachment: (localKey: string) => {
      if (expandedUser) {
        setExpandedUser((prev) =>
          prev ? { ...prev, attachedFiles: prev.attachedFiles.filter((a) => a.localKey !== localKey) } : prev,
        )
      } else {
        setAttachedFiles((prev) => prev.filter((a) => a.localKey !== localKey))
      }
    },
    pcMode,
    modelName,
    enterToSend: settings.enterToSend,
    disabled: !activeSessionId || inputBusy,
  }

  const inputProps = {
    value: inputValue,
    onChange: setInputValue,
    onSend: handleSend,
    onStop: stopStreaming,
    onAttach: handleUploadClick,
    onModelClick: () => setShowModelPicker(true),
    onThisPc: handleThisPc,
    pcMode,
    isStreaming: inputBusy,
    disabled: !activeSessionId || userCardExpanded,
    dimmed: userCardExpanded,
    attachments: attachedFiles,
    onRemoveAttachment: (localKey: string) =>
      setAttachedFiles((prev) => prev.filter((a) => a.localKey !== localKey)),
    modelName,
    enterToSend: settings.enterToSend,
  }

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-[var(--bg)]">
      <input
        ref={fileInputRef}
        type="file"
        accept="*/*"
        className="hidden"
        onChange={handleFileChange}
      />

      <Sidebar
        projects={projects}
        activeProjectId={activeProjectId}
        sessions={sidebarSessions}
        projectIdForSession={projectIdForSession}
        favoriteCount={favorites.length}
        collapsed={sidebarCollapsed}
        width={sidebarWidth}
        isLoading={isLoading}
        isStreaming={isStreaming}
        isDark={isDark}
        onToggleCollapsed={toggleSidebarCollapsed}
        onWidthChange={setSidebarWidth}
        onToggleTheme={() => {
          toggleTheme()
          updateSetting('theme', isDark ? 'light' : 'dark')
        }}
        onOpenSettings={() => setShowSettings(true)}
        onOpenSearch={() => setShowSearch(true)}
        onActivateProject={(id) => {
          void activateProject(id)
        }}
        onOpenFavorites={() => setShowFavorites(true)}
        onSwitchSession={handleSwitchSession}
        onNewSession={(projectId) => {
          void handleNewSession(projectId)
        }}
        onBrowseThisPc={() => setShowWorkspacePicker(true)}
        onRemoveProject={removeProjectFromSidebar}
        onTogglePin={togglePin}
        onMarkRead={(id) => {
          const session = sessions.find((s) => s.id === id)
          markRead(id, session?.updated_at)
        }}
        onMarkUnread={markUnread}
        onCopySessionId={handleCopySessionId}
        onCopyTranscript={handleCopyTranscript}
        onDeleteSession={async (id) => {
          if (isStreaming) return
          draftBySessionRef.current.delete(id)
          try {
            await deleteSession(id)
            showToast('已删除对话')
          } catch {
            showToast('删除失败，请重试')
          }
        }}
        onRenameSession={async (id, newTitle) => {
          await renameSession(id, newTitle)
        }}
      />

      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-11 shrink-0 items-center justify-end gap-2 px-4">
          {activeSessionId && (
            <button
              type="button"
              title="点击复制 session id（dogfood / curl 用）"
              onClick={() => {
                void navigator.clipboard.writeText(activeSessionId).then(
                  () => showToast(`已复制 session id`),
                  () => showToast(activeSessionId),
                )
              }}
              className="max-w-[220px] truncate rounded-[var(--radius-pill)] bg-[var(--surface-hover)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-dim)] hover:text-[var(--text-muted)]"
            >
              {activeSessionId}
            </button>
          )}
          {pcMode && workspace?.root && (
            <span
              title={workspace.root}
              className="max-w-[280px] truncate rounded-[var(--radius-pill)] bg-[var(--accent-bg)] px-2 py-0.5 font-mono text-[11px] text-[var(--text-muted)]"
            >
              {workspace.name || workspace.root}
            </span>
          )}
          {pcMode && !workspace?.root && (
            <span className="rounded-[var(--radius-pill)] bg-[var(--accent-bg)] px-2 py-0.5 text-[11px] text-[var(--text-muted)]">
              This PC
            </span>
          )}
          {providerAvailable === false && (
            <span className="rounded-[var(--radius-pill)] bg-amber-900/30 px-2 py-0.5 text-[11px] text-amber-400">
              LLM 未配置
            </span>
          )}
        </header>

        {globalError && (
          <div className="mx-4 mb-2 rounded-lg border border-red-900/50 bg-red-950/20 px-3 py-2 text-sm text-red-400">
            {globalError}
          </div>
        )}

        {isEmpty ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-6">
            <div className="flex flex-1 flex-col items-center justify-center">
              <div className="mb-[10vh] flex w-full max-w-[640px] flex-col items-stretch gap-3">
                <div className="mb-7 flex flex-col items-center gap-4 text-center">
                  <img src="/favicon.svg" alt="Hal Agent" className="h-14 w-14 drop-shadow-[0_0_24px_rgba(134,59,255,0.35)]" />
                  <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-h)]">
                    What can I help you with?
                  </h1>
                </div>
                <DiffPanel
                  patches={pendingPatches}
                  busyId={patchBusyId}
                  onApply={applyPendingPatch}
                  onReject={rejectPendingPatch}
                  onApplyPartial={applyPartialPatch}
                  onRetry={retryPendingPatch}
                />
                <ShellPanel
                  shells={pendingShells}
                  busyId={shellBusyId}
                  onApply={applyPendingShell}
                  onReject={rejectPendingShell}
                  onRetry={retryPendingShell}
                />
                <MemoryPanel
                  memories={pendingMemories}
                  busyId={memoryBusyId}
                  onApply={applyPendingMemory}
                  onReject={rejectPendingMemory}
                />
                <ChatInput
                  {...inputProps}
                  onThisPc={undefined}
                  variant="center"
                  placeholder="Plan, Build, / for skills, @ for context"
                />
                <div className="flex flex-wrap items-center gap-2.5 pt-0.5">
                  <PillButton label="Plan New Idea" shortcut="⇧Tab" onClick={handlePlanIdea} />
                  <PillButton label="Multitask" onClick={handleMultitask} />
                  <ThisPcButton active={pcMode} onClick={handleThisPc} />
                </div>
              </div>
            </div>
            <p className="shrink-0 pb-5 text-center text-xs text-[var(--text-dim)]">
              Use ↑↓ arrows to navigate between messages
            </p>
          </div>
        ) : (
          <>
            <MessageList
              ref={listRef}
              pairs={pairs}
              currentIndex={currentIndex}
              isStreaming={isStreaming}
              awaitingApproval={awaitingApproval}
              sessionId={activeSessionId}
              expandedUserPairId={expandedUser?.pairId ?? null}
              expandedDraft={expandedUser?.draft ?? ''}
              expandedAttachments={expandedUser?.attachedFiles ?? []}
              onExpandUser={handleExpandUser}
              onExpandedDraftChange={handleExpandedDraftChange}
              onExpandedSend={handleExpandedSend}
              onExpandedAttach={handleExpandedAttach}
              onToggleFavorite={toggleFavorite}
              onRetry={retryLastFailed}
              onRetryToolStep={retryToolStep}
              setItemRef={setItemRef}
              inputToolbar={inputToolbar}
            />

            <div
              className="flex max-h-[42vh] shrink-0 flex-col overflow-hidden px-6 pb-4 pt-2"
              ref={approvalAreaRef}
            >
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
                <DiffPanel
                  patches={pendingPatches}
                  busyId={patchBusyId}
                  onApply={applyPendingPatch}
                  onReject={rejectPendingPatch}
                  onApplyPartial={applyPartialPatch}
                  onRetry={retryPendingPatch}
                />
                <ShellPanel
                  shells={pendingShells}
                  busyId={shellBusyId}
                  onApply={applyPendingShell}
                  onReject={rejectPendingShell}
                  onRetry={retryPendingShell}
                />
                <MemoryPanel
                  memories={pendingMemories}
                  busyId={memoryBusyId}
                  onApply={applyPendingMemory}
                  onReject={rejectPendingMemory}
                />
                {awaitingApproval && (
                  <p className="mx-auto mb-2 max-w-3xl text-center text-xs text-[var(--text-muted)]">
                    等待你审批上方的改动、命令或记忆（Apply / Run / Reject）后，Agent 才会继续…
                  </p>
                )}
              </div>
              <ChatInput {...inputProps} variant="bottom" placeholder="Send follow-up" />
            </div>
          </>
        )}

        {pairs.length > 0 && (
          <MessageNavigator
            currentIndex={currentIndex}
            total={pairs.length}
            onPrevious={goPrevious}
            onNext={goNext}
          />
        )}

        <FavoritesPanel
          favorites={favorites}
          isOpen={showFavorites}
          onClose={() => setShowFavorites(false)}
          onSelectFavorite={handleSelectFavorite}
          onUnfavorite={handleUnfavorite}
          formatPreview={formatPreview}
        />

        <SettingsPanel
          isOpen={showSettings}
          settings={settings}
          onClose={() => setShowSettings(false)}
          onChange={handleSettingChange}
          onToggleSkill={toggleActiveSkill}
          activeSessionId={activeSessionId}
          sessions={sessions.map((s) => ({ id: s.id, title: s.title }))}
          onOpenSession={(sessionId) => {
            handleSwitchSession(sessionId)
            setShowSettings(false)
          }}
        />

        <SearchPanel
          isOpen={showSearch}
          sessions={sessions.map((s) => ({ id: s.id, title: s.title }))}
          pairs={pairs}
          onClose={() => setShowSearch(false)}
          onSelectSession={handleSwitchSession}
          onSelectPair={(pairId) => {
            const index = pairs.findIndex((p) => p.id === pairId)
            if (index >= 0) goToIndex(index)
          }}
        />

        <ModelPicker
          isOpen={showModelPicker}
          current={modelName}
          onClose={() => setShowModelPicker(false)}
          onSelect={handleModelSelect}
        />

        <WorkspacePicker
          isOpen={showWorkspacePicker}
          onClose={() => setShowWorkspacePicker(false)}
          onSaved={handleWorkspaceSaved}
        />

        {toast && (
          <div className="pointer-events-none absolute bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-full border border-[var(--border)] bg-[var(--bg-elevated)] px-4 py-2 text-sm text-[var(--text-h)] shadow-lg">
            {toast}
          </div>
        )}
      </div>
    </div>
  )
}

function PillButton({
  label,
  shortcut,
  onClick,
}: {
  label: string
  shortcut?: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-10 items-center gap-2.5 rounded-full border border-[var(--input-border)] bg-[var(--input-bg)] px-4 text-sm text-[var(--text-muted)] transition-colors hover:border-[var(--input-focus)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
    >
      <span className="font-medium">{label}</span>
      {shortcut && (
        <span className="rounded-md bg-[var(--surface-hover)] px-2 py-1 text-xs leading-none text-[var(--text-dim)]">
          {shortcut}
        </span>
      )}
    </button>
  )
}

function ThisPcButton({ active, onClick }: { active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="绑定本机工作区目录"
      className={[
        'inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm transition-colors',
        active
          ? 'border-[var(--input-focus)] bg-[var(--accent-bg)] text-[var(--text-h)]'
          : 'border-[var(--input-border)] bg-[var(--input-bg)] text-[var(--text-muted)] hover:border-[var(--input-focus)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
      ].join(' ')}
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-4 w-4">
        <rect x="3" y="4" width="18" height="14" rx="2" />
        <path d="M8 20h8M12 18v2" />
      </svg>
      <span className="font-medium">This PC</span>
    </button>
  )
}

export default App
