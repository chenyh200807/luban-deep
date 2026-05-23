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
  // Round 3 H: removed "订单号" from the placeholder until backend exposes an
  // order→member lookup. Showing "订单号" while filterMembers ignores it is UI
  // deception (plan §7.4 contract). Re-add once /api/v1/bi/orders/lookup or
  // an equivalent reverse index ships.
  searchPlaceholder = '手机号 / user_id',
  searchAriaLabel = '全局搜索手机号 / user_id',
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
        <span className="hidden text-[11px] text-slate-500 lg:inline" aria-label="actor / 环境">
          {actor}
        </span>
      ) : null}
    </header>
  )
}
