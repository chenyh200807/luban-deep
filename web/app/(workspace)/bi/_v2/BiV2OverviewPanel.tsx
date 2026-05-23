/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { ArrowDownRight, ArrowUpRight, Minus, RefreshCw, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BiSidePanel,
  BiStatusPill,
  BiMoneyCell,
  BI_TRUST_TONE,
  BI_SEVERITY_TONE,
} from '@/components/bi-v2'
import {
  getBiAnomalies,
  getBiActiveTrend,
  getBiOverview,
  type BiTrendPoint,
  type BiAlertItem,
  type BiMetricCard,
  type BiOverviewData,
} from '@/lib/bi-api'
import { findMetricByLabel, type BiV2MetricDef } from '@/lib/bi-v2-metric-registry.generated'

type DataSource = 'mock' | 'live' | 'loading' | 'error'

type LiveBundle = {
  cards: ReadonlyArray<BiMetricCard>
  alerts: ReadonlyArray<BiAlertItem>
  trend: ReadonlyArray<BiTrendPoint>
  generatedAt: number
  partial: boolean
  errors: string[]
}

type MetricSelection = {
  card: BiMetricCard
  meta: BiV2MetricDef
  trend: 'up' | 'down' | 'flat'
}

type AlertSelection = {
  alert: BiAlertItem
  severity: 'critical' | 'high' | 'medium' | 'low'
  target: BiV2MetricDef
}

// Round 4 S4 (M-B): mock fallback dev-only. Production build dead-code-
// eliminates the literal below and substitutes an empty bundle; the panel
// then renders a "loading / unavailable" state instead of fake KPIs.
const EMPTY_BUNDLE: LiveBundle = {
  cards: [],
  alerts: [],
  trend: [],
  generatedAt: 0,
  partial: true,
  errors: [],
}
const MOCK_BUNDLE: LiveBundle =
  process.env.NODE_ENV === 'production'
    ? EMPTY_BUNDLE
    : {
        cards: [
          {
            label: '活跃学习会话',
            value: 5821,
            hint: '近 30 天窗口',
            delta: '+6.4% WoW',
            tone: 'good',
          },
          { label: '活跃学习者', value: 1284, hint: '去重活跃', delta: '+4.1% WoW', tone: 'good' },
          {
            label: '回合成功率',
            value: '73.4%',
            hint: '总回合 18,200',
            delta: '+1.2pp WoW',
            tone: 'good',
          },
          {
            label: '总成本',
            value: 612.4,
            hint: 'USD（估算）',
            delta: '+12.8% DoD',
            tone: 'warning',
          },
        ],
        alerts: [
          {
            level: 'critical',
            title: '钱包出现负余额会员 3 位',
            detail: 'WALLET_NEGATIVE_BALANCE / wallet team',
          },
          {
            level: 'warning',
            title: '7 笔充值缺少订单上下文（近 7d）',
            detail: 'WALLET_CREDIT_WITHOUT_ORDER / finance ops',
          },
          {
            level: 'warning',
            title: 'AI 反馈 negative 24h 增加 22%',
            detail: 'FeedbackService.list / quality',
          },
          {
            level: 'info',
            title: '12 位 VIP 会员明日到期',
            detail: 'MemberConsoleService risk_score / growth',
          },
          {
            level: 'info',
            title: '成本估算 24h 上升 12.8%',
            detail: 'observability.cost_estimator C 级 / platform',
          },
        ],
        trend: Array.from({ length: 24 }, (_, i) => ({
          label: `Day ${i + 1}`,
          active: 800 + Math.round(120 * Math.sin(i / 2)),
          cost: 30 + Math.round(10 * Math.cos(i / 3)),
          successful: 500 + Math.round(80 * Math.sin(i / 1.5)),
        })),
        generatedAt: 0,
        partial: true,
        errors: [],
      }

type DeltaTone = NonNullable<BiMetricCard['tone']>
const DELTA_DIRECTION: Record<DeltaTone, 'up' | 'down' | 'flat'> = {
  good: 'up',
  warning: 'flat',
  critical: 'down',
  neutral: 'flat',
}

function inferTrend(
  delta: string | undefined,
  tone: DeltaTone | undefined
): 'up' | 'down' | 'flat' {
  if (delta?.trim().startsWith('-')) return 'down'
  if (delta?.trim().startsWith('+')) return 'up'
  return tone ? DELTA_DIRECTION[tone] : 'flat'
}

function TrendIcon({ trend }: { trend: 'up' | 'down' | 'flat' }) {
  if (trend === 'up') return <ArrowUpRight className="h-4 w-4 text-emerald-600" aria-hidden />
  if (trend === 'down') return <ArrowDownRight className="h-4 w-4 text-rose-600" aria-hidden />
  return <Minus className="h-4 w-4 text-slate-500" aria-hidden />
}

const ALERT_LEVEL_TO_SEVERITY: Record<string, 'critical' | 'high' | 'medium' | 'low'> = {
  critical: 'critical',
  error: 'critical',
  warning: 'high',
  info: 'medium',
}

function renderCardValue(card: BiMetricCard, meta: BiV2MetricDef) {
  if (typeof card.value === 'number' && meta.group === 'unit_economics') {
    return <BiMoneyCell amount={card.value} currency="CNY" trust={meta.trust} align="left" />
  }
  return <span className="tabular-nums text-slate-900">{String(card.value)}</span>
}

export function BiV2OverviewPanel({ flagEnabled }: { flagEnabled: boolean }) {
  const [bundle, setBundle] = useState<LiveBundle>(MOCK_BUNDLE)
  const [source, setSource] = useState<DataSource>(flagEnabled ? 'loading' : 'mock')
  const [selectedMetric, setSelectedMetric] = useState<MetricSelection | null>(null)
  const [selectedAlert, setSelectedAlert] = useState<AlertSelection | null>(null)
  const inflightRef = useRef<AbortController | null>(null)

  const loadLive = useCallback(async () => {
    if (!flagEnabled) {
      setBundle(MOCK_BUNDLE)
      setSource('mock')
      return
    }
    inflightRef.current?.abort()
    const ctrl = new AbortController()
    inflightRef.current = ctrl
    setSource('loading')
    const errors: string[] = []
    let overview: BiOverviewData | null = null
    let trend: ReadonlyArray<BiTrendPoint> = MOCK_BUNDLE.trend
    let alerts: ReadonlyArray<BiAlertItem> = MOCK_BUNDLE.alerts
    try {
      overview = await getBiOverview({ days: 30 })
    } catch (err) {
      errors.push(`overview: ${(err as Error).message}`)
    }
    try {
      const t = await getBiActiveTrend({ days: 30 })
      trend = t.points
    } catch (err) {
      errors.push(`trend: ${(err as Error).message}`)
    }
    try {
      const a = await getBiAnomalies({ days: 30 })
      if (a.items.length > 0) alerts = a.items
    } catch (err) {
      errors.push(`anomalies: ${(err as Error).message}`)
    }
    if (ctrl.signal.aborted) return
    if (overview) {
      setBundle({
        cards: overview.cards,
        alerts: overview.alerts.length > 0 ? overview.alerts : alerts,
        trend,
        generatedAt: Date.now(),
        partial: errors.length > 0,
        errors,
      })
      setSource(errors.length > 0 ? 'error' : 'live')
    } else {
      setBundle({ ...MOCK_BUNDLE, errors, partial: true })
      setSource('error')
    }
  }, [flagEnabled])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount pattern; loadLive guards via AbortController
    void loadLive()
    return () => {
      inflightRef.current?.abort()
    }
  }, [loadLive])

  const trendMax = Math.max(...bundle.trend.map(p => p.active), 1)

  return (
    <section className="space-y-5">
      <DataSourceBanner
        source={source}
        bundle={bundle}
        flagEnabled={flagEnabled}
        onReload={loadLive}
      />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {bundle.cards.slice(0, 8).map((card, idx) => {
          const meta = findMetricByLabel(card.label)
          const trend = inferTrend(card.delta, card.tone)
          return (
            <article
              key={`${meta.metric_id}-${idx}`}
              className="flex flex-col gap-2 rounded-md border border-slate-200 bg-white p-4 shadow-sm"
              title={[
                `${meta.metric_id}`,
                `口径：${meta.definition}`,
                `authority: ${meta.authority}`,
                `owner: ${meta.owner}`,
                `可信等级: ${meta.trust}`,
                `更新频率: ${meta.refresh_cadence}`,
                meta.degraded_note ? `降级说明: ${meta.degraded_note}` : `降级说明: 无已知降级路径`,
              ].join(' · ')}
              aria-label={`${card.label} 当前 ${card.value}，数据可信 ${meta.trust} 级，owner ${meta.owner}`}
            >
              <div className="flex items-center justify-between text-xs text-slate-500">
                <span className="font-medium text-slate-700">{card.label}</span>
                <BiStatusPill tone={BI_TRUST_TONE[meta.trust]} label={`${meta.trust} 级`} />
              </div>
              <div className="flex items-baseline justify-between gap-2 text-2xl font-semibold">
                {renderCardValue(card, meta)}
                {card.delta ? (
                  <span className="flex items-center gap-1 text-xs tabular-nums text-slate-600">
                    <TrendIcon trend={trend} />
                    {card.delta}
                  </span>
                ) : null}
              </div>
              <div className="text-[11px] leading-snug text-slate-500">
                <div className="truncate">authority: {meta.authority}</div>
                <div className="truncate">
                  owner: {meta.owner} · metric_id:{' '}
                  <code className="font-mono text-[10px]">{meta.metric_id}</code>
                </div>
              </div>
              {meta.metric_id === 'unknown' ? (
                <div className="rounded bg-amber-50 px-2 py-1 text-[10px] text-amber-700">
                  指标未注册 · 请补充到 BI_V2_METRICS 或 deeptutor/services/bi_metrics.py
                </div>
              ) : null}
              <button
                type="button"
                onClick={() => setSelectedMetric({ card, meta, trend })}
                className="mt-auto inline-flex w-fit items-center rounded border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-300"
                aria-label={`打开 ${card.label} 指标详情`}
              >
                查看详情
              </button>
            </article>
          )
        })}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-md border border-slate-200 bg-white p-4 lg:col-span-2">
          <header className="flex items-center justify-between text-sm">
            <span className="font-medium text-slate-800">活跃 / 成本 / 学习成功趋势</span>
            <span className="text-[11px] text-slate-500">
              {source === 'live' ? 'active-trend API' : source === 'loading' ? '加载中…' : 'mock'}
            </span>
          </header>
          <div className="mt-4 grid h-44 grid-cols-12 items-end gap-1" aria-label="近窗口活跃趋势">
            {bundle.trend.slice(0, 24).map((point, idx) => {
              const h = Math.max(10, Math.round((point.active / trendMax) * 100))
              return (
                <div
                  key={`${point.label}-${idx}`}
                  className="rounded-sm bg-gradient-to-t from-slate-200 to-slate-400"
                  style={{ height: `${h}%` }}
                  aria-hidden
                  title={`${point.label} · active=${point.active} cost=${point.cost} success=${point.successful}`}
                />
              )
            })}
          </div>
          <p className="mt-2 text-[10px] text-slate-500">
            authority: bi_service.get_active_trend · 收入接入由 P1 处理
          </p>
        </div>

        <aside className="rounded-md border border-slate-200 bg-white p-4">
          <header className="border-b border-slate-200 pb-2">
            <h2 className="text-sm font-semibold text-slate-900">今日行动队列</h2>
            <p className="mt-1 text-[11px] text-slate-500">
              {source === 'live'
                ? '来自 overview.alerts + anomalies'
                : 'mock · 真实风险接 alerts/anomalies'}
            </p>
          </header>
          <ul className="mt-3 space-y-1">
            {bundle.alerts.slice(0, 6).map((alert, idx) => {
              const sev = ALERT_LEVEL_TO_SEVERITY[alert.level ?? 'info'] ?? 'low'
              const linkMeta = findMetricByLabel(alert.title)
              return (
                <li key={idx}>
                  <button
                    type="button"
                    onClick={() => setSelectedAlert({ alert, severity: sev, target: linkMeta })}
                    className="flex items-start justify-between gap-3 rounded border border-transparent px-2 py-2 hover:border-slate-200 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-300"
                    aria-label={`查看 ${alert.title}`}
                  >
                    <div className="flex flex-1 items-start gap-2">
                      <BiStatusPill tone={BI_SEVERITY_TONE[sev]} label={sev.toUpperCase()} />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium text-slate-800">
                          {alert.title}
                        </div>
                        {alert.detail ? (
                          <div className="truncate text-[11px] text-slate-500">{alert.detail}</div>
                        ) : null}
                      </div>
                    </div>
                    <span className="text-[11px] text-slate-500">→ {linkMeta.drilldown_hash}</span>
                  </button>
                </li>
              )
            })}
            {bundle.alerts.length === 0 ? (
              <li className="rounded border border-dashed border-slate-200 px-2 py-3 text-center text-xs text-slate-500">
                暂无风险项
              </li>
            ) : null}
          </ul>
        </aside>
      </div>
      <MetricDetailPanel
        selection={selectedMetric}
        onClose={() => setSelectedMetric(null)}
      />
      <AlertDetailPanel
        selection={selectedAlert}
        onClose={() => setSelectedAlert(null)}
      />
    </section>
  )
}

function MetricDetailPanel({
  selection,
  onClose,
}: {
  selection: MetricSelection | null
  onClose: () => void
}) {
  const card = selection?.card
  const meta = selection?.meta
  return (
    <BiSidePanel
      open={Boolean(selection)}
      onClose={onClose}
      title={card ? `指标详情 · ${card.label}` : '指标详情'}
      subtitle={meta ? `${meta.metric_id} · ${meta.trust} 级可信` : undefined}
      width="md"
    >
      {card && meta ? (
        <div className="space-y-4 text-sm">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="text-xs text-slate-500">当前值</div>
            <div className="mt-1 text-2xl font-semibold text-slate-900">{String(card.value)}</div>
            <div className="mt-1 text-xs text-slate-600">
              {card.delta || '暂无环比'} · 趋势 {selection?.trend ?? 'flat'}
            </div>
            {card.hint ? <div className="mt-1 text-xs text-slate-500">{card.hint}</div> : null}
          </div>
          <KV label="指标口径" value={meta.definition} />
          <KV label="唯一 authority" value={meta.authority} />
          <KV label="owner" value={meta.owner} />
          <KV label="更新频率" value={meta.refresh_cadence} />
          <KV label="可信等级" value={`${meta.trust} 级`} />
          <KV label="推荐下钻区" value={meta.drilldown_hash} />
          <KV label="降级说明" value={meta.degraded_note || '无已知降级路径'} />
        </div>
      ) : null}
    </BiSidePanel>
  )
}

function AlertDetailPanel({
  selection,
  onClose,
}: {
  selection: AlertSelection | null
  onClose: () => void
}) {
  const alert = selection?.alert
  return (
    <BiSidePanel
      open={Boolean(selection)}
      onClose={onClose}
      title={alert ? `行动项详情 · ${alert.title}` : '行动项详情'}
      subtitle={selection ? `${selection.severity.toUpperCase()} · ${selection.target.drilldown_hash}` : undefined}
      width="md"
    >
      {alert && selection ? (
        <div className="space-y-4 text-sm">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center gap-2">
              <BiStatusPill
                tone={BI_SEVERITY_TONE[selection.severity]}
                label={selection.severity.toUpperCase()}
              />
              <span className="font-medium text-slate-900">{alert.title}</span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-600">
              {alert.detail || '该行动项暂无更多描述。'}
            </p>
          </div>
          <KV label="来源" value="overview.alerts + /api/v1/bi/anomalies" />
          <KV label="建议处理区" value={selection.target.drilldown_hash} />
          <KV label="关联指标" value={selection.target.metric_id} />
          <KV label="authority" value={selection.target.authority} />
          <p className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-800">
            当前详情只展示 canonical 读模型内容；需要创建运营任务、导出、派单时，必须先接入带
            audit 的后端写 endpoint。
          </p>
        </div>
      ) : null}
    </BiSidePanel>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="text-[11px] font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 break-words text-sm text-slate-800">{value || '—'}</div>
    </div>
  )
}

function DataSourceBanner({
  source,
  bundle,
  flagEnabled,
  onReload,
}: {
  source: DataSource
  bundle: LiveBundle
  flagEnabled: boolean
  onReload: () => void
}) {
  if (!flagEnabled) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        BI_OVERVIEW_V2_ENABLED 未开启 · 当前为 mock 数据。开启 flag 后 client 调用
        <code className="mx-1 font-mono">/api/v1/bi/overview</code> 与
        <code className="mx-1 font-mono">/api/v1/bi/active-trend</code>。
      </div>
    )
  }
  if (source === 'loading') {
    return (
      <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
        正在加载 overview / active-trend…
      </div>
    )
  }
  if (source === 'live') {
    return (
      <div className="flex items-center justify-between rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
        <span>实时数据 · generated_at: {new Date(bundle.generatedAt).toLocaleString('zh-CN')}</span>
        <button
          type="button"
          onClick={onReload}
          className="inline-flex items-center gap-1 text-emerald-900 hover:underline"
          aria-label="刷新 overview"
        >
          <RefreshCw className="h-3 w-3" aria-hidden /> 刷新
        </button>
      </div>
    )
  }
  return (
    <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4" aria-hidden />
        <span>
          overview API 不可用，已回退到 mock 数据。原因：{bundle.errors.join('; ') || '未知'}
        </span>
        <button
          type="button"
          onClick={onReload}
          className="ml-auto inline-flex items-center gap-1 text-rose-900 hover:underline"
          aria-label="重试加载 overview"
        >
          <RefreshCw className="h-3 w-3" aria-hidden /> 重试
        </button>
      </div>
    </div>
  )
}
