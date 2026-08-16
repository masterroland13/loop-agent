import { useEffect, useRef, useState } from 'react'
import { fetchAgentSettings, updateAgentSettings } from '../api/agent'

export type FontSize = 'small' | 'medium' | 'large'

export interface SettingsState {
  theme: 'dark' | 'light' | 'system'
  fontSize: FontSize
  language: 'zh' | 'en'
  autoCompress: boolean
  contextLimit: number
  confirmMemory: boolean
  activeSkills: string[]
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
  activeSkills: [],
  enterToSend: true,
  shortcuts: true,
  dataDir: '',
}

const AGENT_KEYS = new Set<keyof SettingsState>([
  'autoCompress',
  'confirmMemory',
  'contextLimit',
  'activeSkills',
])

export function loadSettings(): SettingsState {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (!raw) return defaultSettings
    const parsed = JSON.parse(raw)
    return {
      ...defaultSettings,
      ...parsed,
      activeSkills: Array.isArray(parsed.activeSkills) ? parsed.activeSkills : [],
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

export function useSettings() {
  const [settings, setSettings] = useState<SettingsState>(() => loadSettings())
  const firstMount = useRef(true)
  const syncingFromApi = useRef(false)
  const prevAgent = useRef({
    autoCompress: settings.autoCompress,
    confirmMemory: settings.confirmMemory,
    contextLimit: settings.contextLimit,
    activeSkills: settings.activeSkills,
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
            contextLimit: remote.context_limit,
            activeSkills: Array.isArray(remote.active_skills) ? remote.active_skills : [],
          }
          prevAgent.current = {
            autoCompress: next.autoCompress,
            confirmMemory: next.confirmMemory,
            contextLimit: next.contextLimit,
            activeSkills: next.activeSkills,
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
      settings.contextLimit !== prevAgent.current.contextLimit ||
      settings.activeSkills.length !== prevAgent.current.activeSkills.length ||
      settings.activeSkills.some((id, i) => id !== prevAgent.current.activeSkills[i])

    if (!agentChanged) return

    prevAgent.current = {
      autoCompress: settings.autoCompress,
      confirmMemory: settings.confirmMemory,
      contextLimit: settings.contextLimit,
      activeSkills: settings.activeSkills,
    }

    updateAgentSettings({
      auto_compress: settings.autoCompress,
      confirm_memory: settings.confirmMemory,
      context_limit: settings.contextLimit,
      active_skills: settings.activeSkills,
    }).catch(() => {
      // ignore transient sync errors
    })
  }, [settings])

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
