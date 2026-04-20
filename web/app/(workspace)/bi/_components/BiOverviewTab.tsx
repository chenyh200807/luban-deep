/* eslint-disable i18n/no-literal-ui-text */
"use client";

import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  BookOpen,
  BrainCircuit,
  Database,
  Sparkles,
  Target,
  TimerReset,
  UserRound,
  Wallet,
} from "lucide-react";
import type {
  BiCapabilityData,
  BiCostData,
  BiKnowledgeData,
  BiMemberData,
  BiMetricCard,
  BiToolData,
  BiTrendData,
  BiTutorBotData,
  BiWorkbenchData,
} from "@/lib/bi-api";
import {
  AlertCard,
  InfoLine,
  LegendDot,
  MetricCard,
  MiniStatCard,
  RankingCard,
  SectionHeader,
  SimpleListCard,
  createLoadingCards,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatTime,
  metricIconByIndex,
  metricToneClasses,
  sparkPath,
  toneClasses,
} from "./BiShared";

type BiOverviewTabProps = {
  loading: boolean;
  days: 7 | 30 | 90;
  overview?: BiWorkbenchData["overview"];
  trend: BiTrendData;
  retention: BiWorkbenchData["retention"];
  anomalies: BiWorkbenchData["anomalies"];
  capabilities: BiCapabilityData;
  tools: BiToolData;
  knowledge: BiKnowledgeData;
  members: BiMemberData;
  cost: BiCostData;
  tutorbots: BiTutorBotData;
  onOpenLearnerDetail: (sample: { user_id: string; display_name: string }) => void;
};

export function BiOverviewTab({
  loading,
  days,
  overview,
  trend,
  retention,
  anomalies,
  capabilities,
  tools,
  knowledge,
  members,
  cost,
  tutorbots,
  onOpenLearnerDetail,
}: BiOverviewTabProps) {
  const topCards = [...(overview?.cards ?? []), ...cost.cards, ...members.cards, ...tutorbots.cards].slice(0, 6);
  const trendSeries = trend.points.map((point) => point.active);
  const trendCostSeries = trend.points.map((point) => point.cost);
  const trendSuccessSeries = trend.points.map((point) => point.successful);

  return (
    <>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        {(loading ? createLoadingCards() : topCards).map((card, index) => (
          <MetricCard
            key={`${card.label}-${index}`}
            title={card.label}
            value={card.value}
            hint={card.hint ?? ""}
            delta={card.delta}
            tone={card.tone}
            icon={metricIconByIndex(index)}
          />
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)]">
        <div className="space-y-6">
          <div className="surface-card p-5">
            <SectionHeader
              title="趋势与波动"
              extra={trend.points.length ? `${trend.points.length} 个周期` : "等待趋势数据"}
            />
            <div className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_320px]">
              <TrendChart
                points={trend.points}
                activeSeries={trendSeries}
                costSeries={trendCostSeries}
                successSeries={trendSuccessSeries}
                days={days}
              />
              <div className="space-y-3">
                {(overview?.highlights ?? []).slice(0, 4).map((item) => (
                  <div key={item} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                    <p className="text-[11px] tracking-[0.18em] text-[var(--muted-foreground)]">洞察</p>
                    <p className="mt-1 text-sm leading-6 text-[var(--secondary-foreground)]">{item}</p>
                  </div>
                ))}
                {!overview?.highlights?.length ? (
                  <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                    后端尚未返回洞察文本，趋势会在接口就绪后自动显示。
                  </p>
                ) : null}
              </div>
            </div>
          </div>

          <div className="surface-card p-5">
            <SectionHeader title="留存矩阵" extra={retention.labels.join(" / ") || "D0 / D1 / D7 / D30"} />
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

          <div className="surface-card p-5">
            <SectionHeader
              title="异常中心"
              extra={anomalies.items.length ? `${anomalies.items.length} 条异常` : "无明显异常"}
            />
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {(anomalies.items.length ? anomalies.items : overview?.alerts ?? []).map((item) => (
                <AlertCard key={`${item.title}-${item.detail ?? ""}`} item={item} />
              ))}
              {!anomalies.items.length && !(overview?.alerts ?? []).length ? (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  后端没有返回告警，当前仅展示数据总览。
                </p>
              ) : null}
            </div>
          </div>
        </div>

        <aside className="space-y-6">
          <OverviewStack overview={overview} cost={cost} members={members} />
          <RankingCard
            title="经营入口分布"
            items={overview?.entrypoints ?? []}
            emptyText="等待入口分布数据。"
          />
          <SimpleListCard
            title="成本结构"
            items={cost.models.length ? cost.models : cost.providers}
            emptyText="等待成本与模型结构数据。"
            icon={<Wallet size={16} />}
          />
        </aside>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div className="space-y-6">
          <div className="surface-card p-5">
            <SectionHeader title="TutorBot 指标" extra={tutorbots.cards.length ? `${tutorbots.cards.length} 项` : "等待指标"} />
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {tutorbots.cards.length ? (
                tutorbots.cards.slice(0, 4).map((card) => (
                  <MiniStatCard key={card.label} label={card.label} value={card.value} hint={card.hint} />
                ))
              ) : (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  后端返回 TutorBot 指标后，这里会展示运行、成功率、调用量等关键数据。
                </p>
              )}
            </div>
          </div>

          <RankingCard
            title="TutorBot 排行"
            items={tutorbots.ranking}
            emptyText="等待 TutorBot 排行数据。"
            icon={<Bot size={16} />}
            headerMeta={tutorbots.cards.length ? `${tutorbots.cards.length} 个指标` : undefined}
          />
          <div className="surface-card p-5">
            <SectionHeader title="最近活跃" extra={tutorbots.recentActive.length ? `${tutorbots.recentActive.length} 个样本` : "等待活跃样本"} />
            <div className="mt-4 space-y-3">
              {tutorbots.recentActive.length ? (
                tutorbots.recentActive.slice(0, 5).map((bot) => (
                  <BotActiveCard key={bot.bot_id || bot.name} bot={bot} />
                ))
              ) : (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  后端返回 TutorBot 最近活跃后，这里会展示运行状态、入口与最新活动时间。
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <RankingCard
            title="运行状态"
            items={tutorbots.statusBreakdown}
            emptyText="等待 TutorBot 运行状态。"
            icon={<Activity size={16} />}
          />
          <div className="surface-card p-5">
            <SectionHeader
              title="最近消息预览"
              extra={tutorbots.recentMessages.length ? `${tutorbots.recentMessages.length} 条` : "等待消息预览"}
            />
            <div className="mt-4 space-y-3">
              {tutorbots.recentMessages.length ? (
                tutorbots.recentMessages.slice(0, 5).map((bot) => (
                  <BotMessageCard key={bot.bot_id || bot.name || bot.recent_message} bot={bot} />
                ))
              ) : (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  后端返回最近消息预览后，这里会展示近期对话摘要。
                </p>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <RankingCard
          title="能力表现"
          items={capabilities.items}
          emptyText="等待 capability 数据。"
          icon={<BrainCircuit size={16} />}
          footerItems={capabilities.upgradePaths}
          footerTitle="升级路径"
        />
        <RankingCard
          title="工具效果"
          items={tools.items}
          emptyText="等待 tool 数据。"
          icon={<Sparkles size={16} />}
          footerItems={tools.efficiency}
          footerTitle="效率/ROI"
        />
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <RankingCard
          title="知识库表现"
          items={knowledge.items}
          emptyText="等待知识库分析数据。"
          icon={<BookOpen size={16} />}
          headerMeta={knowledge.zeroHitRate !== undefined ? `零结果率 ${formatPercent(knowledge.zeroHitRate)}` : undefined}
          footerItems={knowledge.topQueries}
          footerTitle="热查询"
        />
        <div className="space-y-6">
          <div className="surface-card p-5">
            <SectionHeader title="知识库策略" extra="面向内容资产与召回质量" />
            <div className="mt-4 space-y-3 text-sm leading-6 text-[var(--secondary-foreground)]">
              <InfoLine
                label="命中率"
                value={knowledge.items.length ? "关注高频 KB 的零结果率变化" : "等待后端指标"}
              />
              <InfoLine
                label="文档资产"
                value="建议后续把教材、题库、规范、TutorBot 素材统一纳入资产榜单。"
              />
              <InfoLine
                label="学习闭环"
                value="优先看 notebook 保存率与知识库查询后的后续行为变化。"
              />
            </div>
          </div>

          <div className="surface-card p-5">
            <SectionHeader
              title="会员与用户画像"
              extra={members.samples.length ? `${members.samples.length} 个样本` : "等待会员分层数据"}
            />
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {members.cards.length
                ? members.cards.slice(0, 4).map((card) => (
                    <MiniStatCard key={card.label} label={card.label} value={card.value} hint={card.hint} />
                  ))
                : null}
              {!members.cards.length ? (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  会员侧数据将显示活跃、到期、风险和续费相关卡片。
                </p>
              ) : null}
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <RankingCard
                title="会员分层"
                items={members.tiers}
                emptyText="等待会员层级数据。"
                compact
              />
              <RankingCard
                title="风险分层"
                items={members.risks}
                emptyText="等待风险分层数据。"
                compact
              />
            </div>
            <div className="mt-4 space-y-3">
              {members.samples.slice(0, 4).map((sample) => (
                <button
                  key={sample.user_id || sample.display_name}
                  type="button"
                  onClick={() => {
                    if (!sample.user_id) return;
                    onOpenLearnerDetail({ user_id: sample.user_id, display_name: sample.display_name });
                  }}
                  className="w-full rounded-2xl border bg-[var(--background)] px-4 py-3 text-left transition hover:-translate-y-0.5 hover:border-[var(--primary)]/30 hover:shadow-[0_10px_28px_rgba(45,33,25,0.08)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-[var(--foreground)]">{sample.display_name}</p>
                      <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                        {sample.user_id || "--"} · {sample.last_active_at ? formatTime(sample.last_active_at) : "最近活跃待补全"}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {sample.tier ? <span className="muted-chip">{sample.tier}</span> : null}
                      {sample.risk_level ? (
                        <span className={`muted-chip ${toneClasses(sample.risk_level === "high" ? "critical" : sample.risk_level === "medium" ? "warning" : "info")}`}>
                          {sample.risk_level}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {sample.detail ? <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{sample.detail}</p> : null}
                  <div className="mt-3 inline-flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                    <UserRound size={13} />
                    点击查看 Learner 360
                  </div>
                </button>
              ))}
              {!members.samples.length ? (
                <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  后端返回会员样本后，这里会展示高价值、风险和续费窗口用户。
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <SimpleListCard
          title="成本与模型"
          items={cost.models}
          emptyText="等待成本模型明细。"
          icon={<TimerReset size={16} />}
          footer={cost.providers.length ? `来源 ${cost.providers.length} 个` : undefined}
        />
        <SimpleListCard
          title="成本来源"
          items={cost.providers}
          emptyText="等待成本来源拆分。"
          icon={<Database size={16} />}
        />
        <SimpleListCard
          title="总览提示"
          items={(overview?.alerts ?? []).map((item) => ({
            label: item.title,
            value: 0,
            hint: item.detail,
          }))}
          emptyText="后端暂无提示。"
          icon={<Target size={16} />}
        />
      </section>
    </>
  );
}

function OverviewStack({
  overview,
  cost,
  members,
}: {
  overview?: BiWorkbenchData["overview"];
  cost: BiCostData;
  members: BiMemberData;
}) {
  const cards: Array<Pick<BiMetricCard, "label" | "value" | "hint" | "tone" | "delta">> = [
    ...(overview?.alerts ?? []).slice(0, 2).map((item) => ({
      label: item.title,
      value: 0,
      hint: item.detail,
      tone: "warning" as const,
    })),
    ...cost.cards.slice(0, 2),
    ...members.cards.slice(0, 2),
  ];

  return (
    <div className="surface-card p-5">
      <SectionHeader title="经营总览" extra={overview?.subtitle ? "经营 / 学习 / 成本" : undefined} />
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        {cards.length ? (
          cards.slice(0, 6).map((card) => (
            <div key={card.label} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs text-[var(--muted-foreground)]">{card.label}</p>
                  <p className={`mt-1 text-xl font-semibold tracking-tight ${metricToneClasses(card.tone)}`}>
                    {formatNumber(card.value)}
                  </p>
                </div>
                {card.delta ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-white/70 px-2 py-1 text-[11px] text-[var(--secondary-foreground)]">
                    {card.delta.startsWith("-") ? <ArrowDownRight size={12} /> : <ArrowUpRight size={12} />}
                    {card.delta}
                  </span>
                ) : null}
              </div>
              {card.hint ? <p className="mt-2 text-xs leading-5 text-[var(--muted-foreground)]">{card.hint}</p> : null}
            </div>
          ))
        ) : (
          <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
            等待 BI 总览卡片。
          </p>
        )}
      </div>

      <div className="mt-4 space-y-3">
        {(overview?.alerts ?? []).slice(0, 3).map((alert) => (
          <div key={alert.title} className="rounded-2xl border bg-[var(--background)] px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-2">
                <span className={`mt-0.5 inline-flex rounded-full px-2 py-1 text-[11px] ${toneClasses(alert.level)}`}>
                  {alert.level}
                </span>
                <div>
                  <p className="font-medium text-[var(--foreground)]">{alert.title}</p>
                  {alert.detail ? <p className="mt-1 text-sm leading-5 text-[var(--muted-foreground)]">{alert.detail}</p> : null}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrendChart({
  points,
  activeSeries,
  costSeries,
  successSeries,
  days,
}: {
  points: BiTrendData["points"];
  activeSeries: number[];
  costSeries: number[];
  successSeries: number[];
  days: number;
}) {
  const activePath = sparkPath(activeSeries, 420, 160);
  const costPath = sparkPath(costSeries, 420, 160);
  const successPath = sparkPath(successSeries, 420, 160);
  const activeMin = Math.min(...activeSeries, 0);
  const activeSpan = Math.max(Math.max(...activeSeries, 1) - activeMin, 1);

  return (
    <div className="rounded-2xl border border-[var(--border)]/60 bg-[var(--background)] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">{days} 天趋势</p>
          <p className="mt-1 text-sm text-[var(--secondary-foreground)]">活跃、成本与成功结果同屏对比。</p>
        </div>
        <div className="flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
          <LegendDot color="#C35A2C" label="活跃" />
          <LegendDot color="#0f766e" label="成本" />
          <LegendDot color="#6d28d9" label="成功" />
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl bg-[linear-gradient(180deg,rgba(195,90,44,0.04),rgba(255,255,255,0.6))] p-3">
        {points.length ? (
          <svg viewBox="0 0 420 160" className="h-[240px] w-full">
            <defs>
              <linearGradient id="activeFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#C35A2C" stopOpacity="0.24" />
                <stop offset="100%" stopColor="#C35A2C" stopOpacity="0.02" />
              </linearGradient>
            </defs>
            <path d={`${activePath} L 420 160 L 0 160 Z`} fill="url(#activeFill)" />
            <path d={activePath} fill="none" stroke="#C35A2C" strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" />
            <path d={costPath} fill="none" stroke="#0f766e" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
            <path d={successPath} fill="none" stroke="#6d28d9" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
            {points.map((point, index) => {
              const x = (index / Math.max(points.length - 1, 1)) * 420;
              const y = 160 - ((point.active - activeMin) / activeSpan) * 152 - 4;
              return <circle key={point.label} cx={x} cy={y} r={3} fill="#C35A2C" />;
            })}
          </svg>
        ) : (
          <div className="flex h-[240px] items-center justify-center text-sm text-[var(--muted-foreground)]">
            等待趋势数据。
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        {points.slice(-3).map((point) => (
          <div key={point.label} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
            <p className="text-xs text-[var(--muted-foreground)]">{point.label}</p>
            <div className="mt-2 grid grid-cols-3 gap-2 text-sm">
              <span className="text-[var(--secondary-foreground)]">活跃 {formatNumber(point.active)}</span>
              <span className="text-[var(--secondary-foreground)]">成本 {formatCurrency(point.cost)}</span>
              <span className="text-[var(--secondary-foreground)]">成功 {formatPercent(point.successful)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function BotActiveCard({
  bot,
}: {
  bot: {
    bot_id: string;
    name: string;
    capability?: string;
    entrypoint?: string;
    tier?: string;
    status?: string;
    last_active_at?: string;
    detail?: string;
  };
}) {
  return (
    <div className="rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-[var(--foreground)]">{bot.name}</p>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
            {bot.bot_id || "--"} · {bot.last_active_at ? formatTime(bot.last_active_at) : "最近活跃待补全"}
          </p>
        </div>
        {bot.status ? (
          <span className={`muted-chip ${toneClasses(bot.status === "critical" ? "critical" : bot.status === "warning" ? "warning" : "info")}`}>
            {bot.status}
          </span>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {bot.capability ? <span className="muted-chip">{bot.capability}</span> : null}
        {bot.entrypoint ? <span className="muted-chip">{bot.entrypoint}</span> : null}
        {bot.tier ? <span className="muted-chip">{bot.tier}</span> : null}
      </div>
      {bot.detail ? <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{bot.detail}</p> : null}
    </div>
  );
}

function BotMessageCard({
  bot,
}: {
  bot: { bot_id: string; name: string; recent_message?: string; last_active_at?: string; capability?: string; entrypoint?: string; tier?: string };
}) {
  return (
    <div className="rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-[var(--foreground)]">{bot.name}</p>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
            {bot.capability || "chat"} · {bot.entrypoint || "unknown"} · {bot.tier || "unknown"}
          </p>
        </div>
        <span className="text-xs text-[var(--muted-foreground)]">
          {bot.last_active_at ? formatTime(bot.last_active_at) : "--"}
        </span>
      </div>
      <p className="mt-3 line-clamp-3 text-sm leading-6 text-[var(--secondary-foreground)]">
        {bot.recent_message || "等待消息预览"}
      </p>
    </div>
  );
}
