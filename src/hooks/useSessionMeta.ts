import { useCallback, useEffect, useState } from 'react'

const PINNED_KEY = 'agent-chat:pinned-sessions'
const LAST_READ_KEY = 'agent-chat:session-last-read'
const MANUAL_UNREAD_KEY = 'agent-chat:manual-unread'
const SEEN_KEY = 'agent-chat:session-seen'

function loadPinned(): Set<string> {
  try {
    const raw = localStorage.getItem(PINNED_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return new Set(parsed.filter((id) => typeof id === 'string'))
    }
  } catch {
    // ignore
  }
  return new Set()
}

function loadLastRead(): Record<string, string> {
  try {
    const raw = localStorage.getItem(LAST_READ_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object') return parsed as Record<string, string>
    }
  } catch {
    // ignore
  }
  return {}
}

function loadManualUnread(): Set<string> {
  try {
    const raw = localStorage.getItem(MANUAL_UNREAD_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return new Set(parsed.filter((id) => typeof id === 'string'))
    }
  } catch {
    // ignore
  }
  return new Set()
}

function loadSeen(): Set<string> {
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) return new Set(parsed.filter((id) => typeof id === 'string'))
    }
  } catch {
    // ignore
  }
  return new Set()
}

export function useSessionMeta() {
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(loadPinned)
  const [lastReadAt, setLastReadAt] = useState<Record<string, string>>(loadLastRead)
  const [manualUnreadIds, setManualUnreadIds] = useState<Set<string>>(loadManualUnread)
  const [seenIds, setSeenIds] = useState<Set<string>>(loadSeen)

  useEffect(() => {
    localStorage.setItem(PINNED_KEY, JSON.stringify([...pinnedIds]))
  }, [pinnedIds])

  useEffect(() => {
    localStorage.setItem(LAST_READ_KEY, JSON.stringify(lastReadAt))
  }, [lastReadAt])

  useEffect(() => {
    localStorage.setItem(MANUAL_UNREAD_KEY, JSON.stringify([...manualUnreadIds]))
  }, [manualUnreadIds])

  useEffect(() => {
    localStorage.setItem(SEEN_KEY, JSON.stringify([...seenIds]))
  }, [seenIds])

  const isPinned = useCallback((id: string) => pinnedIds.has(id), [pinnedIds])

  const togglePin = useCallback((id: string) => {
    setPinnedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const touchSeen = useCallback((id: string, updatedAt?: string) => {
    setSeenIds((prev) => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      return next
    })
    setLastReadAt((prev) => {
      if (id in prev) return prev
      const stamp = updatedAt || new Date().toISOString()
      return { ...prev, [id]: stamp }
    })
  }, [])

  const isUnread = useCallback(
    (id: string, updatedAt?: string): boolean => {
      if (!seenIds.has(id)) return false
      if (manualUnreadIds.has(id)) return true
      const readAt = lastReadAt[id]
      if (!readAt) return true
      if (updatedAt && readAt < updatedAt) return true
      return false
    },
    [seenIds, manualUnreadIds, lastReadAt],
  )

  const markRead = useCallback((id: string, updatedAt?: string) => {
    const stamp = updatedAt || new Date().toISOString()
    setLastReadAt((prev) => ({ ...prev, [id]: stamp }))
    setManualUnreadIds((prev) => {
      if (!prev.has(id)) return prev
      const next = new Set(prev)
      next.delete(id)
      return next
    })
    setSeenIds((prev) => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      return next
    })
  }, [])

  const markUnread = useCallback((id: string) => {
    setSeenIds((prev) => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      return next
    })
    setLastReadAt((prev) => {
      if (!(id in prev)) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
    setManualUnreadIds((prev) => {
      const next = new Set(prev)
      next.add(id)
      return next
    })
  }, [])

  const isManuallyUnread = useCallback(
    (id: string) => manualUnreadIds.has(id),
    [manualUnreadIds],
  )

  const sortSessions = useCallback(
    <T extends { id: string; updatedAt?: string }>(sessions: T[]): T[] => {
      const pinned: T[] = []
      const unpinned: T[] = []
      for (const s of sessions) {
        if (pinnedIds.has(s.id)) pinned.push(s)
        else unpinned.push(s)
      }
      const byUpdated = (a: T, b: T) => {
        const ta = a.updatedAt || ''
        const tb = b.updatedAt || ''
        return tb.localeCompare(ta)
      }
      pinned.sort(byUpdated)
      unpinned.sort(byUpdated)
      return [...pinned, ...unpinned]
    },
    [pinnedIds],
  )

  return {
    pinnedIds,
    isPinned,
    togglePin,
    isUnread,
    isManuallyUnread,
    markRead,
    markUnread,
    sortSessions,
    touchSeen,
  }
}
