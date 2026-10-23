import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  createSession as createSessionApi,
  deleteSession as deleteSessionApi,
  listSessions,
  updateSessionGoalMode as updateSessionGoalModeApi,
  updateSessionModel as updateSessionModelApi,
  updateSessionPinnedGoal as updateSessionPinnedGoalApi,
  updateSessionTitle as updateSessionTitleApi,
  updateSessionWorkspaceRoot as updateSessionWorkspaceRootApi,
  type Session as ApiSession,
} from '../api/agent'
import { translate, normalizeLocale } from '../i18n'
import { loadSettings } from './useSettings'
import { normalizeRoot, projectIdFromRoot } from './useWorkspaces'

function tErr(key: string) {
  return translate(normalizeLocale(loadSettings().language), key)
}

export function useApiSessions(
  onAssignWorkspace?: (sessionId: string, projectId?: string) => void,
  onRemoveWorkspace?: (sessionId: string) => void,
) {
  const [sessions, setSessions] = useState<ApiSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const hasAutoCreated = useRef(false)

  const createSession = useCallback(
    async (title: string, projectId?: string, workspaceRoot?: string | null) => {
      const root = (workspaceRoot ?? '').trim() || null
      let assignId = projectId
      if (!assignId && root) {
        assignId = projectIdFromRoot(normalizeRoot(root))
      }
      const session = await createSessionApi(title, root)
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
      onAssignWorkspace?.(session.id, assignId)
      return session
    },
    [onAssignWorkspace],
  )

  const load = useCallback(async () => {
    try {
      setError(null)
      const list = await listSessions()
      setSessions(list)
      if (list.length > 0) {
        setActiveSessionId((current) => current ?? list[0].id)
      } else if (!hasAutoCreated.current) {
        hasAutoCreated.current = true
        // No sessions yet: leave unbound (no active project root here).
        await createSession(tErr('appExtra.newChatTitle'))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : tErr('errors.loadSessionsFailed'))
      setSessions([])
    } finally {
      setIsLoading(false)
    }
  }, [createSession])

  useEffect(() => {
    load()
  }, [load])

  const switchSession = useCallback((id: string) => {
    setActiveSessionId(id)
  }, [])

  const updateSessionTitle = useCallback((sessionId: string, title: string, titleLocked?: boolean) => {
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId
          ? { ...session, title, ...(titleLocked ? { title_locked: true } : {}) }
          : session,
      ),
    )
  }, [])

  const goalMode = useMemo(() => {
    if (!activeSessionId) return false
    const active = sessions.find((s) => s.id === activeSessionId)
    return Boolean(active?.goal_mode)
  }, [sessions, activeSessionId])

  const pinnedGoal = useMemo(() => {
    if (!activeSessionId) return null
    const active = sessions.find((s) => s.id === activeSessionId)
    const raw = active?.pinned_goal
    return (raw ?? '').trim() || null
  }, [sessions, activeSessionId])

  const setGoalMode = useCallback(
    async (enabled: boolean) => {
      if (!activeSessionId) return
      const sessionId = activeSessionId
      let prev: boolean | undefined
      setSessions((list) => {
        prev = list.find((s) => s.id === sessionId)?.goal_mode
        return list.map((session) =>
          session.id === sessionId ? { ...session, goal_mode: enabled } : session,
        )
      })
      try {
        const updated = await updateSessionGoalModeApi(sessionId, enabled)
        setSessions((list) =>
          list.map((session) =>
            session.id === sessionId
              ? {
                  ...session,
                  goal_mode: Boolean(updated.goal_mode),
                  pinned_goal: updated.pinned_goal ?? session.pinned_goal,
                }
              : session,
          ),
        )
      } catch (err) {
        setSessions((list) =>
          list.map((session) =>
            session.id === sessionId ? { ...session, goal_mode: prev } : session,
          ),
        )
        setError(err instanceof Error ? err.message : tErr('errors.updateGoalModeFailed'))
        throw err
      }
    },
    [activeSessionId],
  )

  const setPinnedGoal = useCallback(
    async (goal: string | null) => {
      if (!activeSessionId) return
      const sessionId = activeSessionId
      const next = (goal ?? '').trim() || null
      let prev: string | null | undefined
      setSessions((list) => {
        const cur = list.find((s) => s.id === sessionId)?.pinned_goal
        prev = (cur ?? '').trim() || null
        return list.map((session) =>
          session.id === sessionId ? { ...session, pinned_goal: next } : session,
        )
      })
      try {
        const updated = await updateSessionPinnedGoalApi(sessionId, next)
        setSessions((list) =>
          list.map((session) =>
            session.id === sessionId
              ? {
                  ...session,
                  pinned_goal: (updated.pinned_goal ?? '').trim() || null,
                }
              : session,
          ),
        )
      } catch (err) {
        setSessions((list) =>
          list.map((session) =>
            session.id === sessionId ? { ...session, pinned_goal: prev ?? null } : session,
          ),
        )
        setError(err instanceof Error ? err.message : tErr('errors.updatePinnedGoalFailed'))
        throw err
      }
    },
    [activeSessionId],
  )

  const renameSession = useCallback(
    async (sessionId: string, title: string) => {
      const trimmed = title.trim()
      if (!trimmed) return
      await updateSessionTitleApi(sessionId, trimmed, true)
      updateSessionTitle(sessionId, trimmed, true)
    },
    [updateSessionTitle],
  )

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await deleteSessionApi(sessionId)
      } catch (err) {
        setError(err instanceof Error ? err.message : tErr('errors.deleteSessionFailed'))
        throw err
      }
      onRemoveWorkspace?.(sessionId)
      let shouldCreate = false
      let deletedRoot: string | null = null
      setSessions((prev) => {
        const deleted = prev.find((session) => session.id === sessionId)
        const raw = deleted?.workspace_root
        deletedRoot = (raw ?? '').trim() || null
        const next = prev.filter((session) => session.id !== sessionId)
        shouldCreate = next.length === 0
        setActiveSessionId((current) => {
          if (current !== sessionId) return current
          return next[0]?.id ?? null
        })
        return next
      })
      if (shouldCreate) {
        hasAutoCreated.current = true
        const pid = deletedRoot
          ? projectIdFromRoot(normalizeRoot(deletedRoot))
          : undefined
        await createSession(tErr('appExtra.newChatTitle'), pid, deletedRoot)
      }
    },
    [createSession, onRemoveWorkspace],
  )

  const notePrompt = useCallback((sessionId: string) => {
    const stamp = new Date().toISOString()
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId ? { ...session, last_prompt_at: stamp } : session,
      ),
    )
  }, [])

  const replaceSession = useCallback((session: ApiSession) => {
    setSessions((prev) => prev.map((s) => (s.id === session.id ? { ...s, ...session } : s)))
  }, [])

  const setSessionModel = useCallback(
    async (sessionId: string, patch: { model_id?: string | null; profile_id?: string | null }) => {
      const session = await updateSessionModelApi(sessionId, patch)
      replaceSession(session)
      return session
    },
    [replaceSession],
  )

  const bindSessionToWorkspace = useCallback(
    async (sessionId: string, workspaceRoot: string) => {
      const root = workspaceRoot.trim()
      if (!root) throw new Error('workspace root required')
      const session = await updateSessionWorkspaceRootApi(sessionId, root)
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, ...session } : s)),
      )
      onAssignWorkspace?.(sessionId, projectIdFromRoot(normalizeRoot(root)))
      return session
    },
    [onAssignWorkspace],
  )

  return {
    sessions,
    activeSessionId,
    isLoading,
    error,
    createSession,
    switchSession,
    refresh: load,
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
  }
}
