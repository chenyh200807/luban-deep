/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiBossKpiItem } from "@/lib/bi-api";
import { createLoadingCards, metricIconByIndex, MetricCard, SectionHeader } from "./BiShared";

type BiBossKpisProps = {
  loading: boolean;
  kpis: BiBossKpiItem[];
};

export function BiBossKpis({ loading, kpis }: BiBossKpisProps) {
  const cards = loading ? createLoadingCards() : kpis.slice(0, 6);

  return (
    <section className="space-y-4">
      <SectionHeader title="经营 KPI" extra={cards.length ? `${cards.length} 项已接入` : "等待经营聚合"} />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        {cards.length ? (
          cards.map((card, index) => (
            <MetricCard
              key={`${card.label}-${index}`}
              title={card.label}
              value={card.value}
              hint={card.hint ?? ""}
              delta={card.delta}
              tone={card.tone}
              icon={metricIconByIndex(index)}
            />
          ))
        ) : (
          <div className="surface-card col-span-full border-0 bg-white/88 p-5 text-sm text-[var(--muted-foreground)] shadow-[0_10px_30px_rgba(45,33,25,0.06)]">
            当前没有可展示的经营 KPI，接口返回空数组不视为异常。
          </div>
        )}
      </div>
    </section>
  );
}
