'use client'

/**
 * 轻量 ECharts React 封装（不依赖 echarts-for-react，规避 React 19 兼容坑）。
 * 负责：init / setOption / 自适应 resize / dispose。
 */
import * as echarts from 'echarts/core'
import { BarChart, FunnelChart, GaugeChart, LineChart, PieChart, RadarChart } from 'echarts/charts'
import {
  GraphicComponent,
  GridComponent,
  LegendComponent,
  RadarComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'
import type { EChartsOption } from 'echarts'

// 按需注册：`import * as echarts from 'echarts'` 会拉进全量包（实测 br 309KB vs
// 按需 173KB），因为 echarts 的 sideEffects 白名单含 index.js，打包器摇不掉。
// 这份清单必须覆盖 bi-cockpit 下所有 option 用到的 series type 与顶层 component
// key —— 漏注册不会报错，只会静默不渲染。新增图表类型时同步补这里。
// （axisPointer 无需单列，TooltipComponent 的 install 已自带。）
echarts.use([
  BarChart,
  LineChart,
  RadarChart,
  PieChart,
  GaugeChart,
  FunnelChart,
  TooltipComponent,
  GridComponent,
  LegendComponent,
  GraphicComponent,
  RadarComponent,
  CanvasRenderer,
])

export function EChart({
  option,
  height = 240,
  className = '',
  onEvents,
}: {
  option: EChartsOption
  height?: number | string
  className?: string
  /** 事件名 -> 回调（如 { click: (p) => ... }） */
  onEvents?: Record<string, (params: unknown) => void>
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  // init + dispose
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    chartRef.current = chart
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  // option 变化时更新
  useEffect(() => {
    chartRef.current?.setOption(option, true)
  }, [option])

  // 事件绑定
  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !onEvents) return
    const entries = Object.entries(onEvents)
    entries.forEach(([evt, cb]) => chart.on(evt, cb))
    return () => {
      entries.forEach(([evt, cb]) => chart.off(evt, cb))
    }
  }, [onEvents])

  return (
    <div
      ref={ref}
      className={className}
      style={{ width: '100%', height: typeof height === 'number' ? `${height}px` : height }}
    />
  )
}
