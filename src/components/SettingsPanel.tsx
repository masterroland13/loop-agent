import { useEffect, useState } from 'react'
import {
  fetchAssets,
  fetchAudit,
  fetchLlmConfig,
  fetchMemoryContent,
  fetchModels,
  fetchSkills,
  fetchTools,
  testLlmConnection,
  updateAgentSettings,
  updateLlmConfig,
  updateMemoryContent,
  type AssetsStatus,
  type AuditEvent,
  type LlmConfig,
  type LlmTestResult,
  type SkillInfo,
  type ToolInfo,
} from '../api/agent'
import type { SettingsState } from '../hooks/useSettings'

interface SettingsPanelProps {
  isOpen: boolean
  settings: SettingsState
  onClose: () => void
  onChange: <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => void
  onToggleSkill: (skillId: string) => void
}

const SECTIONS = [
  { id: 'model', label: '模型服务' },
  { id: 'appearance', label: '外观' },
  { id: 'agent', label: 'Agent' },
  { id: 'skills', label: '技能' },
  { id: 'memory', label: '记忆' },
  { id: 'cli', label: 'CLI' },
  { id: 'assets', label: '资产' },
  { id: 'audit', label: '审计' },
  { id: 'shortcuts', label: '快捷键' },
  { id: 'data', label: '数据' },
  { id: 'about', label: '关于' },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

export function SettingsPanel({ isOpen, settings, onClose, onChange, onToggleSkill }: SettingsPanelProps) {
  const [activeSection, setActiveSection] = useState<SectionId>('model')
  const [assets, setAssets] = useState<AssetsStatus | null>(null)
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [agentsMdExists, setAgentsMdExists] = useState(false)
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [skillsError, setSkillsError] = useState<string | null>(null)
  const [skillExpanded, setSkillExpanded] = useState<Record<string, boolean>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [llmConfig, setLlmConfig] = useState<LlmConfig | null>(null)
  const [llmKeyDraft, setLlmKeyDraft] = useState('')
  const [llmUrlDraft, setLlmUrlDraft] = useState('')
  const [llmModelDraft, setLlmModelDraft] = useState('')
  const [llmSaving, setLlmSaving] = useState(false)
  const [llmError, setLlmError] = useState<string | null>(null)
  const [llmSavedHint, setLlmSavedHint] = useState<string | null>(null)
  const [llmTempDraft, setLlmTempDraft] = useState(0.7)
  const [llmTokensDraft, setLlmTokensDraft] = useState(2048)
  const [llmTesting, setLlmTesting] = useState(false)
  const [llmTestResult, setLlmTestResult] = useState<LlmTestResult | null>(null)
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [disabledTools, setDisabledTools] = useState<string[]>([])
  const [memoryDraft, setMemoryDraft] = useState('')
  const [memoryPath, setMemoryPath] = useState('')
  const [memorySaving, setMemorySaving] = useState(false)
  const [memoryHint, setMemoryHint] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) return
    const handle = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handle)
    return () => window.removeEventListener('keydown', handle)
  }, [isOpen, onClose])

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setLoadError(null)
    setSkillsLoading(true)
    setSkillsError(null)
    Promise.all([fetchAssets(), fetchAudit(30), fetchSkills(), fetchLlmConfig(), fetchTools(), fetchMemoryContent()])
      .then(([a, events, s, llm, t, mem]) => {
        if (cancelled) return
        setAssets(a)
        setAudit(events)
        setSkills(s.skills)
        setAgentsMdExists(s.agents_md_exists)
        setLlmConfig(llm)
        setLlmUrlDraft(llm.base_url)
        setLlmModelDraft(llm.default_model)
        setLlmTempDraft(llm.temperature)
        setLlmTokensDraft(llm.max_tokens)
        setLlmKeyDraft('')
        setLlmError(null)
        setTools(t.tools)
        setDisabledTools(t.disabled_tools)
        setMemoryDraft(mem.content)
        setMemoryPath(mem.path)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(err instanceof Error ? err.message : '加载资产/审计/技能失败')
      })
      .finally(() => {
        if (!cancelled) setSkillsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  if (!isOpen) return null

  const activeMeta = SECTIONS.find((s) => s.id === activeSection) ?? SECTIONS[0]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative flex h-[82vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-xl">
        <nav className="flex w-44 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-[var(--border-subtle)] bg-[var(--surface)]/30 p-2.5">
          <div className="px-2 pb-2.5 pt-1.5 text-[15px] font-semibold text-[var(--text-h)]">设置</div>
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setActiveSection(s.id)}
              className={[
                'rounded-lg px-3 py-2 text-left text-[13.5px] transition-colors',
                s.id === activeSection
                  ? 'bg-[var(--accent-bg)] font-medium text-[var(--accent)]'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
              ].join(' ')}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-4">
            <h2 className="text-base font-semibold text-[var(--text-h)]">{activeMeta.label}</h2>
            <button
              type="button"
              onClick={onClose}
              className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
                <path d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            {activeSection === 'model' && (
              <>
                <LlmProviderFields
              config={llmConfig}
              keyDraft={llmKeyDraft}
              urlDraft={llmUrlDraft}
              modelDraft={llmModelDraft}
              tempDraft={llmTempDraft}
              tokensDraft={llmTokensDraft}
              saving={llmSaving}
              error={llmError}
              savedHint={llmSavedHint}
              testing={llmTesting}
              testResult={llmTestResult}
              onKeyDraft={setLlmKeyDraft}
              onUrlDraft={setLlmUrlDraft}
              onModelDraft={setLlmModelDraft}
              onTempDraft={setLlmTempDraft}
              onTokensDraft={setLlmTokensDraft}
              onTest={async () => {
                setLlmTesting(true)
                setLlmTestResult(null)
                try {
                  setLlmTestResult(await testLlmConnection())
                } catch (err) {
                  setLlmTestResult({ ok: false, error: err instanceof Error ? err.message : '测试失败' })
                } finally {
                  setLlmTesting(false)
                }
              }}
              onSave={async (patch) => {
                setLlmSaving(true)
                setLlmError(null)
                setLlmSavedHint(null)
                try {
                  const next = await updateLlmConfig(patch)
                  setLlmConfig(next)
                  setLlmUrlDraft(next.base_url)
                  setLlmModelDraft(next.default_model)
                  setLlmTempDraft(next.temperature)
                  setLlmTokensDraft(next.max_tokens)
                  if (patch.api_key) setLlmKeyDraft('')
                  setLlmSavedHint('已保存到 backend/.env，立即生效')
                } catch (err) {
                  setLlmError(err instanceof Error ? err.message : '保存失败')
                } finally {
                  setLlmSaving(false)
                }
              }}
            />
              </>
            )}

            {activeSection === 'appearance' && (
              <>
            <div className="grid grid-cols-3 gap-2">
              <Choice label="深色" active={settings.theme === 'dark'} onClick={() => onChange('theme', 'dark')} />
              <Choice label="浅色" active={settings.theme === 'light'} onClick={() => onChange('theme', 'light')} />
              <Choice label="跟随系统" active={settings.theme === 'system'} onClick={() => onChange('theme', 'system')} />
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <Choice label="小字体" active={settings.fontSize === 'small'} onClick={() => onChange('fontSize', 'small')} />
              <Choice label="中字体" active={settings.fontSize === 'medium'} onClick={() => onChange('fontSize', 'medium')} />
              <Choice label="大字体" active={settings.fontSize === 'large'} onClick={() => onChange('fontSize', 'large')} />
            </div>
              </>
            )}

            {activeSection === 'agent' && (
              <>
            <Toggle
              label="自动压缩历史上下文"
              description="超限时摘要旧轮次再进 loop"
              checked={settings.autoCompress}
              onChange={(v) => onChange('autoCompress', v)}
            />
            <Toggle
              label="写入记忆前确认"
              description="Agent 更新 USER.md 前需要确认"
              checked={settings.confirmMemory}
              onChange={(v) => onChange('confirmMemory', v)}
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm text-[var(--text-h)]">上下文上限</div>
                <div className="text-xs text-[var(--text-muted)]">{settings.contextLimit.toLocaleString()} tokens</div>
              </div>
              <input
                type="range"
                min={2048}
                max={32768}
                step={1024}
                value={settings.contextLimit}
                onChange={(e) => onChange('contextLimit', Number(e.target.value))}
                className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-[var(--border)] accent-[var(--text-h)]"
              />
            </div>
            <AgentGovernanceFields
              tools={tools}
              disabledTools={disabledTools}
              approvalTimeout={settings.approvalTimeoutSec ?? 300}
              onApprovalTimeout={(v) => onChange('approvalTimeoutSec', v)}
              onToggleTool={(name) => {
                const next = disabledTools.includes(name)
                  ? disabledTools.filter((t) => t !== name)
                  : [...disabledTools, name]
                setDisabledTools(next)
                void updateAgentSettings({ disabled_tools: next }).catch(() => {})
              }}
            />
              </>
            )}

            {activeSection === 'skills' && (
              <>
            {skillsLoading && <p className="text-xs text-[var(--text-muted)]">加载中…</p>}
            {skillsError && (
              <p className="text-xs text-amber-400">{skillsError}</p>
            )}
            {skills.length === 0 && !skillsLoading && !skillsError ? (
              <p className="text-xs text-[var(--text-muted)]">
                工作区 skills/ 下未发现技能；可创建 skills/&lt;skill-id&gt;/SKILL.md（推荐，支持 YAML
                frontmatter）或 README.md。
              </p>
            ) : (
              <div className="space-y-2">
                {skills.map((skill) => {
                  const active = settings.activeSkills.includes(skill.id)
                  return (
                    <div key={skill.id} className="rounded-lg bg-[var(--surface)] px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => setSkillExpanded((prev) => ({ ...prev, [skill.id]: !prev[skill.id] }))}
                          className="flex flex-1 items-center gap-1 text-left text-xs text-[var(--text-h)]"
                        >
                          <span className="text-[var(--text-dim)]">{skillExpanded[skill.id] ? '▾' : '▸'}</span>
                          <span className="font-medium">{skill.name}</span>
                          <span className="font-mono text-[var(--text-muted)]">{skill.id}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => onToggleSkill(skill.id)}
                          className={[
                            'rounded-md px-2 py-1 text-xs',
                            active
                              ? 'bg-[var(--text-h)] text-[var(--bg)]'
                              : 'border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-h)]',
                          ].join(' ')}
                        >
                          {active ? '已激活' : '未激活'}
                        </button>
                      </div>
                      {skillExpanded[skill.id] && (
                        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-[10px] text-[var(--text-muted)]">
                          {skill.description ? `${skill.description}\n\n` : ''}
                          {skill.preview}
                        </pre>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            <p className="mt-2 text-xs text-[var(--text-muted)]">
              项目规则：{agentsMdExists ? '已发现 AGENTS.md' : '未发现 AGENTS.md'}
            </p>
              </>
            )}

            {activeSection === 'memory' && (
              <MemorySection
                draft={memoryDraft}
                path={memoryPath}
                saving={memorySaving}
                hint={memoryHint}
                onDraft={setMemoryDraft}
                onSave={async () => {
                  setMemorySaving(true)
                  setMemoryHint(null)
                  try {
                    await updateMemoryContent(memoryDraft)
                    setMemoryHint('已保存，下一轮对话生效')
                  } finally {
                    setMemorySaving(false)
                  }
                }}
                onClear={async () => {
                  if (!window.confirm('确定清空 USER.md 全部记忆？')) return
                  setMemorySaving(true)
                  try {
                    await updateMemoryContent('')
                    setMemoryDraft('')
                    setMemoryHint('已清空')
                  } finally {
                    setMemorySaving(false)
                  }
                }}
              />
            )}

            {activeSection === 'cli' && <CliSection />}

            {activeSection === 'about' && <AboutSection />}

            {activeSection === 'assets' && (
              <>
            {loadError && (
              <p className="mb-2 text-xs text-red-400">{loadError}</p>
            )}
            {assets ? (
              <div className="space-y-1.5 rounded-lg bg-[var(--surface)] px-3 py-3 text-xs text-[var(--text-muted)]">
                <Row label="健康" value={`${assets.status} · ${assets.provider}${assets.provider_available ? '' : '（不可用）'}`} />
                <Row label="会话数" value={String(assets.session_count)} />
                <Row
                  label="USER.md"
                  value={
                    assets.user_md_exists
                      ? `${assets.user_md_size} B`
                      : '尚未创建'
                  }
                />
                <Row
                  label="工作区"
                  value={
                    assets.workspace_configured
                      ? assets.workspace_root || '已配置'
                      : '未绑定'
                  }
                />
                <Row
                  label="压缩 / 记忆确认"
                  value={`${assets.settings.auto_compress ? '开' : '关'} / ${assets.settings.confirm_memory ? '开' : '关'}`}
                />
                <Row label="上下文上限" value={String(assets.settings.context_limit)} />
              </div>
            ) : (
              !loadError && <p className="text-xs text-[var(--text-muted)]">加载中…</p>
            )}
              </>
            )}

            {activeSection === 'audit' && (
              <>
            {audit.length === 0 ? (
              <p className="text-xs text-[var(--text-muted)]">暂无事件</p>
            ) : (
              <ul className="max-h-40 space-y-1.5 overflow-y-auto rounded-lg bg-[var(--surface)] px-3 py-2">
                {audit.map((ev) => (
                  <li key={ev.id} className="border-b border-[var(--border-subtle)] py-1.5 last:border-0">
                    <div className="flex justify-between gap-2 text-[11px]">
                      <span className="font-mono text-[var(--text-h)]">{ev.event_type}</span>
                      <span className="shrink-0 text-[var(--text-dim)]">
                        {new Date(ev.created_at).toLocaleString()}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
              </>
            )}

            {activeSection === 'shortcuts' && (
              <>
            <Toggle
              label="Enter 发送"
              description="关闭后可用 Shift+Enter 换行"
              checked={settings.enterToSend}
              onChange={(v) => onChange('enterToSend', v)}
            />
            <Toggle
              label="启用导航快捷键"
              description="↑/↓ 在消息间跳转，Esc 停止生成"
              checked={settings.shortcuts}
              onChange={(v) => onChange('shortcuts', v)}
            />
            <div className="mt-3 rounded-lg bg-[var(--surface)] px-3 py-2 text-xs text-[var(--text-muted)]">
              <div className="flex justify-between py-1"><span>新对话</span><span className="font-mono text-[var(--text-h)]">Ctrl+N</span></div>
              <div className="flex justify-between py-1"><span>停止生成</span><span className="font-mono text-[var(--text-h)]">Esc</span></div>
              <div className="flex justify-between py-1"><span>上一个 / 下一个</span><span className="font-mono text-[var(--text-h)]">↑ / ↓</span></div>
              <div className="flex justify-between py-1"><span>打开设置</span><span className="font-mono text-[var(--text-h)]">Ctrl+,</span></div>
            </div>
              </>
            )}

            {activeSection === 'data' && (
              <>
            <div className="rounded-lg bg-[var(--surface)] px-3 py-3">
              <div className="text-sm text-[var(--text-h)]">本地数据</div>
              <div className="mt-1 text-xs text-[var(--text-muted)]">会话保存在浏览器本地存储和后端 ./data 中</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const payload = JSON.stringify({ exportedAt: new Date().toISOString(), settings }, null, 2)
                    const blob = new Blob([payload], { type: 'application/json' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `hal-agent-settings-${Date.now()}.json`
                    a.click()
                    URL.revokeObjectURL(url)
                  }}
                  className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-xs text-[var(--text-h)] hover:bg-[var(--surface-hover)]"
                >
                  导出设置
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const payload = JSON.stringify(
                      { exportedAt: new Date().toISOString(), audit },
                      null,
                      2,
                    )
                    const blob = new Blob([payload], { type: 'application/json' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `hal-agent-audit-${Date.now()}.json`
                    a.click()
                    URL.revokeObjectURL(url)
                  }}
                  className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-xs text-[var(--text-h)] hover:bg-[var(--surface-hover)]"
                >
                  导出最近审计
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm('确定清除本地设置缓存？会话数据不会删除。')) {
                      localStorage.removeItem('agent-chat:settings')
                      localStorage.removeItem('agent-chat:theme')
                      window.location.reload()
                    }
                  }}
                  className="rounded-md border border-red-900/40 bg-red-950/20 px-3 py-1.5 text-xs text-red-400 hover:bg-red-950/40"
                >
                  重置设置
                </button>
              </div>
            </div>
              </>
            )}
          </div>

          <div className="border-t border-[var(--border-subtle)] px-5 py-3 text-center text-xs text-[var(--text-muted)]">
            外观存浏览器；Agent 开关与模型服务覆盖同步到后端
          </div>
        </div>
      </div>
    </div>
  )
}

function AgentGovernanceFields({
  tools,
  disabledTools,
  approvalTimeout,
  onApprovalTimeout,
  onToggleTool,
}: {
  tools: ToolInfo[]
  disabledTools: string[]
  approvalTimeout: number
  onApprovalTimeout: (value: number) => void
  onToggleTool: (name: string) => void
}) {
  return (
    <>
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-4">
        <div>
          <div className="text-sm text-[var(--text-h)]">审批超时</div>
          <div className="text-xs text-[var(--text-muted)]">{approvalTimeout} 秒 · 超时后提案自动失效</div>
        </div>
        <input
          type="range"
          min={30}
          max={1800}
          step={30}
          value={approvalTimeout}
          onChange={(e) => onApprovalTimeout(Number(e.target.value))}
          className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-[var(--border)] accent-[var(--accent)]"
        />
      </div>

      <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
        <div className="text-sm text-[var(--text-h)]">工具开关</div>
        <div className="mb-2 text-xs text-[var(--text-muted)]">关闭后模型本轮不再看到该工具</div>
        {tools.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)]">加载中…</p>
        ) : (
          <div className="grid grid-cols-2 gap-1.5">
            {tools.map((tool) => {
              const enabled = !disabledTools.includes(tool.name)
              return (
                <button
                  key={tool.name}
                  type="button"
                  title={tool.description}
                  onClick={() => onToggleTool(tool.name)}
                  className={[
                    'rounded-lg px-2.5 py-1.5 text-left font-mono text-xs transition-colors',
                    enabled
                      ? 'bg-[var(--accent-bg)] text-[var(--text-h)]'
                      : 'bg-[var(--surface)] text-[var(--text-dim)] line-through',
                  ].join(' ')}
                >
                  {tool.name}
                </button>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}

function MemorySection({
  draft,
  path,
  saving,
  hint,
  onDraft,
  onSave,
  onClear,
}: {
  draft: string
  path: string
  saving: boolean
  hint: string | null
  onDraft: (value: string) => void
  onSave: () => Promise<void>
  onClear: () => Promise<void>
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-sm text-[var(--text-h)]">USER.md 长期记忆</div>
          <span className="max-w-[55%] truncate font-mono text-[10px] text-[var(--text-dim)]" title={path}>
            {path}
          </span>
        </div>
        <textarea
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          placeholder="还没有记忆。Agent 提议写入或在这里直接编辑。"
          rows={12}
          className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 font-mono text-[13px] leading-relaxed text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)] focus:border-[var(--accent)]"
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            disabled={saving}
            onClick={() => void onSave()}
            className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-xs text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
          >
            {saving ? '保存中…' : '保存'}
          </button>
          <button
            type="button"
            disabled={saving || !draft.trim()}
            onClick={() => void onClear()}
            className="rounded-md border border-red-900/40 bg-red-950/20 px-3 py-1.5 text-xs text-red-400 hover:bg-red-950/40 disabled:opacity-40"
          >
            清空记忆
          </button>
          {hint && <span className="text-xs text-emerald-400">{hint}</span>}
        </div>
        <p className="mt-2 text-[11px] text-[var(--text-muted)]">
          这里的编辑直接生效（相当于你自己动手，无需审批）。Agent 通过 propose_memory 的写入仍走确认。
        </p>
      </div>
    </div>
  )
}

function CliSection() {
  const commands = [
    { cmd: 'hal ask "问题"', desc: '发起对话（自动建会话）' },
    { cmd: 'hal status', desc: '查看待审批项' },
    { cmd: 'hal approve --patch-id <id>', desc: '批准改动' },
    { cmd: 'hal reject --shell-id <id>', desc: '拒绝命令' },
    { cmd: 'hal run --wait -s <会话> "任务"', desc: '跑任务并等审批完成' },
    { cmd: 'hal sessions', desc: '列出会话' },
  ]
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 text-sm text-[var(--text-h)]">配置文件</div>
        <p className="font-mono text-xs text-[var(--text-muted)]">~/.config/hal-agent/config.json</p>
        <p className="mt-1 text-[11px] text-[var(--text-dim)]">
          优先级：环境变量 AGENT_BASE_URL &gt; 配置文件 &gt; 默认 http://127.0.0.1:8000
        </p>
      </div>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 text-sm text-[var(--text-h)]">常用命令</div>
        <div className="space-y-1.5">
          {commands.map((c) => (
            <div key={c.cmd} className="flex items-baseline justify-between gap-3">
              <code className="rounded bg-[var(--bg)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-h)]">
                {c.cmd}
              </code>
              <span className="shrink-0 text-[11px] text-[var(--text-muted)]">{c.desc}</span>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-[var(--text-dim)]">
          使用前激活虚拟环境：source backend/.venv/bin/activate
        </p>
      </div>
    </div>
  )
}

function AboutSection() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
        <img src="/favicon.svg" alt="Hal Agent" className="h-12 w-12" />
        <div>
          <div className="text-[15px] font-semibold text-[var(--text-h)]">Hal Agent</div>
          <div className="mt-0.5 text-xs text-[var(--text-muted)]">
            可监督的 AI 编码工作台 · React + FastAPI + SQLite
          </div>
        </div>
      </div>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-xs text-[var(--text-muted)]">
        <div className="flex justify-between py-1"><span>后端</span><span className="font-mono text-[var(--text-h)]">hal-agent-backend 0.1.0</span></div>
        <div className="flex justify-between py-1"><span>路线图</span><span className="font-mono text-[var(--text-h)]">docs/agent-window-roadmap.md</span></div>
        <div className="flex justify-between py-1"><span>变更记录</span><span className="font-mono text-[var(--text-h)]">CHANGELOG.md</span></div>
        <div className="flex justify-between py-1"><span>CLI 设计</span><span className="font-mono text-[var(--text-h)]">docs/v1-7-headless-cli-design.md</span></div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span>{label}</span>
      <span className="max-w-[60%] truncate text-right font-mono text-[var(--text-h)]" title={value}>
        {value}
      </span>
    </div>
  )
}

function Choice({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        'rounded-lg px-2 py-2 text-sm transition-colors',
        active
          ? 'bg-[var(--accent-bg)] text-[var(--text-h)]'
          : 'bg-[var(--surface)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

function LlmProviderFields({
  config,
  keyDraft,
  urlDraft,
  modelDraft,
  tempDraft,
  tokensDraft,
  saving,
  error,
  savedHint,
  testing,
  testResult,
  onKeyDraft,
  onUrlDraft,
  onModelDraft,
  onTempDraft,
  onTokensDraft,
  onTest,
  onSave,
}: {
  config: LlmConfig | null
  keyDraft: string
  urlDraft: string
  modelDraft: string
  tempDraft: number
  tokensDraft: number
  saving: boolean
  error: string | null
  savedHint: string | null
  testing: boolean
  testResult: LlmTestResult | null
  onKeyDraft: (value: string) => void
  onUrlDraft: (value: string) => void
  onModelDraft: (value: string) => void
  onTempDraft: (value: number) => void
  onTokensDraft: (value: number) => void
  onTest: () => Promise<void>
  onSave: (patch: {
    api_key?: string
    base_url?: string
    default_model?: string
    temperature?: number
    max_tokens?: number
  }) => Promise<void>
}) {
  const [models, setModels] = useState<string[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)

  useEffect(() => {
    if (!config) return
    let cancelled = false
    setModelsLoading(true)
    fetchModels()
      .then((res) => {
        if (cancelled) return
        setModels(res.models.map((m) => m.id).filter(Boolean))
      })
      .catch(() => {
        if (!cancelled) setModels([])
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false)
      })
    return () => {
      cancelled = true
    }
    // Re-fetch the gateway model list whenever the base URL changes.
  }, [config?.base_url, config?.api_key_configured])

  if (!config) {
    return <p className="text-xs text-[var(--text-muted)]">加载中…</p>
  }

  const dirty =
    urlDraft.trim() !== config.base_url ||
    modelDraft.trim() !== config.default_model ||
    keyDraft.trim().length > 0 ||
    tempDraft !== config.temperature ||
    tokensDraft !== config.max_tokens

  const modelChoices = models.includes(modelDraft)
    ? models
    : modelDraft
      ? [modelDraft, ...models]
      : models

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-sm text-[var(--text-h)]">API Key</div>
          <span className="text-[10px] text-[var(--text-muted)]">
            {config.api_key_configured ? '已保存（明文不回显）' : '未配置'}
          </span>
        </div>
        <input
          type="password"
          autoComplete="off"
          value={keyDraft}
          onChange={(e) => onKeyDraft(e.target.value)}
          placeholder={config.api_key_configured ? '已保存密钥。输入新密钥以替换' : '粘贴 API Key'}
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--accent)]"
        />
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 text-sm text-[var(--text-h)]">Base URL</div>
        <input
          type="url"
          autoComplete="off"
          value={urlDraft}
          onChange={(e) => onUrlDraft(e.target.value)}
          placeholder="https://api.example.com/v1"
          className="w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--accent)]"
        />
        <p className="mt-2 text-[11px] text-[var(--text-muted)]">
          OpenAI 兼容网关地址（含 /v1）。保存后写入 backend/.env 并立即生效。
        </p>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="text-sm text-[var(--text-h)]">默认模型</div>
          {modelsLoading && <span className="text-[10px] text-[var(--text-muted)]">拉取列表…</span>}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {modelChoices.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => onModelDraft(m)}
              className={[
                'rounded-full px-3 py-1 text-xs transition-colors',
                m === modelDraft
                  ? 'bg-[var(--accent-bg)] text-[var(--text-h)] ring-1 ring-[var(--accent)]'
                  : 'bg-[var(--bg)] text-[var(--text-muted)] hover:text-[var(--text-h)]',
              ].join(' ')}
            >
              {m}
            </button>
          ))}
          {modelChoices.length === 0 && !modelsLoading && (
            <span className="text-xs text-[var(--text-muted)]">网关未返回模型列表，可在下方手填。</span>
          )}
        </div>
        <input
          type="text"
          autoComplete="off"
          value={modelDraft}
          onChange={(e) => onModelDraft(e.target.value)}
          placeholder="模型 id，例如 deepseek-v4-flash"
          className="mt-2 w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--accent)]"
        />
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 text-sm text-[var(--text-h)]">生成参数</div>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm text-[var(--text-h)]">Temperature</div>
              <div className="text-xs text-[var(--text-muted)]">{tempDraft.toFixed(2)} · 越高越发散</div>
            </div>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={tempDraft}
              onChange={(e) => onTempDraft(Number(e.target.value))}
              className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-[var(--border)] accent-[var(--accent)]"
            />
          </div>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm text-[var(--text-h)]">Max Tokens</div>
              <div className="text-xs text-[var(--text-muted)]">单次回复最大长度</div>
            </div>
            <input
              type="number"
              min={256}
              max={200000}
              step={256}
              value={tokensDraft}
              onChange={(e) => onTokensDraft(Number(e.target.value))}
              className="w-28 rounded-lg border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1.5 text-right font-mono text-sm text-[var(--text-h)] outline-none focus:border-[var(--accent)]"
            />
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm text-[var(--text-h)]">连接测试</div>
            <div className="text-xs text-[var(--text-muted)]">用当前配置 ping 网关的模型列表</div>
          </div>
          <button
            type="button"
            disabled={testing}
            onClick={() => void onTest()}
            className="rounded-md border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
          >
            {testing ? '测试中…' : '测试连接'}
          </button>
        </div>
        {testResult && (
          <p className={`mt-2 text-xs ${testResult.ok ? 'text-emerald-400' : 'text-red-400'}`}>
            {testResult.ok
              ? `连接正常 · ${testResult.latency_ms}ms · ${testResult.model_count} 个模型`
              : `连接失败：${testResult.error || '未知错误'}`}
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={saving || !dirty}
          onClick={() =>
            void onSave({
              base_url: urlDraft.trim(),
              default_model: modelDraft.trim(),
              temperature: tempDraft,
              max_tokens: tokensDraft,
              ...(keyDraft.trim() ? { api_key: keyDraft.trim() } : {}),
            })
          }
          className="rounded-md bg-[var(--accent-bg)] px-4 py-1.5 text-sm text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
        >
          {saving ? '保存中…' : '保存'}
        </button>
        {error && <p className="text-xs text-red-400">{error}</p>}
        {savedHint && <p className="text-xs text-emerald-400">{savedHint}</p>}
      </div>
    </div>
  )
}

function Toggle({
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  label: string
  description?: string
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
}) {
  return (
    <div className={`mb-3 flex items-center justify-between gap-3 ${disabled ? 'opacity-60' : ''}`}>
      <div>
        <div className="text-sm text-[var(--text-h)]">{label}</div>
        {description && <div className="text-xs text-[var(--text-muted)]">{description}</div>}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => !disabled && onChange(!checked)}
        className={[
          'relative h-6 w-11 shrink-0 rounded-full transition-colors',
          checked ? 'bg-[var(--text-h)]' : 'bg-[var(--border)]',
          disabled ? 'cursor-not-allowed' : '',
        ].join(' ')}
      >
        <span
          className={[
            'absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-[var(--bg)] transition-transform',
            checked ? 'translate-x-5' : 'translate-x-0',
          ].join(' ')}
        />
      </button>
    </div>
  )
}
