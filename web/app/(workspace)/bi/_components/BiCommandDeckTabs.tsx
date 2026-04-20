"use client";

import Link from "next/link";
import { BI_PRIMARY_TABS, getBiPrimaryTabHref, type BiPrimaryTab } from "./BiShared";

type BiCommandDeckTabsProps = {
  activeTab: BiPrimaryTab;
  onTabChange: (tab: BiPrimaryTab) => void;
};

export function BiCommandDeckTabs({ activeTab, onTabChange }: BiCommandDeckTabsProps) {
  return (
    <nav
      aria-label="BI primary tabs"
      className="surface-card flex flex-wrap items-center gap-3 border border-[var(--border)]/60 bg-white/75 p-3 shadow-[0_12px_30px_rgba(45,33,25,0.06)]"
    >
      {BI_PRIMARY_TABS.map((tab) => {
        const isActive = tab.key === activeTab;
        return (
          <Link
            key={tab.key}
            href={getBiPrimaryTabHref(tab.key)}
            onClick={() => onTabChange(tab.key)}
            aria-current={isActive ? "page" : undefined}
            className={`inline-flex min-w-[120px] items-center justify-center rounded-2xl px-4 py-3 text-sm font-medium transition ${
              isActive
                ? "bg-[var(--foreground)] text-white shadow-[0_10px_22px_rgba(45,33,25,0.16)]"
                : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--secondary)]/75"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
