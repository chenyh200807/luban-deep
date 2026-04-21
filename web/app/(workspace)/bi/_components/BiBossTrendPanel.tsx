/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiTrendData, BiWorkbenchData } from "@/lib/bi-api";
import { formatCurrency, formatNumber, formatPercent, sparkPath, LegendDot, SectionHeader } from "./BiShared";

type BiBossTrendPanelProps = {
  loading: boolean;
  days: 7 | 30 | 90;
  trend: BiTrendData;
  overview?: BiWorkbenchData["overview"];
  issue?: string;
};

export function BiBossTrendPanel({ loading, days, trend, overview, issue }: BiBossTrendPanelProps) {
  const points = trend.points;
  const activeSeries = points.map((point) => point.active);
  const costSeries = points.map((point) => point.cost);
  const successSeries = points.map((point) => point.successful);
  const activePath = sparkPath(activeSeries, 540, 180);
  const costPath = sparkPath(costSeries, 540, 180);
  const successPath = sparkPath(successSeries, 540, 180);
  const activeMin = Math.min(...activeSeries, 0);
  const activeSpan = Math.max(Math.max(...activeSeries, 1) - activeMin, 1);
  const latestPoints = points.slice(-3);
  const highlights = (overview?.highlights ?? []).slice(0, 3);

  return (
    <section id="boss-trend-panel" className="surface-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeader title="主趋势图" extra={points.length ? `${points.length} 个周期` : loading ? "加载中" : "等待趋势数据"} />
        <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
          <LegendDot color="#C35A2C" label="活跃" />
          <LegendDot color="#0f766e" label="成本" />
          <LegendDot color="#6d28d9" label="成功" />
        </div>
      </div>
      {issue ? (
        <div className="mt-4 rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-sm text-amber-800">
          经营趋势模块暂未完整返回：{issue}
        </div>
      ) : null}

      <div className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.8fr)]">
        <div className="rounded-2xl border border-[var(--border)]/60 bg-[linear-gradient(180deg,rgba(195,90,44,0.04),rgba(255,255,255,0.74))] p-4">
          {points.length ? (
            <>
              <svg viewBox="0 0 540 180" className="h-[260px] w-full">
                <defs>
                  <linearGradient id="bossActiveFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#C35A2C" stopOpacity="0.24" />
                    <stop offset="100%" stopColor="#C35A2C" stopOpacity="0.02" />
                  </linearGradient>
                </defs>
                <path d={`${activePath} L 540 180 L 0 180 Z`} fill="url(#bossActiveFill)" />
                <path d={activePath} fill="none" stroke="#C35A2C" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" />
                <path d={costPath} fill="none" stroke="#0f766e" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
                <path d={successPath} fill="none" stroke="#6d28d9" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
                {points.map((point, index) => {
                  const x = (index / Math.max(points.length - 1, 1)) * 540;
                  const y = 180 - ((point.active - activeMin) / activeSpan) * 168 - 4;
                  return <circle key={point.label} cx={x} cy={y} r={3} fill="#C35A2C" />;
                })}
              </svg>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {latestPoints.map((point) => (
                  <div key={point.label} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                    <p className="text-xs text-[var(--muted-foreground)]">{point.label}</p>
                    <div className="mt-2 grid gap-1 text-sm text-[var(--secondary-foreground)]">
                      <span>活跃 {formatNumber(point.active)}</span>
                      <span>成本 {formatCurrency(point.cost)}</span>
                      <span>成功 {formatPercent(point.successful)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="flex h-[360px] items-center justify-center rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
              {loading ? "趋势正在加载" : "当前没有趋势数据，空数组不视为异常。"}
            </div>
          )}
        </div>

        <aside className="space-y-3">
          <div className="rounded-2xl border border-[var(--border)]/60 bg-[var(--background)] px-4 py-3">
            <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">{days} 天视图</p>
            <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">
              这一块只负责老板判断趋势，不把 TutorBot、工具、知识库重新拉回一级叙事。
            </p>
          </div>

          <div className="space-y-3">
            {highlights.length ? (
              highlights.map((item) => (
                <div key={item} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                  <p className="text-[11px] tracking-[0.18em] text-[var(--muted-foreground)]">洞察</p>
                  <p className="mt-1 text-sm leading-6 text-[var(--secondary-foreground)]">{item}</p>
                </div>
              ))
            ) : (
              <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)]">
                后端尚未返回趋势洞察，先保留趋势图与最新周期的原始信号。
              </div>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
