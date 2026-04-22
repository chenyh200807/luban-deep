/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiBossActionItem } from "@/lib/bi-api";
import { ShieldAlert } from "lucide-react";
import { SectionHeader, toneClasses } from "./BiShared";

type BiBossActionQueueProps = {
  heroIssue: string;
  actionQueue: BiBossActionItem[];
  onNavigate: (item?: BiBossActionItem) => void;
};

function sourceLabel(source?: BiBossActionItem["source"]) {
  if (source === "anomalies") return "异常";
  if (source === "members") return "会员";
  if (source === "cost") return "成本";
  return "待处理";
}

export function BiBossActionQueue({ heroIssue, actionQueue, onNavigate }: BiBossActionQueueProps) {
  const items = actionQueue.slice(0, 4);

  return (
    <section className="surface-card h-full p-5">
      <div className="flex items-start justify-between gap-3">
        <SectionHeader title="右侧混合待处理区" extra={items.length ? `${items.length} 条待办` : "当前没有待处理项"} />
        <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
          <ShieldAlert size={16} />
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {heroIssue ? (
          <div className="rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-sm text-amber-800">
            {heroIssue}
          </div>
        ) : null}

        {items.length ? (
          items.map((item) => (
            <button
              key={`${item.title}-${item.detail}`}
              type="button"
              onClick={() => onNavigate(item)}
              className="w-full rounded-2xl border border-[var(--border)]/60 bg-[var(--background)] px-4 py-3 text-left transition hover:-translate-y-0.5 hover:border-[var(--primary)]/30 hover:shadow-[0_10px_28px_rgba(45,33,25,0.08)]"
            >
              <div className="flex items-start gap-3">
                <span className={`mt-0.5 inline-flex rounded-full px-2 py-1 text-[11px] ${toneClasses(item.tone)}`}>
                  {sourceLabel(item.source)}
                </span>
                <div className="min-w-0">
                  <p className="font-medium text-[var(--foreground)]">{item.title}</p>
                  <p className="mt-1 text-sm leading-6 text-[var(--muted-foreground)]">{item.detail}</p>
                </div>
              </div>
            </button>
          ))
        ) : heroIssue ? null : (
          <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)]">
            当前没有混合待处理项，空队列不视为异常。
          </div>
        )}
      </div>
    </section>
  );
}
