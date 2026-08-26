import { forwardRef } from 'react'
import type { MessagePair, ToolTraceItem } from '../types'
import { MessagePairItem } from './MessagePairItem'

interface MessageListProps {
  pairs: MessagePair[]
  currentIndex: number
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

export const MessageList = forwardRef<HTMLDivElement, MessageListProps>(
  function MessageList(
    {
      pairs,
      currentIndex,
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
    },
    ref,
  ) {
    return (
      <div ref={ref} className="min-h-0 flex-1 overflow-y-auto scroll-smooth">
        <div className="mx-auto max-w-3xl px-6 py-8">
          {pairs.map((pair, index) => (
            <MessagePairItem
              key={pair.id}
              pair={pair}
              index={index}
              isActive={index === currentIndex}
              isStreaming={isStreaming && index === pairs.length - 1}
              awaitingApproval={awaitingApproval && index === pairs.length - 1}
              sessionId={sessionId}
              expandedUserPairId={expandedUserPairId}
              expandedDraft={expandedDraft}
              expandedAttachments={expandedAttachments}
              onExpandUser={onExpandUser}
              onExpandedDraftChange={onExpandedDraftChange}
              onExpandedSend={onExpandedSend}
              onExpandedAttach={onExpandedAttach}
              onToggleFavorite={onToggleFavorite}
              onRetry={onRetry}
              onRetryToolStep={onRetryToolStep}
              setItemRef={setItemRef}
              inputToolbar={inputToolbar}
            />
          ))}
        </div>
      </div>
    )
  },
)
