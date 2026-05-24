/**
 * Single source of truth for the feedback panel's read window.
 *
 * The previous panel had `getBiFeedback({ days: 30, limit: 100 })` paired
 * with a `<Tile hint="近 7d" />`. The hint never reflected the actual
 * fetch window, which silently misled operators about how recent the
 * feedback counts were.
 *
 * Centralising the value forces fetch + hint to stay in sync; if the
 * window changes, both follow.
 *
 * Pure module (no React imports) so it can be unit-tested with
 * `node --test` against Node 24's native TS type stripping.
 */
export const FEEDBACK_WINDOW_DAYS = 30 as const

/**
 * Human-readable label for the window, used in panel `hint` slots.
 */
export function feedbackWindowHint(): string {
  return `近 ${FEEDBACK_WINDOW_DAYS}d`
}
