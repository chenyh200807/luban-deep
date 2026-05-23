'use client'

import type { ComponentType, SVGProps } from 'react'

export type BiSideNavItem<TKey extends string> = {
  key: TKey
  label: string
  summary?: string
  icon: ComponentType<SVGProps<SVGSVGElement>>
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
                aria-current={active ? 'page' : undefined}
                aria-label={`${item.label}${item.summary ? `：${item.summary}` : ''}`}
                className={`group flex w-full items-start gap-2 rounded px-2 py-2 text-left text-sm ${
                  active ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'
                }`}
              >
                <Icon
                  className={`mt-0.5 h-4 w-4 ${active ? 'text-white' : 'text-slate-500 group-hover:text-slate-700'}`}
                  aria-hidden
                />
                {!collapsed ? (
                  <span className="flex-1">
                    <span className="block font-medium">{item.label}</span>
                    {item.summary ? (
                      <span
                        className={`block text-[11px] leading-tight ${
                          active ? 'text-slate-200' : 'text-slate-500'
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
