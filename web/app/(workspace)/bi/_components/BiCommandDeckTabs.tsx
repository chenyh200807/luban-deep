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
      className="surface-card flex flex-wrap items-center gap-2 border border-[var(--border)]/60 bg-white/80 p-2 shadow-[0_10px_24px_rgba(45,33,25,0.05)]"
    >
      {BI_PRIMARY_TABS.map((tab) => {
        const isActive = tab.key === activeTab;
        return (
          <Link
            key={tab.key}
            href={getBiPrimaryTabHref(tab.key)}
            onClick={() => onTabChange(tab.key)}
            aria-current={isActive ? "page" : undefined}
            className={`inline-flex min-w-[108px] items-center justify-center rounded-full px-4 py-2.5 text-sm font-medium transition ${
              isActive
                ? "border border-transparent bg-[var(--foreground)] text-white shadow-[0_8px_20px_rgba(45,33,25,0.12)]"
                : "border border-transparent bg-transparent text-[var(--muted-foreground)] hover:border-[var(--border)] hover:bg-[var(--secondary)] hover:text-[var(--foreground)]"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
