import { useCallback, useEffect, useRef, useState } from 'react'
import {
  applyMemory,
  applyPatch,
  applyPatchPartial,
  applyShell,
  cancelSession,
  getMessages,
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
import type { MessagePair, PendingMemory, PendingPatch, PendingShell, ToolTraceItem } from '../types'
import { buildMessagePairs, mergeStoppedFailedState } from '../utils/turnTrace'

export function useMessagePairs(
  sessionId: string | null,
  onUpdateSessionTitle?: (sessionId: string, title: string) => void,
  onFavoritesChanged?: () => void,
  modelName?: string,
) {
  const [pairs, setPairs] = useState<MessagePair[]>([])
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
  const activeStream = useRef<(() => void) | null>(null)
  const hasUpdatedTitle = useRef(false)
  const navLockUntil = useRef(0)
  const navLockTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setPairs([])
      setCurrentIndex(0)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])
      setAwaitingApproval(false)
      hasUpdatedTitle.current = false
      return
    }

    // Drop previous session UI immediately so we never flash the wrong thread.
    setPairs([])
    setCurrentIndex(0)
    setPendingPatches([])
    setPendingShells([])
    setPendingMemories([])
    setAwaitingApproval(false)
    setError(null)
    hasUpdatedTitle.current = false

    let cancelled = false

    async function load() {
      try {
        const [messages, patches, shells, memories] = await Promise.all([
          getMessages(sessionId as string),
          listPatches().catch(() => []),
          listShells().catch(() => []),
          listMemoryProposals().catch(() => []),
        ])
        if (cancelled) return

        const loaded = buildMessagePairs(messages)
        const lastIdx = loaded.length > 0 ? loaded.length - 1 : 0
        setPairs(loaded)
        setCurrentIndex(lastIdx)
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
            status: m.status as PendingMemory['status'],
            error: m.error || undefined,
          })),
        )
        setAwaitingApproval(
          patches.some((p) => p.status === 'pending')
            || shells.some((s) => s.status === 'pending')
            || memories.some((m) => m.status === 'pending'),
        )

        // Always land on the latest pair after switching sessions.
        window.setTimeout(() => {
          if (cancelled) return
          const el = itemRefs.current[lastIdx]
          const container = listRef.current
          if (!el || !container) return
          navLockUntil.current = Date.now() + 800
          if (navLockTimer.current) clearTimeout(navLockTimer.current)
          navLockTimer.current = setTimeout(() => {
            navLockUntil.current = 0
          }, 850)
          const containerRect = container.getBoundingClientRect()
          const elementRect = el.getBoundingClientRect()
          const targetScrollTop = container.scrollTop + (elementRect.top - containerRect.top) - 12
          container.scrollTo({ top: Math.max(0, targetScrollTop), behavior: 'auto' })
        }, 50)
      } catch (err) {
        if (cancelled) return
        setError(err instanceof Error ? err.message : '加载消息失败')
        setPairs([])
        setCurrentIndex(0)
        hasUpdatedTitle.current = false
      }
    }

    load()
    return () => {
      cancelled = true
    }
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
      const messages = await getMessages(sessionId as string)
      const loaded = buildMessagePairs(messages)
      const last = loaded[loaded.length - 1]
      return Boolean(last?.turnInProgress)
    }

    async function pollOnce() {
      if (cancelled) return false
      try {
        const [messages, runtime] = await Promise.all([
          getMessages(sessionId as string),
          fetchRuntime().catch(() => ({ active_sessions: [] as string[] })),
        ])
        if (cancelled) return false
        setPairs(buildMessagePairs(messages))
        const active = runtime.active_sessions?.includes(sessionId as string)
        const loaded = buildMessagePairs(messages)
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
    const element = itemRefs.current[index]
    const container = listRef.current
    if (!element || !container) return

    // Keep highlight pinned while smooth-scroll settles (ignore intermediate scroll sync).
    navLockUntil.current = Date.now() + 800
    if (navLockTimer.current) clearTimeout(navLockTimer.current)
    navLockTimer.current = setTimeout(() => {
      navLockUntil.current = 0
    }, 850)

    const containerRect = container.getBoundingClientRect()
    const elementRect = element.getBoundingClientRect()
    const targetScrollTop = container.scrollTop + (elementRect.top - containerRect.top) - 12
    container.scrollTo({ top: Math.max(0, targetScrollTop), behavior: 'smooth' })
  }, [])

  useEffect(() => {
    const container = listRef.current
    if (!container) return

    const handleScroll = () => {
      if (Date.now() < navLockUntil.current) return
      setCurrentIndex(findCurrentIndexFromScroll())
    }

    container.addEventListener('scroll', handleScroll, { passive: true })
    return () => {
      container.removeEventListener('scroll', handleScroll)
      if (navLockTimer.current) clearTimeout(navLockTimer.current)
    }
  }, [findCurrentIndexFromScroll, pairs.length])

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
    // Cancel backend waiters first; aborting SSE alone often drops the TURN_CANCELLED event.
    if (sessionId) {
      void cancelSession(sessionId)
    }
    if (activeStream.current) {
      activeStream.current()
      activeStream.current = null
    }
    setPendingPatches((prev) =>
      prev.map((p) =>
        p.status === 'pending' ? { ...p, status: 'cancelled' as const, error: '已停止' } : p,
      ),
    )
    setPendingShells((prev) =>
      prev.map((s) =>
        s.status === 'pending' || s.status === 'running'
          ? { ...s, status: 'cancelled' as const, error: '已停止' }
          : s,
      ),
    )
    setPendingMemories((prev) =>
      prev.map((m) =>
        m.status === 'pending' ? { ...m, status: 'cancelled' as const, error: '已停止' } : m,
      ),
    )
    setPairs((prev) => {
      const last = prev[prev.length - 1]
      if (!last) return prev
      const trace = (last.toolTrace || []).map((t) =>
        t.status === 'running' ? { ...t, status: 'error' as const, detail: '已停止' } : t,
      )
      const updated = [...prev]
      updated[prev.length - 1] = {
        ...last,
        failed: true,
        turnInProgress: false,
        toolTrace: trace.length > 0 ? trace : last.toolTrace,
        assistant: {
          ...last.assistant,
          content: last.assistant.content || '已停止',
        },
      }
      return updated
    })
    setError('已停止')
    setIsStreaming(false)
    setAwaitingApproval(false)

    if (sessionId) {
      window.setTimeout(async () => {
        try {
          const messages = await getMessages(sessionId)
          const loaded = buildMessagePairs(messages)
          setPairs((prev) => mergeStoppedFailedState(prev, loaded))
        } catch {
          // keep local stopped state
        }
      }, 500)
    }
  }, [sessionId])

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
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Apply 失败')
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch],
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
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : '部分应用失败')
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch],
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
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Reject 失败')
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch],
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
        setError(err instanceof Error ? err.message : 'Retry 失败')
      } finally {
        setPatchBusyId(null)
      }
    },
    [upsertPatch],
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
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Run 失败')
      } finally {
        setShellBusyId(null)
      }
    },
    [upsertShell],
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
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Reject 失败')
      } finally {
        setShellBusyId(null)
      }
    },
    [upsertShell],
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
        setError(err instanceof Error ? err.message : 'Retry 失败')
      } finally {
        setShellBusyId(null)
      }
    },
    [upsertShell],
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
          status: result.status as PendingMemory['status'],
          error: result.error || undefined,
        })
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Apply 记忆失败')
      } finally {
        setMemoryBusyId(null)
      }
    },
    [upsertMemory],
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
          status: result.status as PendingMemory['status'],
          error: result.error || undefined,
        })
        setAwaitingApproval(false)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Reject 记忆失败')
      } finally {
        setMemoryBusyId(null)
      }
    },
    [upsertMemory],
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
            goal: event.goal || last.goal,
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
            goal: event.goal || last.goal,
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
          updated[prev.length - 1] = { ...last, failed: false, toolTrace: trace }
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
          updated[prev.length - 1] = { ...last, toolTrace: trace }
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
        if (!event.status || event.status === 'pending') {
          setAwaitingApproval(true)
        } else {
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
        if (!event.status || event.status === 'pending' || event.status === 'running') {
          setAwaitingApproval(true)
        } else {
          setAwaitingApproval(false)
        }
      } else if (event.type === 'memory' && event.memory_id) {
        upsertMemory({
          id: event.memory_id,
          mode: event.mode || 'replace',
          preview: event.preview || event.content || '',
          content: event.content || event.preview || '',
          status: (event.status as PendingMemory['status']) || 'pending',
          error: event.error,
        })
        if (!event.status || event.status === 'pending') {
          setAwaitingApproval(true)
        } else {
          setAwaitingApproval(false)
        }
      } else if (event.type === 'turn_meta') {
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const updated = [...prev]
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
              goal: event.goal || last.goal,
            },
            goal: event.goal || last.goal,
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
              detail: '等待审批…',
            }
          }
          updated[prev.length - 1] = { ...last, toolTrace: trace }
          return updated
        })
      } else if (event.type === 'tools_disabled') {
        setError(event.message || '当前模型不支持工具调用，已降级为纯文本。')
      } else if (event.type === 'stream_end') {
        // SSE closed without done/error (proxy drop / abort). Keep approval UI if needed.
        setIsStreaming(false)
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last?.toolTrace?.some((t) => t.status === 'running')) return prev
          // leave running markers if still awaiting; otherwise mark stopped
          return prev
        })
      } else if (event.type === 'token' && event.content) {
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
              const messages = await getMessages(sessionId)
              const loaded = buildMessagePairs(messages)
              setPairs((prev) => {
                const lastPrev = prev[prev.length - 1]
                const lastLoaded = loaded[loaded.length - 1]
                if (!lastPrev || !lastLoaded) return loaded.length ? loaded : prev
                const merged = [...loaded]
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
                }
                return merged
              })
            } catch {
              // keep local state
            }
          }, 500)
        }
        setCurrentIndex((prev) => Math.max(prev, pairs.length))
        requestAnimationFrame(() => {
          const container = listRef.current
          if (container) {
            container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' })
          }
        })
      } else if (event.type === 'error') {
        setIsStreaming(false)
        setAwaitingApproval(false)
        activeStream.current = null
        const cancelled = event.code === 'TURN_CANCELLED'
        const errorMessage = event.message || (cancelled ? '已停止' : '抱歉，请求失败，请重试。')
        setError(errorMessage)
        setPairs((prev) => {
          const last = prev[prev.length - 1]
          if (!last) return prev
          const trace = (last.toolTrace || []).map((t) =>
            t.status === 'running' ? { ...t, status: 'error' as const, detail: cancelled ? '已停止' : t.detail } : t,
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
              const messages = await getMessages(sessionId)
              const loaded = buildMessagePairs(messages)
              setPairs((prev) => mergeStoppedFailedState(prev, loaded))
            } catch {
              // keep local state
            }
          }, 500)
        }
      }
    },
    [pairs.length, sessionId, upsertPatch, upsertShell, upsertMemory],
  )

  const handleStreamError = useCallback((streamError: Error) => {
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
          content: last.assistant.content || '抱歉，请求失败，请重试。',
        },
      }
      return updated
    })
  }, [])

  const sendMessage = useCallback(
    (content: string, attachmentIds?: string[], attachmentMetas?: import('../types').AttachmentMeta[]) => {
      if (!sessionId || isStreaming) return

      setIsStreaming(true)
      setError(null)
      setAwaitingApproval(false)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])

      const now = Date.now()
      const pendingUserId = `pending-user-${now}`
      const pendingAssistantId = `pending-assistant-${now}`

      if (!hasUpdatedTitle.current && onUpdateSessionTitle) {
        hasUpdatedTitle.current = true
        const title = content.trim().slice(0, 20) || '新对话'
        onUpdateSessionTitle(sessionId, title)
        updateSessionTitleApi(sessionId, title).catch(() => {
          // ignore title update errors
        })
      }

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
      }

      setPairs((prev) => [...prev, userMessage])

      activeStream.current = sendMessageStream(
        sessionId,
        content,
        handleStreamEvent,
        handleStreamError,
        modelName,
        attachmentIds,
      )
    },
    [
      sessionId,
      isStreaming,
      onUpdateSessionTitle,
      modelName,
      handleStreamEvent,
      handleStreamError,
    ],
  )

  const retryLastFailed = useCallback(
    (pairId: string) => {
      if (!sessionId || isStreaming) return
      const pair = pairs.find((p) => p.id === pairId)
      if (!pair?.failed) return

      setIsStreaming(true)
      setError(null)
      setAwaitingApproval(false)
      setPendingPatches([])
      setPendingShells([])
      setPendingMemories([])
      setPairs((prev) =>
        prev.map((p) =>
          p.id === pairId
            ? {
                ...p,
                failed: false,
                toolTrace: [],
                turnMeta: undefined,
                assistant: { ...p.assistant, content: '' },
              }
            : p,
        ),
      )

      activeStream.current = regenerateStream(
        sessionId,
        handleStreamEvent,
        handleStreamError,
        modelName,
      )
    },
    [sessionId, isStreaming, pairs, modelName, handleStreamEvent, handleStreamError],
  )

  const retryToolStep = useCallback(
    async (pairId: string, item: ToolTraceItem) => {
      if (!sessionId || isStreaming) return
      try {
        const data = JSON.parse(item.detail || '') as Record<string, unknown>
        if (typeof data.patch_id === 'string' && data.patch_id) {
          await handleRetryPatch(data.patch_id)
          return
        }
        if (typeof data.shell_id === 'string' && data.shell_id) {
          await handleRetryShell(data.shell_id)
          return
        }
      } catch (err) {
        if (err instanceof Error && err.message && !err.message.includes('无法单独重试')) {
          setError(err.message)
          return
        }
        // not json / no ids
      }
      const pair = pairs.find((p) => p.id === pairId)
      if (pair?.failed) {
        retryLastFailed(pairId)
        return
      }
      setError('该工具步无法单独重试；请重试整轮或在下方 Diff/Shell 面板操作')
    },
    [
      sessionId,
      isStreaming,
      pairs,
      handleRetryPatch,
      handleRetryShell,
      retryLastFailed,
    ],
  )

  useEffect(() => {
    return () => {
      if (activeStream.current) {
        activeStream.current()
        activeStream.current = null
      }
    }
  }, [])

  const favoritePairs = pairs.filter((pair) => pair.isFavorite)

  return {
    pairs,
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
    retryToolStep,
  }
}

