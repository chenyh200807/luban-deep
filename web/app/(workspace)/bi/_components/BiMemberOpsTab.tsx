/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { ClipboardList, Layers3, ShieldAlert, UserRound } from "lucide-react";
import type { BotOverlaySummary, HeartbeatJob, MemberDetail, MemberListItem } from "@/lib/member-api";
import { BiMember360Panel } from "./BiMember360Panel";
import { BiMemberAdminTable } from "./BiMemberAdminTable";
import { MetricCard, SectionHeader } from "./BiShared";

type BiMemberOpsTabProps = {
  loading?: boolean;
  memberItems: MemberListItem[];
  selectedIds: string[];
  selectedMember: MemberDetail | null;
  detailLoading?: boolean;
  detailError?: string;
  actionLoading?: boolean;
  totalCount: number;
  onToggleMember: (userId: string) => void;
  onOpenMember: (userId: string) => void;
  onBatchGrant: () => void;
  onBatchRevoke: () => void;
  onGrantSingle: () => void;
  onExtendSingle: () => void;
  onRevokeSingle: () => void;
  onAddNote: (content: string) => void;
  onRecordOpsAction: (payload: {
    status: "open" | "in_progress" | "done" | "follow_up";
    result: string;
    action_title?: string;
    next_follow_up_at?: string;
  }) => Promise<void>;
  onToggleHeartbeat: (job: HeartbeatJob) => void;
  onApplyOverlay: (overlay: BotOverlaySummary) => void;
};

export function BiMemberOpsTab({
  loading = false,
  memberItems,
  selectedIds,
  selectedMember,
  detailLoading = false,
  detailError = "",
  actionLoading = false,
  totalCount,
  onToggleMember,
  onOpenMember,
  onBatchGrant,
  onBatchRevoke,
  onGrantSingle,
  onExtendSingle,
  onRevokeSingle,
  onAddNote,
  onRecordOpsAction,
  onToggleHeartbeat,
  onApplyOverlay,
}: BiMemberOpsTabProps) {
  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard title="当前列表" value={memberItems.length} hint={`总会员 ${totalCount}`} tone="neutral" icon={ClipboardList} />
        <MetricCard title="批量勾选" value={selectedIds.length} hint="用于批量开通 / 撤销" tone="neutral" icon={Layers3} />
        <MetricCard title="当前详情" value={selectedMember?.display_name ?? "--"} hint={selectedMember?.user_id ?? "未选择会员"} tone="neutral" icon={UserRound} />
        <MetricCard title="工作区状态" value={loading ? "加载中" : "就绪"} hint="会员运营后台主工作区" tone="neutral" icon={ShieldAlert} />
      </section>

      <section className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionHeader title="会员运营" extra="高密列表 + 学员 360 + 批量动作" />
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={onBatchGrant}
              disabled={selectedIds.length === 0 || actionLoading}
              className="rounded-full bg-[var(--foreground)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              批量开通 30 天 VIP
            </button>
            <button
              type="button"
              onClick={onBatchRevoke}
              disabled={selectedIds.length === 0 || actionLoading}
              className="rounded-full bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 disabled:opacity-60"
            >
              批量撤销
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
          <BiMemberAdminTable
            items={memberItems}
            selectedIds={selectedIds}
            loading={loading}
            onToggle={onToggleMember}
            onOpen={onOpenMember}
          />

          <BiMember360Panel
            member={selectedMember}
            loading={detailLoading}
            error={detailError}
            actionLoading={actionLoading}
            onGrant={onGrantSingle}
            onExtend={onExtendSingle}
            onRevoke={onRevokeSingle}
            onAddNote={onAddNote}
            onRecordOpsAction={onRecordOpsAction}
            onToggleHeartbeat={onToggleHeartbeat}
            onApplyOverlay={onApplyOverlay}
          />
        </div>
      </section>
    </div>
  );
}
