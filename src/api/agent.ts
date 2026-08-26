const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  workspace_root?: string | null
}

export interface CreateSessionRequest {
  title: string
  workspace_root?: string | null
}

export interface MessageRequest {
  content: string
}

export interface HealthStatus {
  status: string
  provider: string
  provider_available: boolean
}

export interface AttachmentMeta {
  id: string
  filename: string
  size: number
  content_type?: string | null
  url: string
}

export interface ApiMessage {
  id: string
  role: string
  content: string
  sequence: number
  is_favorite: boolean
  summary?: string
  trace?: Array<Record<string, unknown>>
  attachments?: AttachmentMeta[]
  created_at: string
}

export interface TurnMeta {
  model: string
  elapsed_ms: number
  approx_prompt_tokens: number
  approx_completion_tokens: number
  compressed: boolean
  memory_injected: boolean
  message_id: string
  goal?: string
}

export interface FavoriteItem {
  id: string
  session_id: string
  session_title: string
  user_content: string
  assistant_content: string
  created_at: string
}

export interface StreamEvent {
  type: string
  content?: string
  message_id?: string
  assistant_message_id?: string
  code?: string
  message?: string
  name?: string
  arguments?: string
  tool_call_id?: string
  patch_id?: string
  path?: string
  unified_diff?: string
  is_new_file?: boolean
  is_delete?: boolean
  status?: string
  error?: string
  kind?: string
  shell_id?: string
  argv?: string[]
  cwd?: string
  command?: string
  exit_code?: number | null
  stdout?: string
  stderr?: string
  truncated?: boolean
  full_ref?: string
  summary?: string
  memory_id?: string
  mode?: string
  preview?: string
  model?: string
  elapsed_ms?: number
  approx_prompt_tokens?: number
  approx_completion_tokens?: number
  compressed?: boolean
  memory_injected?: boolean
  goal?: string
  previous_goal?: string
  tools_since_last?: number
  reason?: string
  reply?: string
  settled?: boolean
}

export interface AgentSettings {
  auto_compress: boolean
  confirm_memory: boolean
  context_limit: number
  active_skills: string[]
  approval_timeout_sec: number
  disabled_tools: string[]
  max_tool_iters: number
  checkpoint_every_n_tools: number
}

export interface MemoryProposal {
  id: string
  mode: string
  preview: string
  content: string
  status: string
  error?: string | null
}

export interface AuditEvent {
  id: string
  session_id?: string | null
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

export interface AssetsStatus {
  status: string
  provider: string
  provider_available: boolean
  session_count: number
  user_md_exists: boolean
  user_md_path: string
  user_md_size: number
  workspace_configured: boolean
  workspace_root?: string | null
  settings: AgentSettings
}

export interface WorkspaceStatus {
  configured: boolean
  root: string | null
  name: string | null
}

export interface WorkspaceBrowse {
  path: string
  parent: string | null
  directories: { name: string; path: string }[]
}

function formatApiError(status: number, body: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown }
    const detail = parsed.detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const msg = (detail as { message?: unknown }).message
      if (typeof msg === 'string' && msg.trim()) return msg
    }
  } catch {
    // ignore
  }
  if (status === 409) return '该会话正在处理中，请稍候或先停止当前回复'
  return body || `Request failed: ${status}`
}

async function apiFetch(input: string, init?: RequestInit) {
  const response = await fetch(`${API_BASE_URL}${input}`, init)
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(formatApiError(response.status, detail))
  }
  return response
}

export async function fetchHealth(): Promise<HealthStatus> {
  const response = await apiFetch('/health')
  return response.json()
}

export interface ModelInfo {
  id: string
}

export interface ModelsResponse {
  models: ModelInfo[]
  default: string
  source: string
}

export async function fetchModels(): Promise<ModelsResponse> {
  const response = await apiFetch('/api/models')
  return response.json()
}

export async function createSession(
  title: string,
  workspaceRoot?: string | null,
): Promise<Session> {
  const response = await apiFetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, workspace_root: workspaceRoot ?? null }),
  })
  return response.json()
}

export async function listSessions(): Promise<Session[]> {
  const response = await apiFetch('/api/sessions')
  return response.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
}

export async function getMessages(sessionId: string): Promise<ApiMessage[]> {
  const response = await apiFetch(`/api/sessions/${sessionId}/messages`)
  return response.json()
}

/** Fetch oversized tool payload spilled under session.data_path (file: ref). */
export async function getSessionBlob(sessionId: string, fileRef: string): Promise<string> {
  const qs = new URLSearchParams({ ref: fileRef })
  const response = await apiFetch(`/api/sessions/${sessionId}/blobs?${qs.toString()}`)
  return response.text()
}

export async function updateSessionTitle(sessionId: string, title: string): Promise<Session> {
  const response = await apiFetch(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return response.json()
}

export async function toggleMessageFavorite(messageId: string, isFavorite: boolean): Promise<ApiMessage> {
  const response = await apiFetch(`/api/messages/${messageId}/favorite`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_favorite: isFavorite }),
  })
  return response.json()
}

export async function listFavorites(): Promise<FavoriteItem[]> {
  const response = await apiFetch('/api/favorites')
  return response.json()
}

export async function fetchWorkspace(): Promise<WorkspaceStatus> {
  const response = await apiFetch('/api/workspace')
  return response.json()
}

export async function setWorkspace(root: string): Promise<WorkspaceStatus> {
  const response = await apiFetch('/api/workspace', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ root }),
  })
  return response.json()
}

export async function clearWorkspace(): Promise<WorkspaceStatus> {
  const response = await apiFetch('/api/workspace', { method: 'DELETE' })
  return response.json()
}

export async function browseWorkspace(path?: string): Promise<WorkspaceBrowse> {
  const qs = path ? `?path=${encodeURIComponent(path)}` : ''
  const response = await apiFetch(`/api/workspace/browse${qs}`)
  return response.json()
}

export interface PatchResponse {
  id: string
  path: string
  unified_diff: string
  is_new_file: boolean
  is_delete?: boolean
  status: string
  error?: string | null
  hunk_count?: number | null
  applied_hunks?: number[] | null
}

export async function listPatches(): Promise<PatchResponse[]> {
  const response = await apiFetch('/api/workspace/patches')
  return response.json()
}

export async function applyPatch(patchId: string): Promise<PatchResponse> {
  const response = await apiFetch(`/api/workspace/patches/${patchId}/apply`, { method: 'POST' })
  return response.json()
}

export async function applyPatchPartial(patchId: string, hunkIds: number[]): Promise<PatchResponse> {
  const response = await apiFetch(`/api/workspace/patches/${patchId}/apply-partial`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hunk_ids: hunkIds }),
  })
  return response.json()
}

export async function rejectPatch(patchId: string): Promise<PatchResponse> {
  const response = await apiFetch(`/api/workspace/patches/${patchId}/reject`, { method: 'POST' })
  return response.json()
}

export async function retryPatch(patchId: string): Promise<PatchResponse> {
  const response = await apiFetch(`/api/workspace/patches/${patchId}/retry`, { method: 'POST' })
  return response.json()
}

export interface ShellResponse {
  id: string
  argv: string[]
  cwd: string
  command: string
  status: string
  exit_code?: number | null
  stdout?: string
  stderr?: string
  truncated?: boolean
  error?: string | null
}

export async function listShells(): Promise<ShellResponse[]> {
  const response = await apiFetch('/api/workspace/shells')
  return response.json()
}

export async function applyShell(shellId: string): Promise<ShellResponse> {
  const response = await apiFetch(`/api/workspace/shells/${shellId}/apply`, { method: 'POST' })
  return response.json()
}

export async function rejectShell(shellId: string): Promise<ShellResponse> {
  const response = await apiFetch(`/api/workspace/shells/${shellId}/reject`, { method: 'POST' })
  return response.json()
}

export async function retryShell(shellId: string): Promise<ShellResponse> {
  const response = await apiFetch(`/api/workspace/shells/${shellId}/retry`, { method: 'POST' })
  return response.json()
}

export async function fetchAgentSettings(): Promise<AgentSettings> {
  const response = await apiFetch('/api/settings')
  return response.json()
}

export async function updateAgentSettings(
  patch: Partial<AgentSettings>,
): Promise<AgentSettings> {
  const response = await apiFetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return response.json()
}

export interface LlmConfig {
  api_key_configured: boolean
  base_url: string
  default_model: string
  temperature: number
  max_tokens: number
}

export async function fetchLlmConfig(): Promise<LlmConfig> {
  const response = await apiFetch('/api/llm-config')
  return response.json()
}

export async function updateLlmConfig(patch: {
  api_key?: string
  base_url?: string
  default_model?: string
  temperature?: number
  max_tokens?: number
}): Promise<LlmConfig> {
  const response = await apiFetch('/api/llm-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return response.json()
}

export interface LlmTestResult {
  ok: boolean
  latency_ms?: number | null
  model_count?: number | null
  error?: string | null
}

export async function testLlmConnection(): Promise<LlmTestResult> {
  const response = await apiFetch('/api/llm-config/test', { method: 'POST' })
  return response.json()
}

export interface ToolInfo {
  name: string
  description: string
}

export interface ToolsResponse {
  tools: ToolInfo[]
  disabled_tools: string[]
}

export async function fetchTools(): Promise<ToolsResponse> {
  const response = await apiFetch('/api/tools')
  return response.json()
}

export interface MemoryContent {
  content: string
  path: string
}

export async function fetchMemoryContent(): Promise<MemoryContent> {
  const response = await apiFetch('/api/memory/content')
  return response.json()
}

export async function updateMemoryContent(content: string): Promise<MemoryContent> {
  const response = await apiFetch('/api/memory/content', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  return response.json()
}

export async function listMemoryProposals(): Promise<MemoryProposal[]> {
  const response = await apiFetch('/api/memory/proposals')
  return response.json()
}

export async function applyMemory(proposalId: string): Promise<MemoryProposal> {
  const response = await apiFetch(`/api/memory/proposals/${proposalId}/apply`, { method: 'POST' })
  return response.json()
}

export async function rejectMemory(proposalId: string): Promise<MemoryProposal> {
  const response = await apiFetch(`/api/memory/proposals/${proposalId}/reject`, { method: 'POST' })
  return response.json()
}

export interface SkillInfo {
  id: string
  name: string
  path: string
  preview: string
  description?: string
}

export interface SkillsResponse {
  workspace_configured: boolean
  workspace_root?: string | null
  skills: SkillInfo[]
  active_skills: string[]
  agents_md_exists: boolean
}

export async function fetchSkills(): Promise<SkillsResponse> {
  const response = await apiFetch('/api/skills')
  return response.json()
}

export async function updateActiveSkills(skillIds: string[]): Promise<SkillsResponse> {
  const response = await apiFetch('/api/skills/active', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active_skills: skillIds }),
  })
  return response.json()
}

export async function fetchAudit(
  limit = 50,
  sessionId?: string | null,
  eventType?: string | null,
): Promise<AuditEvent[]> {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (sessionId) qs.set('session_id', sessionId)
  if (eventType) qs.set('event_type', eventType)
  const response = await apiFetch(`/api/audit?${qs.toString()}`)
  return response.json()
}

export interface AuditSessionSummary {
  session_id: string
  event_count: number
  last_at: string | null
}

export async function fetchAuditSessions(limit = 50): Promise<AuditSessionSummary[]> {
  const response = await apiFetch(`/api/audit/sessions?limit=${limit}`)
  return response.json()
}

export async function fetchSessionAudit(
  sessionId: string,
  limit = 100,
  eventType?: string | null,
): Promise<AuditEvent[]> {
  const qs = new URLSearchParams({ limit: String(limit) })
  if (eventType) qs.set('event_type', eventType)
  const response = await apiFetch(`/api/sessions/${sessionId}/audit?${qs.toString()}`)
  return response.json()
}

export async function emitAudit(
  eventType: string,
  payload?: Record<string, unknown>,
  sessionId?: string,
): Promise<AuditEvent> {
  const response = await apiFetch('/api/audit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type: eventType,
      payload: payload || {},
      session_id: sessionId,
    }),
  })
  return response.json()
}

export async function fetchAssets(): Promise<AssetsStatus> {
  const response = await apiFetch('/api/assets')
  return response.json()
}

export interface RuntimeInfo {
  boot_id: string
  started_at: number
  active_sessions: string[]
}

export async function fetchRuntime(): Promise<RuntimeInfo> {
  const response = await apiFetch('/api/runtime')
  return response.json()
}

export async function cancelSession(sessionId: string): Promise<{ ok: boolean; cancelled: boolean }> {
  const response = await apiFetch(`/api/sessions/${sessionId}/cancel`, { method: 'POST' })
  return response.json()
}


export function attachmentDownloadUrl(sessionId: string, attachmentId: string): string {
  return `${API_BASE_URL}/api/sessions/${sessionId}/attachments/${attachmentId}`
}

export async function uploadAttachment(sessionId: string, file: File): Promise<AttachmentMeta> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiFetch(`/api/sessions/${sessionId}/attachments`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(formatApiError(response.status, detail))
  }
  return response.json()
}

export function sendMessageStream(
  sessionId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
  onError: (error: Error) => void,
  model?: string,
  attachmentIds?: string[],
): () => void {
  return startSseStream(
    `/api/sessions/${sessionId}/messages`,
    {
      content,
      ...(model ? { model } : {}),
      ...(attachmentIds && attachmentIds.length ? { attachment_ids: attachmentIds } : {}),
    },
    onEvent,
    onError,
    sessionId,
  )
}

export function regenerateStream(
  sessionId: string,
  onEvent: (event: StreamEvent) => void,
  onError: (error: Error) => void,
  model?: string,
): () => void {
  return startSseStream(
    `/api/sessions/${sessionId}/regenerate`,
    { ...(model ? { model } : {}) },
    onEvent,
    onError,
    sessionId,
  )
}

function startSseStream(
  path: string,
  body: Record<string, unknown>,
  onEvent: (event: StreamEvent) => void,
  onError: (error: Error) => void,
  sessionId?: string,
): () => void {
  const controller = new AbortController()

  const start = async () => {
    let gotTerminal = false
    try {
      const response = await fetch(`${API_BASE_URL}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      })

      if (!response.ok) {
        const detail = await response.text().catch(() => '')
        throw new Error(formatApiError(response.status, detail))
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('Response body not available')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        let index = 0
        while (true) {
          const eventEnd = buffer.indexOf('\n\n', index)
          if (eventEnd === -1) break

          const eventBlock = buffer.slice(index, eventEnd)
          index = eventEnd + 2

          const lines = eventBlock.split('\n')
          let currentEventType = ''
          let eventData = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6).trim()
            }
          }

          if (currentEventType && eventData) {
            try {
              const parsed = JSON.parse(eventData)
              const evt = { type: currentEventType, ...parsed }
              if (currentEventType === 'done' || currentEventType === 'error') {
                gotTerminal = true
              }
              onEvent(evt)
            } catch {
              onEvent({ type: currentEventType, content: eventData })
            }
          }
        }

        buffer = buffer.slice(index)
      }
      if (!gotTerminal && !controller.signal.aborted) {
        onEvent({ type: 'stream_end' })
      }
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        onError(error as Error)
      } else if (!gotTerminal) {
        onEvent({ type: 'stream_end' })
      }
    }
  }

  start()
  return () => {
    // Prefer cancel before abort so the agent loop can exit wait_for_* cleanly.
    if (sessionId) {
      void cancelSession(sessionId)
    }
    controller.abort()
  }
}

export { API_BASE_URL }

