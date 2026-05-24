/**
 * Pure routing decision for the BI v2 global search input (BiTopBar).
 *
 * Centralised so the topbar can render the routing target in the
 * `actor` slot ("已搜 X：跳转到 Y") without re-implementing the keyword
 * heuristic inline. Unit-tested with `node --test` against Node 24's
 * native TS type stripping (no `.tsx` loader).
 *
 * Routing rules (unchanged from the previous inline logic):
 *  - empty / whitespace-only query → null target (no navigation)
 *  - commerce-keyword regex match (`ord` / `order` / `ledger` / `wallet`
 *    / `pay` / `payment` / `charge` / `recharge` / `txn`) AND commerce
 *    section is enabled → 'commerce'
 *  - else if member-ops section is enabled → 'member-ops'
 *  - else null
 */
export type GlobalSearchSection = 'commerce' | 'member-ops'

export type GlobalSearchRouteDecision = {
  section: GlobalSearchSection | null
  reason: 'empty' | 'commerce-keyword' | 'member-identity' | 'no-enabled-target'
  /**
   * Human-readable Chinese label for the target panel. Stable across
   * renames so the topbar copy stays consistent with the side nav.
   */
  targetLabel: string | null
}

export type GlobalSearchFlagSnapshot = {
  commerceEnabled: boolean
  memberOpsEnabled: boolean
}

const COMMERCE_KEYWORD_PATTERN =
  /^(ord|order|ledger|wallet|pay|payment|charge|recharge|txn)[\w:./-]*/i

export function looksLikeCommerceQuery(query: string): boolean {
  return COMMERCE_KEYWORD_PATTERN.test(query.trim())
}

const SECTION_LABELS: Readonly<Record<GlobalSearchSection, string>> = {
  commerce: '商品账务',
  'member-ops': '会员运营',
}

export function routeForGlobalSearch(
  query: string,
  flags: GlobalSearchFlagSnapshot,
): GlobalSearchRouteDecision {
  const trimmed = query.trim()
  if (!trimmed) {
    return { section: null, reason: 'empty', targetLabel: null }
  }
  if (looksLikeCommerceQuery(trimmed) && flags.commerceEnabled) {
    return {
      section: 'commerce',
      reason: 'commerce-keyword',
      targetLabel: SECTION_LABELS.commerce,
    }
  }
  if (flags.memberOpsEnabled) {
    return {
      section: 'member-ops',
      reason: 'member-identity',
      targetLabel: SECTION_LABELS['member-ops'],
    }
  }
  return { section: null, reason: 'no-enabled-target', targetLabel: null }
}

/**
 * Renders the actor-slot string the BiTopBar should show after a
 * search has been submitted, e.g. "已搜 13800138000：跳转到 会员运营".
 * Returns null when the input is effectively empty.
 */
export function describeGlobalSearchActor(
  query: string,
  decision: GlobalSearchRouteDecision,
): string | null {
  const trimmed = query.trim()
  if (!trimmed) {
    return null
  }
  if (decision.targetLabel) {
    return `已搜 ${trimmed}：跳转到 ${decision.targetLabel}`
  }
  return `已搜 ${trimmed}：无可用目标 panel`
}
