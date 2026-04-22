/* eslint-disable i18n/no-literal-ui-text */
"use client";

import type { MemberListItem } from "@/lib/member-api";
import { formatTime } from "./BiShared";

type BiMemberAdminTableProps = {
  items: MemberListItem[];
  selectedIds: string[];
  loading?: boolean;
  onToggle: (userId: string) => void;
  onOpen: (userId: string) => void;
};

function statusTone(status: string) {
  if (status === "active") return "bg-emerald-100 text-emerald-700";
  if (status === "expiring_soon") return "bg-amber-100 text-amber-700";
  if (status === "expired") return "bg-zinc-200 text-zinc-700";
  if (status === "revoked") return "bg-rose-100 text-rose-700";
  return "bg-slate-100 text-slate-700";
}

export function BiMemberAdminTable({
  items,
  selectedIds,
  loading = false,
  onToggle,
  onOpen,
}: BiMemberAdminTableProps) {
  return (
    <div className="overflow-hidden rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-[var(--secondary)]/50 text-[var(--muted-foreground)]">
            <tr>
              <th className="px-4 py-3 text-left font-medium">选择</th>
              <th className="px-4 py-3 text-left font-medium">会员</th>
              <th className="px-4 py-3 text-left font-medium">等级</th>
              <th className="px-4 py-3 text-left font-medium">状态</th>
              <th className="px-4 py-3 text-left font-medium">最近活跃</th>
              <th className="px-4 py-3 text-left font-medium">到期时间</th>
              <th className="px-4 py-3 text-left font-medium">风险</th>
              <th className="px-4 py-3 text-left font-medium">积分</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]/40">
            {items.map((item) => {
              const checked = selectedIds.includes(item.user_id);
              return (
                <tr key={item.user_id} className="transition hover:bg-[var(--secondary)]/30">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(item.user_id)}
                      className="h-4 w-4 rounded border-[var(--border)] text-[var(--primary)] focus:ring-[var(--primary)]"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => onOpen(item.user_id)} className="text-left">
                      <div className="font-medium text-[var(--foreground)]">{item.display_name}</div>
                      <div className="mt-1 text-xs text-[var(--muted-foreground)]">
                        {item.user_id} · {item.phone}
                      </div>
                    </button>
                  </td>
                  <td className="px-4 py-3">{item.tier.toUpperCase()}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs ${statusTone(item.status)}`}>{item.status}</span>
                  </td>
                  <td className="px-4 py-3 text-[var(--muted-foreground)]">{formatTime(item.last_active_at)}</td>
                  <td className="px-4 py-3 text-[var(--muted-foreground)]">{formatTime(item.expire_at)}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-[var(--secondary)] px-2.5 py-1 text-xs text-[var(--secondary-foreground)]">
                      {item.risk_level}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[var(--foreground)]">{item.points_balance}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {!loading && items.length === 0 ? (
        <div className="px-5 py-10 text-center text-sm text-[var(--muted-foreground)]">当前筛选下没有会员。</div>
      ) : null}
    </div>
  );
}
