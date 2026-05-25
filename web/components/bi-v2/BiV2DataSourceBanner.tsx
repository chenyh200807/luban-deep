import type { ReactNode } from 'react'

export type BiV2DataSourceBannerTone = 'amber' | 'sky' | 'emerald' | 'rose'

export type BiV2DataSourceBannerProps = {
  tone: BiV2DataSourceBannerTone
  children: ReactNode
  action?: ReactNode
  role?: 'alert' | 'status'
}

const TONE_CLASS: Record<BiV2DataSourceBannerTone, string> = {
  amber: 'border-amber-300/25 bg-amber-300/10 text-amber-100',
  sky: 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100',
  emerald: 'border-emerald-300/25 bg-emerald-300/10 text-emerald-100',
  rose: 'border-rose-300/25 bg-rose-300/10 text-rose-100',
}

export function BiV2DataSourceBanner({
  tone,
  children,
  action,
  role,
}: BiV2DataSourceBannerProps) {
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2 rounded-2xl border px-3 py-2 text-xs shadow-sm shadow-black/10 ${TONE_CLASS[tone]}`}
      role={role}
    >
      <div className="min-w-0 flex-1 leading-relaxed">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
