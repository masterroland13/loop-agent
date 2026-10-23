/**
 * Whether inline `code` deserves a chip (light bg).
 * Demotes plain English words / short literals / bare filenames so
 * markdown doesn't look speckled; keeps paths, file:line, symbols, assignments.
 */
export function isMeaningfulInlineCode(raw: string): boolean {
  const s = raw.replace(/\n$/, '').trim()
  if (!s) return false
  // Paths / line refs
  if (/[\\/]/.test(s)) return true
  if (/:\d/.test(s)) return true // file:line or file:start-end
  // Code-ish tokens
  if (/[()=`<>]/.test(s)) return true
  if (/=/.test(s)) return true
  if (/::/.test(s)) return true
  if (/_/.test(s) && s.length >= 4) return true // snake_case
  if (/[a-z][A-Z]/.test(s) && s.length >= 6) return true // camelCase
  // Bare `foo.py` is common noise; only chip longer / compound names
  if (/\.\w{1,8}\b/.test(s) && s.length >= 20) return true
  if (s.length >= 22) return true
  return false
}
