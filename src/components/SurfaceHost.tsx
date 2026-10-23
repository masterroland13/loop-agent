import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import { useT } from '../i18n'

/**
 * Side surface host for Files (and future Terminal / Browser).
 * Width is user-resizable via a thin left-edge hit target.
 */
export type SurfaceKind = 'none' | 'files' // | 'terminal' | 'browser'

/** Keep chat column readable when Files is open. */
export const CHAT_MIN_W = 440
const MIN_PANEL_W = 400
const DEFAULT_PANEL_W = 680

interface SurfaceHostProps {
  surface: Exclude<SurfaceKind, 'none'>
  onClose: () => void
  /** When false, hide without unmounting (preserves FilesPanel state). */
  visible?: boolean
  children: (api: { onClose: () => void }) => ReactNode
}

function clampPanelWidth(desired: number, rowWidth: number) {
  // Prefer chat min width; never claim more than the row can give (or the
  // file tree on the panel's right edge gets clipped off-screen).
  const max = Math.max(0, rowWidth - CHAT_MIN_W)
  const min = Math.min(MIN_PANEL_W, max)
  return Math.min(max, Math.max(min, desired))
}

export function SurfaceHost({ onClose, visible = true, children }: SurfaceHostProps) {
  const t = useT()
  const asideRef = useRef<HTMLElement>(null)
  const rowWidthRef = useRef(
    typeof window !== 'undefined' ? window.innerWidth : DEFAULT_PANEL_W + CHAT_MIN_W,
  )
  const [width, setWidth] = useState(() => {
    const row = typeof window !== 'undefined' ? window.innerWidth : DEFAULT_PANEL_W + CHAT_MIN_W
    return clampPanelWidth(
      Math.min(DEFAULT_PANEL_W, Math.floor(row * 0.58)),
      row,
    )
  })
  const dragging = useRef(false)

  // Measure the chat+surface flex row (aside's parent). Ignore 0-width while
  // display:none — otherwise width collapses to 0 and the panel never comes back.
  useEffect(() => {
    const row = asideRef.current?.parentElement
    if (!row) return
    const apply = () => {
      const rowW = row.getBoundingClientRect().width
      if (rowW < CHAT_MIN_W) return
      rowWidthRef.current = rowW
      setWidth((w) => clampPanelWidth(w, rowW))
    }
    apply()
    const ro = new ResizeObserver(apply)
    ro.observe(row)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!visible) return
    const row = asideRef.current?.parentElement
    if (!row) return
    const rowW = row.getBoundingClientRect().width
    if (rowW < CHAT_MIN_W) return
    rowWidthRef.current = rowW
    setWidth((w) => clampPanelWidth(w || DEFAULT_PANEL_W, rowW))
  }, [visible])

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const row = asideRef.current?.parentElement
      const rowRight = row?.getBoundingClientRect().right ?? window.innerWidth
      const rowW = rowWidthRef.current
      const next = rowRight - e.clientX
      setWidth(clampPanelWidth(next, rowW))
    }
    const onUp = () => {
      dragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  return (
    <aside
      ref={asideRef}
      style={{ width }}
      aria-hidden={!visible}
      className={[
        'relative flex h-full min-h-0 shrink-0 flex-col border-l border-[var(--border)] bg-[var(--bg-elevated)] shadow-[-8px_0_24px_rgba(0,0,0,0.18)]',
        visible ? '' : 'hidden',
      ].join(' ')}
    >
      {/* Thin hit target — looks like a 1px sidebar edge, not a thick purple bar */}
      <div
        role="separator"
        aria-orientation="vertical"
        title={t('files.resizePanelTitle')}
        onMouseDown={(e) => {
          e.preventDefault()
          dragging.current = true
          document.body.style.cursor = 'col-resize'
          document.body.style.userSelect = 'none'
        }}
        className="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize"
      />
      <div className="min-h-0 flex-1 overflow-hidden">{children({ onClose })}</div>
    </aside>
  )
}
