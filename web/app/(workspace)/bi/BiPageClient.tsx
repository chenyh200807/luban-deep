/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search } from "lucide-react";
import { apiUrl } from "@/lib/api";
import {
  loadBiWorkbench,
  type BiBossActionItem,
} from "@/lib/bi-api";
import {
  applyOverlayPromotions,
  batchUpdateMembers,
  createMemberNote,
  getMemberAuditLog,
  getMemberDashboard,
  getMemberDetail,
  listMembers,
  pauseHeartbeatJob,
  revokeMembership,
  resumeHeartbeatJob,
  updateMembership,
  grantMembership,
  type BotOverlaySummary,
  type HeartbeatJob,
  type MemberAuditLogResponse,
  type MemberDashboard,
  type MemberDetail,
  type MemberListItem,
} from "@/lib/member-api";
import { BiBossHeader } from "./_components/BiBossHeader";
import { BiCommandDeckTabs } from "./_components/BiCommandDeckTabs";
import { BiAuditTab } from "./_components/BiAuditTab";
import { BiMember360Panel } from "./_components/BiMember360Panel";
import { BiMemberOpsTab } from "./_components/BiMemberOpsTab";
import { BiOverviewTab } from "./_components/BiOverviewTab";
import {
  BI_PRIMARY_TABS,
  BiFiltersPanel,
  BiIssuesBanner,
  BiTabShell,
  type BiFilterField,
  type BiFilterState,
  type BiPrimaryTab,
  formatTime,
  normalizeBiPrimaryTab,
} from "./_components/BiShared";

type MemberFilterState = {
  search: string;
  status: string;
  tier: string;
  risk_level: string;
};

const DEFAULT_MEMBER_FILTERS: MemberFilterState = {
  search: "",
  status: "all",
  tier: "all",
  risk_level: "all",
};

export default function BiPageClient() {
  const searchParams = useSearchParams();
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [activeTab, setActiveTab] = useState<BiPrimaryTab>("boss-workbench");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState<BiFilterState>({ capability: "", entrypoint: "", tier: "" });
  const [workbench, setWorkbench] = useState<Awaited<ReturnType<typeof loadBiWorkbench>> | null>(null);
  const [issues, setIssues] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const [memberFilters, setMemberFilters] = useState<MemberFilterState>(DEFAULT_MEMBER_FILTERS);
  const [memberDashboard, setMemberDashboard] = useState<MemberDashboard | null>(null);
  const [memberItems, setMemberItems] = useState<MemberListItem[]>([]);
  const [memberTotal, setMemberTotal] = useState(0);
  const [memberLoading, setMemberLoading] = useState(true);
  const [memberError, setMemberError] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedMember, setSelectedMember] = useState<MemberDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  const [auditLog, setAuditLog] = useState<MemberAuditLogResponse | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");

  const refreshBi = useCallback(async () => {
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

  const refreshMembers = useCallback(async () => {
    try {
      setMemberLoading(true);
      setMemberError("");
      setAuditLoading(true);
      setAuditError("");
      const [dashboard, list, audit] = await Promise.all([
        getMemberDashboard(),
        listMembers({
          page: 1,
          page_size: 50,
          search: memberFilters.search.trim() || undefined,
          status: memberFilters.status,
          tier: memberFilters.tier,
          risk_level: memberFilters.risk_level,
        }),
        getMemberAuditLog({ page: 1, page_size: 50 }),
      ]);
      setMemberDashboard(dashboard);
      setMemberItems(list.items);
      setMemberTotal(list.total);
      setAuditLog(audit);
      if (!selectedUserId && list.items[0]) {
        setSelectedUserId(list.items[0].user_id);
      }
      if (selectedUserId && !list.items.some((item) => item.user_id === selectedUserId)) {
        setSelectedUserId(list.items[0]?.user_id ?? "");
      }
      setSelectedIds((current) => current.filter((userId) => list.items.some((item) => item.user_id === userId)));
    } catch (error) {
      const message = error instanceof Error ? error.message : "会员后台加载失败";
      setMemberError(message);
      setAuditError(message);
    } finally {
      setMemberLoading(false);
      setAuditLoading(false);
    }
  }, [memberFilters.risk_level, memberFilters.search, memberFilters.status, memberFilters.tier, selectedUserId]);

  const refreshSelectedMember = useCallback(async () => {
    if (!selectedUserId) {
      setSelectedMember(null);
      return;
    }
    try {
      setDetailLoading(true);
      setDetailError("");
      const detail = await getMemberDetail(selectedUserId);
      setSelectedMember(detail);
    } catch (error) {
      setSelectedMember(null);
      setDetailError(error instanceof Error ? error.message : "学员 360 加载失败");
    } finally {
      setDetailLoading(false);
    }
  }, [selectedUserId]);

  useEffect(() => {
    void refreshBi();
  }, [refreshBi]);

  useEffect(() => {
    void refreshMembers();
  }, [refreshMembers]);

  useEffect(() => {
    setActiveTab(normalizeBiPrimaryTab(searchParams.get("tab")));
  }, [searchParams]);

  useEffect(() => {
    void refreshSelectedMember();
  }, [refreshSelectedMember]);

  useEffect(() => {
    if (filters.tier && filters.tier !== memberFilters.tier) {
      setMemberFilters((current) => ({ ...current, tier: filters.tier }));
    }
  }, [filters.tier, memberFilters.tier]);

  const data = workbench?.data ?? null;
  const boss = workbench?.boss ?? { kpis: [], actionQueue: [], heroIssue: "" };
  const moduleIssues = workbench?.moduleIssues ?? {};
  const overview = data?.overview;
  const trend = data?.trend ?? { points: [] };
  const retention = data?.retention ?? { cohorts: [], labels: ["D0", "D1", "D7", "D30"] };
  const members = data?.members ?? { cards: [], tiers: [], risks: [], samples: [] };

  const activeFilters = [
    filters.capability ? `capability: ${filters.capability}` : "",
    filters.entrypoint ? `entrypoint: ${filters.entrypoint}` : "",
    filters.tier ? `tier: ${filters.tier}` : "",
  ].filter(Boolean);
  const activeTabMeta = BI_PRIMARY_TABS.find((tab) => tab.key === activeTab) ?? BI_PRIMARY_TABS[0];
  const heroIssue = boss.heroIssue || issues[0] || null;

  const updateFilter = useCallback((field: BiFilterField, value: string) => {
    setFilters((current) => ({
      ...current,
      [field]: value,
    }));
  }, []);

  const resetFilters = useCallback(() => {
    setFilters({ capability: "", entrypoint: "", tier: "" });
  }, []);

  const openMember360 = useCallback((userId: string) => {
    setSelectedUserId(userId);
    setActiveTab("learner-360");
  }, []);

  const toggleSelectedMember = useCallback((userId: string) => {
    setSelectedIds((current) => (current.includes(userId) ? current.filter((item) => item !== userId) : [...current, userId]));
  }, []);

  const applyMemberFilterPatch = useCallback((patch: Partial<MemberFilterState>) => {
    setMemberFilters((current) => ({ ...current, ...patch }));
  }, []);

  const navigateFromBossQueue = useCallback(
    (action?: BiBossActionItem) => {
      const handoffFilters = action?.handoffFilters;
      if (action?.source === "members") {
        if (handoffFilters?.status === "expiring_soon") {
          applyMemberFilterPatch({ ...DEFAULT_MEMBER_FILTERS, status: "expiring_soon" });
          setActiveTab("member-ops");
          return;
        }
        if (
          typeof handoffFilters?.status === "string" ||
          typeof handoffFilters?.tier === "string" ||
          typeof handoffFilters?.risk_level === "string" ||
          typeof handoffFilters?.search === "string"
        ) {
          applyMemberFilterPatch({
            ...DEFAULT_MEMBER_FILTERS,
            status: typeof handoffFilters?.status === "string" ? handoffFilters.status : "all",
            tier: typeof handoffFilters?.tier === "string" ? handoffFilters.tier : "all",
            risk_level: typeof handoffFilters?.risk_level === "string" ? handoffFilters.risk_level : "all",
            search: typeof handoffFilters?.search === "string" ? handoffFilters.search : "",
          });
          setActiveTab("member-ops");
          return;
        }
        applyMemberFilterPatch({ risk_level: "high", status: "all" });
        setActiveTab("member-ops");
        return;
      }
      if (action?.source === "anomalies") {
        setActiveTab("audit");
        return;
      }
      setActiveTab("boss-workbench");
    },
    [applyMemberFilterPatch],
  );

  const openLearnerDetail = useCallback((sample: { user_id: string; display_name: string }) => {
    if (!sample.user_id) return;
    setSelectedUserId(sample.user_id);
    setActiveTab("learner-360");
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([refreshBi(), refreshMembers(), refreshSelectedMember()]);
  }, [refreshBi, refreshMembers, refreshSelectedMember]);

  const handleBatchAction = useCallback(
    async (action: "grant" | "revoke") => {
      if (selectedIds.length === 0) return;
      try {
        setActionLoading(true);
        await batchUpdateMembers({
          user_ids: selectedIds,
          action,
          days: action === "grant" ? 30 : undefined,
          tier: action === "grant" ? "vip" : undefined,
          reason: action === "grant" ? "BI 会员工作台批量开通" : "BI 会员工作台批量撤销",
        });
        await refreshMembers();
        if (selectedUserId) {
          await refreshSelectedMember();
        }
        setSelectedIds([]);
      } catch (error) {
        setMemberError(error instanceof Error ? error.message : "批量操作失败");
      } finally {
        setActionLoading(false);
      }
    },
    [refreshMembers, refreshSelectedMember, selectedIds, selectedUserId],
  );

  const handleSingleGrant = useCallback(async () => {
    if (!selectedUserId) return;
    try {
      setActionLoading(true);
      await grantMembership({ user_id: selectedUserId, days: 30, tier: "vip", reason: "BI 会员工作台开通" });
      await refreshMembers();
      await refreshSelectedMember();
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "开通会员失败");
    } finally {
      setActionLoading(false);
    }
  }, [refreshMembers, refreshSelectedMember, selectedUserId]);

  const handleSingleExtend = useCallback(async () => {
    if (!selectedUserId) return;
    try {
      setActionLoading(true);
      await updateMembership({ user_id: selectedUserId, days: 90, reason: "BI 会员工作台续期 90 天" });
      await refreshMembers();
      await refreshSelectedMember();
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "续期会员失败");
    } finally {
      setActionLoading(false);
    }
  }, [refreshMembers, refreshSelectedMember, selectedUserId]);

  const handleSingleRevoke = useCallback(async () => {
    if (!selectedUserId) return;
    try {
      setActionLoading(true);
      await revokeMembership({ user_id: selectedUserId, reason: "BI 会员工作台撤销" });
      await refreshMembers();
      await refreshSelectedMember();
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "撤销会员失败");
    } finally {
      setActionLoading(false);
    }
  }, [refreshMembers, refreshSelectedMember, selectedUserId]);

  const handleAddNote = useCallback(
    async (content: string) => {
      if (!selectedUserId) return;
      try {
        setActionLoading(true);
        await createMemberNote(selectedUserId, { content, pinned: false, channel: "manual" });
        await refreshSelectedMember();
        await refreshMembers();
      } catch (error) {
        setDetailError(error instanceof Error ? error.message : "添加备注失败");
      } finally {
        setActionLoading(false);
      }
    },
    [refreshMembers, refreshSelectedMember, selectedUserId],
  );

  const handleHeartbeatJobAction = useCallback(
    async (job: HeartbeatJob) => {
      if (!selectedUserId) return;
      try {
        setActionLoading(true);
        if (job.status === "active") {
          await pauseHeartbeatJob(selectedUserId, job.job_id);
        } else {
          await resumeHeartbeatJob(selectedUserId, job.job_id);
        }
        await refreshSelectedMember();
      } catch (error) {
        setDetailError(error instanceof Error ? error.message : "Heartbeat job 操作失败");
      } finally {
        setActionLoading(false);
      }
    },
    [refreshSelectedMember, selectedUserId],
  );

  const handleApplyOverlayPromotions = useCallback(
    async (overlay: BotOverlaySummary) => {
      if (!selectedUserId) return;
      try {
        setActionLoading(true);
        await applyOverlayPromotions(selectedUserId, overlay.bot_id, { min_confidence: 0.7, max_candidates: 10 });
        await refreshSelectedMember();
      } catch (error) {
        setDetailError(error instanceof Error ? error.message : "Overlay promotion 执行失败");
      } finally {
        setActionLoading(false);
      }
    },
    [refreshSelectedMember, selectedUserId],
  );

  const exportJson = useCallback(() => {
    setExporting(true);
    try {
      const payload = {
        exported_at: new Date().toISOString(),
        days,
        filters,
        member_filters: memberFilters,
        last_updated_at: lastUpdatedAt,
        issues,
        data,
        boss,
        member_dashboard: memberDashboard,
      };
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `bi-member-admin-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [boss, data, days, filters, issues, lastUpdatedAt, memberDashboard, memberFilters]);

  const canExport = Boolean(workbench || memberItems.length || issues.length);
  const exportHref = useMemo(() => {
    const query = new URLSearchParams();
    if (memberFilters.status !== "all") query.set("status", memberFilters.status);
    if (memberFilters.tier !== "all") query.set("tier", memberFilters.tier);
    if (memberFilters.risk_level !== "all") query.set("risk_level", memberFilters.risk_level);
    if (memberFilters.search.trim()) query.set("search", memberFilters.search.trim());
    const suffix = query.toString();
    return apiUrl(`/api/v1/member/export${suffix ? `?${suffix}` : ""}`);
  }, [memberFilters.risk_level, memberFilters.search, memberFilters.status, memberFilters.tier]);

  return (
    <div className="h-full overflow-y-auto [scrollbar-gutter:stable] bg-[radial-gradient(circle_at_top_left,_rgba(195,90,44,0.14),_transparent_34%),radial-gradient(circle_at_85%_10%,_rgba(18,122,134,0.09),_transparent_28%),linear-gradient(180deg,#faf9f6_0%,#f4efe8_100%)] px-6 py-6">
      <div className="mx-auto flex max-w-[1540px] flex-col gap-6">
        <BiBossHeader
          days={days}
          onDaysChange={setDays}
          onExport={exportJson}
          exporting={exporting}
          onRefresh={() => void refreshAll()}
          refreshing={refreshing || memberLoading || detailLoading}
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

        {(activeTab === "member-ops" || activeTab === "learner-360" || activeTab === "audit") ? (
          <section className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" size={16} />
                <input
                  value={memberFilters.search}
                  onChange={(event) => applyMemberFilterPatch({ search: event.target.value })}
                  placeholder="搜索 User ID / 昵称 / 手机号"
                  className="w-full rounded-2xl border bg-white px-10 py-2.5 text-sm outline-none transition focus:border-[var(--primary)]"
                />
              </div>
              <div className="grid flex-1 gap-3 sm:grid-cols-3">
                <select
                  value={memberFilters.status}
                  onChange={(event) => applyMemberFilterPatch({ status: event.target.value })}
                  className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                >
                  <option value="all">全部状态</option>
                  <option value="active">活跃</option>
                  <option value="expiring_soon">即将到期</option>
                  <option value="expired">已过期</option>
                  <option value="revoked">已撤销</option>
                </select>
                <select
                  value={memberFilters.tier}
                  onChange={(event) => applyMemberFilterPatch({ tier: event.target.value })}
                  className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                >
                  <option value="all">全部层级</option>
                  <option value="trial">Trial</option>
                  <option value="vip">VIP</option>
                  <option value="svip">SVIP</option>
                </select>
                <select
                  value={memberFilters.risk_level}
                  onChange={(event) => applyMemberFilterPatch({ risk_level: event.target.value })}
                  className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                >
                  <option value="all">全部风险</option>
                  <option value="low">低风险</option>
                  <option value="medium">中风险</option>
                  <option value="high">高风险</option>
                </select>
              </div>
            </div>
          </section>
        ) : null}

        {activeTab === "boss-workbench" ? (
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
        ) : activeTab === "member-ops" ? (
          <BiMemberOpsTab
            loading={memberLoading}
            memberItems={memberItems}
            selectedIds={selectedIds}
            selectedMember={selectedMember}
            detailLoading={detailLoading}
            detailError={detailError || memberError}
            actionLoading={actionLoading}
            totalCount={memberTotal}
            onToggleMember={toggleSelectedMember}
            onOpenMember={openMember360}
            onBatchGrant={() => void handleBatchAction("grant")}
            onBatchRevoke={() => void handleBatchAction("revoke")}
            onGrantSingle={() => void handleSingleGrant()}
            onExtendSingle={() => void handleSingleExtend()}
            onRevokeSingle={() => void handleSingleRevoke()}
            onAddNote={(content) => void handleAddNote(content)}
            onToggleHeartbeat={(job) => void handleHeartbeatJobAction(job)}
            onApplyOverlay={(overlay) => void handleApplyOverlayPromotions(overlay)}
          />
        ) : activeTab === "learner-360" ? (
          <BiMember360Panel
            member={selectedMember}
            loading={detailLoading}
            error={detailError || memberError}
            actionLoading={actionLoading}
            onGrant={() => void handleSingleGrant()}
            onExtend={() => void handleSingleExtend()}
            onRevoke={() => void handleSingleRevoke()}
            onAddNote={(content) => void handleAddNote(content)}
            onToggleHeartbeat={(job) => void handleHeartbeatJobAction(job)}
            onApplyOverlay={(overlay) => void handleApplyOverlayPromotions(overlay)}
          />
        ) : activeTab === "audit" ? (
          <BiAuditTab audit={auditLog} loading={auditLoading} error={auditError} exportHref={exportHref} />
        ) : (
          <BiTabShell title={activeTabMeta.label} summary={activeTabMeta.summary} />
        )}
      </div>
    </div>
  );
}
