/** Right-pointing chevron; rotates 90° to point down when open (sidebar style). */
export function ChevronIcon({
  open,
  className = '',
}: {
  /** When set, controls rotate. Omit and use `group-open:rotate-90` for `<details>`. */
  open?: boolean
  className?: string
}) {
  const rotate =
    open === undefined ? '' : open ? 'rotate-90' : 'rotate-0'
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={[
        'h-3.5 w-3.5 shrink-0 transition-transform duration-200 ease-out',
        rotate,
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      aria-hidden
    >
      <path d="M9 18l6-6-6-6" />
    </svg>
  )
}
