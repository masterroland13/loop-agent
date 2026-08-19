import { useState } from 'react'
import type { MessagePair, ToolTraceItem } from '../types'
import { Markdown } from './Markdown'
import { ToolTimeline } from './ToolTimeline'

interface MessagePairItemProps {
  pair: MessagePair
  index: number
  isActive: boolean
  isStreaming?: boolean
  awaitingApproval?: boolean
  onToggleFavorite: (id: string) => void
  onRetry?: (pairId: string) => void
  onRetryToolStep?: (pairId: string, item: ToolTraceItem) => void
  setItemRef: (index: number) => (element: HTMLDivElement | null) => void
}

export function MessagePairItem({
  pair,
  index,
  isActive,
  isStreaming,
  awaitingApproval,
  onToggleFavorite,
  onRetry,
  onRetryToolStep,
  setItemRef,
}: MessagePairItemProps) {
  const [copied, setCopied] = useState(false)
  const hasTools = Boolean(pair.toolTrace && pair.toolTrace.length > 0)
  const isLastAssistantEmpty = isStreaming && !pair.assistant.content && !hasTools

  const handleCopy = async () => {
    const text = `User:\n${pair.user.content}\n\nAgent:\n${pair.assistant.content}`
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div ref={setItemRef(index)} className="group relative mb-8 scroll-mt-6">
      <div
        className={[
          'mb-6 rounded-[var(--radius-lg)] bg-[var(--user-bubble)] px-4 py-3.5 transition-[box-shadow,outline-color] duration-200',
          isActive
            ? 'outline outline-2 outline-[var(--pair-highlight)] outline-offset-2'
            : 'outline outline-2 outline-transparent outline-offset-2',
        ].join(' ')}
      >
        <p className="whitespace-pre-wrap text-[15px] font-[480] leading-[1.75] tracking-[0.02em] text-[var(--text-h)]">
          {pair.user.content}
        </p>
      </div>

      <div className="relative pl-0.5">
        {hasTools && (
          <ToolTimeline
            items={pair.toolTrace!}
            isStreaming={isStreaming}
            onRetryStep={
              onRetryToolStep
                ? (item) => onRetryToolStep(pair.id, item)
                : undefined
            }
          />
        )}

        {isLastAssistantEmpty ? (
          <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <span className="inline-flex gap-1">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-muted)]" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-muted)] [animation-delay:150ms]" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--text-muted)] [animation-delay:300ms]" />
            </span>
            {awaitingApproval ? '等待审批…' : '思考中…'}
          </div>
        ) : pair.assistant.content ? (
          <div
            className={[
              'text-[15px] font-[520] leading-[1.8] tracking-[0.02em]',
              pair.failed ? 'text-red-300/90' : 'text-[var(--text-h)]',
            ].join(' ')}
          >
            <Markdown content={pair.assistant.content} />
            {isStreaming && (
              <span className="ml-1.5 inline-block h-3.5 w-[7px] animate-pulse rounded-[2px] bg-[var(--accent)] align-[-2px]" />
            )}
          </div>
        ) : isStreaming && hasTools ? (
          <div className="text-sm text-[var(--text-muted)]">
            {awaitingApproval ? '等待你审批改动或命令…' : '整理结果…'}
          </div>
        ) : null}

        {((!isLastAssistantEmpty && pair.assistant.content) || pair.failed) && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {pair.turnMeta && (
              <button
                type="button"
                title="复制回合 Meta JSON"
                onClick={async (e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  await navigator.clipboard.writeText(JSON.stringify(pair.turnMeta, null, 2))
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
                }}
                className="rounded-md px-1.5 py-1 font-mono text-[10px] font-normal tracking-wide text-[var(--text-dim)] hover:text-[var(--text-muted)]"
              >
                {[
                  pair.turnMeta.model,
                  `${(pair.turnMeta.elapsed_ms / 1000).toFixed(1)}s`,
                  `~${pair.turnMeta.approx_prompt_tokens}+${pair.turnMeta.approx_completion_tokens}`,
                  pair.turnMeta.compressed ? '压缩' : null,
                  pair.turnMeta.memory_injected ? '记忆' : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </button>
            )}
            <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            {pair.assistant.content && (
              <ActionBtn title={copied ? '已复制' : '复制'} pressed={copied} onClick={handleCopy}>
                <rect x="9" y="9" width="13" height="13" rx="2" />
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
              </ActionBtn>
            )}
            <ActionBtn
              title={pair.isFavorite ? '取消收藏' : '收藏'}
              pressed={pair.isFavorite}
              onClick={() => onToggleFavorite(pair.id)}
              star
            >
              <path d="M12 3.5l2.472 5.008 5.528.804-4 3.898.944 5.504L12 16.27l-4.944 2.444.944-5.504-4-3.898 5.528-.804L12 3.5z" />
            </ActionBtn>
            {pair.failed && onRetry && !isStreaming && (
              <button
                type="button"
                title="重试本轮"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  onRetry(pair.id)
                }}
                className="ml-1 rounded-md px-2 py-1 text-xs text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
              >
                重试
              </button>
            )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ActionBtn({
  title,
  onClick,
  pressed,
  star,
  children,
}: {
  title: string
  onClick: () => void
  pressed?: boolean
  star?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      title={title}
      aria-pressed={Boolean(pressed)}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        onClick()
      }}
      className={[
        'inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors',
        pressed && star
          ? 'text-[var(--star)]'
          : pressed
            ? 'text-[var(--text-h)]'
            : 'text-[var(--text-dim)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-muted)]',
      ].join(' ')}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill={pressed && star ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth={1.75}
        className="h-3.5 w-3.5"
        aria-hidden
      >
        {children}
      </svg>
    </button>
  )
}
