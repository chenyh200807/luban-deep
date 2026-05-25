'use client'

/* eslint-disable i18n/no-literal-ui-text */

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
    <nav className="flex h-full flex-col p-2.5" aria-label={ariaLabel ?? 'BI 主导航'}>
      {!collapsed ? (
        <div className="mb-2 px-1 text-[10px] font-black uppercase text-cyan-300/80">
          command areas
        </div>
      ) : null}
      <ul className="space-y-1.5">
        {items.map(item => {
          const Icon = item.icon
          const active = item.key === current
          return (
            <li key={item.key}>
              <button
                type="button"
                data-testid={`bi-sidenav-item-${String(item.key)}`}
                onClick={() => onSelect(item.key)}
                disabled={item.disabled}
                aria-current={active ? 'page' : undefined}
                aria-disabled={item.disabled ? true : undefined}
                aria-label={`${item.label}${item.summary ? `：${item.summary}` : ''}`}
                title={
                  item.disabled ? `${item.label} · ${item.statusLabel ?? '待接入'}` : undefined
                }
                className={`group relative flex min-h-[58px] w-full items-start gap-2 rounded-md border px-2.5 py-2 text-left text-sm transition ${
                  item.disabled
                    ? 'cursor-not-allowed border-transparent text-slate-500 opacity-70'
                    : active
                      ? 'border-cyan-300/25 bg-gradient-to-br from-cyan-500/20 to-slate-900/70 text-white shadow-lg shadow-black/20'
                      : 'border-transparent text-slate-300 hover:border-white/10 hover:bg-white/[0.05]'
                }`}
              >
                {active ? (
                  <span
                    className="absolute left-0 top-2 h-8 w-1 rounded-r bg-cyan-300"
                    aria-hidden
                  />
                ) : null}
                <Icon
                  className={`mt-0.5 h-4 w-4 shrink-0 ${
                    item.disabled
                      ? 'text-slate-600'
                      : active
                        ? 'text-cyan-200'
                        : 'text-cyan-300/70 group-hover:text-cyan-200'
                  }`}
                  aria-hidden
                />
                {!collapsed ? (
                  <span className="flex-1">
                    <span className="flex items-center justify-between gap-2 font-medium">
                      <span>{item.label}</span>
                      {item.statusLabel ? (
                        <span
                          className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${
                            item.disabled
                              ? 'bg-white/5 text-slate-500'
                              : active
                                ? 'bg-white/15 text-emerald-100'
                                : 'bg-emerald-300/10 text-emerald-200'
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              item.disabled ? 'bg-slate-400' : 'bg-current'
                            }`}
                            aria-hidden
                          />
                          {item.statusLabel}
                        </span>
                      ) : null}
                    </span>
                    {item.summary ? (
                      <span
                        className={`block text-[11px] leading-tight ${
                          item.disabled
                            ? 'text-slate-400'
                            : active
                              ? 'text-slate-300'
                              : 'text-slate-400'
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
      {footer ? <div className="mt-auto pt-3">{footer}</div> : null}
    </nav>
  )
}
