import { useT } from '../i18n'

interface MessageNavigatorProps {
  currentIndex: number
  total: number
  onPrevious: () => void
  onNext: () => void
}

export function MessageNavigator({
  currentIndex,
  total,
  onPrevious,
  onNext,
}: MessageNavigatorProps) {
  const t = useT()
  return (
    <div className="pointer-events-none fixed right-5 top-1/2 z-40 flex -translate-y-1/2 flex-col gap-5">
      <button
        type="button"
        aria-label={t('common.previous')}
        disabled={currentIndex <= 0}
        onClick={onPrevious}
        className="pointer-events-auto flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--text-h)] shadow-[0_0_0_1px_rgba(255,255,255,0.06)] transition-colors hover:border-[var(--input-focus)] hover:bg-[var(--surface-hover)] hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.75} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 opacity-95">
          <path d="M18 15l-6-6-6 6" />
        </svg>
      </button>
      <button
        type="button"
        aria-label={t('common.next')}
        disabled={currentIndex >= total - 1}
        onClick={onNext}
        className="pointer-events-auto flex h-10 w-10 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)] text-[var(--text-h)] shadow-[0_0_0_1px_rgba(255,255,255,0.06)] transition-colors hover:border-[var(--input-focus)] hover:bg-[var(--surface-hover)] hover:text-white disabled:cursor-not-allowed disabled:opacity-45"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.75} strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5 opacity-95">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
    </div>
  )
}
