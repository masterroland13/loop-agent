export type Role = 'user' | 'assistant'

export interface Message {
  id: string
  role: Role
  content: string
  createdAt: number
}

export interface ToolTraceItem {
  name: string
  status: 'running' | 'done' | 'error'
  detail?: string
}

export interface PendingPatch {
  id: string
  path: string
  unified_diff: string
  is_new_file: boolean
  status: 'pending' | 'applied' | 'rejected' | 'timeout' | 'failed' | 'cancelled'
  error?: string
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
  /** Per-turn meta from SSE (not persisted). */
  turnMeta?: TurnMeta
}
