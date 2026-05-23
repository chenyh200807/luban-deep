'use client'

import type { ComponentType, SVGProps } from 'react'

export type BiSideNavItem<TKey extends string> = {
  key: TKey
  label: string
  summary?: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
  disabled?: boolean
  statusLabel?: string
}

export type BiSideNavProps<TKey extends string> = {
  items: ReadonlyArray<BiSideNavItem<TKey>>
  current: TKey
  onSelect: (key: TKey) => void
  ariaLabel?: string
  footer?: React.ReactNode
  collapsed?: boolean
}

export function BiSideNav<TKey extends string>({
  items,
  current,
  onSelect,
  ariaLabel,
  footer,
  collapsed = false,
}: BiSideNavProps<TKey>) {
  return (
    <nav className="h-full p-2" aria-label={ariaLabel ?? 'BI 主导航'}>
      <ul className="space-y-1">
        {items.map(item => {
          const Icon = item.icon
          const active = item.key === current
          return (
            <li key={item.key}>
              <button
                type="button"
                onClick={() => onSelect(item.key)}
                disabled={item.disabled}
                aria-current={active ? 'page' : undefined}
                aria-disabled={item.disabled ? true : undefined}
                aria-label={`${item.label}${item.summary ? `：${item.summary}` : ''}`}
                title={item.disabled ? `${item.label} · ${item.statusLabel ?? '待接入'}` : undefined}
                className={`group flex w-full items-start gap-2 rounded px-2 py-2 text-left text-sm ${
                  item.disabled
                    ? 'cursor-not-allowed text-slate-400 opacity-70'
                    : active
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-700 hover:bg-slate-100'
                }`}
              >
                <Icon
                  className={`mt-0.5 h-4 w-4 ${
                    item.disabled
                      ? 'text-slate-300'
                      : active
                        ? 'text-white'
                        : 'text-slate-500 group-hover:text-slate-700'
                  }`}
                  aria-hidden
                />
                {!collapsed ? (
                  <span className="flex-1">
                    <span className="flex items-center justify-between gap-2 font-medium">
                      <span>{item.label}</span>
                      {item.statusLabel ? (
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] ${
                            item.disabled
                              ? 'bg-slate-100 text-slate-500'
                              : active
                                ? 'bg-white/15 text-slate-100'
                                : 'bg-emerald-50 text-emerald-700'
                          }`}
                        >
                          {item.statusLabel}
                        </span>
                      ) : null}
                    </span>
                    {item.summary ? (
                      <span
                        className={`block text-[11px] leading-tight ${
                          item.disabled ? 'text-slate-400' : active ? 'text-slate-200' : 'text-slate-500'
                        }`}
                      >
                        {item.summary}
                      </span>
                    ) : null}
                  </span>
                ) : null}
              </button>
            </li>
          )
        })}
      </ul>
      {footer ? <div className="mt-3">{footer}</div> : null}
    </nav>
  )
}
