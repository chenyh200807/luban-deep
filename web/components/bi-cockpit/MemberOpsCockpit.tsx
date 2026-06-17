/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 会员运营情报驾驶舱。数据来自 MemberDashboard 聚合（权威），
 * 不从分页 liveRows 派生分布以免失真。表格/筛选/抽屉仍在下方保留。
 */
import { Activity, BarChart3, Gauge, HeartPulse, PieChart, Sparkles, Users } from 'lucide-react'
import type { MemberDashboard } from '@/lib/member-api'
import { CockpitBar, CockpitDonut, CockpitGauge, type Datum } from './Charts'
import { CockpitBg, CockpitKpi, CockpitPanel, SectionLabel } from './Layout'
import { SEMANTIC, SERIES_COLORS } from './theme'

const num = (n: number | null | undefined) => (typeof n === 'number' && isFinite(n) ? n : 0)
const fmt = (n: number) => num(n).toLocaleString()

function Empty({ mini = false }: { mini?: boolean }) {
  return (
    <div className={`grid place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500 ${mini ? 'h-16' : 'h-[200px]'}`}>
      暂无数据
    </div>
  )
}

export function MemberOpsCockpit({ dashboard }: { dashboard: MemberDashboard | null }) {
  const d = dashboard
  const tier = (d?.tier_breakdown ?? []).map(t => ({ name: tierLabel(t.tier), value: num(t.count) })).filter(x => x.value > 0)
  const expiry = (d?.expiry_breakdown ?? []).map(e => ({ name: e.label, value: num(e.count) })).filter(x => x.value > 0)

  const total = num(d?.total_count)
  const active = num(d?.active_count)
  const expiring = num(d?.expiring_soon_count)
  const churn = num(d?.churn_risk_count)
  const other = Math.max(0, total - active - expiring - churn)
  const statusComp: Datum[] = [
    { name: '活跃', value: active, color: SEMANTIC.positive },
    { name: '即将到期', value: expiring, color: SEMANTIC.warning },
    { name: '流失风险', value: churn, color: SEMANTIC.danger },
    { name: '其它', value: other, color: SEMANTIC.neutral },
  ].filter(x => x.value > 0)

  const bh = d?.behavior_health
  const behavior: Datum[] = bh
    ? [
        { name: '学习报告(7d)', value: num(bh.learning_report_open_count_7d) },
        { name: '历史回看(7d)', value: num(bh.history_open_count_7d) },
        { name: '行动开启(7d)', value: num(bh.action_start_count_7d) },
        { name: '低信任', value: num(bh.low_trust_count) },
      ].filter(x => x.value > 0)
    : []

  return (
    <CockpitBg className="p-4 md:p-5">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#E8915A]/90">
        <Activity className="h-3.5 w-3.5" />
        Member Operations Cockpit
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-9">
        <CockpitKpi label="会员总数" value={fmt(total)} tone="cyan" icon={<Users className="h-4 w-4" />} />
        <CockpitKpi label="活跃" value={fmt(active)} tone="emerald" sub={total > 0 ? `${Math.round((active / total) * 100)}%` : undefined} />
        <CockpitKpi label="即将到期" value={fmt(expiring)} tone="amber" />
        <CockpitKpi label="今日新增" value={fmt(num(d?.new_today_count))} tone="teal" />
        <CockpitKpi label="近7天新增" value={fmt(num(d?.new_7d_count))} tone="sky" />
        <CockpitKpi label="近30天新增" value={fmt(num(d?.new_30d_count))} tone="violet" />
        <CockpitKpi label="流失风险" value={fmt(churn)} tone="rose" />
        <CockpitKpi label="健康分" value={num(d?.health_score)} tone="violet" icon={<HeartPulse className="h-4 w-4" />} />
        <CockpitKpi label="自动续费覆盖" value={num(d?.auto_renew_coverage)} unit="%" tone="gold" />
      </div>

      <SectionLabel icon={<PieChart className="h-4 w-4" />}>会员结构</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel glow title="Tier 分布" icon={<PieChart className="h-4 w-4" />}>
          {tier.length ? <CockpitDonut data={tier} centerLabel="会员" centerValue={fmt(total)} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="状态构成" hint="活跃 / 到期 / 风险" icon={<PieChart className="h-4 w-4" />}>
          {statusComp.length ? <CockpitDonut data={statusComp} centerLabel="会员" centerValue={fmt(total)} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="会员健康分" icon={<Gauge className="h-4 w-4" />}>
          <CockpitGauge value={num(d?.health_score)} label="健康分" suffix="" color={SERIES_COLORS[2]} />
        </CockpitPanel>
      </div>

      <SectionLabel icon={<BarChart3 className="h-4 w-4" />}>到期 · 行为 · 建议</SectionLabel>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel title="到期分布" icon={<BarChart3 className="h-4 w-4" />}>
          {expiry.length ? <CockpitBar data={expiry} color={SERIES_COLORS[3]} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="行为健康 (近 7 天)" icon={<HeartPulse className="h-4 w-4" />}>
          {behavior.length ? <CockpitBar data={behavior} color={SERIES_COLORS[0]} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="运营建议" icon={<Sparkles className="h-4 w-4" />}>
          {(d?.recommendations ?? []).length ? (
            <ul className="space-y-2">
              {(d?.recommendations ?? []).slice(0, 6).map((r, i) => (
                <li key={i} className="flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-2.5 text-[12px] text-slate-200">
                  <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#E8915A]" />
                  <span className="min-w-0">{r}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty />
          )}
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

function tierLabel(t: string): string {
  if (t === 'trial') return '体验'
  if (t === 'vip') return 'VIP'
  if (t === 'svip') return 'SVIP'
  return t || '未知'
}
