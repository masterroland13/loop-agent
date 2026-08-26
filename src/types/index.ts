export type Role = 'user' | 'assistant'

export interface AttachmentMeta {
  id: string
  filename: string
  size: number
  content_type?: string | null
  url: string
}

export interface Message {
  id: string
  role: Role
  content: string
  createdAt: number
  attachments?: AttachmentMeta[]
}

export interface ToolTraceItem {
  name: string
  status: 'running' | 'done' | 'error'
  detail?: string
  /** file:turns/... spilled under session.data_path when payload > 8KB */
  fullRef?: string
  truncated?: boolean
}

export interface PendingPatch {
  id: string
  path: string
  unified_diff: string
  is_new_file: boolean
  is_delete?: boolean
  status: 'pending' | 'applied' | 'rejected' | 'timeout' | 'failed' | 'cancelled' | 'partial'
  error?: string
  hunk_count?: number
  applied_hunks?: number[]
}

export interface PendingShell {
  id: string
  argv: string[]
  cwd: string
  command: string
  status: 'pending' | 'running' | 'done' | 'rejected' | 'timeout' | 'failed' | 'cancelled'
  exit_code?: number | null
  stdout?: string
  stderr?: string
  truncated?: boolean
  error?: string
}

export interface PendingMemory {
  id: string
  mode: string
  preview: string
  content: string
  status: 'pending' | 'applied' | 'rejected' | 'timeout' | 'failed' | 'cancelled'
  error?: string
}

export interface TurnMeta {
  type?: 'turn_meta'
  model: string
  elapsed_ms: number
  approx_prompt_tokens: number
  approx_completion_tokens: number
  compressed: boolean
  memory_injected: boolean
  message_id: string
  /** Sticky turn goal injected into the agent loop. */
  goal?: string
}

export interface MessagePair {
  id: string
  user: Message
  assistant: Message
  isFavorite: boolean
  /** Live tool activity for the current turn (not persisted). */
  toolTrace?: ToolTraceItem[]
  /** Last turn failed (stream error); enables retry. */
  failed?: boolean
  /** Per-turn meta from SSE / assistant.summary. */
  turnMeta?: TurnMeta
  /** Live goal from meta/turn_goal before turn_meta arrives. */
  goal?: string
  /** Prior sticky goal when this turn changed intent (F8). */
  previousGoal?: string
  /** Latest progress checkpoint hint (interval or after gate). */
  progressCheckpoint?: {
    toolsSinceLast: number
    reason: string
    reply?: string
    /** True when model skipped mid-loop narration (or turn settled without reply). */
    settled?: boolean
  }
  /** True when assistant row exists but turn_meta not finalized (refresh recovery). */
  turnInProgress?: boolean
}

