import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  emitAudit,
  fetchHealth,
  fetchModelProfiles,
  fetchRuntime,
  fetchWorkspace,
  getMessages,
  getSession,
  setApiErrorLocale,
  setWorkspace,
  toggleMessageFavorite,
  type FavoriteItem,
  type WorkspaceStatus,
} from './api/agent'
import { ChatInput } from './components/ChatInput'
import { DiffPanel } from './components/DiffPanel'
import { FavoritesPanel } from './components/FavoritesPanel'
import { FilesPanel, FilesPanelToggleIcon } from './components/FilesPanel'
import { MemoryPanel } from './components/MemoryPanel'
import { MessageList } from './components/MessageList'
import { MessageNavigator } from './components/MessageNavigator'
import { ModelPicker } from './components/ModelPicker'
import { SearchPanel } from './components/SearchPanel'
import { SettingsPanel } from './components/SettingsPanel'
import { ShellPanel } from './components/ShellPanel'
import { Sidebar } from './components/Sidebar'
import { SurfaceHost, type SurfaceKind } from './components/SurfaceHost'
import type { GateFocusTarget } from './components/TurnActivity'
import { SetupWizard } from './components/SetupWizard'
import { WorkspacePicker } from './components/WorkspacePicker'
import { useGlobalFavorites } from './hooks/useFavorites'
import { useMessagePairs } from './hooks/useMessagePairs'
import { applyFontSize, applyTheme, useSettings } from './hooks/useSettings'
import { I18nProvider, translate } from './i18n'
import { useApiSessions } from './hooks/useSessions'
import { useSessionMeta } from './hooks/useSessionMeta'
import { uploadAttachment } from './api/agent'
import { buildMessagePairs } from './utils/turnTrace'
import { buildSoftLandContinueMessage } from './utils/softLandContinue'
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
  UNBOUND_PROJECT_ID,
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
    reclaimSessionsToProject,
    assignSessionToProject,
    syncSessionsFromServer,
    removeSessionFromProject,
    removeProjectFromSidebar,
    toggleSidebarCollapsed,
    setSidebarWidth,
    projectIdForSession,
  } = useWorkspaces()

  const { isDark, toggleTheme, setTheme } = useTheme()
  const [showSettings, setShowSettings] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [showModelPicker, setShowModelPicker] = useState(false)
  const [modelPickerAnchor, setModelPickerAnchor] = useState<DOMRect | null>(null)
  const [modelName, setModelName] = useState(loadModel)
  const modelSyncedSessionRef = useRef<string | null>(null)
  const modelFallbackRef = useRef<
    (modelId: string, profileId?: string | null, sessionId?: string) => void
  >(() => {})
  const [toast, setToast] = useState<string | null>(null)
  const [showWorkspacePicker, setShowWorkspacePicker] = useState(false)
  const [workspace, setWorkspaceState] = useState<WorkspaceStatus | null>(null)
  const [activeSurface, setActiveSurface] = useState<SurfaceKind>('none')
  /** Once Files has been opened, keep it mounted (hidden) so tabs/dirty survive collapse. */
  const [filesMounted, setFilesMounted] = useState(false)

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
    bindSessionToWorkspace,
    replaceSession,
    notePrompt,
    setSessionModel,
    goalMode,
    setGoalMode,
    pinnedGoal,
    setPinnedGoal,
  } = useApiSessions(assignSessionToProject, removeSessionFromProject)

  const { settings, update: updateSetting, toggleSkill: toggleActiveSkill } = useSettings(activeSessionId)

  useEffect(() => {
    setApiErrorLocale(settings.language)
  }, [settings.language])

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
    isPairsHydrating,
    warmSession,
  } = useMessagePairs(
    activeSessionId,
    updateSessionTitle,
    refreshFavorites,
    sessions.find((s) => s.id === activeSessionId)?.model_id || undefined,
    (fallbackModel, profileId, sessionId) =>
      modelFallbackRef.current(fallbackModel, profileId, sessionId),
    Boolean(sessions.find((s) => s.id === activeSessionId)?.title_locked),
    notePrompt,
  )

  const handleContinueSoftLand = useCallback(
    (pairId: string) => {
      if (isStreaming || awaitingApproval) return
      const pair = pairs.find((p) => p.id === pairId)
      if (!pair?.softLanded) return
      const content = buildSoftLandContinueMessage({
        turnGoal: pair.goal || pair.turnMeta?.goal,
        softLandReply: pair.assistant.content,
      })
      sendMessage(content)
    },
    [isStreaming, awaitingApproval, pairs, sendMessage],
  )

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
  const [busySessionIds, setBusySessionIds] = useState<string[]>([])
  const prevBusySessionIdsRef = useRef<Set<string>>(new Set())
  const inputValueRef = useRef('')
  const attachedFilesRef = useRef<ChatAttachment[]>([])
  inputValueRef.current = inputValue
  attachedFilesRef.current = attachedFiles
  const [providerAvailable, setProviderAvailable] = useState<boolean | null>(null)
  const [pendingFavoriteId, setPendingFavoriteId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const approvalAreaRef = useRef<HTMLDivElement>(null)
  const [gateFocus, setGateFocus] = useState<GateFocusTarget | null>(null)
  const gateFocusClearRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleFocusGate = useCallback((target: GateFocusTarget) => {
    if (gateFocusClearRef.current) clearTimeout(gateFocusClearRef.current)
    setGateFocus(target)
    approvalAreaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    gateFocusClearRef.current = setTimeout(() => setGateFocus(null), 2500)
  }, [])

  // Auto-scroll to approval cards when they appear
  useEffect(() => {
    if (awaitingApproval && approvalAreaRef.current) {
      approvalAreaRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [awaitingApproval])

  useEffect(() => {
    return () => {
      if (gateFocusClearRef.current) clearTimeout(gateFocusClearRef.current)
    }
  }, [])

  const favoriteIndexMap = useMemo(() => {
    const map = new Map<string, number>()
    pairs.forEach((pair, index) => {
      if (pair.isFavorite) map.set(pair.id, index)
    })
    return map
  }, [pairs])

  const isEmpty = pairs.length === 0 && !isStreaming && !isPairsHydrating
  const globalError = sessionError || messageError
  const activeSessionTitle =
    sessions.find((s) => s.id === activeSessionId)?.title?.trim() ||
    translate(settings.language, 'appExtra.newChatTitle')

  const showToast = useCallback((message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 2200)
  }, [])

  modelFallbackRef.current = (fallbackModel, profileId, sessionId) => {
    const sid = sessionId || activeSessionId
    if (!sid) return
    const current = sessions.find((s) => s.id === sid)
    if (current) {
      replaceSession({
        ...current,
        model_id: fallbackModel,
        profile_id: profileId || current.profile_id,
      })
    }
    if (sid !== activeSessionId) return
    modelSyncedSessionRef.current = sid
    setModelName(fallbackModel)
    showToast(translate(settings.language, 'errors.modelProfileFallback'))
  }

  const activeSessionModelId =
    sessions.find((s) => s.id === activeSessionId)?.model_id ?? null
  const activeSessionLoaded = sessions.some((s) => s.id === activeSessionId)

  useEffect(() => {
    if (!activeSessionId || !activeSessionLoaded) return
    if (modelSyncedSessionRef.current === activeSessionId) return
    modelSyncedSessionRef.current = activeSessionId
    if (activeSessionModelId) {
      setModelName(activeSessionModelId)
      return
    }
    let cancelled = false
    fetchModelProfiles()
      .then((list) => {
        if (cancelled || modelSyncedSessionRef.current !== activeSessionId) return
        const active =
          list.profiles.find((p) => p.id === list.active_id && p.enabled) ??
          list.profiles.find((p) => p.enabled)
        if (active?.model_id) setModelName(active.model_id)
      })
      .catch(() => {
        // legacy row: the send omits model and the server uses the active profile
      })
    return () => {
      cancelled = true
    }
  }, [activeSessionId, activeSessionLoaded, activeSessionModelId])

  useEffect(() => {
    for (const s of sessions) {
      touchSeen(s.id, s.updated_at)
    }
  }, [sessions, touchSeen])

  const sidebarSessions = useMemo(() => {
    const busy = new Set(busySessionIds)
    if (isStreaming && activeSessionId) busy.add(activeSessionId)
    const mapped = sessions.map((s) => {
      const unread = isUnread(s.id, s.updated_at)
      const isActive = s.id === activeSessionId
      const isBusy = busy.has(s.id)
      return {
        id: s.id,
        title: s.title,
        updatedAt: s.updated_at,
        promptAt: s.last_prompt_at || s.created_at,
        isActive,
        isPinned: isPinned(s.id),
        isUnread: unread,
        isBusy,
        showUnreadDot: unread && !isBusy && (!isActive || isManuallyUnread(s.id)),
      }
    })
    return sortSessions(mapped)
  }, [
    sessions,
    activeSessionId,
    isUnread,
    isManuallyUnread,
    isPinned,
    sortSessions,
    busySessionIds,
    isStreaming,
  ])

  // Poll which sessions still have a running agent turn (sidebar title shimmer).
  useEffect(() => {
    let cancelled = false
    async function tick() {
      try {
        const runtime = await fetchRuntime()
        if (cancelled) return
        setBusySessionIds(runtime.active_sessions || [])
      } catch {
        // ignore
      }
    }
    void tick()
    const id = window.setInterval(() => {
      void tick()
    }, 2000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  // Background turn finished → unread; finished while viewing → mark read.
  useEffect(() => {
    const prev = prevBusySessionIdsRef.current
    const next = new Set(busySessionIds)
    for (const id of prev) {
      if (next.has(id)) continue
      if (id !== activeSessionId) {
        markUnread(id)
      } else {
        const session = sessions.find((s) => s.id === id)
        const now = new Date().toISOString()
        const stamp =
          session?.updated_at && session.updated_at > now ? session.updated_at : now
        markRead(id, stamp)
      }
    }
    prevBusySessionIdsRef.current = next
  }, [busySessionIds, activeSessionId, markUnread, markRead, sessions])

  const activateProject = useCallback(
    async (projectId: string) => {
      if (projectId === activeProjectId) return
      switchProject(projectId)
      const project = projects.find((p) => p.id === projectId)
      if (project?.root) {
        try {
          const status = await setWorkspace(project.root)
          setWorkspaceState(status)
        } catch {
          showToast(translate(settings.language, 'app.switchWorkspaceFailed'))
        }
      }
    },
    [activeProjectId, projects, switchProject, showToast],
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
      // Only mark-read when the user watched this session finish.
      // Do NOT markUnread here: switching sessions also clears isStreaming while
      // the background turn may still be running (Phase 1 detach).
      if (streamId && activeSessionId === streamId) {
        const session = sessions.find((s) => s.id === streamId)
        const now = new Date().toISOString()
        const stamp =
          session?.updated_at && session.updated_at > now ? session.updated_at : now
        markRead(streamId, stamp)
      }
      streamingSessionIdRef.current = null
    }
    wasStreamingRef.current = isStreaming
  }, [isStreaming, activeSessionId, markRead, sessions])

  // While viewing a session, keep it read as updated_at advances (e.g. post-stream
  // list refresh). Skip manual "Mark as Unread". Prevents a false blue dot after
  // leaving a session the user already watched to completion.
  useEffect(() => {
    if (!activeSessionId || isStreaming) return
    if (isManuallyUnread(activeSessionId)) return
    const session = sessions.find((s) => s.id === activeSessionId)
    if (!session?.updated_at) return
    if (isUnread(activeSessionId, session.updated_at)) {
      markRead(activeSessionId, session.updated_at)
    }
  }, [
    activeSessionId,
    isStreaming,
    sessions,
    isManuallyUnread,
    isUnread,
    markRead,
  ])

  const handleCopySessionId = useCallback(
    (sessionId: string) => {
      void navigator.clipboard.writeText(sessionId).then(
        () => showToast(translate(settings.language, 'app.copiedAgentId')),
        () => showToast(sessionId),
      )
    },
    [showToast],
  )

  const handleCopyTranscript = useCallback(
    async (sessionId: string) => {
      try {
        const [messages, session] = await Promise.all([
          getMessages(sessionId),
          getSession(sessionId).catch(() => null),
        ])
        const pairs = buildMessagePairs(messages, session?.leaf_id)
        const md = pairs
          .map((p) => {
            const user = `### User\n\n${p.user.content}`
            const asst = p.assistant.content
              ? `### Assistant\n\n${p.assistant.content}`
              : null
            return [user, asst].filter(Boolean).join('\n\n')
          })
          .join('\n\n')
        await navigator.clipboard.writeText(md)
        showToast(translate(settings.language, 'app.copiedTranscript'))
      } catch {
        showToast(translate(settings.language, 'app.copyFailed'))
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
            showToast(translate(settings.language, 'app.backendRestarted'))
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
        if (ws.configured && ws.root) {
          const projectId = upsertProjectFromRoot(ws.root, ws.name || undefined, false)
          // Defer reclaim until sessions are loaded (effect below); stash id on ws via state.
          void projectId
        }
      })
      .catch(() => {
        setWorkspaceState(null)
      })
  }, [showToast, upsertProjectFromRoot])

  // Remap orphan proj_* session map entries onto the current disk project (never sweep unbound).
  useEffect(() => {
    if (!workspace?.configured || !workspace.root) return
    const projectId = upsertProjectFromRoot(workspace.root, workspace.name || undefined, false)
    reclaimSessionsToProject(projectId)
  }, [
    workspace?.configured,
    workspace?.root,
    workspace?.name,
    upsertProjectFromRoot,
    reclaimSessionsToProject,
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
      showToast(translate(settings.language, 'app.pickSessionFirst'))
      return
    }

    const target = fileUploadTargetRef.current
    const localKey = `local-${Date.now()}-${file.name}`
    const previewUrl = file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined
    const pending: ChatAttachment = {
      localKey,
      name: file.name,
      kind: 'file',
      status: 'pending',
      size: file.size,
      contentType: file.type || undefined,
      previewUrl,
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
      showToast(translate(settings.language, 'app.uploaded', { name: file.name }))
    } catch (err) {
      const message = err instanceof Error ? err.message : translate(settings.language, 'appExtra.uploadFailedGeneric')
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      upsertAttachment({ ...pending, status: 'error', error: message, previewUrl: undefined }, target)
      showToast(translate(settings.language, 'app.uploadFailed', { name: file.name }))
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
    const text =
      translate(settings.language, 'appExtra.planTemplate')
    if (expandedUser) {
      setExpandedUser((prev) => (prev ? { ...prev, draft: text } : prev))
    } else {
      setInputValue(text)
    }
    showToast(translate(settings.language, 'app.planFilled'))
  }

  const handleMultitask = () => {
    const text = translate(settings.language, 'appExtra.multitaskTemplate')
    if (expandedUser) {
      setExpandedUser((prev) => (prev ? { ...prev, draft: text } : prev))
    } else {
      setInputValue(text)
    }
    showToast(translate(settings.language, 'app.multitaskFilled'))
  }

  const handleAddFileToChat = useCallback(
    (relativePath: string) => {
      const token = `@${relativePath.replace(/^@+/, '')}`
      const insert = (prev: string) => {
        if (!prev.trim()) return `${token} `
        const sep = prev.endsWith(' ') || prev.endsWith('\n') ? '' : ' '
        return `${prev}${sep}${token} `
      }
      if (expandedUser) {
        setExpandedUser((prev) => (prev ? { ...prev, draft: insert(prev.draft) } : prev))
      } else {
        setInputValue((prev) => insert(prev))
      }
      showToast(translate(settings.language, 'app.tokenAdded', { token }))
    },
    [expandedUser, showToast],
  )

  const handleBindSessionToProject = useCallback(
    async (sessionId: string, project: (typeof projects)[number]) => {
      const root = (project.root ?? '').trim()
      if (!root || project.id === UNBOUND_PROJECT_ID) return
      try {
        await bindSessionToWorkspace(sessionId, root)
        assignSessionToProject(sessionId, project.id)
        if (sessionId === activeSessionId) {
          await activateProject(project.id)
        }
        showToast(translate(settings.language, 'app.movedWorkspace', { name: project.name }))
      } catch (err) {
        showToast(err instanceof Error ? err.message : translate(settings.language, 'app.bindFailed'))
        throw err
      }
    },
    [
      bindSessionToWorkspace,
      assignSessionToProject,
      activeSessionId,
      activateProject,
      showToast,
    ],
  )

  const handleWorkspaceSaved = (status: WorkspaceStatus) => {
    setWorkspaceState(status)
    if (status.configured && status.root) {
      const projectId = upsertProjectFromRoot(status.root, status.name || undefined)
      if (activeSessionId) {
        assignSessionToProject(activeSessionId, projectId)
      }
    }
    showToast(
      status.configured
        ? translate(settings.language, 'app.workspaceBound', {
            name: status.name || status.root || '',
          })
        : translate(settings.language, 'app.workspaceCleared'),
    )
  }

  const handleModelSelect = (model: string, profileId?: string | null) => {
    const prev = modelName
    const current = sessions.find((s) => s.id === activeSessionId)
    setModelName(model)
    if (!profileId) {
      try {
        localStorage.setItem(MODEL_KEY, model)
      } catch {
        // last typed id only; a profile pick is stored on the session
      }
    }
    if (activeSessionId && current) {
      modelSyncedSessionRef.current = activeSessionId
      replaceSession({
        ...current,
        model_id: model,
        profile_id: profileId || current.profile_id,
      })
      const patch: { model_id: string; profile_id?: string } = { model_id: model }
      if (profileId) patch.profile_id = profileId
      void setSessionModel(activeSessionId, patch).catch(() => {
        replaceSession(current)
        setModelName(prev)
        showToast(translate(settings.language, 'app.bindFailed'))
      })
    }
    if (model !== prev) {
      emitAudit('model.switch', { from: prev, to: model }, activeSessionId || undefined).catch(() => {})
    }
    showToast(translate(settings.language, 'app.modelSwitched', { model }))
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

  const handleGoalModeToggle = () => {
    if (!activeSessionId) return
    void setGoalMode(!goalMode)
  }

  const openModelPicker = (rect: DOMRect) => {
    setShowModelPicker((open) => {
      if (open) {
        setModelPickerAnchor(null)
        return false
      }
      setModelPickerAnchor(rect)
      return true
    })
  }

  const closeModelPicker = () => {
    setShowModelPicker(false)
    setModelPickerAnchor(null)
  }

  const inputToolbar = {
    onModelClick: openModelPicker,
    onRemoveAttachment: (localKey: string) => {
      const revoke = (list: ChatAttachment[]) => {
        const hit = list.find((a) => a.localKey === localKey)
        if (hit?.previewUrl) URL.revokeObjectURL(hit.previewUrl)
        return list.filter((a) => a.localKey !== localKey)
      }
      if (expandedUser) {
        setExpandedUser((prev) =>
          prev ? { ...prev, attachedFiles: revoke(prev.attachedFiles) } : prev,
        )
      } else {
        setAttachedFiles((prev) => revoke(prev))
      }
    },
    goalMode,
    onGoalModeToggle: activeSessionId ? handleGoalModeToggle : undefined,
    onMultitask: handleMultitask,
    onPlanIdea: handlePlanIdea,
    pinnedGoal,
    onPinnedGoalChange: activeSessionId
      ? (goal: string | null) => {
          void setPinnedGoal(goal)
        }
      : undefined,
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
    onModelClick: openModelPicker,
    goalMode,
    onGoalModeToggle: activeSessionId ? handleGoalModeToggle : undefined,
    onMultitask: handleMultitask,
    onPlanIdea: handlePlanIdea,
    pinnedGoal,
    onPinnedGoalChange: activeSessionId
      ? (goal: string | null) => {
          void setPinnedGoal(goal)
        }
      : undefined,
    isStreaming: inputBusy,
    disabled: !activeSessionId || userCardExpanded,
    dimmed: userCardExpanded,
    attachments: attachedFiles,
    onRemoveAttachment: (localKey: string) =>
      setAttachedFiles((prev) => {
        const hit = prev.find((a) => a.localKey === localKey)
        if (hit?.previewUrl) URL.revokeObjectURL(hit.previewUrl)
        return prev.filter((a) => a.localKey !== localKey)
      }),
    modelName,
    enterToSend: settings.enterToSend,
  }

  const setupWizard = (
    <SetupWizard
      onModelSaved={(modelId, profileId) => {
        if (activeSessionId) {
          const current = sessions.find((item) => item.id === activeSessionId)
          if (current) {
            replaceSession({ ...current, model_id: modelId, profile_id: profileId })
          }
          modelSyncedSessionRef.current = activeSessionId
        }
        setModelName(modelId)
        fetchHealth()
          .then((health) => setProviderAvailable(health.provider_available))
          .catch(() => setProviderAvailable(false))
      }}
      onReady={(status) => {
        handleWorkspaceSaved(status)
        if (status.configured && status.root && activeSessionId) {
          bindSessionToWorkspace(activeSessionId, status.root).catch(() => {
            // The folder is already the workspace. The chat row can be moved later.
          })
        }
        fetchHealth()
          .then((health) => setProviderAvailable(health.provider_available))
          .catch(() => setProviderAvailable(false))
      }}
    />
  )

  if (workspace && !workspace.configured) {
    return <I18nProvider locale={settings.language}>{setupWizard}</I18nProvider>
  }

  return (
    <I18nProvider locale={settings.language}>
    <div className="flex h-dvh w-full overflow-hidden bg-[var(--bg)]">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.pdf,.txt,.md,.json,.csv,.py,.ts,.tsx,.js,.jsx,.zip,.log,*/*"
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
        onWarmSession={warmSession}
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
        onBindSessionToProject={handleBindSessionToProject}
        onDeleteSession={async (id) => {
          if (isStreaming) return
          draftBySessionRef.current.delete(id)
          try {
            await deleteSession(id)
            showToast(translate(settings.language, 'app.deletedChat'))
          } catch {
            showToast(translate(settings.language, 'app.deleteFailed'))
          }
        }}
        onRenameSession={async (id, newTitle) => {
          await renameSession(id, newTitle)
        }}
      />

      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div className="flex min-h-0 min-w-[440px] flex-1 flex-col overflow-hidden">
        <header className="flex h-10 shrink-0 items-center gap-3 border-b border-[var(--border-subtle)] px-4">
          <h1
            className="min-w-0 flex-1 truncate text-[13px] font-medium text-[var(--text-h)]"
            title={activeSessionTitle}
          >
            {activeSessionTitle}
          </h1>
          <div className="flex shrink-0 items-center gap-1.5">
            {providerAvailable === false && (
              <span className="rounded-[var(--radius-pill)] bg-amber-900/30 px-2 py-0.5 text-[11px] text-amber-400">
                {translate(settings.language, 'appExtra.llmUnconfigured')}
              </span>
            )}
            <button
              type="button"
              title={
                activeSurface === 'files'
                  ? translate(settings.language, 'app.closeFiles')
                  : translate(settings.language, 'app.openFiles')
              }
              aria-label={
                activeSurface === 'files'
                  ? translate(settings.language, 'app.closeFiles')
                  : translate(settings.language, 'app.openFiles')
              }
              aria-pressed={activeSurface === 'files'}
              onClick={() => {
                if (activeSurface === 'files') {
                  setActiveSurface('none')
                } else {
                  setFilesMounted(true)
                  setActiveSurface('files')
                }
              }}
              className={[
                'flex h-8 w-8 items-center justify-center rounded-lg transition-colors',
                activeSurface === 'files'
                  ? 'text-[var(--text-h)] hover:bg-[var(--surface-hover)]'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
              ].join(' ')}
            >
              <FilesPanelToggleIcon expanded={activeSurface === 'files'} />
            </button>
          </div>
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
                  <img src="/favicon.svg" alt="Loop Agent" className="h-14 w-14 drop-shadow-[0_0_24px_rgba(134,59,255,0.35)]" />
                  <h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-h)]">
                    What can I help you with?
                  </h1>
                </div>
                <DiffPanel
                  patches={pendingPatches}
                  busyId={patchBusyId}
                  focusId={gateFocus?.kind === 'patch' ? gateFocus.id : null}
                  onApply={applyPendingPatch}
                  onReject={rejectPendingPatch}
                  onApplyPartial={applyPartialPatch}
                  onRetry={retryPendingPatch}
                />
                <ShellPanel
                  shells={pendingShells}
                  busyId={shellBusyId}
                  focusId={gateFocus?.kind === 'shell' ? gateFocus.id : null}
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
                  variant="center"
                  placeholder={translate(settings.language, 'app.emptyPlaceholder')}
                />
                <div className="flex flex-wrap items-center gap-2.5 pt-0.5">
                  <PillButton
                    label="Goal"
                    pressed={goalMode}
                    disabled={!activeSessionId || inputBusy}
                    title={
                      goalMode
                        ? translate(settings.language, 'appExtra.goalOn')
                        : translate(settings.language, 'appExtra.goalOff')
                    }
                    onClick={handleGoalModeToggle}
                  />
                  <PillButton
                    label={translate(settings.language, 'chat.multitask')}
                    onClick={handleMultitask}
                  />
                  <PillButton
                    label={translate(settings.language, 'chat.planIdea')}
                    onClick={handlePlanIdea}
                  />
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
              onContinueSoftLand={handleContinueSoftLand}
              onFocusGate={handleFocusGate}
              setItemRef={setItemRef}
              inputToolbar={inputToolbar}
            />

            <div
              className="mx-auto flex w-full max-w-3xl max-h-[42vh] shrink-0 flex-col overflow-hidden px-6 pb-7 pt-2"
              ref={approvalAreaRef}
            >
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
                <DiffPanel
                  patches={pendingPatches}
                  busyId={patchBusyId}
                  focusId={gateFocus?.kind === 'patch' ? gateFocus.id : null}
                  onApply={applyPendingPatch}
                  onReject={rejectPendingPatch}
                  onApplyPartial={applyPartialPatch}
                  onRetry={retryPendingPatch}
                />
                <ShellPanel
                  shells={pendingShells}
                  busyId={shellBusyId}
                  focusId={gateFocus?.kind === 'shell' ? gateFocus.id : null}
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
                  <p className="mb-2 text-center text-xs text-[var(--text-muted)]">
                    {translate(settings.language, 'appExtra.awaitingGate')}
                  </p>
                )}
              </div>
              <ChatInput {...inputProps} variant="bottom" placeholder={translate(settings.language, 'app.sendFollowUp')} />
            </div>
          </>
        )}

        {pairs.length > 0 && activeSurface !== 'files' && (
          <MessageNavigator
            currentIndex={currentIndex}
            total={pairs.length}
            onPrevious={goPrevious}
            onNext={goNext}
          />
        )}
          </div>

          {/* Keep mounted when closed so open tabs / dirty buffers survive. */}
          {filesMounted ? (
            <SurfaceHost
              surface="files"
              visible={activeSurface === 'files'}
              onClose={() => setActiveSurface('none')}
            >
              {({ onClose }) => (
                <FilesPanel
                  workspaceConfigured={Boolean(workspace?.configured)}
                  workspaceName={workspace?.name || workspace?.root}
                  workspaceRoot={workspace?.root}
                  onOpenWorkspace={() => setShowWorkspacePicker(true)}
                  onAddToChat={handleAddFileToChat}
                  onClose={onClose}
                />
              )}
            </SurfaceHost>
          ) : null}
        </div>

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
          currentProfileId={sessions.find((s) => s.id === activeSessionId)?.profile_id}
          anchor={modelPickerAnchor}
          onClose={closeModelPicker}
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
    </I18nProvider>
  )
}

function PillButton({
  label,
  onClick,
  pressed,
  disabled,
  title,
}: {
  label: string
  onClick: () => void
  pressed?: boolean
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={pressed}
      title={title}
      className={[
        'composer-chip inline-flex h-10 items-center rounded-full px-4 text-sm disabled:opacity-40',
        pressed
          ? 'border-[var(--accent-solid)] bg-[var(--accent-solid)] text-white'
          : 'border-[var(--input-border)] text-[var(--text-muted)] hover:text-[var(--text-h)]',
      ].join(' ')}
    >
      <span className="relative top-[-1px] leading-none font-medium">{label}</span>
    </button>
  )
}

export default App
