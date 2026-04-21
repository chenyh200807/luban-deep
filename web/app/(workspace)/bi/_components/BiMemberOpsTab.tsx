/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { Crown, ShieldAlert, Sparkles, UserRound, Wallet, type LucideIcon } from "lucide-react";
import type { BiCostData, BiMemberData, BiMetricCard, BiRetentionData, BiWorkbenchData } from "@/lib/bi-api";
import {
  InfoLine,
  MetricCard,
  MiniStatCard,
  RankingCard,
  SectionHeader,
  SimpleListCard,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatTime,
  toneClasses,
} from "./BiShared";

type BiMemberOpsTabProps = {
  loading?: boolean;
  overview?: BiWorkbenchData["overview"];
  members: BiMemberData;
  cost: BiCostData;
  retention: BiRetentionData;
  onOpenLearnerDetail: (sample: { user_id: string; display_name: string }) => void;
};

const MEMBER_CARD_ICONS: LucideIcon[] = [Crown, UserRound, ShieldAlert, Wallet];

export function BiMemberOpsTab({
  loading = false,
  overview,
  members,
  cost,
  retention,
  onOpenLearnerDetail,
}: BiMemberOpsTabProps) {
  const topCards = buildMemberOpsCards({ loading, members, cost, overview });
  const leadTier = members.tiers[0];
  const leadRisk = members.risks[0];
  const leadModel = cost.models[0] ?? cost.providers[0];
  const leadHighlight = overview?.highlights?.[0];
  const leadEntrypoint = overview?.entrypoints?.[0];
  const sampleCount = members.samples.length;

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {topCards.map((card, index) => (
          <MetricCard
            key={`${card.label}-${index}`}
            title={card.label}
            value={card.value}
            hint={card.hint}
            delta={card.delta}
            tone={card.tone}
            icon={MEMBER_CARD_ICONS[index] ?? Wallet}
          />
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div className="space-y-6">
          <div className="surface-card p-5">
            <SectionHeader title="会员分层与风险" extra={sampleCount ? `${sampleCount} 个样本可下钻` : "等待会员样本"} />
            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <MiniStatCard
                label="会员样本"
                value={sampleCount}
                hint={sampleCount ? "可直接打开 Learner 360" : "等待样本"}
              />
              <MiniStatCard
                label="主要分层"
                value={leadTier?.label ?? "--"}
                hint={leadTier ? `${formatNumber(leadTier.value)} 人` : "等待 tier 数据"}
              />
              <MiniStatCard
                label="主要风险"
                value={leadRisk?.label ?? "--"}
                hint={leadRisk ? `${formatNumber(leadRisk.value)} 人` : "等待风险数据"}
              />
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <RankingCard title="会员分层" items={members.tiers} emptyText="等待会员层级数据。" compact />
              <RankingCard title="风险分层" items={members.risks} emptyText="等待风险分层数据。" compact />
            </div>
          </div>

          <div className="surface-card p-5">
            <SectionHeader title="重点样本入口" extra={sampleCount ? "点击进入 Learner 360" : "等待重点样本"} />
            <div className="mt-4 space-y-3">
              {members.samples.length ? (
                members.samples.slice(0, 6).map((sample) => {
                  const disabled = !sample.user_id;
                  return (
                    <button
                      key={sample.user_id || sample.display_name}
                      type="button"
                      disabled={disabled}
                      onClick={() => {
                        if (disabled) return;
                        onOpenLearnerDetail({ user_id: sample.user_id, display_name: sample.display_name });
                      }}
                      className="w-full rounded-2xl border bg-[var(--background)] px-4 py-3 text-left transition hover:-translate-y-0.5 hover:border-[var(--primary)]/30 hover:shadow-[0_10px_28px_rgba(45,33,25,0.08)] disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="font-medium text-[var(--foreground)]">{sample.display_name}</p>
                          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                            {sample.user_id || "--"} ·{" "}
                            {sample.last_active_at ? formatTime(sample.last_active_at) : "最近活跃待补全"}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center justify-end gap-2">
                          {sample.tier ? <span className="muted-chip">{sample.tier}</span> : null}
                          {sample.status ? <span className="muted-chip">{sample.status}</span> : null}
                          {sample.risk_level ? (
                            <span
                              className={`muted-chip ${toneClasses(
                                sample.risk_level === "high"
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
                      </div>
                      {sample.detail ? (
                        <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{sample.detail}</p>
                      ) : null}
                      <div className="mt-3 inline-flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                        <UserRound size={13} />
                        {disabled ? "当前样本缺少 user_id，暂不能打开 Learner 360" : "点击查看 Learner 360"}
                      </div>
                    </button>
                  );
                })
              ) : (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  后端返回会员样本后，这里会展示高价值、风险和续费窗口用户，并保留 Learner 360 入口。
                </p>
              )}
            </div>
          </div>

          <div className="surface-card p-5">
            <SectionHeader
              title="留存矩阵"
              extra={retention.labels.length ? retention.labels.join(" / ") : "D0 / D1 / D7 / D30"}
            />
            <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--border)]/60 bg-[var(--background)]">
              <div className="grid grid-cols-[160px_repeat(4,minmax(0,1fr))] border-b border-[var(--border)]/60 bg-[var(--secondary)]/40 px-4 py-3 text-xs tracking-[0.18em] text-[var(--muted-foreground)]">
                <span>队列</span>
                {(retention.labels.length ? retention.labels : ["D0", "D1", "D7", "D30"]).map((label) => (
                  <span key={label} className="text-right">
                    {label}
                  </span>
                ))}
              </div>
              <div className="divide-y divide-[var(--border)]/50">
                {retention.cohorts.length ? (
                  retention.cohorts.map((row) => (
                    <div key={row.label} className="grid grid-cols-[160px_repeat(4,minmax(0,1fr))] gap-0 px-4 py-3">
                      <div className="pr-4">
                        <p className="font-medium text-[var(--foreground)]">{row.label}</p>
                      </div>
                      {(retention.labels.length ? retention.labels : ["D0", "D1", "D7", "D30"]).map((label, index) => {
                        const value = row.values[index] ?? 0;
                        const intensity = Math.max(0.08, Math.min(1, value / 100));
                        return (
                          <div key={`${row.label}-${label}`} className="flex justify-end">
                            <span
                              className="inline-flex min-w-[84px] justify-center rounded-xl px-3 py-2 text-sm font-medium"
                              style={{
                                backgroundColor: `rgba(195, 90, 44, ${intensity * 0.22 + 0.04})`,
                                color: intensity > 0.45 ? "var(--foreground)" : "var(--muted-foreground)",
                              }}
                            >
                              {formatPercent(value)}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ))
                ) : (
                  <div className="px-4 py-10 text-center text-sm text-[var(--muted-foreground)]">
                    等待留存接口返回 cohort 数据。
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="surface-card p-5">
            <SectionHeader title="经营洞察" extra="只使用 members / cost / overview 现有信号" />
            <div className="mt-4 space-y-3">
              <InfoLine
                label="会员盘面"
                value={
                  leadTier
                    ? `${leadTier.label} ${formatNumber(leadTier.value)} 人${leadTier.rate !== undefined ? ` · ${formatPercent(leadTier.rate)}` : ""}`
                    : "等待会员分层返回主要层级。"
                }
              />
              <InfoLine
                label="风险焦点"
                value={
                  leadRisk
                    ? `${leadRisk.label} ${formatNumber(leadRisk.value)} 人${leadRisk.hint ? ` · ${leadRisk.hint}` : ""}`
                    : "等待风险榜单，暂无法判断续费/流失压力。"
                }
              />
              <InfoLine
                label="成本提醒"
                value={
                  leadModel
                    ? `${leadModel.label} ${describeRankValue(leadModel.value)}${leadModel.hint ? ` · ${leadModel.hint}` : ""}`
                    : "等待成本结构数据，暂无法观察会员经营成本压力。"
                }
              />
              <InfoLine
                label="主要入口"
                value={
                  leadEntrypoint
                    ? `${leadEntrypoint.label} ${formatNumber(leadEntrypoint.value)}${leadEntrypoint.hint ? ` · ${leadEntrypoint.hint}` : ""}`
                    : "等待总览入口分布，用于判断会员获取/活跃来源。"
                }
              />
            </div>

            <div className="mt-4 grid gap-3">
              {(overview?.highlights?.slice(0, 3) ?? []).map((item, index) => (
                <div
                  key={`${item}-${index}`}
                  className="rounded-2xl border border-[var(--border)]/60 bg-[linear-gradient(135deg,rgba(195,90,44,0.08),rgba(255,255,255,0.92))] px-4 py-4"
                >
                  <p className="text-[11px] tracking-[0.18em] text-[var(--muted-foreground)]">
                    INSIGHT {String(index + 1).padStart(2, "0")}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{item}</p>
                </div>
              ))}
              {!overview?.highlights?.length ? (
                <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  暂无经营洞察文本返回，后续会优先展示会员风险、续费窗口和成本变化建议。
                </div>
              ) : null}
            </div>

            <div className="mt-4 rounded-2xl bg-[linear-gradient(135deg,rgba(22,19,17,0.96),rgba(64,39,28,0.94),rgba(143,70,37,0.86))] px-4 py-4 text-white">
              <div className="flex items-start gap-3">
                <div className="rounded-2xl bg-white/12 p-2 text-white">
                  <Sparkles size={16} />
                </div>
                <div>
                  <p className="text-xs tracking-[0.18em] text-white/70">NEXT FOCUS</p>
                  <p className="mt-2 text-sm leading-6 text-white/85">
                    {leadHighlight ??
                      "先用会员分层、风险榜单和重点样本，把经营关注点收敛到具体人群，再结合成本结构判断资源倾斜。"}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <SimpleListCard
            title="会员经营成本结构"
            items={cost.models.length ? cost.models : cost.providers}
            emptyText="等待成本模型或供应商结构数据。"
            icon={<Wallet size={16} />}
            footer={cost.providers.length ? `${cost.providers.length} 个 provider` : undefined}
          />
        </div>
      </section>
    </div>
  );
}

function buildMemberOpsCards({
  loading,
  members,
  cost,
  overview,
}: {
  loading: boolean;
  members: BiMemberData;
  cost: BiCostData;
  overview?: BiWorkbenchData["overview"];
}): BiMetricCard[] {
  if (loading) {
    return [
      { label: "活跃会员", value: "--", hint: "等待会员指标", tone: "neutral" },
      { label: "续费窗口", value: "--", hint: "等待会员指标", tone: "neutral" },
      { label: "风险会员", value: "--", hint: "等待风险指标", tone: "neutral" },
      { label: "经营成本", value: "--", hint: "等待成本指标", tone: "neutral" },
    ];
  }

  const uniqueCards: BiMetricCard[] = [];
  const seen = new Set<string>();

  [...members.cards, ...cost.cards, ...(overview?.cards ?? [])].forEach((card) => {
    const key = `${card.label}-${card.hint ?? ""}`;
    if (!card.label || seen.has(key) || uniqueCards.length >= 4) {
      return;
    }
    seen.add(key);
    uniqueCards.push(card);
  });

  if (uniqueCards.length) {
    return uniqueCards;
  }

  return [
    { label: "活跃会员", value: "--", hint: "等待会员指标", tone: "neutral" },
    { label: "续费窗口", value: "--", hint: "等待续费数据", tone: "neutral" },
    { label: "风险会员", value: "--", hint: "等待风险榜单", tone: "neutral" },
    { label: "经营成本", value: "--", hint: "等待成本结构", tone: "neutral" },
  ];
}

function describeRankValue(value: number) {
  if (value >= 1000) {
    return formatCurrency(value);
  }
  return formatNumber(value);
}
