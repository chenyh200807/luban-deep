'use client'

/**
 * 驾驶舱布局原子：大屏背景、玻璃面板（科技感切角+发光描边）、KPI 大数字、区块标题。
 */
import type { ReactNode } from 'react'
import { COCKPIT, SERIES_COLORS, alpha } from './theme'

/* ------------------------------------------------------ 大屏背景（网格+光晕） */
export function CockpitBg({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`relative isolate overflow-hidden rounded-3xl ${className}`}
      style={{ background: COCKPIT.bgDeep }}
    >
      {/* 暖色网格（与设计板 .bg-grid 一致：34px 格 + 顶部椭圆渐隐） */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: `linear-gradient(${COCKPIT.grid} 1px, transparent 1px), linear-gradient(90deg, ${COCKPIT.grid} 1px, transparent 1px)`,
          backgroundSize: '34px 34px',
          maskImage: 'radial-gradient(ellipse 90% 55% at 50% 0%, #000 30%, transparent 100%)',
        }}
      />
      {/* 顶部暖光晕 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 h-80 w-[120%] -translate-x-1/2"
        style={{
          background: `radial-gradient(ellipse at center, ${alpha(SERIES_COLORS[0], 0.16)}, transparent 60%)`,
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-32 -right-20 h-72 w-72 rounded-full"
        style={{
          background: `radial-gradient(circle, ${alpha(COCKPIT.brandDeep, 0.14)}, transparent 60%)`,
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  )
}

/* ----------------------------------------------------- 玻璃面板（科技感切角） */
export function CockpitPanel({
  children,
  className = '',
  glow = false,
  title,
  hint,
  icon,
  action,
}: {
  children: ReactNode
  className?: string
  glow?: boolean
  title?: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <section
      className={`group relative rounded-2xl border p-4 ${className}`}
      style={{
        borderColor: glow ? 'rgba(232,145,90,0.4)' : 'rgba(212,140,90,0.18)',
        background: 'linear-gradient(160deg, rgba(40,28,20,0.6), rgba(28,19,13,0.55))',
        boxShadow: glow
          ? '0 0 0 1px rgba(232,145,90,0.18), 0 16px 48px -16px rgba(0,0,0,0.7)'
          : '0 16px 48px -20px rgba(0,0,0,0.6)',
        backdropFilter: 'blur(10px)',
      }}
    >
      {/* 四角切角装饰 */}
      <Corner pos="tl" />
      <Corner pos="tr" />
      <Corner pos="bl" />
      <Corner pos="br" />
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[13px] font-bold text-slate-100">
              {icon && <span style={{ color: COCKPIT.accentBright }}>{icon}</span>}
              <span className="truncate">{title}</span>
            </div>
            {hint && <p className="mt-0.5 truncate text-[11px] text-slate-500">{hint}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

function Corner({ pos }: { pos: 'tl' | 'tr' | 'bl' | 'br' }) {
  const base = 'pointer-events-none absolute h-3 w-3 border-[#E8915A]/55'
  const map: Record<string, string> = {
    tl: 'left-1.5 top-1.5 border-l border-t rounded-tl',
    tr: 'right-1.5 top-1.5 border-r border-t rounded-tr',
    bl: 'left-1.5 bottom-1.5 border-l border-b rounded-bl',
    br: 'right-1.5 bottom-1.5 border-r border-b rounded-br',
  }
  return <span aria-hidden className={`${base} ${map[pos]}`} />
}

/* -------------------------------------------------------------- KPI 大数字卡 */
const TONE: Record<string, { ring: string; text: string; glow: string }> = {
  // 键名沿用，色值全部换成品牌暖色，调用处无需改动
  cyan: { ring: 'rgba(232,145,90,0.35)', text: '#F0A878', glow: 'rgba(232,145,90,0.5)' }, // 陶土橙
  teal: { ring: 'rgba(242,184,92,0.35)', text: '#F2C572', glow: 'rgba(242,184,92,0.5)' }, // 琥珀
  violet: { ring: 'rgba(197,142,90,0.35)', text: '#D8A878', glow: 'rgba(197,142,90,0.5)' }, // 古铜
  amber: { ring: 'rgba(242,184,92,0.35)', text: '#F4CE86', glow: 'rgba(242,184,92,0.5)' }, // 金
  rose: { ring: 'rgba(216,108,87,0.35)', text: '#E89A8E', glow: 'rgba(216,108,87,0.5)' }, // 黏土
  emerald: { ring: 'rgba(134,185,122,0.35)', text: '#A6C99A', glow: 'rgba(134,185,122,0.5)' }, // 鼠尾草
}

export function CockpitKpi({
  label,
  value,
  unit,
  sub,
  tone = 'cyan',
  icon,
  delta,
}: {
  label: string
  value: string | number
  unit?: string
  sub?: ReactNode
  tone?: keyof typeof TONE | string
  icon?: ReactNode
  delta?: { value: string; up: boolean }
}) {
  const t = TONE[tone] ?? TONE.cyan
  return (
    <div
      className="relative overflow-hidden rounded-2xl border p-4"
      style={{
        borderColor: t.ring,
        background: 'linear-gradient(150deg, rgba(40,28,20,0.7), rgba(24,16,11,0.5))',
      }}
    >
      <div
        aria-hidden
        className="absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-40 blur-xl"
        style={{ background: t.glow }}
      />
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          {label}
        </span>
        {icon && <span style={{ color: t.text }}>{icon}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span
          className="text-3xl font-black tabular-nums"
          style={{ color: t.text, textShadow: `0 0 18px ${t.glow}` }}
        >
          {value}
        </span>
        {unit && <span className="text-xs font-bold text-slate-400">{unit}</span>}
      </div>
      <div className="mt-1 flex items-center gap-2">
        {delta && (
          <span
            className={`text-[11px] font-bold ${delta.up ? 'text-emerald-300' : 'text-rose-300'}`}
          >
            {delta.up ? '▲' : '▼'} {delta.value}
          </span>
        )}
        {sub && <span className="truncate text-[11px] text-slate-500">{sub}</span>}
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- 区块小标题 */
export function SectionLabel({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span
        className="h-3.5 w-1 rounded-full"
        style={{
          background: `linear-gradient(${SERIES_COLORS[0]}, ${COCKPIT.brandDeep})`,
          boxShadow: `0 0 8px ${COCKPIT.borderGlow}`,
        }}
      />
      {icon && <span style={{ color: COCKPIT.accentBright }}>{icon}</span>}
      <h3 className="text-sm font-extrabold tracking-wide text-slate-100">{children}</h3>
    </div>
  )
}
