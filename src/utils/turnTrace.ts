import type { ApiMessage } from '../api/agent'
import type { MessagePair, ToolTraceItem, TurnMeta } from '../types'
import {
  activityEventsFromTrace,
  buildTurnActivity,
} from './turnActivity'

export interface TurnEvent {
  type: string
  ts?: number
  tool?: string
  status?: string
  summary?: string
  full_ref?: string
  goal?: string
  previous_goal?: string
  tools_since_last?: number
  reason?: string
  reply?: string
  settled?: boolean
  truncated?: boolean
}

const FILE_REF_PREFIX = 'file:'

export function isFileRef(value?: string | null): boolean {
  return Boolean(value && value.startsWith(FILE_REF_PREFIX))
}

function detailFieldsFromEvent(ev: TurnEvent): Pick<ToolTraceItem, 'detail' | 'fullRef' | 'truncated'> {
  if (isFileRef(ev.full_ref)) {
    return {
      detail: ev.summary || '大输出已落盘',
      fullRef: ev.full_ref,
      truncated: true,
    }
  }
  return {
    detail: ev.full_ref || ev.summary || '',
    truncated: Boolean(ev.truncated),
  }
}

export type AssistantSummaryState =
  | { kind: 'meta'; turnMeta: TurnMeta }
  | { kind: 'cancelled'; message: string; code?: string }
  | { kind: 'failed'; message: string; code?: string }

function parseTurnMeta(summary?: string): TurnMeta | undefined {
  if (!summary) return undefined
  try {
    const parsed = JSON.parse(summary) as Record<string, unknown>
    if (parsed.type === 'turn_meta') {
      return parsed as unknown as TurnMeta
    }
  } catch {
    // ignore
  }
  return undefined
}

export function parseAssistantSummary(summary?: string | null): AssistantSummaryState | undefined {
  if (!summary) return undefined
  try {
    const parsed = JSON.parse(summary) as Record<string, unknown>
    const type = parsed.type
    if (type === 'turn_meta') {
      const turnMeta = parseTurnMeta(summary)
      if (turnMeta) return { kind: 'meta', turnMeta }
    }
    if (type === 'turn_cancelled') {
      return {
        kind: 'cancelled',
        message: String(parsed.message || '已停止'),
        code: typeof parsed.code === 'string' ? parsed.code : undefined,
      }
    }
    if (type === 'turn_failed') {
      return {
        kind: 'failed',
        message: String(parsed.message || '请求失败'),
        code: typeof parsed.code === 'string' ? parsed.code : undefined,
      }
    }
  } catch {
    // ignore
  }
  return undefined
}

export function eventsToToolTrace(events: TurnEvent[]): ToolTraceItem[] {
  const trace: ToolTraceItem[] = []
  for (const ev of events) {
    if (ev.type === 'tool_start') {
      trace.push({
        name: ev.tool || 'tool',
        status: 'running',
        ...detailFieldsFromEvent(ev),
      })
    } else if (ev.type === 'tool_result') {
      const name = ev.tool || 'tool'
      const status = ev.status || 'done'
      const isError = ['failed', 'timeout', 'error', 'rejected', 'cancelled'].includes(status)
      const item: ToolTraceItem = {
        name,
        status: isError ? 'error' : 'done',
        ...detailFieldsFromEvent(ev),
      }
      const idx = [...trace].reverse().findIndex((t) => t.name === name && t.status === 'running')
      if (idx >= 0) {
        trace[trace.length - 1 - idx] = item
      } else {
        trace.push(item)
      }
    } else if (
      (ev.type === 'gate' || ev.type === 'diff' || ev.type === 'shell' || ev.type === 'memory') &&
      ev.status === 'pending'
    ) {
      const last = trace[trace.length - 1]
      if (last?.status === 'running') {
        trace[trace.length - 1] = {
          ...last,
          detail: ev.summary || '等待审批…',
        }
      }
    } else if (ev.type === 'error') {
      const last = trace[trace.length - 1]
      if (last?.status === 'running') {
        trace[trace.length - 1] = {
          ...last,
          status: 'error',
          detail: ev.summary || '已停止',
        }
      }
    }
  }
  return trace
}

export function latestGoal(events: TurnEvent[]): string | undefined {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i]
    if (ev.type === 'turn_goal') {
      const goal = (ev.goal || ev.summary || '').trim()
      if (goal) return goal
    }
  }
  return undefined
}

export function latestPreviousGoal(events: TurnEvent[]): string | undefined {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i]
    if (ev.type === 'turn_goal') {
      const prev = (ev.previous_goal || '').trim()
      if (prev) return prev
    }
  }
  return undefined
}

export function latestProgressCheckpoint(
  events: TurnEvent[],
): MessagePair['progressCheckpoint'] | undefined {
  let pending: MessagePair['progressCheckpoint'] | undefined
  let settled: MessagePair['progressCheckpoint'] | undefined
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const ev = events[i]
    if (ev.type !== 'progress_checkpoint') continue
    let reply = (ev.reply || '').trim()
    if (!reply && ev.full_ref) {
      const maybe = ev.full_ref.trim()
      if (maybe && maybe !== 'interval' && maybe !== 'gate') reply = maybe
    }
    const item: NonNullable<MessagePair['progressCheckpoint']> = {
      toolsSinceLast: ev.tools_since_last ?? 0,
      reason: ev.reason || ev.summary || 'interval',
    }
    if (reply) {
      item.reply = reply
      item.settled = true
      return item
    }
    if (ev.settled) {
      item.settled = true
      if (!settled) settled = item
      continue
    }
    if (!pending) pending = item
  }
  return settled ?? pending
}

export function isAssistantTurnInProgress(
  assistant: ApiMessage,
  summaryState?: AssistantSummaryState,
): boolean {
  if (summaryState?.kind === 'meta') return false
  if (summaryState?.kind === 'cancelled' || summaryState?.kind === 'failed') return false
  const events = assistant.trace || []
  return events.length > 0 || !assistant.content.trim()
}

export function hydrateAssistantFromTrace(
  assistant: ApiMessage,
  summaryState?: AssistantSummaryState,
  turnMeta?: TurnMeta,
): Pick<
  MessagePair,
  | 'toolTrace'
  | 'goal'
  | 'previousGoal'
  | 'progressCheckpoint'
  | 'turnInProgress'
  | 'failed'
  | 'softLanded'
  | 'activityEvents'
  | 'activity'
  | 'activityStartedAt'
> {
  const events: TurnEvent[] = (assistant.trace || []).map((ev) => ({
    type: String(ev.type ?? ''),
    ts: typeof ev.ts === 'number' ? ev.ts : undefined,
    tool: typeof ev.tool === 'string' ? ev.tool : undefined,
    status: typeof ev.status === 'string' ? ev.status : undefined,
    summary: typeof ev.summary === 'string' ? ev.summary : undefined,
    full_ref: typeof ev.full_ref === 'string' ? ev.full_ref : undefined,
    goal: typeof ev.goal === 'string' ? ev.goal : undefined,
    previous_goal: typeof ev.previous_goal === 'string' ? ev.previous_goal : undefined,
    tools_since_last: typeof (ev as { tools_since_last?: number }).tools_since_last === 'number'
      ? (ev as { tools_since_last: number }).tools_since_last
      : undefined,
    reason: typeof ev.reason === 'string' ? ev.reason : undefined,
    reply: typeof ev.reply === 'string' ? ev.reply : undefined,
    settled: Boolean((ev as { settled?: boolean }).settled),
    truncated: Boolean(ev.truncated),
  }))
  const parsed = summaryState ?? parseAssistantSummary(assistant.summary)
  const meta = turnMeta ?? (parsed?.kind === 'meta' ? parsed.turnMeta : undefined)
  const failed =
    parsed?.kind === 'cancelled' ||
    parsed?.kind === 'failed' ||
    events.some((e) => e.type === 'error' && e.status === 'TURN_CANCELLED')
  const softFromTrace = events.some((e) => e.type === 'soft_land')
  const softFromContent =
    typeof assistant.content === 'string' &&
    (assistant.content.includes('工具轮次已用尽') || assistant.content.includes('提前收口'))
  const activityEvents = activityEventsFromTrace(
    (assistant.trace || []) as Array<Record<string, unknown>>,
  )
  const activity = activityEvents.length > 0 ? buildTurnActivity(activityEvents) : undefined
  const firstTs = events.find((e) => typeof e.ts === 'number')?.ts
  return {
    toolTrace: events.length > 0 ? eventsToToolTrace(events) : undefined,
    goal: latestGoal(events) ?? meta?.goal,
    previousGoal: latestPreviousGoal(events),
    progressCheckpoint: latestProgressCheckpoint(events),
    turnInProgress: isAssistantTurnInProgress(assistant, parsed),
    failed: failed || undefined,
    softLanded: softFromTrace || softFromContent || undefined,
    activityEvents: activityEvents.length > 0 ? activityEvents : undefined,
    activity,
    activityStartedAt: firstTs,
  }
}

/** Keep local stopped/failed state if API reload races finalize_interrupted. */
export function mergeStoppedFailedState(prev: MessagePair[], loaded: MessagePair[]): MessagePair[] {
  const lastPrev = prev[prev.length - 1]
  const lastLoaded = loaded[loaded.length - 1]
  if (!lastPrev?.failed || !lastLoaded || lastLoaded.failed) return loaded
  const merged = [...loaded]
  merged[merged.length - 1] = {
    ...lastLoaded,
    failed: true,
    turnInProgress: false,
    assistant: {
      ...lastLoaded.assistant,
      content: lastLoaded.assistant.content || lastPrev.assistant.content || '已停止',
    },
  }
  return merged
}

/** Walk parent_id chain leaf→root, return root→leaf. */
export function walkPathToRoot(messages: ApiMessage[], leafId: string): ApiMessage[] {
  const byId = new Map(messages.map((m) => [m.id, m]))
  const path: ApiMessage[] = []
  const seen = new Set<string>()
  let currentId: string | null | undefined = leafId
  while (currentId) {
    if (seen.has(currentId)) break
    seen.add(currentId)
    const msg = byId.get(currentId)
    if (!msg) break
    path.push(msg)
    currentId = msg.parent_id ?? null
  }
  path.reverse()
  return path
}

/** Prefer session leaf_id; else newest by sequence (matches backend fallback). */
export function resolveLeafId(messages: ApiMessage[], leafId?: string | null): string | null {
  if (leafId && messages.some((m) => m.id === leafId)) return leafId
  if (messages.length === 0) return null
  let best = messages[0]
  for (const m of messages) {
    if (m.sequence > best.sequence) best = m
  }
  return best.id
}

function pairAlongOrderedMessages(ordered: ApiMessage[]): MessagePair[] {
  const pairs: MessagePair[] = []
  for (let i = 0; i < ordered.length; i += 1) {
    const user = ordered[i]
    if (user.role !== 'user') continue

    const next = ordered[i + 1]
    const assistant: ApiMessage =
      next?.role === 'assistant'
        ? next
        : {
            id: `orphan-assistant-${user.id}`,
            role: 'assistant',
            content: '',
            sequence: user.sequence + 1,
            is_favorite: false,
            trace: [],
            created_at: user.created_at,
          }

    const summaryState = parseAssistantSummary(assistant.summary)
    const turnMeta = summaryState?.kind === 'meta' ? summaryState.turnMeta : undefined
    const hydrated = hydrateAssistantFromTrace(assistant, summaryState, turnMeta)

    pairs.push({
      id: user.id,
      user: {
        id: user.id,
        role: 'user',
        content: user.content,
        createdAt: new Date(user.created_at).getTime(),
        attachments: user.attachments,
      },
      assistant: {
        id: assistant.id,
        role: 'assistant',
        content: assistant.content,
        createdAt: new Date(assistant.created_at).getTime(),
      },
      isFavorite: user.is_favorite,
      turnMeta,
      ...hydrated,
    })

    if (next?.role === 'assistant') i += 1
  }
  return pairs
}

/**
 * Build chat pairs for the active session tip.
 * After regenerate, siblings share a user: sequence pairing would stick to the *old*
 * assistant. We walk parent_id from leaf_id (or max sequence) so the UI shows the tip path.
 */
export function buildMessagePairs(
  messages: ApiMessage[],
  leafId?: string | null,
): MessagePair[] {
  if (messages.length === 0) return []

  const hasParentLinks = messages.some((m) => m.parent_id != null && m.parent_id !== '')
  const tip = resolveLeafId(messages, leafId)

  if (hasParentLinks && tip) {
    const path = walkPathToRoot(messages, tip)
    // Degenerate (broken ids): fall back to linear sequence
    if (path.length >= 1) {
      return pairAlongOrderedMessages(path)
    }
  }

  const sorted = [...messages].sort((a, b) => a.sequence - b.sequence)
  return pairAlongOrderedMessages(sorted)
}
