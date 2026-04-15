/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Activity,
  Bot,
  BookOpen,
  BrainCircuit,
  CircleAlert,
  Download,
  Database,
  CalendarDays,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  TimerReset,
  UserRound,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import RestrictedSurface from "@/components/common/RestrictedSurface";
import Modal from "@/components/common/Modal";
import {
  getBiLearnerDetail,
  loadBiWorkbench,
  type BiLearnerDetailData,
  type BiMetricCard,
  type BiCostData,
  type BiMemberData,
  type BiTutorBotData,
  type BiTrendData,
  type BiWorkbenchData,
} from "@/lib/bi-api";
import { requiresWebAuth } from "@/lib/web-access";
import type { ReactNode } from "react";

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const numberFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

const currencyFormatter = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 2,
});

function formatNumber(value: number | string) {
  if (typeof value === "string") return value;
  if (!Number.isFinite(value)) return "--";
  if (Math.abs(value) >= 1000) return numberFormatter.format(value);
  return String(Math.round(value * 10) / 10);
}

function formatPercent(value?: number) {
  if (value === undefined || Number.isNaN(value)) return "--";
  if (value > 1) return `${numberFormatter.format(value)}%`;
  return `${numberFormatter.format(value * 100)}%`;
}

function formatCurrency(value?: number) {
  if (value === undefined || Number.isNaN(value)) return "--";
  return `¥${currencyFormatter.format(value)}`;
}

function formatTime(value?: string) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateFormatter.format(date);
}

function formatDuration(minutes?: number) {
  if (minutes === undefined || Number.isNaN(minutes)) return "--";
  if (minutes < 60) return `${Math.round(minutes)} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return `${hours} 小时${rest ? ` ${rest} 分钟` : ""}`;
}

function toneClasses(level?: string) {
  if (level === "critical") return "bg-rose-100 text-rose-700";
  if (level === "warning") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-700";
}

function metricToneClasses(tone?: string) {
  if (tone === "good") return "text-emerald-600";
  if (tone === "warning") return "text-amber-600";
  if (tone === "critical") return "text-rose-600";
  return "text-[var(--foreground)]";
}

const FILTER_OPTIONS = {
  capability: [
    { label: "全部 capability", value: "" },
    { label: "chat", value: "chat" },
    { label: "deep_solve", value: "deep_solve" },
    { label: "deep_question", value: "deep_question" },
    { label: "deep_research", value: "deep_research" },
  ],
  entrypoint: [
    { label: "全部 entrypoint", value: "" },
    { label: "wx_miniprogram", value: "wx_miniprogram" },
    { label: "chat", value: "chat" },
    { label: "app", value: "app" },
    { label: "web", value: "web" },
    { label: "local", value: "local" },
    { label: "tutorbot", value: "tutorbot" },
  ],
  tier: [
    { label: "全部 tier", value: "" },
    { label: "trial", value: "trial" },
    { label: "vip", value: "vip" },
    { label: "svip", value: "svip" },
  ],
} as const;

type BiFilterField = keyof typeof FILTER_OPTIONS;

function sparkPath(values: number[], width = 240, height = 72) {
  if (!values.length) return "";
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = Math.max(max - min, 1);
  return values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * width;
      const y = height - ((value - min) / span) * (height - 8) - 4;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

export default function BiPage() {
  if (!requiresWebAuth()) {
    return (
      <RestrictedSurface
        title="BI workspace unavailable"
        message="当前 Web 端未接入登录态，BI 工作台已默认关闭。请使用已鉴权入口访问。"
      />
    );
  }
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [filters, setFilters] = useState({ capability: "", entrypoint: "", tier: "" });
  const [data, setData] = useState<BiWorkbenchData | null>(null);
  const [issues, setIssues] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [selectedLearner, setSelectedLearner] = useState<{ user_id: string; display_name: string } | null>(null);
  const [learnerDetail, setLearnerDetail] = useState<BiLearnerDetailData | null>(null);
  const [learnerLoading, setLearnerLoading] = useState(false);
  const [learnerError, setLearnerError] = useState("");

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const result = await loadBiWorkbench({
        days,
        capability: filters.capability || undefined,
        entrypoint: filters.entrypoint || undefined,
        tier: filters.tier || undefined,
      });
      setData(result.data);
      setIssues(result.issues);
      setLastUpdatedAt(new Date().toISOString());
    } catch (error) {
      setIssues([error instanceof Error ? error.message : "BI 数据加载失败"]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [days, filters.capability, filters.entrypoint, filters.tier]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedLearner) {
      setLearnerDetail(null);
      setLearnerError("");
      setLearnerLoading(false);
      return;
    }

    let active = true;
    const run = async () => {
      try {
        setLearnerLoading(true);
        setLearnerError("");
        const detail = await getBiLearnerDetail(selectedLearner.user_id, { days });
        if (!active) return;
        setLearnerDetail(detail);
      } catch (error) {
        if (!active) return;
        setLearnerError(error instanceof Error ? error.message : "Learner 360 加载失败");
        setLearnerDetail(null);
      } finally {
        if (active) {
          setLearnerLoading(false);
        }
      }
    };

    void run();

    return () => {
      active = false;
    };
  }, [days, selectedLearner]);

  const overview = data?.overview;
  const trend = data?.trend ?? { points: [] };
  const retention = data?.retention ?? { cohorts: [], labels: ["D0", "D1", "D7", "D30"] };
  const capabilities = data?.capabilities ?? { items: [], upgradePaths: [] };
  const tools = data?.tools ?? { items: [], efficiency: [] };
  const knowledge = data?.knowledge ?? { items: [], topQueries: [] };
  const members = data?.members ?? { cards: [], tiers: [], risks: [], samples: [] };
  const cost = data?.cost ?? { cards: [], models: [], providers: [] };
  const tutorbots: BiTutorBotData =
    data?.tutorbots ?? { cards: [], ranking: [], statusBreakdown: [], recentActive: [], recentMessages: [] };
  const anomalies = data?.anomalies ?? { items: [] };

  const trendSeries = useMemo(
    () => trend.points.map((point) => point.active),
    [trend.points],
  );
  const trendCostSeries = useMemo(
    () => trend.points.map((point) => point.cost),
    [trend.points],
  );
  const trendSuccessSeries = useMemo(
    () => trend.points.map((point) => point.successful),
    [trend.points],
  );

  const heroTitle = overview?.title ?? "DeepTutor BI 工作台";
  const heroSubtitle =
    overview?.subtitle ??
    "加载后端 BI 接口后即可查看经营、学习、能力、知识库与会员的统一视图。";

  const topCards = useMemo(() => {
    const combined = [...(overview?.cards ?? []), ...(cost.cards ?? []), ...(members.cards ?? []), ...(tutorbots.cards ?? [])];
    return combined.slice(0, 6);
  }, [cost.cards, members.cards, overview?.cards, tutorbots.cards]);

  const activeFilters = [
    filters.capability ? `capability: ${filters.capability}` : "",
    filters.entrypoint ? `entrypoint: ${filters.entrypoint}` : "",
    filters.tier ? `tier: ${filters.tier}` : "",
  ].filter(Boolean);

  const rangeLabel = days === 7 ? "7 天" : days === 90 ? "90 天" : "30 天";
  const exportPayload = useMemo(
    () => ({
      exported_at: new Date().toISOString(),
      days,
      filters,
      last_updated_at: lastUpdatedAt,
      issues,
      data,
    }),
    [data, days, filters, issues, lastUpdatedAt],
  );

  const handleExport = useCallback(() => {
    setExporting(true);
    try {
      const fileName = `deeptutor-bi-${days}d-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
      const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = fileName;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [days, exportPayload]);

  const openLearnerDetail = useCallback((sample: { user_id: string; display_name: string }) => {
    setSelectedLearner(sample);
  }, []);

  const closeLearnerDetail = useCallback(() => {
    setSelectedLearner(null);
    setLearnerDetail(null);
    setLearnerError("");
  }, []);

  const updateFilter = useCallback((field: BiFilterField, value: string) => {
    setFilters((current) => ({
      ...current,
      [field]: value,
    }));
  }, []);

  const resetFilters = useCallback(() => {
    setFilters({ capability: "", entrypoint: "", tier: "" });
  }, []);

  return (
    <div className="h-full overflow-y-auto [scrollbar-gutter:stable] bg-[radial-gradient(circle_at_top_left,_rgba(195,90,44,0.14),_transparent_34%),radial-gradient(circle_at_85%_10%,_rgba(18,122,134,0.09),_transparent_28%),linear-gradient(180deg,#faf9f6_0%,#f4efe8_100%)] px-6 py-6">
      <div className="mx-auto flex max-w-[1540px] flex-col gap-6">
        <section className="surface-card overflow-hidden border-0 bg-[linear-gradient(135deg,#151312_0%,#2a211d_44%,#8f4625_100%)] text-white shadow-[0_24px_60px_rgba(31,26,23,0.22)]">
          <div className="flex flex-col gap-6 p-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs tracking-[0.2em] text-white/75">
                <BarChart3 size={14} />
                BI WORKBENCH
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">{heroTitle}</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-white/75">{heroSubtitle}</p>
              <div className="mt-5 flex flex-wrap gap-2">
                <JumpChip href="#overview" label="总览" />
                <JumpChip href="#trend" label="趋势" />
                <JumpChip href="#tutorbot" label="TutorBot" />
                <JumpChip href="#capability" label="能力与工具" />
                <JumpChip href="#knowledge" label="知识库" />
                <JumpChip href="#member" label="会员" />
              </div>
            </div>

            <div className="flex flex-col gap-3 self-start">
              <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-white/8 p-2">
                {[7, 30, 90].map((value) => (
                  <button
                    key={value}
                    onClick={() => setDays(value as 7 | 30 | 90)}
                    className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium transition ${
                      days === value ? "bg-white text-[#2d2119]" : "text-white/75 hover:bg-white/10 hover:text-white"
                    }`}
                  >
                    <CalendarDays size={14} />
                    {value} 天
                  </button>
                ))}
              </div>
              <button
                onClick={handleExport}
                disabled={exporting || !data}
                className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-medium text-[#2d2119] transition hover:bg-white/90 disabled:opacity-60"
              >
                <Download size={16} className={exporting ? "animate-pulse" : ""} />
                导出 JSON
              </button>
              <button
                onClick={() => void refresh()}
                disabled={refreshing}
                className="inline-flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/16 disabled:opacity-60"
              >
                <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
                刷新数据
              </button>
              <div className="rounded-2xl border border-white/10 bg-white/8 px-4 py-3 text-xs leading-5 text-white/80">
                <p>最近同步：{lastUpdatedAt ? formatTime(lastUpdatedAt) : "尚未同步"}</p>
                <p className="mt-1">时间范围：{rangeLabel}</p>
                <p className="mt-1">当前筛选：{activeFilters.length ? activeFilters.join(" · ") : "全部"}</p>
                <p className="mt-1">当前接口：`/api/v1/bi/*`</p>
              </div>
            </div>
          </div>
        </section>

        <section className="surface-card p-5">
          <SectionHeader
            title="筛选器"
            extra={activeFilters.length ? `${activeFilters.length} 个已启用` : "当前未启用额外筛选"}
          />
          <div className="mt-4 grid gap-4 xl:grid-cols-[repeat(3,minmax(0,1fr))_auto]">
            <FilterSelect
              label="Capability"
              value={filters.capability}
              options={FILTER_OPTIONS.capability}
              onChange={(value) => updateFilter("capability", value)}
            />
            <FilterSelect
              label="Entrypoint"
              value={filters.entrypoint}
              options={FILTER_OPTIONS.entrypoint}
              onChange={(value) => updateFilter("entrypoint", value)}
            />
            <FilterSelect
              label="Tier"
              value={filters.tier}
              options={FILTER_OPTIONS.tier}
              onChange={(value) => updateFilter("tier", value)}
            />
            <div className="flex items-end">
              <button
                type="button"
                onClick={resetFilters}
                disabled={!activeFilters.length}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm font-medium text-[var(--foreground)] transition hover:border-[var(--primary)]/30 hover:shadow-[0_10px_28px_rgba(45,33,25,0.08)] disabled:opacity-50"
              >
                <RefreshCw size={15} />
                重置筛选
              </button>
            </div>
          </div>
          <p className="mt-3 text-xs leading-5 text-[var(--muted-foreground)]">
            筛选会透传到 BI 聚合接口；会员、能力、趋势全量生效，TutorBot 当前按入口和层级筛选。
          </p>
        </section>

        {issues.length ? (
          <div className="surface-card border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <div className="flex items-start gap-2">
              <ShieldAlert size={16} className="mt-0.5 shrink-0" />
              <div>
                <p>部分 BI 接口未完全加载，页面已自动降级展示。</p>
                <p className="mt-1 text-xs leading-5 text-amber-700">{issues[0]}</p>
              </div>
            </div>
          </div>
        ) : null}

        <section id="overview" className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
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

        <section id="trend" className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,0.9fr)]">
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

        <section id="tutorbot" className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
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

        <section id="capability" className="grid gap-6 xl:grid-cols-2">
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

        <section id="knowledge" className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
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

            <div id="member" className="surface-card p-5">
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
                      openLearnerDetail({ user_id: sample.user_id, display_name: sample.display_name });
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
                        {sample.risk_level ? <span className={`muted-chip ${toneClasses(sample.risk_level === "high" ? "critical" : sample.risk_level === "medium" ? "warning" : "info")}`}>{sample.risk_level}</span> : null}
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

        <Modal
          isOpen={Boolean(selectedLearner)}
          onClose={closeLearnerDetail}
          title="Learner 360"
          titleIcon={<UserRound size={16} />}
          width="xl"
          footer={
            <div className="flex justify-end">
              <button
                onClick={closeLearnerDetail}
                className="rounded-full bg-[var(--primary)] px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
              >
                关闭
              </button>
            </div>
          }
        >
          <div className="space-y-5 p-5">
            <div className="rounded-2xl bg-[linear-gradient(135deg,rgba(195,90,44,0.12),rgba(15,118,110,0.08))] px-4 py-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">当前样本</p>
                  <h3 className="mt-1 text-xl font-semibold text-[var(--foreground)]">
                    {learnerDetail?.display_name ?? selectedLearner?.display_name ?? "Learner 360"}
                  </h3>
                  <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                    {learnerDetail?.user_id ?? selectedLearner?.user_id ?? "--"} · {rangeLabel} 视图
                  </p>
                </div>
                <div className="rounded-2xl bg-white/80 px-4 py-3 text-right">
                  <p className="text-[11px] tracking-[0.18em] text-[var(--muted-foreground)]">状态</p>
                  <p className="mt-1 text-sm font-medium text-[var(--foreground)]">
                    {learnerLoading ? "加载中" : learnerError ? "异常" : "已就绪"}
                  </p>
                </div>
              </div>
            </div>

            {learnerError ? (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {learnerError}
              </div>
            ) : null}

            {learnerLoading ? (
              <div className="rounded-2xl border bg-[var(--secondary)] px-4 py-6 text-sm text-[var(--muted-foreground)]">
                {`正在请求 /api/v1/bi/learner/${selectedLearner?.user_id ?? "user_id"}，请稍候。`}
              </div>
            ) : null}

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <div className="space-y-5">
                <div className="surface-card p-4">
                  <SectionHeader title="基础画像" extra={`${learnerDetail?.profile.length ?? 0} 项指标`} />
                  <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {(learnerDetail?.profile ?? []).length ? (
                      learnerDetail!.profile.slice(0, 6).map((card) => (
                        <MiniStatCard key={card.label} label={card.label} value={card.value} hint={card.hint} />
                      ))
                    ) : (
                      <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                        后端尚未返回画像指标。
                      </p>
                    )}
                  </div>
                </div>

                <div className="surface-card p-4">
                  <SectionHeader
                    title="最近会话"
                    extra={learnerDetail?.recent_sessions.length ? `${learnerDetail.recent_sessions.length} 条` : "暂无会话"}
                  />
                  <div className="mt-4 space-y-3">
                    {learnerDetail?.recent_sessions.length ? (
                      learnerDetail.recent_sessions.slice(0, 4).map((session) => (
                        <div key={session.session_id} className="rounded-2xl border bg-[var(--background)] px-4 py-3">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className="font-medium text-[var(--foreground)]">{session.title}</p>
                              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                                {session.capability || "chat"} · {session.status || "unknown"} · {formatTime(session.started_at)}
                              </p>
                            </div>
                            <span className="rounded-full bg-[var(--secondary)] px-2 py-1 text-xs text-[var(--secondary-foreground)]">
                              {formatDuration(session.duration_minutes)}
                            </span>
                          </div>
                          {session.summary ? <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{session.summary}</p> : null}
                        </div>
                      ))
                    ) : (
                      <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                        后端尚未返回最近会话。
                      </p>
                    )}
                  </div>
                </div>
              </div>

              <div className="space-y-5">
                <div className="surface-card p-4">
                  <SectionHeader
                    title="章节掌握"
                    extra={learnerDetail?.chapter_mastery.length ? `Top ${Math.min(learnerDetail.chapter_mastery.length, 6)}` : "暂无数据"}
                  />
                  <div className="mt-4 space-y-3">
                    {learnerDetail?.chapter_mastery.length ? (
                      learnerDetail.chapter_mastery.slice(0, 6).map((chapter) => {
                        const masteryWidth = Math.max(4, Math.min(100, chapter.mastery > 1 ? chapter.mastery : chapter.mastery * 100));
                        return (
                          <div key={chapter.chapter_id ?? chapter.name} className="rounded-2xl border bg-[var(--background)] px-4 py-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="font-medium text-[var(--foreground)]">{chapter.name}</p>
                                {chapter.hint ? <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">{chapter.hint}</p> : null}
                              </div>
                              <p className="text-sm font-semibold text-[var(--foreground)]">{formatPercent(chapter.mastery)}</p>
                            </div>
                            <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--secondary)]">
                              <div
                                className="h-full rounded-full bg-[linear-gradient(90deg,#C35A2C,#0f766e)]"
                                style={{ width: `${masteryWidth}%` }}
                              />
                            </div>
                            {chapter.evidence ? <p className="mt-2 text-xs leading-5 text-[var(--muted-foreground)]">{chapter.evidence}</p> : null}
                          </div>
                        );
                      })
                    ) : (
                      <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                        后端尚未返回章节掌握数据。
                      </p>
                    )}
                  </div>
                </div>

                <div className="surface-card p-4">
                  <SectionHeader title="账本 / 备注摘要" extra="最近可行动信息" />
                  <div className="mt-4 grid gap-3">
                    <InfoLine
                      label="备注数量"
                      value={
                        learnerDetail?.notes_summary.notes_count !== undefined
                          ? String(learnerDetail.notes_summary.notes_count)
                          : "未返回"
                      }
                    />
                    <InfoLine
                      label="置顶备注"
                      value={
                        learnerDetail?.notes_summary.pinned_notes_count !== undefined
                          ? String(learnerDetail.notes_summary.pinned_notes_count)
                          : "未返回"
                      }
                    />
                    <InfoLine
                      label="钱包余额"
                      value={
                        learnerDetail?.notes_summary.wallet_balance !== undefined
                          ? formatNumber(learnerDetail.notes_summary.wallet_balance)
                          : "未返回"
                      }
                    />
                    <InfoLine
                      label="账本摘要"
                      value={learnerDetail?.notes_summary.recent_ledger || learnerDetail?.notes_summary.summary || "等待后端返回"}
                    />
                    <InfoLine
                      label="备注摘要"
                      value={learnerDetail?.notes_summary.recent_note || learnerDetail?.notes_summary.summary || "等待后端返回"}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Modal>
      </div>
    </div>
  );
}

function createLoadingCards() {
  return Array.from({ length: 6 }, (_, index) => ({
    label: `加载中 ${index + 1}`,
    value: "--",
    hint: "等待 BI 接口",
    delta: "",
    tone: "neutral" as const,
  }));
}

function metricIconByIndex(index: number) {
  const icons: LucideIcon[] = [BarChart3, Bot, Sparkles, Target, Wallet, CircleAlert];
  return icons[index % icons.length];
}

function JumpChip({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="rounded-full border border-white/15 bg-white/8 px-3 py-1 text-xs text-white/80 transition hover:bg-white/14 hover:text-white"
    >
      {label}
    </a>
  );
}

function SectionHeader({ title, extra }: { title: string; extra?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold tracking-[0.18em] text-[var(--muted-foreground)]">{title}</h2>
      {extra ? <span className="text-xs text-[var(--muted-foreground)]">{extra}</span> : null}
    </div>
  );
}

function MetricCard({
  title,
  value,
  hint,
  delta,
  tone = "neutral",
  icon,
}: {
  title: string;
  value: number | string;
  hint?: string;
  delta?: string;
  tone?: "neutral" | "good" | "warning" | "critical";
  icon: LucideIcon;
}) {
  const Icon = icon;
  return (
    <article className="surface-card overflow-hidden border-0 bg-white/90 p-5 shadow-[0_10px_30px_rgba(45,33,25,0.06)]">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted-foreground)]">{title}</p>
        <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
          <Icon size={16} />
        </div>
      </div>
      <p className={`mt-5 text-3xl font-semibold tracking-tight ${metricToneClasses(tone)}`}>{formatNumber(value)}</p>
      {delta ? <p className="mt-2 text-xs text-[var(--muted-foreground)]">{delta}</p> : null}
      {hint ? <p className="mt-2 text-sm text-[var(--muted-foreground)]">{hint}</p> : null}
    </article>
  );
}

function MiniStatCard({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
      <p className="text-xs text-[var(--muted-foreground)]">{label}</p>
      <p className="mt-1 text-lg font-semibold tracking-tight text-[var(--foreground)]">{formatNumber(value)}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
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
  const cards: Array<
    Pick<BiMetricCard, "label" | "value" | "hint" | "tone" | "delta">
  > = [
    ...(overview?.alerts ?? []).slice(0, 2).map((item) => ({
      label: item.title,
      value: 0,
      hint: item.detail,
      tone: "warning" as const,
    })),
    ...(cost.cards ?? []).slice(0, 2),
    ...(members.cards ?? []).slice(0, 2),
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
              const y = 160 - ((point.active - Math.min(...activeSeries, 0)) / Math.max(Math.max(...activeSeries, 1) - Math.min(...activeSeries, 0), 1)) * 152 - 4;
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

function RankingCard({
  title,
  items,
  emptyText,
  icon,
  headerMeta,
  footerItems,
  footerTitle,
  compact = false,
}: {
  title: string;
  items: Array<{ label: string; value: number; rate?: number; hint?: string; secondary?: string }>;
  emptyText: string;
  icon?: ReactNode;
  headerMeta?: string;
  footerItems?: Array<{ label: string; value: number; rate?: number; hint?: string; secondary?: string }>;
  footerTitle?: string;
  compact?: boolean;
}) {
  return (
    <div className="surface-card p-5">
      <div className="flex items-start justify-between gap-3">
        <SectionHeader title={title} extra={headerMeta} />
        {icon ? (
          <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
            {icon}
          </div>
        ) : null}
      </div>
      <div className="mt-4 space-y-3">
        {items.length ? (
          items.slice(0, compact ? 5 : 6).map((item) => (
            <RankRow key={item.label} item={item} compact={compact} />
          ))
        ) : (
          <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">{emptyText}</p>
        )}
      </div>
      {footerItems?.length ? (
        <div className="mt-5 border-t border-[var(--border)]/60 pt-4">
          <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">{footerTitle ?? "补充视图"}</p>
          <div className="mt-3 space-y-2">
            {footerItems.slice(0, 4).map((item) => (
              <RankRow key={`${footerTitle ?? "footer"}-${item.label}`} item={item} compact />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function SimpleListCard({
  title,
  items,
  emptyText,
  icon,
  footer,
}: {
  title: string;
  items: Array<{ label: string; value: number; hint?: string }>;
  emptyText: string;
  icon: ReactNode;
  footer?: string;
}) {
  return (
    <div className="surface-card p-5">
      <div className="flex items-center justify-between gap-3">
        <SectionHeader title={title} extra={footer} />
        <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">{icon}</div>
      </div>
      <div className="mt-4 space-y-3">
        {items.length ? (
          items.slice(0, 5).map((item) => <RankRow key={item.label} item={item} compact />)
        ) : (
          <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">{emptyText}</p>
        )}
      </div>
    </div>
  );
}

function RankRow({
  item,
  compact = false,
}: {
  item: { label: string; value: number; rate?: number; hint?: string; secondary?: string };
  compact?: boolean;
}) {
  const width = Math.max(6, Math.min(100, item.value));
  return (
    <div className="space-y-2 rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium text-[var(--foreground)]">{item.label}</p>
          {item.hint ? <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">{item.hint}</p> : null}
          {item.secondary ? <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">{item.secondary}</p> : null}
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold text-[var(--foreground)]">{formatNumber(item.value)}</p>
          {item.rate !== undefined ? <p className="text-xs text-[var(--muted-foreground)]">{formatPercent(item.rate)}</p> : null}
        </div>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[var(--secondary)]">
        <div className="h-full rounded-full bg-[linear-gradient(90deg,#C35A2C,#8f4625)]" style={{ width: `${width}%` }} />
      </div>
      {compact ? null : item.rate !== undefined ? (
        <p className="text-xs text-[var(--muted-foreground)]">转化/成功率：{formatPercent(item.rate)}</p>
      ) : null}
    </div>
  );
}

function AlertCard({ item }: { item: { level: string; title: string; detail?: string } }) {
  return (
    <div className="rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start gap-3">
        <span className={`mt-0.5 inline-flex rounded-full px-2 py-1 text-[11px] ${toneClasses(item.level)}`}>{item.level}</span>
        <div>
          <p className="font-medium text-[var(--foreground)]">{item.title}</p>
          {item.detail ? <p className="mt-1 text-sm leading-5 text-[var(--muted-foreground)]">{item.detail}</p> : null}
        </div>
      </div>
    </div>
  );
}

function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl bg-[var(--secondary)] px-4 py-3">
      <span className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">{label}</span>
      <span className="max-w-[70%] text-right text-sm text-[var(--secondary-foreground)]">{value}</span>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: ReadonlyArray<{ label: string; value: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-2">
      <span className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-[var(--border)] bg-[var(--background)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-[var(--primary)]/40 focus:ring-2 focus:ring-[var(--primary)]/10"
      >
        {options.map((option) => (
          <option key={option.label} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function BotActiveCard({ bot }: { bot: { bot_id: string; name: string; capability?: string; entrypoint?: string; tier?: string; status?: string; last_active_at?: string; detail?: string } }) {
  return (
    <div className="rounded-2xl border bg-[var(--background)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-[var(--foreground)]">{bot.name}</p>
          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
            {bot.bot_id || "--"} · {bot.last_active_at ? formatTime(bot.last_active_at) : "最近活跃待补全"}
          </p>
        </div>
        {bot.status ? <span className={`muted-chip ${toneClasses(bot.status === "critical" ? "critical" : bot.status === "warning" ? "warning" : "info")}`}>{bot.status}</span> : null}
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
