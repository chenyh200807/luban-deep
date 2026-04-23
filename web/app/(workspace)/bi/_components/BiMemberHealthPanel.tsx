/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiMemberHealthPayload } from "@/lib/bi-api";
import { Activity } from "lucide-react";
import { formatNumber, SectionHeader } from "./BiShared";

type BiMemberHealthPanelProps = {
  payload?: BiMemberHealthPayload;
};

export function BiMemberHealthPanel({ payload }: BiMemberHealthPanelProps) {
  if (!payload) {
    return null;
  }
  const isDegraded = payload.score.trustLevel !== "A" && payload.score.trustLevel !== "B";

  return (
    <section className={`surface-card p-5 ${isDegraded ? "border border-amber-200/80 bg-amber-50/35" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <SectionHeader title="会员健康" extra={isDegraded ? "降级展示" : `可信 ${payload.score.trustLevel || "--"}`} />
        <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
          <Activity size={16} />
        </div>
      </div>
      <p className="mt-4 text-4xl font-semibold tracking-tight text-[var(--foreground)]">
        {isDegraded ? "降级展示" : payload.score.value === undefined ? "--" : formatNumber(payload.score.value)}
      </p>
      {isDegraded ? (
        <p className="mt-2 text-sm font-medium text-amber-700">
          这是 C 级透明规则评分，只能辅助排查风险，不作为老板首页正式健康结论。
        </p>
      ) : null}
      <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">{payload.score.note || payload.score.definition}</p>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {payload.distribution.map((item) => (
          <div key={item.bucket} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
            <p className="text-xs text-[var(--muted-foreground)]">{item.label}</p>
            <p className="mt-1 text-lg font-semibold">{formatNumber(item.count)}</p>
          </div>
        ))}
      </div>
      {payload.reasons.length ? (
        <ul className="mt-4 space-y-2 text-sm leading-6 text-[var(--muted-foreground)]">
          {payload.reasons.slice(0, 3).map((reason) => (
            <li key={reason}>- {reason}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
