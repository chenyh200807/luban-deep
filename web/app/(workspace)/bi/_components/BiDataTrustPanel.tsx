/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiDataTrustPayload, BiOperatingRhythmPayload } from "@/lib/bi-api";
import { Database } from "lucide-react";
import { SectionHeader } from "./BiShared";

type BiDataTrustPanelProps = {
  dataTrust?: BiDataTrustPayload;
  operatingRhythm?: BiOperatingRhythmPayload;
};

export function BiDataTrustPanel({ dataTrust, operatingRhythm }: BiDataTrustPanelProps) {
  if (!dataTrust && !operatingRhythm) {
    return null;
  }

  return (
    <section className="surface-card p-5">
      <div className="flex items-start justify-between gap-3">
        <SectionHeader title="数据可信与经营节奏" extra={dataTrust?.status || "等待数据"} />
        <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
          <Database size={16} />
        </div>
      </div>
      <p className="mt-3 text-sm leading-6 text-[var(--muted-foreground)]">
        {dataTrust?.trustModel || "核心指标必须先说明口径、来源、可信等级和可下钻对象。"}
      </p>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          {(dataTrust?.degradedModules ?? []).slice(0, 4).map((item) => (
            <div key={item.id} className="rounded-2xl border border-[var(--border)]/60 bg-white/80 px-4 py-3">
              <p className="font-medium text-[var(--foreground)]">{item.label}</p>
              <p className="mt-1 text-sm leading-6 text-[var(--muted-foreground)]">{item.detail}</p>
            </div>
          ))}
        </div>
        <div className="space-y-3">
          {(operatingRhythm?.topActions ?? []).slice(0, 3).map((item) => (
            <div key={`${item.title}-${item.target}`} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
              <p className="font-medium text-[var(--foreground)]">{item.title}</p>
              <p className="mt-1 text-sm text-[var(--muted-foreground)]">{item.reason}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
