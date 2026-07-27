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
import { NewRegistrationCard } from './NewRegistrationCard'
import { SERIES_COLORS } from './theme'

const num = (n: number | null | undefined) => (typeof n === 'number' && isFinite(n) ? n : 0)
const fmt = (n: number) => num(n).toLocaleString()

function Empty({ mini = false }: { mini?: boolean }) {
  return (
    <div className={`grid place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500 ${mini ? 'h-16' : 'h-[200px]'}`}>
      暂无数据
    </div>
  )
}

export function MemberOpsCockpit({
  dashboard,
  loading = false,
  error = '',
}: {
  dashboard: MemberDashboard | null
  loading?: boolean
  error?: string
}) {
  const d = dashboard
  if (!d) {
    return (
      <CockpitBg className="p-4 md:p-5">
        <div className="grid min-h-36 place-items-center rounded-xl border border-dashed border-white/10 px-4 text-center text-sm text-slate-400">
          {loading ? '正在加载真实会员经营数据…' : error ? '会员经营数据暂不可用，请稍后刷新。' : '暂无会员经营数据。'}
        </div>
      </CockpitBg>
    )
  }
  const tier = (d?.tier_breakdown ?? []).map(t => ({ name: tierLabel(t.tier), value: num(t.count) })).filter(x => x.value > 0)
  const expiry = (d?.expiry_breakdown ?? []).map(e => ({ name: e.label, value: num(e.count) })).filter(x => x.value > 0)

  const total = num(d?.total_count)
  const active = num(d?.active_count)
  const expiring = num(d?.expiring_soon_count)
  const churn = num(d?.churn_risk_count)
  const bh = d?.behavior_health
  const behavior: Datum[] = bh
    ? [
        { name: '学习报告(7d)', value: num(bh.learning_report_open_count_7d) },
        { name: '历史回看(7d)', value: num(bh.history_open_count_7d) },
        { name: '行动开启(7d)', value: num(bh.action_start_count_7d) },
        { name: '低信任', value: num(bh.low_trust_count) },
      ].filter(x => x.value > 0)
    : []
  const moduleUsage: Datum[] = (bh?.module_usage ?? []).slice(0, 8).map(item => ({
    name: moduleLabel(item.module),
    value: num(item.member_count),
  }))
  const moduleUsageRows = (bh?.module_usage ?? []).slice(0, 8)
  const firstRun = bh?.first_run

  return (
    <CockpitBg className="p-4 md:p-5">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#E8915A]/90">
        <Activity className="h-3.5 w-3.5" />
        Member Operations Cockpit
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-9">
        {/* 新增注册收成一张可自选窗口的卡：今日/7/30 三个固定数字曾各自算一遍，
            现在全部是同一个每日序列的后缀和，口径不会再打架。 */}
        <NewRegistrationCard
          trend={d?.new_registration_trend}
          operationalStartAt={d?.authority?.operational_start_at}
          className="col-span-2 md:col-span-2 xl:col-span-3"
        />
        <CockpitKpi label="会员总数" value={fmt(total)} tone="cyan" icon={<Users className="h-4 w-4" />} />
        <CockpitKpi label="权益有效" value={fmt(active)} tone="emerald" sub={total > 0 ? `${Math.round((active / total) * 100)}%` : undefined} />
        <CockpitKpi label="即将到期" value={fmt(expiring)} tone="amber" />
        <CockpitKpi label="流失风险" value={fmt(churn)} tone="rose" />
        <CockpitKpi label="权益有效率" value={num(d?.health_score)} unit="%" tone="violet" icon={<HeartPulse className="h-4 w-4" />} />
        <CockpitKpi label="自动续费覆盖" value={num(d?.auto_renew_coverage)} unit="%" tone="gold" />
      </div>

      <SectionLabel icon={<PieChart className="h-4 w-4" />}>会员结构</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <CockpitPanel glow title="Tier 分布" icon={<PieChart className="h-4 w-4" />}>
          {tier.length ? <CockpitDonut data={tier} centerLabel="会员" centerValue={fmt(total)} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="权益有效率" hint="权益状态为有效的会员占比" icon={<Gauge className="h-4 w-4" />}>
          <CockpitGauge value={num(d?.health_score)} label="权益有效率" suffix="%" color={SERIES_COLORS[2]} />
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

      <SectionLabel icon={<BarChart3 className="h-4 w-4" />}>产品行为智能</SectionLabel>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div data-testid="bi-member-module-usage">
          <CockpitPanel title="模块使用 (近 7 天)" hint="触达、访问、行动、完成与快速退出；不把单次访问冒充喜欢" icon={<BarChart3 className="h-4 w-4" />}>
            {moduleUsage.length ? (
              <div className="space-y-3">
                {num(bh?.identity_collision_count) > 0 ? (
                  <div className="rounded-lg border border-amber-400/20 bg-amber-400/10 px-3 py-2 text-[11px] text-amber-200">
                    已排除 {num(bh?.identity_collision_count)} 个冲突身份，影响 {num(bh?.identity_collision_member_count)} 位会员；未把歧义行为计入模块数据。
                  </div>
                ) : null}
                <CockpitBar data={moduleUsage} color={SERIES_COLORS[1]} />
                <div className="overflow-x-auto text-[11px] text-slate-300">
                  <div className="grid min-w-[520px] grid-cols-6 gap-2 border-b border-white/10 px-2 py-1 text-slate-500">
                    <span>模块</span><span>会员</span><span>访问</span><span>行动</span><span>完成</span><span>快速退出</span>
                  </div>
                  {moduleUsageRows.map(item => (
                    <div key={item.module} className="grid min-w-[520px] grid-cols-6 gap-2 border-b border-white/5 px-2 py-1.5">
                      <span>{moduleLabel(item.module)}</span>
                      <span>{num(item.member_count)}</span>
                      <span>{num(item.visit_count)}</span>
                      <span>{num(item.action_count)}</span>
                      <span>{num(item.completion_count)}</span>
                      <span>{num(item.quick_exit_count)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : <Empty />}
          </CockpitPanel>
        </div>
        <div data-testid="bi-member-first-run-funnel">
          <CockpitPanel title="First Run 完成漏斗" hint="完成只认 learner-state 权威标记；埋点仅作过程证据" icon={<Sparkles className="h-4 w-4" />}>
            {firstRun ? (
              <div className="grid grid-cols-2 gap-2 text-[12px] text-slate-200 md:grid-cols-3">
                <Metric label="应覆盖" value={firstRun.eligible_member_count} />
                <Metric label="已开始" value={firstRun.started_member_count} />
                <Metric label="完成" value={firstRun.completed_member_count} />
                <Metric label="进行答题" value={firstRun.question_member_count} />
                <Metric label="未开始" value={firstRun.not_started_member_count} />
                <Metric label="同步异常" value={firstRun.sync_anomaly_member_count} />
                <Metric label="真相不可用" value={firstRun.truth_unavailable_member_count} />
                <Metric label="真相覆盖率" value={`${Math.round(num(firstRun.truth_coverage_rate) * 100)}%`} />
                <Metric label="已确认完成率" value={`${Math.round(num(firstRun.completion_rate_of_confirmed) * 100)}%`} />
              </div>
            ) : <Empty />}
          </CockpitPanel>
        </div>
      </div>
    </CockpitBg>
  )
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3"><div className="text-slate-500">{label}</div><div className="mt-1 text-lg font-bold text-white">{value}</div></div>
}

function moduleLabel(module: string): string {
  return ({ learning: '学习', chat: '问鲁班', history: '历史', learning_report: '学情', notebook: '错题本', practice: '练习', assessment: '测评', profile: '我的' } as Record<string, string>)[module] || module
}

function tierLabel(t: string): string {
  if (t === 'trial') return '体验'
  if (t === 'vip') return 'VIP'
  if (t === 'svip') return 'SVIP'
  return t || '未知'
}
