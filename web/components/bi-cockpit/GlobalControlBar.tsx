/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 驾驶舱全局控制条（方向 A 轴①）：时间范围 7/30/90 天切换。
 *
 * 受控组件：窗口状态由数据获取的 owner（BiV2OverviewPanel）持有，
 * 控制条不自建第二套窗口状态。环比对比开关为 P3 占位（disabled）。
 */
import { CalendarRange } from 'lucide-react'
import { COCKPIT, SERIES_COLORS, alpha } from './theme'

export const COCKPIT_WINDOW_OPTIONS = [7, 30, 90] as const
export type CockpitWindowDays = (typeof COCKPIT_WINDOW_OPTIONS)[number]

export function GlobalControlBar({
  days,
  onDaysChange,
  busy,
}: {
  days: CockpitWindowDays
  onDaysChange: (days: CockpitWindowDays) => void
  /** 数据加载中时禁用切换，避免连点产生竞态请求 */
  busy?: boolean
}) {
  return (
    <div
      className="mb-4 flex flex-wrap items-center gap-2.5 rounded-2xl border px-3 py-2"
      style={{ borderColor: COCKPIT.border, background: COCKPIT.bgPanel }}
    >
      <span
        className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide"
        style={{ color: COCKPIT.textMuted }}
      >
        <CalendarRange className="h-3.5 w-3.5" aria-hidden />
        时间范围
      </span>

      <div
        className="inline-flex overflow-hidden rounded-xl border"
        style={{ borderColor: COCKPIT.border }}
        role="group"
        aria-label="时间范围切换"
      >
        {COCKPIT_WINDOW_OPTIONS.map(value => {
          const active = days === value
          return (
            <button
              key={value}
              type="button"
              disabled={busy}
              aria-pressed={active}
              onClick={() => onDaysChange(value)}
              className="px-3 py-1 text-[11px] font-black tabular-nums transition disabled:cursor-not-allowed disabled:opacity-60"
              style={
                active
                  ? {
                      color: '#1a120c',
                      background: `linear-gradient(135deg, ${SERIES_COLORS[0]}, ${SERIES_COLORS[1]})`,
                    }
                  : { color: COCKPIT.textMuted, background: 'transparent' }
              }
            >
              {value} 天
            </button>
          )
        })}
      </div>

      {/* 环比开关：P3 接入前仅占位（title 即 tooltip） */}
      <span className="ml-auto inline-flex" title="P3 接入">
        <button
          type="button"
          disabled
          aria-disabled
          className="cursor-not-allowed rounded-xl border px-2.5 py-1 text-[10px] font-bold opacity-60"
          style={{ color: COCKPIT.textFaint, borderColor: alpha(COCKPIT.textFaint, 0.35) }}
        >
          环比对比 · P3
        </button>
      </span>
    </div>
  )
}
