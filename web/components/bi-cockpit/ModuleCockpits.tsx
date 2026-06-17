/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 按模块的反馈情报驾驶舱（AI 反馈 / 内测申请 / 内测回访）。
 *
 * 单一权威 + 数据想通：入参类型即真实 BI payload；只做「真实字段 -> 图表」纯映射，
 * 不编造数字，缺失维度降级为「暂无数据」。图表点击统一回调 onDrill（= 展开现有明细表）。
 */
import {
  Activity,
  BarChart3,
  Gauge,
  Layers,
  MessageSquareWarning,
  PieChart,
  Radar,
  TrendingUp,
  Users,
} from 'lucide-react'
import type {
  BiFeedbackPayload,
  BiInviteTestStats,
  BiLubanFeedbackResponse,
  BiLubanFeedbackStats,
} from '@/lib/bi-api'
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

const num = (n: number | null | undefined) => (typeof n === 'number' && isFinite(n) ? n : 0)
const ratePct = (n: number | null | undefined) => Math.round(num(n) * (Math.abs(num(n)) <= 1 ? 100 : 1))
const top = (arr: Datum[], n: number) => [...arr].sort((a, b) => b.value - a.value).slice(0, n)
const fmt = (n: number) => num(n).toLocaleString()

function mapBreakdown<T extends Record<string, unknown>>(
  rows: T[] | undefined,
  nameKey: keyof T,
  valueKey: keyof T = 'count' as keyof T
): Datum[] {
  return (rows ?? [])
    .map(r => ({ name: String(r[nameKey] ?? '未知') || '未知', value: Number(r[valueKey] ?? 0) }))
    .filter(d => d.value > 0)
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

/* ============================================================ AI 消息反馈 */
export function FeedbackModuleCockpit({
  feedback,
  onDrill,
}: {
  feedback: BiFeedbackPayload | null
  onDrill: () => void
}) {
  const s = feedback?.summary
  const recent = feedback?.recent ?? []
  const total = num(s?.total_feedback)

  const sentiment: Datum[] = [
    { name: '赞', value: num(s?.thumbs_up), color: SEMANTIC.positive },
    { name: '踩', value: num(s?.thumbs_down), color: SEMANTIC.danger },
    { name: '中性', value: num(s?.neutral), color: SEMANTIC.neutral },
  ].filter(d => d.value > 0)

  const rating = mapBreakdown(feedback?.rating_breakdown, 'label')
  const reason = top(mapBreakdown(feedback?.top_reason_tags, 'tag'), 6)
  const answerMode = mapBreakdown(feedback?.answer_modes, 'answer_mode')

  // recent[] 聚合
  const triage = countBy(recent, r => triageLabel(r.triage_status))
  const problem = top(countBy(recent, r => r.problem_type), 6)
  const symptom = top(countByList(recent, r => r.symptom_tags), 6)
  const degrade = top(countBy(recent, r => r.response_mode_degrade_reason || '无降级'), 6)
  const platform = top(countBy(recent, r => r.context_snapshot?.platform), 6)
  const trend = trendByDay(recent.map(r => r.created_at))

  const upRate = total > 0 ? Math.round((num(s?.thumbs_up) / total) * 100) : 0
  const commentRate = total > 0 ? Math.round((num(s?.commented) / total) * 100) : 0

  return (
    <CockpitBg className="p-4 md:p-5">
      <Eyebrow icon={<MessageSquareWarning className="h-3.5 w-3.5" />} text="AI Feedback Cockpit" />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <CockpitKpi label="反馈总量" value={fmt(total)} tone="cyan" icon={<MessageSquareWarning className="h-4 w-4" />} />
        <CockpitKpi label="点赞率" value={upRate} unit="%" tone="emerald" icon={<TrendingUp className="h-4 w-4" />} sub={`赞 ${num(s?.thumbs_up)} / 踩 ${num(s?.thumbs_down)}`} />
        <CockpitKpi label="评论率" value={commentRate} unit="%" tone="amber" sub={`含文字 ${num(s?.commented)}`} />
        <CockpitKpi label="独立用户" value={fmt(num(s?.unique_users))} tone="teal" icon={<Users className="h-4 w-4" />} />
        <CockpitKpi label="独立会话" value={fmt(num(s?.unique_sessions))} tone="violet" />
        <CockpitKpi label="独立消息" value={fmt(num(s?.unique_messages))} tone="rose" />
      </div>

      <SectionLabel icon={<PieChart className="h-4 w-4" />}>情绪与评分</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel glow title="赞 / 踩 / 中性" hint="点击下钻明细" icon={<PieChart className="h-4 w-4" />}>
          {sentiment.length ? <CockpitDonut data={sentiment} centerLabel="情绪" centerValue={fmt(total)} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="评分分布" icon={<BarChart3 className="h-4 w-4" />}>
          {rating.length ? <CockpitBar data={rating} color={SERIES_COLORS[0]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="反馈量趋势" hint="按天" icon={<TrendingUp className="h-4 w-4" />}>
          {trend.length ? <CockpitTrend points={trend} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<MessageSquareWarning className="h-4 w-4" />}>问题诊断</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        <CockpitPanel title="Top 原因标签" icon={<BarChart3 className="h-4 w-4" />}>
          {reason.length ? <CockpitBar data={reason} color={SERIES_COLORS[1]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="问题类型" icon={<PieChart className="h-4 w-4" />}>
          {problem.length ? <CockpitDonut data={problem} centerLabel="问题" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="症状标签" icon={<BarChart3 className="h-4 w-4" />}>
          {symptom.length ? <CockpitBar data={symptom} color={SERIES_COLORS[3]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<Layers className="h-4 w-4" />}>回答模式 · 处理 · 终端</SectionLabel>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <CockpitPanel title="回答模式占比" icon={<PieChart className="h-4 w-4" />}>
          {answerMode.length ? <CockpitDonut data={answerMode} centerLabel="回答" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="响应降级原因" icon={<BarChart3 className="h-4 w-4" />}>
          {degrade.length ? <CockpitBar data={degrade} color={SERIES_COLORS[6]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="处理状态" icon={<PieChart className="h-4 w-4" />}>
          {triage.length ? <CockpitDonut data={triage} centerLabel="近期样本" centerValue={fmt(recent.length)} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="终端平台" icon={<BarChart3 className="h-4 w-4" />}>
          {platform.length ? <CockpitBar data={platform} color={SERIES_COLORS[7]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

/* ============================================================ 内测申请 */
export function InviteModuleCockpit({
  invite,
  onDrill,
}: {
  invite: BiInviteTestStats | null
  onDrill: () => void
}) {
  const s = invite?.summary
  const examType = top(mapBreakdown(invite?.exam_type_breakdown, 'exam_type'), 6)
  const examStage = mapBreakdown(invite?.exam_stage_breakdown, 'exam_stage')
  const prepYears = mapBreakdown(invite?.preparation_years_breakdown, 'preparation_years')
  const foundation = mapBreakdown(invite?.knowledge_foundation_breakdown, 'knowledge_foundation')
  const age = mapBreakdown(invite?.age_range_breakdown, 'age_range')
  const education = mapBreakdown(invite?.education_breakdown, 'education')
  const occupation = top(mapBreakdown(invite?.occupation_breakdown, 'occupation'), 6)
  const province = top(mapBreakdown(invite?.province_breakdown, 'province'), 6)
  const weekly = mapBreakdown(invite?.weekly_time_breakdown, 'weekly_time')
  const daily = mapBreakdown(invite?.daily_study_time_breakdown, 'daily_study_time')
  const pain = top(mapBreakdown(invite?.pain_point_breakdown, 'pain_point'), 6)
  const status = mapBreakdown(invite?.status_breakdown, 'status')
  const source = mapBreakdown(invite?.source_breakdown, 'source_page')

  return (
    <CockpitBg className="p-4 md:p-5">
      <Eyebrow icon={<Users className="h-3.5 w-3.5" />} text="Invite Application Cockpit" />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <CockpitKpi label="申请总量" value={fmt(num(s?.total_applications))} tone="cyan" icon={<Users className="h-4 w-4" />} />
        <CockpitKpi label="独立联系人" value={fmt(num(s?.unique_contacts))} tone="teal" />
        <CockpitKpi label="接受回访率" value={ratePct(s?.accept_interview_rate)} unit="%" tone="emerald" icon={<Gauge className="h-4 w-4" />} sub={`${num(s?.accept_interview_count)} 人愿访谈`} />
        <CockpitKpi label="带错题率" value={ratePct(s?.with_wrong_question_rate)} unit="%" tone="amber" sub={`${num(s?.with_wrong_question_count)} 份`} />
        <CockpitKpi label="同意授权" value={fmt(num(s?.consented_count))} tone="rose" />
      </div>

      <SectionLabel icon={<PieChart className="h-4 w-4" />}>转化与来源</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <CockpitPanel glow title="申请状态" hint="点击下钻明细" icon={<PieChart className="h-4 w-4" />}>
          {status.length ? <CockpitDonut data={status} centerLabel="申请" centerValue={fmt(num(s?.total_applications))} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="来源渠道" icon={<PieChart className="h-4 w-4" />}>
          {source.length ? <CockpitDonut data={source} centerLabel="来源" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<BarChart3 className="h-4 w-4" />}>考试画像</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <CockpitPanel title="考试类型" icon={<BarChart3 className="h-4 w-4" />}>
          {examType.length ? <CockpitBar data={examType} color={SERIES_COLORS[0]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="备考阶段" icon={<PieChart className="h-4 w-4" />}>
          {examStage.length ? <CockpitDonut data={examStage} centerLabel="阶段" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="备考年限" icon={<BarChart3 className="h-4 w-4" />}>
          {prepYears.length ? <CockpitBar data={prepYears} color={SERIES_COLORS[1]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="知识基础" icon={<BarChart3 className="h-4 w-4" />}>
          {foundation.length ? <CockpitBar data={foundation} color={SERIES_COLORS[4]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<Users className="h-4 w-4" />}>人群画像</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <CockpitPanel title="年龄段" icon={<PieChart className="h-4 w-4" />}>
          {age.length ? <CockpitDonut data={age} centerLabel="年龄" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="学历" icon={<BarChart3 className="h-4 w-4" />}>
          {education.length ? <CockpitBar data={education} color={SERIES_COLORS[2]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="职业" icon={<BarChart3 className="h-4 w-4" />}>
          {occupation.length ? <CockpitBar data={occupation} color={SERIES_COLORS[6]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="地域 Top" icon={<Radar className="h-4 w-4" />}>
          {province.length ? <CockpitRadar data={province} color={SERIES_COLORS[2]} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<Layers className="h-4 w-4" />}>学习画像</SectionLabel>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <CockpitPanel title="每周时长" icon={<BarChart3 className="h-4 w-4" />}>
          {weekly.length ? <CockpitBar data={weekly} color={SERIES_COLORS[7]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="每日时长" icon={<BarChart3 className="h-4 w-4" />}>
          {daily.length ? <CockpitBar data={daily} color={SERIES_COLORS[5]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="核心痛点 Top" icon={<BarChart3 className="h-4 w-4" />}>
          {pain.length ? <CockpitBar data={pain} color={SERIES_COLORS[3]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

/* ============================================================ 内测回访 */
export function LubanModuleCockpit({
  luban,
  responses,
  onDrill,
}: {
  luban: BiLubanFeedbackStats | null
  responses: BiLubanFeedbackResponse[]
  onDrill: () => void
}) {
  const s = luban?.summary
  const satisfaction = mapBreakdown(luban?.satisfaction_breakdown, 'overall_satisfaction')
  const mostValuable = top(mapBreakdown(luban?.most_valuable_breakdown, 'most_valuable'), 6)
  const willContinue = mapBreakdown(luban?.will_continue_breakdown, 'will_continue')
  const payWill = mapBreakdown(luban?.pay_willingness_breakdown, 'pay_willingness')
  const revisit = mapBreakdown(luban?.revisit_willingness_breakdown, 'revisit_willingness')
  const attempt = mapBreakdown(luban?.attempt_count_breakdown, 'attempt_count')
  const timeframe = mapBreakdown(luban?.exam_timeframe_breakdown, 'exam_timeframe')
  const feature = featureRadar(responses)

  const nps = num(s?.nps_score)
  const promoterRate = num(s?.nps_base) > 0 ? Math.round((num(s?.promoters) / num(s?.nps_base)) * 100) : 0

  return (
    <CockpitBg className="p-4 md:p-5">
      <Eyebrow icon={<Gauge className="h-3.5 w-3.5" />} text="Revisit Survey Cockpit" />
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <CockpitKpi label="NPS" value={nps} tone={nps >= 0 ? 'emerald' : 'rose'} icon={<BarChart3 className="h-4 w-4" />} sub={`样本 ${num(s?.nps_base)}`} />
        <CockpitKpi label="满意度" value={num(s?.avg_satisfaction).toFixed(1)} unit="/5" tone="amber" />
        <CockpitKpi label="复访意愿率" value={ratePct(s?.revisit_willing_rate)} unit="%" tone="cyan" icon={<Activity className="h-4 w-4" />} />
        <CockpitKpi label="留资率" value={ratePct(s?.with_contact_rate)} unit="%" tone="teal" sub={`${num(s?.with_contact_count)} 人`} />
        <CockpitKpi label="回访总量" value={fmt(num(s?.total_responses))} tone="violet" />
        <CockpitKpi label="推荐者占比" value={promoterRate} unit="%" tone="rose" sub={`${num(s?.promoters)} 人`} />
      </div>

      <SectionLabel icon={<Gauge className="h-4 w-4" />}>口碑</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel glow title="NPS 仪表" icon={<Gauge className="h-4 w-4" />}>
          <CockpitGauge value={nps} label="NPS" suffix="" color={nps >= 0 ? SEMANTIC.positive : SEMANTIC.danger} />
        </CockpitPanel>
        <CockpitPanel title="NPS 结构" hint="推荐 / 被动 / 贬损" icon={<BarChart3 className="h-4 w-4" />}>
          {num(s?.promoters) + num(s?.passives) + num(s?.detractors) > 0 ? (
            <div className="flex flex-col gap-3 pt-6">
              <CockpitNpsBar promoters={num(s?.promoters)} passives={num(s?.passives)} detractors={num(s?.detractors)} />
              <div className="flex justify-between text-[11px] font-bold">
                <span className="text-emerald-300">推荐 {num(s?.promoters)}</span>
                <span className="text-amber-300">被动 {num(s?.passives)}</span>
                <span className="text-rose-300">贬损 {num(s?.detractors)}</span>
              </div>
            </div>
          ) : (
            <Empty mini />
          )}
        </CockpitPanel>
        <CockpitPanel title="满意度分布" icon={<BarChart3 className="h-4 w-4" />}>
          {satisfaction.length ? <CockpitBar data={satisfaction} color={SERIES_COLORS[1]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<PieChart className="h-4 w-4" />}>价值与意愿</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <CockpitPanel title="最有价值功能" hint="点击下钻明细" icon={<BarChart3 className="h-4 w-4" />}>
          {mostValuable.length ? <CockpitBar data={mostValuable} color={SERIES_COLORS[0]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="是否续用" icon={<PieChart className="h-4 w-4" />}>
          {willContinue.length ? <CockpitDonut data={willContinue} centerLabel="续用" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="付费意愿" icon={<PieChart className="h-4 w-4" />}>
          {payWill.length ? <CockpitDonut data={payWill} centerLabel="付费" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="复访意愿" icon={<PieChart className="h-4 w-4" />}>
          {revisit.length ? <CockpitDonut data={revisit} centerLabel="复访" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<Radar className="h-4 w-4" />}>功能体验 · 考情</SectionLabel>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        <CockpitPanel glow title="功能体验六维" hint="均分(满分 5)" icon={<Radar className="h-4 w-4" />}>
          {feature.length ? <CockpitRadar data={feature} color={SERIES_COLORS[0]} max={5} height={240} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="考试次数" icon={<PieChart className="h-4 w-4" />}>
          {attempt.length ? <CockpitDonut data={attempt} centerLabel="次数" onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="考试时间窗" icon={<BarChart3 className="h-4 w-4" />}>
          {timeframe.length ? <CockpitBar data={timeframe} color={SERIES_COLORS[7]} onSelect={onDrill} /> : <Empty />}
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

/* ---------------------------------------------------------------- 共享小工具 */
function Eyebrow({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#E8915A]/90">
      {icon}
      {text}
    </div>
  )
}

function triageLabel(s: string | undefined): string {
  if (s === 'triaged') return '已看'
  if (s === 'ignored') return '已忽略'
  return '待处理'
}

function countBy<T>(rows: T[], pick: (r: T) => string | undefined | null): Datum[] {
  const m = new Map<string, number>()
  for (const r of rows) {
    const k = (pick(r) ?? '').trim()
    if (!k) continue
    m.set(k, (m.get(k) ?? 0) + 1)
  }
  return [...m.entries()].map(([name, value]) => ({ name, value }))
}

function countByList<T>(rows: T[], pick: (r: T) => string[] | undefined): Datum[] {
  const m = new Map<string, number>()
  for (const r of rows) {
    for (const raw of pick(r) ?? []) {
      const k = (raw ?? '').trim()
      if (!k) continue
      m.set(k, (m.get(k) ?? 0) + 1)
    }
  }
  return [...m.entries()].map(([name, value]) => ({ name, value }))
}

function trendByDay(dates: Array<string | undefined>): Array<{ label: string; value: number }> {
  const m = new Map<string, number>()
  for (const d of dates) {
    const day = (d ?? '').slice(5, 10) // MM-DD
    if (!day) continue
    m.set(day, (m.get(day) ?? 0) + 1)
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([label, value]) => ({ label, value }))
}

/** 从 responses 的功能评分字段算均分雷达；只用能解析成 1-5 的真实值，不编造 */
const SAT_WORD: Record<string, number> = {
  非常满意: 5, 很满意: 5, 比较满意: 4, 满意: 4, 一般: 3, 不太满意: 2, 不满意: 2, 很不满意: 1, 非常不满意: 1,
}
function toScore(v: string | undefined | null): number | null {
  if (v == null) return null
  const s = String(v).trim()
  if (!s) return null
  if (/^[1-5]$/.test(s)) return Number(s)
  if (s in SAT_WORD) return SAT_WORD[s]
  const f = parseFloat(s)
  return isFinite(f) && f >= 1 && f <= 5 ? f : null
}
function featureRadar(responses: BiLubanFeedbackResponse[]): Datum[] {
  const fields: Array<[string, keyof BiLubanFeedbackResponse]> = [
    ['案例批改', 'feat_case_grading'],
    ['错题教练', 'feat_error_coach'],
    ['知识问答', 'feat_qa'],
    ['易用性', 'ease_of_use'],
    ['准确性', 'accuracy'],
    ['速度', 'speed'],
  ]
  return fields
    .map(([name, key]) => {
      const vals = responses.map(r => toScore(r[key] as string)).filter((v): v is number => v != null)
      if (!vals.length) return null
      return { name, value: Number((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2)) }
    })
    .filter((d): d is Datum => d != null)
}
