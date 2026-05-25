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
        className="rounded-lg border border-white/10 bg-white/5 p-1.5 text-slate-200 hover:bg-white/10 md:hidden"
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
      className="bi-v2-dark-scope h-[100dvh] min-h-0 overflow-y-auto overflow-x-hidden bg-[#101622] text-slate-100 [scrollbar-gutter:stable] [-webkit-overflow-scrolling:touch]"
      style={{
        backgroundImage:
          'radial-gradient(circle at 92% 4%, rgba(56,189,248,0.18), transparent 30%), radial-gradient(circle at 14% 18%, rgba(52,211,153,0.11), transparent 26%), linear-gradient(180deg, #101622 0%, #111a29 48%, #0f1726 100%)',
      }}
    >
      {topbar(api)}
      {navOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-10 bg-slate-950/35 md:hidden"
          onClick={() => setNavOpen(false)}
          aria-label="关闭 BI 主导航遮罩"
        />
      ) : null}
      <div className="flex min-h-[calc(100dvh-3rem)]">
        <aside
          className={`fixed inset-y-12 left-0 z-20 w-[252px] border-r border-white/10 bg-[#0a0f19]/90 shadow-2xl shadow-black/30 backdrop-blur-xl transition-transform md:sticky md:top-12 md:translate-x-0 md:self-start md:shadow-none ${
            navOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          {sidenav(api)}
        </aside>
        <main className="min-w-0 flex-1 px-3 py-4 md:px-6 md:py-5 xl:px-8">
          <div className="mx-auto max-w-[1680px] space-y-4">
            {pageTitle ? (
              <div className="relative overflow-hidden rounded-[1.75rem] border border-white/10 bg-white/[0.045] p-4 shadow-xl shadow-black/15 lg:p-5">
                <div
                  className="pointer-events-none absolute inset-0 opacity-80"
                  style={{
                    backgroundImage:
                      'radial-gradient(circle at 88% 18%, rgba(94,221,234,0.16), transparent 26%), radial-gradient(circle at 12% 8%, rgba(251,146,60,0.10), transparent 24%)',
                  }}
                  aria-hidden
                />
                <div className="relative flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                  <div className="min-w-0">
                    <div className="text-[11px] font-black uppercase tracking-normal text-cyan-300">
                      实时经营指挥台 · BI COMMAND WORKSPACE
                    </div>
                    <h1 className="mt-1 text-2xl font-black tracking-normal text-white">
                      {pageTitle}
                    </h1>
                    {pageSummary ? (
                      <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-300/80">
                        {pageSummary}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-300">
                    <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1.5 font-bold text-emerald-200">
                      admin-only
                    </span>
                    <span className="rounded-full border border-cyan-300/25 bg-cyan-300/10 px-3 py-1.5 font-bold text-cyan-200">
                      audit writes
                    </span>
                  </div>
                </div>
              </div>
            ) : null}
            {children}
            {footer ? (
              <footer className="border-t border-white/10 pt-3 text-[11px] text-slate-400">
                {footer}
              </footer>
            ) : null}
          </div>
        </main>
      </div>
    </div>
  )
}
