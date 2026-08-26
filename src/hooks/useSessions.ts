import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createSession as createSessionApi,
  deleteSession as deleteSessionApi,
  listSessions,
  updateSessionTitle as updateSessionTitleApi,
  type Session as ApiSession,
} from '../api/agent'
import { normalizeRoot, projectIdFromRoot } from './useWorkspaces'

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
        await createSession('新对话')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载会话失败')
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

  const updateSessionTitle = useCallback((sessionId: string, title: string) => {
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId ? { ...session, title } : session,
      ),
    )
  }, [])

  const renameSession = useCallback(
    async (sessionId: string, title: string) => {
      const trimmed = title.trim()
      if (!trimmed) return
      await updateSessionTitleApi(sessionId, trimmed)
      updateSessionTitle(sessionId, trimmed)
    },
    [updateSessionTitle],
  )

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await deleteSessionApi(sessionId)
      } catch (err) {
        setError(err instanceof Error ? err.message : '删除会话失败')
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
        await createSession('新对话', pid, deletedRoot)
      }
    },
    [createSession, onRemoveWorkspace],
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
  }
}
