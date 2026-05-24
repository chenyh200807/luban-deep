import test from 'node:test'
import assert from 'node:assert/strict'

import {
  reduceOverviewBundle,
  type OverviewLiveBundle,
} from '../app/(workspace)/bi/_v2/overview-bundle-reducer.ts'

const EMPTY: OverviewLiveBundle = {
  cards: [],
  alerts: [],
  trend: [],
  generatedAt: 0,
  partial: true,
  errors: [],
}

const NOW = 1_700_000_000_000

function ok<T>(value: T): PromiseSettledResult<T> {
  return { status: 'fulfilled', value }
}

function fail(reason: unknown): PromiseSettledResult<never> {
  return { status: 'rejected', reason } as PromiseSettledResult<never>
}

// Helpers to build minimal payload shapes the reducer cares about.
function mkOverview(
  overrides: Partial<{
    cards: ReadonlyArray<unknown>
    alerts: ReadonlyArray<unknown>
  }> = {}
): unknown {
  return {
    cards: overrides.cards ?? [{ label: 'sample', value: 1 }],
    alerts: overrides.alerts ?? [],
  }
}

function mkTrend(points: ReadonlyArray<unknown> = [{ day: 'd1', active: 10 }]): unknown {
  return { points }
}

function mkAnomalies(items: ReadonlyArray<unknown> = []): unknown {
  return { items }
}

test('all three fetches succeed -> live bundle with overview alerts when present', () => {
  const res = reduceOverviewBundle({
    overview: ok(
      mkOverview({
        cards: [{ label: 'a', value: 1 }],
        alerts: [{ level: 'critical', title: 'alert_overview' }],
      }) as never
    ),
    trend: ok(mkTrend([{ day: 'd1', active: 5 }]) as never),
    anomalies: ok(mkAnomalies([{ level: 'warning', title: 'anom_extra' }]) as never),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.source, 'live')
  assert.equal(res.bundle.partial, false)
  assert.deepEqual(res.bundle.errors, [])
  // overview alerts take precedence over anomalies items
  assert.deepEqual(
    res.bundle.alerts.map(a => a.title),
    ['alert_overview']
  )
  assert.equal(res.bundle.cards.length, 1)
  assert.equal(res.bundle.trend.length, 1)
  assert.equal(res.bundle.generatedAt, NOW)
})

test('overview alerts empty + anomalies has items -> alerts come from anomalies', () => {
  const res = reduceOverviewBundle({
    overview: ok(mkOverview({ alerts: [] }) as never),
    trend: ok(mkTrend() as never),
    anomalies: ok(
      mkAnomalies([
        { level: 'warning', title: 'anom_1' },
        { level: 'info', title: 'anom_2' },
      ]) as never
    ),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.source, 'live')
  assert.deepEqual(
    res.bundle.alerts.map(a => a.title),
    ['anom_1', 'anom_2']
  )
})

test('overview alerts empty + anomalies empty -> alerts is empty fallback', () => {
  const res = reduceOverviewBundle({
    overview: ok(mkOverview({ alerts: [] }) as never),
    trend: ok(mkTrend() as never),
    anomalies: ok(mkAnomalies([]) as never),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.source, 'live')
  assert.equal(res.bundle.alerts.length, 0)
})

test('trend fetch fails -> trend falls back to empty, error recorded, source=error', () => {
  const res = reduceOverviewBundle({
    overview: ok(mkOverview() as never),
    trend: fail(new Error('upstream 502')),
    anomalies: ok(mkAnomalies() as never),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.source, 'error')
  assert.equal(res.bundle.partial, true)
  assert.deepEqual(res.bundle.errors, ['trend: upstream 502'])
  assert.equal(res.bundle.trend.length, 0)
  // overview cards still rendered
  assert.equal(res.bundle.cards.length, 1)
})

test('anomalies fetch fails -> alerts fall back to overview alerts, error recorded', () => {
  const res = reduceOverviewBundle({
    overview: ok(
      mkOverview({
        alerts: [{ level: 'critical', title: 'alert_overview' }],
      }) as never
    ),
    trend: ok(mkTrend() as never),
    anomalies: fail(new Error('timeout')),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.source, 'error')
  assert.deepEqual(res.bundle.errors, ['anomalies: timeout'])
  assert.deepEqual(
    res.bundle.alerts.map(a => a.title),
    ['alert_overview']
  )
})

test('overview fetch fails -> bundle is empty fallback with overview error first', () => {
  const res = reduceOverviewBundle({
    overview: fail(new Error('admin gate')),
    trend: ok(mkTrend() as never),
    anomalies: ok(mkAnomalies() as never),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.source, 'error')
  assert.equal(res.bundle.partial, true)
  // overview error comes first in the list (matches old serial-await order)
  assert.equal(res.bundle.errors[0], 'overview: admin gate')
  assert.equal(res.bundle.cards.length, 0)
  assert.equal(res.bundle.trend.length, 0)
  assert.equal(res.bundle.alerts.length, 0)
})

test('all three fail -> errors ordered overview/trend/anomalies, empty bundle', () => {
  const res = reduceOverviewBundle({
    overview: fail(new Error('o-fail')),
    trend: fail(new Error('t-fail')),
    anomalies: fail(new Error('a-fail')),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.source, 'error')
  assert.deepEqual(res.bundle.errors, ['overview: o-fail', 'trend: t-fail', 'anomalies: a-fail'])
  assert.equal(res.bundle.cards.length, 0)
})

test('non-Error rejection reason is stringified safely', () => {
  const res = reduceOverviewBundle({
    overview: ok(mkOverview() as never),
    trend: fail('plain-string-error'),
    anomalies: ok(mkAnomalies() as never),
    now: NOW,
    emptyBundle: EMPTY,
  })
  assert.equal(res.bundle.errors[0], 'trend: plain-string-error')
})
