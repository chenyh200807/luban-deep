import type { ReactNode } from 'react'

export type BiV2DataSourceBannerTone = 'amber' | 'sky' | 'emerald' | 'rose'

export type BiV2DataSourceBannerProps = {
  tone: BiV2DataSourceBannerTone
  children: ReactNode
  action?: ReactNode
  role?: 'alert' | 'status'
}

const TONE_CLASS: Record<BiV2DataSourceBannerTone, string> = {
  amber: 'border-amber-200 bg-amber-50 text-amber-800',
  sky: 'border-sky-200 bg-sky-50 text-sky-800',
  emerald: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  rose: 'border-rose-200 bg-rose-50 text-rose-800',
}

export function BiV2DataSourceBanner({
  tone,
  children,
  action,
  role,
}: BiV2DataSourceBannerProps) {
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs ${TONE_CLASS[tone]}`}
      role={role}
    >
      <div className="min-w-0 flex-1 leading-relaxed">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}
