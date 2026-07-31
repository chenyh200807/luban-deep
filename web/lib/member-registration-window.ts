/**
 * 新增注册窗口的派生逻辑。
 *
 * 后端 `/bi/member/overview` 一次返回近 365 天的每日新增数组
 * (`dashboard.new_registration_trend`)，运营切窗口只是对同一个数组求后缀和，
 * 不再发请求、也不重拉整个 member overview 大 payload。
 *
 * 口径与后端 `_sum_registration_window` 一致：按服务时区(UTC+8)的自然日分桶，
 * 与会员表格的 registered_from / registered_to 筛选同源，所以 KPI 数字点进去
 * 筛出来的行数对得上。这里不做第二套算法。
 */

export type NewRegistrationTrend = {
  start_date: string
  end_date: string
  window_days: number
  daily_counts: number[]
  undated_member_count?: number
  before_window_member_count?: number
  future_dated_member_count?: number
  timezone_offset_minutes?: number
}

export type RegistrationWindowPreset = {
  days: number
  label: string
}

/** 运营首屏允许切换的固定窗口。 */
export const REGISTRATION_WINDOW_PRESETS: RegistrationWindowPreset[] = [
  { days: 1, label: '近 1 天' },
  { days: 3, label: '近 3 天' },
  { days: 7, label: '近 7 天' },
  { days: 30, label: '近 30 天' },
]

export const DEFAULT_REGISTRATION_WINDOW_DAYS = 30

export function axisLength(trend: NewRegistrationTrend | null | undefined): number {
  return trend?.daily_counts?.length ?? 0
}

/** 把用户输入的天数夹到 [1, 序列长度]；序列缺失时退回 1，绝不返回 0 或负数。 */
export function clampWindowDays(days: number, trend: NewRegistrationTrend | null | undefined): number {
  const axis = axisLength(trend)
  const parsed = Math.floor(Number(days))
  if (!Number.isFinite(parsed) || parsed < 1) return 1
  if (axis > 0) return Math.min(parsed, axis)
  return parsed
}

/** 窗口内每日新增，按日期升序；最后一项是今天。 */
export function windowSeries(
  trend: NewRegistrationTrend | null | undefined,
  days: number
): Array<{ date: string; count: number }> {
  const counts = trend?.daily_counts
  if (!counts || counts.length === 0) return []
  const span = Math.max(1, Math.min(Math.floor(days), counts.length))
  const slice = counts.slice(counts.length - span)
  const end = parseIsoDate(trend?.end_date)
  return slice.map((count, index) => ({
    date: end ? isoDateAfter(end, index - (span - 1)) : '',
    count: Number(count) || 0,
  }))
}

/** 窗口内新增总数 —— 与后端 `_sum_registration_window` 同一口径。 */
export function sumWindow(trend: NewRegistrationTrend | null | undefined, days: number): number {
  return windowSeries(trend, days).reduce((total, item) => total + item.count, 0)
}

/**
 * 上一个等长周期的新增总数，用于环比。
 * 序列不够长（上一周期被窗口起点截断）时返回 null —— 半个周期跟整个周期比是假环比。
 */
export function previousWindowSum(
  trend: NewRegistrationTrend | null | undefined,
  days: number
): number | null {
  const counts = trend?.daily_counts
  if (!counts || counts.length === 0) return null
  const span = Math.max(1, Math.min(Math.floor(days), counts.length))
  const end = counts.length - span
  const start = end - span
  if (start < 0) return null
  return counts.slice(start, end).reduce((total, value) => total + (Number(value) || 0), 0)
}

export type WindowDelta = {
  /** 上一周期总数；不可比时为 null。 */
  previous: number
  /** 变化比例，previous 为 0 时为 null（除以 0 不是 +∞ 增长）。 */
  ratio: number | null
  up: boolean
}

export function windowDelta(
  trend: NewRegistrationTrend | null | undefined,
  days: number
): WindowDelta | null {
  const previous = previousWindowSum(trend, days)
  if (previous === null) return null
  const current = sumWindow(trend, days)
  if (previous === 0) {
    return { previous, ratio: null, up: current > 0 }
  }
  const ratio = (current - previous) / previous
  return { previous, ratio, up: ratio >= 0 }
}

/**
 * 把过长的序列等分聚合到至多 maxBars 根柱子，避免 365 根柱糊成一片。
 * 聚合是求和（不是抽样），所以柱子总和仍等于窗口总数。
 */
export function compressSeries(
  series: Array<{ date: string; count: number }>,
  maxBars: number
): Array<{ label: string; count: number }> {
  if (series.length === 0) return []
  if (maxBars < 1 || series.length <= maxBars) {
    return series.map(item => ({ label: item.date, count: item.count }))
  }
  const bucketCount = maxBars
  const out: Array<{ label: string; count: number }> = []
  for (let index = 0; index < bucketCount; index += 1) {
    const from = Math.floor((index * series.length) / bucketCount)
    const to = Math.floor(((index + 1) * series.length) / bucketCount)
    const slice = series.slice(from, Math.max(to, from + 1))
    const count = slice.reduce((total, item) => total + item.count, 0)
    const first = slice[0]?.date ?? ''
    const last = slice[slice.length - 1]?.date ?? first
    out.push({ label: first === last ? first : `${first} ~ ${last}`, count })
  }
  return out
}

/** 窗口内被排除的成员（注册时间缺失/未来/超出序列），用于说明数字为什么可能偏低。 */
export function excludedMemberCount(trend: NewRegistrationTrend | null | undefined): number {
  if (!trend) return 0
  return (
    (Number(trend.undated_member_count) || 0) + (Number(trend.future_dated_member_count) || 0)
  )
}

function parseIsoDate(value: string | null | undefined): Date | null {
  const raw = String(value ?? '').trim()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null
  const parsed = new Date(`${raw}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function isoDateAfter(base: Date, offsetDays: number): string {
  const shifted = new Date(base.getTime() + offsetDays * 86_400_000)
  return shifted.toISOString().slice(0, 10)
}
