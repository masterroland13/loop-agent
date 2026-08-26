import { useLayoutEffect, useRef } from 'react'
import type { ChatAttachment } from '../utils/chatAttachment'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop?: () => void
  onAttach?: () => void
  onModelClick?: () => void
  onThisPc?: () => void
  pcMode?: boolean
  isStreaming: boolean
  disabled: boolean
  attachments?: ChatAttachment[]
  onRemoveAttachment?: (localKey: string) => void
  placeholder?: string
  variant?: 'center' | 'bottom' | 'card'
  modelName?: string
  enterToSend?: boolean
  dimmed?: boolean
}

const MAX_HEIGHT_BOTTOM_PX = 208
const MAX_HEIGHT_CENTER_PX = 280
const MAX_HEIGHT_CARD_PX = 320

/** Shared chrome for +, This PC, and model chips (height locked to 32px). */
const TOOL_BTN =
  'box-border inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-full border border-transparent text-[13px] leading-none transition-colors disabled:opacity-40'

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  onAttach,
  onModelClick,
  onThisPc,
  pcMode = false,
  isStreaming,
  disabled,
  attachments = [],
  onRemoveAttachment,
  placeholder = 'Send follow-up',
  variant = 'bottom',
  modelName = 'kimi-for-coding',
  enterToSend = true,
  dimmed = false,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isCenter = variant === 'center'
  const isCard = variant === 'card'

  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '0px'
    const max = isCard
      ? MAX_HEIGHT_CARD_PX
      : isCenter
        ? MAX_HEIGHT_CENTER_PX
        : MAX_HEIGHT_BOTTOM_PX
    const next = Math.min(el.scrollHeight, max)
    el.style.height = `${Math.max(next, isCenter || isCard ? 64 : 28)}px`
    el.style.overflowY = el.scrollHeight > max ? 'auto' : 'hidden'
  }, [value, isCenter, isCard])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (enterToSend) {
        e.preventDefault()
        if (!isStreaming && (value.trim() || attachments.some((a) => a.status === 'ready'))) onSend()
      }
    }
  }

  return (
    <div
      className={[
        isCenter || isCard ? 'w-full' : 'mx-auto w-full max-w-3xl',
        dimmed ? 'pointer-events-none opacity-40' : '',
      ].join(' ')}
    >
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
          {attachments.map((att) => (
            <span
              key={att.localKey}
              className="inline-flex items-center gap-1.5 rounded-[var(--radius-pill)] bg-[var(--accent-bg)] px-2.5 py-0.5 text-[var(--text-h)]"
            >
              {att.status === 'pending' && <span className="text-[var(--text-muted)]">上传中…</span>}
              {att.status === 'error' && (
                <span className="text-red-500">{att.name}（失败）</span>
              )}
              {att.status === 'ready' && <span>{att.name}</span>}
              {onRemoveAttachment && (
                <button
                  type="button"
                  onClick={() => onRemoveAttachment(att.localKey)}
                  className="hover:text-[var(--text-h)]"
                  aria-label="移除附件"
                >
                  ×
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      <div
        className={[
          'w-full rounded-2xl border border-[var(--input-border)] bg-[var(--input-bg)] shadow-[0_0_0_1px_rgba(255,255,255,0.02)] transition-all focus-within:border-[var(--accent)] focus-within:shadow-[0_0_0_3px_var(--accent-bg)]',
          isCenter ? 'min-h-[148px] px-5 pb-3.5 pt-4' : isCard ? 'px-4 pb-3 pt-3.5' : 'px-4 py-3',
        ].join(' ')}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || isStreaming}
          placeholder={placeholder}
          rows={isCenter || isCard ? 2 : 1}
          className={[
            'w-full resize-none overflow-y-hidden bg-transparent text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)] disabled:opacity-50',
            isCenter ? 'min-h-[64px] text-lg leading-7' : isCard ? 'min-h-[80px] text-[15px] leading-[1.75]' : 'min-h-[28px] text-base leading-6',
          ].join(' ')}
        />

        <div className="mt-3 flex items-center justify-between gap-2">
          <div className="flex h-8 min-w-0 items-center gap-2">
            {onAttach && (
              <button
                type="button"
                onClick={onAttach}
                disabled={disabled || isStreaming}
                title="附加文件"
                className={`${TOOL_BTN} w-8 bg-[var(--surface-hover)] px-0 text-[var(--text-muted)] hover:text-[var(--text-h)]`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            )}
            {onThisPc && (
              <button
                type="button"
                onClick={onThisPc}
                disabled={disabled || isStreaming}
                title="绑定本机工作区目录"
                className={[
                  TOOL_BTN,
                  'px-3',
                  pcMode
                    ? 'bg-[var(--accent-bg)] text-[var(--text-h)] ring-1 ring-[var(--input-focus)]'
                    : 'bg-[var(--surface-hover)] text-[var(--text-muted)] hover:text-[var(--text-h)]',
                ].join(' ')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-3.5 w-3.5 shrink-0">
                  <rect x="3" y="4" width="18" height="14" rx="2" />
                  <path d="M8 20h8M12 18v2" />
                </svg>
                <span className="font-medium">This PC</span>
              </button>
            )}
            {onModelClick && (
              <button
                type="button"
                onClick={onModelClick}
                title="切换模型"
                className={`${TOOL_BTN} max-w-[260px] bg-[var(--surface-hover)] px-3 text-[var(--text-muted)] hover:text-[var(--text-h)]`}
              >
                <span className="truncate font-medium">{modelName}</span>
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3.5 w-3.5 shrink-0">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>
            )}
          </div>

          <div className="flex h-8 shrink-0 items-center gap-2">
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                title="停止"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--surface-hover)] text-[var(--text-h)] transition-colors hover:bg-[var(--surface-active)]"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-3.5 w-3.5">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                </svg>
              </button>
            ) : (
              <button
                type="button"
                onClick={onSend}
                disabled={disabled || (!value.trim() && !attachments.some((a) => a.status === 'ready')) || attachments.some((a) => a.status === 'pending')}
                title="发送"
                aria-label="发送"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--accent-solid)] text-white transition-all hover:brightness-110 active:scale-[0.94] disabled:opacity-30"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4">
                  <path d="M12 19V5" />
                  <path d="M5 12l7-7 7 7" />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
