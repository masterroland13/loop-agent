import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createSession as createSessionApi,
  deleteSession as deleteSessionApi,
  listSessions,
  updateSessionTitle as updateSessionTitleApi,
  type Session as ApiSession,
} from '../api/agent'

export function useApiSessions(
  onAssignWorkspace?: (sessionId: string) => void,
  onRemoveWorkspace?: (sessionId: string) => void,
) {
  const [sessions, setSessions] = useState<ApiSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const hasAutoCreated = useRef(false)

  const createSession = useCallback(
    async (title: string) => {
      const session = await createSessionApi(title)
      setSessions((prev) => [session, ...prev])
      setActiveSessionId(session.id)
      onAssignWorkspace?.(session.id)
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
      setSessions((prev) => {
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
        await createSession('新对话')
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
