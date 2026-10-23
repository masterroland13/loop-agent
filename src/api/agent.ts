import { translate, type Locale } from '../i18n'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

let apiErrorLocale: Locale = 'zh'

/** Sync UI language so HTTP error fallbacks match the active locale. */
export function setApiErrorLocale(locale: Locale) {
  apiErrorLocale = locale
}

export function getApiErrorLocale(): Locale {
  return apiErrorLocale
}

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  workspace_root?: string | null
  goal_mode?: boolean
  pinned_goal?: string | null
  leaf_id?: string | null
  profile_id?: string | null
  model_id?: string | null
  title_locked?: boolean
  /** Time of the latest user instruction. Replies do not move this. */
  last_prompt_at?: string | null
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
  parent_id?: string | null
  entry_type?: string
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
  target?: string
  op_summary?: string
  model?: string
  elapsed_ms?: number
  approx_prompt_tokens?: number
  approx_completion_tokens?: number
  compressed?: boolean
  memory_injected?: boolean
  goal?: string
  model_fallback?: boolean
  profile_id?: string | null
  previous_goal?: string
  tools_since_last?: number
  reason?: string
  reply?: string
  settled?: boolean
  max_tool_iters?: number
  tools_ran?: number
  /** S1 Thought channel */
  phase?: string
  text?: string
  duration_ms?: number
  source?: string
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
  exploration_repeat_threshold: number
  loop_preset: 'yolo' | 'trusted' | 'strict'
  user_md_char_limit?: number
  memory_md_char_limit?: number
}

export interface MemoryProposal {
  id: string
  mode: string
  preview: string
  content: string
  target?: 'user' | 'memory'
  status: string
  error?: string | null
  op_summary?: string
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
  memory_md_exists?: boolean
  memory_md_path?: string
  memory_md_size?: number
  user_md_chars?: number
  user_md_limit?: number
  memory_md_chars?: number
  memory_md_limit?: number
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
    if (Array.isArray(detail) && detail.length > 0) {
      const parts = detail
        .map((item) => {
          if (!item || typeof item !== 'object') return null
          const msg = (item as { msg?: unknown }).msg
          return typeof msg === 'string' ? msg : null
        })
        .filter((m): m is string => Boolean(m))
      if (parts.length > 0) {
        return parts
          .map((m) => m.replace(/^Value error,\s*/i, ''))
          .join('; ')
      }
    }
    if (detail && typeof detail === 'object' && 'message' in detail) {
      const msg = (detail as { message?: unknown }).message
      if (typeof msg === 'string' && msg.trim()) return msg
    }
  } catch {
    // ignore
  }
  if (status === 409) return translate(apiErrorLocale, 'errors.sessionBusy')
  if (status === 400) return translate(apiErrorLocale, 'errors.invalidRequest')
  return (
    body.slice(0, 160) ||
    translate(apiErrorLocale, 'errors.requestFailedWithStatus', { status })
  )
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

export async function getSession(sessionId: string): Promise<Session> {
  const response = await apiFetch(`/api/sessions/${sessionId}`)
  return response.json()
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch(`/api/sessions/${sessionId}`, { method: 'DELETE' })
}

export async function getMessages(
  sessionId: string,
  opts?: { view?: 'all' | 'active' },
): Promise<ApiMessage[]> {
  const view = opts?.view ?? 'all'
  const qs = view === 'all' ? '' : `?view=${encodeURIComponent(view)}`
  const response = await apiFetch(`/api/sessions/${sessionId}/messages${qs}`)
  return response.json()
}

export async function updateSessionTitle(
  sessionId: string,
  title: string,
  titleLocked = false,
): Promise<Session> {
  const response = await apiFetch(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(titleLocked ? { title, title_locked: true } : { title }),
  })
  return response.json()
}

export async function updateSessionGoalMode(
  sessionId: string,
  goalMode: boolean,
): Promise<Session> {
  const response = await apiFetch(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal_mode: goalMode }),
  })
  return response.json()
}

export async function updateSessionModel(
  sessionId: string,
  patch: { model_id?: string | null; profile_id?: string | null },
): Promise<Session> {
  const response = await apiFetch(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return response.json()
}

export interface ProviderPreset {
  id: string
  label: string
  base_url: string
  model_id: string
  inherit_base_url: boolean
}

export async function fetchProviderPresets(): Promise<ProviderPreset[]> {
  const response = await apiFetch('/api/model-profile-presets')
  return response.json()
}

export async function updateSessionPinnedGoal(
  sessionId: string,
  pinnedGoal: string | null,
): Promise<Session> {
  const response = await apiFetch(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pinned_goal: pinnedGoal }),
  })
  return response.json()
}

export async function updateSessionWorkspaceRoot(
  sessionId: string,
  workspaceRoot: string,
): Promise<Session> {
  const response = await apiFetch(`/api/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_root: workspaceRoot }),
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

export async function createWorkspaceFolder(parent: string, name: string): Promise<{ path: string }> {
  const response = await apiFetch('/api/workspace/mkdir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent, name }),
  })
  return response.json()
}

export interface WorkspaceFileEntry {
  name: string
  path: string
  type: 'file' | 'dir' | string
  size?: number | null
}

export interface WorkspaceFilesList {
  path: string
  entries: WorkspaceFileEntry[]
  truncated: boolean
}

export type WorkspaceFileEncoding = 'utf-8' | 'docx-html'

export interface WorkspaceFileRead {
  path: string
  content: string
  /** Decimal string — JSON numbers cannot represent ns timestamps in JS. */
  mtime_ns: string
  size: number
  encoding: WorkspaceFileEncoding
}

export interface WorkspaceFileWriteResult {
  path: string
  mtime_ns: string
  size: number
}

export async function listWorkspaceFiles(path = '.'): Promise<WorkspaceFilesList> {
  const qs = `?path=${encodeURIComponent(path)}`
  const response = await apiFetch(`/api/workspace/files/list${qs}`)
  return response.json()
}

export async function readWorkspaceFile(path: string): Promise<WorkspaceFileRead> {
  const qs = `?path=${encodeURIComponent(path)}`
  const response = await apiFetch(`/api/workspace/files/read${qs}`)
  return response.json()
}

export async function writeWorkspaceFile(
  path: string,
  content: string,
  ifMatchMtimeNs?: string | null,
  ifMatchBaseContent?: string | null,
  encoding: WorkspaceFileEncoding = 'utf-8',
): Promise<WorkspaceFileWriteResult> {
  const response = await apiFetch('/api/workspace/files/write', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      path,
      content,
      if_match_mtime_ns: ifMatchMtimeNs ?? null,
      if_match_base_content: ifMatchBaseContent ?? null,
      encoding,
    }),
  })
  return response.json()
}

export async function mkdirWorkspaceDirectory(path: string): Promise<{ path: string }> {
  const response = await apiFetch('/api/workspace/files/mkdir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return response.json()
}

export async function renameWorkspaceEntry(
  fromPath: string,
  toPath: string,
): Promise<{ from: string; path: string }> {
  const response = await apiFetch('/api/workspace/files/rename', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: fromPath, to: toPath }),
  })
  return response.json()
}

export async function deleteWorkspaceEntry(
  path: string,
  recursive = false,
): Promise<{ path: string; recursive: boolean }> {
  const qs = `?path=${encodeURIComponent(path)}&recursive=${recursive ? 'true' : 'false'}`
  const response = await apiFetch(`/api/workspace/files/delete${qs}`, { method: 'DELETE' })
  return response.json()
}

export async function copyWorkspaceEntry(
  fromPath: string,
  toPath: string,
): Promise<{ from: string; path: string }> {
  const response = await apiFetch('/api/workspace/files/copy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: fromPath, to: toPath }),
  })
  return response.json()
}

export async function fetchWorkspaceTreeStats(
  path: string,
): Promise<{ path: string; file_count: number; dir_count: number }> {
  const qs = `?path=${encodeURIComponent(path)}`
  const response = await apiFetch(`/api/workspace/files/stats${qs}`)
  return response.json()
}

export async function revealWorkspaceEntry(path: string): Promise<{ path: string; revealed: string }> {
  const response = await apiFetch('/api/workspace/files/reveal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
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
  session_id?: string | null
}

export async function listPatches(sessionId?: string | null): Promise<PatchResponse[]> {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  const response = await apiFetch(`/api/workspace/patches${qs}`)
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
  session_id?: string | null
}

export async function listShells(sessionId?: string | null): Promise<ShellResponse[]> {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  const response = await apiFetch(`/api/workspace/shells${qs}`)
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
  sessionId?: string,
): Promise<AgentSettings> {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  const response = await apiFetch(`/api/settings${qs}`, {
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

export interface ModelProfile {
  id: string
  label: string
  enabled: boolean
  base_url: string
  model_id: string
  api: string
  api_key_configured: boolean
  supports_reasoning?: boolean
  reasoning_mode?: string
}

export interface ModelProfilesList {
  active_id: string
  temperature: number
  max_tokens: number
  profiles: ModelProfile[]
}

export async function fetchModelProfiles(): Promise<ModelProfilesList> {
  const response = await apiFetch('/api/model-profiles')
  return response.json()
}

export async function createModelProfile(body: {
  label?: string
  base_url?: string
  api_key?: string
  model_id?: string
  enabled?: boolean
  activate?: boolean
}): Promise<ModelProfile> {
  const response = await apiFetch('/api/model-profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return response.json()
}

export async function updateModelProfile(
  id: string,
  patch: {
    label?: string
    base_url?: string
    api_key?: string
    model_id?: string
    enabled?: boolean
    temperature?: number
    max_tokens?: number
    supports_reasoning?: boolean
    reasoning_mode?: string
  },
): Promise<ModelProfilesList> {
  const response = await apiFetch(`/api/model-profiles/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return response.json()
}

export async function deleteModelProfile(id: string): Promise<ModelProfilesList> {
  const response = await apiFetch(`/api/model-profiles/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
  return response.json()
}

export async function activateModelProfile(id: string): Promise<ModelProfilesList> {
  const response = await apiFetch(`/api/model-profiles/${encodeURIComponent(id)}/activate`, {
    method: 'POST',
  })
  return response.json()
}

export async function updateModelGlobals(patch: {
  temperature?: number
  max_tokens?: number
}): Promise<ModelProfilesList> {
  const response = await apiFetch('/api/model-profiles/globals', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return response.json()
}

export async function testModelProfile(id: string): Promise<LlmTestResult> {
  const response = await apiFetch(`/api/model-profiles/${encodeURIComponent(id)}/test`, {
    method: 'POST',
  })
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
  target?: 'user' | 'memory'
  chars?: number
  limit?: number
}

export async function fetchMemoryContent(target: 'user' | 'memory' = 'user'): Promise<MemoryContent> {
  const response = await apiFetch(`/api/memory/tracks/${encodeURIComponent(target)}/content`)
  const data = (await response.json()) as MemoryContent
  const expected = target === 'memory' ? 'MEMORY.md' : 'USER.md'
  const path = (data.path || '').replace(/\\/g, '/')
  if (data.target && data.target !== target) {
    throw new Error(`记忆轨错位：请求 ${target}，响应 target=${data.target}`)
  }
  if (!path.endsWith(expected)) {
    throw new Error(`记忆路径错位：请求 ${target}，得到 ${data.path || '(empty)'}（后端可能未重启）`)
  }
  return data
}

export async function updateMemoryContent(
  content: string,
  target: 'user' | 'memory' = 'user',
): Promise<MemoryContent> {
  const response = await apiFetch(`/api/memory/tracks/${encodeURIComponent(target)}/content`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, target }),
  })
  const data = (await response.json()) as MemoryContent
  const expected = target === 'memory' ? 'MEMORY.md' : 'USER.md'
  const path = (data.path || '').replace(/\\/g, '/')
  if (!path.endsWith(expected)) {
    throw new Error(`保存后路径错位：期望 ${expected}，得到 ${data.path || '(empty)'}（后端可能未重启）`)
  }
  return data
}

export async function listMemoryProposals(sessionId?: string | null): Promise<MemoryProposal[]> {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  const response = await apiFetch(`/api/memory/proposals${qs}`)
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
  /** Session this stream belongs to (cancel is caller's job — see Stop). */
  _sessionId?: string,
): () => void {
  const controller = new AbortController()
  void _sessionId

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
            // Ignore stray error events after a successful terminal `done`.
            if (gotTerminal && currentEventType === 'error') {
              continue
            }
            try {
              const parsed = JSON.parse(eventData) as Record<string, unknown>
              // SSE event line is authoritative; JSON `type` is metadata only.
              const evt = { ...parsed, type: currentEventType } as StreamEvent
              if (currentEventType === 'done' || currentEventType === 'error') {
                gotTerminal = true
              }
              onEvent(evt)
            } catch {
              if (currentEventType === 'error') {
                gotTerminal = true
              }
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
  // Detach only: abort the fetch. Backend `_sse_detach_producer` keeps the turn running.
  // Callers that must stop the agent must `cancelSession` themselves (e.g. Stop button).
  return () => {
    controller.abort()
  }
}

export { API_BASE_URL }

