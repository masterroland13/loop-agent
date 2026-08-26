import { useCallback, useEffect, useMemo, useState } from 'react'

/** A real disk workspace shown as a Cursor-style project folder. */
export interface Project {
  id: string
  name: string
  /** Absolute filesystem root; null for the virtual "unbound" bucket. */
  root: string | null
}

export const UNBOUND_PROJECT_ID = '__unbound__'

const PROJECTS_KEY = 'agent-chat:projects'
const ACTIVE_PROJECT_KEY = 'agent-chat:active-project'
const SESSION_PROJECT_KEY = 'agent-chat:session-projects'
const SIDEBAR_COLLAPSED_KEY = 'agent-chat:sidebar-collapsed'
const SIDEBAR_WIDTH_KEY = 'agent-chat:sidebar-width'
/** One-shot: pull sessions stranded in 未绑定 after Workspaces rewrite back onto the disk root. */
const RECLAIM_UNBOUND_KEY = 'agent-chat:reclaim-unbound-v1'
/** Marks reclaim policy that never sweeps intentional __unbound__ sessions. */
const RECLAIM_POLICY_V2_KEY = 'agent-chat:reclaim-policy-v2'

/** Legacy keys from the fake 当前工作区/个人项目/团队协作 buckets. */
const LEGACY_WORKSPACES_KEY = 'agent-chat:workspaces'
const LEGACY_ACTIVE_KEY = 'agent-chat:active-workspace'
const LEGACY_SESSION_MAP_KEY = 'agent-chat:session-workspaces'

export function normalizeRoot(root: string): string {
  return root.replace(/\\/g, '/').replace(/\/+$/, '')
}

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

function basenameFromRoot(root: string): string {
  const parts = root.replace(/\\/g, '/').split('/').filter(Boolean)
  return parts[parts.length - 1] || root
}

/** Stable short id from an absolute path (browser-safe). */
export function projectIdFromRoot(root: string): string {
  const normalized = normalizeRoot(root)
  let hash = 0
  for (let i = 0; i < normalized.length; i++) {
    hash = (hash * 31 + normalized.charCodeAt(i)) >>> 0
  }
  return `proj_${hash.toString(16)}`
}

function makeUnbound(): Project {
  return { id: UNBOUND_PROJECT_ID, name: '未绑定工作区', root: null }
}

function loadProjects(): Project[] {
  try {
    const raw = localStorage.getItem(PROJECTS_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        const cleaned = parsed.filter(
          (p: unknown): p is Project =>
            !!p &&
            typeof p === 'object' &&
            typeof (p as Project).id === 'string' &&
            typeof (p as Project).name === 'string' &&
            ((p as Project).root === null || typeof (p as Project).root === 'string') &&
            (p as Project).id !== UNBOUND_PROJECT_ID,
        )
        return cleaned
      }
    }
  } catch {
    // ignore
  }
  return []
}

function loadSessionProjectMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(SESSION_PROJECT_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object') return parsed as Record<string, string>
    }
  } catch {
    // ignore
  }

  // One-shot migrate from legacy fake workspace buckets.
  // Prefer the sole saved disk project when present; otherwise unbound (reclaimed on boot).
  try {
    const legacy = localStorage.getItem(LEGACY_SESSION_MAP_KEY)
    if (!legacy) return {}
    const parsed = JSON.parse(legacy)
    if (!parsed || typeof parsed !== 'object') return {}
    const disk = loadProjects().filter((p) => p.root)
    const targetId = disk.length === 1 ? disk[0].id : UNBOUND_PROJECT_ID
    const next: Record<string, string> = {}
    for (const [sessionId] of Object.entries(parsed as Record<string, string>)) {
      next[sessionId] = targetId
    }
    localStorage.setItem(SESSION_PROJECT_KEY, JSON.stringify(next))
    localStorage.removeItem(LEGACY_SESSION_MAP_KEY)
    localStorage.removeItem(LEGACY_WORKSPACES_KEY)
    localStorage.removeItem(LEGACY_ACTIVE_KEY)
    if (targetId !== UNBOUND_PROJECT_ID) {
      localStorage.setItem(RECLAIM_UNBOUND_KEY, '1')
    }
    return next
  } catch {
    return {}
  }
}

export function useWorkspaces() {
  const [projects, setProjects] = useState<Project[]>(loadProjects)
  const [activeProjectId, setActiveProjectId] = useState(() => {
    return localStorage.getItem(ACTIVE_PROJECT_KEY) || UNBOUND_PROJECT_ID
  })
  const [sessionProjectMap, setSessionProjectMap] = useState<Record<string, string>>(loadSessionProjectMap)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true'
  })
  const [sidebarWidth, setSidebarWidthState] = useState(loadSidebarWidth)

  useEffect(() => {
    localStorage.setItem(ACTIVE_PROJECT_KEY, activeProjectId)
  }, [activeProjectId])

  useEffect(() => {
    localStorage.setItem(SESSION_PROJECT_KEY, JSON.stringify(sessionProjectMap))
  }, [sessionProjectMap])

  useEffect(() => {
    localStorage.setItem(PROJECTS_KEY, JSON.stringify(projects))
  }, [projects])

  useEffect(() => {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth))
  }, [sidebarWidth])

  const setSidebarWidth = useCallback((width: number) => {
    setSidebarWidthState(clampSidebarWidth(width))
  }, [])

  const upsertProjectFromRoot = useCallback((root: string, name?: string, activate = true) => {
    const normalized = normalizeRoot(root)
    const id = projectIdFromRoot(normalized)
    const display = (name || '').trim() || basenameFromRoot(normalized)
    setProjects((prev) => {
      const existing = prev.find(
        (p) => p.id === id || (p.root != null && normalizeRoot(p.root) === normalized),
      )
      if (existing) {
        return prev.map((p) =>
          p.id === existing.id ? { ...p, id, root: normalized, name: display || p.name } : p,
        )
      }
      return [...prev, { id, name: display, root: normalized }]
    })
    if (activate) setActiveProjectId(id)
    return id
  }, [])

  /**
   * After boot knows the server workspace root: attach stranded sessions to that project.
   * - Orphan map entries (proj_* no longer in sidebar) always remapped.
   * - `__unbound__` (and missing map entries) remapped once — Workspaces rewrite left everyone unbound.
   */
  /**
   * Remap orphan proj_* session map entries (project id no longer in sidebar) onto the
   * current disk project. Does NOT reclaim intentional `__unbound__` sessions.
   * Legacy unbound sweep was one-shot via RECLAIM_UNBOUND_KEY during Workspaces migration;
   * v2 policy keeps unbound as-is (no auto-undo — intent unknown after aggressive reclaim).
   */
  const reclaimOrphanSessionsToProject = useCallback((projectId: string) => {
    if (!projectId || projectId === UNBOUND_PROJECT_ID) return
    try {
      localStorage.setItem(RECLAIM_POLICY_V2_KEY, '1')
    } catch {
      // ignore
    }
    setSessionProjectMap((prev) => {
      const known = new Set(loadProjects().map((p) => p.id))
      known.add(projectId)
      let changed = false
      const next = { ...prev }
      for (const [sessionId, pid] of Object.entries(prev)) {
        const orphan = pid !== UNBOUND_PROJECT_ID && !known.has(pid)
        if (orphan) {
          next[sessionId] = projectId
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [])

  /** @deprecated alias — orphan remap only; does not sweep `__unbound__`. */
  const reclaimSessionsToProject = useCallback(
    (projectId: string, _sessionIds: string[] = []) => {
      reclaimOrphanSessionsToProject(projectId)
    },
    [reclaimOrphanSessionsToProject],
  )

  const switchProject = useCallback((id: string) => {
    setActiveProjectId(id)
  }, [])

  const assignSessionToProject = useCallback(
    (sessionId: string, projectId?: string) => {
      setSessionProjectMap((prev) => ({
        ...prev,
        [sessionId]: projectId ?? activeProjectId,
      }))
    },
    [activeProjectId],
  )

  /**
   * Server truth: sessions with workspace_root map onto projectIdFromRoot.
   * Null/empty workspace_root left unchanged (legacy / unbound mess).
   */
  const syncSessionsFromServer = useCallback(
    (sessions: { id: string; workspace_root?: string | null }[]) => {
      setSessionProjectMap((prev) => {
        let changed = false
        const next = { ...prev }
        for (const s of sessions) {
          const raw = (s.workspace_root ?? '').trim()
          if (!raw) continue
          const pid = projectIdFromRoot(normalizeRoot(raw))
          if (next[s.id] !== pid) {
            next[s.id] = pid
            changed = true
          }
        }
        return changed ? next : prev
      })
    },
    [],
  )

  const removeSessionFromProject = useCallback((sessionId: string) => {
    setSessionProjectMap((prev) => {
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

  const removeProjectFromSidebar = useCallback(
    (projectId: string) => {
      if (projectId === UNBOUND_PROJECT_ID) return
      setProjects((prev) => prev.filter((p) => p.id !== projectId))
      setSessionProjectMap((prev) => {
        const next = { ...prev }
        for (const [sessionId, pid] of Object.entries(next)) {
          if (pid === projectId) next[sessionId] = UNBOUND_PROJECT_ID
        }
        return next
      })
      if (activeProjectId === projectId) {
        setActiveProjectId(UNBOUND_PROJECT_ID)
      }
    },
    [activeProjectId],
  )

  const projectIdForSession = useCallback(
    (sessionId: string) => sessionProjectMap[sessionId] ?? UNBOUND_PROJECT_ID,
    [sessionProjectMap],
  )

  const sessionsForProject = useCallback(
    <T extends { id: string }>(sessions: T[], projectId: string): T[] => {
      return sessions.filter((s) => projectIdForSession(s.id) === projectId)
    },
    [projectIdForSession],
  )

  /** Real roots plus the always-present unbound bucket. */
  const visibleProjects = useMemo(() => [...projects, makeUnbound()], [projects])

  const activeProject = useMemo(() => {
    return (
      visibleProjects.find((p) => p.id === activeProjectId) ||
      projects.find((p) => p.id === activeProjectId) ||
      makeUnbound()
    )
  }, [visibleProjects, projects, activeProjectId])

  // Back-compat aliases so App.tsx renames can be gradual
  return {
    projects: visibleProjects,
    rawProjects: projects,
    activeProjectId,
    activeProject,
    sidebarCollapsed,
    sidebarWidth,
    sessionProjectMap,
    upsertProjectFromRoot,
    reclaimOrphanSessionsToProject,
    reclaimSessionsToProject,
    switchProject,
    assignSessionToProject,
    syncSessionsFromServer,
    removeSessionFromProject,
    toggleSidebarCollapsed,
    setSidebarWidth,
    removeProjectFromSidebar,
    sessionsForProject,
    projectIdForSession,
    // legacy names used by App during transition
    workspaces: visibleProjects.map((p) => ({ id: p.id, name: p.name })),
    activeWorkspaceId: activeProjectId,
    switchWorkspace: switchProject,
    assignSessionToWorkspace: assignSessionToProject,
    removeSessionFromWorkspace: removeSessionFromProject,
    filterSessionsByWorkspace: <T extends { id: string }>(sessions: T[]) =>
      sessionsForProject(sessions, activeProjectId),
  }
}

// Re-export old type name for Sidebar during rename
export type Workspace = Project
