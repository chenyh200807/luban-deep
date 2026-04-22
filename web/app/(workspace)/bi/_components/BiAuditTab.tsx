/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { MemberAuditLogResponse } from "@/lib/member-api";
import { SectionHeader, formatTime } from "./BiShared";

type BiAuditTabProps = {
  audit: MemberAuditLogResponse | null;
  loading?: boolean;
  error?: string;
  exportHref?: string;
};

export function BiAuditTab({ audit, loading = false, error = "", exportHref = "" }: BiAuditTabProps) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionHeader title="经营审计" extra={loading ? "加载中" : `${audit?.total ?? 0} 条记录`} />
        {exportHref ? (
          <a
            href={exportHref}
            className="rounded-full border border-[var(--border)] bg-white px-4 py-2 text-sm text-[var(--foreground)] transition hover:bg-[var(--secondary)]"
          >
            导出当前会员 CSV
          </a>
        ) : null}
      </div>

      {error ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
      ) : null}

      <div className="overflow-hidden rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
        <div className="grid grid-cols-[180px_160px_160px_minmax(220px,1fr)_180px] gap-0 border-b border-[var(--border)]/50 bg-[var(--secondary)]/50 px-4 py-3 text-xs tracking-[0.16em] text-[var(--muted-foreground)]">
          <span>时间</span>
          <span>操作人</span>
          <span>动作</span>
          <span>目标与原因</span>
          <span>目标用户</span>
        </div>
        <div className="divide-y divide-[var(--border)]/40">
          {(audit?.items ?? []).map((item) => (
            <div
              key={item.id}
              className="grid grid-cols-[180px_160px_160px_minmax(220px,1fr)_180px] gap-0 px-4 py-4 text-sm"
            >
              <span className="text-[var(--muted-foreground)]">{formatTime(item.created_at)}</span>
              <span>{item.operator ?? "--"}</span>
              <span>{item.action ?? "--"}</span>
              <span className="text-[var(--secondary-foreground)]">{item.reason || "--"}</span>
              <span className="text-[var(--secondary-foreground)]">{item.target_user ?? "--"}</span>
            </div>
          ))}
          {!loading && (audit?.items?.length ?? 0) === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-[var(--muted-foreground)]">暂无审计记录。</div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
