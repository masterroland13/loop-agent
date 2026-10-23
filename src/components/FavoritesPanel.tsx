import type { FavoriteItem } from '../api/agent'
import { useT } from '../i18n'

interface FavoritesPanelProps {
  favorites: FavoriteItem[]
  isOpen: boolean
  onClose: () => void
  onSelectFavorite: (item: FavoriteItem) => void
  onUnfavorite: (item: FavoriteItem) => void
  formatPreview: (content: string, maxLength?: number) => string
}

export function FavoritesPanel({
  favorites,
  isOpen,
  onClose,
  onSelectFavorite,
  onUnfavorite,
  formatPreview,
}: FavoritesPanelProps) {
  const t = useT()
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="flex h-full w-80 flex-col border-l border-[var(--border)] bg-[var(--bg-elevated)]">
        <div className="flex h-12 items-center justify-between px-4">
          <span className="text-sm font-medium text-[var(--text-h)]">{t('favorites.title')}</span>
          <button
            type="button"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] hover:bg-[var(--surface-hover)]"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 pb-3">
          {favorites.length === 0 ? (
            <p className="py-12 text-center text-sm text-[var(--text-muted)]">{t('favorites.empty')}</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {favorites.map((item) => (
                <li key={item.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelectFavorite(item)}
                    className="w-full rounded-lg bg-[var(--surface)] px-3 py-2.5 pr-9 text-left transition-colors hover:bg-[var(--surface-hover)]"
                  >
                    <div className="mb-1 flex items-center gap-2 text-[11px] text-[var(--text-dim)]">
                      <span className="truncate">{item.session_title}</span>
                      <span>{new Date(item.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="line-clamp-2 text-[13px] text-[var(--text-h)]">
                      {formatPreview(item.user_content)}
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => onUnfavorite(item)}
                    className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded text-[var(--star)] opacity-0 group-hover:opacity-100"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-3.5 w-3.5">
                      <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                    </svg>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
