import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { workedForLabel } from '../utils/workedFor'

/**
 * Live "Worked for Xs" while streaming (1s tick); static elapsed when done.
 * Falls back to "Worked for 0s" while streaming if no start time yet.
 */
export function useWorkedForLabel(
  startedAt?: number | null,
  options?: {
    elapsedMs?: number | null
    isStreaming?: boolean
  },
): string {
  const elapsedMs = options?.elapsedMs
  const isStreaming = Boolean(options?.isStreaming)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!isStreaming) return
    const id = window.setInterval(() => setTick((n) => n + 1), 1000)
    return () => window.clearInterval(id)
  }, [isStreaming])

  return useMemo(() => {
    void tick
    if (typeof elapsedMs === 'number' && elapsedMs >= 0 && !isStreaming) {
      return workedForLabel(elapsedMs)
    }
    if (typeof startedAt === 'number' && startedAt > 0) {
      return workedForLabel(Date.now() - startedAt)
    }
    if (isStreaming) return workedForLabel(0)
    return 'Activity'
  }, [elapsedMs, startedAt, isStreaming, tick])
}

/** Cursor-style text with optional light sweep (`.text-shimmer`). */
export function WorkedForText({
  children,
  shimmer,
  className,
}: {
  children: ReactNode
  shimmer?: boolean
  className?: string
}) {
  return (
    <span
      className={[shimmer ? 'text-shimmer' : null, className].filter(Boolean).join(' ')}
    >
      {children}
    </span>
  )
}
