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
    <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-slate-200 bg-white px-3 md:px-4">
      {leftSlot}
      {brand ? (
        <div className="flex items-center gap-2 text-sm font-semibold tracking-tight">{brand}</div>
      ) : null}
      <label
        className="ml-auto flex w-full max-w-md items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 focus-within:border-slate-400 focus-within:bg-white"
        aria-label={searchAriaLabel}
      >
        <Search className="h-3.5 w-3.5 text-slate-400" aria-hidden />
        <input
          type="text"
          data-testid="bi-topbar-search"
          className="w-full bg-transparent text-xs outline-none placeholder:text-slate-400"
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
          className="hidden text-[11px] text-slate-500 lg:inline"
          aria-label="actor / 环境"
        >
          {actor}
        </span>
      ) : null}
    </header>
  )
}
