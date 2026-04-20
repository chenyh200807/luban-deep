"use client";

import { CalendarDays, Download, RefreshCw } from "lucide-react";

type BiCommandDeckHeroProps = {
  title: string;
  subtitle: string;
  days: 7 | 30 | 90;
  onDaysChange: (days: 7 | 30 | 90) => void;
  onExport: () => void;
  exporting: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  canExport: boolean;
  lastUpdatedLabel: string;
  rangeLabel: string;
  activeFilters: string[];
};

export function BiCommandDeckHero({
  title,
  subtitle,
  days,
  onDaysChange,
  onExport,
  exporting,
  onRefresh,
  refreshing,
  canExport,
  lastUpdatedLabel,
  rangeLabel,
  activeFilters,
}: BiCommandDeckHeroProps) {
  return (
    <section className="surface-card overflow-hidden border-0 bg-[linear-gradient(135deg,#151312_0%,#2a211d_44%,#8f4625_100%)] text-white shadow-[0_24px_60px_rgba(31,26,23,0.22)]">
      <div className="flex flex-col gap-6 p-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-3xl">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs tracking-[0.2em] text-white/75">
            COMMAND DECK
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-white/75">{subtitle}</p>
        </div>

        <div className="flex flex-col gap-3 self-start">
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-white/8 p-2">
            {[7, 30, 90].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => onDaysChange(value as 7 | 30 | 90)}
                className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition ${
                  days === value ? "bg-white text-[#2d2119]" : "text-white/75 hover:bg-white/10 hover:text-white"
                }`}
              >
                <CalendarDays size={14} />
                {value} 天
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onExport}
            disabled={exporting || !canExport}
            className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-medium text-[#2d2119] transition hover:bg-white/90 disabled:opacity-60"
          >
            <Download size={16} className={exporting ? "animate-pulse" : ""} />
            导出 JSON
          </button>
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/16 disabled:opacity-60"
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            刷新数据
          </button>
          <div className="rounded-2xl border border-white/10 bg-white/8 px-4 py-3 text-xs leading-5 text-white/80">
            <p>最近同步：{lastUpdatedLabel}</p>
            <p className="mt-1">时间范围：{rangeLabel}</p>
            <p className="mt-1">当前筛选：{activeFilters.length ? activeFilters.join(" · ") : "全部"}</p>
            <p className="mt-1">当前接口：`/api/v1/bi/*`</p>
          </div>
        </div>
      </div>
    </section>
  );
}
