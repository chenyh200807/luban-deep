/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Search } from 'lucide-react'
import { useState, type ReactNode } from 'react'

export type BiTopBarProps = {
  brand?: ReactNode
  actor?: ReactNode
  searchPlaceholder?: string
  searchAriaLabel?: string
  onSubmitSearch?: (value: string) => void
  rightSlot?: ReactNode
  leftSlot?: ReactNode
}

export function BiTopBar({
  brand,
  actor,
  // Global search is routed by the shell: member identity queries go to
  // MemberOps; order / ledger-like queries go to the commerce read model.
  // The input itself remains a thin UI control and does not interpret data.
  searchPlaceholder = '手机号 / user_id / 订单号',
  searchAriaLabel = '全局搜索手机号 / user_id / 订单号',
  onSubmitSearch,
  rightSlot,
  leftSlot,
}: BiTopBarProps) {
  const [value, setValue] = useState('')
  const [composing, setComposing] = useState(false)

  function submit() {
    if (composing) return
    onSubmitSearch?.(value.trim())
  }

  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-white/10 bg-[#101622]/90 px-3 backdrop-blur-xl md:px-4">
      {leftSlot}
      {brand ? (
        <div className="flex min-w-fit items-center gap-2 text-sm font-semibold">{brand}</div>
      ) : null}
      <label
        className="ml-auto flex h-8 w-full max-w-xl items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-2.5 text-slate-100 shadow-inner shadow-black/10 focus-within:border-cyan-300/40 focus-within:bg-white/[0.08] focus-within:ring-2 focus-within:ring-cyan-300/20"
        aria-label={searchAriaLabel}
      >
        <Search className="h-3.5 w-3.5 text-slate-400" aria-hidden />
        <input
          type="text"
          data-testid="bi-topbar-search"
          className="w-full bg-transparent text-xs text-slate-100 outline-none placeholder:text-slate-500"
          placeholder={searchPlaceholder}
          aria-label={searchAriaLabel}
          value={value}
          onChange={e => setValue(e.target.value)}
          onCompositionStart={() => setComposing(true)}
          onCompositionEnd={e => {
            setComposing(false)
            setValue(e.currentTarget.value)
          }}
          onKeyDown={e => {
            if (e.key === 'Enter') submit()
            if (e.key === 'Escape') setValue('')
          }}
        />
      </label>
      {rightSlot}
      {actor ? (
        <span
          data-testid="bi-topbar-actor"
          className="hidden rounded-full border border-white/10 bg-white/[0.06] px-2 py-1 text-[11px] font-bold text-slate-300 lg:inline"
          aria-label="actor / 环境"
        >
          {actor}
        </span>
      ) : null}
    </header>
  )
}
