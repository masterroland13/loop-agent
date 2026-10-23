import { useEffect, useRef, useState } from 'react'
import { fetchAgentSettings, updateAgentSettings } from '../api/agent'
import { normalizeLocale } from '../i18n'

export type FontSize = 'small' | 'medium' | 'large'
export type LoopPreset = 'yolo' | 'trusted' | 'strict'

export interface SettingsState {
  theme: 'dark' | 'light' | 'system'
  fontSize: FontSize
  language: 'zh' | 'en'
  autoCompress: boolean
  contextLimit: number
  confirmMemory: boolean
  loopPreset: LoopPreset
  activeSkills: string[]
  approvalTimeoutSec: number
  maxToolIters: number
  checkpointEveryNTools: number
  explorationRepeatThreshold: number
  enterToSend: boolean
  shortcuts: boolean
  dataDir: string
}

const SETTINGS_KEY = 'agent-chat:settings'

export const defaultSettings: SettingsState = {
  theme: 'dark',
  fontSize: 'medium',
  language: 'zh',
  autoCompress: false,
  contextLimit: 8192,
  confirmMemory: true,
  loopPreset: 'yolo',
  activeSkills: [],
  approvalTimeoutSec: 300,
  maxToolIters: 24,
  checkpointEveryNTools: 4,
  explorationRepeatThreshold: 6,
  enterToSend: true,
  shortcuts: true,
  dataDir: '',
}

const AGENT_KEYS = new Set<keyof SettingsState>([
  'autoCompress',
  'confirmMemory',
  'loopPreset',
  'contextLimit',
  'activeSkills',
  'approvalTimeoutSec',
  'maxToolIters',
  'checkpointEveryNTools',
  'explorationRepeatThreshold',
])

function normalizeLoopPreset(value: unknown): LoopPreset {
  const raw = String(value || 'yolo').trim().toLowerCase()
  if (raw === 'trusted' || raw === 'strict' || raw === 'yolo') return raw
  return 'yolo'
}

export function loadSettings(): SettingsState {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (!raw) return defaultSettings
    const parsed = JSON.parse(raw)
    return {
      ...defaultSettings,
      ...parsed,
      language: normalizeLocale(parsed.language),
      activeSkills: Array.isArray(parsed.activeSkills) ? parsed.activeSkills : [],
      loopPreset: normalizeLoopPreset(parsed.loopPreset),
    }
  } catch {
    return defaultSettings
  }
}

export function saveSettings(settings: SettingsState) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  } catch {
    // ignore
  }
}

export function useSettings(sessionId?: string | null) {
  const [settings, setSettings] = useState<SettingsState>(() => loadSettings())
  const firstMount = useRef(true)
  const syncingFromApi = useRef(false)
  const prevAgent = useRef({
    autoCompress: settings.autoCompress,
    confirmMemory: settings.confirmMemory,
    loopPreset: settings.loopPreset,
    contextLimit: settings.contextLimit,
    activeSkills: settings.activeSkills,
    approvalTimeoutSec: settings.approvalTimeoutSec,
    maxToolIters: settings.maxToolIters,
    checkpointEveryNTools: settings.checkpointEveryNTools,
    explorationRepeatThreshold: settings.explorationRepeatThreshold,
  })

  useEffect(() => {
    let cancelled = false
    fetchAgentSettings()
      .then((remote) => {
        if (cancelled) return
        syncingFromApi.current = true
        setSettings((prev) => {
          const next = {
            ...prev,
            autoCompress: remote.auto_compress,
            confirmMemory: remote.confirm_memory,
            loopPreset: normalizeLoopPreset(remote.loop_preset),
            contextLimit: remote.context_limit,
            activeSkills: Array.isArray(remote.active_skills) ? remote.active_skills : [],
            approvalTimeoutSec: remote.approval_timeout_sec ?? 300,
            maxToolIters: remote.max_tool_iters ?? 24,
            checkpointEveryNTools: remote.checkpoint_every_n_tools ?? 4,
            explorationRepeatThreshold: remote.exploration_repeat_threshold ?? 6,
          }
          prevAgent.current = {
            autoCompress: next.autoCompress,
            confirmMemory: next.confirmMemory,
            loopPreset: next.loopPreset,
            contextLimit: next.contextLimit,
            activeSkills: next.activeSkills,
            approvalTimeoutSec: next.approvalTimeoutSec,
            maxToolIters: next.maxToolIters,
            checkpointEveryNTools: next.checkpointEveryNTools,
            explorationRepeatThreshold: next.explorationRepeatThreshold,
          }
          return next
        })
      })
      .catch(() => {
        // backend may be down; keep local defaults
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (firstMount.current) {
      firstMount.current = false
      return
    }
    saveSettings(settings)

    if (syncingFromApi.current) {
      syncingFromApi.current = false
      return
    }

    const agentChanged =
      settings.autoCompress !== prevAgent.current.autoCompress ||
      settings.confirmMemory !== prevAgent.current.confirmMemory ||
      settings.loopPreset !== prevAgent.current.loopPreset ||
      settings.contextLimit !== prevAgent.current.contextLimit ||
      settings.approvalTimeoutSec !== prevAgent.current.approvalTimeoutSec ||
      settings.maxToolIters !== prevAgent.current.maxToolIters ||
      settings.checkpointEveryNTools !== prevAgent.current.checkpointEveryNTools ||
      settings.explorationRepeatThreshold !== prevAgent.current.explorationRepeatThreshold ||
      settings.activeSkills.length !== prevAgent.current.activeSkills.length ||
      settings.activeSkills.some((id, i) => id !== prevAgent.current.activeSkills[i])

    if (!agentChanged) return

    prevAgent.current = {
      autoCompress: settings.autoCompress,
      confirmMemory: settings.confirmMemory,
      loopPreset: settings.loopPreset,
      contextLimit: settings.contextLimit,
      activeSkills: settings.activeSkills,
      approvalTimeoutSec: settings.approvalTimeoutSec,
      maxToolIters: settings.maxToolIters,
      checkpointEveryNTools: settings.checkpointEveryNTools,
      explorationRepeatThreshold: settings.explorationRepeatThreshold,
    }

    updateAgentSettings({
      auto_compress: settings.autoCompress,
      confirm_memory: settings.confirmMemory,
      loop_preset: settings.loopPreset,
      context_limit: settings.contextLimit,
      active_skills: settings.activeSkills,
      approval_timeout_sec: settings.approvalTimeoutSec,
      max_tool_iters: settings.maxToolIters,
      checkpoint_every_n_tools: settings.checkpointEveryNTools,
      exploration_repeat_threshold: settings.explorationRepeatThreshold,
    }, sessionId || undefined).catch(() => {
      // ignore transient sync errors
    })
  }, [settings, sessionId])

  const update = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  const toggleSkill = (skillId: string) => {
    setSettings((prev) => {
      const has = prev.activeSkills.includes(skillId)
      const next = has ? prev.activeSkills.filter((id) => id !== skillId) : [...prev.activeSkills, skillId]
      return { ...prev, activeSkills: next }
    })
  }

  return { settings, update, setSettings, toggleSkill, agentKeys: AGENT_KEYS }
}

export function applyTheme(theme: SettingsState['theme']) {
  if (theme === 'system') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light')
  } else {
    document.documentElement.setAttribute('data-theme', theme)
  }
}

export function applyFontSize(size: FontSize) {
  const root = document.documentElement
  root.classList.remove('text-sm', 'text-base', 'text-lg')
  if (size === 'small') root.classList.add('text-sm')
  else if (size === 'large') root.classList.add('text-lg')
  else root.classList.add('text-base')
}
