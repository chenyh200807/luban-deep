/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 新增注册卡：一个可自选窗口的大数字 + 每日新增迷你柱线 + 环比。
 *
 * 切窗口不发请求 —— 后端一次给了近 365 天的每日数组，这里只是对同一数组求后缀和。
 * 迷你柱线是纯 CSS，不挂 ECharts 实例（首屏体积/渲染成本已经在治理中）。
 */
import { useMemo, useState } from 'react'
import { UserPlus } from 'lucide-react'
import {
  DEFAULT_REGISTRATION_WINDOW_DAYS,
  REGISTRATION_WINDOW_PRESETS,
  axisLength,
  clampWindowDays,
  compressSeries,
  excludedMemberCount,
  sumWindow,
  windowDelta,
  windowSeries,
  type NewRegistrationTrend,
} from '@/lib/member-registration-window'
import { COCKPIT, SERIES_COLORS, alpha } from './theme'

const MAX_BARS = 60

export function NewRegistrationCard({
  trend,
  operationalStartAt,
  className = '',
}: {
  trend: NewRegistrationTrend | null | undefined
  /** BI 运营口径起点(ISO)。窗口跨过它时要说明早期的 0 是没数据，不是没人注册。 */
  operationalStartAt?: string
  className?: string
}) {
  const [presetDays, setPresetDays] = useState(DEFAULT_REGISTRATION_WINDOW_DAYS)

  const axis = axisLength(trend)
  const days = clampWindowDays(presetDays, trend)

  const { total, bars, peak, delta, series } = useMemo(() => {
    const rows = windowSeries(trend, days)
    const compressed = compressSeries(rows, MAX_BARS)
    return {
      series: rows,
      total: sumWindow(trend, days),
      bars: compressed,
      peak: compressed.reduce((max, item) => Math.max(max, item.count), 0),
      delta: windowDelta(trend, days),
    }
  }, [trend, days])

  const excluded = excludedMemberCount(trend)
  const hasAxis = axis > 0
  const windowStart = series[0]?.date ?? ''
  const operationalStartDate = String(operationalStartAt ?? '').slice(0, 10)
  // 窗口起点早于 BI 运营口径起点时，前半段的 0 是"没有数据"而不是"没人注册"。
  const predatesOperationalStart =
    /^\d{4}-\d{2}-\d{2}$/.test(operationalStartDate) &&
    windowStart !== '' &&
    windowStart < operationalStartDate

  return (
    <div
      data-testid="bi-member-new-registration-card"
      className={`relative overflow-hidden rounded-2xl border p-4 ${className}`}
      style={{
        borderColor: 'rgba(232,145,90,0.4)',
        background: 'linear-gradient(150deg, rgba(40,28,20,0.7), rgba(24,16,11,0.5))',
      }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full opacity-40 blur-xl"
        style={{ background: alpha(SERIES_COLORS[0], 0.5) }}
      />

      <div className="relative z-10 flex items-start justify-between gap-2">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          <UserPlus className="h-3.5 w-3.5" style={{ color: COCKPIT.accentBright }} />
          新增注册
        </span>
        <div className="flex items-center gap-1.5">
          <label className="sr-only" htmlFor="new-registration-window">
            新增注册统计窗口
          </label>
          <select
            id="new-registration-window"
            data-testid="bi-member-new-registration-window"
            className="rounded-lg border border-white/15 bg-black/30 px-2 py-1 text-[11px] font-semibold text-slate-200 outline-none focus:border-[#E8915A]/60"
            value={String(presetDays)}
            onChange={event => setPresetDays(Number(event.target.value))}
            disabled={!hasAxis}
          >
            {REGISTRATION_WINDOW_PRESETS.map(preset => (
              <option key={preset.days} value={String(preset.days)}>
                {preset.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {hasAxis ? (
        <>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span
              data-testid="bi-member-new-registration-total"
              className="text-3xl font-black tabular-nums"
              style={{ color: '#F0A878', textShadow: `0 0 18px ${alpha(SERIES_COLORS[0], 0.5)}` }}
            >
              {total.toLocaleString()}
            </span>
            <span className="text-xs font-bold text-slate-400">人</span>
            <span className="ml-1 text-[11px] text-slate-500">
              {days === 1 ? '今日' : `近 ${days} 天`}
            </span>
          </div>

          <MiniBars bars={bars} peak={peak} />

          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            {delta ? (
              delta.ratio === null ? (
                <span className="text-slate-500">
                  上一周期 {delta.previous.toLocaleString()} 人
                </span>
              ) : (
                <span
                  data-testid="bi-member-new-registration-delta"
                  className={`font-bold ${delta.up ? 'text-emerald-300' : 'text-rose-300'}`}
                >
                  {delta.up ? '▲' : '▼'} {Math.abs(Math.round(delta.ratio * 100))}%
                  <span className="ml-1 font-normal text-slate-500">
                    环比上一周期（{delta.previous.toLocaleString()} 人）
                  </span>
                </span>
              )
            ) : (
              <span className="text-slate-500">上一周期数据不足，暂不计算环比</span>
            )}
            <span className="text-slate-600">
              {series[0]?.date} ~ {series[series.length - 1]?.date}
            </span>
          </div>

          {predatesOperationalStart && (
            <p data-testid="bi-member-new-registration-predates-note" className="mt-1 text-[11px] text-amber-200/80">
              BI 运营口径自 {operationalStartDate} 起，该日期之前的 0 是没有数据，不是没有新注册。
            </p>
          )}

          {excluded > 0 && (
            <p className="mt-1 text-[11px] text-amber-200/80">
              另有 {excluded} 位会员注册时间缺失或异常，未计入任何日期桶。
            </p>
          )}
        </>
      ) : (
        <div className="mt-3 grid h-20 place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500">
          新增注册序列不可用
        </div>
      )}
    </div>
  )
}

function MiniBars({ bars, peak }: { bars: Array<{ label: string; count: number }>; peak: number }) {
  if (bars.length === 0) {
    return <div className="mt-2 h-10" />
  }
  return (
    <div className="mt-2 flex h-12 items-end gap-[2px]" aria-hidden>
      {bars.map((bar, index) => {
        // 高度线性映射（不做 sqrt 之类的美化缩放，免得把 3 人看成接近 100 人），
        // 但非零最低给 18% 高度：单个爆发日不该把其它有注册的日子压成看不见。
        // 0 只画一条 2px 底线 —— "那天真的没人注册"和"没有那天"要能分辨。
        const ratio = peak > 0 ? bar.count / peak : 0
        return (
          <span
            key={`${bar.label}-${index}`}
            title={`${bar.label}：${bar.count} 人`}
            className="min-w-[2px] flex-1 rounded-sm"
            style={{
              height: bar.count > 0 ? `${Math.max(ratio * 100, 18)}%` : '2px',
              background:
                bar.count > 0
                  ? `linear-gradient(180deg, ${SERIES_COLORS[0]}, ${alpha(SERIES_COLORS[0], 0.35)})`
                  : 'rgba(255,255,255,0.12)',
            }}
          />
        )
      })}
    </div>
  )
}
