import { useRef } from 'react'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop?: () => void
  onAttach?: () => void
  onModelClick?: () => void
  isStreaming: boolean
  disabled: boolean
  attachedFileName?: string | null
  onRemoveAttachment?: () => void
  placeholder?: string
  variant?: 'center' | 'bottom'
  modelName?: string
  enterToSend?: boolean
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  onAttach,
  onModelClick,
  isStreaming,
  disabled,
  attachedFileName,
  onRemoveAttachment,
  placeholder = 'Send follow-up',
  variant = 'bottom',
  modelName = 'kimi-for-coding',
  enterToSend = true,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      if (enterToSend) {
        e.preventDefault()
        if (!isStreaming && value.trim()) onSend()
      }
    }
  }

  const isCenter = variant === 'center'

  return (
    <div className={isCenter ? 'w-full' : 'mx-auto w-full max-w-3xl'}>
      {attachedFileName && (
        <div className="mb-2 flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <span className="rounded-[var(--radius-pill)] bg-[var(--accent-bg)] px-2.5 py-0.5 text-[var(--text-h)]">
            {attachedFileName}
          </span>
          {onRemoveAttachment && (
            <button type="button" onClick={onRemoveAttachment} className="hover:text-[var(--text-h)]">
              移除
            </button>
          )}
        </div>
      )}

      <div
        className={[
          'w-full rounded-2xl border border-[var(--input-border)] bg-[var(--input-bg)] shadow-[0_0_0_1px_rgba(255,255,255,0.02)] transition-colors focus-within:border-[var(--input-focus)]',
          isCenter ? 'min-h-[148px] px-5 pb-3.5 pt-4' : 'px-4 py-3',
        ].join(' ')}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || isStreaming}
          placeholder={placeholder}
          rows={isCenter ? 2 : 1}
          className={[
            'w-full resize-none bg-transparent text-[var(--text-h)] outline-none placeholder:text-[var(--text-dim)] disabled:opacity-50',
            isCenter ? 'min-h-[64px] text-lg leading-7' : 'min-h-[28px] max-h-40 text-base leading-6',
          ].join(' ')}
        />

        <div className="mt-3 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            {onAttach && (
              <button
                type="button"
                onClick={onAttach}
                disabled={disabled || isStreaming}
                title="附加文件"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)] disabled:opacity-40"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>
            )}
            <button
              type="button"
              onClick={onModelClick}
              title="切换模型"
              className="flex max-w-[260px] items-center gap-2 rounded-full bg-[var(--surface-hover)] px-3.5 py-2 text-base text-[var(--text-muted)] transition-colors hover:text-[var(--text-h)]"
            >
              <span className="truncate font-medium">{modelName}</span>
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4 shrink-0">
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                title="停止"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--surface-hover)] text-[var(--text-h)] transition-colors hover:bg-[var(--surface-active)]"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-3.5 w-3.5">
                  <rect x="6" y="6" width="12" height="12" rx="1" />
                </svg>
              </button>
            ) : (
              <button
                type="button"
                onClick={onSend}
                disabled={disabled || !value.trim()}
                title="发送"
                aria-label="发送"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--text-h)] text-[var(--bg)] transition-opacity hover:opacity-90 disabled:opacity-30"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="h-4.5 w-4.5">
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
