import type { ReactNode } from 'react'

/**
 * Context-menu icons matching Cursor / Lucide.
 * 24×24 viewBox → 16×16 display, strokeWidth 2, inherit currentColor (same as label).
 */

type IconProps = { className?: string }

function Svg({
  children,
  className = 'h-4 w-4 shrink-0',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      {children}
    </svg>
  )
}

/** Simple upright pin — round head + needle straight down (fills ~3–22 like other menu icons). */
function PushpinPaths() {
  return (
    <>
      <circle cx="12" cy="6.25" r="4.5" />
      <path d="M12 10.75V22" />
    </>
  )
}

export function MenuPinIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      {/* Slight scale — thin stroke reads smaller than pencil/copy at same box size */}
      <g transform="translate(12 12) scale(1.08) translate(-12 -12)">
        <PushpinPaths />
      </g>
    </Svg>
  )
}

/** Cursor Rename — pencil */
export function MenuPencilIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
      <path d="m15 5 4 4" />
    </Svg>
  )
}

/** Cursor Mark as Unread — bell (+ blue badge like Cursor) */
export function MenuBellIcon({
  className,
  withDot = true,
}: IconProps & { withDot?: boolean }) {
  return (
    <span className="relative inline-flex h-4 w-4 shrink-0">
      <Svg className={className ?? 'h-4 w-4'}>
        <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </Svg>
      {withDot && (
        <span
          className="absolute right-0 top-0 h-1.5 w-1.5 rounded-full bg-[#3b82f6] ring-[1.5px] ring-[var(--bg-elevated)]"
          aria-hidden
        />
      )}
    </span>
  )
}

/** Cursor Copy */
export function MenuCopyIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </Svg>
  )
}

/** Cursor Copy Agent ID */
export function MenuHashIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <line x1="4" x2="20" y1="9" y2="9" />
      <line x1="4" x2="20" y1="15" y2="15" />
      <line x1="10" x2="8" y1="3" y2="21" />
      <line x1="16" x2="14" y1="3" y2="21" />
    </Svg>
  )
}

/** Cursor Copy Transcript */
export function MenuTranscriptIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </Svg>
  )
}

/** Cursor Delete (row sets red via currentColor) */
export function MenuTrashIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M3 6h18" />
      <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
      <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
      <line x1="10" x2="10" y1="11" y2="17" />
      <line x1="14" x2="14" y1="11" y2="17" />
    </Svg>
  )
}

export function MenuSidebarRemoveIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <rect width="18" height="18" x="3" y="3" rx="2" />
      <path d="M9 3v18" />
      <path d="m16 15-3-3 3-3" />
    </Svg>
  )
}

export function MenuChevronRightIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-3.5 w-3.5 shrink-0 opacity-50"
      aria-hidden
    >
      <path d="m9 18 6-6-6-6" />
    </svg>
  )
}

export function SessionPinIcon() {
  return (
    <Svg className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]">
      <PushpinPaths />
    </Svg>
  )
}

/** Bind session to an existing workspace — folder with inbound arrow (folder-input) */
export function MenuBindFolderIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M2 9V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1" />
      <path d="M2 13h10" />
      <path d="m9 10 3 3-3 3" />
    </Svg>
  )
}

/**
 * Scissors — Cut.
 * Two continuous polylines through the pivot (12,12) so blade/handle strokes
 * don't butt-end at the center and look broken.
 */
export function MenuCutIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M20 4 12 12 20 20" />
      <path d="M8.12 8.12 12 12 8.12 15.88" />
    </Svg>
  )
}

/** New file — matches other menu icon weight */
export function MenuNewFileIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M12 11v6" />
      <path d="M9 14h6" />
    </Svg>
  )
}

/** Message + — Add to Chat */
export function MenuChatAddIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M12 7v6" />
      <path d="M9 10h6" />
    </Svg>
  )
}

/** External / reveal in file explorer */
export function MenuRevealIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M15 3h6v6" />
      <path d="M10 14 21 3" />
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    </Svg>
  )
}

/** Folder glyph for Bind submenu workspace rows */
export function MenuFolderIcon({ className }: IconProps) {
  return (
    <Svg className={className}>
      <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9l-.8-1.2A2 2 0 0 0 7.9 2H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2z" />
    </Svg>
  )
}

/** Solid blue unread indicator — Cursor-style */
export function UnreadDot({ className = '' }: { className?: string }) {
  return (
    <span
      className={['h-[5px] w-[5px] shrink-0 rounded-full bg-[#3b82f6]', className]
        .filter(Boolean)
        .join(' ')}
      aria-label="Unread"
    />
  )
}
