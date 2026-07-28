import test from 'node:test'
import assert from 'node:assert/strict'

import {
  REGISTRATION_WINDOW_PRESETS,
  clampWindowDays,
  compressSeries,
  excludedMemberCount,
  previousWindowSum,
  sumWindow,
  windowDelta,
  windowSeries,
  type NewRegistrationTrend,
} from '../lib/member-registration-window.ts'

function trendOf(daily: number[], endDate = '2026-06-30'): NewRegistrationTrend {
  const end = new Date(`${endDate}T00:00:00Z`)
  const start = new Date(end.getTime() - (daily.length - 1) * 86_400_000)
  return {
    start_date: start.toISOString().slice(0, 10),
    end_date: endDate,
    window_days: daily.length,
    daily_counts: daily,
  }
}

// 1,2,3,4,5,6,7,8,9,10 —— 最后一项是今天
const TEN_DAYS = trendOf([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

test('运营窗口固定为 1、3、7、30 天', () => {
  assert.deepEqual(
    REGISTRATION_WINDOW_PRESETS.map(item => item.days),
    [1, 3, 7, 30]
  )
})

test('窗口总数是每日序列的后缀和（与后端 _sum_registration_window 同口径）', () => {
  assert.equal(sumWindow(TEN_DAYS, 1), 10)
  assert.equal(sumWindow(TEN_DAYS, 3), 27) // 8+9+10
  assert.equal(sumWindow(TEN_DAYS, 10), 55)
})

test('窗口超出序列长度时夹到序列长度，不越界也不返回 NaN', () => {
  assert.equal(sumWindow(TEN_DAYS, 999), 55)
  assert.equal(clampWindowDays(999, TEN_DAYS), 10)
  assert.equal(clampWindowDays(0, TEN_DAYS), 1)
  assert.equal(clampWindowDays(-5, TEN_DAYS), 1)
  assert.equal(clampWindowDays(Number.NaN, TEN_DAYS), 1)
  assert.equal(clampWindowDays(7, TEN_DAYS), 7)
})

test('序列缺失时一切归零，不伪造数字', () => {
  assert.equal(sumWindow(null, 30), 0)
  assert.equal(sumWindow(undefined, 30), 0)
  assert.equal(sumWindow(trendOf([]), 30), 0)
  assert.deepEqual(windowSeries(null, 7), [])
  assert.equal(previousWindowSum(null, 7), null)
  assert.equal(windowDelta(null, 7), null)
})

test('窗口序列带真实日期，最后一项是 end_date', () => {
  const series = windowSeries(TEN_DAYS, 3)
  assert.deepEqual(series, [
    { date: '2026-06-28', count: 8 },
    { date: '2026-06-29', count: 9 },
    { date: '2026-06-30', count: 10 },
  ])
})

test('环比读上一个等长周期', () => {
  assert.equal(previousWindowSum(TEN_DAYS, 3), 5 + 6 + 7)
  const delta = windowDelta(TEN_DAYS, 3)
  assert.ok(delta)
  assert.equal(delta.previous, 18)
  assert.equal(delta.up, true)
  assert.equal(Math.round((delta.ratio ?? 0) * 100), 50) // 27 vs 18
})

test('上一周期被序列起点截断时不算环比 —— 半个周期比整个周期是假环比', () => {
  assert.equal(previousWindowSum(TEN_DAYS, 6), null)
  assert.equal(windowDelta(TEN_DAYS, 6), null)
})

test('上一周期为 0 时不报无穷增长', () => {
  const delta = windowDelta(trendOf([0, 0, 3, 4]), 2)
  assert.ok(delta)
  assert.equal(delta.previous, 0)
  assert.equal(delta.ratio, null)
  assert.equal(delta.up, true)
})

test('迷你柱线聚合是求和，柱子总和仍等于窗口总数', () => {
  const series = windowSeries(trendOf(Array.from({ length: 365 }, () => 2)), 365)
  const bars = compressSeries(series, 60)
  assert.equal(bars.length, 60)
  assert.equal(
    bars.reduce((total, bar) => total + bar.count, 0),
    730
  )
})

test('序列不长于柱数上限时按天原样渲染', () => {
  const bars = compressSeries(windowSeries(TEN_DAYS, 10), 60)
  assert.equal(bars.length, 10)
  assert.equal(bars[bars.length - 1].label, '2026-06-30')
})

test('注册时间缺失/未来的会员单独计数，供界面标注为什么数字可能偏低', () => {
  assert.equal(
    excludedMemberCount({
      ...TEN_DAYS,
      undated_member_count: 2,
      future_dated_member_count: 1,
      before_window_member_count: 9,
    }),
    3
  )
  assert.equal(excludedMemberCount(TEN_DAYS), 0)
  assert.equal(excludedMemberCount(null), 0)
})
