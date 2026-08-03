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
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  if (bars.length === 0) {
    return <div className="mt-2 h-10" />
  }

  const activeBar = activeIndex === null ? null : bars[activeIndex] ?? null
  const activePosition =
    activeIndex === null ? 50 : ((activeIndex + 0.5) / Math.max(bars.length, 1)) * 100

  return (
    <div
      className="relative mt-2 h-16"
      onMouseLeave={() => setActiveIndex(null)}
      aria-label="每日新增注册趋势"
    >
      <div className="absolute inset-x-0 bottom-0 flex h-10 items-end gap-[2px]">
        {bars.map((bar, index) => {
          // 高度线性映射（不做 sqrt 之类的美化缩放，免得把 3 人看成接近 100 人），
          // 但非零最低给 18% 高度：单个爆发日不该把其它有注册的日子压成看不见。
          // 0 只画一条 2px 底线 —— "那天真的没人注册"和"没有那天"要能分辨。
          const ratio = peak > 0 ? bar.count / peak : 0
          const isActive = activeIndex === index
          return (
            <span
              key={`${bar.label}-${index}`}
              data-testid={`bi-member-new-registration-bar-${index}`}
              role="img"
              tabIndex={0}
              aria-label={`${formatBarLabel(bar.label)}，${bar.count} 人`}
              aria-describedby={isActive ? 'bi-member-new-registration-tooltip' : undefined}
              onMouseEnter={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
              onBlur={() => setActiveIndex(null)}
              className={`group flex h-full min-w-[2px] flex-1 cursor-crosshair items-end outline-none transition-opacity duration-200 ${
                activeIndex !== null && !isActive ? 'opacity-45' : 'opacity-100'
              }`}
            >
              <span
                aria-hidden
                className="w-full origin-bottom rounded-sm transition-[height,transform,filter,box-shadow] duration-300 ease-out group-hover:scale-y-110 group-hover:brightness-125 group-hover:drop-shadow-[0_0_6px_rgba(240,168,120,0.7)] group-focus-visible:scale-y-110 group-focus-visible:brightness-125 group-focus-visible:drop-shadow-[0_0_6px_rgba(240,168,120,0.7)]"
                style={{
                  height: bar.count > 0 ? `${Math.max(ratio * 100, 18)}%` : '2px',
                  background:
                    bar.count > 0
                      ? `linear-gradient(180deg, ${SERIES_COLORS[0]}, ${alpha(SERIES_COLORS[0], 0.35)})`
                      : 'rgba(255,255,255,0.12)',
                }}
              />
            </span>
          )
        })}
      </div>

      <div
        id="bi-member-new-registration-tooltip"
        data-testid="bi-member-new-registration-tooltip"
        role="tooltip"
        aria-hidden={!activeBar}
        className={`pointer-events-none absolute top-0 z-20 -translate-x-1/2 whitespace-nowrap rounded-lg border border-[#F0A878]/55 bg-[#0d0907] px-2.5 py-1.5 text-xs font-bold shadow-[0_8px_24px_rgba(0,0,0,0.55)] transition-[left,opacity,transform] duration-150 ease-out ${
          activeBar
            ? 'translate-y-0 scale-100 opacity-100'
            : 'translate-y-1 scale-95 opacity-0'
        }`}
        style={{ left: `clamp(4.75rem, ${activePosition}%, calc(100% - 4.75rem))` }}
      >
        <span className="text-slate-50">{activeBar ? formatBarLabel(activeBar.label) : '—'}</span>
        <span className="mx-1.5 text-slate-500">·</span>
        <span className="text-sm font-black tabular-nums text-[#F0A878]">
          {activeBar?.count.toLocaleString() ?? 0} 人
        </span>
      </div>
    </div>
  )
}

function formatBarLabel(label: string): string {
  return label
    .split(' ~ ')
    .map(value => {
      const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
      return match ? `${match[1]}年${Number(match[2])}月${Number(match[3])}日` : value
    })
    .join(' 至 ')
}
