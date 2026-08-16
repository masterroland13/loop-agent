import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  emitAudit,
  fetchHealth,
  fetchModels,
  fetchRuntime,
  fetchWorkspace,
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
import { useTheme } from './hooks/useTheme'
import { useWorkspaces } from './hooks/useWorkspaces'

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
    workspaces,
    activeWorkspaceId,
    sidebarCollapsed,
    sidebarWidth,
    switchWorkspace,
    assignSessionToWorkspace,
    removeSessionFromWorkspace,
    toggleSidebarCollapsed,
    setSidebarWidth,
    filterSessionsByWorkspace,
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
  } = useApiSessions(assignSessionToWorkspace, removeSessionFromWorkspace)

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
  const [attachedFileName, setAttachedFileName] = useState<string | null>(null)
  const [providerAvailable, setProviderAvailable] = useState<boolean | null>(null)
  const [pendingFavoriteId, setPendingFavoriteId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const visibleSessions = useMemo(
    () => filterSessionsByWorkspace(sessions),
    [filterSessionsByWorkspace, sessions],
  )

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
  }, [showToast])

  useEffect(() => {
    if (visibleSessions.length === 0) return
    if (!visibleSessions.some((s) => s.id === activeSessionId)) {
      switchSession(visibleSessions[0].id)
    }
  }, [activeWorkspaceId, visibleSessions, activeSessionId, switchSession])

  useEffect(() => {
    if (!pendingFavoriteId) return
    const index = pairs.findIndex((p) => p.id === pendingFavoriteId)
    if (index >= 0) {
      goToIndex(index)
      setPendingFavoriteId(null)
      setShowFavorites(false)
    }
  }, [pendingFavoriteId, pairs, goToIndex])

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
        if (!isLoading && !isStreaming) void createSession('New Agent')
        return
      }
      if ((e.ctrlKey || e.metaKey) && e.key === ',') {
        e.preventDefault()
        setShowSettings(true)
        return
      }
      if (e.key === 'Escape') {
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
    stopStreaming,
    goPrevious,
    goNext,
  ])

  const handleSend = () => {
    const content = inputValue.trim()
    if (!content || isStreaming || awaitingApproval) return
    const prefix = pcMode ? '' : ''
    sendMessage(`${prefix}${content}`)
    setInputValue('')
    setAttachedFileName(null)
  }

  const handleNewSession = async () => {
    if (isLoading || isStreaming) return
    await createSession('New Agent')
  }

  const handleUploadClick = () => fileInputRef.current?.click()

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const textExts = ['.txt', '.md', '.json', '.csv', '.log', '.py', '.ts', '.tsx', '.js', '.jsx', '.html', '.css']
    const isText = file.type.startsWith('text/') || textExts.some((ext) => file.name.toLowerCase().endsWith(ext))
    if (!isText) {
      setInputValue((p) => `${p}${p ? '\n\n' : ''}[附件: ${file.name}]`)
      setAttachedFileName(file.name)
      e.target.value = ''
      return
    }
    try {
      const text = await file.text()
      const snippet = text.length > 8000 ? `${text.slice(0, 8000)}\n...(截断)` : text
      setInputValue((p) => (p ? `${p}\n\n--- ${file.name} ---\n${snippet}` : `--- ${file.name} ---\n${snippet}`))
      setAttachedFileName(file.name)
    } catch {
      setInputValue((p) => `${p}${p ? '\n\n' : ''}[读取失败: ${file.name}]`)
    }
    e.target.value = ''
  }

  const handleSelectFavorite = (item: FavoriteItem) => {
    if (item.session_id !== activeSessionId) {
      setPendingFavoriteId(item.id)
      switchSession(item.session_id)
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

  const inputProps = {
    value: inputValue,
    onChange: setInputValue,
    onSend: handleSend,
    onStop: stopStreaming,
    onAttach: handleUploadClick,
    onModelClick: () => setShowModelPicker(true),
    isStreaming: inputBusy,
    disabled: !activeSessionId,
    attachedFileName,
    onRemoveAttachment: () => setAttachedFileName(null),
    modelName,
    enterToSend: settings.enterToSend,
  }

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-[var(--bg)]">
      <input
        ref={fileInputRef}
        type="file"
        accept=".txt,.md,.json,.csv,.log,.py,.ts,.tsx,.js,.jsx,.html,.css,text/*"
        className="hidden"
        onChange={handleFileChange}
      />

      <Sidebar
        workspaces={workspaces}
        activeWorkspaceId={activeWorkspaceId}
        sessions={visibleSessions.map((s) => ({
          id: s.id,
          title: s.title,
          updatedAt: s.updated_at,
          isActive: s.id === activeSessionId,
        }))}
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
        onSwitchWorkspace={switchWorkspace}
        onOpenFavorites={() => setShowFavorites(true)}
        onSwitchSession={switchSession}
        onNewSession={handleNewSession}
        onDeleteSession={async (id) => {
          if (isStreaming) return
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
              <div className="mb-[12vh] flex w-full max-w-[640px] flex-col items-stretch gap-3">
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
              onToggleFavorite={toggleFavorite}
              onRetry={retryLastFailed}
              onRetryToolStep={retryToolStep}
              setItemRef={setItemRef}
            />

            <div className="shrink-0 px-6 pb-4 pt-2">
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
              <ChatInput {...inputProps} variant="bottom" placeholder="Send follow-up" />
              <div className="mx-auto mt-2 flex max-w-3xl items-center">
                <ThisPcButton active={pcMode} onClick={handleThisPc} />
              </div>
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
        />

        <SearchPanel
          isOpen={showSearch}
          sessions={visibleSessions.map((s) => ({ id: s.id, title: s.title }))}
          pairs={pairs}
          onClose={() => setShowSearch(false)}
          onSelectSession={switchSession}
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
