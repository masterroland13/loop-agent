import { useCallback, useEffect, useState } from 'react'

export interface Workspace {
  id: string
  name: string
}

const WORKSPACES_KEY = 'agent-chat:workspaces'
const ACTIVE_WORKSPACE_KEY = 'agent-chat:active-workspace'
const SESSION_WORKSPACE_KEY = 'agent-chat:session-workspaces'
const SIDEBAR_COLLAPSED_KEY = 'agent-chat:sidebar-collapsed'
const SIDEBAR_WIDTH_KEY = 'agent-chat:sidebar-width'

export const SIDEBAR_WIDTH_DEFAULT = 260
export const SIDEBAR_WIDTH_MIN = 180
export const SIDEBAR_WIDTH_MAX = 480

function clampSidebarWidth(width: number) {
  return Math.min(SIDEBAR_WIDTH_MAX, Math.max(SIDEBAR_WIDTH_MIN, Math.round(width)))
}

function loadSidebarWidth() {
  try {
    const raw = localStorage.getItem(SIDEBAR_WIDTH_KEY)
    if (!raw) return SIDEBAR_WIDTH_DEFAULT
    const value = Number(raw)
    if (Number.isFinite(value)) return clampSidebarWidth(value)
  } catch {
    // ignore
  }
  return SIDEBAR_WIDTH_DEFAULT
}

const DEFAULT_WORKSPACES: Workspace[] = [
  { id: 'ws-1', name: '当前工作区' },
  { id: 'ws-2', name: '个人项目' },
  { id: 'ws-3', name: '团队协作' },
]

function loadWorkspaces(): Workspace[] {
  try {
    const raw = localStorage.getItem(WORKSPACES_KEY)
    if (!raw) return DEFAULT_WORKSPACES
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed) && parsed.length > 0) return parsed
  } catch {
    // ignore
  }
  return DEFAULT_WORKSPACES
}

function loadSessionWorkspaceMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(SESSION_WORKSPACE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') return parsed
  } catch {
    // ignore
  }
  return {}
}

export function useWorkspaces() {
  const [workspaces] = useState<Workspace[]>(loadWorkspaces)
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(() => {
    return localStorage.getItem(ACTIVE_WORKSPACE_KEY) || DEFAULT_WORKSPACES[0].id
  })
  const [sessionWorkspaceMap, setSessionWorkspaceMap] = useState<Record<string, string>>(
    loadSessionWorkspaceMap,
  )
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  })
  const [sidebarWidth, setSidebarWidthState] = useState(loadSidebarWidth)

  useEffect(() => {
    localStorage.setItem(ACTIVE_WORKSPACE_KEY, activeWorkspaceId)
  }, [activeWorkspaceId])

  useEffect(() => {
    localStorage.setItem(SESSION_WORKSPACE_KEY, JSON.stringify(sessionWorkspaceMap))
  }, [sessionWorkspaceMap])

  useEffect(() => {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth))
  }, [sidebarWidth])

  const setSidebarWidth = useCallback((width: number) => {
    setSidebarWidthState(clampSidebarWidth(width))
  }, [])

  const switchWorkspace = useCallback((id: string) => {
    setActiveWorkspaceId(id)
  }, [])

  const assignSessionToWorkspace = useCallback((sessionId: string, workspaceId?: string) => {
    setSessionWorkspaceMap((prev) => ({
      ...prev,
      [sessionId]: workspaceId ?? activeWorkspaceId,
    }))
  }, [activeWorkspaceId])

  const removeSessionFromWorkspace = useCallback((sessionId: string) => {
    setSessionWorkspaceMap((prev) => {
      const next = { ...prev }
      delete next[sessionId]
      return next
    })
  }, [])

  const toggleSidebarCollapsed = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next))
      return next
    })
  }, [])

  const filterSessionsByWorkspace = useCallback(
    <T extends { id: string }>(sessions: T[]): T[] => {
      return sessions.filter((session) => {
        const workspaceId = sessionWorkspaceMap[session.id] ?? DEFAULT_WORKSPACES[0].id
        return workspaceId === activeWorkspaceId
      })
    },
    [activeWorkspaceId, sessionWorkspaceMap],
  )

  return {
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
  }
}
