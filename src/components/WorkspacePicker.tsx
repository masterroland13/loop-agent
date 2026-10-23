import { useCallback, useEffect, useState } from 'react'
import {
  browseWorkspace,
  clearWorkspace,
  fetchWorkspace,
  setWorkspace,
  type WorkspaceStatus,
} from '../api/agent'
import { useT } from '../i18n'

interface WorkspacePickerProps {
  isOpen: boolean
  onClose: () => void
  onSaved: (status: WorkspaceStatus) => void
}

export function WorkspacePicker({ isOpen, onClose, onSaved }: WorkspacePickerProps) {
  const t = useT()
  const [status, setStatus] = useState<WorkspaceStatus | null>(null)
  const [browsePath, setBrowsePath] = useState('')
  const [parent, setParent] = useState<string | null>(null)
  const [dirs, setDirs] = useState<{ name: string; path: string }[]>([])
  const [manualPath, setManualPath] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const loadBrowse = useCallback(async (path?: string) => {
    setError(null)
    try {
      const data = await browseWorkspace(path)
      setBrowsePath(data.path)
      setParent(data.parent)
      setDirs(data.directories)
      setManualPath(data.path)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('workspace.browseFailed'))
    }
  }, [t])

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    ;(async () => {
      try {
        const ws = await fetchWorkspace()
        if (cancelled) return
        setStatus(ws)
        await loadBrowse(ws.root || undefined)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : t('workspace.loadFailed'))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isOpen, loadBrowse, t])

  useEffect(() => {
    if (!isOpen) return
    const handle = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handle)
    return () => window.removeEventListener('keydown', handle)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const handleSelect = async (path: string) => {
    setBusy(true)
    setError(null)
    try {
      const next = await setWorkspace(path)
      setStatus(next)
      onSaved(next)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('workspace.setFailed'))
    } finally {
      setBusy(false)
    }
  }

  const handleClear = async () => {
    setBusy(true)
    setError(null)
    try {
      const next = await clearWorkspace()
      setStatus(next)
      onSaved(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('workspace.clearFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl border border-[var(--border)] bg-[var(--bg-elevated)] shadow-xl">
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-[var(--text-h)]">{t('workspace.modalTitle')}</h2>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">{t('workspace.modalSubtitle')}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--text-h)]"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-4 w-4">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {status?.configured && (
            <div className="mb-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface)] px-3 py-2 text-xs">
              <div className="text-[var(--text-muted)]">{t('workspace.currentWorkspace')}</div>
              <div className="mt-0.5 break-all font-mono text-[var(--text-h)]">{status.root}</div>
            </div>
          )}

          <div className="mb-3 flex gap-2">
            <input
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              placeholder={t('workspace.pathPlaceholder')}
              className="min-w-0 flex-1 rounded-lg border border-[var(--input-border)] bg-[var(--input-bg)] px-3 py-2 font-mono text-sm text-[var(--text-h)] outline-none focus:border-[var(--input-focus)]"
            />
            <button
              type="button"
              disabled={busy || !manualPath.trim()}
              onClick={() => handleSelect(manualPath.trim())}
              className="shrink-0 rounded-lg bg-[var(--text-h)] px-3 py-2 text-sm font-medium text-[var(--bg)] disabled:opacity-40"
            >
              {t('workspace.bind')}
            </button>
          </div>

          <div className="mb-2 flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span className="truncate font-mono">{browsePath || '…'}</span>
            <div className="flex gap-2">
              {parent && (
                <button type="button" className="hover:text-[var(--text-h)]" onClick={() => loadBrowse(parent)}>
                  {t('workspace.parent')}
                </button>
              )}
              <button type="button" className="hover:text-[var(--text-h)]" onClick={() => loadBrowse(browsePath)}>
                {t('workspace.refresh')}
              </button>
            </div>
          </div>

          <div className="max-h-64 overflow-y-auto rounded-lg border border-[var(--border-subtle)]">
            {dirs.length === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-[var(--text-muted)]">{t('workspace.noSubdirs')}</div>
            ) : (
              dirs.map((d) => (
                <div
                  key={d.path}
                  className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2 last:border-b-0 hover:bg-[var(--surface-hover)]"
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left text-sm text-[var(--text-h)]"
                    onClick={() => loadBrowse(d.path)}
                  >
                    {d.name}/
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleSelect(d.path)}
                    className="shrink-0 rounded-md px-2 py-1 text-xs text-[var(--text-muted)] hover:bg-[var(--surface)] hover:text-[var(--text-h)]"
                  >
                    {t('workspace.selectThis')}
                  </button>
                </div>
              ))
            )}
          </div>

          {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        </div>

        <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-5 py-3">
          <button
            type="button"
            disabled={busy || !status?.configured}
            onClick={handleClear}
            className="text-sm text-[var(--text-muted)] hover:text-[var(--text-h)] disabled:opacity-40"
          >
            {t('workspace.clearBinding')}
          </button>
          <button
            type="button"
            disabled={busy || !browsePath}
            onClick={() => handleSelect(browsePath)}
            className="rounded-lg bg-[var(--text-h)] px-4 py-2 text-sm font-medium text-[var(--bg)] disabled:opacity-40"
          >
            {t('workspace.useCurrentDir')}
          </button>
        </div>
      </div>
    </div>
  )
}
