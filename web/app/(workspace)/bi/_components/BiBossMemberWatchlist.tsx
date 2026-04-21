/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { ChevronRight, UserRound } from "lucide-react";
import type { BiMemberData } from "@/lib/bi-api";
import { formatTime, SectionHeader, toneClasses } from "./BiShared";

type BiBossMemberWatchlistProps = {
  members: BiMemberData;
  onOpenLearnerDetail: (sample: { user_id: string; display_name: string }) => void;
};

function riskRank(value?: string) {
  const normalized = (value ?? "").toLowerCase();
  if (normalized.includes("critical") || normalized.includes("high")) return 0;
  if (normalized.includes("medium") || normalized.includes("warn")) return 1;
  if (normalized.includes("low")) return 2;
  return 3;
}

export function BiBossMemberWatchlist({ members, onOpenLearnerDetail }: BiBossMemberWatchlistProps) {
  const samples = [...members.samples]
    .sort((a, b) => {
      const riskDelta = riskRank(a.risk_level) - riskRank(b.risk_level);
      if (riskDelta !== 0) return riskDelta;
      const aTime = a.last_active_at ? Date.parse(a.last_active_at) : 0;
      const bTime = b.last_active_at ? Date.parse(b.last_active_at) : 0;
      return bTime - aTime;
    })
    .slice(0, 6);

  return (
    <section className="surface-card p-5">
      <SectionHeader title="重点会员 watchlist" extra={samples.length ? `${samples.length} 个重点样本` : "等待重点会员"} />
      <div className="mt-4 space-y-3">
        {samples.length ? (
          samples.map((sample) => (
            <button
              key={sample.user_id || sample.display_name}
              type="button"
              onClick={() => {
                if (!sample.user_id) return;
                onOpenLearnerDetail({ user_id: sample.user_id, display_name: sample.display_name });
              }}
              className="w-full rounded-2xl border border-[var(--border)]/60 bg-[var(--background)] px-4 py-3 text-left transition hover:-translate-y-0.5 hover:border-[var(--primary)]/30 hover:shadow-[0_10px_28px_rgba(45,33,25,0.08)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-medium text-[var(--foreground)]">{sample.display_name}</p>
                    {sample.tier ? <span className="muted-chip">{sample.tier}</span> : null}
                    {sample.status ? <span className="muted-chip">{sample.status}</span> : null}
                    {sample.risk_level ? (
                      <span
                        className={`muted-chip ${toneClasses(
                          sample.risk_level === "high" || sample.risk_level === "critical"
                            ? "critical"
                            : sample.risk_level === "medium"
                              ? "warning"
                              : "info",
                        )}`}
                      >
                        {sample.risk_level}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                    {sample.user_id || "--"} · {sample.last_active_at ? formatTime(sample.last_active_at) : "最近活跃待补全"}
                  </p>
                </div>
                <ChevronRight size={16} className="mt-1 shrink-0 text-[var(--muted-foreground)]" />
              </div>

              {sample.detail ? <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{sample.detail}</p> : null}
              <div className="mt-3 inline-flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                <UserRound size={13} />
                点击查看 Learner 360
              </div>
            </button>
          ))
        ) : (
          <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)]">
            当前没有重点会员样本，空列表不视为失败。
          </div>
        )}
      </div>
    </section>
  );
}
