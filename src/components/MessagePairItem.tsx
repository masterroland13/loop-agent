import { useState } from 'react'
import type { MessagePair } from '../types'
import { Markdown } from './Markdown'
import { TurnActivity, type GateFocusTarget } from './TurnActivity'
import { useWorkedForLabel, WorkedForText } from './WorkedForText'
import { UserMessageCard } from './UserMessageCard'
import { useT } from '../i18n'

/** Strip leading 「目标：」 so the strip label does not read「目标 目标：…」. */
function formatGoalBody(goal: string): string {
  const t = goal.trim()
  const stripped = t.replace(/^(目标|Goal)\s*[:：]\s*/i, '').trim()
  return stripped || t
}

const EMPTY_WORKED =
  'text-[15px] font-normal leading-[1.8] tracking-[0.02em] text-[var(--text-muted)]'

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
  onContinueSoftLand?: (pairId: string) => void
  onFocusGate?: (target: GateFocusTarget) => void
  setItemRef: (index: number) => (element: HTMLDivElement | null) => void
  inputToolbar?: {
    onModelClick?: (anchor: DOMRect) => void
    onRemoveAttachment?: (localKey: string) => void
    goalMode?: boolean
    onGoalModeToggle?: () => void
    onMultitask?: () => void
    onPlanIdea?: () => void
    pinnedGoal?: string | null
    onPinnedGoalChange?: (goal: string | null) => void
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
  onContinueSoftLand,
  onFocusGate,
  setItemRef,
  inputToolbar,
}: MessagePairItemProps) {
  const t = useT()
  const [copied, setCopied] = useState(false)
  const hasActivity = Boolean(pair.activity?.segments?.length)
  const hasTools = hasActivity || Boolean(pair.toolTrace && pair.toolTrace.length > 0)
  const goalText = pair.goal || pair.turnMeta?.goal
  const previousGoal = pair.previousGoal
  const goalChanged = Boolean(previousGoal && goalText && previousGoal !== goalText)
  const turnBusy = Boolean(isStreaming || pair.turnInProgress)
  const isLastAssistantEmpty = turnBusy && !pair.assistant.content && !hasTools
  const isUserExpanded = expandedUserPairId === pair.id
  const turnStartedAt =
    pair.activityStartedAt ?? pair.assistant.createdAt ?? pair.user.createdAt
  const emptyWorkedLabel = useWorkedForLabel(turnStartedAt, {
    elapsedMs: pair.turnMeta?.elapsed_ms,
    isStreaming: isLastAssistantEmpty && !awaitingApproval,
  })

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
        onRemoveAttachment={inputToolbar?.onRemoveAttachment}
        goalMode={inputToolbar?.goalMode}
        onGoalModeToggle={inputToolbar?.onGoalModeToggle}
        onMultitask={inputToolbar?.onMultitask}
        onPlanIdea={inputToolbar?.onPlanIdea}
        pinnedGoal={inputToolbar?.pinnedGoal}
        onPinnedGoalChange={inputToolbar?.onPinnedGoalChange}
        modelName={inputToolbar?.modelName}
        enterToSend={inputToolbar?.enterToSend}
        isStreaming={Boolean(isStreaming)}
        disabled={Boolean(inputToolbar?.disabled)}
      />

      <div className="relative pl-0.5">
        {goalText ? (
          <div
            className="mb-3 max-w-full truncate rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-[13px] leading-5 text-[var(--text-h)]"
            title={goalChanged ? `${previousGoal} → ${goalText}` : goalText}
          >
            <span className="mr-1.5 font-medium text-[var(--text-muted)]">
              {goalChanged ? t('message.goalChanged') : t('message.goal')}
            </span>
            {formatGoalBody(goalText)}
          </div>
        ) : null}

        {hasActivity ? (
          <TurnActivity
            snapshot={pair.activity}
            startedAt={pair.activityStartedAt}
            elapsedMs={pair.turnMeta?.elapsed_ms}
            isStreaming={turnBusy}
            onFocusGate={onFocusGate}
          />
        ) : null}

        {pair.turnInProgress && !isStreaming && hasTools && (
          <div className="mt-2 text-sm text-[var(--text-muted)]">{t('message.background')}</div>
        )}

        {pair.failed && !pair.assistant.content && hasTools && (
          <div className="mt-2 text-sm text-red-300/90">{t('message.stopped')}</div>
        )}

        {isLastAssistantEmpty ? (
          awaitingApproval ? (
            <div className={EMPTY_WORKED}>{t('message.waitingApproval')}</div>
          ) : (
            <div className="text-[15px] font-normal leading-[1.8] tracking-[0.02em]">
              <WorkedForText shimmer>{emptyWorkedLabel}</WorkedForText>
            </div>
          )
        ) : pair.assistant.content ? (
          <div
            className={[
              'text-[15px] font-[520] leading-[1.8] tracking-[0.02em]',
              pair.failed ? 'text-red-300/90' : 'text-[var(--text-h)]',
            ].join(' ')}
          >
            {pair.softLanded ? (
              <div className="mb-2 flex flex-wrap items-center gap-2 rounded border border-amber-700/80 bg-amber-950/35 px-2 py-1.5 text-xs font-normal tracking-normal text-amber-100">
                <span className="min-w-0 flex-1">
                  {t('message.softLand')}
                </span>
                {onContinueSoftLand && !isStreaming && !pair.turnInProgress ? (
                  <button
                    type="button"
                    title={t('message.softLandContinue')}
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      onContinueSoftLand(pair.id)
                    }}
                    className="shrink-0 rounded border border-amber-500/50 bg-amber-900/50 px-2 py-0.5 text-amber-50 hover:bg-amber-800/60"
                  >
                    {t('common.continue')}
                  </button>
                ) : null}
              </div>
            ) : null}
            <Markdown content={pair.assistant.content} />
            {isStreaming && (
              <span className="ml-1.5 inline-block h-3.5 w-[7px] animate-pulse rounded-[2px] bg-[var(--accent)] align-[-2px]" />
            )}
          </div>
        ) : isStreaming && hasTools ? (
          <div className="text-sm text-[var(--text-muted)]">
            {awaitingApproval ? t('message.waitingApprovalShort') : t('message.summarizing')}
          </div>
        ) : null}

        {(hasTools || pair.failed || (!isLastAssistantEmpty && pair.assistant.content)) && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {pair.turnMeta && (
              <button
                type="button"
                title={t('message.copyMeta')}
                onClick={async (e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  const payload = {
                    ...pair.turnMeta,
                    session_id: sessionId ?? null,
                  }
                  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
                }}
                className="rounded-md px-1.5 py-1 font-mono text-[12px] font-normal leading-5 tracking-wide text-[var(--text-muted)] hover:text-[var(--text-h)]"
              >
                {[
                  sessionId || null,
                  pair.turnMeta.goal ? t('message.metaGoal') : null,
                  pair.turnMeta.model,
                  `${(pair.turnMeta.elapsed_ms / 1000).toFixed(1)}s`,
                  `~${pair.turnMeta.approx_prompt_tokens}+${pair.turnMeta.approx_completion_tokens}`,
                  pair.turnMeta.compressed ? t('message.metaCompressed') : null,
                  pair.turnMeta.memory_injected ? t('message.metaMemory') : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </button>
            )}
            <div className="flex items-center gap-1">
            {pair.assistant.content && (
              <ActionBtn title={copied ? t('common.copied') : t('common.copy')} pressed={copied} onClick={handleCopy} icon="copy" />
            )}
            <ActionBtn
              title={pair.isFavorite ? t('common.unfavorite') : t('common.favorite')}
              pressed={pair.isFavorite}
              onClick={() => onToggleFavorite(pair.id)}
              icon="star"
            />
            </div>
            {pair.failed && onRetry && !isStreaming && (
              <button
                type="button"
                title={t('common.retry')}
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  onRetry(pair.id)
                }}
                className="rounded-md border border-red-400/30 px-2 py-1 text-xs text-red-300/90 hover:bg-red-400/10"
              >
                {t('common.retry')}
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
  icon,
}: {
  title: string
  onClick: () => void
  pressed?: boolean
  icon: 'copy' | 'star'
}) {
  const active = Boolean(pressed)
  return (
    <button
      type="button"
      title={title}
      aria-pressed={active}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        onClick()
      }}
      className={[
        'inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors',
        active && icon === 'star'
          ? 'text-[var(--star)]'
          : active
            ? 'text-[var(--text-h)]'
            : 'text-[var(--text-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]',
      ].join(' ')}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill={active && icon === 'star' ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-4 w-4"
        aria-hidden
      >
        {icon === 'copy' ? (
          <>
            {/* Lucide / Cursor copy — same geometry as ContextMenuIcons.MenuCopyIcon */}
            <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
          </>
        ) : (
          /* Lucide star — smooth 5-point, fills cleanly when favorited */
          <path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z" />
        )}
      </svg>
    </button>
  )
}
