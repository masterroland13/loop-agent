import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  activateModelProfile,
  createModelProfile,
  deleteModelProfile,
  fetchAssets,
  fetchAudit,
  fetchMemoryContent,
  fetchModelProfiles,
  fetchProviderPresets,
  fetchSkills,
  fetchTools,
  testModelProfile,
  updateAgentSettings,
  updateModelGlobals,
  updateModelProfile,
  updateMemoryContent,
  type AssetsStatus,
  type LlmTestResult,
  type ModelProfilesList,
  type ProviderPreset,
  type SkillInfo,
  type ToolInfo,
} from '../api/agent'
import type { SettingsState } from '../hooks/useSettings'
import { useT } from '../i18n'
import { AuditPanel } from './AuditPanel'
import { ChevronIcon } from './ChevronIcon'

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

const SECTION_DEFS = [
  { id: 'model', labelKey: 'settings.nav.model', icon: 'model' },
  { id: 'preferences', labelKey: 'settings.nav.preferences', icon: 'appearance' },
  { id: 'agent', labelKey: 'settings.nav.agent', icon: 'agent' },
  { id: 'skills', labelKey: 'settings.nav.skills', icon: 'skills' },
  { id: 'memory', labelKey: 'settings.nav.memory', icon: 'memory' },
  { id: 'cli', labelKey: 'settings.nav.cli', icon: 'cli' },
  { id: 'assets', labelKey: 'settings.nav.assets', icon: 'assets' },
  { id: 'audit', labelKey: 'settings.nav.audit', icon: 'audit' },
  { id: 'shortcuts', labelKey: 'settings.nav.shortcuts', icon: 'shortcuts' },
  { id: 'data', labelKey: 'settings.nav.data', icon: 'data' },
  { id: 'about', labelKey: 'settings.nav.about', icon: 'about' },
] as const

type SectionId = (typeof SECTION_DEFS)[number]['id']
type SectionIcon = (typeof SECTION_DEFS)[number]['icon']

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
  const t = useT()
  const sections = useMemo(
    () => SECTION_DEFS.map((s) => ({ ...s, label: t(s.labelKey) })),
    [t],
  )
  const [activeSection, setActiveSection] = useState<SectionId>('model')
  const [assets, setAssets] = useState<AssetsStatus | null>(null)
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [agentsMdExists, setAgentsMdExists] = useState(false)
  const [skillsLoading, setSkillsLoading] = useState(false)
  const [skillsError, setSkillsError] = useState<string | null>(null)
  const [skillExpanded, setSkillExpanded] = useState<Record<string, boolean>>({})
  const [loadError, setLoadError] = useState<string | null>(null)
  const [profilesList, setProfilesList] = useState<ModelProfilesList | null>(null)
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [disabledTools, setDisabledTools] = useState<string[]>([])
  const [memoryDraft, setMemoryDraft] = useState('')
  const [memoryPath, setMemoryPath] = useState('')
  const [projectMemoryDraft, setProjectMemoryDraft] = useState('')
  const [projectMemoryPath, setProjectMemoryPath] = useState('')
  const [memorySaving, setMemorySaving] = useState(false)
  const [memoryHint, setMemoryHint] = useState<string | null>(null)
  const [projectMemoryHint, setProjectMemoryHint] = useState<string | null>(null)

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
    Promise.all([
      fetchAssets(),
      fetchSkills(),
      fetchModelProfiles(),
      fetchTools(),
      fetchMemoryContent('user'),
      fetchMemoryContent('memory'),
    ])
      .then(([a, s, profiles, t, mem, proj]) => {
        if (cancelled) return
        setAssets(a)
        setSkills(s.skills)
        setAgentsMdExists(s.agents_md_exists)
        setProfilesList(profiles)
        setTools(t.tools)
        setDisabledTools(t.disabled_tools)
        setMemoryDraft(mem.content)
        setMemoryPath(mem.path)
        setProjectMemoryDraft(proj.content)
        setProjectMemoryPath(proj.path)
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(err instanceof Error ? err.message : t('settings.loadAssetsFailed'))
      })
      .finally(() => {
        if (!cancelled) setSkillsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [isOpen, t])

  if (!isOpen) return null

  const activeMeta = sections.find((s) => s.id === activeSection) ?? sections[0]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative flex h-[82vh] w-full max-w-4xl overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-xl">
        <nav className="flex w-48 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-[var(--border-subtle)] bg-[var(--surface)]/30 p-2">
          <div className="px-2.5 pb-2 pt-1.5 text-[14px] font-semibold text-[var(--text-h)]">{t('settings.title')}</div>
          {sections.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setActiveSection(s.id)}
              className={[
                'flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[14px] transition-colors',
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
            <h2 className="text-[14px] font-semibold text-[var(--text-h)]">{activeMeta.label}</h2>
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

          <div className="flex-1 overflow-y-auto px-5 py-4 text-[14px] leading-relaxed">
            <div className="mx-auto w-full max-w-xl space-y-3">
            {activeSection === 'model' && (
              <ModelProfilesSection list={profilesList} onChange={setProfilesList} />
            )}

            {activeSection === 'preferences' && (
              <>
                <SettingsCard title={t('settings.theme')}>
                  <div className="grid grid-cols-3 gap-2">
                    <Choice label={t('settings.themeDark')} active={settings.theme === 'dark'} onClick={() => onChange('theme', 'dark')} />
                    <Choice label={t('settings.themeLight')} active={settings.theme === 'light'} onClick={() => onChange('theme', 'light')} />
                    <Choice label={t('settings.themeSystem')} active={settings.theme === 'system'} onClick={() => onChange('theme', 'system')} />
                  </div>
                </SettingsCard>
                <SettingsCard title={t('settings.fontSize')}>
                  <div className="grid grid-cols-3 gap-2">
                    <Choice label={t('settings.fontSmall')} active={settings.fontSize === 'small'} onClick={() => onChange('fontSize', 'small')} />
                    <Choice label={t('settings.fontMedium')} active={settings.fontSize === 'medium'} onClick={() => onChange('fontSize', 'medium')} />
                    <Choice label={t('settings.fontLarge')} active={settings.fontSize === 'large'} onClick={() => onChange('fontSize', 'large')} />
                  </div>
                </SettingsCard>
                <SettingsCard title={t('settings.language')} hint={t('settings.languageHint')}>
                  <div className="grid grid-cols-2 gap-2">
                    <Choice
                      label={t('settings.languageZh')}
                      active={settings.language === 'zh'}
                      onClick={() => onChange('language', 'zh')}
                    />
                    <Choice
                      label={t('settings.languageEn')}
                      active={settings.language === 'en'}
                      onClick={() => onChange('language', 'en')}
                    />
                  </div>
                </SettingsCard>
              </>
            )}

            {activeSection === 'agent' && (
              <>
            <Toggle
              label={t('settings.autoCompress')}
              description={t('settings.autoCompressDesc')}
              checked={settings.autoCompress}
              onChange={(v) => onChange('autoCompress', v)}
            />
            <Toggle
              label={t('settings.confirmMemory')}
              description={t('settings.confirmMemoryDesc')}
              checked={settings.confirmMemory}
              onChange={(v) => onChange('confirmMemory', v)}
            />
            <div className="mt-3">
              <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.preset')}</div>
              <div className="mt-0.5 text-[14px] text-[var(--text-muted)]">
                {t('settings.presetDesc')}
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2">
                <Choice
                  label="YOLO"
                  active={settings.loopPreset === 'yolo'}
                  onClick={() => onChange('loopPreset', 'yolo')}
                />
                <Choice
                  label="Trusted"
                  active={settings.loopPreset === 'trusted'}
                  onClick={() => onChange('loopPreset', 'trusted')}
                />
                <Choice
                  label="Strict"
                  active={settings.loopPreset === 'strict'}
                  onClick={() => onChange('loopPreset', 'strict')}
                />
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.contextLimit')}</div>
                <div className="text-[14px] text-[var(--text-muted)]">{settings.contextLimit.toLocaleString()} tokens</div>
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
              explorationRepeatThreshold={settings.explorationRepeatThreshold ?? 6}
              onExplorationRepeatThreshold={(v) => onChange('explorationRepeatThreshold', v)}
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
            {skillsLoading && <p className="text-[14px] text-[var(--text-muted)]">{t('settings.loading')}</p>}
            {skillsError && (
              <p className="text-[14px] text-amber-400">{skillsError}</p>
            )}
            {skills.length === 0 && !skillsLoading && !skillsError ? (
              <p className="text-[14px] text-[var(--text-muted)]">
                {t('settings.skillsEmpty')}
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
                          className="flex flex-1 items-center gap-1 text-left text-[14px] text-[var(--text-h)]"
                        >
                          <span className="text-[var(--text-dim)]">{skillExpanded[skill.id] ? '▾' : '▸'}</span>
                          <span className="font-medium">{skill.name}</span>
                          <span className="font-mono text-[var(--text-muted)]">{skill.id}</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => onToggleSkill(skill.id)}
                          className={[
                            'rounded-md px-2 py-1 text-[14px]',
                            active
                              ? 'bg-[var(--text-h)] text-[var(--bg)]'
                              : 'border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-h)]',
                          ].join(' ')}
                        >
                          {active ? t('settings.skillOn') : t('settings.skillOff')}
                        </button>
                      </div>
                      {skillExpanded[skill.id] && (
                        <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap text-[14px] text-[var(--text-muted)]">
                          {skill.description ? `${skill.description}\n\n` : ''}
                          {skill.preview}
                        </pre>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
            <p className="mt-2 text-[14px] text-[var(--text-muted)]">
              {agentsMdExists ? t('settings.agentsMdYes') : t('settings.agentsMdNo')}
            </p>
              </>
            )}

            {activeSection === 'memory' && (
              <div className="space-y-4">
                <MemorySection
                  title={t('settings.memoryUser')}
                  draft={memoryDraft}
                  path={memoryPath}
                  saving={memorySaving}
                  hint={memoryHint}
                  usageLabel={
                    assets
                      ? `${assets.user_md_chars ?? 0}/${assets.user_md_limit ?? 1375} chars`
                      : undefined
                  }
                  onDraft={setMemoryDraft}
                  onSave={async () => {
                    setMemorySaving(true)
                    setMemoryHint(null)
                    try {
                      await updateMemoryContent(memoryDraft, 'user')
                      setMemoryHint(t('settings.memorySaved'))
                    } finally {
                      setMemorySaving(false)
                    }
                  }}
                  onClear={async () => {
                    if (!window.confirm(t('settings.memoryClearUserConfirm'))) return
                    setMemorySaving(true)
                    try {
                      await updateMemoryContent('', 'user')
                      setMemoryDraft('')
                      setMemoryHint(t('settings.memoryCleared'))
                    } finally {
                      setMemorySaving(false)
                    }
                  }}
                />
                <MemorySection
                  title={t('settings.memoryProject')}
                  draft={projectMemoryDraft}
                  path={projectMemoryPath}
                  saving={memorySaving}
                  hint={projectMemoryHint}
                  usageLabel={
                    assets
                      ? `${assets.memory_md_chars ?? 0}/${assets.memory_md_limit ?? 2200} chars`
                      : undefined
                  }
                  onDraft={setProjectMemoryDraft}
                  onSave={async () => {
                    setMemorySaving(true)
                    setProjectMemoryHint(null)
                    try {
                      const saved = await updateMemoryContent(projectMemoryDraft, 'memory')
                      setProjectMemoryPath(saved.path)
                      setProjectMemoryHint(t('settings.memorySaved'))
                      const a = await fetchAssets()
                      setAssets(a)
                    } finally {
                      setMemorySaving(false)
                    }
                  }}
                  onClear={async () => {
                    if (!window.confirm(t('settings.memoryClearProjectConfirm'))) return
                    setMemorySaving(true)
                    try {
                      await updateMemoryContent('', 'memory')
                      setProjectMemoryDraft('')
                      setProjectMemoryHint(t('settings.memoryCleared'))
                      const a = await fetchAssets()
                      setAssets(a)
                    } finally {
                      setMemorySaving(false)
                    }
                  }}
                />
              </div>
            )}

            {activeSection === 'cli' && <CliSection />}

            {activeSection === 'about' && <AboutSection />}

            {activeSection === 'assets' && (
              <>
            {loadError && (
              <p className="mb-2 text-[14px] text-red-400">{loadError}</p>
            )}
            {assets ? (
              <div className="space-y-1.5 rounded-lg bg-[var(--surface)] px-3 py-3 text-[14px] text-[var(--text-muted)]">
                <Row
                  label={t('settings.assetsHealth')}
                  value={`${assets.status} · ${assets.provider}${assets.provider_available ? '' : t('settings.assetsUnavailable')}`}
                />
                <Row label={t('settings.assetsSessions')} value={String(assets.session_count)} />
                <Row
                  label="USER.md"
                  value={
                    assets.user_md_exists
                      ? `${assets.user_md_size} B`
                      : t('settings.assetsNotCreated')
                  }
                />
                <Row
                  label={t('settings.assetsWorkspace')}
                  value={
                    assets.workspace_configured
                      ? assets.workspace_root || t('settings.assetsConfigured')
                      : t('settings.assetsUnbound')
                  }
                />
                <Row
                  label={t('settings.assetsCompressMemory')}
                  value={`${assets.settings.auto_compress ? t('settings.assetsOn') : t('settings.assetsOff')} / ${assets.settings.confirm_memory ? t('settings.assetsOn') : t('settings.assetsOff')}`}
                />
                <Row
                  label="Preset"
                  value={String(assets.settings.loop_preset || 'yolo')}
                />
                <Row label={t('settings.contextLimit')} value={String(assets.settings.context_limit)} />
              </div>
            ) : (
              !loadError && <p className="text-[14px] text-[var(--text-muted)]">{t('settings.loading')}</p>
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
              label={t('settings.enterToSend')}
              description={t('settings.enterToSendDesc')}
              checked={settings.enterToSend}
              onChange={(v) => onChange('enterToSend', v)}
            />
            <Toggle
              label={t('settings.navShortcuts')}
              description={t('settings.navShortcutsDesc')}
              checked={settings.shortcuts}
              onChange={(v) => onChange('shortcuts', v)}
            />
            <div className="mt-3 rounded-lg bg-[var(--surface)] px-3 py-2 text-[14px] text-[var(--text-muted)]">
              <div className="flex justify-between py-1"><span>{t('settings.shortcutNew')}</span><span className="font-mono text-[var(--text-h)]">Ctrl+N</span></div>
              <div className="flex justify-between py-1"><span>{t('settings.shortcutStop')}</span><span className="font-mono text-[var(--text-h)]">Esc</span></div>
              <div className="flex justify-between py-1"><span>{t('settings.shortcutNav')}</span><span className="font-mono text-[var(--text-h)]">↑ / ↓</span></div>
              <div className="flex justify-between py-1"><span>{t('settings.shortcutSettings')}</span><span className="font-mono text-[var(--text-h)]">Ctrl+,</span></div>
            </div>
              </>
            )}

            {activeSection === 'data' && (
              <>
            <div className="rounded-lg bg-[var(--surface)] px-3 py-3">
              <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.dataLocal')}</div>
              <div className="mt-1 text-[14px] text-[var(--text-muted)]">{t('settings.dataLocalDesc')}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const payload = JSON.stringify({ exportedAt: new Date().toISOString(), settings }, null, 2)
                    const blob = new Blob([payload], { type: 'application/json' })
                    const url = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = url
                    a.download = `loop-agent-settings-${Date.now()}.json`
                    a.click()
                    URL.revokeObjectURL(url)
                  }}
                  className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-[14px] text-[var(--text-h)] hover:bg-[var(--surface-hover)]"
                >
                  {t('settings.exportSettings')}
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
                      a.download = `loop-agent-audit-${Date.now()}.json`
                      a.click()
                      URL.revokeObjectURL(url)
                    })
                  }}
                  className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-[14px] text-[var(--text-h)] hover:bg-[var(--surface-hover)]"
                >
                  {t('settings.exportAudit')}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(t('settings.resetConfirm'))) {
                      localStorage.removeItem('agent-chat:settings')
                      localStorage.removeItem('agent-chat:theme')
                      window.location.reload()
                    }
                  }}
                  className="rounded-md border border-red-900/40 bg-red-950/20 px-3 py-1.5 text-[14px] text-red-400 hover:bg-red-950/40"
                >
                  {t('settings.resetSettings')}
                </button>
              </div>
            </div>
              </>
            )}
            </div>
          </div>

          <div className="border-t border-[var(--border-subtle)] px-5 py-2.5 text-center text-[14px] text-[var(--text-dim)]">
            {t('settings.footer')}
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
  explorationRepeatThreshold,
  onExplorationRepeatThreshold,
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
  explorationRepeatThreshold: number
  onExplorationRepeatThreshold: (value: number) => void
  onToggleTool: (name: string) => void
}) {
  const t = useT()
  return (
    <>
      <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-4">
        <div>
          <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.approvalTimeout')}</div>
          <div className="text-[14px] text-[var(--text-muted)]">
            {t('settings.approvalTimeoutDesc', { sec: approvalTimeout })}
          </div>
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
          <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.maxToolIters')}</div>
          <div className="text-[14px] text-[var(--text-muted)]">
            {t('settings.maxToolItersDesc', { n: maxToolIters })}
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
          <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.checkpoint')}</div>
          <div className="text-[14px] text-[var(--text-muted)]">
            {checkpointEveryNTools === 0
              ? t('settings.checkpointGateOnly')
              : t('settings.checkpointEvery', { n: checkpointEveryNTools })}
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

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] pt-4">
        <div>
          <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.exploration')}</div>
          <div className="text-[14px] text-[var(--text-muted)]">
            {explorationRepeatThreshold === 0
              ? t('settings.explorationOff')
              : t('settings.explorationOn', { n: explorationRepeatThreshold })}
          </div>
        </div>
        <input
          type="range"
          min={0}
          max={12}
          step={1}
          value={explorationRepeatThreshold}
          onChange={(e) => {
            const raw = Number(e.target.value)
            // Backend: 0=off; else clamp 3–12 (skip 1–2 dead zone in UI).
            onExplorationRepeatThreshold(raw === 0 ? 0 : Math.max(3, raw))
          }}
          className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-[var(--border)] accent-[var(--accent)]"
        />
      </div>

      <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
        <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.turnGoalTitle')}</div>
        <div className="mt-1 text-[14px] leading-relaxed text-[var(--text-muted)]">{t('settings.turnGoalBody')}</div>
        <div className="mt-2 text-[14px] leading-relaxed text-[var(--text-dim)]">{t('settings.turnGoalCheckpoint')}</div>
      </div>

      <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
        <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.toolsTitle')}</div>
        <div className="mb-2 text-[14px] text-[var(--text-muted)]">{t('settings.toolsHint')}</div>
        {tools.length === 0 ? (
          <p className="text-[14px] text-[var(--text-muted)]">{t('settings.loading')}</p>
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
                    'rounded-lg px-2.5 py-1.5 text-left font-mono text-[14px] transition-colors',
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
  title,
  draft,
  path,
  saving,
  hint,
  usageLabel,
  onDraft,
  onSave,
  onClear,
}: {
  title: string
  draft: string
  path: string
  saving: boolean
  hint: string | null
  usageLabel?: string
  onDraft: (value: string) => void
  onSave: () => Promise<void>
  onClear: () => Promise<void>
}) {
  const t = useT()
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="text-[14px] font-medium text-[var(--text-h)]">{title}</div>
          <div className="flex min-w-0 flex-col items-end gap-0.5">
            {usageLabel && (
              <span className="font-mono text-[14px] text-[var(--text-muted)]">{usageLabel}</span>
            )}
            <span className="max-w-[55%] truncate font-mono text-[14px] text-[var(--text-dim)]" title={path}>
              {path}
            </span>
          </div>
        </div>
        <textarea
          value={draft}
          onChange={(e) => onDraft(e.target.value)}
          placeholder={t('settings.memoryPlaceholder')}
          rows={10}
          className="w-full resize-y rounded-lg border border-[var(--border)] bg-[var(--bg)] px-3 py-2 font-mono text-[14px] leading-relaxed text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)] focus:border-[var(--accent)]"
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            disabled={saving}
            onClick={() => void onSave()}
            className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-[14px] text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
          >
            {saving ? t('settings.saving') : t('settings.save')}
          </button>
          <button
            type="button"
            disabled={saving || !draft.trim()}
            onClick={() => void onClear()}
            className="rounded-md border border-red-900/40 bg-red-950/20 px-3 py-1.5 text-[14px] text-red-400 hover:bg-red-950/40 disabled:opacity-40"
          >
            {t('settings.memoryClear')}
          </button>
          {hint && <span className="text-[14px] text-emerald-400">{hint}</span>}
        </div>
        <p className="mt-2 text-[14px] text-[var(--text-muted)]">{t('settings.memoryEditHint')}</p>
      </div>
    </div>
  )
}

function CliSection() {
  const t = useT()
  const commands = [
    { cmd: 'loop ask "question"', descKey: 'settings.cliAsk' as const },
    { cmd: 'loop status', descKey: 'settings.cliStatus' as const },
    { cmd: 'loop approve --patch-id <id>', descKey: 'settings.cliApprove' as const },
    { cmd: 'loop reject --shell-id <id>', descKey: 'settings.cliReject' as const },
    { cmd: 'loop run --wait -s <session> "task"', descKey: 'settings.cliRun' as const },
    { cmd: 'loop sessions', descKey: 'settings.cliSessions' as const },
  ]
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 text-[14px] font-medium text-[var(--text-h)]">{t('settings.cliConfig')}</div>
        <p className="font-mono text-[14px] text-[var(--text-muted)]">~/.config/loop-agent/config.json</p>
        <p className="mt-1 text-[14px] text-[var(--text-dim)]">{t('settings.cliConfigHint')}</p>
      </div>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3">
        <div className="mb-2 text-[14px] font-medium text-[var(--text-h)]">{t('settings.cliCommands')}</div>
        <div className="space-y-1.5">
          {commands.map((c) => (
            <div key={c.cmd} className="flex items-baseline justify-between gap-3">
              <code className="rounded bg-[var(--bg)] px-1.5 py-0.5 font-mono text-[14px] text-[var(--text-h)]">
                {c.cmd}
              </code>
              <span className="shrink-0 text-[14px] text-[var(--text-muted)]">{t(c.descKey)}</span>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[14px] text-[var(--text-dim)]">{t('settings.cliVenv')}</p>
      </div>
    </div>
  )
}

function AboutSection() {
  const t = useT()
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-4">
        <img src="/favicon.svg" alt="Loop Agent" className="h-12 w-12" />
        <div>
          <div className="text-[14px] font-semibold text-[var(--text-h)]">Loop Agent</div>
          <div className="mt-0.5 text-[14px] text-[var(--text-muted)]">{t('settings.aboutTagline')}</div>
        </div>
      </div>
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3 py-3 text-[14px] text-[var(--text-muted)]">
        <div className="flex justify-between py-1"><span>{t('settings.aboutBackend')}</span><span className="font-mono text-[var(--text-h)]">loop-agent-backend 0.1.0</span></div>
        <div className="flex justify-between py-1"><span>{t('settings.aboutRoadmap')}</span><span className="font-mono text-[var(--text-h)]">docs/agent-window-roadmap.md</span></div>
        <div className="flex justify-between py-1"><span>{t('settings.aboutChangelog')}</span><span className="font-mono text-[var(--text-h)]">CHANGELOG.md</span></div>
        <div className="flex justify-between py-1"><span>{t('settings.aboutCli')}</span><span className="font-mono text-[var(--text-h)]">docs/design/v1-7-headless-cli-design.md</span></div>
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
        'rounded-lg px-2 py-2 text-[14px] transition-colors',
        active
          ? 'bg-[var(--accent-bg)] font-medium text-[var(--text-h)]'
          : 'bg-[var(--surface)] text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
      ].join(' ')}
    >
      {label}
    </button>
  )
}

function ModelProfilesSection({
  list,
  onChange,
}: {
  list: ModelProfilesList | null
  onChange: (next: ModelProfilesList) => void
}) {
  const t = useT()
  const [presets, setPresets] = useState<ProviderPreset[]>([])
  const [presetId, setPresetId] = useState('router')
  const [presetsReady, setPresetsReady] = useState(false)
  const [addingPreset, setAddingPreset] = useState(false)
  const addingPresetRef = useRef(false)
  const [drafts, setDrafts] = useState<
    Record<string, { label: string; base_url: string; model_id: string; api_key: string }>
  >({})
  const [tempDraft, setTempDraft] = useState(0.7)
  const [tokensDraft, setTokensDraft] = useState(2048)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hint, setHint] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, LlmTestResult>>({})
  const [globalsSaving, setGlobalsSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchProviderPresets()
      .then((rows) => {
        if (cancelled) return
        setPresets(rows)
        if (rows.length > 0 && !rows.some((row) => row.id === 'router')) {
          setPresetId(rows[0].id)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPresets([])
          setError(t('settings.presetsLoadFailed'))
        }
      })
      .finally(() => {
        if (!cancelled) setPresetsReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [t])

  useEffect(() => {
    if (!list) return
    const next: typeof drafts = {}
    for (const p of list.profiles) {
      next[p.id] = {
        label: p.label,
        base_url: p.base_url,
        model_id: p.model_id,
        api_key: '',
      }
    }
    setDrafts(next)
    setTempDraft(list.temperature)
    setTokensDraft(list.max_tokens)
  }, [list])

  if (!list) {
    return <p className="text-[14px] text-[var(--text-muted)]">{t('settings.loading')}</p>
  }

  const patchDraft = (id: string, patch: Partial<(typeof drafts)[string]>) => {
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }))
  }

  const applyList = (next: ModelProfilesList) => {
    onChange(next)
    setHint(null)
  }

  return (
    <div className="space-y-4">
      {list.profiles.map((profile) => {
        const draft = drafts[profile.id] ?? {
          label: profile.label,
          base_url: profile.base_url,
          model_id: profile.model_id,
          api_key: '',
        }
        const isActive = profile.id === list.active_id
        const testResult = testResults[profile.id]
        const dirty =
          draft.label.trim() !== profile.label ||
          draft.base_url.trim() !== profile.base_url ||
          draft.model_id.trim() !== profile.model_id ||
          draft.api_key.trim().length > 0

        return (
          <div key={profile.id} className="space-y-2">
            <div>
              <div className="flex items-center gap-3">
                <input
                  type="text"
                  value={draft.label}
                  onChange={(e) => patchDraft(profile.id, { label: e.target.value })}
                  className="min-w-0 flex-1 border-0 bg-transparent p-0 text-[14px] font-medium leading-5 text-[var(--text-h)] outline-none focus:ring-0"
                  aria-label={t('settings.profileNameAria')}
                />
                <div className="flex h-5 shrink-0 items-center gap-3">
                  {isActive && (
                    <span className="inline-flex h-5 items-center rounded-md bg-[var(--accent-bg)] px-1.5 text-[14px] font-medium leading-none text-[var(--text-h)]">
                      {t('settings.profileActiveBadge')}
                    </span>
                  )}
                  <SwitchControl
                    checked={profile.enabled}
                    ariaLabel={t('settings.profileEnabledAria', { label: profile.label })}
                    disabled={busyId === profile.id}
                    onClick={() => {
                      void (async () => {
                        setBusyId(profile.id)
                        setError(null)
                        try {
                          applyList(await updateModelProfile(profile.id, { enabled: !profile.enabled }))
                        } catch (err) {
                          setError(err instanceof Error ? err.message : t('settings.updateFailed'))
                        } finally {
                          setBusyId(null)
                        }
                      })()
                    }}
                  />
                </div>
              </div>
              <p className="mt-0.5 text-[14px] leading-relaxed text-[var(--text-muted)]">
                {t('settings.profileEndpointHint')}
              </p>
            </div>

            <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)]">
              <ProfileRow
                label="Base URL"
                value={draft.base_url}
                placeholder="https://api.example.com/v1"
                onChange={(v) => patchDraft(profile.id, { base_url: v })}
              />
              <ProfileRow
                label="API Key"
                value={draft.api_key}
                type="password"
                placeholder={
                  profile.api_key_configured
                    ? t('settings.profileKeySavedPlaceholder')
                    : t('settings.profileKeyPastePlaceholder')
                }
                onChange={(v) => patchDraft(profile.id, { api_key: v })}
              />
              <ProfileRow
                label="Model ID"
                value={draft.model_id}
                placeholder="kimi-for-coding"
                onChange={(v) => patchDraft(profile.id, { model_id: v })}
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {!isActive && (
                <button
                  type="button"
                  disabled={busyId === profile.id}
                  onClick={() => {
                    void (async () => {
                      setBusyId(profile.id)
                      setError(null)
                      try {
                        applyList(await activateModelProfile(profile.id))
                        setHint(t('settings.profileActive'))
                      } catch (err) {
                        setError(err instanceof Error ? err.message : t('settings.activateFailed'))
                      } finally {
                        setBusyId(null)
                      }
                    })()
                  }}
                  className="rounded-md border border-[var(--border)] px-2.5 py-1 text-[14px] text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
                >
                  {t('settings.profileSetActive')}
                </button>
              )}
              <button
                type="button"
                disabled={busyId === profile.id}
                onClick={() => {
                  void (async () => {
                    setBusyId(profile.id)
                    setError(null)
                    try {
                      const result = await testModelProfile(profile.id)
                      setTestResults((prev) => ({ ...prev, [profile.id]: result }))
                    } catch (err) {
                      setTestResults((prev) => ({
                        ...prev,
                        [profile.id]: {
                          ok: false,
                          error: err instanceof Error ? err.message : t('settings.testFailed'),
                        },
                      }))
                    } finally {
                      setBusyId(null)
                    }
                  })()
                }}
                className="rounded-md border border-[var(--border)] px-2.5 py-1 text-[14px] text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
              >
                {t('settings.profileTest')}
              </button>
              <button
                type="button"
                disabled={busyId === profile.id || !dirty}
                onClick={() => {
                  void (async () => {
                    setBusyId(profile.id)
                    setError(null)
                    setHint(null)
                    try {
                      const patch: {
                        label?: string
                        base_url?: string
                        model_id?: string
                        api_key?: string
                      } = {
                        label: draft.label.trim(),
                        base_url: draft.base_url.trim(),
                        model_id: draft.model_id.trim(),
                      }
                      if (draft.api_key.trim()) patch.api_key = draft.api_key.trim()
                      applyList(await updateModelProfile(profile.id, patch))
                      setHint(t('settings.profileSaved'))
                    } catch (err) {
                      setError(err instanceof Error ? err.message : t('settings.saveFailed'))
                    } finally {
                      setBusyId(null)
                    }
                  })()
                }}
                className="rounded-md bg-[var(--accent-bg)] px-2.5 py-1 text-[14px] text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
              >
                {t('settings.save')}
              </button>
              <button
                type="button"
                disabled={busyId === profile.id || list.profiles.length <= 1}
                onClick={() => {
                  void (async () => {
                    setBusyId(profile.id)
                    setError(null)
                    try {
                      applyList(await deleteModelProfile(profile.id))
                      setHint(t('settings.profileDeleted'))
                    } catch (err) {
                      setError(err instanceof Error ? err.message : t('settings.deleteFailed'))
                    } finally {
                      setBusyId(null)
                    }
                  })()
                }}
                className="rounded-md border border-[var(--border)] px-2.5 py-1 text-[14px] text-red-400 hover:bg-[var(--surface-hover)] disabled:opacity-40"
              >
                {t('settings.profileDelete')}
              </button>
              {testResult && (
                <span className={`text-[14px] ${testResult.ok ? 'text-emerald-400' : 'text-red-400'}`}>
                  {testResult.ok
                    ? t('settings.profileTestOk', {
                        ms: testResult.latency_ms ?? 0,
                        count: testResult.model_count ?? 0,
                      })
                    : t('settings.profileTestFail', {
                        error: testResult.error || t('settings.profileTestUnknown'),
                      })}
                </span>
              )}
            </div>
          </div>
        )
      })}

      <div className="flex items-center gap-2">
        <div
          className={`relative min-w-0 flex-1 ${!presetsReady || addingPreset || presets.length === 0 ? 'opacity-50' : ''}`}
        >
          <select
            value={presets.some((row) => row.id === presetId) ? presetId : ''}
            onChange={(e) => setPresetId(e.target.value)}
            disabled={!presetsReady || addingPreset || presets.length === 0}
            className="w-full appearance-none rounded-lg border border-[var(--border)] bg-[var(--bg)] py-2 pl-2.5 pr-9 text-[14px] text-[var(--text-h)] outline-none focus:border-[var(--accent)]"
            aria-label={t('settings.addPreset')}
          >
          {presets.length === 0 ? (
            <option value="">{presetsReady ? t('settings.presetsLoadFailed') : t('model.loading')}</option>
          ) : (
            presets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.label}
              </option>
            ))
          )}
          </select>
          <ChevronIcon
            open
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          />
        </div>
        <button
          type="button"
          disabled={!presetsReady || addingPreset}
          onClick={() => {
            if (addingPresetRef.current) return
            addingPresetRef.current = true
            setAddingPreset(true)
            void (async () => {
              setError(null)
              const preset = presets.find((row) => row.id === presetId)
              try {
                if (!preset || preset.inherit_base_url) {
                  await createModelProfile({
                    label: preset?.label || t('settings.profileNew'),
                    model_id: preset?.model_id || 'kimi-k3',
                  })
                } else if (!preset.base_url.trim()) {
                  setError(t('settings.createFailed'))
                  return
                } else {
                  await createModelProfile({
                    label: preset.label,
                    base_url: preset.base_url,
                    model_id: preset.model_id,
                  })
                }
                applyList(await fetchModelProfiles())
              } catch (err) {
                setError(err instanceof Error ? err.message : t('settings.createFailed'))
              } finally {
                addingPresetRef.current = false
                setAddingPreset(false)
              }
            })()
          }}
          className="shrink-0 rounded-xl border border-dashed border-[var(--border)] px-3 py-2 text-[14px] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--text-h)] disabled:opacity-50"
        >
          {t('settings.addPreset')}
        </button>
      </div>

      <SettingsCard title={t('settings.genParams')} hint={t('settings.genParamsHint')}>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.genTemp')}</div>
              <div className="text-[14px] text-[var(--text-muted)]">
                {t('settings.genTempHint', { value: tempDraft.toFixed(2) })}
              </div>
            </div>
            <input
              type="range"
              min={0}
              max={2}
              step={0.05}
              value={tempDraft}
              onChange={(e) => setTempDraft(Number(e.target.value))}
              className="h-1.5 w-32 cursor-pointer appearance-none rounded-full bg-[var(--border)] accent-[var(--accent)]"
            />
          </div>
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[14px] font-medium text-[var(--text-h)]">{t('settings.genTokens')}</div>
              <div className="text-[14px] text-[var(--text-muted)]">{t('settings.genTokensHint')}</div>
            </div>
            <input
              type="number"
              min={256}
              max={200000}
              step={256}
              value={tokensDraft}
              onChange={(e) => setTokensDraft(Number(e.target.value))}
              className="w-28 rounded-lg border border-[var(--border)] bg-[var(--bg)] px-2.5 py-1.5 text-right font-mono text-[14px] text-[var(--text-h)] outline-none focus:border-[var(--accent)]"
            />
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              disabled={
                globalsSaving ||
                (tempDraft === list.temperature && tokensDraft === list.max_tokens)
              }
              onClick={() => {
                void (async () => {
                  setGlobalsSaving(true)
                  setError(null)
                  try {
                    applyList(
                      await updateModelGlobals({
                        temperature: tempDraft,
                        max_tokens: tokensDraft,
                      }),
                    )
                    setHint(t('settings.genSaved'))
                  } catch (err) {
                    setError(err instanceof Error ? err.message : t('settings.saveFailed'))
                  } finally {
                    setGlobalsSaving(false)
                  }
                })()
              }}
              className="rounded-md bg-[var(--accent-bg)] px-3 py-1.5 text-[14px] text-[var(--text-h)] hover:bg-[var(--surface-hover)] disabled:opacity-40"
            >
              {globalsSaving ? t('settings.saving') : t('settings.saveParams')}
            </button>
          </div>
        </div>
      </SettingsCard>

      {error && <p className="text-[14px] text-red-400">{error}</p>}
      {hint && <p className="text-[14px] text-emerald-400">{hint}</p>}
    </div>
  )
}

function ProfileRow({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
  last,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  type?: string
  last?: boolean
}) {
  return (
    <div
      className={[
        'flex items-center justify-between gap-3 px-3.5 py-2.5',
        last ? '' : 'border-b border-[var(--border-subtle)]',
      ].join(' ')}
    >
      <span className="shrink-0 text-[14px] text-[var(--text-muted)]">{label}</span>
      <input
        type={type}
        autoComplete="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 border-0 bg-transparent text-right text-[14px] text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)] focus:ring-0"
      />
    </div>
  )
}

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
      <div className="mb-2.5">
        <h3 className="whitespace-nowrap text-[14px] font-medium text-[var(--text-h)]">{title}</h3>
        {hint ? <div className="text-[14px] text-[var(--text-muted)]">{hint}</div> : null}
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

function SwitchControl({
  checked,
  onClick,
  disabled,
  ariaLabel,
  onTrackClass = 'bg-[var(--text-h)]',
  thumbClass = 'bg-[var(--bg)]',
}: {
  checked: boolean
  onClick: () => void
  disabled?: boolean
  ariaLabel?: string
  onTrackClass?: string
  thumbClass?: string
}) {
  // 36×20 track, 14px knob, 3px inset on all sides (top+bottom pin).
  // Avoids flex/half-pixel drift that made the knob hug one edge and look jagged.
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={onClick}
      className={[
        'relative box-border h-5 w-9 shrink-0 overflow-hidden rounded-full border-0 p-0 leading-none align-middle transition-colors',
        checked ? onTrackClass : 'bg-[var(--border)]',
        disabled ? 'cursor-not-allowed opacity-40' : '',
      ].join(' ')}
    >
      <span
        aria-hidden
        className={[
          'pointer-events-none absolute top-[3px] bottom-[3px] left-[3px] w-[14px] rounded-full',
          'transition-transform duration-200 ease-out',
          thumbClass,
          checked ? 'translate-x-4' : 'translate-x-0',
        ].join(' ')}
      />
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
    <div className={`mb-2.5 flex items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-3.5 py-2.5 ${disabled ? 'opacity-60' : ''}`}>
      <div>
        <div className="text-[14px] font-medium text-[var(--text-h)]">{label}</div>
        {description && <div className="text-[14px] text-[var(--text-muted)]">{description}</div>}
      </div>
      <SwitchControl
        checked={checked}
        disabled={disabled}
        onClick={() => {
          if (!disabled) onChange(!checked)
        }}
      />
    </div>
  )
}
