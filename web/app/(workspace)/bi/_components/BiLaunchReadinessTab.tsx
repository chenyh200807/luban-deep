/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { CheckCircle2, CircleAlert, Clock3, ShieldCheck, XCircle } from "lucide-react";
import type { BiLaunchReadinessDashboard, BiLaunchReadinessRow } from "@/lib/bi-api";
import { InfoLine, MetricCard, SectionHeader } from "./BiShared";

type BiLaunchReadinessTabProps = {
  dashboard: BiLaunchReadinessDashboard | null;
  loading: boolean;
  error: string;
  onRefresh: () => void;
};

const STATUS_TONE: Record<string, "good" | "warning" | "critical" | "neutral"> = {
  PASS: "good",
  WARN: "warning",
  FAIL: "critical",
  NOT_RUN: "critical",
  SKIP: "warning",
};

function statusTone(status?: string): "good" | "warning" | "critical" | "neutral" {
  return STATUS_TONE[String(status || "").toUpperCase()] ?? "neutral";
}

function statusIcon(status?: string) {
  const normalized = String(status || "").toUpperCase();
  if (normalized === "PASS") return CheckCircle2;
  if (normalized === "WARN" || normalized === "SKIP") return CircleAlert;
  if (normalized === "NOT_RUN") return Clock3;
  return XCircle;
}

function statusClass(status?: string) {
  const tone = statusTone(status);
  if (tone === "good") return "bg-emerald-100 text-emerald-700";
  if (tone === "warning") return "bg-amber-100 text-amber-700";
  if (tone === "critical") return "bg-rose-100 text-rose-700";
  return "bg-slate-100 text-slate-700";
}

function readinessLabel(status?: string, recommendation?: string) {
  if (!status) return "等待数据";
  if (status === "PASS" && recommendation === "canary") return "可以进入 canary";
  if (status === "WARN") return "有条件 hold";
  if (status === "FAIL") return "暂不发布";
  return status;
}

function countRows(rows: BiLaunchReadinessRow[], status: string) {
  return rows.filter((row) => String(row.status).toUpperCase() === status).length;
}

export function BiLaunchReadinessTab({ dashboard, loading, error, onRefresh }: BiLaunchReadinessTabProps) {
  const rows = dashboard?.rows ?? [];
  const passCount = countRows(rows, "PASS");
  const warnCount = countRows(rows, "WARN") + countRows(rows, "SKIP");
  const failCount = countRows(rows, "FAIL") + countRows(rows, "NOT_RUN");
  const finalTone = statusTone(dashboard?.final_status);

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="发布判定"
          value={readinessLabel(dashboard?.final_status, dashboard?.recommendation)}
          hint={dashboard?.run_id || (loading ? "正在读取 readiness control-plane" : "等待上线面板数据")}
          tone={finalTone}
          icon={ShieldCheck}
        />
        <MetricCard
          title="通过项"
          value={passCount}
          hint={rows.length ? `${rows.length} 个 readiness 项` : "暂无检查项"}
          tone="good"
          icon={CheckCircle2}
        />
        <MetricCard
          title="观察项"
          value={warnCount}
          hint="WARN / SKIP 需要发布前确认"
          tone={warnCount ? "warning" : "good"}
          icon={CircleAlert}
        />
        <MetricCard
          title="阻塞项"
          value={failCount}
          hint={dashboard?.blockers.length ? `${dashboard.blockers.length} 个 blocker` : "无 blocker"}
          tone={failCount ? "critical" : "good"}
          icon={XCircle}
        />
      </section>

      <section className="surface-card p-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <SectionHeader
            title="上线 readiness"
            extra={dashboard?.generated_at ? `生成时间 ${dashboard.generated_at}` : "等待 control-plane"}
          />
          <button
            type="button"
            onClick={onRefresh}
            disabled={loading}
            className="inline-flex items-center justify-center rounded-2xl border border-[var(--border)] bg-white px-4 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-[var(--secondary)] disabled:opacity-60"
          >
            {loading ? "刷新中..." : "刷新"}
          </button>
        </div>
        {error ? (
          <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p>
        ) : null}
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <InfoLine label="release" value={dashboard?.release.release_id || "--"} />
          <InfoLine label="git sha" value={dashboard?.release.git_sha || "--"} />
          <InfoLine label="environment" value={dashboard?.release.deployment_environment || "--"} />
          <InfoLine label="recommendation" value={dashboard?.recommendation || "--"} />
        </div>
      </section>

      <section className="grid gap-4">
        {rows.length ? (
          rows.map((row) => {
            const Icon = statusIcon(row.status);
            return (
              <article key={row.check_id} className="surface-card border border-[var(--border)]/60 bg-white/90 p-5">
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${statusClass(row.status)}`}>
                        <Icon size={14} />
                        {row.status}
                      </span>
                      <span className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">
                        {row.required ? "REQUIRED" : "OPTIONAL"}
                      </span>
                      {row.source_kind ? (
                        <span className="text-xs text-[var(--muted-foreground)]">{row.source_kind}</span>
                      ) : null}
                    </div>
                    <h3 className="mt-3 text-lg font-semibold tracking-tight text-[var(--foreground)]">{row.label}</h3>
                    <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">{row.summary || "暂无摘要"}</p>
                  </div>
                  <div className="min-w-[220px] rounded-2xl bg-[var(--secondary)] px-4 py-3 text-sm text-[var(--secondary-foreground)]">
                    <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">RUN</p>
                    <p className="mt-1 break-all font-medium">{row.run_id || "--"}</p>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <EvidenceList title="Evidence" items={row.evidence} emptyText="暂无证据行" />
                  <EvidenceList title="Blockers" items={row.blockers} emptyText="无 blocker" critical={row.blockers.length > 0} />
                </div>
              </article>
            );
          })
        ) : (
          <div className="surface-card p-5 text-sm text-[var(--muted-foreground)]">
            {loading ? "正在加载上线 readiness 面板。" : "暂无 readiness rows。"}
          </div>
        )}
      </section>
    </div>
  );
}

function EvidenceList({
  title,
  items,
  emptyText,
  critical = false,
}: {
  title: string;
  items: string[];
  emptyText: string;
  critical?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)]/60 bg-[var(--background)] px-4 py-3">
      <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">{title}</p>
      {items.length ? (
        <ul className="mt-3 space-y-2">
          {items.slice(0, 5).map((item) => (
            <li
              key={item}
              className={`break-words rounded-xl px-3 py-2 text-xs leading-5 ${
                critical ? "bg-rose-50 text-rose-700" : "bg-[var(--secondary)] text-[var(--secondary-foreground)]"
              }`}
            >
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-xl bg-[var(--secondary)] px-3 py-2 text-xs text-[var(--muted-foreground)]">{emptyText}</p>
      )}
    </div>
  );
}
