/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 产品功能偏好驾驶舱（P3 埋点计划 · 专家 B 布局）。
 * 覆盖全产品模块（chat/learning/practice/first_run/assessment/history/notebook/
 * learning_report/profile…）的触达×深度、教学内容复看与点击量、功能使用与练习热度。
 *
 * thin wrapper：全复用 components/bi-cockpit 图表原语（CockpitBar / CockpitKpi /
 * CockpitBg / CockpitPanel / SectionLabel），零新增图表原语。
 *
 * 诚实性护栏（焊入 UI，不可省）：
 *  - completion_source=dwell：观看口径一律标"停留时长"，绝不显示"完播率%"。
 *  - 低流量小样本：顶部醒目提示 + memberCount<10 行挂 C 级灰徽标。
 *  - demo：include_demo 开关，demoIncluded=true 时顶部合成数据 banner。
 *  - 空数据走 Empty，绝不补 0 冒充。
 */
import {
  BookOpen,
  Flame,
  GraduationCap,
  Layers,
  LayoutGrid,
  LineChart,
  MousePointerClick,
  Repeat,
  Sparkles,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { BiV2DataSourceBanner } from '@/components/bi-v2'
import { CockpitBar, type Datum } from '@/components/bi-cockpit/Charts'
import { CockpitBg, CockpitKpi, CockpitPanel, SectionLabel } from '@/components/bi-cockpit/Layout'
import { SERIES_COLORS, TRUST_LEVEL_COLORS, alpha } from '@/components/bi-cockpit/theme'
import {
  getBiLearningPreference,
  type BiLearningPreferenceData,
  type BiLearningPrefRow,
} from '@/lib/bi-api'

/* ---------------------------------------------------------------- 标签映射 */
const OBJECT_TYPE_LABEL: Record<string, string> = {
  station: '考点站',
  microlesson: '微课',
  concept_card: '考点卡',
  variant: '练习题',
  seethrough_day: '看穿',
  retest: '复测',
  full_answer: '闯关',
}
function objectTypeLabel(t: string): string {
  return OBJECT_TYPE_LABEL[t] || t || '未知'
}

const ACTION_LABEL: Record<string, string> = {
  view: '浏览',
  open_detail: '打开详情',
  start_training: '开始学习',
  complete: '完成',
}
function actionLabel(a: string): string {
  return ACTION_LABEL[a] || a || '未知'
}

/** 全产品模块名 → 中文标签；未知模块原样显示。 */
const MODULE_LABEL: Record<string, string> = {
  learning: '学习',
  chat: '问答/AI答疑',
  practice: '练习',
  first_run: '首次体验',
  assessment: '测评',
  history: '历史',
  notebook: '笔记',
  learning_report: '学情报告',
  profile: '我的',
}
function moduleLabel(m: string): string {
  return MODULE_LABEL[m] || m || '未知'
}

/* ------------------------------------------------------------------ 数值工具 */
const num = (n: number | null | undefined) => (typeof n === 'number' && isFinite(n) ? n : 0)
const fmtInt = (n: number | null | undefined) => num(n).toLocaleString('zh-CN')
const fmtRatio = (n: number | null | undefined) => num(n).toFixed(1)
/** 小样本阈值：低于此触达人数的行/指标不作结论，挂 C 级灰徽标。 */
const SMALL_SAMPLE = 10
/** accuracy / 正确率是 0-1 比率；null=不可算，绝不显示 0%。 */
function pctOrDash(rate: number | null): string {
  if (rate === null) return '—'
  return `${Math.round(num(rate) * 100)}%`
}
/** 人均深度 = 事件数 / 触达人数（去入口曝光偏置）。 */
function depthOf(row: BiLearningPrefRow): number {
  return row.memberCount > 0 ? row.eventCount / row.memberCount : 0
}
function repeatRateOf(row: BiLearningPrefRow): number {
  return row.memberCount > 0 ? row.visitCount / row.memberCount : 0
}

/* ------------------------------------------------------------------- 小组件 */
function Empty({ height = 200 }: { height?: number }) {
  return (
    <div
      className="grid place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500"
      style={{ height }}
    >
      暂无数据（埋点未回流；不补 0 冒充）
    </div>
  )
}

/** 小样本 C 级灰徽标：单一权威取 theme.TRUST_LEVEL_COLORS.C。 */
function SmallSamplePill() {
  const color = TRUST_LEVEL_COLORS.C
  return (
    <span
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-1.5 py-px text-[9.5px] font-bold"
      style={{ color, borderColor: alpha(color, 0.4), background: alpha(color, 0.13) }}
      title={`触达 < ${SMALL_SAMPLE} 人，样本不足，仅方向参考（C 级）`}
    >
      ● C 小样本
    </span>
  )
}

export type BiV2LearningPrefPanelProps = {
  flagEnabled: boolean
}

export function BiV2LearningPrefPanel({ flagEnabled }: BiV2LearningPrefPanelProps) {
  const [includeDemo, setIncludeDemo] = useState(false)
  const [data, setData] = useState<BiLearningPreferenceData | null>(null)
  const [loading, setLoading] = useState(flagEnabled)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!flagEnabled) {
      setData(null)
      setLoading(false)
      setError('')
      return
    }
    try {
      setLoading(true)
      setError('')
      const result = await getBiLearningPreference(7, includeDemo, 12)
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : '产品功能偏好加载失败')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [flagEnabled, includeDemo])

  useEffect(() => {
    void load()
  }, [load])

  if (!flagEnabled) {
    return (
      <section className="space-y-4" data-testid="bi-learning-pref">
        <BiV2DataSourceBanner tone="amber">
          BI_LEARNING_PREF_V2_ENABLED 未开启 · 产品功能偏好（P3）看板待灰度通电。接口{' '}
          <code className="font-mono">/api/v1/bi/learning-preference</code> 已就绪，UI 已对齐。
        </BiV2DataSourceBanner>
      </section>
    )
  }

  const modulePref = data?.modulePreference ?? []
  const submodules = data?.submoduleInterest ?? []
  const contentTop = data?.contentTop ?? []
  const featureUsage = data?.featureUsage ?? []
  const practice = data?.practice
  const practiceTopics = practice?.byTopic ?? []
  const hasAny =
    modulePref.length > 0 ||
    submodules.length > 0 ||
    contentTop.length > 0 ||
    featureUsage.length > 0 ||
    num(practice?.answeredCount) > 0

  // KPI 汇总（跨模块无法去重合并，触达取峰值模块作 floor；人均深度用总量比）。
  const peakReach = submodules.reduce((m, r) => Math.max(m, r.memberCount), 0)
  const totalEvents = submodules.reduce((s, r) => s + r.eventCount, 0)
  const totalReachSum = submodules.reduce((s, r) => s + r.memberCount, 0)
  const avgDepth = totalReachSum > 0 ? totalEvents / totalReachSum : 0
  const avgContentRepeat =
    contentTop.length > 0
      ? contentTop.reduce((s, r) => s + r.repeatRate, 0) / contentTop.length
      : 0
  const avgDwellMs =
    submodules.length > 0
      ? submodules.reduce((s, r) => s + r.avgDwellMs, 0) / submodules.length
      : 0

  // 全模块偏好双条（题眼，第一屏）：左=触达人数(member_count)，右=人均深度(repeat_rate)。
  const moduleReachBars: Datum[] = modulePref.map(r => ({
    name: moduleLabel(r.objectType || r.key),
    value: r.memberCount,
  }))
  const moduleDepthBars: Datum[] = modulePref.map(r => ({
    name: moduleLabel(r.objectType || r.key),
    value: Math.round(r.repeatRate * 10) / 10,
  }))
  // 模块兴趣双条（题眼）：左=触达人数，右=人均深度。
  const reachBars: Datum[] = submodules.map(r => ({
    name: objectTypeLabel(r.objectType || r.key),
    value: r.memberCount,
  }))
  const depthBars: Datum[] = submodules.map(r => ({
    name: objectTypeLabel(r.objectType || r.key),
    value: Math.round(depthOf(r) * 10) / 10,
  }))
  // 内容点击/播放 Top：按 event_count（被点击/播放总次数）——"哪个视频被点了多少次"。
  const contentClickBars: Datum[] = contentTop.map(r => ({
    name: `${objectTypeLabel(r.objectType)}·${r.key}`,
    value: r.eventCount,
  }))
  const featureBars: Datum[] = featureUsage.map(r => ({
    name: actionLabel(r.key),
    value: r.memberCount,
  }))
  // 各主题练习热度：按 event_count（该主题练习被做的次数），key=pack_id。
  const topicHeatBars: Datum[] = practiceTopics.map(r => ({
    name: r.key,
    value: r.eventCount,
  }))

  return (
    <section className="space-y-4" data-testid="bi-learning-pref">
      {/* 数据源 / 刷新 banner */}
      <BiV2DataSourceBanner
        tone="sky"
        action={
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-cyan-300/25 bg-cyan-300/10 px-2 py-1 text-cyan-100">
            <input
              type="checkbox"
              checked={includeDemo}
              onChange={e => setIncludeDemo(e.target.checked)}
              className="h-3 w-3 accent-cyan-400"
              aria-label="含演示数据"
            />
            含演示数据
          </label>
        }
      >
        BI_LEARNING_PREF_V2_ENABLED 已开启 · 读取{' '}
        <code className="font-mono">/api/v1/bi/learning-preference</code>（窗口{' '}
        {num(data?.days) || 7} 天）。指标全 C 级 · authority: product_behavior_store。
      </BiV2DataSourceBanner>

      {/* 小样本醒目提示（常驻） */}
      <BiV2DataSourceBanner tone="amber" role="status">
        ⚠ 产品功能偏好当前样本量小，数据为<strong>方向参考</strong>非结论；触达 &lt; {SMALL_SAMPLE}{' '}
        人的行/指标挂灰色可信徽标，请结合人均深度一起看，勿单看触达下结论。
      </BiV2DataSourceBanner>

      {/* demo banner（仅 demoIncluded 时） */}
      {data?.demoIncluded ? (
        <BiV2DataSourceBanner tone="rose" role="alert">
          🧪 当前<strong>含合成演示数据</strong>（生产真实数据待小程序发版埋点通电）。数字仅用于
          UI 走查与布局验收，不代表真实用户行为。
        </BiV2DataSourceBanner>
      ) : null}

      {loading ? (
        <CockpitBg className="p-6">
          <div className="grid h-40 place-items-center text-sm text-slate-400">加载中…</div>
        </CockpitBg>
      ) : error ? (
        <BiV2DataSourceBanner tone="rose" role="alert">
          {error}
        </BiV2DataSourceBanner>
      ) : !hasAny ? (
        <CockpitBg className="p-6">
          <Empty height={220} />
        </CockpitBg>
      ) : (
        <CockpitBg className="p-4 md:p-5">
          <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#E8915A]/90">
            <GraduationCap className="h-3.5 w-3.5" />
            Product Feature Preference Cockpit
          </div>
          <h2 className="mb-3 text-lg font-black text-slate-100">产品功能偏好</h2>

          {/* ---------- 全模块偏好双条（题眼，第一屏最上） ---------- */}
          {modulePref.length ? (
            <>
              <SectionLabel icon={<LayoutGrid className="h-4 w-4" />}>
                产品模块偏好 · 触达 × 深度
              </SectionLabel>
              <div className="mb-3 rounded-xl border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2 text-[11px] leading-relaxed text-amber-100/90">
                全产品功能偏好总览：<strong>learning / chat / practice / first_run / assessment /
                history / notebook / learning_report / profile</strong> 等所有被监测模块都在这（login
                已排除）。<strong>左=谁被点得多（触达人数）</strong>，
                <strong>右=谁被深度使用（人均深度）</strong>——回答"哪个产品模块最受欢迎、哪个被深度使用"。
              </div>
              <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
                <CockpitPanel
                  glow
                  title="模块触达（去重人数）"
                  hint="进入某产品模块的去重人数，降序；login 已排除"
                  icon={<LayoutGrid className="h-4 w-4" />}
                >
                  {moduleReachBars.length ? (
                    <CockpitBar data={moduleReachBars} color={SERIES_COLORS[0]} />
                  ) : (
                    <Empty />
                  )}
                </CockpitPanel>
                <CockpitPanel
                  title="模块人均深度（repeat_rate）"
                  hint="后端 repeat_rate 口径（人均复用深度）；标签取整，条长为真实比值"
                  icon={<LineChart className="h-4 w-4" />}
                >
                  {moduleDepthBars.length ? (
                    <CockpitBar data={moduleDepthBars} color={SERIES_COLORS[1]} />
                  ) : (
                    <Empty />
                  )}
                </CockpitPanel>
              </div>
              {/* 小样本模块灰徽标明细（member_count 小的模块标灰） */}
              <div className="mb-4 flex flex-wrap gap-2 text-[11px] text-slate-300">
                {modulePref.map(r => (
                  <span
                    key={r.key}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] px-2 py-1"
                  >
                    <span className="font-semibold text-slate-200">
                      {moduleLabel(r.objectType || r.key)}
                    </span>
                    <span className="tabular-nums text-slate-400">
                      {fmtInt(r.memberCount)} 人 · 深度 {fmtRatio(r.repeatRate)}
                    </span>
                    {r.memberCount < SMALL_SAMPLE ? <SmallSamplePill /> : null}
                  </span>
                ))}
              </div>
            </>
          ) : null}

          {/* ---------- KPI 行 ---------- */}
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <CockpitKpi
              label="学习触达人数"
              value={fmtInt(peakReach)}
              tone="cyan"
              icon={<GraduationCap className="h-4 w-4" />}
              sub="峰值子模块去重人数（跨模块不可合并去重）"
            />
            <CockpitKpi
              label="人均深度"
              value={fmtRatio(avgDepth)}
              unit="次/人"
              tone="teal"
              sub="总事件 / 总触达人次"
            />
            <CockpitKpi
              label="内容复看均值"
              value={fmtRatio(avgContentRepeat)}
              unit="×"
              tone="amber"
              icon={<Repeat className="h-4 w-4" />}
              sub="Top 内容复看率均值"
            />
            <CockpitKpi
              label="练习答题量"
              value={fmtInt(practice?.answeredCount)}
              tone="violet"
              sub="随堂练 / 复测 / 闯关"
            />
            <CockpitKpi
              label="练习正确率"
              value={pctOrDash(practice?.accuracy ?? null)}
              tone="emerald"
              sub={
                practice?.accuracy === null || practice?.accuracy === undefined
                  ? '无作答，不可算（不补 0）'
                  : `${fmtInt(practice?.correctCount)} / ${fmtInt(practice?.answeredCount)} 正确`
              }
            />
            <CockpitKpi
              label="平均停留"
              value={fmtRatio(avgDwellMs / 1000)}
              unit="s"
              tone="rose"
              icon={<LineChart className="h-4 w-4" />}
              sub="停留时长口径（完播率不可采）"
            />
          </div>

          {/* ---------- 模块兴趣双条（题眼，第一屏） ---------- */}
          <SectionLabel icon={<Layers className="h-4 w-4" />}>模块兴趣 · 触达 × 深度</SectionLabel>
          <div className="mb-3 rounded-xl border border-amber-300/20 bg-amber-300/[0.06] px-3 py-2 text-[11px] leading-relaxed text-amber-100/90">
            怎么读：<strong>左=谁被点得多（触达）</strong>，<strong>右=谁被玩得深（人均深度）</strong>。
            左高右低 = 首页位置带来的<strong>泡沫</strong>（点进去就走）；左低右高 =
            被埋没的<strong>金矿</strong>（少数人反复深用）。两条并看才有结论，单看触达=入口位置榜。
          </div>
          <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <CockpitPanel
              glow
              title="子模块触达（去重人数）"
              hint="进入某学习子模块的去重人数，降序"
              icon={<Layers className="h-4 w-4" />}
            >
              {reachBars.length ? <CockpitBar data={reachBars} /> : <Empty />}
            </CockpitPanel>
            <CockpitPanel
              title="子模块人均深度（事件/人）"
              hint="去入口曝光偏置；标签取整，条长为真实比值"
              icon={<LineChart className="h-4 w-4" />}
            >
              {depthBars.length ? <CockpitBar data={depthBars} color="#F2B85C" /> : <Empty />}
            </CockpitPanel>
          </div>

          {/* ---------- 内容点击/播放 Top + 练习正确率 ---------- */}
          <SectionLabel icon={<MousePointerClick className="h-4 w-4" />}>
            内容点击/播放 · 复看 · 练习正确率
          </SectionLabel>
          <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <CockpitPanel
              title="教学内容点击/播放 Top"
              hint="微课/考点卡/看穿讲解被点击/播放总次数（观看=停留时长口径，非完播率）"
              icon={<MousePointerClick className="h-4 w-4" />}
            >
              {contentClickBars.length ? (
                <div className="space-y-3">
                  {/* 主条=点击/播放次数（"哪个视频被点了多少次"一眼可见） */}
                  <CockpitBar data={contentClickBars} color={SERIES_COLORS[0]} />
                  <div className="overflow-x-auto text-[11px] text-slate-300">
                    <div className="grid min-w-[420px] grid-cols-[1fr_auto_auto_auto] gap-2 border-b border-white/10 px-2 py-1 text-slate-500">
                      <span>内容</span>
                      <span className="text-right">点击/播放</span>
                      <span className="text-right">观看人数</span>
                      <span className="text-right">复看率</span>
                    </div>
                    {contentTop.map(r => (
                      <div
                        key={r.key}
                        className="grid min-w-[420px] grid-cols-[1fr_auto_auto_auto] gap-2 border-b border-white/5 px-2 py-1.5"
                      >
                        <span className="flex min-w-0 items-center gap-1.5">
                          <span className="truncate">
                            {objectTypeLabel(r.objectType)}·{r.key}
                          </span>
                          {r.memberCount < SMALL_SAMPLE ? <SmallSamplePill /> : null}
                        </span>
                        <span className="text-right font-bold tabular-nums text-slate-100">
                          {fmtInt(r.eventCount)} 次
                        </span>
                        <span className="text-right tabular-nums">{fmtInt(r.memberCount)}</span>
                        <span className="text-right tabular-nums">{fmtRatio(r.repeatRate)}×</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <Empty />
              )}
            </CockpitPanel>
            <CockpitPanel
              title="练习正确率（按对象类型）"
              hint="retest_item_answered 口径，与 V1 判分/turns 不同源不可混"
              icon={<Sparkles className="h-4 w-4" />}
            >
              {practice && (practice.byObjectType.length || practice.answeredCount > 0) ? (
                <div className="space-y-2 text-[12px] text-slate-200">
                  <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
                    <div className="text-slate-500">全部练习</div>
                    <div className="mt-1 flex items-baseline gap-2">
                      <span className="text-lg font-bold text-white">
                        {pctOrDash(practice.accuracy)}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {fmtInt(practice.correctCount)} / {fmtInt(practice.answeredCount)} 正确
                      </span>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <div className="grid min-w-[320px] grid-cols-[1fr_auto_auto] gap-2 border-b border-white/10 px-2 py-1 text-[11px] text-slate-500">
                      <span>对象类型</span>
                      <span className="text-right">答题量</span>
                      <span className="text-right">正确率</span>
                    </div>
                    {practice.byObjectType.map(row => (
                      <div
                        key={row.objectType}
                        className="grid min-w-[320px] grid-cols-[1fr_auto_auto] gap-2 border-b border-white/5 px-2 py-1.5 text-[11px]"
                      >
                        <span className="truncate">{objectTypeLabel(row.objectType)}</span>
                        <span className="text-right tabular-nums">{fmtInt(row.answeredCount)}</span>
                        <span className="text-right tabular-nums">{pctOrDash(row.accuracy)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <Empty />
              )}
            </CockpitPanel>
          </div>

          {/* ---------- 各主题练习热度 ---------- */}
          {topicHeatBars.length ? (
            <>
              <SectionLabel icon={<Flame className="h-4 w-4" />}>各主题练习热度</SectionLabel>
              <div className="mb-4">
                <CockpitPanel
                  title="各主题(pack)练习热度"
                  hint="按该主题练习被做的次数（event_count），key=pack_id——回答'哪个主题的练习被点开/做了多少次'"
                  icon={<Flame className="h-4 w-4" />}
                >
                  <div className="space-y-3">
                    <CockpitBar data={topicHeatBars} color={SERIES_COLORS[3]} />
                    <div className="overflow-x-auto text-[11px] text-slate-300">
                      <div className="grid min-w-[360px] grid-cols-[1fr_auto_auto] gap-2 border-b border-white/10 px-2 py-1 text-slate-500">
                        <span>主题 pack_id</span>
                        <span className="text-right">练习次数</span>
                        <span className="text-right">练习人数</span>
                      </div>
                      {practiceTopics.map(r => (
                        <div
                          key={r.key}
                          className="grid min-w-[360px] grid-cols-[1fr_auto_auto] gap-2 border-b border-white/5 px-2 py-1.5"
                        >
                          <span className="flex min-w-0 items-center gap-1.5">
                            <span className="truncate font-mono">{r.key}</span>
                            {r.memberCount < SMALL_SAMPLE ? <SmallSamplePill /> : null}
                          </span>
                          <span className="text-right font-bold tabular-nums text-slate-100">
                            {fmtInt(r.eventCount)} 次
                          </span>
                          <span className="text-right tabular-nums">{fmtInt(r.memberCount)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </CockpitPanel>
              </div>
            </>
          ) : null}

          {/* ---------- 驾驶舱功能偏好（可选副屏） ---------- */}
          {featureBars.length ? (
            <>
              <SectionLabel icon={<Sparkles className="h-4 w-4" />}>功能偏好</SectionLabel>
              <div className="mb-4">
                <CockpitPanel title="功能动作触达" hint="view/open_detail/start_training… 按触达人数">
                  <CockpitBar data={featureBars} color="#D86C57" />
                </CockpitPanel>
              </div>
            </>
          ) : null}

          {/* ---------- 明细表 ---------- */}
          <SectionLabel icon={<BookOpen className="h-4 w-4" />}>子模块明细 · 归一化比率</SectionLabel>
          <div className="overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.03]">
            <div className="grid min-w-[880px] grid-cols-[1.2fr_repeat(9,1fr)] gap-2 border-b border-white/10 px-3 py-2 text-[11px] text-slate-500">
              <span>子模块</span>
              <span className="text-right">触达</span>
              <span className="text-right">访问</span>
              <span className="text-right">事件</span>
              <span className="text-right">深度</span>
              <span className="text-right">复访</span>
              <span className="text-right">答题</span>
              <span className="text-right">正确率</span>
              <span className="text-right">复看率</span>
              <span className="text-right">平均停留</span>
            </div>
            {submodules.map(r => (
              <div
                key={r.key}
                className="grid min-w-[880px] grid-cols-[1.2fr_repeat(9,1fr)] gap-2 border-b border-white/5 px-3 py-2 text-[11px] text-slate-200"
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className="truncate">{objectTypeLabel(r.objectType || r.key)}</span>
                  {r.memberCount < SMALL_SAMPLE ? <SmallSamplePill /> : null}
                </span>
                <span className="text-right tabular-nums">{fmtInt(r.memberCount)}</span>
                <span className="text-right tabular-nums">{fmtInt(r.visitCount)}</span>
                <span className="text-right tabular-nums">{fmtInt(r.eventCount)}</span>
                <span className="text-right tabular-nums">{fmtRatio(depthOf(r))}</span>
                <span className="text-right tabular-nums">{fmtRatio(repeatRateOf(r))}</span>
                <span className="text-right tabular-nums">{fmtInt(r.answeredCount)}</span>
                <span className="text-right tabular-nums">{pctOrDash(r.accuracy)}</span>
                <span className="text-right tabular-nums">{fmtRatio(r.repeatRate)}×</span>
                <span className="text-right tabular-nums">{fmtRatio(r.avgDwellMs / 1000)}s</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[10.5px] leading-relaxed text-slate-500">
            口径：深度=事件/触达，复访=访问/触达；观看/复看均为<strong>停留时长口径</strong>
            （completion_source={data?.completionSource || 'dwell'}，完播率受 web-view
            沙箱限制不可采，故不呈现完播率%）。完成/快退口径埋点待小程序发版通电。全部指标 C
            级，低触达行仅方向参考。
          </p>
        </CockpitBg>
      )}
    </section>
  )
}
