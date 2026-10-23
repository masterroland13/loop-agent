/** Pure helpers for ChatInput bar wrap/stack decisions (DOM-free for tests). */

/** Single-line bar min height (px); matches `min-h-8` / leading-8. */
export const BAR_MIN_HEIGHT_PX = 32

/** `composer-shell--bar` horizontal padding (`px-2.5` × 2). */
export const BAR_SHELL_PAD_X_PX = 20

/** `gap-1.5` between tools ↔ textarea ↔ tools in the single-row bar. */
export const BAR_ROW_GAP_PX = 6

/** Textarea content width in the horizontal bar (tools on the same row as text). */
export function singleRowContentWidth(
  shellClientWidth: number,
  leftToolsWidth: number,
  rightToolsWidth: number,
): number {
  const gaps = BAR_ROW_GAP_PX * 2
  return Math.max(
    shellClientWidth - BAR_SHELL_PAD_X_PX - leftToolsWidth - rightToolsWidth - gaps,
    80,
  )
}

/**
 * Whether wrap-only text (no `\n`) should use the stacked bar chrome.
 * `scrollHeight` must be measured at {@link singleRowContentWidth}, never at the
 * full shell width — otherwise expand widens the field, remeasure says one line,
 * collapse narrows and wraps again → pill/block layout oscillation.
 */
export function barNeedsWrapStack(
  scrollHeightAtSingleRowWidth: number,
  currentlyStacked: boolean,
  hasNewline: boolean,
  minHeight = BAR_MIN_HEIGHT_PX,
): boolean {
  if (hasNewline) return true
  if (currentlyStacked) return scrollHeightAtSingleRowWidth > minHeight
  return scrollHeightAtSingleRowWidth > minHeight + 4
}
