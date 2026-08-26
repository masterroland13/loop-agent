import { useState } from 'react'
import type { MessagePair, ToolTraceItem } from '../types'
import { ChevronIcon } from './ChevronIcon'
import { Markdown } from './Markdown'
import { ToolTimeline } from './ToolTimeline'
import { UserMessageCard } from './UserMessageCard'

interface MessagePairItemProps {
  pair: MessagePair
  index: number
  isActive: boolean
  isStreaming?: boolean
  awaitingApproval?: boolean
  sessionId?: string | null
  expandedUserPairId: string | null
  expandedDraft: string
  expandedAttachments?: import('../utils/chatAttachment').ChatAttachment[]
  onExpandUser: (pairId: string, content: string) => void
  onExpandedDraftChange: (value: string) => void
  onExpandedSend: () => void
  onExpandedAttach?: () => void
  onToggleFavorite: (id: string) => void
  onRetry?: (pairId: string) => void
  onRetryToolStep?: (pairId: string, item: ToolTraceItem) => void
  setItemRef: (index: number) => (element: HTMLDivElement | null) => void
  inputToolbar?: {
    onModelClick?: () => void
    onThisPc?: () => void
    onRemoveAttachment?: (localKey: string) => void
    pcMode?: boolean
    modelName?: string
    enterToSend?: boolean
    disabled?: boolean
  }
}

export function MessagePairItem({
  pair,
  index,
  isActive,
  isStreaming,
  awaitingApproval,
  sessionId,
  expandedUserPairId,
  expandedDraft,
  expandedAttachments,
  onExpandUser,
  onExpandedDraftChange,
  onExpandedSend,
  onExpandedAttach,
  onToggleFavorite,
  onRetry,
  onRetryToolStep,
  setItemRef,
  inputToolbar,
}: MessagePairItemProps) {
  const [copied, setCopied] = useState(false)
  const hasTools = Boolean(pair.toolTrace && pair.toolTrace.length > 0)
  const goalText = pair.goal || pair.turnMeta?.goal
  const previousGoal = pair.previousGoal
  const goalChanged = Boolean(previousGoal && goalText && previousGoal !== goalText)
  const checkpoint = pair.progressCheckpoint
  const turnBusy = Boolean(isStreaming || pair.turnInProgress)
  const isLastAssistantEmpty = turnBusy && !pair.assistant.content && !hasTools
  const isUserExpanded = expandedUserPairId === pair.id

  const handleCopy = async () => {
    const text = `User:\n${pair.user.content}\n\nAgent:\n${pair.assistant.content}`
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div ref={setItemRef(index)} className="group relative mb-8 scroll-mt-6">
      <UserMessageCard
        pairId={pair.id}
        content={pair.user.content}
        index={index}
        isActive={isActive}
        isExpanded={isUserExpanded}
        draft={expandedDraft}
        attachments={expandedAttachments}
        messageAttachments={pair.user.attachments}
        sessionId={sessionId}
        onExpand={onExpandUser}
        onDraftChange={onExpandedDraftChange}
        onSend={onExpandedSend}
        onAttach={onExpandedAttach}
        onModelClick={inputToolbar?.onModelClick}
        onThisPc={inputToolbar?.onThisPc}
        onRemoveAttachment={inputToolbar?.onRemoveAttachment}
        pcMode={inputToolbar?.pcMode}
        modelName={inputToolbar?.modelName}
        enterToSend={inputToolbar?.enterToSend}
        isStreaming={Boolean(isStreaming)}
        disabled={Boolean(inputToolbar?.disabled)}
      />

      <div className="relative pl-0.5">
        {goalText ? (
          <div
            className="mb-2 max-w-full truncate rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-[13px] leading-5 text-[var(--text-h)]"
            title={goalChanged ? `${previousGoal} → ${goalText}` : goalText}
          >
            <span className="mr-1.5 font-medium text-[var(--text-muted)]">
              {goalChanged ? '目标 · 已变更' : '目标'}
            </span>
            {goalText}
          </div>
        ) : null}
        {checkpoint ? (
          <details className="group mb-2 rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-[13px] leading-5 text-[var(--text-muted)]">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] leading-5 text-[var(--text-h)] [&::-webkit-details-marker]:hidden">
              <ChevronIcon className="shrink-0 text-[var(--text-muted)] rotate-0 group-open:rotate-90" />
              <span className="min-w-0 flex-1 truncate text-[13px] font-normal leading-5 tracking-normal">
                {`检查点 · ${
                  checkpoint.reason === 'gate'
                    ? '审批返回'
                    : `已用 ${checkpoint.toolsSinceLast} 次工具`
                } · 对照目标 · ${
                  checkpoint.reply
                    ? '有进度说明'
                    : checkpoint.settled || !turnBusy
                      ? '无进度说明'
                      : '等待说明'
                }`}
              </span>
            </summary>
            {checkpoint.reply ? (
              <p className="mt-2 whitespace-pre-wrap break-words text-[13px] leading-relaxed text-[var(--text-h)]">
                {checkpoint.reply}
              </p>
            ) : null}
          </details>
        ) : null}
        {hasTools && (
          <ToolTimeline
            items={pair.toolTrace!}
            isStreaming={turnBusy}
            sessionId={sessionId}
            onRetryStep={
              onRetryToolStep
                ? (item) => onRetryToolStep(pair.id, item)
                : undefined
            }
          />
        )}

        {pair.turnInProgress && !isStreaming && hasTools && (
          <div className="mt-2 text-sm text-[var(--text-muted)]">后台生成中…</div>
        )}

        {pair.failed && !pair.assistant.content && hasTools && (
          <div className="mt-2 text-sm text-red-300/90">已停止</div>
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

        {(hasTools || pair.failed || (!isLastAssistantEmpty && pair.assistant.content)) && (
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
                className="rounded-md px-1.5 py-1 font-mono text-[12px] font-normal leading-5 tracking-wide text-[var(--text-muted)] hover:text-[var(--text-h)]"
              >
                {[
                  pair.turnMeta.goal ? '目标' : null,
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
            </div>
            {pair.failed && onRetry && !isStreaming && (
              <button
                type="button"
                title="重试本轮"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  onRetry(pair.id)
                }}
                className="rounded-md border border-red-400/30 px-2 py-1 text-xs text-red-300/90 hover:bg-red-400/10"
              >
                重试
              </button>
            )}
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
