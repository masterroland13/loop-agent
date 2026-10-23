/**
 * Turn activity timeline types + reducer (S0a).
 * Mirrors backend `agent_window.agent.turn_activity` for S0b UI wiring.
 * Thought only comes from explicit `thought` events — never invented from tools.
 */

export type ActivityKind = 'thought' | 'explore' | 'edit' | 'run' | 'note'
export type SegmentKind = 'thought' | 'explored' | 'edited' | 'note'
export type ExploreAction = 'read' | 'grep' | 'list' | 'other'

export const EXPLORE_TOOLS = new Set([
  'list_dir',
  'read_file',
  'grep',
  'read_attachment',
])
export const EDIT_TOOLS = new Set(['propose_edit', 'propose_delete'])
export const RUN_TOOLS = new Set(['propose_shell'])
export const MEMORY_TOOLS = new Set(['propose_memory'])

const ERROR_STATUSES = new Set([
  'failed',
  'timeout',
  'error',
  'rejected',
  'cancelled',
])
const APPLIED_EDIT_STATUSES = new Set(['applied', 'partial'])

export interface ActivityItem {
  id: string
  kind: ActivityKind
  summary: string
  ts?: number
  action?: ExploreAction
  path?: string
  query?: string
  lines?: string
  status?: string
  patch_id?: string
  shell_id?: string
  add_lines?: number
  del_lines?: number
  command?: string
  exit_code?: number
  text?: string
  duration_ms?: number
  source?: string
  note_type?: string
  tool_call_id?: string
}

export interface ActivitySegment {
  kind: SegmentKind
  summary: string
  items: ActivityItem[]
  add_total: number
  del_total: number
  applied_file_count: number
  pending_file_count: number
  rejected_file_count: number
  command_count: number
  file_count: number
  search_count: number
}

export interface TurnActivitySnapshot {
  items: ActivityItem[]
  segments: ActivitySegment[]
  stats: {
    applied_file_count: number
    pending_file_count: number
    add_total: number
    del_total: number
    has_thought: boolean
  }
}

export type ActivityEvent = Record<string, unknown>

export function classifyTool(name: string): ActivityKind | null {
  const n = (name || '').trim()
  if (EXPLORE_TOOLS.has(n)) return 'explore'
  if (EDIT_TOOLS.has(n)) return 'edit'
  if (RUN_TOOLS.has(n)) return 'run'
  if (MEMORY_TOOLS.has(n)) return 'note'
  return null
}

export function countDiffLines(unifiedDiff?: string | null): [number, number] {
  if (!unifiedDiff) return [0, 0]
  let add = 0
  let del = 0
  for (const line of unifiedDiff.split('\n')) {
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) continue
    if (line.startsWith('+')) add += 1
    else if (line.startsWith('-')) del += 1
  }
  return [add, del]
}

export function toolNameOf(event: ActivityEvent): string {
  return String(event.name || event.tool || '').trim()
}

export function parseToolArguments(event: ActivityEvent): Record<string, unknown> {
  let raw: unknown = event.arguments
  if (raw == null) {
    const ref = event.full_ref
    if (typeof ref === 'string' && ref.trim() && !ref.startsWith('file:')) {
      raw = ref
    }
  }
  return parseJsonObj(raw)
}

function toolResultPayload(event: ActivityEvent): Record<string, unknown> {
  return (
    parseJsonObj(event.content) ||
    parseJsonObj(event.full_ref) ||
    parseJsonObj(event.summary) ||
    {}
  )
}

/** Expand persisted TurnEvent shapes into live SSE-like activity events. */
export function normalizeActivityEvent(event: ActivityEvent): ActivityEvent {
  const out: ActivityEvent = { ...event }
  const etype = String(out.type || '')

  if ((etype === 'tool_start' || etype === 'tool_result') && !out.name && out.tool) {
    out.name = out.tool
  }

  if (etype !== 'gate') return out

  const tool = String(out.tool || '').trim()
  const payload = parseJsonObj(out.full_ref)
  const payloadType = String(payload.type || '').trim()

  if (tool === 'propose_edit' || payloadType === 'diff') {
    return {
      ...out,
      ...payload,
      type: 'diff',
      status: out.status || payload.status || 'pending',
      patch_id: payload.patch_id ?? out.patch_id,
      path: payload.path ?? out.path,
      unified_diff: payload.unified_diff ?? out.unified_diff,
      is_new_file: payload.is_new_file ?? out.is_new_file,
      is_delete: payload.is_delete ?? out.is_delete,
      error: payload.error ?? out.error,
    }
  }

  if (tool === 'propose_shell' || payloadType === 'shell') {
    return {
      ...out,
      ...payload,
      type: 'shell',
      status: out.status || payload.status || 'pending',
      shell_id: payload.shell_id ?? payload.id ?? out.shell_id,
      command: payload.command ?? out.command,
      argv: payload.argv ?? out.argv,
      exit_code: payload.exit_code ?? out.exit_code,
    }
  }

  if (tool === 'propose_memory' || payloadType === 'memory') {
    return {
      ...out,
      ...payload,
      type: 'memory',
      status: out.status || payload.status || 'pending',
      memory_id: payload.memory_id ?? payload.id ?? out.memory_id,
      target: payload.target ?? out.target ?? 'memory',
    }
  }

  return out
}

function parseJsonObj(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, unknown>
  }
  if (typeof raw !== 'string' || !raw.trim()) return {}
  try {
    const parsed = JSON.parse(raw) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    // ignore
  }
  return {}
}

function basename(path?: string | null): string {
  if (!path) return ''
  const p = path.replace(/\\/g, '/').replace(/\/+$/, '')
  const parts = p.split('/')
  return parts[parts.length - 1] || path
}

function lineRange(args: Record<string, unknown>): string | undefined {
  const offset = args.offset
  const limit = args.limit
  if (offset == null && limit == null) return undefined
  try {
    const start = offset != null ? Number(offset) : 1
    if (Number.isNaN(start)) return undefined
    if (limit == null) return `L${start}+`
    const end = start + Number(limit) - 1
    return `L${start}–${Number.isNaN(end) ? start : Math.max(start, end)}`
  } catch {
    return undefined
  }
}

function exploreAction(tool: string): ExploreAction {
  if (tool === 'read_file' || tool === 'read_attachment') return 'read'
  if (tool === 'grep') return 'grep'
  if (tool === 'list_dir') return 'list'
  return 'other'
}

function exploreSummary(
  action: ExploreAction,
  path?: string,
  query?: string,
  lines?: string,
): string {
  const label = basename(path) || path || ''
  if (action === 'read') {
    const base = label ? `Read ${label}` : 'Read file'
    return lines ? `${base} ${lines}`.trim() : base
  }
  if (action === 'grep') {
    const q = (query || '').trim()
    const qBit = q ? ` \`${q}\`` : ''
    const where = label ? ` in ${label}` : ''
    return `Grepped${qBit}${where}`.trim()
  }
  if (action === 'list') return label ? `Listed ${label}` : 'Listed directory'
  return label || 'Explored'
}

function editSummary(path: string | undefined, status: string, addN: number, delN: number): string {
  const label = basename(path) || path || 'file'
  if (APPLIED_EDIT_STATUSES.has(status)) return `Edited ${label} +${addN} −${delN}`
  if (status === 'pending') return `Proposed ${label}`
  if (status === 'rejected') return `Rejected ${label}`
  if (status === 'partial') return `Partially edited ${label} +${addN} −${delN}`
  return `Edit ${label} (${status})`
}

function runSummary(command: string | undefined, status: string, exitCode?: number): string {
  let cmd = (command || '').trim() || 'command'
  if (cmd.length > 80) cmd = `${cmd.slice(0, 77)}…`
  if (status === 'pending' || status === 'running') return `Ran ${cmd}`
  if (status === 'done' || status === 'applied') {
    if (exitCode != null && exitCode !== 0) return `Ran ${cmd} (exit ${exitCode})`
    return `Ran ${cmd}`
  }
  return `Ran ${cmd} (${status})`
}

function thoughtSummary(durationMs?: number, text?: string): string {
  if (durationMs != null && durationMs < 1000) return 'Thought briefly'
  if (durationMs != null) {
    const secs = Math.max(1, Math.round(durationMs / 1000))
    return `Thought ${secs}s`
  }
  if (text && text.trim()) return 'Thought'
  return 'Thought'
}

/** Short thoughts nest into Explored/Edited; long ones stay top-level. */
const NESTABLE_THOUGHT_MS = 5000

function isNestableThought(it: ActivityItem): boolean {
  if (it.kind !== 'thought') return false
  if (it.duration_ms == null) return true
  return it.duration_ms < NESTABLE_THOUGHT_MS
}

function itemSegmentKind(it: ActivityItem): SegmentKind {
  if (it.kind === 'thought') return 'thought'
  if (it.kind === 'note') return 'note'
  if (it.kind === 'explore') return 'explored'
  return 'edited'
}

function buildSegment(kind: SegmentKind, items: ActivityItem[]): ActivitySegment {
  const empty = {
    add_total: 0,
    del_total: 0,
    applied_file_count: 0,
    pending_file_count: 0,
    rejected_file_count: 0,
    command_count: 0,
    file_count: 0,
    search_count: 0,
  }
  if (kind === 'thought') {
    const it = items[0]
    return {
      kind: 'thought',
      summary: thoughtSummary(it.duration_ms, it.text),
      items: [...items],
      ...empty,
    }
  }
  if (kind === 'note') {
    return { kind: 'note', summary: items[0].summary, items: [...items], ...empty }
  }
  if (kind === 'explored') {
    const paths: string[] = []
    let searchCount = 0
    for (const it of items) {
      if (it.action === 'grep') searchCount += 1
      else if (it.path) paths.push(it.path)
      else if (it.action === 'list') paths.push(it.path || '.')
    }
    const fileCount = new Set(paths.filter(Boolean).map((p) => p.replace(/\\/g, '/'))).size
    const parts: string[] = []
    if (fileCount) parts.push(`${fileCount} file${fileCount !== 1 ? 's' : ''}`)
    if (searchCount) parts.push(`${searchCount} search${searchCount !== 1 ? 'es' : ''}`)
    if (!parts.length) {
      const exploreN = items.filter((x) => x.kind === 'explore').length
      const n = exploreN || items.length
      parts.push(`${n} step${n !== 1 ? 's' : ''}`)
    }
    return {
      kind: 'explored',
      summary: `Explored ${parts.join(', ')}`,
      items: [...items],
      ...empty,
      file_count: fileCount,
      search_count: searchCount,
    }
  }

  let applied = 0
  let pending = 0
  let rejected = 0
  let addTotal = 0
  let delTotal = 0
  let commands = 0
  for (const it of items) {
    if (it.kind === 'thought') continue
    if (it.kind === 'run') {
      commands += 1
      continue
    }
    if (it.kind !== 'edit') continue
    const st = (it.status || '').toLowerCase()
    if (APPLIED_EDIT_STATUSES.has(st)) {
      applied += 1
      addTotal += it.add_lines || 0
      delTotal += it.del_lines || 0
    } else if (st === 'pending') pending += 1
    else if (ERROR_STATUSES.has(st)) rejected += 1
    else pending += 1
  }
  const bits: string[] = []
  if (applied) bits.push(`Edited ${applied} file${applied !== 1 ? 's' : ''}`)
  if (pending) bits.push(`proposed ${pending}`)
  if (rejected && !applied && !pending) {
    bits.push(`Rejected ${rejected} file${rejected !== 1 ? 's' : ''}`)
  } else if (rejected) bits.push(`${rejected} rejected`)
  if (commands) bits.push(`ran ${commands} command${commands !== 1 ? 's' : ''}`)
  if (!bits.length) bits.push('Edited')
  let summary = bits[0]
  if (bits.length > 1) summary = `${bits[0]}, ${bits.slice(1).join(', ')}`
  if (applied && (addTotal || delTotal)) summary = `${summary}  +${addTotal} −${delTotal}`
  return {
    kind: 'edited',
    summary,
    items: [...items],
    add_total: addTotal,
    del_total: delTotal,
    applied_file_count: applied,
    pending_file_count: pending,
    rejected_file_count: rejected,
    command_count: commands,
    file_count: 0,
    search_count: 0,
  }
}

export function groupActivityItems(
  items: ActivityItem[],
  options?: { merge?: boolean },
): ActivitySegment[] {
  const merge = options?.merge !== false
  if (!merge) return items.map((it) => buildSegment(itemSegmentKind(it), [it]))

  const segments: ActivitySegment[] = []
  let buf: ActivityItem[] = []
  let bufKind: SegmentKind | null = null
  let leadingThoughts: ActivityItem[] = []

  const flushBuf = () => {
    if (!buf.length || !bufKind) {
      buf = []
      bufKind = null
      return
    }
    segments.push(buildSegment(bufKind, buf))
    buf = []
    bufKind = null
  }

  const flushLeadingAsTop = () => {
    for (const thought of leadingThoughts) {
      segments.push(buildSegment('thought', [thought]))
    }
    leadingThoughts = []
  }

  for (const it of items) {
    const sk = itemSegmentKind(it)
    if (sk === 'note') {
      flushBuf()
      flushLeadingAsTop()
      segments.push(buildSegment('note', [it]))
      continue
    }
    if (sk === 'thought') {
      if (isNestableThought(it)) {
        if (bufKind != null) buf.push(it)
        else leadingThoughts.push(it)
      } else {
        flushBuf()
        flushLeadingAsTop()
        segments.push(buildSegment('thought', [it]))
      }
      continue
    }
    if (!bufKind) {
      bufKind = sk
      buf = [...leadingThoughts, it]
      leadingThoughts = []
      continue
    }
    if (sk === bufKind) {
      buf.push(it)
      continue
    }
    flushBuf()
    bufKind = sk
    buf = [...leadingThoughts, it]
    leadingThoughts = []
  }
  flushBuf()
  flushLeadingAsTop()
  return segments
}

export class ActivityBuilder {
  items: ActivityItem[] = []
  private seq = 0
  private openExplore = new Map<string, number>()
  private editByPatch = new Map<string, number>()
  private runByShell = new Map<string, number>()
  private openThoughtIdx: number | null = null

  private nextId(prefix: string): string {
    this.seq += 1
    return `${prefix}-${this.seq}`
  }

  apply(event: ActivityEvent): void {
    if (!event || typeof event !== 'object') return
    const normalized = normalizeActivityEvent(event)
    const etype = String(normalized.type || '')
    if (etype === 'thought') this.applyThought(normalized)
    else if (etype === 'tool_start') this.applyToolStart(normalized)
    else if (etype === 'tool_result') this.applyToolResult(normalized)
    else if (etype === 'diff') this.applyDiff(normalized)
    else if (etype === 'shell') this.applyShell(normalized)
    else if (etype === 'edit_nudge' || etype === 'soft_land') {
      this.applyNote(normalized, etype)
    } else if (etype === 'memory') this.applyMemory(normalized)
  }

  applyMany(events: ActivityEvent[]): void {
    for (const ev of events) this.apply(ev)
  }

  segments(options?: { merge?: boolean }): ActivitySegment[] {
    return groupActivityItems(this.items, options)
  }

  snapshot(options?: { merge?: boolean }): TurnActivitySnapshot {
    const segs = this.segments(options)
    const applied = segs
      .filter((s) => s.kind === 'edited')
      .reduce((n, s) => n + s.applied_file_count, 0)
    const pending = segs
      .filter((s) => s.kind === 'edited')
      .reduce((n, s) => n + s.pending_file_count, 0)
    const addTotal = segs
      .filter((s) => s.kind === 'edited')
      .reduce((n, s) => n + s.add_total, 0)
    const delTotal = segs
      .filter((s) => s.kind === 'edited')
      .reduce((n, s) => n + s.del_total, 0)
    return {
      items: this.items.map((i) => ({ ...i })),
      segments: segs,
      stats: {
        applied_file_count: applied,
        pending_file_count: pending,
        add_total: addTotal,
        del_total: delTotal,
        has_thought: this.items.some((i) => i.kind === 'thought'),
      },
    }
  }

  private applyThought(event: ActivityEvent): void {
    const phase = String(event.phase || 'end').toLowerCase()
    const textS = event.text != null ? String(event.text) : ''
    let durationI: number | undefined
    if (event.duration_ms != null) {
      const n = Number(event.duration_ms)
      if (!Number.isNaN(n)) durationI = n
    }
    const sourceS = event.source != null ? String(event.source) : 'reasoning'
    const tsI = typeof event.ts === 'number' ? event.ts : undefined

    if (phase === 'start') {
      this.items.push({
        id: this.nextId('thought'),
        kind: 'thought',
        summary: thoughtSummary(undefined, undefined),
        text: '',
        source: sourceS,
        ts: tsI,
      })
      this.openThoughtIdx = this.items.length - 1
      return
    }

    if (phase === 'delta') {
      if (this.openThoughtIdx == null) {
        this.items.push({
          id: this.nextId('thought'),
          kind: 'thought',
          summary: thoughtSummary(undefined, textS),
          text: textS,
          source: sourceS,
          ts: tsI,
        })
        this.openThoughtIdx = this.items.length - 1
      } else {
        const cur = this.items[this.openThoughtIdx]
        cur.text = (cur.text || '') + textS
        cur.summary = thoughtSummary(cur.duration_ms, cur.text)
      }
      return
    }

    if (this.openThoughtIdx != null) {
      const cur = this.items[this.openThoughtIdx]
      if (textS && !(cur.text || '').trim()) cur.text = textS
      else if (textS && phase === 'end' && !(cur.text || '').endsWith(textS)) {
        cur.text = (cur.text || '') + textS
      }
      if (durationI != null) cur.duration_ms = durationI
      cur.summary = thoughtSummary(cur.duration_ms, cur.text)
      this.openThoughtIdx = null
      return
    }

    this.items.push({
      id: this.nextId('thought'),
      kind: 'thought',
      summary: thoughtSummary(durationI, textS),
      text: textS || undefined,
      duration_ms: durationI,
      source: sourceS,
      ts: tsI,
    })
  }

  private applyToolStart(event: ActivityEvent): void {
    const name = toolNameOf(event)
    if (classifyTool(name) !== 'explore') return
    const args = parseToolArguments(event)
    const action = exploreAction(name)
    const pathS = args.path != null ? String(args.path).trim() : undefined
    const queryRaw = args.query ?? args.pattern
    const queryS = queryRaw != null ? String(queryRaw).trim() : undefined
    const lines = lineRange(args)
    const callS = event.tool_call_id != null ? String(event.tool_call_id) : undefined
    this.items.push({
      id: this.nextId('explore'),
      kind: 'explore',
      summary: exploreSummary(action, pathS, queryS, lines),
      action,
      path: pathS,
      query: queryS,
      lines,
      status: 'running',
      tool_call_id: callS,
      ts: typeof event.ts === 'number' ? event.ts : undefined,
    })
    if (callS) this.openExplore.set(callS, this.items.length - 1)
  }

  private applyToolResult(event: ActivityEvent): void {
    const name = toolNameOf(event)
    const kind = classifyTool(name)
    const status = String(event.status || 'done')
    const callS = event.tool_call_id != null ? String(event.tool_call_id) : undefined

    if (kind === 'explore') {
      let idx: number | undefined
      if (callS && this.openExplore.has(callS)) {
        idx = this.openExplore.get(callS)
        this.openExplore.delete(callS)
      } else {
        for (let i = this.items.length - 1; i >= 0; i -= 1) {
          const it = this.items[i]
          if (
            it.kind === 'explore' &&
            it.status === 'running' &&
            (!callS || it.tool_call_id === callS)
          ) {
            idx = i
            break
          }
        }
      }
      if (idx != null) {
        this.items[idx].status = ERROR_STATUSES.has(status.toLowerCase()) ? 'error' : 'done'
      }
      return
    }

    if (kind === 'edit') {
      const parsed = toolResultPayload(event)
      const patchId = String(parsed.patch_id || '').trim()
      const pathS = parsed.path != null ? String(parsed.path) : undefined
      const st = String(parsed.status || status || 'done').toLowerCase()
      if (patchId && this.editByPatch.has(patchId)) {
        const it = this.items[this.editByPatch.get(patchId)!]
        it.status = st
        if (pathS) it.path = pathS
        it.summary = editSummary(it.path, st, it.add_lines || 0, it.del_lines || 0)
        return
      }
      if (patchId || pathS) {
        this.items.push({
          id: this.nextId('edit'),
          kind: 'edit',
          summary: editSummary(pathS, st, 0, 0),
          path: pathS,
          status: st,
          patch_id: patchId || undefined,
          add_lines: 0,
          del_lines: 0,
          tool_call_id: callS,
        })
        if (patchId) this.editByPatch.set(patchId, this.items.length - 1)
      }
      return
    }

    if (kind === 'run') {
      const parsed = toolResultPayload(event)
      const shellId = String(parsed.shell_id || '').trim()
      const commandS = parsed.command != null ? String(parsed.command) : undefined
      const st = String(parsed.status || status || 'done').toLowerCase()
      let exitI: number | undefined
      if (parsed.exit_code != null) {
        const n = Number(parsed.exit_code)
        if (!Number.isNaN(n)) exitI = n
      }
      if (shellId && this.runByShell.has(shellId)) {
        const it = this.items[this.runByShell.get(shellId)!]
        it.status = st
        if (commandS) it.command = commandS
        if (exitI != null) it.exit_code = exitI
        it.summary = runSummary(it.command, st, it.exit_code)
        return
      }
      if (shellId || commandS) {
        this.items.push({
          id: this.nextId('run'),
          kind: 'run',
          summary: runSummary(commandS, st, exitI),
          status: st,
          shell_id: shellId || undefined,
          command: commandS,
          exit_code: exitI,
          tool_call_id: callS,
        })
        if (shellId) this.runByShell.set(shellId, this.items.length - 1)
      }
      return
    }

    if (kind === 'note' && MEMORY_TOOLS.has(name)) {
      const parsed = toolResultPayload(event)
      const err = parsed.error != null ? String(parsed.error).trim() : ''
      const code = parsed.code != null ? String(parsed.code).trim().toUpperCase() : ''
      let preview = 'Memory update'
      if (code === 'DUPLICATE' || /duplicate/i.test(err)) {
        preview = 'Memory · already present (duplicate)'
      } else if (err) {
        preview = `Memory · ${err.slice(0, 160)}`
      } else if (event.summary != null) {
        preview = String(event.summary)
      }
      const st = String(parsed.status || status || 'done')
      this.items.push({
        id: this.nextId('note'),
        kind: 'note',
        summary: preview.slice(0, 200),
        note_type: 'propose_memory',
        status: st,
        tool_call_id: callS,
      })
    }
  }

  private applyDiff(event: ActivityEvent): void {
    const patchId = String(event.patch_id || '').trim()
    if (!patchId) return
    const pathS = event.path != null ? String(event.path) : undefined
    const status = String(event.status || 'pending').toLowerCase()
    let unified =
      event.unified_diff != null ? String(event.unified_diff) : null
    if (!unified) {
      const payload = parseJsonObj(event.full_ref)
      if (payload.unified_diff != null) unified = String(payload.unified_diff)
    }
    const [addN, delN] = countDiffLines(unified)
    if (this.editByPatch.has(patchId)) {
      const it = this.items[this.editByPatch.get(patchId)!]
      it.status = status
      it.path = pathS || it.path
      it.add_lines = addN
      it.del_lines = delN
      it.summary = editSummary(it.path, status, addN, delN)
      return
    }
    this.items.push({
      id: this.nextId('edit'),
      kind: 'edit',
      summary: editSummary(pathS, status, addN, delN),
      path: pathS,
      status,
      patch_id: patchId,
      add_lines: addN,
      del_lines: delN,
      ts: typeof event.ts === 'number' ? event.ts : undefined,
    })
    this.editByPatch.set(patchId, this.items.length - 1)
  }

  private applyShell(event: ActivityEvent): void {
    const shellId = String(event.shell_id || event.id || '').trim()
    if (!shellId) return
    let commandS =
      event.command != null ? String(event.command) : undefined
    if (!commandS && Array.isArray(event.argv)) {
      commandS = event.argv.map(String).join(' ')
    }
    const status = String(event.status || 'pending').toLowerCase()
    let exitI: number | undefined
    if (event.exit_code != null) {
      const n = Number(event.exit_code)
      if (!Number.isNaN(n)) exitI = n
    }
    if (this.runByShell.has(shellId)) {
      const it = this.items[this.runByShell.get(shellId)!]
      it.status = status
      it.command = commandS || it.command
      it.exit_code = exitI ?? it.exit_code
      it.summary = runSummary(it.command, status, it.exit_code)
      return
    }
    this.items.push({
      id: this.nextId('run'),
      kind: 'run',
      summary: runSummary(commandS, status, exitI),
      status,
      shell_id: shellId,
      command: commandS,
      exit_code: exitI,
      ts: typeof event.ts === 'number' ? event.ts : undefined,
    })
    this.runByShell.set(shellId, this.items.length - 1)
  }

  private applyNote(event: ActivityEvent, noteType: string): void {
    let summary =
      noteType === 'edit_nudge'
        ? '催促提出文件修改（edit_nudge）'
        : noteType === 'soft_land'
          ? '工具轮次触顶软着陆'
          : noteType
    const reason = event.reason ?? event.summary
    if (reason) summary = `${summary} · ${String(reason)}`
    this.items.push({
      id: this.nextId('note'),
      kind: 'note',
      summary: summary.slice(0, 240),
      note_type: noteType,
      ts: typeof event.ts === 'number' ? event.ts : undefined,
    })
  }

  private applyMemory(event: ActivityEvent): void {
    const status = String(event.status || 'pending')
    const target = event.target != null ? String(event.target) : 'memory'
    this.items.push({
      id: this.nextId('note'),
      kind: 'note',
      summary: `Memory (${target}) ${status}`,
      note_type: 'propose_memory',
      status,
    })
  }
}

export function buildTurnActivity(
  events: ActivityEvent[],
  options?: { merge?: boolean },
): TurnActivitySnapshot {
  const builder = new ActivityBuilder()
  builder.applyMany(events)
  return builder.snapshot(options)
}

/** Append one SSE/activity event and rebuild the snapshot. */
export function appendActivityEvent(
  events: ActivityEvent[] | undefined,
  event: ActivityEvent,
): { activityEvents: ActivityEvent[]; activity: TurnActivitySnapshot } {
  const activityEvents = [...(events || []), event]
  return {
    activityEvents,
    activity: buildTurnActivity(activityEvents),
  }
}

/** Append an activity event onto a message pair and rebuild the snapshot. */
export function pairWithActivityEvent(
  pair: {
    activityEvents?: ActivityEvent[]
    activityStartedAt?: number
  },
  event: ActivityEvent,
  extras?: Record<string, unknown>,
): {
  activityEvents: ActivityEvent[]
  activity: TurnActivitySnapshot
  activityStartedAt: number
} & Record<string, unknown> {
  const { activityEvents, activity } = appendActivityEvent(pair.activityEvents, event)
  return {
    ...extras,
    activityEvents,
    activity,
    activityStartedAt: pair.activityStartedAt ?? Date.now(),
  }
}

/** Map persisted assistant.trace rows into activity events. */
export function activityEventsFromTrace(
  trace: Array<Record<string, unknown>> | undefined | null,
): ActivityEvent[] {
  if (!trace || !trace.length) return []
  const out: ActivityEvent[] = []
  for (const raw of trace) {
    if (!raw || typeof raw !== 'object') continue
    const type = String(raw.type || '')
    if (
      type === 'tool_start' ||
      type === 'tool_result' ||
      type === 'thought' ||
      type === 'diff' ||
      type === 'shell' ||
      type === 'memory' ||
      type === 'gate' ||
      type === 'edit_nudge' ||
      type === 'soft_land'
    ) {
      out.push(normalizeActivityEvent({ ...raw }))
    }
  }
  return out
}

/** Prefer the snapshot that still has edit/run facts after a reload race. */
export function pickRicherActivity(
  a?: TurnActivitySnapshot | null,
  b?: TurnActivitySnapshot | null,
): TurnActivitySnapshot | undefined {
  if (!a) return b || undefined
  if (!b) return a
  const score = (s: TurnActivitySnapshot) =>
    (s.stats.applied_file_count || 0) * 10 +
    (s.stats.pending_file_count || 0) * 3 +
    s.items.filter((i) => i.kind === 'run').length * 5 +
    s.items.filter((i) => i.kind === 'edit').length * 4 +
    s.items.filter((i) => i.kind === 'explore').length +
    (s.stats.has_thought ? 1 : 0)
  return score(a) >= score(b) ? a : b
}
