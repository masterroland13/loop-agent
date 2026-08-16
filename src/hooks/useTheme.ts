import { useCallback, useEffect, useState } from 'react'

export type ThemeMode = 'dark' | 'light'

const THEME_KEY = 'agent-chat:theme'

function applyTheme(theme: ThemeMode) {
  document.documentElement.setAttribute('data-theme', theme)
}

function loadTheme(): ThemeMode {
  try {
    const saved = localStorage.getItem(THEME_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // ignore
  }
  return 'dark'
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    const initial = loadTheme()
    applyTheme(initial)
    return initial
  })

  useEffect(() => {
    applyTheme(theme)
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      // ignore
    }
  }, [theme])

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === 'dark' ? 'light' : 'dark'))
  }, [])

  const setTheme = useCallback((next: ThemeMode) => {
    setThemeState(next)
  }, [])

  return { theme, toggleTheme, setTheme, isDark: theme === 'dark' }
}
