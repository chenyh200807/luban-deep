/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'

export type BiSidePanelProps = {
  open: boolean
  onClose: () => void
  title: ReactNode
  subtitle?: ReactNode
  width?: 'sm' | 'md' | 'lg'
  children: ReactNode
  footer?: ReactNode
}

const WIDTH_CLASS = {
  sm: 'sm:max-w-md',
  md: 'sm:max-w-xl',
  lg: 'sm:max-w-3xl',
} as const

export function BiSidePanel({
  open,
  onClose,
  title,
  subtitle,
  width = 'md',
  children,
  footer,
}: BiSidePanelProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-slate-950/65 transition-opacity backdrop-blur-sm"
      role="presentation"
      onClick={e => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : '侧栏抽屉'}
        tabIndex={-1}
        className={`flex h-full w-full flex-col border-l border-white/10 bg-[#101622] text-slate-100 shadow-2xl shadow-black/40 outline-none ${WIDTH_CLASS[width]}`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-white/10 bg-white/[0.04] px-4 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-black text-white">{title}</div>
            {subtitle ? (
              <div className="mt-0.5 truncate text-[11px] text-slate-400">{subtitle}</div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭抽屉"
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/[0.06] text-slate-300 hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto bg-[#101622] px-4 py-3 text-sm">{children}</div>
        {footer ? (
          <footer className="border-t border-white/10 bg-[#101622] px-4 py-3">{footer}</footer>
        ) : null}
      </div>
    </div>
  )
}
