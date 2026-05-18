/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { ClipboardList, Mail, MessageSquareText, Phone, RefreshCw, Search, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import type { BiInviteTestApplication, BiInviteTestStats } from "@/lib/bi-api";
import { formatNumber, formatPercent, formatTime, SectionHeader } from "./BiShared";

export type InviteTestFilterState = {
  q: string;
  status: string;
  source_page: string;
};

type BiInviteTestTabProps = {
  stats: BiInviteTestStats | null;
  applications: BiInviteTestApplication[];
  total: number;
  loading: boolean;
  error: string;
  filters: InviteTestFilterState;
  onFilterChange: (field: keyof InviteTestFilterState, value: string) => void;
  onRefresh: () => void;
};

export function BiInviteTestTab({
  stats,
  applications,
  total,
  loading,
  error,
  filters,
  onFilterChange,
  onRefresh,
}: BiInviteTestTabProps) {
  const summary = stats?.summary;
  const topPainPoints = stats?.pain_point_breakdown?.slice(0, 5) ?? [];
  const topExamTypes = stats?.exam_type_breakdown?.slice(0, 5) ?? [];
  const storageStatus = stats?.storage_status || "unknown";

  return (
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <div className="surface-card border border-[var(--border)]/60 bg-white/90 p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <SectionHeader title="内测申请池" extra={`数据源：${storageStatus}`} />
              <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
                这里展示公开申请表写入的申请记录，用于筛选首批体验学员和安排回访。
              </p>
            </div>
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-[var(--border)] bg-white px-4 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-[var(--secondary)] disabled:opacity-60"
            >
              <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
              刷新
            </button>
          </div>

          <div className="mt-5 grid gap-3 md:grid-cols-4">
            <InviteMetric label="申请总数" value={summary?.total_applications ?? "--"} />
            <InviteMetric label="可联系人数" value={summary?.unique_contacts ?? "--"} />
            <InviteMetric label="愿意回访" value={summary?.accept_interview_count ?? "--"} hint={formatPercent(summary?.accept_interview_rate)} />
            <InviteMetric label="带错题样本" value={summary?.with_wrong_question_count ?? "--"} hint={formatPercent(summary?.with_wrong_question_rate)} />
          </div>

          <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
            <label className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" size={15} />
              <input
                value={filters.q}
                onChange={(event) => onFilterChange("q", event.target.value)}
                placeholder="搜索姓名 / 手机 / 邮箱 / 考试 / 痛点"
                className="w-full rounded-2xl border bg-white px-10 py-2.5 text-sm outline-none transition focus:border-[var(--primary)]"
              />
            </label>
            <select
              value={filters.status}
              onChange={(event) => onFilterChange("status", event.target.value)}
              className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
            >
              <option value="">全部状态</option>
              <option value="submitted">已提交</option>
              <option value="contacted">已联系</option>
              <option value="accepted">已入选</option>
              <option value="rejected">未入选</option>
            </select>
            <input
              value={filters.source_page}
              onChange={(event) => onFilterChange("source_page", event.target.value)}
              placeholder="来源页"
              className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
            />
            <div className="flex items-center justify-end text-sm text-[var(--muted-foreground)]">
              共 {formatNumber(total)} 条
            </div>
          </div>
          {error ? <p className="mt-3 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
        </div>

        <div className="surface-card overflow-hidden border border-[var(--border)]/60 bg-white/90 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
          <div className="grid grid-cols-[180px_220px_180px_minmax(240px,1fr)_160px] border-b border-[var(--border)]/60 bg-[var(--secondary)] px-5 py-3 text-xs font-medium tracking-[0.12em] text-[var(--muted-foreground)]">
            <span>学员</span>
            <span>联系方式</span>
            <span>考试阶段</span>
            <span>痛点与材料</span>
            <span className="text-right">提交时间</span>
          </div>
          <div className="divide-y divide-[var(--border)]/60">
            {loading ? (
              <p className="px-5 py-8 text-sm text-[var(--muted-foreground)]">正在加载内测申请...</p>
            ) : applications.length ? (
              applications.map((item) => <InviteApplicationRow key={item.id || `${item.phone}-${item.created_at}`} item={item} />)
            ) : (
              <p className="px-5 py-8 text-sm text-[var(--muted-foreground)]">当前筛选下暂无申请记录。</p>
            )}
          </div>
        </div>
      </div>

      <aside className="space-y-5">
        <BreakdownCard title="考试类型" items={topExamTypes.map((item) => ({ label: item.exam_type, count: item.count }))} />
        <BreakdownCard title="最想解决的问题" items={topPainPoints.map((item) => ({ label: item.pain_point, count: item.count }))} />
        <BreakdownCard
          title="备考阶段"
          items={(stats?.exam_stage_breakdown ?? []).slice(0, 5).map((item) => ({ label: item.exam_stage, count: item.count }))}
        />
        <BreakdownCard
          title="每周可测试时间"
          items={(stats?.weekly_time_breakdown ?? []).slice(0, 5).map((item) => ({ label: item.weekly_time, count: item.count }))}
        />
      </aside>
    </section>
  );
}

function InviteMetric({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-[var(--border)]/70 bg-[var(--background)] px-4 py-3">
      <p className="text-xs tracking-[0.16em] text-[var(--muted-foreground)]">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-[var(--foreground)]">{formatNumber(value)}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
  );
}

function InviteApplicationRow({ item }: { item: BiInviteTestApplication }) {
  return (
    <article className="grid grid-cols-[180px_220px_180px_minmax(240px,1fr)_160px] gap-0 px-5 py-4 text-sm">
      <div className="min-w-0">
        <div className="flex items-center gap-2 font-medium text-[var(--foreground)]">
          <UserRound size={15} className="text-[var(--primary)]" />
          <span className="truncate">{item.name || "未命名"}</span>
        </div>
        <p className="mt-2 text-xs text-[var(--muted-foreground)]">{item.source_page || "unknown"}</p>
        <p className="mt-1 text-xs text-[var(--muted-foreground)]">提交 {formatNumber(item.submit_count)} 次</p>
      </div>
      <div className="space-y-2 text-xs text-[var(--muted-foreground)]">
        <ContactLine icon={<Phone size={13} />} value={item.phone || "--"} />
        <ContactLine icon={<Mail size={13} />} value={item.email || "--"} />
        <ContactLine icon={<MessageSquareText size={13} />} value={item.wechat_id || "--"} />
      </div>
      <div className="space-y-2">
        <p className="font-medium text-[var(--foreground)]">{item.exam_type || "--"}</p>
        <p className="text-xs leading-5 text-[var(--muted-foreground)]">{item.exam_stage || "--"}</p>
        <p className="text-xs leading-5 text-[var(--muted-foreground)]">{item.weekly_time || "--"}</p>
      </div>
      <div className="min-w-0 space-y-2">
        <p className="inline-flex rounded-full bg-[var(--secondary)] px-3 py-1 text-xs font-medium text-[var(--foreground)]">
          {item.pain_point || "未填写痛点"}
        </p>
        <p className="line-clamp-2 text-xs leading-5 text-[var(--muted-foreground)]">
          {item.latest_wrong_question || item.current_method || "未填写补充材料"}
        </p>
        {item.accept_interview ? (
          <span className="inline-flex rounded-full bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700">愿意回访</span>
        ) : null}
      </div>
      <div className="text-right text-xs text-[var(--muted-foreground)]">
        <p>{formatTime(item.created_at)}</p>
        <p className="mt-2 inline-flex rounded-full bg-[var(--secondary)] px-2 py-1">{item.status || "submitted"}</p>
      </div>
    </article>
  );
}

function ContactLine({ icon, value }: { icon: ReactNode; value: string }) {
  return (
    <p className="flex min-w-0 items-center gap-2">
      <span className="text-[var(--primary)]">{icon}</span>
      <span className="truncate">{value}</span>
    </p>
  );
}

function BreakdownCard({ title, items }: { title: string; items: Array<{ label: string; count: number }> }) {
  return (
    <div className="surface-card border border-[var(--border)]/60 bg-white/90 p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
      <div className="flex items-center justify-between gap-3">
        <SectionHeader title={title} />
        <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">
          <ClipboardList size={15} />
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {items.length ? (
          items.map((item) => (
            <div key={item.label || title} className="rounded-2xl border bg-[var(--background)] px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium leading-5 text-[var(--foreground)]">{item.label || "unknown"}</p>
                <p className="text-sm font-semibold text-[var(--foreground)]">{formatNumber(item.count)}</p>
              </div>
            </div>
          ))
        ) : (
          <p className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">暂无数据。</p>
        )}
      </div>
    </div>
  );
}
