"use client";

import { CalendarDays, ChevronDown, Download, Funnel, RefreshCw, ShieldAlert } from "lucide-react";

type BiBossHeaderProps = {
  days: 7 | 30 | 90;
  onDaysChange: (days: 7 | 30 | 90) => void;
  onExport: () => void;
  exporting: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  canExport: boolean;
  filtersOpen: boolean;
  onToggleFilters: () => void;
  activeFilters: string[];
  lastUpdatedLabel: string;
  heroIssue?: string | null;
  heroIssueTitle?: string;
};

export function BiBossHeader({
  days,
  onDaysChange,
  onExport,
  exporting,
  onRefresh,
  refreshing,
  canExport,
  filtersOpen,
  onToggleFilters,
  activeFilters,
  lastUpdatedLabel,
  heroIssue,
  heroIssueTitle = "经营提醒",
}: BiBossHeaderProps) {
  return (
    <section className="surface-card border border-[var(--border)]/70 bg-white/88 px-5 py-4 shadow-[0_14px_32px_rgba(45,33,25,0.06)] backdrop-blur">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-[var(--secondary)] px-2.5 py-1 text-[11px] font-medium tracking-[0.16em] text-[var(--muted-foreground)]">
              BOSS WORKBENCH
            </span>
            <span className="text-xs text-[var(--muted-foreground)]">最近同步：{lastUpdatedLabel}</span>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[var(--foreground)]">DeepTutor BI 工作台</h1>
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
            经营、质量、会员、TutorBot 四条主线的轻量总览入口。
          </p>
          <p className="mt-2 text-xs text-[var(--muted-foreground)]">
            当前筛选：{activeFilters.length ? activeFilters.join(" · ") : "全部"}
          </p>
        </div>

        <div className="flex flex-col gap-3 xl:items-end">
          <div className="flex flex-wrap items-center gap-2">
            {[7, 30, 90].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => onDaysChange(value as 7 | 30 | 90)}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-sm font-medium transition ${
                  days === value
                    ? "border-[var(--foreground)] bg-[var(--foreground)] text-white"
                    : "border-[var(--border)] bg-white text-[var(--foreground)] hover:border-[var(--primary)]/40 hover:bg-[var(--secondary)]"
                }`}
              >
                <CalendarDays size={14} />
                {value} 天
              </button>
            ))}
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white px-3.5 py-2 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--primary)]/40 hover:bg-[var(--secondary)] disabled:opacity-60"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
              刷新
            </button>
            <button
              type="button"
              onClick={onExport}
              disabled={exporting || !canExport}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white px-3.5 py-2 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--primary)]/40 hover:bg-[var(--secondary)] disabled:opacity-60"
            >
              <Download size={14} className={exporting ? "animate-pulse" : ""} />
              导出 JSON
            </button>
            <button
              type="button"
              onClick={onToggleFilters}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-white px-3.5 py-2 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--primary)]/40 hover:bg-[var(--secondary)]"
              aria-expanded={filtersOpen}
            >
              <Funnel size={14} />
              筛选
              <ChevronDown size={14} className={`transition ${filtersOpen ? "rotate-180" : ""}`} />
            </button>
          </div>

          {heroIssue ? (
            <div className="inline-flex max-w-[540px] items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs leading-5 text-amber-800">
              <ShieldAlert size={14} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-medium">{heroIssueTitle}</p>
                <p className="text-amber-700">{heroIssue}</p>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
