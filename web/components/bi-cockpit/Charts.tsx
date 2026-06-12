'use client'

/**
 * 驾驶舱可复用图表组件。每个组件只接收朴素数据，内部套用深色大屏主题。
 * 数据契约统一为 { name, value }，便于直接喂 *_breakdown 这类后端字段。
 */
import type { EChartsOption } from 'echarts'
import { EChart } from './EChart'
import {
  COCKPIT,
  COCKPIT_FONT,
  COCKPIT_TOOLTIP,
  SEMANTIC,
  SERIES_COLORS,
  alpha,
  vGradient,
} from './theme'

export type Datum = { name: string; value: number; color?: string }

const fmt = (n: number) => new Intl.NumberFormat('en-US').format(Math.round(n))

/* ---------------------------------------------------------------- 环形占比图 */
export function CockpitDonut({
  data,
  centerLabel,
  centerValue,
  height = 220,
  centerSize = 24,
  onSelect,
}: {
  data: Datum[]
  centerLabel?: string
  centerValue?: string
  height?: number
  /** 环中心大数字字号（设计板方向 A 的中心大数字用 28-30） */
  centerSize?: number
  onSelect?: (d: Datum) => void
}) {
  const total = data.reduce((s, d) => s + d.value, 0)
  const colorOf = (d: Datum, i: number) => d.color ?? SERIES_COLORS[i % SERIES_COLORS.length]
  const option: EChartsOption = {
    color: SERIES_COLORS as unknown as string[],
    tooltip: {
      ...COCKPIT_TOOLTIP,
      trigger: 'item',
      formatter: (p: any) => `${p.name}<br/><b>${fmt(p.value)}</b> · ${p.percent}%`,
    },
    series: [
      {
        type: 'pie',
        radius: ['58%', '82%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        padAngle: 3,
        itemStyle: {
          borderRadius: 6,
          borderColor: COCKPIT.bgPanelSolid,
          borderWidth: 2,
          shadowBlur: 14,
          shadowColor: 'rgba(0,0,0,0.4)',
        },
        // 数字放到右侧图例表，环形本身保持干净
        label: { show: false },
        labelLine: { show: false },
        emphasis: { scale: true, scaleSize: 6, itemStyle: { shadowBlur: 22 } },
        data: data.map((d, i) => ({
          name: d.name,
          value: d.value,
          itemStyle: { color: colorOf(d, i) },
        })),
      },
    ],
    graphic: centerValue
      ? [
          {
            type: 'text',
            left: 'center',
            top: '42%',
            style: {
              text: centerValue,
              fill: COCKPIT.accentBright,
              fontSize: centerSize,
              fontWeight: 900,
              fontFamily: COCKPIT_FONT,
            },
          },
          {
            type: 'text',
            left: 'center',
            top: '57%',
            style: {
              text: centerLabel ?? '',
              fill: COCKPIT.textMuted,
              fontSize: 11,
              fontFamily: COCKPIT_FONT,
            },
          },
        ]
      : undefined,
  }
  const ringH = Math.min(height, 168)
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
      <div className="shrink-0" style={{ width: ringH, height: ringH }}>
        <EChart
          option={option}
          height={ringH}
          onEvents={
            onSelect ? { click: (p: any) => onSelect({ name: p.name, value: p.value }) } : undefined
          }
        />
      </div>
      {/* 旁边图例表：色块 + 名称 + 数值 + 占比；窄面板自动换到环下方 */}
      <ul className="min-w-[150px] flex-1 space-y-1.5">
        {data.map((d, i) => {
          const pct = total > 0 ? Math.round((d.value / total) * 100) : 0
          return (
            <li
              key={`${d.name}-${i}`}
              onClick={onSelect ? () => onSelect(d) : undefined}
              className={`flex items-center gap-2 text-[11px] ${onSelect ? 'cursor-pointer hover:opacity-80' : ''}`}
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ background: colorOf(d, i) }}
              />
              <span className="min-w-0 flex-1 truncate text-slate-300">{d.name}</span>
              <span className="shrink-0 font-bold tabular-nums text-slate-100">{fmt(d.value)}</span>
              <span className="w-9 shrink-0 text-right tabular-nums text-slate-500">{pct}%</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/* ----------------------------------------------------------------- 进度仪表环 */
export function CockpitGauge({
  value,
  label,
  suffix = '%',
  color = SEMANTIC.info,
  height = 200,
}: {
  value: number
  label?: string
  suffix?: string
  color?: string
  height?: number
}) {
  const option: EChartsOption = {
    series: [
      {
        type: 'gauge',
        startAngle: 220,
        endAngle: -40,
        radius: '92%',
        center: ['50%', '54%'],
        progress: {
          show: true,
          width: 12,
          roundCap: true,
          itemStyle: {
            color: vGradient(alpha(color, 0.4), color),
            shadowBlur: 16,
            shadowColor: alpha(color, 0.6),
          },
        },
        axisLine: { lineStyle: { width: 12, color: [[1, alpha(color, 0.12)]] } },
        pointer: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        title: {
          show: !!label,
          offsetCenter: [0, '32%'],
          color: COCKPIT.textMuted,
          fontSize: 11,
          fontFamily: COCKPIT_FONT,
        },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, '-2%'],
          formatter: (v: number) => `${Math.round(v)}${suffix}`,
          color: COCKPIT.text,
          fontSize: 28,
          fontWeight: 800,
          fontFamily: COCKPIT_FONT,
        },
        data: [{ value, name: label ?? '' }],
      },
    ],
  }
  return <EChart option={option} height={height} />
}

/* ------------------------------------------------------------ 横向排行条形图 */
export function CockpitBar({
  data,
  color = SERIES_COLORS[0],
  height,
  onSelect,
}: {
  data: Datum[]
  color?: string
  height?: number
  onSelect?: (d: Datum) => void
}) {
  const sorted = [...data].sort((a, b) => a.value - b.value)
  const h = height ?? Math.max(140, sorted.length * 34 + 24)
  const option: EChartsOption = {
    grid: { left: 4, right: 36, top: 8, bottom: 4, containLabel: true },
    tooltip: { ...COCKPIT_TOOLTIP, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', show: false, max: 'dataMax' },
    yAxis: {
      type: 'category',
      data: sorted.map(d => d.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: COCKPIT.textMuted,
        fontSize: 11,
        fontFamily: COCKPIT_FONT,
        width: 96,
        overflow: 'truncate',
      },
    },
    series: [
      {
        type: 'bar',
        barWidth: 12,
        itemStyle: {
          borderRadius: [0, 6, 6, 0],
          color: vGradient(alpha(color, 0.35), color),
          shadowBlur: 10,
          shadowColor: alpha(color, 0.45),
        },
        label: {
          show: true,
          position: 'right',
          color: COCKPIT.text,
          fontSize: 11,
          fontWeight: 700,
          fontFamily: COCKPIT_FONT,
          formatter: (p: any) => fmt(p.value),
        },
        data: sorted.map(d => d.value),
      },
    ],
  }
  return (
    <EChart
      option={option}
      height={h}
      onEvents={
        onSelect ? { click: (p: any) => onSelect({ name: p.name, value: p.value }) } : undefined
      }
    />
  )
}

/* ----------------------------------------------------------------- 雷达画像图 */
export function CockpitRadar({
  data,
  color = SERIES_COLORS[2],
  height = 240,
  max,
}: {
  data: Datum[]
  color?: string
  height?: number
  max?: number
}) {
  const maxVal = max ?? Math.max(1, ...data.map(d => d.value))
  const option: EChartsOption = {
    tooltip: { ...COCKPIT_TOOLTIP },
    radar: {
      indicator: data.map(d => ({ name: d.name, max: maxVal })),
      radius: '66%',
      center: ['50%', '52%'],
      splitNumber: 4,
      axisName: { color: COCKPIT.textMuted, fontSize: 10, fontFamily: COCKPIT_FONT },
      splitLine: { lineStyle: { color: COCKPIT.grid } },
      splitArea: { areaStyle: { color: ['rgba(56,189,248,0.03)', 'rgba(56,189,248,0.06)'] } },
      axisLine: { lineStyle: { color: COCKPIT.grid } },
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color, width: 2, shadowBlur: 10, shadowColor: alpha(color, 0.6) },
        areaStyle: { color: alpha(color, 0.22) },
        itemStyle: { color },
        data: [{ value: data.map(d => d.value), name: '画像' }],
      },
    ],
  }
  return <EChart option={option} height={height} />
}

/* ------------------------------------------------------------- 趋势面积折线图 */
export function CockpitTrend({
  points,
  color = SERIES_COLORS[0],
  height = 200,
  smooth = true,
}: {
  points: Array<{ label: string; value: number }>
  color?: string
  height?: number
  smooth?: boolean
}) {
  const option: EChartsOption = {
    grid: { left: 6, right: 12, top: 16, bottom: 4, containLabel: true },
    tooltip: { ...COCKPIT_TOOLTIP, trigger: 'axis' },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: points.map(p => p.label),
      axisLine: { lineStyle: { color: COCKPIT.grid } },
      axisTick: { show: false },
      axisLabel: { color: COCKPIT.textFaint, fontSize: 10, fontFamily: COCKPIT_FONT },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: COCKPIT.grid } },
      axisLabel: { color: COCKPIT.textFaint, fontSize: 10, fontFamily: COCKPIT_FONT },
    },
    series: [
      {
        type: 'line',
        smooth,
        showSymbol: false,
        lineStyle: { color, width: 2.5, shadowBlur: 12, shadowColor: alpha(color, 0.5) },
        areaStyle: { color: vGradient(alpha(color, 0.32), alpha(color, 0.01)) },
        data: points.map(p => p.value),
      },
    ],
  }
  return <EChart option={option} height={height} />
}

/* --------------------------------------------------------------- NPS 分段条 */
export function CockpitNpsBar({
  promoters,
  passives,
  detractors,
  height = 64,
}: {
  promoters: number
  passives: number
  detractors: number
  height?: number
}) {
  const option: EChartsOption = {
    grid: { left: 0, right: 0, top: 8, bottom: 8 },
    tooltip: { ...COCKPIT_TOOLTIP, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', show: false, max: 'dataMax' },
    yAxis: { type: 'category', show: false, data: ['NPS'] },
    series: [
      {
        name: '推荐者',
        type: 'bar',
        stack: 'nps',
        barWidth: 18,
        itemStyle: { color: SEMANTIC.positive, borderRadius: [6, 0, 0, 6] },
        data: [promoters],
      },
      {
        name: '被动者',
        type: 'bar',
        stack: 'nps',
        barWidth: 18,
        itemStyle: { color: SEMANTIC.warning },
        data: [passives],
      },
      {
        name: '贬损者',
        type: 'bar',
        stack: 'nps',
        barWidth: 18,
        itemStyle: { color: SEMANTIC.danger, borderRadius: [0, 6, 6, 0] },
        data: [detractors],
      },
    ],
  }
  return <EChart option={option} height={height} />
}
