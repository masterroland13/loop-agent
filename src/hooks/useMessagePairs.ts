import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  applyMemory,
  applyPatch,
  applyPatchPartial,
  applyShell,
  cancelSession,
  getMessages,
  getSession,
  listMemoryProposals,
  listPatches,
  listShells,
  fetchRuntime,
  regenerateStream,
  rejectMemory,
  rejectPatch,
  rejectShell,
  retryPatch,
  retryShell,
  sendMessageStream,
  toggleMessageFavorite,
  updateSessionTitle as updateSessionTitleApi,
  type StreamEvent,
} from '../api/agent'
import type { MessagePair, PendingMemory, PendingPatch, PendingShell } from '../types'
import { buildMessagePairs, mergeStoppedFailedState } from '../utils/turnTrace'
import { pairWithActivityEvent, pickRicherActivity, type ActivityEvent } from '../utils/turnActivity'
import { applyOfflineStreamEvent } from '../utils/offlineStreamReduce'
import { translate, normalizeLocale } from '../i18n'
import { sessionTitleFromInstruction } from '../utils/sessionTitle'
import { useSettings } from './useSettings'

type LiveStream = {
  abort: () => void
  epoch: number
  pairs: MessagePair[]
  pendingPatches: PendingPatch[]
  pendingShells: PendingShell[]
  pendingMemories: PendingMemory[]
  awaitingApproval: boolean
  error: string | null
}

function sameTranscript(a: MessagePair[], b: MessagePair[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i].id !== b[i].id) return false
    if (a[i].user.content !== b[i].user.content) return false
    if ((a[i].assistant.content || '') !== (b[i].assistant.content || '')) return false
  }
  return true
}

type SessionTranscript = {
  pairs: MessagePair[]
  currentIndex: number
  pendingPatches: PendingPatch[]
  pendingShells: PendingShell[]
  pendingMemories: PendingMemory[]
  awaitingApproval: boolean
  error: string | null
  isStreaming: boolean
}

function applyActivityToLast(
  prev: MessagePair[],
  event: ActivityEvent,
  extra?: Partial<MessagePair>,
): MessagePair[] {
  const last = prev[prev.length - 1]
  if (!last) return prev
  const updated = [...prev]
  const act = pairWithActivityEvent(last, event)
  updated[prev.length - 1] = {
    ...last,
    ...extra,
    activityEvents: act.activityEvents,
    activity: act.activity,
    activityStartedAt: act.activityStartedAt,
  }
  return updated
}

/** Load messages + session leaf so regenerate siblings pair to the active tip. */
async function loadMessagePairs(sessionId: string): Promise<MessagePair[]> {
  const [messages, session] = await Promise.all([
    getMessages(sessionId),
    getSession(sessionId).catch(() => null),
  ])
  return buildMessagePairs(messages, session?.leaf_id)
}

export function useMessagePairs(
  sessionId: string | null,
  onUpdateSessionTitle?: (sessionId: string, title: string) => void,
  onFavoritesChanged?: () => void,
  modelName?: string,
  onModelFallback?: (
    modelId: string,
    profileId?: string | null,
    sessionId?: string,
  ) => void,
  titleLocked = false,
  onPromptSent?: (sessionId: string) => void,
) {
  const { settings } = useSettings(sessionId)
  const locale = normalizeLocale(settings.language)
  const t = useMemo(
    () => (key: string, vars?: Record<string, string | number>) => translate(locale, key, vars),
    [locale],
  )
  const [pairs, setPairs] = useState<MessagePair[]>([])
  /** True while cold-loading messages after session switch (avoids empty↔chat composer flip). */
  const [isPairsHydrating, setIsPairsHydrating] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isStreaming, setIsStreaming] = useState(false)
  const [awaitingApproval, setAwaitingApproval] = useState(false)
  const [pendingPatches, setPendingPatches] = useState<PendingPatch[]>([])
  const [pendingShells, setPendingShells] = useState<PendingShell[]>([])
  const [pendingMemories, setPendingMemories] = useState<PendingMemory[]>([])
  const [patchBusyId, setPatchBusyId] = useState<string | null>(null)
  const [shellBusyId, setShellBusyId] = useState<string | null>(null)
  const [memoryBusyId, setMemoryBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const itemRefs = useRef<(HTMLDivElement | null)[]>([])
  const listRef = useRef<HTMLDivElement | null>(null)
  /** Abort handle for the *active* session's SSE (also stored in liveStreamsRef). */
  const activeStream = useRef<(() => void) | null>(null)
  /** Per-session live SSE + reduced UI (Phase 2: survive session switch). */
  const liveStreamsRef = useRef(new Map<string, LiveStream>())
  const activeSessionIdRef = useRef<string | null>(sessionId)
  const pairsRef = useRef(pairs)
  const pendingPatchesRef = useRef(pendingPatches)
  const pendingShellsRef = useRef(pendingShells)
  const pendingMemoriesRef = useRef(pendingMemories)
  const awaitingApprovalRef = useRef(awaitingApproval)
  pairsRef.current = pairs
  pendingPatchesRef.current = pendingPatches
  pendingShellsRef.current = pendingShells
  pendingMemoriesRef.current = pendingMemories
  awaitingApprovalRef.current = awaitingApproval
  /** Session id that owns the live SSE shown in the Stop button. */
  const streamingSessionIdRef = useRef<string | null>(null)
  const hasUpdatedTitle = useRef(false)
  const navLockUntil = useRef(0)
  const navLockTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Per-session scrollTop so switching back restores where the user left off. */
  const scrollBySession = useRef<Record<string, number>>({})
  const prevSessionIdRef = useRef<string | null>(null)
  const viewCacheRef = useRef(new Map<string, SessionTranscript>())
  const warmingRef = useRef(new Set<string>())
  const hydratingRef = useRef(false)
  const titleLockedRef = useRef(titleLocked)
  const onPromptSentRef = useRef(onPromptSent)
  /** Scroll-spy must not walk the white pair border while a switch restores scroll. */
  const highlightLockUntil = useRef(0)
  /** Session whose list position was already restored this visit. */
  const positionedFor = useRef<string | null>(null)
  const [viewSessionId, setViewSessionId] = useState(sessionId)
  hydratingRef.current = isPairsHydrating
  titleLockedRef.current = titleLocked
  onPromptSentRef.current = onPromptSent

  const pinPairToTop = useCallback((index: number, behavior: ScrollBehavior = 'auto') => {
    const element = itemRefs.current[index]
    const container = listRef.current
    if (!element || !container) return

    navLockUntil.current = Date.now() + (behavior === 'smooth' ? 800 : 100)
    if (navLockTimer.current) clearTimeout(navLockTimer.current)
    navLockTimer.current = setTimeout(
      () => {
        navLockUntil.current = 0
      },
      behavior === 'smooth' ? 850 : 120,
    )

    const containerRect = container.getBoundingClientRect()
    const elementRect = element.getBoundingClientRect()
    const targetScrollTop = container.scrollTop + (elementRect.top - containerRect.top) - 12
    container.scrollTo({ top: Math.max(0, targetScrollTop), behavior })
  }, [])

  if (sessionId !== viewSessionId) {
    const leaving = listRef.current
    if (viewSessionId && leaving) {
      scrollBySession.current[viewSessionId] = leaving.scrollTop
    }
    if (viewSessionId) {
      const live = liveStreamsRef.current.get(viewSessionId)
      if (live) {
        live.pairs = pairsRef.current
        live.pendingPatches = pendingPatchesRef.current
        live.pendingShells = pendingShellsRef.current
        live.pendingMemories = pendingMemoriesRef.current
        live.awaitingApproval = awaitingApprovalRef.current
      }
      if (!hydratingRef.current) {
        viewCacheRef.current.set(viewSessionId, {
          pairs: pairsRef.current,
          currentIndex,
          pendingPatches: pendingPatchesRef.current,
          pendingShells: pendingShellsRef.current,
          pendingMemories: pendingMemoriesRef.current,
          awaitingApproval: awaitingApprovalRef.current,
          error,
          isStreaming:
            Boolean(live) || streamingSessionIdRef.current === viewSessionId,
        })
      }
    }
    setViewSessionId(sessionId)
    prevSessionIdRef.current = sessionId
    activeSessionIdRef.current = sessionId
    highlightLockUntil.current = Date.now() + 700
    positionedFor.current = null
    const liveNext = sessionId ? liveStreamsRef.current.get(sessionId) : undefined
    const cached = sessionId ? viewCacheRef.current.get(sessionId) : undefined
    if (!sessionId) {
      setIsPairsHydrating(false)
      setPairs([])
      setCurrentIndex(0)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])
      setAwaitingApproval(false)
      setError(null)
      setIsStreaming(false)
      hasUpdatedTitle.current = false
    } else if (liveNext) {
      const lastIdx = liveNext.pairs.length > 0 ? liveNext.pairs.length - 1 : 0
      const cachedIdx = viewCacheRef.current.get(sessionId)?.currentIndex
      setPairs(liveNext.pairs)
      setPendingPatches(liveNext.pendingPatches)
      setPendingShells(liveNext.pendingShells)
      setPendingMemories(liveNext.pendingMemories)
      setAwaitingApproval(liveNext.awaitingApproval)
      setError(liveNext.error)
      setIsStreaming(true)
      setIsPairsHydrating(false)
      setCurrentIndex(cachedIdx == null ? lastIdx : Math.max(0, Math.min(cachedIdx, lastIdx)))
      hasUpdatedTitle.current = liveNext.pairs.length > 0
      streamingSessionIdRef.current = sessionId
    } else if (cached) {
      setPairs(cached.pairs)
      setCurrentIndex(cached.currentIndex)
      setPendingPatches(cached.pendingPatches)
      setPendingShells(cached.pendingShells)
      setPendingMemories(cached.pendingMemories)
      setAwaitingApproval(cached.awaitingApproval)
      setError(cached.error)
      setIsStreaming(cached.isStreaming)
      setIsPairsHydrating(false)
      hasUpdatedTitle.current = cached.pairs.length > 0
      streamingSessionIdRef.current = cached.isStreaming ? sessionId : null
    } else {
      setIsPairsHydrating(true)
      setPairs([])
      setCurrentIndex(0)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])
      setAwaitingApproval(false)
      setError(null)
      setIsStreaming(false)
      hasUpdatedTitle.current = false
      streamingSessionIdRef.current = null
    }
  }

  useEffect(() => {
    // Save scroll of the session we're leaving before the list is cleared.
    const prev = prevSessionIdRef.current
    const container = listRef.current
    if (prev && prev !== sessionId && container) {
      scrollBySession.current[prev] = container.scrollTop
    }

    // Flush React UI into the live map for the session we're leaving (SSE stays up).
    if (prev) {
      const live = liveStreamsRef.current.get(prev)
      if (live) {
        live.pairs = pairsRef.current
        live.pendingPatches = pendingPatchesRef.current
        live.pendingShells = pendingShellsRef.current
        live.pendingMemories = pendingMemoriesRef.current
        live.awaitingApproval = awaitingApprovalRef.current
      }
    }

    prevSessionIdRef.current = sessionId
    activeSessionIdRef.current = sessionId

    const restoreListPosition = (id: string, lastIdx: number) => {
      if (positionedFor.current === id) return
      const el = listRef.current
      if (!el || el.clientHeight === 0) return
      highlightLockUntil.current = Date.now() + 400
      const saved = scrollBySession.current[id]
      if (typeof saved === 'number') {
        el.scrollTo({ top: saved, behavior: 'auto' })
      } else if (lastIdx > 0) {
        pinPairToTop(lastIdx, 'auto')
      }
      positionedFor.current = id
    }

    if (!sessionId) {
      setIsPairsHydrating(false)
      setPairs([])
      setCurrentIndex(0)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])
      setAwaitingApproval(false)
      setIsStreaming(false)
      hasUpdatedTitle.current = false
      return
    }

    const existing = liveStreamsRef.current.get(sessionId)
    if (existing) {
      setIsPairsHydrating(false)
      // Switch-back onto a live SSE: restore reduced UI, keep fetch open.
      setPairs(existing.pairs)
      setPendingPatches(existing.pendingPatches)
      setPendingShells(existing.pendingShells)
      setPendingMemories(existing.pendingMemories)
      setAwaitingApproval(existing.awaitingApproval)
      setError(existing.error)
      setIsStreaming(true)
      streamingSessionIdRef.current = sessionId
      activeStream.current = existing.abort
      hasUpdatedTitle.current = existing.pairs.length > 0
      const lastIdx = existing.pairs.length > 0 ? existing.pairs.length - 1 : 0
      window.setTimeout(() => restoreListPosition(sessionId, lastIdx), 0)
      return
    }

    activeStream.current = null
    const cachedNow = viewCacheRef.current.get(sessionId)
    if (cachedNow) {
      window.setTimeout(
        () => restoreListPosition(sessionId, cachedNow.currentIndex),
        0,
      )
    }

    // Cold session: visible state was already swapped before paint.
    // Refresh from the API without clearing a transcript we already have.
    let cancelled = false

    async function load() {
      try {
        const [messages, patches, shells, memories, session, runtime] = await Promise.all([
          getMessages(sessionId as string),
          listPatches(sessionId as string).catch(() => []),
          listShells(sessionId as string).catch(() => []),
          listMemoryProposals(sessionId as string).catch(() => []),
          getSession(sessionId as string).catch(() => null),
          fetchRuntime().catch(() => ({ active_sessions: [] as string[] })),
        ])
        if (cancelled || activeSessionIdRef.current !== sessionId) return
        // Another send may have registered a live stream while we were loading.
        if (liveStreamsRef.current.has(sessionId as string)) return

        const loaded = buildMessagePairs(messages, session?.leaf_id)
        const lastIdx = loaded.length > 0 ? loaded.length - 1 : 0
        if (!sameTranscript(pairsRef.current, loaded)) setPairs(loaded)
        if (positionedFor.current !== sessionId) {
          const cachedIdx = viewCacheRef.current.get(sessionId as string)?.currentIndex
          setCurrentIndex(
            cachedIdx == null ? lastIdx : Math.max(0, Math.min(cachedIdx, lastIdx)),
          )
        }
        hasUpdatedTitle.current = loaded.length > 0
        setPendingPatches(
          patches.map((p) => ({
            id: p.id,
            path: p.path,
            unified_diff: p.unified_diff,
            is_new_file: p.is_new_file,
            is_delete: Boolean(p.is_delete),
            status: p.status as PendingPatch['status'],
            error: p.error || undefined,
          })),
        )
        setPendingShells(
          shells.map((s) => ({
            id: s.id,
            argv: s.argv,
            cwd: s.cwd,
            command: s.command,
            status: s.status as PendingShell['status'],
            exit_code: s.exit_code,
            stdout: s.stdout,
            stderr: s.stderr,
            truncated: s.truncated,
            error: s.error || undefined,
          })),
        )
        setPendingMemories(
          memories.map((m) => ({
            id: m.id,
            mode: m.mode,
            preview: m.preview,
            content: m.content,
            target: m.target === 'memory' ? 'memory' : 'user',
            status: m.status as PendingMemory['status'],
            error: m.error || undefined,
            op_summary: m.op_summary || undefined,
          })),
        )
        setAwaitingApproval(
          patches.some((p) => p.status === 'pending')
            || shells.some((s) => s.status === 'pending')
            || memories.some((m) => m.status === 'pending'),
        )

        const stillRunning = Boolean(
          runtime.active_sessions?.includes(sessionId as string) ||
            loaded[loaded.length - 1]?.turnInProgress,
        )
        if (stillRunning) {
          setIsStreaming(true)
          streamingSessionIdRef.current = sessionId as string
        }

        window.setTimeout(() => {
          if (cancelled || activeSessionIdRef.current !== sessionId) return
          restoreListPosition(sessionId as string, lastIdx)
        }, 0)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : t('errors.loadMessagesFailed'))
        setPairs([])
        setCurrentIndex(0)
        hasUpdatedTitle.current = false
      } finally {
        if (!cancelled) setIsPairsHydrating(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // F6: recover in-progress turn after refresh while backend still runs.
  useEffect(() => {
    if (!sessionId || isStreaming) return

    let cancelled = false
    let timer: ReturnType<typeof setInterval> | undefined

    async function shouldPoll(): Promise<boolean> {
      try {
        const runtime = await fetchRuntime()
        if (runtime.active_sessions.includes(sessionId as string)) return true
      } catch {
        // ignore
      }
      const loaded = await loadMessagePairs(sessionId as string)
      const last = loaded[loaded.length - 1]
      return Boolean(last?.turnInProgress)
    }

    async function pollOnce() {
      if (cancelled) return false
      try {
        const [loaded, runtime] = await Promise.all([
          loadMessagePairs(sessionId as string),
          fetchRuntime().catch(() => ({ active_sessions: [] as string[] })),
        ])
        if (cancelled) return false
        setPairs(loaded)
        const active = runtime.active_sessions?.includes(sessionId as string)
        const last = loaded[loaded.length - 1]
        return Boolean(active || last?.turnInProgress)
      } catch {
        return false
      }
    }

    shouldPoll().then((needed) => {
      if (!needed || cancelled) return
      timer = window.setInterval(() => {
        pollOnce().then((continuePoll) => {
          if (!continuePoll && timer) {
            window.clearInterval(timer)
            timer = undefined
          }
        })
      }, 2000)
    })

    return () => {
      cancelled = true
      if (timer) window.clearInterval(timer)
    }
  }, [sessionId, isStreaming])

  // After switch-back (or refresh) onto a busy session without a live SSE handle:
  // poll messages until the turn ends, then clear isStreaming.
  useEffect(() => {
    if (!sessionId || !isStreaming) return

    let cancelled = false
    let timer: ReturnType<typeof setInterval> | undefined

    async function pollDetached() {
      if (cancelled) return
      // Live SSE owns updates when present (Phase 2 map or active abort handle).
      if (activeStream.current || liveStreamsRef.current.has(sessionId as string)) return
      try {
        const [loaded, runtime, patches, shells, memories] = await Promise.all([
          loadMessagePairs(sessionId as string),
          fetchRuntime().catch(() => ({ active_sessions: [] as string[] })),
          listPatches(sessionId as string).catch(() => []),
          listShells(sessionId as string).catch(() => []),
          listMemoryProposals(sessionId as string).catch(() => []),
        ])
        if (cancelled) return
        setPairs(loaded)
        setPendingPatches(
          patches.map((p) => ({
            id: p.id,
            path: p.path,
            unified_diff: p.unified_diff,
            is_new_file: p.is_new_file,
            is_delete: Boolean(p.is_delete),
            status: p.status as PendingPatch['status'],
            error: p.error || undefined,
          })),
        )
        setPendingShells(
          shells.map((s) => ({
            id: s.id,
            argv: s.argv,
            cwd: s.cwd,
            command: s.command,
            status: s.status as PendingShell['status'],
            exit_code: s.exit_code,
            stdout: s.stdout,
            stderr: s.stderr,
            truncated: s.truncated,
            error: s.error || undefined,
          })),
        )
        setPendingMemories(
          memories.map((m) => ({
            id: m.id,
            mode: m.mode,
            preview: m.preview,
            content: m.content,
            target: m.target === 'memory' ? 'memory' : 'user',
            status: m.status as PendingMemory['status'],
            error: m.error || undefined,
            op_summary: m.op_summary || undefined,
          })),
        )
        setAwaitingApproval(
          patches.some((p) => p.status === 'pending')
            || shells.some((s) => s.status === 'pending')
            || memories.some((m) => m.status === 'pending'),
        )
        const active = runtime.active_sessions?.includes(sessionId as string)
        const last = loaded[loaded.length - 1]
        if (!active && !last?.turnInProgress) {
          setIsStreaming(false)
          streamingSessionIdRef.current = null
          if (timer) {
            window.clearInterval(timer)
            timer = undefined
          }
        }
      } catch {
        // keep polling
      }
    }

    timer = window.setInterval(() => {
      void pollDetached()
    }, 2000)
    void pollDetached()

    return () => {
      cancelled = true
      if (timer) window.clearInterval(timer)
    }
  }, [sessionId, isStreaming])

  const findCurrentIndexFromScroll = useCallback(() => {
    const container = listRef.current
    if (!container) return currentIndex
    const containerTop = container.getBoundingClientRect().top + 24

    let bestIndex = 0
    let bestOffset = Number.POSITIVE_INFINITY

    itemRefs.current.forEach((element, index) => {
      if (!element) return
      const offset = Math.abs(element.getBoundingClientRect().top - containerTop)
      if (offset < bestOffset) {
        bestOffset = offset
        bestIndex = index
      }
    })

    return bestIndex
  }, [currentIndex])

  const scrollToIndex = useCallback((index: number) => {
    setCurrentIndex(index)
    pinPairToTop(index, 'smooth')
  }, [pinPairToTop])

  useEffect(() => {
    const container = listRef.current
    if (!container) return

    const handleScroll = () => {
      if (sessionId) {
        scrollBySession.current[sessionId] = container.scrollTop
      }
      if (Date.now() < navLockUntil.current || Date.now() < highlightLockUntil.current) return
      setCurrentIndex(findCurrentIndexFromScroll())
    }
    const releaseHighlightLock = () => {
      highlightLockUntil.current = 0
    }

    container.addEventListener('scroll', handleScroll, { passive: true })
    container.addEventListener('wheel', releaseHighlightLock, { passive: true })
    container.addEventListener('touchstart', releaseHighlightLock, { passive: true })
    return () => {
      container.removeEventListener('scroll', handleScroll)
      container.removeEventListener('wheel', releaseHighlightLock)
      container.removeEventListener('touchstart', releaseHighlightLock)
      if (navLockTimer.current) clearTimeout(navLockTimer.current)
    }
  }, [findCurrentIndexFromScroll, pairs.length, sessionId])

  const goPrevious = useCallback(() => {
    const fromIndex = Date.now() < navLockUntil.current ? currentIndex : findCurrentIndexFromScroll()
    const next = Math.max(0, fromIndex - 1)
    setCurrentIndex(next)
    scrollToIndex(next)
  }, [currentIndex, findCurrentIndexFromScroll, scrollToIndex])

  const goNext = useCallback(() => {
    const fromIndex = Date.now() < navLockUntil.current ? currentIndex : findCurrentIndexFromScroll()
    const next = Math.min(pairs.length - 1, fromIndex + 1)
    setCurrentIndex(next)
    scrollToIndex(next)
  }, [currentIndex, findCurrentIndexFromScroll, pairs.length, scrollToIndex])

  const goToIndex = useCallback(
    (index: number) => {
      const safeIndex = Math.max(0, Math.min(pairs.length - 1, index))
      setCurrentIndex(safeIndex)
      scrollToIndex(safeIndex)
    },
    [pairs.length, scrollToIndex],
  )

  const setFavorite = useCallback((id: string, isFavorite: boolean) => {
    setPairs((prev) =>
      prev.map((item) => (item.id === id ? { ...item, isFavorite } : item)),
    )
  }, [])

  const toggleFavorite = useCallback(
    async (id: string) => {
      const pair = pairs.find((item) => item.id === id)
      if (!pair) return
      const nextFavorite = !pair.isFavorite

      setPairs((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, isFavorite: nextFavorite } : item,
        ),
      )

      try {
        await toggleMessageFavorite(id, nextFavorite)
        onFavoritesChanged?.()
      } catch {
        setPairs((prev) =>
          prev.map((item) =>
            item.id === id ? { ...item, isFavorite: !nextFavorite } : item,
          ),
        )
      }
    },
    [pairs, onFavoritesChanged],
  )

  const setItemRef = useCallback((index: number) => {
    return (element: HTMLDivElement | null) => {
      itemRefs.current[index] = element
    }
  }, [])

  const stopStreaming = useCallback(() => {
    const targetSession = sessionId
    if (!targetSession) return
    // Cancel backend waiters first; aborting SSE alone often drops the TURN_CANCELLED event.
    void cancelSession(targetSession)
    const live = liveStreamsRef.current.get(targetSession)
    if (live) {
      live.epoch += 1
      live.abort()
      liveStreamsRef.current.delete(targetSession)
    }
    if (activeStream.current) {
      activeStream.current = null
    }
    streamingSessionIdRef.current = null
    setPendingPatches((prev) =>
      prev.map((p) =>
        p.status === 'pending' ? { ...p, status: 'cancelled' as const, error: t('message.stopped') } : p,
      ),
    )
    setPendingShells((prev) =>
      prev.map((s) =>
        s.status === 'pending' || s.status === 'running'
          ? { ...s, status: 'cancelled' as const, error: t('message.stopped') }
          : s,
      ),
    )
    setPendingMemories((prev) =>
      prev.map((m) =>
        m.status === 'pending' ? { ...m, status: 'cancelled' as const, error: t('message.stopped') } : m,
      ),
    )
    setPairs((prev) => {
      const last = prev[prev.length - 1]
      if (!last) return prev
      const trace = (last.toolTrace || []).map((item) =>
        item.status === 'running'
          ? { ...item, status: 'error' as const, detail: t('message.stopped') }
          : item,
      )
      const updated = [...prev]
      updated[prev.length - 1] = {
        ...last,
        failed: true,
        turnInProgress: false,
        toolTrace: trace.length > 0 ? trace : last.toolTrace,
        assistant: {
          ...last.assistant,
          content: last.assistant.content || t('message.stopped'),
        },
      }
      return updated
    })
    setError(t('message.stopped'))
    setIsStreaming(false)
    setAwaitingApproval(false)

    window.setTimeout(async () => {
      try {
        const loaded = await loadMessagePairs(targetSession)
        if (activeSessionIdRef.current !== targetSession) return
        setPairs((prev) => mergeStoppedFailedState(prev, loaded))
      } catch {
        // keep local stopped state
      }
    }, 500)
  }, [sessionId, t])

  const upsertPatch = useCallback((patch: PendingPatch) => {
    setPendingPatches((prev) => {
      const idx = prev.findIndex((p) => p.id === patch.id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], ...patch }
        return next
      }
      return [...prev, patch]
    })
  }, [])

  const upsertShell = useCallback((shell: PendingShell) => {
    setPendingShells((prev) => {
      const idx = prev.findIndex((p) => p.id === shell.id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], ...shell }
        return next
      }
      return [...prev, shell]
    })
  }, [])

  const upsertMemory = useCallback((memory: PendingMemory) => {
    setPendingMemories((prev) => {
      const idx = prev.findIndex((p) => p.id === memory.id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = { ...next[idx], ...memory }
        return next
      }
      return [...prev, memory]
    })
  }, [])

  const handleApplyPatch = useCallback(
    async (id: string) => {
      setPatchBusyId(id)
      try {
        const result = await applyPatch(id)
        upsertPatch({
          id: result.id,
          path: result.path,
          unified_diff: result.unified_diff,
          is_new_file: result.is_new_file,
          is_delete: Boolean(result.is_delete),
          status: result.status as PendingPatch['status'],
          error: result.error || undefined,
          hunk_count: result.hunk_count ?? undefined,
          applied_hunks: result.applied_hunks ?? undefined,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'diff',
            patch_id: result.id,
            path: result.path,
            unified_diff: result.unified_diff,
            status: result.status,
            is_new_file: result.is_new_file,
            is_delete: Boolean(result.is_delete),
            error: result.error,
          }),
        )
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.applyFailed'))
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch, t],
  )

  const handleApplyPartial = useCallback(
    async (id: string, hunkIds: number[]) => {
      setPatchBusyId(id)
      try {
        const result = await applyPatchPartial(id, hunkIds)
        upsertPatch({
          id: result.id,
          path: result.path,
          unified_diff: result.unified_diff,
          is_new_file: result.is_new_file,
          is_delete: Boolean(result.is_delete),
          status: result.status as PendingPatch['status'],
          error: result.error || undefined,
          hunk_count: result.hunk_count ?? undefined,
          applied_hunks: result.applied_hunks ?? undefined,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'diff',
            patch_id: result.id,
            path: result.path,
            unified_diff: result.unified_diff,
            status: result.status,
            is_new_file: result.is_new_file,
            is_delete: Boolean(result.is_delete),
            error: result.error,
          }),
        )
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.partialApplyFailed'))
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch, t],
  )

  const handleRejectPatch = useCallback(
    async (id: string) => {
      setPatchBusyId(id)
      try {
        const result = await rejectPatch(id)
        upsertPatch({
          id: result.id,
          path: result.path,
          unified_diff: result.unified_diff,
          is_new_file: result.is_new_file,
          is_delete: Boolean(result.is_delete),
          status: result.status as PendingPatch['status'],
          error: result.error || undefined,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'diff',
            patch_id: result.id,
            path: result.path,
            unified_diff: result.unified_diff,
            status: result.status,
            is_new_file: result.is_new_file,
            is_delete: Boolean(result.is_delete),
            error: result.error,
          }),
        )
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.rejectFailed'))
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch, t],
  )

  const handleRetryPatch = useCallback(
    async (id: string) => {
      setPatchBusyId(id)
      try {
        const result = await retryPatch(id)
        upsertPatch({
          id: result.id,
          path: result.path,
          unified_diff: result.unified_diff,
          is_new_file: result.is_new_file,
          is_delete: Boolean(result.is_delete),
          status: result.status as PendingPatch['status'],
          error: result.error || undefined,
        })
        if (result.status === 'applied') {
          setAwaitingApproval(false)
        }
        if (result.status === 'pending') {
          setAwaitingApproval(true)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.retryFailed'))
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch, t],
  )

  const handleApplyShell = useCallback(
    async (id: string) => {
      setShellBusyId(id)
      try {
        const result = await applyShell(id)
        upsertShell({
          id: result.id,
          argv: result.argv,
          cwd: result.cwd,
          command: result.command,
          status: result.status as PendingShell['status'],
          exit_code: result.exit_code,
          stdout: result.stdout,
          stderr: result.stderr,
          truncated: result.truncated,
          error: result.error || undefined,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'shell',
            shell_id: result.id,
            command: result.command,
            argv: result.argv,
            status: result.status,
            exit_code: result.exit_code,
            error: result.error,
          }),
        )
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.runFailed'))
      } finally {
        setShellBusyId(null)
      }
    },
    [upsertShell, t],
  )

  const handleRejectShell = useCallback(
    async (id: string) => {
      setShellBusyId(id)
      try {
        const result = await rejectShell(id)
        upsertShell({
          id: result.id,
          argv: result.argv,
          cwd: result.cwd,
          command: result.command,
          status: result.status as PendingShell['status'],
          exit_code: result.exit_code,
          stdout: result.stdout,
          stderr: result.stderr,
          truncated: result.truncated,
          error: result.error || undefined,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'shell',
            shell_id: result.id,
            command: result.command,
            argv: result.argv,
            status: result.status,
            exit_code: result.exit_code,
            error: result.error,
          }),
        )
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.rejectFailed'))
      } finally {
        setShellBusyId(null)
      }
    },
    [upsertShell, t],
  )

  const handleRetryShell = useCallback(
    async (id: string) => {
      setShellBusyId(id)
      try {
        const result = await retryShell(id)
        upsertShell({
          id: result.id,
          argv: result.argv,
          cwd: result.cwd,
          command: result.command,
          status: result.status as PendingShell['status'],
          exit_code: result.exit_code,
          stdout: result.stdout,
          stderr: result.stderr,
          truncated: result.truncated,
          error: result.error || undefined,
        })
        if (result.status === 'done') {
          setAwaitingApproval(false)
        }
        if (result.status === 'pending') {
          setAwaitingApproval(true)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.retryFailed'))
      } finally {
        setShellBusyId(null)
      }
    },
    [upsertShell, t],
  )

  const handleApplyMemory = useCallback(
    async (id: string) => {
      setMemoryBusyId(id)
      try {
        const result = await applyMemory(id)
        upsertMemory({
          id: result.id,
          mode: result.mode,
          preview: result.preview,
          content: result.content,
          target: result.target === 'memory' ? 'memory' : 'user',
          status: result.status as PendingMemory['status'],
          error: result.error || undefined,
          op_summary: result.op_summary || undefined,
        })
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.applyMemoryFailed'))
      } finally {
        setMemoryBusyId(null)
      }
    },
    [upsertMemory, t],
  )

  const handleRejectMemory = useCallback(
    async (id: string) => {
      setMemoryBusyId(id)
      try {
        const result = await rejectMemory(id)
        upsertMemory({
          id: result.id,
          mode: result.mode,
          preview: result.preview,
          content: result.content,
          target: result.target === 'memory' ? 'memory' : 'user',
          status: result.status as PendingMemory['status'],
          error: result.error || undefined,
          op_summary: result.op_summary || undefined,
        })
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : t('errors.rejectMemoryFailed'))
      } finally {
        setMemoryBusyId(null)
      }
    },
    [upsertMemory, t],
  )

  const handleStreamEvent = useCallback(
    (event: StreamEvent) => {
      if (event.type === 'meta' && event.message_id) {
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
          updated[prev.length - 1] = {
            ...last,
            id: event.message_id as string,
            user: { ...last.user, id: event.message_id as string },
            // Only set goal when Goal mode sent one; do not inherit prior pair's goal.
            goal:
              typeof event.goal === 'string' && event.goal.trim()
                ? event.goal.trim()
                : undefined,
            turnInProgress: true,
            assistant: event.assistant_message_id
              ? { ...last.assistant, id: event.assistant_message_id as string }
              : last.assistant,
          }
          return updated
        })
      } else if (event.type === 'turn_goal' && event.goal) {
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
          const prevGoal =
            typeof event.previous_goal === 'string' && event.previous_goal.trim()
              ? event.previous_goal.trim()
              : undefined
          updated[prev.length - 1] = {
            ...last,
            goal: event.goal,
            ...(prevGoal ? { previousGoal: prevGoal } : {}),
          }
          return updated
        })
      } else if (event.type === 'progress_checkpoint') {
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
          const prevCp = last.progressCheckpoint
          const replyText =
            typeof event.reply === 'string' && event.reply.trim() ? event.reply.trim() : ''
          const isOpening = !event.settled && !replyText
          let nextCp: NonNullable<typeof prevCp>
          if (isOpening) {
            nextCp = {
              toolsSinceLast: event.tools_since_last ?? 0,
              reason: event.reason || 'interval',
            }
          } else if (replyText) {
            nextCp = {
              toolsSinceLast: event.tools_since_last ?? prevCp?.toolsSinceLast ?? 0,
              reason: event.reason || prevCp?.reason || 'interval',
              reply: replyText,
              settled: true,
            }
          } else {
            nextCp = {
              toolsSinceLast: event.tools_since_last ?? prevCp?.toolsSinceLast ?? 0,
              reason: event.reason || prevCp?.reason || 'interval',
              settled: true,
              ...(prevCp?.reply ? { reply: prevCp.reply } : {}),
            }
          }
          updated[prev.length - 1] = {
            ...last,
            goal:
              typeof event.goal === 'string' && event.goal.trim()
                ? event.goal.trim()
                : last.goal,
            progressCheckpoint: nextCp,
          }
          return updated
        })
      } else if (event.type === 'tool_start' && event.name) {
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
          const trace = [...(last.toolTrace || [])]
          trace.push({
            name: event.name as string,
            status: 'running',
            detail: typeof event.arguments === 'string' ? event.arguments : undefined,
          })
          const act = pairWithActivityEvent(last, {
            type: 'tool_start',
            name: event.name,
            arguments: event.arguments,
            tool_call_id: event.tool_call_id,
          })
          updated[prev.length - 1] = {
            ...last,
            failed: false,
            toolTrace: trace,
            activityEvents: act.activityEvents,
            activity: act.activity,
            activityStartedAt: act.activityStartedAt,
          }
          return updated
        })
      } else if (event.type === 'tool_result' && event.name) {
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
          const trace = [...(last.toolTrace || [])]
          const idx = [...trace].reverse().findIndex(
            (t) => t.name === event.name && t.status === 'running',
          )
          const snippet = (event.content || '').slice(0, 400)
          const fullRef = typeof event.full_ref === 'string' ? event.full_ref : undefined
          const truncated = Boolean(event.truncated)
          const detail =
            truncated || Boolean(fullRef?.startsWith('file:'))
              ? event.summary || snippet
              : snippet
          let isError = false
          try {
            const parsed = JSON.parse(event.content || '') as { error?: unknown; status?: string }
            isError = Boolean(parsed.error) || parsed.status === 'failed' || parsed.status === 'timeout'
          } catch {
            isError = false
          }
          const item = {
            name: event.name as string,
            status: (isError ? 'error' : 'done') as 'error' | 'done',
            detail,
            fullRef,
            truncated,
          }
          if (idx >= 0) {
            const realIdx = trace.length - 1 - idx
            trace[realIdx] = {
              ...trace[realIdx],
              ...item,
            }
          } else {
            trace.push(item)
          }
          const act = pairWithActivityEvent(last, {
            type: 'tool_result',
            name: event.name,
            status: item.status,
            content: event.content,
            summary: event.summary,
            tool_call_id: event.tool_call_id,
            full_ref: fullRef,
          })
          updated[prev.length - 1] = {
            ...last,
            toolTrace: trace,
            activityEvents: act.activityEvents,
            activity: act.activity,
            activityStartedAt: act.activityStartedAt,
          }
          return updated
        })
      } else if (event.type === 'diff' && event.patch_id && event.path) {
        upsertPatch({
          id: event.patch_id,
          path: event.path,
          unified_diff: event.unified_diff || '',
          is_new_file: Boolean(event.is_new_file),
          is_delete: Boolean(event.is_delete),
          status: (event.status as PendingPatch['status']) || 'pending',
          error: event.error,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'diff',
            patch_id: event.patch_id,
            path: event.path,
            unified_diff: event.unified_diff,
            status: event.status || 'pending',
            is_new_file: event.is_new_file,
            is_delete: event.is_delete,
          }),
        )
        // Approval wait is signaled by await_approval (Trusted/Strict). YOLO skips pending.
        if (event.status && event.status !== 'pending') {
          setAwaitingApproval(false)
        }
      } else if (event.type === 'shell' && event.shell_id) {
        upsertShell({
          id: event.shell_id,
          argv: event.argv || [],
          cwd: event.cwd || '.',
          command: event.command || (event.argv || []).join(' '),
          status: (event.status as PendingShell['status']) || 'pending',
          exit_code: event.exit_code,
          stdout: event.stdout,
          stderr: event.stderr,
          truncated: event.truncated,
          error: event.error,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'shell',
            shell_id: event.shell_id,
            command: event.command || (event.argv || []).join(' '),
            argv: event.argv,
            status: event.status || 'pending',
            exit_code: event.exit_code,
          }),
        )
        if (event.status && event.status !== 'pending' && event.status !== 'running') {
          setAwaitingApproval(false)
        }
      } else if (event.type === 'memory' && event.memory_id) {
        upsertMemory({
          id: event.memory_id,
          mode: event.mode || 'replace',
          target: event.target === 'memory' ? 'memory' : 'user',
          preview: event.preview || event.content || '',
          content: event.content || event.preview || '',
          status: (event.status as PendingMemory['status']) || 'pending',
          error: event.error,
          op_summary: typeof event.op_summary === 'string' ? event.op_summary : undefined,
        })
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'memory',
            status: event.status || 'pending',
            target: event.target === 'memory' ? 'memory' : 'user',
          }),
        )
        if (event.status && event.status !== 'pending') {
          setAwaitingApproval(false)
        }
      } else if (event.type === 'turn_meta') {
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
          const liveGoal =
            typeof event.goal === 'string' && event.goal.trim()
              ? event.goal.trim()
              : undefined
          updated[prev.length - 1] = {
            ...last,
            turnMeta: {
              model: event.model || '',
              elapsed_ms: event.elapsed_ms || 0,
              approx_prompt_tokens: event.approx_prompt_tokens || 0,
              approx_completion_tokens: event.approx_completion_tokens || 0,
              compressed: Boolean(event.compressed),
              memory_injected: Boolean(event.memory_injected),
              message_id: event.message_id || '',
              ...(liveGoal ? { goal: liveGoal } : {}),
            },
            goal: liveGoal,
            assistant: event.message_id
              ? { ...last.assistant, id: event.message_id }
              : last.assistant,
          }
          return updated
        })
      } else if (event.type === 'await_approval') {
        setAwaitingApproval(true)
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last?.toolTrace?.length) return prev
          const updated = [...prev]
          const trace = [...last.toolTrace]
          const idx = [...trace].reverse().findIndex((t) => t.status === 'running')
          if (idx >= 0) {
            const realIdx = trace.length - 1 - idx
            trace[realIdx] = {
              ...trace[realIdx],
              status: 'running',
              detail: t('message.waitingApproval'),
            }
          }
          updated[prev.length - 1] = { ...last, toolTrace: trace }
          return updated
        })
      } else if (event.type === 'soft_land') {
        setPairs((prev) =>
          applyActivityToLast(
            prev,
            { type: 'soft_land', reason: event.reason },
            { softLanded: true },
          ),
        )
      } else if (event.type === 'edit_nudge') {
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'edit_nudge',
            reason: event.reason || 'missing_propose_edit',
          }),
        )
      } else if (event.type === 'thought') {
        setPairs((prev) =>
          applyActivityToLast(prev, {
            type: 'thought',
            phase: event.phase || 'end',
            text: event.text || event.content || '',
            duration_ms: event.duration_ms,
            source: event.source,
          }),
        )
      } else if (event.type === 'tools_disabled') {
        setError(event.message || t('errors.toolsDisabled'))
      } else if (event.type === 'stream_end') {
        // SSE closed without done/error (proxy drop / abort). Keep approval UI if needed.
        streamingSessionIdRef.current = null
        setIsStreaming(false)
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last?.toolTrace?.some((t) => t.status === 'running')) return prev
          // leave running markers if still awaiting; otherwise mark stopped
          return prev
        })
      } else if (event.type === 'token' && event.content) {
        setError(null)
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
          updated[prev.length - 1] = {
            ...last,
            failed: false,
            assistant: {
              ...last.assistant,
              content: last.assistant.content + event.content,
            },
          }
          return updated
        })
      } else if (event.type === 'done') {
        setError(null)
        streamingSessionIdRef.current = null
        setIsStreaming(false)
        setAwaitingApproval(false)
        activeStream.current = null
        if (event.message_id) {
          setPairs((prev) => {
            const last = prev[prev.length - 1]
            if (!last) return prev
            const updated = [...prev]
            updated[prev.length - 1] = {
              ...last,
              failed: false,
              turnInProgress: false,
              assistant: { ...last.assistant, id: event.message_id as string },
            }
            return updated
          })
        }
        if (sessionId) {
          window.setTimeout(async () => {
            try {
              const loaded = await loadMessagePairs(sessionId)
              setPairs((prev) => {
                const lastPrev = prev[prev.length - 1]
                const lastLoaded = loaded[loaded.length - 1]
                if (!lastPrev || !lastLoaded) return loaded.length ? loaded : prev
                const merged = [...loaded]
                const richer = pickRicherActivity(lastPrev.activity, lastLoaded.activity)
                merged[merged.length - 1] = {
                  ...lastLoaded,
                  failed: false,
                  turnInProgress: false,
                  assistant: {
                    ...lastLoaded.assistant,
                    content: lastLoaded.assistant.content || lastPrev.assistant.content,
                    id: lastLoaded.assistant.id || lastPrev.assistant.id,
                  },
                  toolTrace:
                    lastLoaded.toolTrace && lastLoaded.toolTrace.length > 0
                      ? lastLoaded.toolTrace
                      : lastPrev.toolTrace,
                  goal: lastLoaded.goal ?? lastPrev.goal,
                  previousGoal: lastLoaded.previousGoal ?? lastPrev.previousGoal,
                  progressCheckpoint: lastLoaded.progressCheckpoint ?? lastPrev.progressCheckpoint,
                  turnMeta: lastLoaded.turnMeta ?? lastPrev.turnMeta,
                  activity: richer,
                  activityEvents:
                    richer === lastPrev.activity
                      ? lastPrev.activityEvents || lastLoaded.activityEvents
                      : lastLoaded.activityEvents || lastPrev.activityEvents,
                  activityStartedAt:
                    lastLoaded.activityStartedAt ?? lastPrev.activityStartedAt,
                }
                return merged
              })
            } catch {
              // keep local state
            }
          }, 500)
        }
        setCurrentIndex((prev) => Math.max(prev, pairs.length))
        // Keep the turn pinned near the top (Cursor-style); do not slide to absolute bottom.
      } else if (event.type === 'error') {
        streamingSessionIdRef.current = null
        setIsStreaming(false)
        setAwaitingApproval(false)
        activeStream.current = null
        const cancelled = event.code === 'TURN_CANCELLED'
        const errorMessage =
          event.message || (cancelled ? t('message.stopped') : t('errors.requestFailed'))
        setError(errorMessage)
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const trace = (last.toolTrace || []).map((item) =>
            item.status === 'running'
              ? {
                  ...item,
                  status: 'error' as const,
                  detail: cancelled ? t('message.stopped') : item.detail,
                }
              : item,
          )
          const updated = [...prev]
          updated[prev.length - 1] = {
            ...last,
            failed: true,
            turnInProgress: false,
            toolTrace: trace.length > 0 ? trace : last.toolTrace,
            assistant: {
              ...last.assistant,
              content: last.assistant.content || errorMessage,
            },
          }
          return updated
        })
        if (sessionId) {
          window.setTimeout(async () => {
            try {
              const loaded = await loadMessagePairs(sessionId)
              setPairs((prev) => mergeStoppedFailedState(prev, loaded))
            } catch {
              // keep local state
            }
          }, 500)
        }
      }
    },
    [pairs.length, sessionId, upsertPatch, upsertShell, upsertMemory, t],
  )

  const handleStreamError = useCallback((streamError: Error) => {
    streamingSessionIdRef.current = null
    setIsStreaming(false)
    setAwaitingApproval(false)
    activeStream.current = null
    setError(streamError.message)
    setPairs((prev) => {
      const last = prev[prev.length - 1]
      if (!last) return prev
      const updated = [...prev]
      updated[prev.length - 1] = {
        ...last,
        failed: true,
        assistant: {
          ...last.assistant,
          content: last.assistant.content || t('errors.requestFailed'),
        },
      }
      return updated
    })
  }, [t])

  const wrapStreamHandlers = useCallback(
    (ownerSessionId: string, epoch: number) => ({
      onEvent: (event: StreamEvent) => {
        const live = liveStreamsRef.current.get(ownerSessionId)
        if (!live || live.epoch !== epoch) return
        if (event.type === 'meta' && event.model_fallback && event.model) {
          onModelFallback?.(event.model, event.profile_id, ownerSessionId)
        }

        if (activeSessionIdRef.current === ownerSessionId) {
          handleStreamEvent(event)
          queueMicrotask(() => {
            const cur = liveStreamsRef.current.get(ownerSessionId)
            if (!cur || cur.epoch !== epoch) return
            cur.pairs = pairsRef.current
            cur.pendingPatches = pendingPatchesRef.current
            cur.pendingShells = pendingShellsRef.current
            cur.pendingMemories = pendingMemoriesRef.current
            cur.awaitingApproval = awaitingApprovalRef.current
            if (
              event.type === 'done' ||
              event.type === 'error' ||
              event.type === 'stream_end'
            ) {
              liveStreamsRef.current.delete(ownerSessionId)
              if (activeStream.current === cur.abort) activeStream.current = null
            }
          })
          return
        }

        // Background session: reduce into the map only (no React updates for the wrong chat).
        const ended = applyOfflineStreamEvent(live, event)
        if (ended) {
          liveStreamsRef.current.delete(ownerSessionId)
        }
      },
      onError: (streamError: Error) => {
        const live = liveStreamsRef.current.get(ownerSessionId)
        if (!live || live.epoch !== epoch) return
        if (activeSessionIdRef.current === ownerSessionId) {
          handleStreamError(streamError)
          liveStreamsRef.current.delete(ownerSessionId)
          if (activeStream.current === live.abort) activeStream.current = null
          return
        }
        applyOfflineStreamEvent(live, {
          type: 'error',
          message: streamError.message,
        })
        liveStreamsRef.current.delete(ownerSessionId)
      },
    }),
    [handleStreamEvent, handleStreamError, onModelFallback],
  )

  const sendMessage = useCallback(
    (content: string, attachmentIds?: string[], attachmentMetas?: import('../types').AttachmentMeta[]) => {
      if (!sessionId || isStreaming) return

      const prevLive = liveStreamsRef.current.get(sessionId)
      const epoch = (prevLive?.epoch ?? 0) + 1
      if (prevLive) {
        prevLive.epoch = epoch
        prevLive.abort()
        liveStreamsRef.current.delete(sessionId)
      }

      setIsStreaming(true)
      streamingSessionIdRef.current = sessionId
      setError(null)
      setAwaitingApproval(false)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])

      const now = Date.now()
      const pendingUserId = `pending-user-${now}`
      const pendingAssistantId = `pending-assistant-${now}`

      if (!hasUpdatedTitle.current && !titleLockedRef.current && onUpdateSessionTitle) {
        hasUpdatedTitle.current = true
        const title = sessionTitleFromInstruction(content, t('appExtra.newChatTitle'))
        onUpdateSessionTitle(sessionId, title)
        updateSessionTitleApi(sessionId, title).catch(() => {
          // ignore title update errors
        })
      }
      if (sessionId) onPromptSentRef.current?.(sessionId)

      const userMessage: MessagePair = {
        id: pendingUserId,
        user: {
          id: pendingUserId,
          role: 'user',
          content,
          createdAt: now,
          attachments: attachmentMetas,
        },
        assistant: {
          id: pendingAssistantId,
          role: 'assistant',
          content: '',
          createdAt: now,
        },
        isFavorite: false,
        activityStartedAt: now,
      }

      const nextPairs = [...pairsRef.current, userMessage]
      const live: LiveStream = {
        abort: () => {},
        epoch,
        pairs: nextPairs,
        pendingPatches: [],
        pendingShells: [],
        pendingMemories: [],
        awaitingApproval: false,
        error: null,
      }
      liveStreamsRef.current.set(sessionId, live)

      setPairs(() => {
        const idx = nextPairs.length - 1
        window.setTimeout(() => {
          setCurrentIndex(idx)
          pinPairToTop(idx, 'smooth')
          const container = listRef.current
          if (sessionId && container) {
            scrollBySession.current[sessionId] = container.scrollTop
          }
        }, 50)
        return nextPairs
      })

      const { onEvent, onError } = wrapStreamHandlers(sessionId, epoch)
      const abortFn = sendMessageStream(
        sessionId,
        content,
        onEvent,
        onError,
        modelName,
        attachmentIds,
      )
      live.abort = abortFn
      activeStream.current = abortFn
    },
    [
      sessionId,
      isStreaming,
      onUpdateSessionTitle,
      modelName,
      wrapStreamHandlers,
      pinPairToTop,
      t,
    ],
  )

  const retryLastFailed = useCallback(
    (pairId: string) => {
      if (!sessionId || isStreaming) return
      const pair = pairs.find((p) => p.id === pairId)
      if (!pair?.failed) return

      const prevLive = liveStreamsRef.current.get(sessionId)
      const epoch = (prevLive?.epoch ?? 0) + 1
      if (prevLive) {
        prevLive.epoch = epoch
        prevLive.abort()
        liveStreamsRef.current.delete(sessionId)
      }

      setIsStreaming(true)
      streamingSessionIdRef.current = sessionId
      setError(null)
      setAwaitingApproval(false)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])
      const nextPairs = pairs.map((p) =>
        p.id === pairId
          ? {
              ...p,
              failed: false,
              toolTrace: [],
              activityEvents: [],
              activity: undefined,
              activityStartedAt: Date.now(),
              turnMeta: undefined,
              assistant: { ...p.assistant, content: '' },
            }
          : p,
      )
      setPairs(nextPairs)

      const live: LiveStream = {
        abort: () => {},
        epoch,
        pairs: nextPairs,
        pendingPatches: [],
        pendingShells: [],
        pendingMemories: [],
        awaitingApproval: false,
        error: null,
      }
      liveStreamsRef.current.set(sessionId, live)

      const { onEvent, onError } = wrapStreamHandlers(sessionId, epoch)
      const abortFn = regenerateStream(sessionId, onEvent, onError, modelName)
      live.abort = abortFn
      activeStream.current = abortFn
    },
    [sessionId, isStreaming, pairs, modelName, wrapStreamHandlers],
  )

  useEffect(() => {
    return () => {
      // Unmount: detach all fetches (backend may keep running via SSE detach).
      for (const live of liveStreamsRef.current.values()) {
        live.abort()
      }
      liveStreamsRef.current.clear()
      activeStream.current = null
    }
  }, [])

  const warmSession = useCallback((id: string) => {
    if (!id || viewCacheRef.current.has(id) || liveStreamsRef.current.has(id)) return
    if (warmingRef.current.has(id)) return
    warmingRef.current.add(id)
    void (async () => {
      try {
        const [messages, session] = await Promise.all([
          getMessages(id),
          getSession(id).catch(() => null),
        ])
        if (viewCacheRef.current.has(id) || liveStreamsRef.current.has(id)) return
        const nextPairs = buildMessagePairs(messages, session?.leaf_id)
        const view: SessionTranscript = {
          pairs: nextPairs,
          currentIndex: nextPairs.length > 0 ? nextPairs.length - 1 : 0,
          pendingPatches: [],
          pendingShells: [],
          pendingMemories: [],
          awaitingApproval: false,
          error: null,
          isStreaming: Boolean(nextPairs[nextPairs.length - 1]?.turnInProgress),
        }
        viewCacheRef.current.set(id, view)
      } catch {
        // the visible load path reports its own error
      } finally {
        warmingRef.current.delete(id)
      }
    })()
  }, [])

  const favoritePairs = pairs.filter((pair) => pair.isFavorite)

  return {
    pairs,
    isPairsHydrating,
    favoritePairs,
    currentIndex,
    isStreaming,
    awaitingApproval,
    pendingPatches,
    pendingShells,
    pendingMemories,
    patchBusyId,
    shellBusyId,
    memoryBusyId,
    error,
    listRef,
    goPrevious,
    goNext,
    goToIndex,
    toggleFavorite,
    setItemRef,
    sendMessage,
    stopStreaming,
    setFavorite,
    applyPendingPatch: handleApplyPatch,
    applyPartialPatch: handleApplyPartial,
    rejectPendingPatch: handleRejectPatch,
    retryPendingPatch: handleRetryPatch,
    applyPendingShell: handleApplyShell,
    rejectPendingShell: handleRejectShell,
    retryPendingShell: handleRetryShell,
    applyPendingMemory: handleApplyMemory,
    rejectPendingMemory: handleRejectMemory,
    retryLastFailed,
    warmSession,
  }
}

