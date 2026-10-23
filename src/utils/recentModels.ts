/** Recently used model ids — survives custom “使用” so picker list grows without re-typing. */

const STORAGE_KEY = 'loop.recentModels'
const LEGACY_STORAGE_KEY = 'hal.recentModels'
const MAX_RECENT = 16

export function loadRecentModels(): string[] {
  try {
    let raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      raw = localStorage.getItem(LEGACY_STORAGE_KEY)
      if (raw) localStorage.setItem(STORAGE_KEY, raw)
    }
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
      .map((x) => x.trim())
      .slice(0, MAX_RECENT)
  } catch {
    return []
  }
}

/** Prepend `id`, dedupe, cap length. Returns the new list. */
export function rememberModel(id: string): string[] {
  const trimmed = id.trim()
  if (!trimmed) return loadRecentModels()
  const next = [trimmed, ...loadRecentModels().filter((x) => x !== trimmed)].slice(0, MAX_RECENT)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // ignore quota / private mode
  }
  return next
}
