/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Search } from "lucide-react";
import { BI_API_TOKEN, apiUrl } from "@/lib/api";
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
  expire_within_days: number | null;
};

type AuditFilterState = {
  target_user: string;
  operator: string;
  action: string;
};

const DEFAULT_MEMBER_FILTERS: MemberFilterState = {
  search: "",
  status: "all",
  tier: "all",
  risk_level: "all",
  expire_within_days: null,
};

const DEFAULT_AUDIT_FILTERS: AuditFilterState = {
  target_user: "",
  operator: "",
  action: "all",
};

const BI_READ_ONLY_SUMMARY =
  "当前通过 BI API Token 只读访问，经营 BI 聚合可正常查看；会员运营、学员 360、经营审计与导出仍需管理员登录态。";

export default function BiPageClient() {
  const searchParams = useSearchParams();
  const biReadOnly = Boolean(BI_API_TOKEN);
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
  const [auditFilters, setAuditFilters] = useState<AuditFilterState>(DEFAULT_AUDIT_FILTERS);
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
    if (biReadOnly) {
      setMemberLoading(false);
      setMemberError("");
      setMemberDashboard(null);
      setMemberItems([]);
      setMemberTotal(0);
      setSelectedIds([]);
      setSelectedUserId("");
      return;
    }
    try {
      setMemberLoading(true);
      setMemberError("");
      const [dashboard, list] = await Promise.all([
        getMemberDashboard(),
        listMembers({
          page: 1,
          page_size: 50,
          search: memberFilters.search.trim() || undefined,
          status: memberFilters.status,
          tier: memberFilters.tier,
          risk_level: memberFilters.risk_level,
          expire_within_days: memberFilters.expire_within_days ?? undefined,
        }),
      ]);
      setMemberDashboard(dashboard);
      setMemberItems(list.items);
      setMemberTotal(list.total);
      if (!selectedUserId && list.items[0]) {
        setSelectedUserId(list.items[0].user_id);
      }
      if (selectedUserId && !list.items.some((item) => item.user_id === selectedUserId)) {
        setSelectedUserId(list.items[0]?.user_id ?? "");
      }
      setSelectedIds((current) => current.filter((userId) => list.items.some((item) => item.user_id === userId)));
    } catch (error) {
      setMemberError(error instanceof Error ? error.message : "会员后台加载失败");
    } finally {
      setMemberLoading(false);
    }
  }, [
    biReadOnly,
    memberFilters.expire_within_days,
    memberFilters.risk_level,
    memberFilters.search,
    memberFilters.status,
    memberFilters.tier,
    selectedUserId,
  ]);

  const refreshAudit = useCallback(async () => {
    if (biReadOnly) {
      setAuditLoading(false);
      setAuditError("");
      setAuditLog(null);
      return;
    }
    try {
      setAuditLoading(true);
      setAuditError("");
      const audit = await getMemberAuditLog({
        page: 1,
        page_size: 50,
        target_user: auditFilters.target_user.trim() || undefined,
        operator: auditFilters.operator.trim() || undefined,
        action: auditFilters.action === "all" ? undefined : auditFilters.action,
      });
      setAuditLog(audit);
    } catch (error) {
      setAuditError(error instanceof Error ? error.message : "经营审计加载失败");
    } finally {
      setAuditLoading(false);
    }
  }, [auditFilters.action, auditFilters.operator, auditFilters.target_user, biReadOnly]);

  const refreshSelectedMember = useCallback(async () => {
    if (biReadOnly) {
      setDetailLoading(false);
      setDetailError("");
      setSelectedMember(null);
      return;
    }
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
  }, [biReadOnly, selectedUserId]);

  useEffect(() => {
    void refreshBi();
  }, [refreshBi]);

  useEffect(() => {
    void refreshMembers();
  }, [refreshMembers]);

  useEffect(() => {
    void refreshAudit();
  }, [refreshAudit]);

  useEffect(() => {
    setActiveTab(normalizeBiPrimaryTab(searchParams.get("tab")));
  }, [searchParams]);

  useEffect(() => {
    void refreshSelectedMember();
  }, [refreshSelectedMember]);

  useEffect(() => {
    const nextTier = filters.tier || "all";
    if (nextTier !== memberFilters.tier) {
      setMemberFilters((current) => ({ ...current, tier: nextTier }));
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

  const updateAuditFilter = useCallback((field: keyof AuditFilterState, value: string) => {
    setAuditFilters((current) => ({ ...current, [field]: value }));
  }, []);

  const navigateFromBossQueue = useCallback(
    (action?: BiBossActionItem) => {
      const handoffFilters = action?.handoffFilters;
      if (action?.source === "members") {
        if (typeof handoffFilters?.expire_within_days === "number") {
          applyMemberFilterPatch({
            ...DEFAULT_MEMBER_FILTERS,
            expire_within_days: handoffFilters.expire_within_days,
          });
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
        applyMemberFilterPatch({ ...DEFAULT_MEMBER_FILTERS, risk_level: "high" });
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
    if (biReadOnly) {
      await refreshBi();
      return;
    }
    await Promise.all([refreshBi(), refreshMembers(), refreshAudit(), refreshSelectedMember()]);
  }, [biReadOnly, refreshAudit, refreshBi, refreshMembers, refreshSelectedMember]);

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
        await refreshBi();
        await refreshMembers();
        await refreshAudit();
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
    [refreshAudit, refreshBi, refreshMembers, refreshSelectedMember, selectedIds, selectedUserId],
  );

  const handleSingleGrant = useCallback(async () => {
    if (!selectedUserId) return;
    try {
      setActionLoading(true);
      await grantMembership({ user_id: selectedUserId, days: 30, tier: "vip", reason: "BI 会员工作台开通" });
      await refreshBi();
      await refreshMembers();
      await refreshAudit();
      await refreshSelectedMember();
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "开通会员失败");
    } finally {
      setActionLoading(false);
    }
  }, [refreshAudit, refreshBi, refreshMembers, refreshSelectedMember, selectedUserId]);

  const handleSingleExtend = useCallback(async () => {
    if (!selectedUserId) return;
    try {
      setActionLoading(true);
      await updateMembership({ user_id: selectedUserId, days: 90, reason: "BI 会员工作台续期 90 天" });
      await refreshBi();
      await refreshMembers();
      await refreshAudit();
      await refreshSelectedMember();
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "续期会员失败");
    } finally {
      setActionLoading(false);
    }
  }, [refreshAudit, refreshBi, refreshMembers, refreshSelectedMember, selectedUserId]);

  const handleSingleRevoke = useCallback(async () => {
    if (!selectedUserId) return;
    try {
      setActionLoading(true);
      await revokeMembership({ user_id: selectedUserId, reason: "BI 会员工作台撤销" });
      await refreshBi();
      await refreshMembers();
      await refreshAudit();
      await refreshSelectedMember();
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "撤销会员失败");
    } finally {
      setActionLoading(false);
    }
  }, [refreshAudit, refreshBi, refreshMembers, refreshSelectedMember, selectedUserId]);

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
    if (memberFilters.expire_within_days !== null) query.set("expire_within_days", String(memberFilters.expire_within_days));
    if (memberFilters.search.trim()) query.set("search", memberFilters.search.trim());
    const suffix = query.toString();
    return apiUrl(`/api/v1/member/export${suffix ? `?${suffix}` : ""}`);
  }, [memberFilters.expire_within_days, memberFilters.risk_level, memberFilters.search, memberFilters.status, memberFilters.tier]);

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

        {(activeTab === "member-ops" || activeTab === "learner-360" || activeTab === "audit") && !biReadOnly ? (
          <section className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" size={16} />
                <input
                  value={memberFilters.search}
                  onChange={(event) => applyMemberFilterPatch({ search: event.target.value, expire_within_days: null })}
                  placeholder="搜索 User ID / 昵称 / 手机号"
                  className="w-full rounded-2xl border bg-white px-10 py-2.5 text-sm outline-none transition focus:border-[var(--primary)]"
                />
              </div>
              <div className="grid flex-1 gap-3 sm:grid-cols-3">
                <select
                  value={memberFilters.status}
                  onChange={(event) => applyMemberFilterPatch({ status: event.target.value, expire_within_days: null })}
                  className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                >
                  <option value="all">全部状态</option>
                  <option value="active">活跃</option>
                  <option value="expired">已过期</option>
                  <option value="revoked">已撤销</option>
                </select>
                <select
                  value={memberFilters.tier}
                  onChange={(event) => applyMemberFilterPatch({ tier: event.target.value, expire_within_days: null })}
                  className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                >
                  <option value="all">全部层级</option>
                  <option value="trial">Trial</option>
                  <option value="vip">VIP</option>
                  <option value="svip">SVIP</option>
                </select>
                <select
                  value={memberFilters.risk_level}
                  onChange={(event) => applyMemberFilterPatch({ risk_level: event.target.value, expire_within_days: null })}
                  className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                >
                  <option value="all">全部风险</option>
                  <option value="low">低风险</option>
                  <option value="medium">中风险</option>
                  <option value="high">高风险</option>
                </select>
              </div>
            </div>
            {memberFilters.expire_within_days !== null ? (
              <p className="mt-3 text-sm text-[var(--muted-foreground)]">
                当前附加筛选：{memberFilters.expire_within_days} 天内到期
              </p>
            ) : null}
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
          biReadOnly ? (
            <BiTabShell title="会员运营（需管理员登录）" summary={BI_READ_ONLY_SUMMARY} />
          ) : (
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
          )
        ) : activeTab === "learner-360" ? (
          biReadOnly ? (
            <BiTabShell title="学员 360（需管理员登录）" summary={BI_READ_ONLY_SUMMARY} />
          ) : (
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
          )
        ) : activeTab === "audit" ? (
          biReadOnly ? (
            <BiTabShell title="经营审计（需管理员登录）" summary={BI_READ_ONLY_SUMMARY} />
          ) : (
          <BiAuditTab
            audit={auditLog}
            loading={auditLoading}
            error={auditError}
            exportHref={exportHref}
            filters={auditFilters}
            onFilterChange={updateAuditFilter}
          />
          )
        ) : (
          <BiTabShell title={activeTabMeta.label} summary={activeTabMeta.summary} />
        )}
      </div>
    </div>
  );
}
