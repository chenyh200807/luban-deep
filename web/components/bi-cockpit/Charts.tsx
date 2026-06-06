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
  onSelect,
}: {
  data: Datum[]
  centerLabel?: string
  centerValue?: string
  height?: number
  onSelect?: (d: Datum) => void
}) {
  const total = data.reduce((s, d) => s + d.value, 0)
  const option: EChartsOption = {
    color: SERIES_COLORS as unknown as string[],
    tooltip: { ...COCKPIT_TOOLTIP, trigger: 'item', formatter: (p: any) => `${p.name}<br/><b>${fmt(p.value)}</b> · ${p.percent}%` },
    series: [
      {
        type: 'pie',
        radius: ['62%', '86%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        padAngle: 3,
        itemStyle: { borderRadius: 6, borderColor: COCKPIT.bgPanelSolid, borderWidth: 2, shadowBlur: 14, shadowColor: 'rgba(0,0,0,0.4)' },
        label: { show: false },
        labelLine: { show: false },
        emphasis: { scale: true, scaleSize: 6, itemStyle: { shadowBlur: 22 } },
        data: data.map((d, i) => ({
          name: d.name,
          value: d.value,
          itemStyle: d.color ? { color: d.color } : { color: SERIES_COLORS[i % SERIES_COLORS.length] },
        })),
      },
    ],
    graphic: centerValue
      ? [
          {
            type: 'text',
            left: 'center',
            top: '42%',
            style: { text: centerValue, fill: COCKPIT.text, fontSize: 26, fontWeight: 800, fontFamily: COCKPIT_FONT },
          },
          {
            type: 'text',
            left: 'center',
            top: '58%',
            style: { text: centerLabel ?? '', fill: COCKPIT.textMuted, fontSize: 11, fontFamily: COCKPIT_FONT },
          },
        ]
      : undefined,
  }
  void total
  return <EChart option={option} height={height} onEvents={onSelect ? { click: (p: any) => onSelect({ name: p.name, value: p.value }) } : undefined} />
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
        progress: { show: true, width: 12, roundCap: true, itemStyle: { color: vGradient(alpha(color, 0.4), color), shadowBlur: 16, shadowColor: alpha(color, 0.6) } },
        axisLine: { lineStyle: { width: 12, color: [[1, alpha(color, 0.12)]] } },
        pointer: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        title: { show: !!label, offsetCenter: [0, '32%'], color: COCKPIT.textMuted, fontSize: 11, fontFamily: COCKPIT_FONT },
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
      data: sorted.map((d) => d.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: COCKPIT.textMuted, fontSize: 11, fontFamily: COCKPIT_FONT, width: 96, overflow: 'truncate' },
    },
    series: [
      {
        type: 'bar',
        barWidth: 12,
        itemStyle: { borderRadius: [0, 6, 6, 0], color: vGradient(alpha(color, 0.35), color), shadowBlur: 10, shadowColor: alpha(color, 0.45) },
        label: { show: true, position: 'right', color: COCKPIT.text, fontSize: 11, fontWeight: 700, fontFamily: COCKPIT_FONT, formatter: (p: any) => fmt(p.value) },
        data: sorted.map((d) => d.value),
      },
    ],
  }
  return <EChart option={option} height={h} onEvents={onSelect ? { click: (p: any) => onSelect({ name: p.name, value: p.value }) } : undefined} />
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
  const maxVal = max ?? Math.max(1, ...data.map((d) => d.value))
  const option: EChartsOption = {
    tooltip: { ...COCKPIT_TOOLTIP },
    radar: {
      indicator: data.map((d) => ({ name: d.name, max: maxVal })),
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
        data: [{ value: data.map((d) => d.value), name: '画像' }],
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
      data: points.map((p) => p.label),
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
        data: points.map((p) => p.value),
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
      { name: '推荐者', type: 'bar', stack: 'nps', barWidth: 18, itemStyle: { color: SEMANTIC.positive, borderRadius: [6, 0, 0, 6] }, data: [promoters] },
      { name: '被动者', type: 'bar', stack: 'nps', barWidth: 18, itemStyle: { color: SEMANTIC.warning }, data: [passives] },
      { name: '贬损者', type: 'bar', stack: 'nps', barWidth: 18, itemStyle: { color: SEMANTIC.danger, borderRadius: [0, 6, 6, 0] }, data: [detractors] },
    ],
  }
  return <EChart option={option} height={height} />
}
