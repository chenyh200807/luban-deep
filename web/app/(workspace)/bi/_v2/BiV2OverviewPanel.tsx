/* eslint-disable i18n/no-literal-ui-text */
'use client'

import {
  ArrowRight,
  CircleDollarSign,
  ClipboardCheck,
  Radar,
  RefreshCw,
  ShieldAlert,
  Users,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BiButton,
  BiSidePanel,
  BiStatusPill,
  BiNotice,
  BiV2DataSourceBanner,
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
import { OverviewCockpit } from '@/components/bi-cockpit/OverviewCockpit'
import { reduceOverviewBundle } from './overview-bundle-reducer'

type DataSource = 'mock' | 'live' | 'loading' | 'error'

type LiveBundle = {
  cards: ReadonlyArray<BiMetricCard>
  alerts: ReadonlyArray<BiAlertItem>
  trend: ReadonlyArray<BiTrendPoint>
  generatedAt: number
  partial: boolean
  errors: string[]
  overview?: BiOverviewData | null
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

const ALERT_LEVEL_TO_SEVERITY: Record<string, 'critical' | 'high' | 'medium' | 'low'> = {
  critical: 'critical',
  error: 'critical',
  warning: 'high',
  info: 'medium',
}

function metricText(card?: BiMetricCard) {
  if (!card) return '--'
  return typeof card.value === 'number' ? card.value.toLocaleString('zh-CN') : String(card.value)
}

function parsePercent(value?: string | number) {
  if (typeof value === 'number') return Math.max(0, Math.min(100, value))
  if (!value) return null
  const parsed = Number(value.replace('%', '').trim())
  return Number.isFinite(parsed) ? Math.max(0, Math.min(100, parsed)) : null
}

function findCard(cards: ReadonlyArray<BiMetricCard>, patterns: ReadonlyArray<string>) {
  return cards.find(card => patterns.some(pattern => card.label.includes(pattern)))
}

function sourceLabel(source: DataSource) {
  if (source === 'live') return '实时读模型'
  if (source === 'loading') return '正在同步'
  if (source === 'error') return '读模型异常'
  return '开发 mock'
}

type OverviewModule = {
  title: string
  kicker: string
  desc: string
  href: string
  icon: LucideIcon
  tone: string
  stats: [string, string]
}

function buildOverviewModules({
  activeCard,
  costCard,
  successCard,
  alertCount,
}: {
  activeCard?: BiMetricCard
  costCard?: BiMetricCard
  successCard?: BiMetricCard
  alertCount: number
}): OverviewModule[] {
  return [
    {
      title: '会员运营',
      kicker: '看人群和续费',
      desc: '从活跃、到期、风险和 360 证据进入跟进。',
      href: '/bi?tab=member-ops',
      icon: Users,
      tone: 'from-cyan-300/20 to-sky-500/10 border-cyan-300/20',
      stats: [metricText(activeCard), '活跃'],
    },
    {
      title: '商品账务',
      kicker: '看套餐和流水',
      desc: '把收入、余额、充值和账务异常放在同一条链路。',
      href: '/bi?tab=commerce',
      icon: CircleDollarSign,
      tone: 'from-amber-300/20 to-orange-500/10 border-amber-300/20',
      stats: [metricText(costCard), '成本'],
    },
    {
      title: '反馈中心',
      kicker: '看满意度和内测',
      desc: '负反馈、文字反馈和内测申请进入增长闭环。',
      href: '/bi?tab=feedback&panel=invite-test',
      icon: ClipboardCheck,
      tone: 'from-emerald-300/20 to-teal-500/10 border-emerald-300/20',
      stats: [metricText(successCard), '成功率'],
    },
    {
      title: '系统运维',
      kicker: '看可信和审计',
      desc: '数据可信、操作审计、权限审计和上线状态集中排查。',
      href: '/bi?tab=ops',
      icon: Radar,
      tone: 'from-indigo-300/20 to-blue-500/10 border-indigo-300/20',
      stats: [String(alertCount), '风险项'],
    },
  ]
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
    // Round 4 follow-up (B-P2-11): the three GETs are independent reads of
    // separate read-models; running them in parallel cuts the user-perceived
    // refresh latency from sum-of-three to max-of-three while keeping per-fetch
    // error isolation. Reducer logic lives in `overview-bundle-reducer.ts` for
    // unit-testability without an `.tsx` loader.
    const [overviewResult, trendResult, anomaliesResult] = await Promise.allSettled([
      getBiOverview({ days: 30 }),
      getBiActiveTrend({ days: 30 }),
      getBiAnomalies({ days: 30 }),
    ])
    if (ctrl.signal.aborted) return
    const { bundle: nextBundle, source: nextSource } = reduceOverviewBundle({
      overview: overviewResult,
      trend: trendResult,
      anomalies: anomaliesResult,
      now: Date.now(),
      emptyBundle: EMPTY_BUNDLE,
    })
    setBundle(nextBundle)
    setSource(nextSource)
  }, [flagEnabled])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-mount pattern; loadLive guards via AbortController
    void loadLive()
    return () => {
      inflightRef.current?.abort()
    }
  }, [loadLive])

  const activeCard = findCard(bundle.cards, ['活跃学习会话', '活跃学习者', '活跃'])
  const successCard = findCard(bundle.cards, ['成功率', '回合成功'])
  const costCard = findCard(bundle.cards, ['总成本', '成本'])
  const commandScore = parsePercent(successCard?.value) ?? (source === 'live' ? 82 : 0)
  const primaryAlert = bundle.alerts[0]
  const primaryMetric = bundle.cards[0]
  const modules = buildOverviewModules({
    activeCard,
    costCard,
    successCard,
    alertCount: bundle.alerts.length,
  })

  return (
    <section className="space-y-5">
      <OverviewCommandHero
        source={source}
        generatedAt={bundle.generatedAt}
        commandScore={commandScore}
        primaryMetric={primaryMetric}
        primaryAlert={primaryAlert}
        onReload={loadLive}
      />

      <DataSourceBanner
        source={source}
        bundle={bundle}
        flagEnabled={flagEnabled}
        onReload={loadLive}
      />

      <OverviewConclusionStack
        primaryMetric={primaryMetric}
        primaryAlert={primaryAlert}
        source={source}
      />

      <OverviewCockpit
        cards={bundle.cards}
        trend={bundle.trend}
        alerts={bundle.alerts}
        overview={bundle.overview ?? null}
        windowLabel={
          source === 'live'
            ? 'active-trend API'
            : source === 'loading'
              ? '加载中…'
              : source === 'error'
                ? 'API 不可用'
                : 'mock'
        }
        onMetric={card => {
          const meta = findMetricByLabel(card.label)
          setSelectedMetric({ card, meta, trend: inferTrend(card.delta, card.tone) })
        }}
        onAlert={alert => {
          const sev = ALERT_LEVEL_TO_SEVERITY[alert.level ?? 'info'] ?? 'low'
          setSelectedAlert({ alert, severity: sev, target: findMetricByLabel(alert.title) })
        }}
      />

      <OverviewModuleGrid modules={modules} />

      <MetricDetailPanel selection={selectedMetric} onClose={() => setSelectedMetric(null)} />
      <AlertDetailPanel selection={selectedAlert} onClose={() => setSelectedAlert(null)} />
    </section>
  )
}

function OverviewCommandHero({
  source,
  generatedAt,
  commandScore,
  primaryMetric,
  primaryAlert,
  onReload,
}: {
  source: DataSource
  generatedAt: number
  commandScore: number
  primaryMetric?: BiMetricCard
  primaryAlert?: BiAlertItem
  onReload: () => void
}) {
  const generatedLabel = generatedAt
    ? new Date(generatedAt).toLocaleString('zh-CN')
    : source === 'loading'
      ? '正在生成'
      : '暂无实时生成时间'
  return (
    <div className="relative overflow-hidden rounded-[2rem] border border-cyan-300/20 bg-[#152341] p-4 shadow-2xl shadow-black/25 sm:p-5">
      <div
        className="pointer-events-none absolute inset-0 opacity-90"
        style={{
          backgroundImage:
            'radial-gradient(circle at 86% 16%, rgba(94,221,234,0.22), transparent 28%), radial-gradient(circle at 12% 22%, rgba(251,146,60,0.14), transparent 24%), linear-gradient(145deg, rgba(31,41,89,0.94), rgba(15,23,42,0.86))',
        }}
        aria-hidden
      />
      <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1fr)_220px] lg:items-center">
        <div className="min-w-0">
          <div className="text-[11px] font-black uppercase tracking-normal text-amber-200">
            今日经营处方
          </div>
          <h2 className="mt-2 max-w-3xl text-2xl font-black leading-tight text-white sm:text-4xl">
            {primaryAlert?.title || primaryMetric?.label || '先看北极星，再处理高价值动作'}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
            {primaryAlert?.detail ||
              primaryMetric?.hint ||
              '把活跃、付费、留存、成本和风险压缩成今天可执行的经营判断。'}
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <span className="rounded-2xl border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-xs font-black text-cyan-100">
              {sourceLabel(source)}
            </span>
            <span className="rounded-2xl border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-xs font-black text-emerald-100">
              audit 写动作受控
            </span>
            <button
              type="button"
              onClick={onReload}
              className="inline-flex items-center gap-1 rounded-2xl border border-white/10 bg-white/[0.06] px-3 py-2 text-xs font-black text-slate-100 transition hover:bg-white/10"
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden /> 刷新处方
            </button>
          </div>
          <div className="mt-5 rounded-3xl border border-white/10 bg-slate-950/20 p-3 text-xs text-slate-300">
            <span className="font-bold text-cyan-100">generated_at</span>
            <span className="mx-2 text-slate-500">/</span>
            <span>{generatedLabel}</span>
          </div>
        </div>
        <div className="relative mx-auto flex h-48 w-48 items-center justify-center lg:mx-0">
          <div
            className="absolute inset-0 rounded-full shadow-[0_0_42px_rgba(94,221,234,0.2)]"
            style={{
              background: `conic-gradient(#5eddea 0 ${commandScore * 3.6}deg, rgba(255,255,255,0.12) ${commandScore * 3.6}deg 360deg)`,
            }}
            aria-hidden
          />
          <div className="absolute inset-7 rounded-full bg-[#152341] shadow-inner shadow-black/40" />
          <div className="relative text-center">
            <div className="text-4xl font-black tabular-nums text-cyan-100">{commandScore}%</div>
            <div className="mt-1 text-[11px] font-bold text-slate-400">经营健康度</div>
            <div className="mt-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-[11px] font-black text-amber-100">
              可追溯
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function OverviewConclusionStack({
  primaryMetric,
  primaryAlert,
  source,
}: {
  primaryMetric?: BiMetricCard
  primaryAlert?: BiAlertItem
  source: DataSource
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <div className="rounded-3xl border border-amber-300/20 bg-amber-300/10 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-black uppercase text-amber-100">先处理什么</div>
            <div className="mt-2 text-lg font-black text-white">
              {primaryAlert?.title || primaryMetric?.label || '等待经营读模型返回'}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              {primaryAlert?.detail ||
                primaryMetric?.hint ||
                '当前没有明确风险项，优先检查活跃、付费和成本三条主线。'}
            </p>
          </div>
          <span className="rounded-2xl border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-xs font-black text-amber-100">
            处方
          </span>
        </div>
      </div>
      <div className="rounded-3xl border border-cyan-300/20 bg-cyan-300/10 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] font-black uppercase text-cyan-100">为什么可信</div>
            <div className="mt-2 text-lg font-black text-white">
              {sourceLabel(source)} · 指标 registry · 可下钻
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              每张指标卡保留 metric_id、owner、authority 和可信等级；行动项进入详情后只展示
              canonical 读模型，不制造第二套业务事实。
            </p>
          </div>
          <span className="rounded-2xl border border-cyan-300/25 bg-cyan-300/10 px-3 py-1 text-xs font-black text-cyan-100">
            依据
          </span>
        </div>
      </div>
    </div>
  )
}

function OverviewModuleGrid({ modules }: { modules: ReadonlyArray<OverviewModule> }) {
  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[11px] font-black uppercase text-cyan-300">深入查看</div>
          <h2 className="mt-1 text-lg font-black text-white">像学情页一样按问题进入细节</h2>
        </div>
        <span className="hidden text-xs font-bold text-slate-400 sm:inline">模块是经营工具箱</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        {modules.map(module => {
          const Icon = module.icon
          return (
            <a
              key={module.title}
              href={module.href}
              className={`group min-h-[12rem] overflow-hidden rounded-3xl border bg-gradient-to-br p-4 shadow-xl shadow-black/15 transition hover:-translate-y-0.5 hover:shadow-black/25 ${module.tone}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-black text-slate-400">{module.kicker}</div>
                  <div className="mt-1 text-lg font-black text-white">{module.title}</div>
                </div>
                <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.06] text-cyan-100">
                  <Icon className="h-4 w-4" aria-hidden />
                </span>
              </div>
              <p className="mt-3 min-h-[3rem] text-sm leading-6 text-slate-300">{module.desc}</p>
              <div className="mt-4 flex items-center justify-between gap-2 border-t border-white/10 pt-3 text-xs">
                <span>
                  <span className="block text-xl font-black tabular-nums text-white">
                    {module.stats[0]}
                  </span>
                  <span className="text-slate-400">{module.stats[1]}</span>
                </span>
                <span className="inline-flex items-center gap-1 font-black text-cyan-100">
                  进入
                  <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
                </span>
              </div>
            </a>
          )
        })}
      </div>
    </div>
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
          <div className="rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <div className="text-xs text-slate-400">当前值</div>
            <div className="mt-1 text-3xl font-black text-slate-50">{String(card.value)}</div>
            <div className="mt-1 text-xs text-slate-300">
              {card.delta || '暂无环比'} · 趋势 {selection?.trend ?? 'flat'}
            </div>
            {card.hint ? <div className="mt-1 text-xs text-slate-400">{card.hint}</div> : null}
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
      subtitle={
        selection
          ? `${selection.severity.toUpperCase()} · ${selection.target.drilldown_hash}`
          : undefined
      }
      width="md"
    >
      {alert && selection ? (
        <div className="space-y-4 text-sm">
          <div className="rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <div className="flex items-center gap-2">
              <BiStatusPill
                tone={BI_SEVERITY_TONE[selection.severity]}
                label={selection.severity.toUpperCase()}
              />
              <span className="font-bold text-slate-100">{alert.title}</span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-300">
              {alert.detail || '该行动项暂无更多描述。'}
            </p>
          </div>
          <KV label="来源" value="overview.alerts + /api/v1/bi/anomalies" />
          <KV label="建议处理区" value={selection.target.drilldown_hash} />
          <KV label="关联指标" value={selection.target.metric_id} />
          <KV label="authority" value={selection.target.authority} />
          <BiNotice tone="amber">
            当前详情只展示 canonical 读模型内容；需要创建运营任务、导出、派单时，必须先接入带 audit
            的后端写 endpoint。
          </BiNotice>
        </div>
      ) : null}
    </BiSidePanel>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-3">
      <div className="text-[11px] font-bold uppercase text-slate-400">{label}</div>
      <div className="mt-1 break-words text-sm text-slate-100">{value || '—'}</div>
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
      <BiV2DataSourceBanner tone="amber">
        BI_OVERVIEW_V2_ENABLED 未开启 · 当前为 mock 数据。开启 flag 后 client 调用
        <code className="mx-1 font-mono">/api/v1/bi/overview</code> 与
        <code className="mx-1 font-mono">/api/v1/bi/active-trend</code>。
      </BiV2DataSourceBanner>
    )
  }
  if (source === 'loading') {
    return (
      <BiV2DataSourceBanner tone="sky" role="status">
        正在加载 overview / active-trend…
      </BiV2DataSourceBanner>
    )
  }
  if (source === 'live') {
    return (
      <BiV2DataSourceBanner
        tone="emerald"
        action={
          <BiButton onClick={onReload} variant="secondary" size="xs" aria-label="刷新 overview">
            <RefreshCw className="h-3 w-3" aria-hidden /> 刷新
          </BiButton>
        }
      >
        实时数据 · generated_at: {new Date(bundle.generatedAt).toLocaleString('zh-CN')}
      </BiV2DataSourceBanner>
    )
  }
  return (
    <BiV2DataSourceBanner
      tone="rose"
      role="alert"
      action={
        <BiButton onClick={onReload} variant="secondary" size="xs" aria-label="重试加载 overview">
          <RefreshCw className="h-3 w-3" aria-hidden /> 重试
        </BiButton>
      }
    >
      <div className="flex items-center gap-2">
        <ShieldAlert className="h-4 w-4" aria-hidden />
        <span>
          overview API 不可用，未展示 mock 数据。原因：{bundle.errors.join('; ') || '未知'}
        </span>
      </div>
    </BiV2DataSourceBanner>
  )
}
