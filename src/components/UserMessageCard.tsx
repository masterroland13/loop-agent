import { ChatInput } from './ChatInput'
import type { AttachmentMeta } from '../types'
import { isImageAttachment, type ChatAttachment } from '../utils/chatAttachment'
import { attachmentDownloadUrl } from '../api/agent'

const LINE_CLAMP = 4

function needsClamp(text: string): boolean {
  if (!text.trim()) return false
  const lines = text.split('\n')
  return lines.length > LINE_CLAMP || text.length > 280
}

function displayUserText(content: string): string {
  const marker = '\n\n[附件]'
  const idx = content.indexOf(marker)
  if (idx >= 0) return content.slice(0, idx).trim()
  if (content.startsWith('（见附件）')) return ''
  if (content.startsWith('[附件]')) return ''
  return content
}

function resolveAttUrl(sessionId: string | null | undefined, att: AttachmentMeta): string {
  if (att.url?.startsWith('http')) return att.url
  if (sessionId && att.id) return attachmentDownloadUrl(sessionId, att.id)
  return att.url || '#'
}

interface UserMessageCardProps {
  pairId: string
  content: string
  index: number
  isActive: boolean
  isExpanded: boolean
  draft: string
  attachments?: ChatAttachment[]
  messageAttachments?: AttachmentMeta[]
  sessionId?: string | null
  onExpand: (pairId: string, content: string) => void
  onDraftChange: (value: string) => void
  onSend: () => void
  onAttach?: () => void
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
  isStreaming: boolean
  disabled: boolean
}

export function UserMessageCard({
  pairId,
  content,
  index,
  isActive,
  isExpanded,
  draft,
  attachments = [],
  messageAttachments,
  sessionId,
  onExpand,
  onDraftChange,
  onSend,
  onAttach,
  onModelClick,
  onRemoveAttachment,
  goalMode,
  onGoalModeToggle,
  onMultitask,
  onPlanIdea,
  pinnedGoal,
  onPinnedGoalChange,
  modelName,
  enterToSend,
  isStreaming,
  disabled,
}: UserMessageCardProps) {
  const visible = displayUserText(content)
  const clamped = needsClamp(visible)
  const cards = messageAttachments && messageAttachments.length > 0 ? messageAttachments : []

  return (
    <div
      className="sticky top-0 mb-3 scroll-mt-6 border-b border-transparent bg-[var(--bg)] pb-3 pt-1 shadow-[0_8px_12px_-8px_var(--bg)]"
      style={{ zIndex: 1000 - index }}
    >
      {isExpanded ? (
        <div data-expanded-user-card>
          <ChatInput
            variant="card"
            value={draft}
            onChange={onDraftChange}
            onSend={() => {
              onSend()
            }}
            onAttach={onAttach}
            onModelClick={onModelClick}
            onRemoveAttachment={onRemoveAttachment}
            goalMode={goalMode}
            onGoalModeToggle={onGoalModeToggle}
            onMultitask={onMultitask}
            onPlanIdea={onPlanIdea}
            pinnedGoal={pinnedGoal}
            onPinnedGoalChange={onPinnedGoalChange}
            isStreaming={isStreaming}
            disabled={disabled}
            attachments={attachments}
            modelName={modelName}
            enterToSend={enterToSend}
            placeholder="Send follow-up"
            highlighted={isActive}
          />
        </div>
      ) : (
        <button
          type="button"
          onClick={() => onExpand(pairId, displayUserText(content) || content)}
          className={[
            'user-bubble-shell w-full px-4 py-2.5 text-left transition-[box-shadow,outline-color] duration-200',
            isActive
              ? 'outline outline-2 outline-[var(--pair-highlight)] outline-offset-2'
              : 'outline outline-2 outline-transparent outline-offset-2 hover:outline-[var(--border-subtle)]',
          ].join(' ')}
        >
          {cards.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2" onClick={(e) => e.stopPropagation()}>
              {cards.map((att) => {
                const href = resolveAttUrl(sessionId, att)
                const image = isImageAttachment({
                  contentType: att.content_type,
                  filename: att.filename,
                })
                return (
                  <a
                    key={att.id}
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[13px] text-[var(--accent)] hover:underline"
                  >
                    {image ? (
                      <img
                        src={href}
                        alt=""
                        className="h-8 w-8 rounded object-cover"
                      />
                    ) : null}
                    <span>
                      {att.filename}
                      <span className="ml-1.5 text-[11px] text-[var(--text-muted)]">
                        {att.size >= 1024 ? `${Math.round(att.size / 1024)}KB` : `${att.size}B`}
                      </span>
                    </span>
                  </a>
                )
              })}
            </div>
          )}
          {visible ? (
            <p
              className={[
                'whitespace-pre-wrap text-[15px] font-[480] leading-[1.75] tracking-[0.02em] text-[var(--text-h)]',
                clamped ? 'line-clamp-4' : '',
              ].join(' ')}
            >
              {visible}
            </p>
          ) : null}
        </button>
      )}
    </div>
  )
}
