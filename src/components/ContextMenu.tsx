import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { MenuChevronRightIcon } from './ContextMenuIcons'

export type ContextMenuItem =
  | {
      type: 'item'
      id: string
      label: string
      icon?: ReactNode
      shortcut?: string
      danger?: boolean
      disabled?: boolean
      onClick: () => void
    }
  | { type: 'separator' }
  | {
      type: 'submenu'
      id: string
      label: string
      icon?: ReactNode
      children: Exclude<ContextMenuItem, { type: 'submenu' }>[]
    }

interface ContextMenuProps {
  x: number
  y: number
  onClose: () => void
  items: ContextMenuItem[]
}

/** Compact Cursor-like panel — no transform animation (keeps fixed/absolute coords honest). */
const PANEL =
  'rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] py-1 shadow-[0_8px_28px_rgba(0,0,0,0.45),0_0_0_1px_rgba(255,255,255,0.05)]'

function MenuSeparator() {
  return <div className="mx-2 my-0.5 h-px bg-[var(--border-subtle)]" role="separator" />
}

function MenuItemButton({
  label,
  icon,
  shortcut,
  danger,
  disabled,
  hasSubmenu,
  highlighted,
  onClick,
}: {
  label: string
  icon?: ReactNode
  shortcut?: string
  danger?: boolean
  disabled?: boolean
  hasSubmenu?: boolean
  highlighted?: boolean
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      role="menuitem"
      disabled={disabled}
      onClick={onClick}
      className={[
        // leading-none + truncate(overflow:hidden) clips descenders (e.g. "Copy" → y)
        'flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-left text-[13px] leading-5 tracking-[0.01em] transition-colors duration-75',
        danger
          ? highlighted
            ? 'bg-red-500/12 text-red-400'
            : 'text-red-400 hover:bg-red-500/10'
          : highlighted
            ? 'bg-[var(--surface-hover)] text-[var(--text-h)]'
            : 'text-[var(--text-h)] hover:bg-[var(--surface-hover)]',
        disabled ? 'pointer-events-none opacity-40' : '',
      ].join(' ')}
    >
      {/* Icons inherit currentColor — same brightness as label (Cursor style) */}
      <span className="flex h-4 w-4 shrink-0 items-center justify-center">
        {icon ?? <span className="inline-block h-4 w-4" />}
      </span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {shortcut && (
        <span className="shrink-0 pl-2 font-mono text-[10px] text-[var(--text-dim)]">{shortcut}</span>
      )}
      {hasSubmenu && <MenuChevronRightIcon />}
    </button>
  )
}

/**
 * Submenu is position:absolute relative to its row — NOT fixed.
 * Fixed + parent transform/animation was causing the flyout to float away from Copy.
 */
function SubmenuFlyout({
  children,
  onMouseEnter,
  onMouseLeave,
}: {
  children: ReactNode
  onMouseEnter: () => void
  onMouseLeave: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [flipLeft, setFlipLeft] = useState(false)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    if (rect.right > window.innerWidth - 6) setFlipLeft(true)
  }, [])

  return (
    <div
      ref={ref}
      role="menu"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className={[
        'absolute top-[-2px] z-[70] min-w-[120px] max-w-[180px] px-0.5',
        PANEL,
        flipLeft ? 'right-full mr-0.5' : 'left-full ml-0.5',
      ].join(' ')}
    >
      {children}
    </div>
  )
}

export function ContextMenu({ x, y, onClose, items }: ContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const [openSubmenu, setOpenSubmenu] = useState<string | null>(null)
  const [pos, setPos] = useState({ top: y, left: x })
  const closeTimer = useRef<number | null>(null)

  useLayoutEffect(() => {
    const el = menuRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    let top = y
    let left = x
    if (left + rect.width > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - rect.width - 8)
    }
    if (top + rect.height > window.innerHeight - 8) {
      top = Math.max(8, window.innerHeight - rect.height - 8)
    }
    setPos({ top, left })
  }, [x, y])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    const onPointer = (e: MouseEvent) => {
      const target = e.target as Node
      if (menuRef.current?.contains(target)) return
      onClose()
    }
    // Defer so the opening contextmenu event doesn't immediately close us.
    const tid = window.setTimeout(() => {
      window.addEventListener('keydown', onKey)
      window.addEventListener('mousedown', onPointer)
    }, 0)
    return () => {
      window.clearTimeout(tid)
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('mousedown', onPointer)
      if (closeTimer.current) window.clearTimeout(closeTimer.current)
    }
  }, [onClose])

  const scheduleSubmenuClose = () => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => setOpenSubmenu(null), 100)
  }

  const cancelSubmenuClose = () => {
    if (closeTimer.current) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }

  const renderLeaf = (
    item: Extract<ContextMenuItem, { type: 'item' }>,
    key: string,
  ) => (
    <MenuItemButton
      key={key}
      label={item.label}
      icon={item.icon}
      shortcut={item.shortcut}
      danger={item.danger}
      disabled={item.disabled}
      onClick={() => {
        if (!item.disabled) {
          item.onClick()
          onClose()
        }
      }}
    />
  )

  const menu = (
    <div
      ref={menuRef}
      className={`fixed z-[60] min-w-[168px] px-1 ${PANEL}`}
      style={{ top: pos.top, left: pos.left }}
      role="menu"
    >
      {items.map((item, idx) => {
        if (item.type === 'separator') {
          return <MenuSeparator key={`sep-${idx}`} />
        }

        if (item.type === 'submenu') {
          const isOpen = openSubmenu === item.id
          return (
            <div
              key={item.id}
              className="relative"
              onMouseEnter={() => {
                cancelSubmenuClose()
                setOpenSubmenu(item.id)
              }}
              onMouseLeave={scheduleSubmenuClose}
            >
              <MenuItemButton
                label={item.label}
                icon={item.icon}
                hasSubmenu
                highlighted={isOpen}
              />
              {isOpen && (
                <SubmenuFlyout
                  onMouseEnter={cancelSubmenuClose}
                  onMouseLeave={scheduleSubmenuClose}
                >
                  {item.children.map((child, childIdx) => {
                    if (child.type === 'separator') {
                      return <MenuSeparator key={`sub-sep-${childIdx}`} />
                    }
                    return renderLeaf(child, child.id)
                  })}
                </SubmenuFlyout>
              )}
            </div>
          )
        }

        return renderLeaf(item, item.id)
      })}
    </div>
  )

  return createPortal(menu, document.body)
}
