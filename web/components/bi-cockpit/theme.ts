/**
 * BI Cockpit — 科技感深色大屏设计 token（暖色·品牌对齐版）
 *
 * 与品牌主色对齐：陶土橙 #C35A2C / 深色态 #D4734B、暖中性、警示珊瑚红 #D44A3C。
 * 单一权威：所有驾驶舱图表/卡片的颜色、渐变、发光都从这里取，
 * 不在组件里散落硬编码色值。
 */
import type { EChartsOption } from 'echarts'

/** 主色板：暖炭黑底 + 琥珀/陶土发光 */
export const COCKPIT = {
  /** 页面/面板背景层 */
  bgDeep: '#150f0b',
  bgPanel: 'rgba(38, 28, 22, 0.55)',
  bgPanelSolid: '#211710',
  /** 描边 */
  border: 'rgba(212, 140, 90, 0.18)',
  borderGlow: 'rgba(232, 150, 80, 0.45)',
  /** 文本（暖白/暖灰，呼应品牌 foreground） */
  text: '#F1E9E1',
  textMuted: '#A99B8C',
  textFaint: '#6E5F52',
  /** 网格线 */
  grid: 'rgba(212, 150, 100, 0.09)',
} as const

/** 序列强调色（暖色主导，保留少量低饱和冷色做类别区分） */
export const SERIES_COLORS = [
  '#E8915A', // 陶土橙（品牌主色提亮）
  '#F2B85C', // 琥珀金
  '#E6CB86', // 沙金
  '#D86C57', // 黏土珊瑚
  '#9DB89C', // 鼠尾草绿（冷色区分）
  '#E0A39A', // 暖灰玫瑰
  '#C58E5A', // 古铜
  '#7FA8AE', // 雾青（冷色区分）
] as const

/** 语义色：状态/情绪（暖向，danger 用品牌珊瑚红） */
export const SEMANTIC = {
  positive: '#86B97A',
  warning: '#F2B85C',
  danger: '#D44A3C',
  info: '#E8915A',
  neutral: '#A99B8C',
} as const

/**
 * 可信度色阶（KPI 徽标用）：A=暖橙（陶土主色）、B=琥珀、C=灰（降级熄火）、
 * D=警示珊瑚（注册表外指标，元数据不可信）。
 */
export const TRUST_LEVEL_COLORS: Record<'A' | 'B' | 'C' | 'D', string> = {
  A: SERIES_COLORS[0],
  B: SERIES_COLORS[1],
  C: COCKPIT.textMuted,
  D: SEMANTIC.danger,
} as const

/** 构造竖直渐变（图表填充用） */
export function vGradient(from: string, to: string) {
  return {
    type: 'linear' as const,
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: from },
      { offset: 1, color: to },
    ],
  }
}

/** 把 hex 加上透明度（#rrggbb + alpha 0-1） */
export function alpha(hex: string, a: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

/** 统一 tooltip 风格（暖色深玻璃 + 发光描边） */
export const COCKPIT_TOOLTIP: NonNullable<EChartsOption['tooltip']> = {
  backgroundColor: 'rgba(28, 19, 13, 0.92)',
  borderColor: COCKPIT.borderGlow,
  borderWidth: 1,
  padding: [8, 12],
  textStyle: { color: COCKPIT.text, fontSize: 12 },
  extraCssText:
    'backdrop-filter: blur(8px); border-radius: 10px; box-shadow: 0 8px 32px rgba(0,0,0,0.5);',
}

/** 字体栈：与小程序/web 一致，数字用 tabular */
export const COCKPIT_FONT =
  '"Inter", system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
