/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 反馈情报驾驶舱（旗舰）。
 *
 * 数据想通保证：入参类型即三套真实 BI payload（与 bi-api.ts 的 getter 返回完全一致）。
 * 本组件只做「真实字段 -> 图表数据」的纯映射，不编造任何数字；
 * 字段缺失时降级为占位，不伪造。
 */
import {
  Activity,
  BarChart3,
  Gauge,
  MessageSquareWarning,
  PieChart,
  Radar,
  TrendingUp,
  Users,
} from 'lucide-react'
import type { BiFeedbackPayload, BiInviteTestStats, BiLubanFeedbackStats } from '@/lib/bi-api'
import {
  CockpitBar,
  CockpitDonut,
  CockpitGauge,
  CockpitNpsBar,
  CockpitRadar,
  CockpitTrend,
  type Datum,
} from './Charts'
import { CockpitBg, CockpitKpi, CockpitPanel, SectionLabel } from './Layout'
import { SEMANTIC, SERIES_COLORS } from './theme'

type Props = {
  feedback: BiFeedbackPayload | null
  invite: BiInviteTestStats | null
  luban: BiLubanFeedbackStats | null
  windowDays?: number
}

const num = (n: number | null | undefined) => (typeof n === 'number' && isFinite(n) ? n : 0)
const pct = (n: number | null | undefined) =>
  `${Math.round(num(n) * (Math.abs(num(n)) <= 1 ? 100 : 1))}`
const top = (arr: Datum[], n: number) => [...arr].sort((a, b) => b.value - a.value).slice(0, n)

/** 把后端 *_breakdown 数组映射成 {name,value} */
function mapBreakdown<T extends Record<string, unknown>>(
  rows: T[] | undefined,
  nameKey: keyof T,
  valueKey: keyof T = 'count' as keyof T
): Datum[] {
  return (rows ?? [])
    .map(r => ({ name: String(r[nameKey] ?? '未知') || '未知', value: Number(r[valueKey] ?? 0) }))
    .filter(d => d.value > 0)
}

/** 从 recent 反馈按天聚合出趋势 */
function feedbackTrend(payload: BiFeedbackPayload | null): Array<{ label: string; value: number }> {
  const recent = payload?.recent ?? []
  if (recent.length === 0) return []
  const byDay = new Map<string, number>()
  for (const r of recent) {
    const d = (r.created_at ?? '').slice(5, 10) // MM-DD
    if (!d) continue
    byDay.set(d, (byDay.get(d) ?? 0) + 1)
  }
  return [...byDay.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([label, value]) => ({ label, value }))
}

/** 从 recent 反馈聚合 triage 状态 */
function triageBreakdown(payload: BiFeedbackPayload | null): Datum[] {
  const recent = payload?.recent ?? []
  const m = { open: 0, triaged: 0, ignored: 0 }
  for (const r of recent) {
    const s = (r.triage_status ?? 'open') as keyof typeof m
    if (s in m) m[s] += 1
  }
  return [
    { name: '待处理', value: m.open, color: SEMANTIC.warning },
    { name: '已分诊', value: m.triaged, color: SEMANTIC.info },
    { name: '已忽略', value: m.ignored, color: SEMANTIC.neutral },
  ].filter(d => d.value > 0)
}

export function FeedbackCockpit({ feedback, invite, luban, windowDays = 30 }: Props) {
  const fs = feedback?.summary
  const is = invite?.summary
  const ls = luban?.summary

  const moduleComposition: Datum[] = [
    { name: 'AI 消息反馈', value: num(fs?.total_feedback), color: SERIES_COLORS[0] },
    { name: '内测申请', value: num(is?.total_applications), color: SERIES_COLORS[1] },
    { name: '内测回访', value: num(ls?.total_responses), color: SERIES_COLORS[2] },
  ].filter(d => d.value > 0)
  const grandTotal = moduleComposition.reduce((s, d) => s + d.value, 0)

  const thumbUpRate =
    fs && fs.total_feedback > 0 ? Math.round((fs.thumbs_up / fs.total_feedback) * 100) : 0
  const trend = feedbackTrend(feedback)

  const ratingData = mapBreakdown(feedback?.rating_breakdown, 'label')
  const reasonData = top(mapBreakdown(feedback?.top_reason_tags, 'tag'), 6)
  const triage = triageBreakdown(feedback)

  const examTypeData = top(mapBreakdown(invite?.exam_type_breakdown, 'exam_type'), 6)
  const painData = top(mapBreakdown(invite?.pain_point_breakdown, 'pain_point'), 6)
  const inviteProfile = top(mapBreakdown(invite?.province_breakdown, 'province'), 6)

  const npsPromoters = num(ls?.promoters)
  const npsPassives = num(ls?.passives)
  const npsDetractors = num(ls?.detractors)
  const valuableData = top(mapBreakdown(luban?.most_valuable_breakdown, 'most_valuable'), 6)

  return (
    <CockpitBg className="p-4 md:p-6">
      {/* —— 顶部标题 —— */}
      <header className="mb-5 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-cyan-300/80">
            <Activity className="h-3.5 w-3.5" />
            Feedback Intelligence Cockpit
          </div>
          <h1 className="mt-1 text-2xl font-black text-white md:text-[28px]">反馈情报驾驶舱</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1 text-[11px] font-bold text-cyan-200">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-cyan-300" />
            </span>
            实时 · 近 {windowDays} 天
          </span>
        </div>
      </header>

      {/* —— KPI 带 —— */}
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <CockpitKpi
          label="反馈总量"
          value={grandTotal.toLocaleString()}
          tone="cyan"
          icon={<MessageSquareWarning className="h-4 w-4" />}
          sub="三类数据合计"
        />
        <CockpitKpi
          label="点赞率"
          value={thumbUpRate}
          unit="%"
          tone="emerald"
          icon={<TrendingUp className="h-4 w-4" />}
          sub={`赞 ${num(fs?.thumbs_up)} · 踩 ${num(fs?.thumbs_down)}`}
        />
        <CockpitKpi
          label="内测申请"
          value={num(is?.total_applications).toLocaleString()}
          tone="teal"
          icon={<Users className="h-4 w-4" />}
          sub={`独立联系人 ${num(is?.unique_contacts)}`}
        />
        <CockpitKpi
          label="接受回访率"
          value={pct(is?.accept_interview_rate)}
          unit="%"
          tone="violet"
          icon={<Gauge className="h-4 w-4" />}
          sub={`${num(is?.accept_interview_count)} 人愿访谈`}
        />
        <CockpitKpi
          label="NPS"
          value={num(ls?.nps_score)}
          tone={num(ls?.nps_score) >= 0 ? 'emerald' : 'rose'}
          icon={<BarChart3 className="h-4 w-4" />}
          sub={`样本 ${num(ls?.nps_base)}`}
        />
        <CockpitKpi
          label="复访意愿率"
          value={pct(ls?.revisit_willing_rate)}
          unit="%"
          tone="amber"
          icon={<Radar className="h-4 w-4" />}
          sub={`满意度 ${num(ls?.avg_satisfaction).toFixed(1)}`}
        />
      </div>

      {/* —— 主视觉行 —— */}
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-[1.1fr_1.4fr_1fr]">
        <CockpitPanel
          glow
          title="三类数据占比"
          hint="AI 反馈 / 内测申请 / 内测回访"
          icon={<PieChart className="h-4 w-4" />}
        >
          {moduleComposition.length ? (
            <CockpitDonut
              data={moduleComposition}
              centerLabel="反馈总量"
              centerValue={grandTotal.toLocaleString()}
              height={240}
            />
          ) : (
            <Empty />
          )}
        </CockpitPanel>

        <CockpitPanel
          title="反馈量趋势"
          hint="近期 AI 消息反馈按天"
          icon={<TrendingUp className="h-4 w-4" />}
        >
          {trend.length ? <CockpitTrend points={trend} height={240} /> : <Empty />}
        </CockpitPanel>

        <CockpitPanel
          title="NPS 结构"
          hint="推荐者 / 被动者 / 贬损者"
          icon={<Gauge className="h-4 w-4" />}
        >
          <div className="flex flex-col gap-3">
            <CockpitGauge
              value={num(ls?.nps_score)}
              label="NPS"
              suffix=""
              color={num(ls?.nps_score) >= 0 ? SEMANTIC.positive : SEMANTIC.danger}
              height={170}
            />
            {npsPromoters + npsPassives + npsDetractors > 0 ? (
              <>
                <CockpitNpsBar
                  promoters={npsPromoters}
                  passives={npsPassives}
                  detractors={npsDetractors}
                  height={48}
                />
                <div className="flex justify-between text-[11px] font-bold">
                  <span className="text-emerald-300">推荐 {npsPromoters}</span>
                  <span className="text-amber-300">被动 {npsPassives}</span>
                  <span className="text-rose-300">贬损 {npsDetractors}</span>
                </div>
              </>
            ) : (
              <Empty mini />
            )}
          </div>
        </CockpitPanel>
      </div>

      {/* —— AI 反馈细分 —— */}
      <SectionLabel icon={<MessageSquareWarning className="h-4 w-4" />}>AI 消息反馈</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        <CockpitPanel title="处理状态分布" icon={<PieChart className="h-4 w-4" />}>
          {triage.length ? (
            <CockpitDonut
              data={triage}
              centerLabel="近期样本"
              centerValue={String(triage.reduce((s, d) => s + d.value, 0))}
              height={200}
            />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
        <CockpitPanel title="评分分布" icon={<BarChart3 className="h-4 w-4" />}>
          {ratingData.length ? (
            <CockpitBar data={ratingData} color={SERIES_COLORS[0]} />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
        <CockpitPanel title="Top 原因标签" icon={<BarChart3 className="h-4 w-4" />}>
          {reasonData.length ? (
            <CockpitBar data={reasonData} color={SERIES_COLORS[3]} />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
      </div>

      {/* —— 内测申请细分 —— */}
      <SectionLabel icon={<Users className="h-4 w-4" />}>内测申请池</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        <CockpitPanel title="考试类型分布" icon={<BarChart3 className="h-4 w-4" />}>
          {examTypeData.length ? (
            <CockpitBar data={examTypeData} color={SERIES_COLORS[1]} />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
        <CockpitPanel title="核心痛点 Top" icon={<BarChart3 className="h-4 w-4" />}>
          {painData.length ? <CockpitBar data={painData} color={SERIES_COLORS[4]} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="地域分布 Top" icon={<Radar className="h-4 w-4" />}>
          {inviteProfile.length ? (
            <CockpitRadar data={inviteProfile} color={SERIES_COLORS[2]} height={220} />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
      </div>

      {/* —— 内测回访细分 —— */}
      <SectionLabel icon={<Gauge className="h-4 w-4" />}>内测回访问卷</SectionLabel>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <CockpitPanel title="最有价值功能" icon={<BarChart3 className="h-4 w-4" />}>
          {valuableData.length ? (
            <CockpitBar data={valuableData} color={SERIES_COLORS[5]} />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
        <CockpitPanel title="满意度均值" icon={<Gauge className="h-4 w-4" />}>
          <CockpitGauge
            value={Math.round(num(ls?.avg_satisfaction) * 20)}
            label={`满意度 ${num(ls?.avg_satisfaction).toFixed(1)}/5`}
            color={SERIES_COLORS[5]}
            height={200}
          />
        </CockpitPanel>
        <CockpitPanel title="付费意愿分布" icon={<PieChart className="h-4 w-4" />}>
          {mapBreakdown(luban?.pay_willingness_breakdown, 'pay_willingness').length ? (
            <CockpitDonut
              data={top(mapBreakdown(luban?.pay_willingness_breakdown, 'pay_willingness'), 5)}
              centerLabel="回访样本"
              centerValue={String(num(ls?.total_responses))}
              height={200}
            />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

function Empty({ mini = false }: { mini?: boolean }) {
  return (
    <div
      className={`grid place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500 ${mini ? 'h-16' : 'h-[200px]'}`}
    >
      暂无数据
    </div>
  )
}
