import { useEffect, useState, type ReactNode } from 'react'
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
  type LlmConfig,
  type LlmTestResult,
  type SkillInfo,
  type ToolInfo,
} from '../api/agent'
import type { SettingsState } from '../hooks/useSettings'
import { AuditPanel } from './AuditPanel'

interface SettingsPanelProps {
  isOpen: boolean
  settings: SettingsState
  onClose: () => void
  onChange: <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => void
  onToggleSkill: (skillId: string) => void
  activeSessionId?: string | null
  sessions?: { id: string; title: string }[]
  onOpenSession?: (sessionId: string) => void
}

const SECTIONS = [
  { id: 'model', label: '模型服务', icon: 'model' },
  { id: 'appearance', label: '外观', icon: 'appearance' },
  { id: 'agent', label: 'Agent', icon: 'agent' },
  { id: 'skills', label: '技能', icon: 'skills' },
  { id: 'memory', label: '记忆', icon: 'memory' },
  { id: 'cli', label: 'CLI', icon: 'cli' },
  { id: 'assets', label: '资产', icon: 'assets' },
  { id: 'audit', label: '审计', icon: 'audit' },
  { id: 'shortcuts', label: '快捷键', icon: 'shortcuts' },
  { id: 'data', label: '数据', icon: 'data' },
  { id: 'about', label: '关于', icon: 'about' },
] as const

type SectionId = (typeof SECTIONS)[number]['id']
type SectionIcon = (typeof SECTIONS)[number]['icon']

export function SettingsPanel({
  isOpen,
  settings,
  onClose,
  onChange,
  onToggleSkill,
  activeSessionId,
  sessions = [],
  onOpenSession,
}: SettingsPanelProps) {
  const [activeSection, setActiveSection] = useState<SectionId>('model')
  const [assets, setAssets] = useState<AssetsStatus | null>(null)
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
    Promise.all([fetchAssets(), fetchSkills(), fetchLlmConfig(), fetchTools(), fetchMemoryContent()])
      .then(([a, s, llm, t, mem]) => {
        if (cancelled) return
        setAssets(a)
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
        setLoadError(err instanceof Error ? err.message : '加载资产/技能失败')
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
        <nav className="flex w-48 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-[var(--border-subtle)] bg-[var(--surface)]/30 p-2">
          <div className="px-2.5 pb-2 pt-1.5 text-[15px] font-semibold text-[var(--text-h)]">设置</div>
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setActiveSection(s.id)}
              className={[
                'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px] transition-colors',
                s.id === activeSection
                  ? 'bg-[var(--surface-hover)] font-medium text-[var(--text-h)]'
                  : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)]/70 hover:text-[var(--text-h)]',
              ].join(' ')}
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center opacity-90">
                <SettingsNavIcon name={s.icon} />
              </span>
              <span className="truncate">{s.label}</span>
            </button>
          ))}
        </nav>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3">
            <h2 className="text-[15px] font-semibold text-[var(--text-h)]">{activeMeta.label}</h2>
            <button
              type="button"
              onClick={onClose}
              className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
                <path d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            <div className="mx-auto w-full max-w-xl space-y-3">
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
                <SettingsCard title="主题">
                  <div className="grid grid-cols-3 gap-2">
                    <Choice label="深色" active={settings.theme === 'dark'} onClick={() => onChange('theme', 'dark')} />
                    <Choice label="浅色" active={settings.theme === 'light'} onClick={() => onChange('theme', 'light')} />
                    <Choice label="跟随系统" active={settings.theme === 'system'} onClick={() => onChange('theme', 'system')} />
                  </div>
                </SettingsCard>
                <SettingsCard title="字号">
                  <div className="grid grid-cols-3 gap-2">
                    <Choice label="小" active={settings.fontSize === 'small'} onClick={() => onChange('fontSize', 'small')} />
                    <Choice label="中" active={settings.fontSize === 'medium'} onClick={() => onChange('fontSize', 'medium')} />
                    <Choice label="大" active={settings.fontSize === 'large'} onClick={() => onChange('fontSize', 'large')} />
                  </div>
                </SettingsCard>
              </>
            )}

            {activeSection === 'agent' && (
              <>
            <Toggle
              label="自动压缩历史上下文"
              description="超限时折叠旧轮次；本轮 Goal 会写入摘要并重新注入，不会被冲掉"
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
              maxToolIters={settings.maxToolIters ?? 24}
              onMaxToolIters={(v) => onChange('maxToolIters', v)}
              checkpointEveryNTools={settings.checkpointEveryNTools ?? 4}
              onCheckpointEveryNTools={(v) => onChange('checkpointEveryNTools', v)}
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
              <AuditPanel
                activeSessionId={activeSessionId}
                sessions={sessions}
                onOpenSession={onOpenSession}
              />
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
                    void fetchAudit(100).then((events) => {
                      const payload = JSON.stringify(
                        { exportedAt: new Date().toISOString(), audit: events },
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
                    })
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
          </div>

          <div className="border-t border-[var(--border-subtle)] px-5 py-2.5 text-center text-[11px] text-[var(--text-dim)]">
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
  maxToolIters,
  onMaxToolIters,
  checkpointEveryNTools,
  onCheckpointEveryNTools,
  onToggleTool,
}: {
  tools: ToolInfo[]
  disabledTools: string[]
  approvalTimeout: number
  onApprovalTimeout: (value: number) => void
  maxToolIters: number
  onMaxToolIters: (value: number) => void
  checkpointEveryNTools: number
  onCheckpointEveryNTools: (value: number) => void
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

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-4">
        <div>
          <div className="text-sm text-[var(--text-h)]">工具轮次上限</div>
          <div className="text-xs text-[var(--text-muted)]">
            {maxToolIters} 轮 · 达上限后尝试总结而非直接中止
          </div>
        </div>
        <input
          type="range"
          min={8}
          max={64}
          step={1}
          value={maxToolIters}
          onChange={(e) => onMaxToolIters(Number(e.target.value))}
          className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-[var(--border)] accent-[var(--accent)]"
        />
      </div>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-4">
        <div>
          <div className="text-sm text-[var(--text-h)]">进度检查点</div>
          <div className="text-xs text-[var(--text-muted)]">
            {checkpointEveryNTools === 0
              ? '仅审批 gate 返回后对照目标'
              : `每 ${checkpointEveryNTools} 次工具 · 强制对照目标`}
          </div>
        </div>
        <input
          type="range"
          min={0}
          max={16}
          step={1}
          value={checkpointEveryNTools}
          onChange={(e) => onCheckpointEveryNTools(Number(e.target.value))}
          className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-[var(--border)] accent-[var(--accent)]"
        />
      </div>

      <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
        <div className="text-sm text-[var(--text-h)]">本轮目标（Turn Goal）</div>
        <div className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
          每轮从用户消息自动提取目标并注入 loop；短回复如「好的 / 继续」会继承上一轮实质目标。消息旁显示「目标」条。目标变更会写入审计，并在目标条标「已变更」。
        </div>
        <div className="mt-2 text-xs leading-relaxed text-[var(--text-dim)]">
          检查点（F2）：每 N 次工具或审批返回后，loop 要求模型说明相对目标的进度 / 阻塞 / 下一步；说明会出现在消息旁「检查点」条（可折叠）。
        </div>
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
    <div className="space-y-3">
      <SettingsCard title="连接" hint={config.api_key_configured ? '密钥已保存（不回显）' : '尚未配置密钥'}>
        <label className="block">
          <span className="mb-1 block text-[12px] text-[var(--text-muted)]">API Key</span>
          <input
            type="password"
            autoComplete="off"
            value={keyDraft}
            onChange={(e) => onKeyDraft(e.target.value)}
            placeholder={config.api_key_configured ? '已保存。输入新密钥以替换' : '粘贴 API Key'}
            className={fieldClass}
          />
        </label>
        <label className="mt-3 block">
          <span className="mb-1 block text-[12px] text-[var(--text-muted)]">Base URL</span>
          <input
            type="url"
            autoComplete="off"
            value={urlDraft}
            onChange={(e) => onUrlDraft(e.target.value)}
            placeholder="https://api.example.com/v1"
            className={fieldClass}
          />
          <p className="mt-1.5 text-[11px] leading-relaxed text-[var(--text-dim)]">
            OpenAI 兼容网关（含 /v1）。保存写入 backend/.env 并立即生效。
          </p>
        </label>
        <div className="mt-3 flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-3">
          <div className="min-w-0">
            <div className="text-[13px] text-[var(--text-h)]">连接测试</div>
            {testResult && (
              <p className={`mt-0.5 text-[11px] ${testResult.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                {testResult.ok
                  ? `正常 · ${testResult.latency_ms}ms · ${testResult.model_count} 个模型`
                  : `失败：${testResult.error || '未知错误'}`}
              </p>
            )}
          </div>
          <button
            type="button"
            disabled={testing}
            onClick={() => void onTest()}
            className="shrink-0 rounded-md border border-[var(--border)] px-3 py-1.5 text-xs text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
          >
            {testing ? '测试中…' : '测试连接'}
          </button>
        </div>
      </SettingsCard>

      <SettingsCard title="默认模型" hint={modelsLoading ? '拉取列表…' : undefined}>
        <div className="flex flex-wrap gap-1.5">
          {modelChoices.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => onModelDraft(m)}
              className={[
                'rounded-full px-2.5 py-1 text-[12px] transition-colors',
                m === modelDraft
                  ? 'bg-[var(--accent-bg)] text-[var(--text-h)] ring-1 ring-[var(--accent)]'
                  : 'bg-[var(--bg)] text-[var(--text-muted)] hover:text-[var(--text-h)]',
              ].join(' ')}
            >
              {m}
            </button>
          ))}
          {modelChoices.length === 0 && !modelsLoading && (
            <span className="text-[12px] text-[var(--text-muted)]">网关未返回列表，可手填下方。</span>
          )}
        </div>
        <input
          type="text"
          autoComplete="off"
          value={modelDraft}
          onChange={(e) => onModelDraft(e.target.value)}
          placeholder="模型 id，例如 deepseek-v4-flash"
          className={`mt-2.5 ${fieldClass}`}
        />
      </SettingsCard>

      <SettingsCard title="生成参数">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[13px] text-[var(--text-h)]">Temperature</div>
              <div className="text-[11px] text-[var(--text-muted)]">{tempDraft.toFixed(2)} · 越高越发散</div>
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
              <div className="text-[13px] text-[var(--text-h)]">Max Tokens</div>
              <div className="text-[11px] text-[var(--text-muted)]">单次回复最大长度</div>
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
      </SettingsCard>

      <div className="flex items-center gap-3 pt-1">
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

const fieldClass =
  'w-full rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--text-h)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--accent)]'

function SettingsCard({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: ReactNode
}) {
  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3.5 py-3">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <h3 className="text-[13px] font-medium text-[var(--text-h)]">{title}</h3>
        {hint && <span className="text-[10px] text-[var(--text-muted)]">{hint}</span>}
      </div>
      {children}
    </section>
  )
}

function SettingsNavIcon({ name }: { name: SectionIcon }) {
  const common = {
    xmlns: 'http://www.w3.org/2000/svg',
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.75,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className: 'h-4 w-4',
    'aria-hidden': true as const,
  }
  switch (name) {
    case 'model':
      return (
        <svg {...common}>
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
          <path d="M3.3 7L12 12l8.7-5M12 22V12" />
        </svg>
      )
    case 'appearance':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 3v18" />
          <path d="M12 3a9 9 0 010 18" fill="currentColor" stroke="none" opacity={0.35} />
        </svg>
      )
    case 'agent':
      return (
        <svg {...common}>
          <path d="M22 3H2l8 9.5V19l4 2v-8.5L22 3z" />
        </svg>
      )
    case 'skills':
      return (
        <svg {...common}>
          <path d="M13 2L3 14h8l-1 8 10-12h-8l1-8z" />
        </svg>
      )
    case 'memory':
      return (
        <svg {...common}>
          <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
        </svg>
      )
    case 'cli':
      return (
        <svg {...common}>
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M7 9l3 3-3 3M12 15h5" />
        </svg>
      )
    case 'assets':
      return (
        <svg {...common}>
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
        </svg>
      )
    case 'audit':
      return (
        <svg {...common}>
          <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
          <rect x="9" y="3" width="6" height="4" rx="1" />
          <path d="M9 12h6M9 16h4" />
        </svg>
      )
    case 'shortcuts':
      return (
        <svg {...common}>
          <rect x="2" y="6" width="20" height="12" rx="2" />
          <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8" />
        </svg>
      )
    case 'data':
      return (
        <svg {...common}>
          <ellipse cx="12" cy="5" rx="8" ry="3" />
          <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
          <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
        </svg>
      )
    case 'about':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
      )
    default:
      return null
  }
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
    <div className={`mb-2.5 flex items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3.5 py-2.5 ${disabled ? 'opacity-60' : ''}`}>
      <div>
        <div className="text-[13px] text-[var(--text-h)]">{label}</div>
        {description && <div className="text-[11px] text-[var(--text-muted)]">{description}</div>}
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
