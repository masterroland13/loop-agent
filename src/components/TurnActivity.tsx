import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useT } from '../i18n'
import type { ActivityItem, ActivitySegment, TurnActivitySnapshot } from '../utils/turnActivity'
import { ChevronIcon } from './ChevronIcon'
import { useWorkedForLabel, WorkedForText } from './WorkedForText'

export type GateFocusTarget = { kind: 'patch' | 'shell'; id: string }

/** Match MessagePairItem body metrics; rest of line stays muted, never bold. */
const ACTIVITY_BASE = 'text-[15px] font-normal leading-[1.8] tracking-[0.02em]'
const ACTIVITY_MUTED = `${ACTIVITY_BASE} text-[var(--text-muted)]`
/** Keywords one step brighter than muted (--text). */
const ACTIVITY_KEY = 'text-[var(--text)]'

const KEYWORD_RE =
  /^(Worked for|Working…|Activity|Thought|Explored|Edited|Proposed|Rejected|Partially edited|Read|Grepped|Listed|Ran|Memory)\b(.*)$/i

interface TurnActivityProps {
  snapshot?: TurnActivitySnapshot | null
  startedAt?: number
  elapsedMs?: number
  isStreaming?: boolean
  onFocusGate?: (target: GateFocusTarget) => void
}

function segmentLabel(seg: ActivitySegment): string {
  return seg.summary
}

function gateTargetForItem(item: ActivityItem): GateFocusTarget | null {
  if (item.kind === 'edit' && item.patch_id) {
    return { kind: 'patch', id: item.patch_id }
  }
  if (item.kind === 'run' && item.shell_id) {
    return { kind: 'shell', id: item.shell_id }
  }
  return null
}

/** Brighten leading keyword; leave the rest muted. */
function ActivityLabel({ text }: { text: string }): ReactNode {
  const m = text.match(KEYWORD_RE)
  if (!m) return text
  return (
    <>
      <span className={ACTIVITY_KEY}>{m[1]}</span>
      <span className="text-[var(--text-muted)]">{m[2]}</span>
    </>
  )
}

function NestedThoughtRow({ item }: { item: ActivityItem }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const raw = (item.text || '').trim()
  const looksLikeToolJson =
    raw.startsWith('{') &&
    (/"error"\s*:/.test(raw) || /"code"\s*:\s*"DUPLICATE"/i.test(raw))
  if (looksLikeToolJson) return null
  const label = item.summary || 'Thought'
  const body = raw || t('message.thinking')
  return (
    <li className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`${ACTIVITY_BASE} group inline-flex max-w-full items-baseline gap-1 text-left`}
      >
        <span className="min-w-0">
          <ActivityLabel text={label} />
        </span>
        <ChevronIcon
          open={open}
          className="relative top-[0.15em] shrink-0 text-[var(--text-dim)] opacity-80 group-hover:opacity-100"
        />
      </button>
      {open ? (
        <div
          className={`${ACTIVITY_MUTED} my-1.5 whitespace-pre-wrap break-words`}
          title={raw || undefined}
        >
          {body}
        </div>
      ) : null}
    </li>
  )
}

function ItemRow({
  item,
  showThoughtLabel,
  onFocusGate,
}: {
  item: ActivityItem
  /** When nested under Explored/Edited, collapsible Thought label (body collapsed). */
  showThoughtLabel?: boolean
  onFocusGate?: (target: GateFocusTarget) => void
}) {
  const t = useT()
  const bad =
    item.status === 'rejected' ||
    item.status === 'failed' ||
    item.status === 'error' ||
    item.status === 'cancelled' ||
    item.status === 'timeout'
  const gate = gateTargetForItem(item)
  const clickable = Boolean(gate && onFocusGate)

  if (item.kind === 'thought') {
    if (showThoughtLabel) {
      return <NestedThoughtRow item={item} />
    }
    const raw = (item.text || '').trim()
    const looksLikeToolJson =
      raw.startsWith('{') &&
      (/"error"\s*:/.test(raw) || /"code"\s*:\s*"DUPLICATE"/i.test(raw))
    if (looksLikeToolJson) return null
    return (
      <li className={`${ACTIVITY_MUTED} whitespace-pre-wrap break-words`} title={item.text || item.summary}>
        {raw || t('message.thinking')}
      </li>
    )
  }

  if (clickable && gate) {
    return (
      <li>
        <button
          type="button"
          title={`${t('message.focusGate')} · ${item.summary}`}
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onFocusGate?.(gate)
          }}
          className={`${ACTIVITY_BASE} text-left underline-offset-2 hover:underline ${
            bad ? 'text-[var(--status-err)]' : ''
          }`}
        >
          {bad ? item.summary : <ActivityLabel text={item.summary} />}
        </button>
      </li>
    )
  }

  return (
    <li
      className={`${ACTIVITY_BASE} ${bad ? 'text-[var(--status-err)]' : ''}`}
      title={item.summary}
    >
      {bad ? item.summary : <ActivityLabel text={item.summary} />}
    </li>
  )
}

function SegmentBlock({
  seg,
  onFocusGate,
}: {
  seg: ActivitySegment
  onFocusGate?: (target: GateFocusTarget) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`${ACTIVITY_BASE} group inline-flex max-w-full items-baseline gap-1 text-left`}
      >
        <span className="min-w-0">
          <ActivityLabel text={segmentLabel(seg)} />
        </span>
        <ChevronIcon
          open={open}
          className="relative top-[0.15em] shrink-0 text-[var(--text-dim)] opacity-80 group-hover:opacity-100"
        />
      </button>
      {open ? (
        <ul className="my-1.5 space-y-0 pl-0">
          {seg.items.map((it) => (
            <ItemRow
              key={it.id}
              item={it}
              showThoughtLabel={seg.kind !== 'thought'}
              onFocusGate={onFocusGate}
            />
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export function TurnActivity({
  snapshot,
  startedAt,
  elapsedMs,
  isStreaming,
  onFocusGate,
}: TurnActivityProps) {
  const segments = snapshot?.segments || []
  const [rootOpen, setRootOpen] = useState(Boolean(isStreaming))
  const wasStreamingRef = useRef(Boolean(isStreaming))
  const streaming = Boolean(isStreaming)

  const header = useWorkedForLabel(startedAt, {
    elapsedMs,
    isStreaming: streaming,
  })

  useEffect(() => {
    if (isStreaming) {
      setRootOpen(true)
      wasStreamingRef.current = true
      return
    }
    // Stream just ended → collapse to a single "Worked for" line (user can reopen).
    if (wasStreamingRef.current) {
      setRootOpen(false)
      wasStreamingRef.current = false
    }
  }, [isStreaming])

  if (!segments.length) return null

  return (
    <div className="mb-3 min-w-0 space-y-0">
      <button
        type="button"
        onClick={() => setRootOpen((v) => !v)}
        className={`${ACTIVITY_BASE} group inline-flex max-w-full items-baseline gap-1 text-left`}
      >
        <span className="min-w-0">
          {streaming ? (
            <WorkedForText shimmer>{header}</WorkedForText>
          ) : (
            <ActivityLabel text={header} />
          )}
        </span>
        <ChevronIcon
          open={rootOpen}
          className="relative top-[0.15em] shrink-0 text-[var(--text-dim)] opacity-80 group-hover:opacity-100"
        />
      </button>
      {rootOpen ? (
        <div className="my-1.5 min-w-0 space-y-0">
          {segments.map((seg) => (
            <SegmentBlock
              key={`${seg.kind}-${seg.items.map((i) => i.id).join('-')}`}
              seg={seg}
              onFocusGate={onFocusGate}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}
