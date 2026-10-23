/** Parse a server timestamp. Naive ISO values are UTC, not local time. */
function parseServerTime(dateInput: string | number): Date {
  if (typeof dateInput === 'number') return new Date(dateInput)
  const raw = dateInput.trim()
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(raw) && !/(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(raw)) {
    return new Date(`${raw.replace(' ', 'T')}Z`)
  }
  return new Date(raw)
}

export function formatRelativeTime(dateInput: string | number): string {
  const time = parseServerTime(dateInput).getTime()
  if (Number.isNaN(time)) return ''
  const diffMs = Date.now() - time
  if (diffMs < 60000) return 'now'
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 60) return `${diffMin}m`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 30) return `${diffDay}d`
  return new Date(time).toLocaleDateString()
}
