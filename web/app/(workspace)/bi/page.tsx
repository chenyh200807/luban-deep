/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { UserRound } from "lucide-react";
import Modal from "@/components/common/Modal";
import {
  getBiLearnerDetail,
  loadBiWorkbench,
  type BiBossActionItem,
  type BiLearnerDetailData,
  type BiTutorBotData,
} from "@/lib/bi-api";
import { BiBossHeader } from "./_components/BiBossHeader";
import { BiCommandDeckTabs } from "./_components/BiCommandDeckTabs";
import { BiMemberOpsTab } from "./_components/BiMemberOpsTab";
import { BiOverviewTab } from "./_components/BiOverviewTab";
import { BiQualityTab } from "./_components/BiQualityTab";
import { BiTutorBotTab } from "./_components/BiTutorBotTab";
import {
  BI_PRIMARY_TABS,
  BiFiltersPanel,
  BiIssuesBanner,
  BiTabShell,
  type BiFilterField,
  type BiFilterState,
  type BiPrimaryTab,
  InfoLine,
  MiniStatCard,
  SectionHeader,
  formatDuration,
  formatNumber,
  formatPercent,
  formatTime,
  normalizeBiPrimaryTab,
} from "./_components/BiShared";

export default function BiPage() {
  const searchParams = useSearchParams();
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [activeTab, setActiveTab] = useState<BiPrimaryTab>("overview");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<BiFilterState>({ capability: "", entrypoint: "", tier: "" });
  const [workbench, setWorkbench] = useState<Awaited<ReturnType<typeof loadBiWorkbench>> | null>(null);
  const [issues, setIssues] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
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
      setWorkbench(result);
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
    setActiveTab(normalizeBiPrimaryTab(searchParams.get("tab")));
  }, [searchParams]);

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

  const data = workbench?.data ?? null;
  const boss = workbench?.boss ?? { kpis: [], actionQueue: [], heroIssue: "" };
  const moduleIssues = workbench?.moduleIssues ?? {};
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

  const activeFilters = [
    filters.capability ? `capability: ${filters.capability}` : "",
    filters.entrypoint ? `entrypoint: ${filters.entrypoint}` : "",
    filters.tier ? `tier: ${filters.tier}` : "",
  ].filter(Boolean);
  const activeTabMeta = BI_PRIMARY_TABS.find((tab) => tab.key === activeTab) ?? BI_PRIMARY_TABS[0];
  const heroIssue = boss.heroIssue || issues[0] || null;

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

  const navigateFromBossQueue = useCallback(
    (source?: BiBossActionItem["source"]) => {
      if (source === "anomalies") {
        setActiveTab("quality");
        return;
      }
      if (source === "members") {
        setActiveTab("member-ops");
        return;
      }
      if (source === "cost") {
        setActiveTab("overview");
        requestAnimationFrame(() => {
          document.getElementById("boss-snapshot-grid")?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      }
    },
    [setActiveTab],
  );

  const exportJson = useCallback(() => {
    setExporting(true);
    try {
      const payload = {
        exported_at: new Date().toISOString(),
        days,
        filters,
        last_updated_at: lastUpdatedAt,
        issues,
        data,
        boss,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `bi-workbench-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [boss, days, data, issues, filters, lastUpdatedAt]);

  const canExport = Boolean(workbench || issues.length);

  return (
    <div className="h-full overflow-y-auto [scrollbar-gutter:stable] bg-[radial-gradient(circle_at_top_left,_rgba(195,90,44,0.14),_transparent_34%),radial-gradient(circle_at_85%_10%,_rgba(18,122,134,0.09),_transparent_28%),linear-gradient(180deg,#faf9f6_0%,#f4efe8_100%)] px-6 py-6">
      <div className="mx-auto flex max-w-[1540px] flex-col gap-6">
        <BiBossHeader
          days={days}
          onDaysChange={setDays}
          onExport={exportJson}
          exporting={exporting}
          onRefresh={() => void refresh()}
          refreshing={refreshing}
          canExport={canExport}
          lastUpdatedLabel={lastUpdatedAt ? formatTime(lastUpdatedAt) : "尚未同步"}
          filtersOpen={filtersOpen}
          onToggleFilters={() => setFiltersOpen((open) => !open)}
          activeFilters={activeFilters}
          heroIssue={heroIssue}
        />

        <BiCommandDeckTabs activeTab={activeTab} onTabChange={setActiveTab} />

        {filtersOpen ? (
          <BiFiltersPanel
            filters={filters}
            activeFilters={activeFilters}
            onChange={updateFilter}
            onReset={resetFilters}
          />
        ) : null}

        <BiIssuesBanner issues={issues} />

        {activeTab === "overview" ? (
          <BiOverviewTab
            loading={loading}
            days={days}
            boss={boss}
            overview={overview}
            trend={trend}
            retention={retention}
            members={members}
            moduleIssues={moduleIssues}
            onNavigateFromBossQueue={navigateFromBossQueue}
            onOpenLearnerDetail={openLearnerDetail}
          />
        ) : activeTab === "quality" ? (
          <BiQualityTab
            trend={trend}
            anomalies={anomalies}
            overview={overview}
            issues={issues}
          />
        ) : activeTab === "member-ops" ? (
          <BiMemberOpsTab
            loading={loading}
            overview={overview}
            members={members}
            cost={cost}
            retention={retention}
            onOpenLearnerDetail={openLearnerDetail}
          />
        ) : activeTab === "tutorbot" ? (
          <BiTutorBotTab
            days={days}
            overview={overview}
            tutorbots={tutorbots}
            capabilities={capabilities}
            tools={tools}
            knowledge={knowledge}
            cost={cost}
          />
        ) : (
          <BiTabShell title={activeTabMeta.label} summary={activeTabMeta.summary} />
        )}

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
                    {learnerDetail?.user_id ?? selectedLearner?.user_id ?? "--"} · {days} 天视图
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
