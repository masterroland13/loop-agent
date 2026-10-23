/**
 * Apply SSE events to an in-memory session snapshot while the UI is on another chat.
 * Keeps Phase-2 background streams coherent for switch-back without touching React state.
 */
import type { MessagePair, PendingMemory, PendingPatch, PendingShell } from '../types'
import type { StreamEvent } from '../api/agent'
import { getApiErrorLocale } from '../api/agent'
import { translate } from '../i18n'
import { pairWithActivityEvent, type ActivityEvent } from './turnActivity'

export type OfflineLiveState = {
  pairs: MessagePair[]
  pendingPatches: PendingPatch[]
  pendingShells: PendingShell[]
  pendingMemories: PendingMemory[]
  awaitingApproval: boolean
  error: string | null
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

function upsertById<T extends { id: string }>(list: T[], item: T): T[] {
  const idx = list.findIndex((x) => x.id === item.id)
  if (idx < 0) return [...list, item]
  const next = [...list]
  next[idx] = { ...next[idx], ...item }
  return next
}

/** @returns true if the stream should be considered finished (drop live entry). */
export function applyOfflineStreamEvent(
  live: OfflineLiveState,
  event: StreamEvent,
): boolean {
  if (event.type === 'meta' && event.message_id) {
    const last = live.pairs[live.pairs.length - 1]
    if (!last) return false
    const updated = [...live.pairs]
    updated[updated.length - 1] = {
      ...last,
      id: event.message_id as string,
      user: { ...last.user, id: event.message_id as string },
      goal:
        typeof event.goal === 'string' && event.goal.trim()
          ? event.goal.trim()
          : undefined,
      turnInProgress: true,
      assistant: event.assistant_message_id
        ? { ...last.assistant, id: event.assistant_message_id as string }
        : last.assistant,
    }
    live.pairs = updated
    return false
  }

  if (event.type === 'turn_goal' && event.goal) {
    const last = live.pairs[live.pairs.length - 1]
    if (!last) return false
    const prevGoal =
      typeof event.previous_goal === 'string' && event.previous_goal.trim()
        ? event.previous_goal.trim()
        : undefined
    const updated = [...live.pairs]
    updated[updated.length - 1] = {
      ...last,
      goal: event.goal,
      ...(prevGoal ? { previousGoal: prevGoal } : {}),
    }
    live.pairs = updated
    return false
  }

  if (event.type === 'tool_start' && event.name) {
    const last = live.pairs[live.pairs.length - 1]
    if (!last) return false
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
    const updated = [...live.pairs]
    updated[updated.length - 1] = {
      ...last,
      failed: false,
      toolTrace: trace,
      activityEvents: act.activityEvents,
      activity: act.activity,
      activityStartedAt: act.activityStartedAt,
    }
    live.pairs = updated
    return false
  }

  if (event.type === 'tool_result' && event.name) {
    const last = live.pairs[live.pairs.length - 1]
    if (!last) return false
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
      isError =
        Boolean(parsed.error) || parsed.status === 'failed' || parsed.status === 'timeout'
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
      trace[realIdx] = { ...trace[realIdx], ...item }
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
    const updated = [...live.pairs]
    updated[updated.length - 1] = {
      ...last,
      toolTrace: trace,
      activityEvents: act.activityEvents,
      activity: act.activity,
      activityStartedAt: act.activityStartedAt,
    }
    live.pairs = updated
    return false
  }

  if (event.type === 'diff' && event.patch_id && event.path) {
    live.pendingPatches = upsertById(live.pendingPatches, {
      id: event.patch_id,
      path: event.path,
      unified_diff: event.unified_diff || '',
      is_new_file: Boolean(event.is_new_file),
      is_delete: Boolean(event.is_delete),
      status: (event.status as PendingPatch['status']) || 'pending',
      error: event.error,
    })
    live.pairs = applyActivityToLast(live.pairs, {
      type: 'diff',
      patch_id: event.patch_id,
      path: event.path,
      unified_diff: event.unified_diff,
      status: event.status || 'pending',
      is_new_file: event.is_new_file,
      is_delete: event.is_delete,
    })
    if (event.status && event.status !== 'pending') live.awaitingApproval = false
    return false
  }

  if (event.type === 'shell' && event.shell_id) {
    live.pendingShells = upsertById(live.pendingShells, {
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
    live.pairs = applyActivityToLast(live.pairs, {
      type: 'shell',
      shell_id: event.shell_id,
      command: event.command || (event.argv || []).join(' '),
      argv: event.argv,
      status: event.status || 'pending',
      exit_code: event.exit_code,
    })
    if (event.status && event.status !== 'pending' && event.status !== 'running') {
      live.awaitingApproval = false
    }
    return false
  }

  if (event.type === 'memory' && event.memory_id) {
    live.pendingMemories = upsertById(live.pendingMemories, {
      id: event.memory_id,
      mode: event.mode || 'replace',
      target: event.target === 'memory' ? 'memory' : 'user',
      preview: event.preview || event.content || '',
      content: event.content || event.preview || '',
      status: (event.status as PendingMemory['status']) || 'pending',
      error: event.error,
      op_summary: typeof event.op_summary === 'string' ? event.op_summary : undefined,
    })
    live.pairs = applyActivityToLast(live.pairs, {
      type: 'memory',
      status: event.status || 'pending',
      target: event.target === 'memory' ? 'memory' : 'user',
    })
    if (event.status && event.status !== 'pending') live.awaitingApproval = false
    return false
  }

  if (event.type === 'await_approval') {
    live.awaitingApproval = true
    return false
  }

  if (event.type === 'soft_land') {
    live.pairs = applyActivityToLast(
      live.pairs,
      { type: 'soft_land', reason: event.reason },
      { softLanded: true },
    )
    return false
  }

  if (event.type === 'edit_nudge') {
    live.pairs = applyActivityToLast(live.pairs, {
      type: 'edit_nudge',
      reason: event.reason || 'missing_propose_edit',
    })
    return false
  }

  if (event.type === 'thought') {
    live.pairs = applyActivityToLast(live.pairs, {
      type: 'thought',
      phase: event.phase || 'end',
      text: event.text || event.content || '',
      duration_ms: event.duration_ms,
      source: event.source,
    })
    return false
  }

  if (event.type === 'token' && event.content) {
    live.error = null
    const last = live.pairs[live.pairs.length - 1]
    if (!last) return false
    const updated = [...live.pairs]
    updated[updated.length - 1] = {
      ...last,
      failed: false,
      assistant: {
        ...last.assistant,
        content: last.assistant.content + event.content,
      },
    }
    live.pairs = updated
    return false
  }

  if (event.type === 'tools_disabled') {
    live.error =
      event.message || translate(getApiErrorLocale(), 'errors.toolsDisabled')
    return false
  }

  if (event.type === 'turn_meta') {
    const last = live.pairs[live.pairs.length - 1]
    if (!last) return false
    const liveGoal =
      typeof event.goal === 'string' && event.goal.trim() ? event.goal.trim() : undefined
    const updated = [...live.pairs]
    updated[updated.length - 1] = {
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
    live.pairs = updated
    return false
  }

  if (event.type === 'done') {
    live.error = null
    live.awaitingApproval = false
    if (event.message_id) {
      const last = live.pairs[live.pairs.length - 1]
      if (last) {
        const updated = [...live.pairs]
        updated[updated.length - 1] = {
          ...last,
          failed: false,
          turnInProgress: false,
          assistant: { ...last.assistant, id: event.message_id as string },
        }
        live.pairs = updated
      }
    } else {
      const last = live.pairs[live.pairs.length - 1]
      if (last?.turnInProgress) {
        const updated = [...live.pairs]
        updated[updated.length - 1] = { ...last, turnInProgress: false }
        live.pairs = updated
      }
    }
    return true
  }

  if (event.type === 'error' || event.type === 'stream_end') {
    const cancelled = event.type === 'error' && event.code === 'TURN_CANCELLED'
    const locale = getApiErrorLocale()
    const errorMessage =
      event.type === 'error'
        ? event.message ||
          (cancelled
            ? translate(locale, 'message.stopped')
            : translate(locale, 'errors.requestFailed'))
        : null
    if (errorMessage) live.error = errorMessage
    live.awaitingApproval = false
    const last = live.pairs[live.pairs.length - 1]
    if (last && event.type === 'error') {
      const stopped = translate(locale, 'message.stopped')
      const trace = (last.toolTrace || []).map((t) =>
        t.status === 'running'
          ? { ...t, status: 'error' as const, detail: cancelled ? stopped : t.detail }
          : t,
      )
      const updated = [...live.pairs]
      updated[updated.length - 1] = {
        ...last,
        failed: true,
        turnInProgress: false,
        toolTrace: trace.length > 0 ? trace : last.toolTrace,
        assistant: {
          ...last.assistant,
          content: last.assistant.content || errorMessage || '',
        },
      }
      live.pairs = updated
    }
    return true
  }

  return false
}
