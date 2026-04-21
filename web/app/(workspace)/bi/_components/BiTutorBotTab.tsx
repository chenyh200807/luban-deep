/* eslint-disable i18n/no-literal-ui-text */
"use client";

import {
  Activity,
  Bot,
  BrainCircuit,
  MessageSquareText,
  Radar,
  Sparkles,
  Database,
  ShieldAlert,
} from "lucide-react";
import type {
  BiCapabilityData,
  BiCostData,
  BiKnowledgeData,
  BiToolData,
  BiTutorBotData,
  BiTutorBotItem,
  BiWorkbenchData,
} from "@/lib/bi-api";
import {
  InfoLine,
  MetricCard,
  MiniStatCard,
  RankingCard,
  SectionHeader,
  SimpleListCard,
  formatNumber,
  formatPercent,
  formatTime,
  metricIconByIndex,
  toneClasses,
} from "./BiShared";

type BiTutorBotTabProps = {
  days: 7 | 30 | 90;
  overview?: BiWorkbenchData["overview"];
  tutorbots: BiTutorBotData;
  capabilities: BiCapabilityData;
  tools: BiToolData;
  knowledge: BiKnowledgeData;
  cost: BiCostData;
};

export function BiTutorBotTab({
  days,
  overview,
  tutorbots,
  capabilities,
  tools,
  knowledge,
  cost,
}: BiTutorBotTabProps) {
  const metricCards = tutorbots.cards.slice(0, 6);
  const activitySamples = tutorbots.recentActive.slice(0, 6);
  const messageSamples = tutorbots.recentMessages.slice(0, 6);
  const watchItems = (overview?.alerts ?? []).slice(0, 4);
  const highlightItems = (overview?.highlights ?? []).slice(0, 3);

  return (
    <>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        {metricCards.length ? (
          metricCards.map((card, index) => (
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
          <article className="surface-card col-span-full overflow-hidden border-0 bg-[linear-gradient(135deg,rgba(33,26,21,0.96),rgba(65,42,30,0.94),rgba(195,90,44,0.82))] p-6 text-white shadow-[0_24px_60px_rgba(31,26,23,0.16)]">
            <p className="text-xs tracking-[0.22em] text-white/70">TUTORBOT COMMAND DECK</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">运行指标就绪后，这里直接接管 TutorBot 主视图</h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-white/78">
              当前没有返回 TutorBot 指标卡片，页面仍保留排行、状态、最近活跃、最近消息和能力/工具联动位，等 BI 聚合接口补齐后会自动落到同一条指挥链。
            </p>
          </article>
        )}
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,0.95fr)]">
        <div className="space-y-6">
          <div className="surface-card p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <SectionHeader
                  title="运行态总览"
                  extra={tutorbots.statusBreakdown.length ? `${tutorbots.statusBreakdown.length} 个状态切片` : `${days} 天窗口`}
                />
                <p className="mt-3 text-sm leading-6 text-[var(--secondary-foreground)]">
                  用同一屏同时看运行指标、状态分布和近期活跃，避免 TutorBot 数据继续埋在 Overview 里。
                </p>
              </div>
              <div className="rounded-2xl bg-[linear-gradient(135deg,rgba(195,90,44,0.14),rgba(143,70,37,0.1))] p-3 text-[var(--primary)]">
                <Radar size={18} />
              </div>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
              <div className="grid gap-3 sm:grid-cols-2">
                {tutorbots.statusBreakdown.length ? (
                  tutorbots.statusBreakdown.slice(0, 4).map((item) => (
                    <MiniStatCard
                      key={item.label}
                      label={item.label}
                      value={item.value}
                      hint={item.rate !== undefined ? `占比 ${formatPercent(item.rate)}` : item.hint}
                    />
                  ))
                ) : (
                  <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)] sm:col-span-2">
                    当前没有状态分布样本，先保持 TutorBot 运行视图空态，不把空数组误判成异常。
                  </div>
                )}
              </div>

              <div className="rounded-[28px] border border-[var(--border)]/60 bg-[linear-gradient(180deg,rgba(195,90,44,0.08),rgba(255,255,255,0.86))] p-5">
                <p className="text-xs tracking-[0.2em] text-[var(--muted-foreground)]">WATCH LIST</p>
                <div className="mt-3 space-y-3">
                  {watchItems.length ? (
                    watchItems.map((item) => (
                      <div key={`${item.title}-${item.detail ?? ""}`} className="rounded-2xl bg-white/80 px-4 py-3">
                        <div className="flex items-start gap-3">
                          <span className={`mt-0.5 inline-flex rounded-full px-2 py-1 text-[11px] ${toneClasses(item.level)}`}>
                            {item.level}
                          </span>
                          <div>
                            <p className="font-medium text-[var(--foreground)]">{item.title}</p>
                            {item.detail ? (
                              <p className="mt-1 text-sm leading-5 text-[var(--muted-foreground)]">{item.detail}</p>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-2xl bg-white/80 px-4 py-4 text-sm text-[var(--muted-foreground)]">
                      当前没有总览级告警，TutorBot 主线保持 clean state。
                    </div>
                  )}

                  {highlightItems.length ? (
                    <div className="rounded-2xl border border-[var(--border)]/60 bg-white/70 px-4 py-4">
                      <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">观察摘要</p>
                      <div className="mt-3 space-y-2">
                        {highlightItems.map((item) => (
                          <p key={item} className="text-sm leading-6 text-[var(--secondary-foreground)]">
                            {item}
                          </p>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <RankingCard
            title="TutorBot 排行"
            items={tutorbots.ranking}
            emptyText="当前没有 TutorBot 排行样本。"
            icon={<Bot size={16} />}
            headerMeta={metricCards.length ? `${metricCards.length} 个关键指标已接入` : undefined}
          />

          <div className="surface-card p-5">
            <SectionHeader
              title="最近活跃"
              extra={activitySamples.length ? `${activitySamples.length} 个样本` : "当前没有活跃样本"}
            />
            <div className="mt-4 space-y-3">
              {activitySamples.length ? (
                activitySamples.map((bot) => <TutorBotActiveCard key={bot.bot_id || bot.name} bot={bot} />)
              ) : (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  当前没有最近活跃样本，说明这段时间没有可展示的 TutorBot 活动，不等同于数据加载失败。
                </p>
              )}
            </div>
          </div>
        </div>

        <aside className="space-y-6">
          <RankingCard
            title="运行状态"
            items={tutorbots.statusBreakdown}
            emptyText="当前没有 TutorBot 状态分布。"
            icon={<Activity size={16} />}
          />

          <div className="surface-card p-5">
            <SectionHeader
              title="最近消息"
              extra={messageSamples.length ? `${messageSamples.length} 条样本` : "当前没有消息样本"}
            />
            <div className="mt-4 space-y-3">
              {messageSamples.length ? (
                messageSamples.map((bot) => (
                  <TutorBotMessageCard key={bot.bot_id || bot.name || bot.recent_message} bot={bot} />
                ))
              ) : (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  当前没有最近消息摘要，后端返回样本后会直接展示最近对话切片。
                </p>
              )}
            </div>
          </div>

          <div className="surface-card p-5">
            <div className="flex items-start justify-between gap-3">
              <SectionHeader title="知识库副面板" extra={knowledge.items.length ? `${knowledge.items.length} 个知识源` : "副面板"} />
              <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
                <Database size={16} />
              </div>
            </div>
            <div className="mt-4 space-y-3">
              <InfoLine
                label="零结果率"
                value={knowledge.zeroHitRate !== undefined ? formatPercent(knowledge.zeroHitRate) : "暂无"}
              />
              <InfoLine
                label="主要用途"
                value={knowledge.items.length ? "作为 TutorBot 的知识命中副视图，不单独抢一级导航" : "等待知识库表现数据"}
              />
              <InfoLine
                label="联动关注"
                value={knowledge.topQueries.length ? "优先看高频查询后的消息质量与成功率变化" : "等待高频查询返回"}
              />
            </div>
            <div className="mt-4">
              <SimpleListCard
                title="知识命中"
                items={knowledge.items}
                emptyText="当前没有知识命中样本。"
                icon={<Database size={16} />}
                footer={knowledge.topQueries.length ? `热查询 ${knowledge.topQueries.length} 条` : undefined}
              />
            </div>
          </div>
        </aside>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(320px,0.82fr)]">
        <RankingCard
          title="能力联动"
          items={capabilities.items}
          emptyText="当前没有 capability 联动数据。"
          icon={<BrainCircuit size={16} />}
          footerItems={capabilities.upgradePaths}
          footerTitle="升级路径"
        />
        <RankingCard
          title="工具联动"
          items={tools.items}
          emptyText="当前没有 tool 联动数据。"
          icon={<Sparkles size={16} />}
          footerItems={tools.efficiency}
          footerTitle="效率/ROI"
        />
        <div className="surface-card p-5">
          <div className="flex items-start justify-between gap-3">
            <SectionHeader title="动作建议" extra={`${days} 天窗口`} />
            <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
              <ShieldAlert size={16} />
            </div>
          </div>
          <div className="mt-4 space-y-3 text-sm leading-6 text-[var(--secondary-foreground)]">
            <InfoLine
              label="主观察"
              value={tutorbots.ranking.length ? "优先对比高运行量 Bot 的成功率与状态分布是否同步恶化" : "等待排行样本后给出主观察"}
            />
            <InfoLine
              label="能力侧"
              value={capabilities.upgradePaths.length ? "把高调用 TutorBot 优先映射到升级路径最清晰的 capability" : "等待升级路径返回"}
            />
            <InfoLine
              label="工具侧"
              value={tools.efficiency.length ? "工具效率波动时，回看最近消息与知识命中是否同时变差" : "等待工具效率返回"}
            />
            <InfoLine
              label="知识侧"
              value={knowledge.zeroHitRate !== undefined ? "知识库只做副面板，重点盯零结果率对消息质量的拖累" : "等待知识库零结果率"}
            />
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <SimpleListCard
          title="成本摘要"
          items={cost.models.length ? cost.models : cost.providers}
          emptyText="当前没有成本结构样本。"
          icon={<Database size={16} />}
          footer={cost.providers.length ? `${cost.providers.length} 个 provider` : undefined}
        />
        <div className="surface-card p-5">
          <SectionHeader title="成本联动提醒" extra="知识库与能力之外的运行约束" />
          <div className="mt-4 space-y-3">
            <InfoLine
              label="成本主项"
              value={
                cost.models[0]
                  ? `${cost.models[0].label} ${formatNumber(cost.models[0].value)}`
                  : cost.providers[0]
                    ? `${cost.providers[0].label} ${formatNumber(cost.providers[0].value)}`
                    : "等待成本结构返回"
              }
            />
            <InfoLine
              label="运营建议"
              value={
                cost.models.length || cost.providers.length
                  ? "把高成本模型与高运行量 TutorBot 排行对照，优先定位 ROI 异常的 Bot。"
                  : "当前没有成本样本，先用 TutorBot 运行与知识命中视图完成一阶判断。"
              }
            />
            <InfoLine
              label="副面板定位"
              value="成本只做 TutorBot 主线的约束面板，不再回到一级导航。"
            />
          </div>
        </div>
      </section>
    </>
  );
}

function TutorBotActiveCard({ bot }: { bot: BiTutorBotItem }) {
  const tone = getBotTone(bot.status);

  return (
    <div className="rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-[var(--foreground)]">{bot.name || bot.bot_id || "TutorBot"}</p>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
            {bot.bot_id || "--"} · {bot.last_active_at ? formatTime(bot.last_active_at) : "最近活跃暂无时间戳"}
          </p>
        </div>
        {bot.status ? <span className={`muted-chip ${toneClasses(tone)}`}>{bot.status}</span> : null}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {bot.capability ? <span className="muted-chip">{bot.capability}</span> : null}
        {bot.entrypoint ? <span className="muted-chip">{bot.entrypoint}</span> : null}
        {bot.tier ? <span className="muted-chip">{bot.tier}</span> : null}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <InfoLine label="运行量" value={bot.runs !== undefined ? formatNumber(bot.runs) : "暂无"} />
        <InfoLine
          label="成功率"
          value={bot.success_rate !== undefined ? formatPercent(bot.success_rate) : "暂无"}
        />
      </div>

      {bot.detail ? <p className="mt-3 text-sm leading-6 text-[var(--secondary-foreground)]">{bot.detail}</p> : null}
    </div>
  );
}

function TutorBotMessageCard({ bot }: { bot: BiTutorBotItem }) {
  return (
    <div className="rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <div className="rounded-full bg-[var(--secondary)] p-1.5 text-[var(--primary)]">
              <MessageSquareText size={14} />
            </div>
            <p className="font-medium text-[var(--foreground)]">{bot.name || bot.bot_id || "TutorBot"}</p>
          </div>
          <p className="mt-2 text-xs text-[var(--muted-foreground)]">
            {bot.capability || "capability 暂无"} · {bot.entrypoint || "entrypoint 暂无"} · {bot.tier || "tier 暂无"}
          </p>
        </div>
        <span className="text-xs text-[var(--muted-foreground)]">
          {bot.last_active_at ? formatTime(bot.last_active_at) : "--"}
        </span>
      </div>

      <p className="mt-3 line-clamp-4 text-sm leading-6 text-[var(--secondary-foreground)]">
        {bot.recent_message || "当前没有最近消息预览。"}
      </p>
    </div>
  );
}

function getBotTone(status?: string) {
  if (!status) return "info";
  const normalized = status.toLowerCase();
  if (
    normalized.includes("critical") ||
    normalized.includes("error") ||
    normalized.includes("down") ||
    normalized.includes("fail")
  ) {
    return "critical";
  }
  if (
    normalized.includes("warning") ||
    normalized.includes("degraded") ||
    normalized.includes("busy") ||
    normalized.includes("slow")
  ) {
    return "warning";
  }
  return "info";
}
