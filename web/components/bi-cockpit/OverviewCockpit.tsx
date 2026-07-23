/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 总览情报驾驶舱（方向 A「指挥舱进化」完整形态）。
 *
 * 信息架构对齐设计板 docs/bi-cockpit-preview/2026-06-12-bi-vnext-design-board.html
 * 的方向 A section：
 *   hero/控制条 → KPI 徽标卡行 → 主图表区（成本日趋势大图 + 会话入口环形）
 *   → 双轴趋势 → 增长与质量 → 告警行动队列。
 *
 * 数据来自 overview LiveBundle（cards / trend / alerts / overview），
 * 只做真实字段 -> 图表映射；指标卡点击和告警点击通过回调复用面板已有的
 * MetricDetailPanel / AlertDetailPanel 抽屉（不重复造下钻）。
 * 设计板的「成本三源对账趋势」线上无 Langfuse 序列，按诚实替代原则
 * 渲染 UsageLedger 单源日成本 + 静态对账事实说明（来自已发布对账报告）。
 */
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CircleDollarSign,
  PieChart,
  TrendingUp,
} from 'lucide-react'
import type { ReactNode } from 'react'
import type { BiAlertItem, BiMetricCard, BiOverviewData, BiTrendPoint } from '@/lib/bi-api'
import { CockpitDonut, type Datum } from './Charts'
import { EChart } from './EChart'
import { GlobalControlBar, type CockpitWindowDays } from './GlobalControlBar'
import { GrowthQualitySection } from './GrowthQualitySection'
import { KpiTrustCard } from './KpiTrustCard'
import { CockpitBg, CockpitPanel, SectionLabel } from './Layout'
import { MeasuredEstimatedBar, TrustPill } from './TrustBadge'
import {
  COCKPIT,
  COCKPIT_FONT,
  COCKPIT_TOOLTIP,
  SEMANTIC,
  SERIES_COLORS,
  alpha,
  vGradient,
} from './theme'

const fmtNum = (n: number) => new Intl.NumberFormat('en-US').format(Math.round(n))

const AXIS_LABEL = { color: COCKPIT.textFaint, fontSize: 10, fontFamily: COCKPIT_FONT }

export function OverviewCockpit({
  cards,
  trend,
  alerts,
  overview,
  windowLabel,
  days,
  onDaysChange,
  daysBusy,
  onMetric,
  onAlert,
}: {
  cards: ReadonlyArray<BiMetricCard>
  trend: ReadonlyArray<BiTrendPoint>
  alerts: ReadonlyArray<BiAlertItem>
  overview?: BiOverviewData | null
  windowLabel?: string
  /** 时间范围受控状态（由数据获取 owner 持有），两者都传时渲染全局控制条 */
  days?: CockpitWindowDays
  onDaysChange?: (days: CockpitWindowDays) => void
  daysBusy?: boolean
  onMetric?: (card: BiMetricCard) => void
  onAlert?: (alert: BiAlertItem) => void
}) {
  const kpis = cards.slice(0, 8)
  const costCard =
    cards.find(c => c.metricId === 'total_cost_usd') ?? cards.find(c => c.label.includes('成本'))
  // 成本日趋势单源 = UsageLedger 逐日（daily_cost.series）；active-trend 不承载成本。
  const costSeries = (overview?.dailyCostSeries ?? [])
    .filter((p): p is typeof p & { costUsd: number } => p.costUsd !== null)
    .map(p => ({
      label: p.label,
      cost: p.costUsd,
    }))
  const hasCostSeries = costSeries.length > 0
  const hasTrend = trend.length > 0
  const entrypoints: Datum[] = (overview?.entrypoints ?? []).map(item => ({
    name: item.label,
    value: Number(item.value) || 0,
  }))
  const entryTotal = entrypoints.reduce((s, d) => s + d.value, 0)

  return (
    <CockpitBg className="p-4 md:p-6">
      {/* ---------------------------------------------------------- hero 区 */}
      <div
        className="flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.22em]"
        style={{ color: alpha(SERIES_COLORS[0], 0.9) }}
      >
        <Activity className="h-3.5 w-3.5" aria-hidden />◢ Operations Overview Cockpit
      </div>
      <div className="mb-3 mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[24px] font-black leading-tight" style={{ color: COCKPIT.text }}>
          总览指挥舱
        </h2>
        {windowLabel ? (
          <span className="text-[12px]" style={{ color: COCKPIT.textMuted }}>
            {windowLabel}
          </span>
        ) : null}
        <span className="ml-auto hidden text-[11px] sm:inline" style={{ color: COCKPIT.textFaint }}>
          每个数字自带身份证 · trust 徽标 hover 可看口径
        </span>
      </div>

      {days != null && onDaysChange ? (
        <GlobalControlBar days={days} onDaysChange={onDaysChange} busy={daysBusy} />
      ) : null}

      {/* -------------------------------------------------- KPI 徽标卡行 */}
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {kpis.map((card, i) => (
          <KpiTrustCard
            key={`${card.metricId ?? card.label}-${i}`}
            card={card}
            onClick={onMetric ? () => onMetric(card) : undefined}
          />
        ))}
        {kpis.length === 0 ? <Empty /> : null}
      </div>

      {/* ------------------------------------------------------ 主图表区 */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.5fr_1fr]">
        <CockpitPanel
          glow
          title="成本日趋势（UsageLedger 单源）"
          hint="对账残差 vs Langfuse 16% · P3 持续核对 · measured/estimated 分量见下方微条"
          icon={<CircleDollarSign className="h-4 w-4" />}
          action={costCard?.metricId ? <TrustPill metricId={costCard.metricId} /> : undefined}
        >
          {hasCostSeries ? (
            <EChart option={buildCostOption(costSeries)} height={272} />
          ) : (
            <Empty height={272} />
          )}
          {costCard &&
          typeof costCard.measuredValue === 'number' &&
          typeof costCard.estimatedValue === 'number' ? (
            <div className="mt-2 px-1">
              <MeasuredEstimatedBar
                measured={costCard.measuredValue}
                estimated={costCard.estimatedValue}
                provenance={costCard.provenance}
              />
            </div>
          ) : null}
        </CockpitPanel>

        <CockpitPanel
          title="会话入口构成"
          hint="overview.entrypoints · 环中心 = 窗口入口会话合计"
          icon={<PieChart className="h-4 w-4" />}
        >
          {entrypoints.length ? (
            <CockpitDonut
              data={entrypoints}
              centerLabel="入口会话"
              centerValue={fmtNum(entryTotal)}
              centerSize={28}
              height={240}
            />
          ) : (
            <Empty height={240} />
          )}
        </CockpitPanel>
      </div>

      {/* ---------------------------------------------------- 双轴趋势 */}
      <div className="mt-4">
        <CockpitPanel
          title="活跃 × 学习成功 双轴趋势"
          hint="active-trend API · 按窗口 · 环比虚影待 P3 接入后叠加上一周期"
          icon={<TrendingUp className="h-4 w-4" />}
        >
          {hasTrend ? <EChart option={buildDualAxisOption(trend)} height={236} /> : <Empty />}
        </CockpitPanel>
      </div>

      {/* ------------------------------------------------ 增长与质量区 */}
      {overview ? (
        <div className="mt-5">
          <GrowthQualitySection overview={overview} />
        </div>
      ) : null}

      {/* ---------------------------------------------- 告警行动队列 */}
      <div className="mt-5">
        <SectionLabel icon={<AlertTriangle className="h-4 w-4" />}>今日行动队列</SectionLabel>
        <CockpitPanel hint="overview.alerts + anomalies · 点击进入行动项详情">
          <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {alerts.slice(0, 8).map((alert, idx) => (
              <li key={idx}>
                <button
                  type="button"
                  onClick={onAlert ? () => onAlert(alert) : undefined}
                  className="group flex w-full items-start gap-2.5 rounded-xl border border-white/10 bg-white/[0.03] p-2.5 text-left transition hover:border-[#E8915A]/30 hover:bg-[#E8915A]/[0.06]"
                >
                  <span
                    className="mt-0.5 h-2 w-2 shrink-0 rounded-full"
                    style={{
                      background: LEVEL_COLOR[alert.level] ?? SEMANTIC.neutral,
                      boxShadow: `0 0 8px ${alpha(LEVEL_COLOR[alert.level] ?? SEMANTIC.neutral, 0.6)}`,
                    }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-bold text-slate-100">
                      {alert.title}
                    </span>
                    {alert.detail ? (
                      <span className="mt-0.5 block truncate text-[11px] text-slate-400">
                        {alert.detail}
                      </span>
                    ) : null}
                  </span>
                  <ArrowRight className="mt-1 h-3 w-3 shrink-0 text-slate-500 transition group-hover:translate-x-0.5" />
                </button>
              </li>
            ))}
            {alerts.length === 0 ? (
              <li className="grid place-items-center rounded-xl border border-dashed border-white/10 px-2 py-8 text-[11px] text-slate-500 md:col-span-2">
                暂无风险项
              </li>
            ) : null}
          </ul>
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

/* ------------------------------------------------ 成本日趋势（单源诚实版） */
function buildCostOption(trend: ReadonlyArray<{ label: string; cost: number }>) {
  return {
    tooltip: {
      ...COCKPIT_TOOLTIP,
      trigger: 'axis' as const,
      valueFormatter: (v: unknown) => `$${Number(v).toFixed(4)}`,
    },
    grid: { left: 8, right: 12, top: 30, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category' as const,
      boundaryGap: false,
      data: trend.map(p => p.label),
      axisLine: { lineStyle: { color: alpha(SERIES_COLORS[0], 0.3) } },
      axisTick: { show: false },
      axisLabel: AXIS_LABEL,
    },
    yAxis: {
      type: 'value' as const,
      name: 'USD/日',
      nameTextStyle: { color: COCKPIT.textFaint, fontSize: 10 },
      splitLine: { lineStyle: { color: COCKPIT.grid } },
      axisLabel: AXIS_LABEL,
    },
    series: [
      {
        name: '日成本（UsageLedger）',
        type: 'line' as const,
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: trend.map(p => p.cost),
        lineStyle: {
          width: 2.5,
          color: SERIES_COLORS[1],
          shadowBlur: 12,
          shadowColor: alpha(SERIES_COLORS[1], 0.5),
        },
        itemStyle: { color: SERIES_COLORS[1], borderColor: COCKPIT.bgDeep, borderWidth: 2 },
        areaStyle: {
          color: vGradient(alpha(SERIES_COLORS[1], 0.28), alpha(SERIES_COLORS[1], 0.02)),
        },
      },
    ],
  }
}

/* ------------------------------------------- 活跃 × 学习成功 双轴趋势 */
function buildDualAxisOption(trend: ReadonlyArray<BiTrendPoint>) {
  return {
    tooltip: { ...COCKPIT_TOOLTIP, trigger: 'axis' as const },
    legend: {
      top: 0,
      textStyle: { color: COCKPIT.textMuted, fontSize: 11, fontFamily: COCKPIT_FONT },
      itemWidth: 12,
      itemHeight: 8,
    },
    grid: { left: 8, right: 8, top: 32, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category' as const,
      data: trend.map(p => p.label),
      axisLine: { lineStyle: { color: alpha(SERIES_COLORS[0], 0.3) } },
      axisTick: { show: false },
      axisLabel: AXIS_LABEL,
    },
    yAxis: [
      {
        type: 'value' as const,
        name: '活跃',
        nameTextStyle: { color: COCKPIT.textFaint, fontSize: 10 },
        splitLine: { lineStyle: { color: COCKPIT.grid } },
        axisLabel: AXIS_LABEL,
      },
      {
        type: 'value' as const,
        name: '学习成功',
        nameTextStyle: { color: COCKPIT.textFaint, fontSize: 10 },
        splitLine: { show: false },
        axisLabel: AXIS_LABEL,
      },
    ],
    series: [
      {
        name: '活跃',
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        data: trend.map(p => p.active),
        lineStyle: {
          width: 2.5,
          color: SERIES_COLORS[0],
          shadowBlur: 12,
          shadowColor: alpha(SERIES_COLORS[0], 0.5),
        },
        itemStyle: { color: SERIES_COLORS[0] },
        areaStyle: {
          color: vGradient(alpha(SERIES_COLORS[0], 0.25), alpha(SERIES_COLORS[0], 0.02)),
        },
      },
      {
        name: '学习成功',
        type: 'bar' as const,
        yAxisIndex: 1,
        barWidth: 10,
        data: trend.map(p => p.successful),
        itemStyle: {
          color: vGradient(alpha(SEMANTIC.positive, 0.8), alpha(SEMANTIC.positive, 0.25)),
          borderRadius: [3, 3, 0, 0] as [number, number, number, number],
        },
      },
    ],
  }
}

const LEVEL_COLOR: Record<string, string> = {
  info: SEMANTIC.info,
  warning: SEMANTIC.warning,
  critical: SEMANTIC.danger,
}

function Empty({ height = 200 }: { height?: number }): ReactNode {
  return (
    <div
      className="grid place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500"
      style={{ height }}
    >
      暂无数据
    </div>
  )
}
