export function formatRelativeTime(dateInput: string | number): string {
  const date = typeof dateInput === 'number' ? new Date(dateInput) : new Date(dateInput)
  const diffMs = Date.now() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'now'
  if (diffMin < 60) return `${diffMin}m`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `${diffHour}h`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay < 30) return `${diffDay}d`
  return date.toLocaleDateString()
}
