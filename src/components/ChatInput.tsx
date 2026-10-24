import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { barNeedsWrapStack, singleRowContentWidth } from '../utils/barWrapStack'
import { isImageAttachment, type ChatAttachment } from '../utils/chatAttachment'
import { useT } from '../i18n'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop?: () => void
  onAttach?: () => void
  onModelClick?: (anchor: DOMRect) => void
  goalMode?: boolean
  onGoalModeToggle?: () => void
  onMultitask?: () => void
  onPlanIdea?: () => void
  pinnedGoal?: string | null
  onPinnedGoalChange?: (goal: string | null) => void
  isStreaming: boolean
  disabled: boolean
  attachments?: ChatAttachment[]
  onRemoveAttachment?: (localKey: string) => void
  placeholder?: string
  /** center = empty hero; bottom/card = single-line bar (same actions via ⋮) */
  variant?: 'center' | 'bottom' | 'card'
  modelName?: string
  enterToSend?: boolean
  dimmed?: boolean
  /** Active pair highlight on the bar itself (no outer outline shell) */
  highlighted?: boolean
  occupancyPercent?: number | null
  onCompact?: () => void
}

const MAX_HEIGHT_BAR_PX = 160
const MAX_HEIGHT_CENTER_PX = 280

const TOOL_BTN =
  'box-border inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-full border text-[13px] leading-none transition-colors disabled:opacity-40'
const TOOL_ICON = 'block h-3.5 w-3.5 shrink-0'
const ACTION_BTN =
  'box-border inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors disabled:opacity-40'

type MoreItem = {
  id: string
  label: string
  onClick: () => void
  pressed?: boolean
  disabled?: boolean
}

function ComposerMoreMenu({
  items,
  disabled,
}: {
  items: MoreItem[]
  disabled?: boolean
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })

  useLayoutEffect(() => {
    if (!open || !btnRef.current) return
    const r = btnRef.current.getBoundingClientRect()
    const menuW = 148
    const menuH = 8 + items.length * 30 + 5
    let left = r.left
    let top = r.bottom + 4
    if (left + menuW > window.innerWidth - 8) left = Math.max(8, window.innerWidth - menuW - 8)
    if (top + menuH > window.innerHeight - 8) top = Math.max(8, r.top - menuH - 4)
    setPos({ top, left })
  }, [open, items.length])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    const onPointer = (e: MouseEvent) => {
      const t = e.target as Node
      if (btnRef.current?.contains(t) || menuRef.current?.contains(t)) return
      setOpen(false)
    }
    const tid = window.setTimeout(() => {
      window.addEventListener('keydown', onKey)
      window.addEventListener('mousedown', onPointer)
    }, 0)
    return () => {
      window.clearTimeout(tid)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onPointer)
    }
  }, [open])

  if (items.length === 0) return null

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        title={t('chat.more')}
        onClick={() => setOpen((v) => !v)}
        className="box-border inline-flex h-8 w-3.5 shrink-0 items-center justify-center rounded-full border-0 bg-transparent text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)] disabled:opacity-40"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="currentColor"
          className="h-4 w-4"
          aria-hidden
        >
          <circle cx="12" cy="5" r="1.6" />
          <circle cx="12" cy="12" r="1.6" />
          <circle cx="12" cy="19" r="1.6" />
        </svg>
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            style={{ top: pos.top, left: pos.left }}
            className="fixed z-[80] min-w-[132px] max-w-[168px] overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-1 py-1 shadow-[0_8px_28px_rgba(0,0,0,0.45),0_0_0_1px_rgba(255,255,255,0.05)]"
          >
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                role="menuitem"
                disabled={item.disabled}
                aria-pressed={item.pressed}
                onClick={() => {
                  if (item.disabled) return
                  item.onClick()
                  setOpen(false)
                }}
                className={[
                  'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[12.5px] leading-5 tracking-[0.01em] transition-colors duration-75 disabled:opacity-40',
                  item.pressed
                    ? 'bg-[var(--surface-hover)] text-[var(--text-h)]'
                    : 'text-[var(--text-h)] hover:bg-[var(--surface-hover)]',
                ].join(' ')}
              >
                <span className="min-w-0 truncate font-medium">{item.label}</span>
                {item.pressed ? (
                  <span className="shrink-0 text-[10px] text-[var(--text-dim)]">{t('common.on')}</span>
                ) : null}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  )
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  onAttach,
  onModelClick,
  goalMode = false,
  onGoalModeToggle,
  onMultitask,
  onPlanIdea,
  pinnedGoal = null,
  onPinnedGoalChange,
  isStreaming,
  disabled,
  attachments = [],
  onRemoveAttachment,
  placeholder = 'Send follow-up',
  variant = 'bottom',
  modelName = 'kimi-for-coding',
  enterToSend = true,
  dimmed = false,
  highlighted = false,
  occupancyPercent = null,
  onCompact,
}: ChatInputProps) {
  const t = useT()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const leftToolsRef = useRef<HTMLDivElement>(null)
  const rightToolsRef = useRef<HTMLDivElement>(null)
  const composingRef = useRef(false)
  const isCenter = variant === 'center'
  /** bottom + card share the single-line bar chrome */
  const isBar = !isCenter
  const [goalDraft, setGoalDraft] = useState(pinnedGoal ?? '')
  /**
   * Wrap-only multi-line (no `\n`) needs measure; newlines sync on render so paste
   * never paints one frame as a tall pill.
   */
  const [wrapExpanded, setWrapExpanded] = useState(false)
  const hasNewline = value.includes('\n')
  const barExpanded = isBar && (hasNewline || wrapExpanded)

  useEffect(() => {
    setGoalDraft(pinnedGoal ?? '')
  }, [pinnedGoal])

  // Wrap decision must not depend on barExpanded: stacking flips leading-8↔leading-5
  // and can make scrollHeight oscillate at the threshold → infinite setState → white screen.
  const captureTextareaFocus = () => {
    const el = textareaRef.current
    if (!el || document.activeElement !== el) return null
    return { start: el.selectionStart, end: el.selectionEnd }
  }

  const restoreTextareaFocus = (sel: { start: number; end: number } | null) => {
    if (!sel) return
    const el = textareaRef.current
    if (!el) return
    el.focus({ preventScroll: true })
    try {
      el.setSelectionRange(sel.start, sel.end)
    } catch {
      // ignore if selection no longer valid
    }
  }

  useLayoutEffect(() => {
    if (!isBar) {
      setWrapExpanded(false)
      return
    }
    if (composingRef.current) return
    const el = textareaRef.current
    if (!el) return
    const sel = captureTextareaFocus()

    const shell = el.closest('.composer-shell') as HTMLElement | null
    const measureW = singleRowContentWidth(
      shell?.clientWidth ?? el.clientWidth,
      leftToolsRef.current?.offsetWidth ?? 0,
      rightToolsRef.current?.offsetWidth ?? 0,
    )
    const prevWidth = el.style.width
    const prevHeight = el.style.height
    const prevLineHeight = el.style.lineHeight
    // Probe at single-row width + stable line-height (never full shell width).
    el.style.width = `${measureW}px`
    el.style.height = '0px'
    el.style.lineHeight = '32px'
    const fullScroll = el.scrollHeight
    el.style.width = prevWidth
    el.style.height = prevHeight
    el.style.lineHeight = prevLineHeight

    setWrapExpanded((prev) => {
      const next = barNeedsWrapStack(fullScroll, prev, hasNewline)
      return next === prev ? prev : next
    })
    restoreTextareaFocus(sel)
  }, [value, isBar, hasNewline, attachments.length, goalMode])

  useLayoutEffect(() => {
    if (composingRef.current) return
    const el = textareaRef.current
    if (!el) return
    const sel = captureTextareaFocus()
    const max = isCenter ? MAX_HEIGHT_CENTER_PX : MAX_HEIGHT_BAR_PX
    const min = isCenter ? 44 : 32

    el.style.height = '0px'
    const next = Math.min(Math.max(el.scrollHeight, min), max)
    el.style.height = `${next}px`
    el.style.overflowY = next >= max ? 'auto' : 'hidden'
    restoreTextareaFocus(sel)
  }, [value, isCenter, isBar, hasNewline, barExpanded, attachments.length, goalMode])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (enterToSend) {
        e.preventDefault()
        if (!isStreaming && (value.trim() || attachments.some((a) => a.status === 'ready'))) onSend()
      }
    }
  }

  const commitPinnedGoal = () => {
    if (!onPinnedGoalChange) return
    const next = goalDraft.trim() || null
    const prev = (pinnedGoal ?? '').trim() || null
    if (next === prev) {
      setGoalDraft(prev ?? '')
      return
    }
    void onPinnedGoalChange(next)
  }

  const moreItems: MoreItem[] = []
  if (onGoalModeToggle) {
    moreItems.push({
      id: 'goal',
      label: t('chat.goal'),
      pressed: goalMode,
      disabled: disabled || isStreaming,
      onClick: onGoalModeToggle,
    })
  }
  if (onMultitask) {
    moreItems.push({
      id: 'multitask',
      label: t('chat.multitask'),
      disabled: disabled || isStreaming,
      onClick: onMultitask,
    })
  }
  if (onPlanIdea) {
    moreItems.push({
      id: 'plan',
      label: t('chat.planIdea'),
      disabled: disabled || isStreaming,
      onClick: onPlanIdea,
    })
  }
  if (onCompact) {
    moreItems.push({
      id: 'compact',
      label: t('chat.compact'),
      disabled: disabled || isStreaming,
      onClick: onCompact,
    })
  }

  /** Tall chrome → block radius (multi-line, Goal row, or attachments) */
  const barChromeExpanded =
    isBar &&
    (barExpanded ||
      Boolean(goalMode && onPinnedGoalChange) ||
      attachments.length > 0)

  const leftTools = (
    <div ref={leftToolsRef} className="flex h-8 shrink-0 items-center gap-0.5">
      {onAttach && (
        <button
          type="button"
          onClick={onAttach}
          disabled={disabled || isStreaming}
          title={t('chat.attach')}
          className={`${ACTION_BTN} composer-chip border-[var(--input-border)] text-[var(--text-muted)] hover:text-[var(--text-h)]`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={TOOL_ICON}>
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      )}
      {/* ⋮ only on bottom/card bar — empty center keeps Goal/Multitask/Plan capsules below */}
      {isBar ? <ComposerMoreMenu items={moreItems} disabled={disabled} /> : null}
    </div>
  )

  const rightTools = (
    <div ref={rightToolsRef} className="flex h-8 shrink-0 items-center gap-1.5">
      {occupancyPercent != null && occupancyPercent >= 0 && (
        <span
          title={t('chat.contextUsage', { percent: String(occupancyPercent) })}
          className={`shrink-0 tabular-nums text-[12px] ${
            occupancyPercent >= 85 ? 'text-[var(--warn,var(--text-muted))]' : 'text-[var(--text-dim)]'
          }`}
        >
          {occupancyPercent}%
        </span>
      )}
      {onModelClick && (
        <button
          type="button"
          data-model-picker-anchor
          onClick={(e) => onModelClick(e.currentTarget.getBoundingClientRect())}
          title={t('chat.switchModel')}
          className={`${TOOL_BTN} max-w-[min(220px,36vw)] border-transparent bg-transparent px-2.5 text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]`}
        >
          <span className="max-w-full truncate leading-5 font-medium">{modelName}</span>
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className={TOOL_ICON}>
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>
      )}
      {isStreaming ? (
        <button
          type="button"
          onClick={onStop}
          title={t('chat.stop')}
          className={`${ACTION_BTN} border-transparent bg-[var(--surface-hover)] text-[var(--text-h)] hover:bg-[var(--surface-active)]`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-3.5 w-3.5">
            <rect x="6" y="6" width="12" height="12" rx="1.5" />
          </svg>
        </button>
      ) : (
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || (!value.trim() && !attachments.some((a) => a.status === 'ready'))}
          title={t('chat.send')}
          className={`${ACTION_BTN} border-transparent bg-[var(--accent-solid)] text-white`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
            <path d="M12 19V5" />
            <path d="M5 12l7-7 7 7" />
          </svg>
        </button>
      )}
    </div>
  )

  const pinnedGoalRow =
    goalMode && onPinnedGoalChange ? (
      <div className="mb-2 flex items-center gap-2">
        <span className="shrink-0 text-[12px] font-medium text-[var(--text-muted)]">{t('chat.pinnedGoal')}</span>
        <input
          type="text"
          value={goalDraft}
          onChange={(e) => setGoalDraft(e.target.value)}
          onBlur={commitPinnedGoal}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              ;(e.target as HTMLInputElement).blur()
            }
            if (e.key === 'Escape') {
              setGoalDraft(pinnedGoal ?? '')
              ;(e.target as HTMLInputElement).blur()
            }
          }}
          disabled={disabled || isStreaming}
          maxLength={240}
          placeholder={t('chat.pinnedGoalPlaceholder')}
          className="min-w-0 flex-1 bg-transparent text-[13px] leading-5 text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)] disabled:opacity-50"
          aria-label={t('chat.pinnedGoal')}
        />
        {goalDraft.trim() ? (
          <button
            type="button"
            disabled={disabled || isStreaming}
            onClick={() => {
              setGoalDraft('')
              void onPinnedGoalChange(null)
            }}
            className="shrink-0 text-[12px] text-[var(--text-muted)] hover:text-[var(--text-h)] disabled:opacity-40"
          >
            {t('chat.clear')}
          </button>
        ) : null}
      </div>
    ) : null

  const textarea = (
    <textarea
      ref={textareaRef}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onCompositionStart={() => {
        composingRef.current = true
      }}
      onCompositionEnd={() => {
        composingRef.current = false
      }}
      onKeyDown={handleKeyDown}
      disabled={disabled || isStreaming}
      placeholder={placeholder}
      rows={1}
      className={[
        'w-full resize-none overflow-y-hidden bg-transparent text-[var(--text-h)] outline-none disabled:opacity-50',
        isCenter
          ? 'min-h-[44px] text-lg leading-7 placeholder:text-[var(--text-dim)]'
          : barExpanded
            ? 'block min-h-8 w-full py-0 text-[14px] font-[480] leading-5 placeholder:font-medium placeholder:text-[var(--text-muted)]'
            : 'block min-h-8 w-full py-0 text-[14px] font-[480] leading-8 placeholder:font-medium placeholder:text-[var(--text-muted)]',
      ].join(' ')}
    />
  )

  return (
    <div
      className={[
        isCenter || isBar ? 'w-full' : 'mx-auto w-full max-w-3xl',
        dimmed ? 'pointer-events-none opacity-40' : '',
      ].join(' ')}
    >
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
          {attachments.map((att) => {
            const thumb = isImageAttachment(att) ? att.previewUrl || att.url : undefined
            return (
              <span
                key={att.localKey}
                className="inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] bg-[var(--accent-bg)] px-2.5 py-0.5 text-[var(--text-h)]"
              >
                {thumb ? (
                  <img src={thumb} alt="" className="h-7 w-7 rounded object-cover" />
                ) : null}
                {att.status === 'pending' && <span className="text-[var(--text-muted)]">{t('chat.uploading')}</span>}
                {att.status === 'error' && (
                  <span className="text-red-500">{t('chat.uploadFailedChip', { name: att.name })}</span>
                )}
                {att.status === 'ready' && <span>{att.name}</span>}
                {onRemoveAttachment && (
                  <button
                    type="button"
                    onClick={() => onRemoveAttachment(att.localKey)}
                    className="hover:text-[var(--text-h)]"
                    aria-label={t('chat.removeAttachment')}
                  >
                    ×
                  </button>
                )}
              </span>
            )
          })}
        </div>
      )}

      {isBar ? (
        <div
          className={[
            'composer-shell composer-shell--bar w-full px-2.5',
            barChromeExpanded ? 'is-expanded py-2.5' : 'py-2',
            highlighted ? 'is-highlighted' : '',
          ].join(' ')}
        >
          {pinnedGoalRow}
          <div
            className={
              barExpanded
                ? 'flex min-h-0 flex-col gap-1.5'
                : 'flex min-h-8 items-center gap-1.5'
            }
          >
            {!barExpanded ? leftTools : null}
            <div
              key="composer-textarea-slot"
              className={
                barExpanded
                  ? 'min-w-0 px-0.5'
                  : 'flex min-h-8 min-w-0 flex-1 items-center'
              }
            >
              {textarea}
            </div>
            {!barExpanded ? rightTools : null}
            {barExpanded ? (
              <div className="flex items-center justify-between gap-2">
                {leftTools}
                {rightTools}
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="composer-shell w-full min-h-[118px] px-3.5 pb-3.5 pt-3.5">
          {pinnedGoalRow}
          {textarea}
          <div className="mt-2.5 flex items-center justify-between gap-2">
            {leftTools}
            {rightTools}
          </div>
        </div>
      )}
    </div>
  )
}
