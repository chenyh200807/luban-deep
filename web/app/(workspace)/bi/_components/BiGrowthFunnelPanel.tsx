/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiGrowthFunnelPayload } from "@/lib/bi-api";
import { formatNumber, SectionHeader } from "./BiShared";

type BiGrowthFunnelPanelProps = {
  payload?: BiGrowthFunnelPayload;
};

export function BiGrowthFunnelPanel({ payload }: BiGrowthFunnelPanelProps) {
  if (!payload) {
    return null;
  }

  return (
    <section className="surface-card p-5">
      <SectionHeader title="增长漏斗" extra={`${payload.steps.length} 步`} />
      <p className="mt-3 text-sm leading-6 text-[var(--muted-foreground)]">{payload.summary}</p>
      <div className="mt-5 space-y-3">
        {payload.steps.map((step, index) => (
          <div key={step.id} className="rounded-2xl border border-[var(--border)]/60 bg-white/80 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-[var(--foreground)]">{index + 1}. {step.label}</p>
                <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                  {step.authority} · 可信 {step.trustLevel || "--"}
                </p>
              </div>
              <div className="text-right">
                <p className="text-2xl font-semibold text-[var(--foreground)]">{formatNumber(step.value)}</p>
                <p className="text-xs text-[var(--muted-foreground)]">转化 {formatNumber(step.conversionRate)}%</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
