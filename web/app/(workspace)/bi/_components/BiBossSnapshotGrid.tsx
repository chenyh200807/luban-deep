/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { BiMemberData, BiRetentionData, BiWorkbenchData } from "@/lib/bi-api";
import { formatNumber, formatPercent, InfoLine, MiniStatCard, SectionHeader } from "./BiShared";

type BiBossSnapshotGridProps = {
  overview?: BiWorkbenchData["overview"];
  retention: BiRetentionData;
  members: BiMemberData;
};

function RankLine({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-[var(--foreground)]">{label}</p>
          {hint ? <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">{hint}</p> : null}
        </div>
        <span className="text-sm font-semibold text-[var(--secondary-foreground)]">{value}</span>
      </div>
    </div>
  );
}

export function BiBossSnapshotGrid({ overview, retention, members }: BiBossSnapshotGridProps) {
  const memberTiers = members.tiers.slice(0, 3);
  const memberRisks = members.risks.slice(0, 2);
  const sampleCount = members.samples.length;
  const retentionLabels = retention.labels.length ? retention.labels : ["D0", "D1", "D7", "D30"];
  const retentionRows = retention.cohorts.slice(0, 2);
  const entrypoints = (overview?.entrypoints ?? []).slice(0, 3);
  const topHighlight = (overview?.highlights ?? [])[0] ?? "";

  return (
    <section className="grid gap-6 xl:grid-cols-3">
      <div className="surface-card p-5">
        <SectionHeader title="会员分层" extra={sampleCount ? `${sampleCount} 个重点样本` : "等待会员样本"} />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {members.cards.slice(0, 2).map((card) => (
            <MiniStatCard key={card.label} label={card.label} value={card.value} hint={card.hint} />
          ))}
          {!members.cards.length ? (
            <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)] sm:col-span-2">
              会员 KPI 暂未返回，空数组保持为正常空态。
            </div>
          ) : null}
        </div>

        <div className="mt-4 space-y-2">
          {memberTiers.length ? (
            memberTiers.map((item) => <RankLine key={item.label} label={item.label} value={formatNumber(item.value)} hint={item.hint} />)
          ) : (
            <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)]">
              会员分层还没有返回。
            </div>
          )}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {memberRisks.length ? (
            memberRisks.map((item) => (
              <InfoLine key={item.label} label={item.label} value={item.hint || item.secondary || formatNumber(item.value)} />
            ))
          ) : (
            <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)] sm:col-span-2">
              当前没有风险分层信号。
            </div>
          )}
        </div>
      </div>

      <div className="surface-card p-5">
        <SectionHeader title="留存" extra={retentionLabels.join(" / ") || "D0 / D1 / D7 / D30"} />
        <div className="mt-4 space-y-3">
          <InfoLine
            label="队列数"
            value={retention.cohorts.length ? `${retention.cohorts.length} 个 cohort` : "等待 cohort"}
          />
          <InfoLine
            label="最近样本"
            value={retentionRows.length ? retentionRows[0]?.label || "已返回" : "空数组不视为失败"}
          />
          <InfoLine
            label="覆盖窗口"
            value={retentionLabels.length ? retentionLabels.join(" / ") : "D0 / D1 / D7 / D30"}
          />
        </div>

        <div className="mt-4 space-y-2">
          {retentionRows.length ? (
            retentionRows.map((row) => (
              <div key={row.label} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-[var(--foreground)]">{row.label}</p>
                  <span className="text-xs text-[var(--muted-foreground)]">{row.values.length} 列</span>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {row.values.slice(0, 4).map((value, index) => (
                    <div key={`${row.label}-${index}`} className="rounded-xl bg-white/70 px-3 py-2 text-sm text-[var(--secondary-foreground)]">
                      <span className="text-[11px] tracking-[0.16em] text-[var(--muted-foreground)]">
                        {retentionLabels[index] ?? `D${index}`}
                      </span>
                      <div className="mt-1 font-medium">{formatPercent(value)}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))
          ) : (
            <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)]">
              当前没有留存 cohort。
            </div>
          )}
        </div>
      </div>

      <div className="surface-card p-5">
        <SectionHeader title="渠道" extra={entrypoints.length ? `${entrypoints.length} 个来源` : "等待渠道数据"} />
        <div className="mt-4 space-y-3">
          <InfoLine
            label="经营摘要"
            value={topHighlight || overview?.subtitle || "后端尚未返回渠道摘要。"}
          />
          <InfoLine
            label="入口数量"
            value={overview?.entrypoints.length ? `${overview.entrypoints.length} 个入口` : "空数组不视为失败"}
          />
          <InfoLine
            label="可见渠道"
            value={entrypoints.length ? entrypoints.map((item) => item.label).join(" / ") : "等待 top entrypoints"}
          />
        </div>

        <div className="mt-4 space-y-2">
          {entrypoints.length ? (
            entrypoints.map((item) => (
              <RankLine
                key={item.label}
                label={item.label}
                value={formatNumber(item.value)}
                hint={item.hint || item.secondary}
              />
            ))
          ) : (
            <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm leading-6 text-[var(--muted-foreground)]">
              渠道摘要还没有返回。
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
