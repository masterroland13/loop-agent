import { useEffect, useState } from 'react'
import {
  fetchAssets,
  fetchAudit,
  fetchSkills,
  type AssetsStatus,
  type AuditEvent,
  type SkillInfo,
} from '../api/agent'
import type { SettingsState } from '../hooks/useSettings'

interface SettingsPanelProps {
  isOpen: boolean
  settings: SettingsState
  onClose: () => void
  onChange: <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => void
  onToggleSkill: (skillId: string) => void
}

export function SettingsPanel({ isOpen, settings, onClose, onChange, onToggleSkill }: SettingsPanelProps) {
  const [assets, setAssets] = useState<AssetsStatus | null>(null)
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [agentsMdExists, setAgentsMdExists] = useState(false)
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [skillsError, setSkillsError] = useState<string | null>(null)
  const [skillExpanded, setSkillExpanded] = useState<Record<string, boolean>>({})
  const [loadError, setLoadError] = useState<string | null>(null)

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
    Promise.all([fetchAssets(), fetchAudit(30), fetchSkills()])
      .then(([a, events, s]) => {
        if (cancelled) return
        setAssets(a)
        setAudit(events)
        setSkills(s.skills)
        setAgentsMdExists(s.agents_md_exists)
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative flex max-h-[85vh] w-full max-w-md flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-xl">
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-4">
          <h2 className="text-base font-semibold text-[var(--text-h)]">设置</h2>
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

        <div className="flex-1 overflow-y-auto px-5 py-5">
          <Section title="外观">
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
          </Section>

          <Section title="Agent">
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
          </Section>

          <Section title="技能 (Skills)">
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
          </Section>

          <Section title="资产">
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
          </Section>

          <Section title="最近审计">
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
          </Section>

          <Section title="快捷键">
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
          </Section>

          <Section title="数据">
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
          </Section>
        </div>

        <div className="border-t border-[var(--border-subtle)] px-5 py-3 text-center text-xs text-[var(--text-muted)]">
          外观存浏览器；Agent 开关同步到后端
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">{title}</h3>
      {children}
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
