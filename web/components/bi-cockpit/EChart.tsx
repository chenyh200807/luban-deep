'use client'

/**
 * 轻量 ECharts React 封装（不依赖 echarts-for-react，规避 React 19 兼容坑）。
 * 负责：init / setOption / 自适应 resize / dispose。
 */
import * as echarts from 'echarts'
import { useEffect, useRef } from 'react'
import type { EChartsOption } from 'echarts'

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
