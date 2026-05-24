/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Menu, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

export type BiAppShellApi = {
  navOpen: boolean
  toggleNav: () => void
  closeNav: () => void
  hamburger: ReactNode
}

export type BiAppShellProps = {
  topbar: (api: BiAppShellApi) => ReactNode
  sidenav: (api: BiAppShellApi) => ReactNode
  children: ReactNode
  pageTitle?: string
  pageSummary?: string
  footer?: ReactNode
}

export function BiAppShell({
  topbar,
  sidenav,
  children,
  pageTitle,
  pageSummary,
  footer,
}: BiAppShellProps) {
  const [navOpen, setNavOpen] = useState(false)

  const api: BiAppShellApi = {
    navOpen,
    toggleNav: () => setNavOpen(v => !v),
    closeNav: () => setNavOpen(false),
    hamburger: (
      <button
        type="button"
        className="rounded p-1.5 text-slate-600 hover:bg-slate-100 md:hidden"
        onClick={() => setNavOpen(v => !v)}
        aria-label={navOpen ? '关闭主导航' : '打开主导航'}
        aria-expanded={navOpen}
      >
        {navOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
      </button>
    ),
  }

  return (
    <div
      data-bi-app-shell
      className="h-[100dvh] min-h-0 overflow-y-auto overflow-x-hidden bg-slate-50 text-slate-900 [scrollbar-gutter:stable] [-webkit-overflow-scrolling:touch]"
    >
      {topbar(api)}
      <div className="flex">
        <aside
          className={`fixed inset-y-12 left-0 z-20 w-56 border-r border-slate-200 bg-white transition-transform md:sticky md:top-12 md:translate-x-0 md:self-start ${
            navOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          {sidenav(api)}
        </aside>
        <main className="flex-1 px-3 py-4 md:px-6 md:py-6">
          <div className="mx-auto max-w-screen-2xl space-y-4">
            {pageTitle ? (
              <div>
                <h1 className="text-xl font-semibold tracking-tight text-slate-900">{pageTitle}</h1>
                {pageSummary ? <p className="text-xs text-slate-500">{pageSummary}</p> : null}
              </div>
            ) : null}
            {children}
            {footer ? (
              <footer className="border-t border-slate-200 pt-3 text-[11px] text-slate-500">
                {footer}
              </footer>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  )
}
