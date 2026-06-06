/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 总览情报驾驶舱。数据来自 overview LiveBundle（cards / trend / alerts），
 * 只做真实字段 -> 图表映射；指标卡点击和告警点击通过回调复用面板已有的
 * MetricDetailPanel / AlertDetailPanel 抽屉（不重复造下钻）。
 */
import { Activity, AlertTriangle, ArrowRight, TrendingUp } from 'lucide-react'
import type { ReactNode } from 'react'
import type { BiAlertItem, BiMetricCard, BiTrendPoint } from '@/lib/bi-api'
import { EChart } from './EChart'
import { CockpitBg, CockpitKpi, CockpitPanel, SectionLabel } from './Layout'
import { COCKPIT, COCKPIT_FONT, COCKPIT_TOOLTIP, SEMANTIC, alpha, vGradient } from './theme'

const TONE_BY_CARD: Record<string, string> = { good: 'emerald', warning: 'amber', critical: 'rose', neutral: 'cyan' }
const TONE_CYCLE = ['cyan', 'teal', 'violet', 'amber', 'emerald', 'rose']
const fmtNum = (n: number) => new Intl.NumberFormat('en-US').format(Math.round(n))

function deltaUp(delta?: string, tone?: string): boolean {
  if (delta && /^[+↑]|增|升/.test(delta.trim())) return true
  if (delta && /^[-↓]|降|跌/.test(delta.trim())) return false
  return tone === 'good'
}

export function OverviewCockpit({
  cards,
  trend,
  alerts,
  windowLabel,
  onMetric,
  onAlert,
}: {
  cards: ReadonlyArray<BiMetricCard>
  trend: ReadonlyArray<BiTrendPoint>
  alerts: ReadonlyArray<BiAlertItem>
  windowLabel?: string
  onMetric?: (card: BiMetricCard) => void
  onAlert?: (alert: BiAlertItem) => void
}) {
  const kpis = cards.slice(0, 8)
  const labels = trend.map(p => p.label)
  const hasTrend = trend.length > 0

  const trendOption = {
    color: [SEMANTIC.info, SEMANTIC.positive, SEMANTIC.warning],
    tooltip: { ...COCKPIT_TOOLTIP, trigger: 'axis' as const },
    legend: {
      data: ['活跃', '学习成功', '成本($)'],
      textStyle: { color: COCKPIT.textMuted, fontSize: 11, fontFamily: COCKPIT_FONT },
      top: 0,
      itemWidth: 12,
      itemHeight: 8,
    },
    grid: { left: 8, right: 8, top: 34, bottom: 4, containLabel: true },
    xAxis: {
      type: 'category' as const,
      boundaryGap: false,
      data: labels,
      axisLine: { lineStyle: { color: COCKPIT.grid } },
      axisTick: { show: false },
      axisLabel: { color: COCKPIT.textFaint, fontSize: 10, fontFamily: COCKPIT_FONT },
    },
    yAxis: [
      {
        type: 'value' as const,
        name: '人次',
        nameTextStyle: { color: COCKPIT.textFaint, fontSize: 10 },
        splitLine: { lineStyle: { color: COCKPIT.grid } },
        axisLabel: { color: COCKPIT.textFaint, fontSize: 10, fontFamily: COCKPIT_FONT },
      },
      {
        type: 'value' as const,
        name: '成本$',
        nameTextStyle: { color: COCKPIT.textFaint, fontSize: 10 },
        splitLine: { show: false },
        axisLabel: { color: COCKPIT.textFaint, fontSize: 10, fontFamily: COCKPIT_FONT },
      },
    ],
    series: [
      {
        name: '活跃',
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: SEMANTIC.info, width: 2.5, shadowBlur: 12, shadowColor: alpha(SEMANTIC.info, 0.5) },
        areaStyle: { color: vGradient(alpha(SEMANTIC.info, 0.28), alpha(SEMANTIC.info, 0.01)) },
        data: trend.map(p => p.active),
      },
      {
        name: '学习成功',
        type: 'line' as const,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: SEMANTIC.positive, width: 2.5 },
        data: trend.map(p => p.successful),
      },
      {
        name: '成本($)',
        type: 'line' as const,
        yAxisIndex: 1,
        smooth: true,
        showSymbol: false,
        lineStyle: { color: SEMANTIC.warning, width: 2, type: 'dashed' as const },
        data: trend.map(p => p.cost),
      },
    ],
  }

  return (
    <CockpitBg className="p-4 md:p-5">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#E8915A]/90">
        <Activity className="h-3.5 w-3.5" />
        Operations Overview Cockpit
        {windowLabel ? <span className="ml-1 normal-case tracking-normal text-slate-500">· {windowLabel}</span> : null}
      </div>

      {/* KPI 带（来自 overview.cards，点击打开指标详情抽屉） */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        {kpis.map((card, i) => (
          <button key={`${card.label}-${i}`} type="button" onClick={onMetric ? () => onMetric(card) : undefined} className="text-left">
            <CockpitKpi
              label={card.label}
              value={card.value as string | number}
              tone={(TONE_BY_CARD[card.tone ?? 'neutral'] ?? TONE_CYCLE[i % TONE_CYCLE.length]) as never}
              sub={card.hint}
              delta={card.delta ? { value: card.delta, up: deltaUp(card.delta, card.tone) } : undefined}
            />
          </button>
        ))}
        {kpis.length === 0 ? <Empty /> : null}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.5fr_1fr]">
        <CockpitPanel glow title="活跃 / 学习成功 / 成本 趋势" hint="active-trend API · 按窗口" icon={<TrendingUp className="h-4 w-4" />}>
          {hasTrend ? <EChart option={trendOption} height={260} /> : <Empty />}
        </CockpitPanel>

        <CockpitPanel title="今日行动队列" hint="overview.alerts + anomalies" icon={<AlertTriangle className="h-4 w-4" />}>
          <ul className="space-y-2">
            {alerts.slice(0, 6).map((alert, idx) => (
              <li key={idx}>
                <button
                  type="button"
                  onClick={onAlert ? () => onAlert(alert) : undefined}
                  className="group flex w-full items-start gap-2.5 rounded-xl border border-white/10 bg-white/[0.03] p-2.5 text-left transition hover:border-[#E8915A]/30 hover:bg-[#E8915A]/[0.06]"
                >
                  <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full" style={{ background: LEVEL_COLOR[alert.level] ?? SEMANTIC.neutral }} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-bold text-slate-100">{alert.title}</span>
                    {alert.detail ? <span className="mt-0.5 block truncate text-[11px] text-slate-400">{alert.detail}</span> : null}
                  </span>
                  <ArrowRight className="mt-1 h-3 w-3 shrink-0 text-slate-500 transition group-hover:translate-x-0.5" />
                </button>
              </li>
            ))}
            {alerts.length === 0 ? (
              <li className="grid place-items-center rounded-xl border border-dashed border-white/10 px-2 py-8 text-[11px] text-slate-500">暂无风险项</li>
            ) : null}
          </ul>
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

const LEVEL_COLOR: Record<string, string> = { info: SEMANTIC.info, warning: SEMANTIC.warning, critical: SEMANTIC.danger }

function Empty(): ReactNode {
  return <div className="grid h-[200px] place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500">暂无数据</div>
}

void fmtNum
