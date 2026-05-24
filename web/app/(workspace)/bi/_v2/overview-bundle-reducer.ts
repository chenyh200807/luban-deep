/**
 * Pure reducer that turns the three parallel BI overview fetches into the
 * panel's `LiveBundle` + display source state.
 *
 * Kept as its own module (no React imports) so it can be unit-tested with
 * `node --test` against Node 24's native TS type stripping, without pulling
 * `.tsx` files through the loader.
 *
 * Behavior must remain identical to the previous serial-await flow:
 *  - overview success: cards = overview.cards
 *  - overview success + overview.alerts is non-empty: alerts = overview.alerts
 *  - overview success + overview.alerts empty: alerts = anomalies items (or empty fallback)
 *  - overview failure: bundle = empty fallback, source = 'error'
 *  - trend success: trend = trend.points
 *  - trend failure: trend = empty fallback
 *  - anomalies failure or empty: alerts fall back to overview.alerts (which may itself be empty)
 *  - errors[] aggregates any individual fetch failure
 *  - source = 'error' iff there was at least one error, else 'live'
 */
import type {
  BiAlertItem,
  BiAnomalyData,
  BiMetricCard,
  BiOverviewData,
  BiTrendData,
  BiTrendPoint,
} from '@/lib/bi-api'

export type OverviewLiveBundle = {
  cards: ReadonlyArray<BiMetricCard>
  alerts: ReadonlyArray<BiAlertItem>
  trend: ReadonlyArray<BiTrendPoint>
  generatedAt: number
  partial: boolean
  errors: string[]
}

export type OverviewReducerSource = 'live' | 'error'

export type OverviewReducerResult = {
  bundle: OverviewLiveBundle
  source: OverviewReducerSource
}

export type OverviewReducerInput = {
  overview: PromiseSettledResult<BiOverviewData>
  trend: PromiseSettledResult<BiTrendData>
  anomalies: PromiseSettledResult<BiAnomalyData>
  now: number
  emptyBundle: OverviewLiveBundle
}

function rejectionMessage(prefix: string, reason: unknown): string {
  if (reason instanceof Error) {
    return `${prefix}: ${reason.message}`
  }
  return `${prefix}: ${String(reason)}`
}

export function reduceOverviewBundle({
  overview,
  trend,
  anomalies,
  now,
  emptyBundle,
}: OverviewReducerInput): OverviewReducerResult {
  const errors: string[] = []

  let trendPoints: ReadonlyArray<BiTrendPoint> = emptyBundle.trend
  if (trend.status === 'fulfilled') {
    trendPoints = trend.value.points
  } else {
    errors.push(rejectionMessage('trend', trend.reason))
  }

  let anomaliesAlerts: ReadonlyArray<BiAlertItem> = emptyBundle.alerts
  if (anomalies.status === 'fulfilled') {
    if (anomalies.value.items.length > 0) {
      anomaliesAlerts = anomalies.value.items
    }
  } else {
    errors.push(rejectionMessage('anomalies', anomalies.reason))
  }

  if (overview.status === 'fulfilled') {
    const overviewValue = overview.value
    const overviewAlerts = overviewValue.alerts
    const mergedAlerts =
      overviewAlerts.length > 0 ? overviewAlerts : anomaliesAlerts
    return {
      bundle: {
        cards: overviewValue.cards,
        alerts: mergedAlerts,
        trend: trendPoints,
        generatedAt: now,
        partial: errors.length > 0,
        errors,
      },
      source: errors.length > 0 ? 'error' : 'live',
    }
  }

  errors.unshift(rejectionMessage('overview', overview.reason))
  return {
    bundle: { ...emptyBundle, errors, partial: true },
    source: 'error',
  }
}
