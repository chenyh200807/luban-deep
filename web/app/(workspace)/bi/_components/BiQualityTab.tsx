/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { Activity, CircleAlert, Database, ShieldAlert, TrendingUp } from "lucide-react";
import type { BiAlertItem, BiTrendData, BiWorkbenchData } from "@/lib/bi-api";
import {
  AlertCard,
  InfoLine,
  LegendDot,
  MetricCard,
  MiniStatCard,
  SectionHeader,
  formatCurrency,
  formatNumber,
  formatPercent,
  metricToneClasses,
  sparkPath,
} from "./BiShared";

type BiQualityTabProps = {
  trend: BiTrendData;
  anomalies: BiWorkbenchData["anomalies"];
  overview?: BiWorkbenchData["overview"];
  issues: string[];
};

type QualityAlert = BiAlertItem & {
  source: "anomaly" | "overview";
};

export function BiQualityTab({ trend, anomalies, overview, issues }: BiQualityTabProps) {
  const allAlerts: QualityAlert[] = [
    ...anomalies.items.map((item) => ({ ...item, source: "anomaly" as const })),
    ...(overview?.alerts ?? []).map((item) => ({ ...item, source: "overview" as const })),
  ];
  const successRates = trend.points.map((point) => toRate(point.successful));
  const costSeries = trend.points.map((point) => point.cost);
  const activeSeries = trend.points.map((point) => point.active);
  const activePath = sparkPath(activeSeries, 420, 160);
  const costPath = sparkPath(costSeries, 420, 160);
  const successPath = sparkPath(successRates, 420, 160);
  const maxSuccessSwing = getAdjacentSwing(successRates);
  const maxCostSwing = getAdjacentSwing(costSeries);
  const maxActiveSwing = getAdjacentSwing(activeSeries);
  const avgRecentSuccess =
    successRates.length > 0
      ? successRates.slice(-Math.min(3, successRates.length)).reduce((sum, value) => sum + value, 0) /
        Math.min(3, successRates.length)
      : undefined;
  const stablePeriods = successRates.filter((rate) => rate >= 0.8).length;
  const criticalCount = allAlerts.filter((item) => item.level === "critical").length;
  const warningCount = allAlerts.filter((item) => item.level === "warning").length;
  const dataCoverageItems = [
    {
      label: "趋势数据",
      ready: trend.points.length > 0,
      value: trend.points.length ? `${trend.points.length} 个周期` : "未返回",
    },
    {
      label: "异常列表",
      ready: true,
      value: anomalies.items.length ? `${anomalies.items.length} 条` : "0 条",
    },
    {
      label: "总览 alerts",
      ready: true,
      value: (overview?.alerts ?? []).length ? `${overview?.alerts.length ?? 0} 条` : "0 条",
    },
    {
      label: "降级接口",
      ready: issues.length === 0,
      value: issues.length ? `${issues.length} 个` : "无",
    },
  ];
  const readyCount = dataCoverageItems.filter((item) => item.ready).length;
  const healthTone: "good" | "warning" | "critical" =
    issues.length || criticalCount ? "critical" : warningCount || (avgRecentSuccess ?? 1) < 0.8 ? "warning" : "good";
  const healthSummary =
    issues.length || criticalCount
      ? "当前质量面板显示显著告警或接口降级，优先检查异常与依赖数据源。"
      : warningCount || (avgRecentSuccess ?? 1) < 0.8
        ? "存在波动与观察项，建议结合异常中心继续跟踪。"
        : "当前质量信号相对稳定，可继续观察趋势是否延续。";

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="最近成功率"
          value={avgRecentSuccess === undefined ? "--" : formatPercent(avgRecentSuccess)}
          hint={trend.points.length ? "默认取最近 3 个周期平均值" : "等待趋势数据"}
          tone={avgRecentSuccess !== undefined && avgRecentSuccess < 0.8 ? "warning" : "good"}
          icon={ShieldAlert}
        />
        <MetricCard
          title="稳定周期占比"
          value={trend.points.length ? `${stablePeriods}/${trend.points.length}` : "--"}
          hint="以成功率 >= 80% 视为稳定周期"
          tone={trend.points.length && stablePeriods < trend.points.length / 2 ? "warning" : "good"}
          icon={TrendingUp}
        />
        <MetricCard
          title="异常与告警"
          value={allAlerts.length}
          hint={
            allAlerts.length
              ? `critical ${criticalCount} / warning ${warningCount}`
              : "当前无异常或 alerts"
          }
          tone={criticalCount ? "critical" : warningCount ? "warning" : "good"}
          icon={CircleAlert}
        />
        <MetricCard
          title="数据完整性"
          value={`${readyCount}/${dataCoverageItems.length}`}
          hint={issues.length ? `${issues.length} 个接口降级` : "当前无降级接口"}
          tone={issues.length ? "critical" : readyCount < dataCoverageItems.length ? "warning" : "good"}
          icon={Database}
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <div className="surface-card p-5">
          <SectionHeader title="趋势波动" extra={trend.points.length ? `${trend.points.length} 个周期` : "等待趋势数据"} />
          <div className="mt-4 rounded-2xl border border-[var(--border)]/60 bg-[var(--background)] p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">SUCCESS TREND</p>
                <p className="mt-1 text-sm text-[var(--secondary-foreground)]">
                  仅用现有 trend 数据观察成功率、成本和活跃波动。
                </p>
              </div>
              <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
                <LegendDot color="#6d28d9" label="成功率" />
                <LegendDot color="#0f766e" label="成本" />
                <LegendDot color="#C35A2C" label="活跃" />
              </div>
            </div>

            <div className="mt-4 overflow-hidden rounded-2xl bg-[linear-gradient(180deg,rgba(109,40,217,0.08),rgba(255,255,255,0.7))] p-3">
              {trend.points.length ? (
                <svg viewBox="0 0 420 160" className="h-[240px] w-full">
                  <path d={activePath} fill="none" stroke="#C35A2C" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
                  <path d={costPath} fill="none" stroke="#0f766e" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
                  <path d={successPath} fill="none" stroke="#6d28d9" strokeWidth="2.6" strokeLinejoin="round" strokeLinecap="round" />
                  {trend.points.map((point, index) => {
                    const x = (index / Math.max(trend.points.length - 1, 1)) * 420;
                    const y = 160 - (toRate(point.successful) / Math.max(...successRates, 0.01)) * 144 - 8;
                    return <circle key={point.label} cx={x} cy={y} r={3.2} fill="#6d28d9" />;
                  })}
                </svg>
              ) : (
                <div className="flex h-[240px] items-center justify-center text-sm text-[var(--muted-foreground)]">
                  等待趋势数据。
                </div>
              )}
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              <MiniStatCard
                label="成功率波动"
                value={trend.points.length ? formatPercent(maxSuccessSwing) : "--"}
                hint="相邻周期最大摆幅"
              />
              <MiniStatCard
                label="成本波动"
                value={trend.points.length ? formatCurrency(maxCostSwing) : "--"}
                hint="相邻周期最大成本摆幅"
              />
              <MiniStatCard
                label="活跃波动"
                value={trend.points.length ? formatNumber(maxActiveSwing) : "--"}
                hint="相邻周期最大活跃摆幅"
              />
            </div>

            <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {trend.points.slice(-4).map((point) => (
                <div key={point.label} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                  <p className="text-xs text-[var(--muted-foreground)]">{point.label}</p>
                  <p className={`mt-1 text-lg font-semibold ${metricToneClasses(toRate(point.successful) < 0.8 ? "warning" : "good")}`}>
                    {formatPercent(point.successful)}
                  </p>
                  <p className="mt-2 text-xs text-[var(--muted-foreground)]">
                    活跃 {formatNumber(point.active)} · 成本 {formatCurrency(point.cost)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="surface-card p-5">
            <SectionHeader title="降级 / 数据完整性" extra={issues.length ? `${issues.length} 个接口降级` : "当前无降级"} />
            <div className="mt-4 space-y-3">
              <InfoLine label="整体判定" value={healthSummary} />
              {dataCoverageItems.map((item) => (
                <InfoLine
                  key={item.label}
                  label={item.label}
                  value={item.ready ? item.value : `${item.value} · 待补齐`}
                />
              ))}
              {issues.length ? (
                <InfoLine label="首个降级提示" value={issues[0] ?? "未知错误"} />
              ) : (
                <InfoLine label="接口状态" value="当前页面未检测到聚合接口降级。" />
              )}
            </div>
          </div>

          <div className="surface-card p-5">
            <SectionHeader title="质量摘要" extra={healthTone === "critical" ? "需要优先关注" : "持续观察"} />
            <div className="mt-4 space-y-3">
              <QualitySummaryCard
                title="异常优先级"
                tone={criticalCount ? "critical" : warningCount ? "warning" : "good"}
                content={
                  allAlerts.length
                    ? `critical ${criticalCount} 条，warning ${warningCount} 条，总计 ${allAlerts.length} 条异常/告警。`
                    : "当前未收到异常或 overview alerts。"
                }
              />
              <QualitySummaryCard
                title="稳定性判断"
                tone={avgRecentSuccess !== undefined && avgRecentSuccess < 0.8 ? "warning" : "good"}
                content={
                  avgRecentSuccess === undefined
                    ? "趋势数据尚未返回，暂时无法判断稳定周期。"
                    : `最近成功率均值 ${formatPercent(avgRecentSuccess)}，稳定周期 ${stablePeriods}/${trend.points.length || 0}。`
                }
              />
              <QualitySummaryCard
                title="降级影响"
                tone={issues.length ? "critical" : readyCount < dataCoverageItems.length ? "warning" : "good"}
                content={
                  issues.length
                    ? "页面已进入自动降级展示，质量判断需结合缺失接口一起解读。"
                    : "当前未触发聚合接口降级，质量信号可直接使用。"
                }
              />
            </div>
          </div>
        </div>
      </section>

      <section className="surface-card p-5">
        <SectionHeader title="异常与告警清单" extra={allAlerts.length ? `${allAlerts.length} 条` : "当前为空"} />
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {allAlerts.length ? (
            allAlerts.map((item) => (
              <div key={`${item.source}-${item.title}-${item.detail ?? ""}`} className="space-y-2">
                <div className="flex items-center gap-2 text-[11px] tracking-[0.18em] text-[var(--muted-foreground)]">
                  <span className="rounded-full bg-[var(--secondary)] px-2 py-1">
                    {item.source === "anomaly" ? "ANOMALY" : "OVERVIEW ALERT"}
                  </span>
                </div>
                <AlertCard item={item} />
              </div>
            ))
          ) : (
            <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
              当前没有可展示的异常或告警，质量面板会继续等待后端返回更多信号。
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

function QualitySummaryCard({
  title,
  tone,
  content,
}: {
  title: string;
  tone: "good" | "warning" | "critical";
  content: string;
}) {
  return (
    <div className="rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-[var(--foreground)]">{title}</p>
          <p className="mt-1 text-sm leading-6 text-[var(--muted-foreground)]">{content}</p>
        </div>
        <span className={`rounded-full px-2 py-1 text-[11px] ${tone === "critical" ? "bg-rose-100 text-rose-700" : tone === "warning" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
          {tone}
        </span>
      </div>
    </div>
  );
}

function toRate(value: number) {
  return value > 1 ? value / 100 : value;
}

function getAdjacentSwing(values: number[]) {
  if (values.length < 2) return 0;
  let maxSwing = 0;
  for (let index = 1; index < values.length; index += 1) {
    maxSwing = Math.max(maxSwing, Math.abs(values[index] - values[index - 1]));
  }
  return maxSwing;
}
