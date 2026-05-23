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
  sm: 'max-w-md',
  md: 'max-w-xl',
  lg: 'max-w-3xl',
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
      className="fixed inset-0 z-40 flex justify-end bg-slate-900/40 transition-opacity"
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
        className={`flex h-full w-full flex-col bg-white shadow-xl outline-none ${WIDTH_CLASS[width]}`}
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-900">{title}</div>
            {subtitle ? (
              <div className="mt-0.5 truncate text-[11px] text-slate-500">{subtitle}</div>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭抽屉"
            className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-4 w-4" aria-hidden />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-3 text-sm">{children}</div>
        {footer ? <footer className="border-t border-slate-200 px-4 py-3">{footer}</footer> : null}
      </div>
    </div>
  )
}
