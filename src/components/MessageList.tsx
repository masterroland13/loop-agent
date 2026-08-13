import { forwardRef } from 'react'
import type { MessagePair, ToolTraceItem } from '../types'
import { MessagePairItem } from './MessagePairItem'

interface MessageListProps {
  pairs: MessagePair[]
  currentIndex: number
  isStreaming?: boolean
  awaitingApproval?: boolean
  onToggleFavorite: (id: string) => void
  onRetry?: (pairId: string) => void
  onRetryToolStep?: (pairId: string, item: ToolTraceItem) => void
  setItemRef: (index: number) => (element: HTMLDivElement | null) => void
}

export const MessageList = forwardRef<HTMLDivElement, MessageListProps>(
  function MessageList(
    {
      pairs,
      currentIndex,
      isStreaming,
      awaitingApproval,
      onToggleFavorite,
      onRetry,
      onRetryToolStep,
      setItemRef,
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
              onToggleFavorite={onToggleFavorite}
              onRetry={onRetry}
              onRetryToolStep={onRetryToolStep}
              setItemRef={setItemRef}
            />
          ))}
        </div>
      </div>
    )
  },
)
