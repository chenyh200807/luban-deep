/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { RefreshCw, Search } from "lucide-react";
import type { BiLubanFeedbackResponse, BiLubanFeedbackStats } from "@/lib/bi-api";
import { formatNumber, formatPercent, formatTime, SectionHeader } from "./BiShared";

export type LubanFeedbackFilterState = {
  q: string;
  status: string;
  source_page: string;
};

type BiLubanFeedbackTabProps = {
  stats: BiLubanFeedbackStats | null;
  responses: BiLubanFeedbackResponse[];
  total: number;
  loading: boolean;
  error: string;
  filters: LubanFeedbackFilterState;
  onFilterChange: (field: keyof LubanFeedbackFilterState, value: string) => void;
  onRefresh: () => void;
};

const MOST_VALUABLE_LABELS: Record<string, string> = {
  case_grading: "案例题阅卷",
  error_coach: "错因陪练",
  qa: "AI 答疑",
  none_yet: "暂无帮助",
  unknown: "未填",
};
const WILL_CONTINUE_LABELS: Record<string, string> = {
  definitely: "一定会用",
  probably: "大概率用",
  depends: "看后续",
  probably_not: "可能不会",
  no: "不会再用",
  unknown: "未填",
};
const PAY_LABELS: Record<string, string> = {
  happy_to_pay: "很愿付费",
  if_priced_right: "价格合适就付",
  free_only: "只用免费",
  no_pay: "不会付费",
  unsure: "说不好",
  unknown: "未填",
};
const REVISIT_LABELS: Record<string, string> = {
  very_willing: "非常愿意",
  ok: "可以约",
  depends_time: "看时间",
  no: "不方便",
  unknown: "未填",
};
const ATTEMPT_LABELS: Record<string, string> = {
  first: "一战",
  second: "二战",
  third_plus: "三战及以上",
  unknown: "未填",
};
const TIMEFRAME_LABELS: Record<string, string> = {
  within_1m: "1 个月内",
  "1to3m": "1–3 个月",
  "3to6m": "3–6 个月",
  over_6m: "半年以上",
  passed: "已考完",
  unknown: "未填",
};
const STATUS_LABELS: Record<string, string> = {
  submitted: "待处理",
  contacted: "已联系",
  interviewed: "已回访",
  resolved: "已闭环",
  archived: "已归档",
  unknown: "未知",
};

function label(map: Record<string, string>, key: string): string {
  return map[key] || key || "未填";
}

function LubanMetric({ label, value, hint, tone }: { label: string; value: number | string; hint?: string; tone?: string }) {
  return (
    <div className="rounded-2xl border border-[var(--border)]/60 bg-white p-4">
      <p className="text-xs font-medium tracking-[0.08em] text-[var(--muted-foreground)]">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone || "text-[var(--foreground)]"}`}>{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
  );
}

function BreakdownCard({
  title,
  rows,
  labelMap,
}: {
  title: string;
  rows: Array<Record<string, string | number>>;
  labelMap?: Record<string, string>;
}) {
  const labelKey = rows.length ? Object.keys(rows[0]).find((k) => k !== "count") || "" : "";
  const max = rows.reduce((m, r) => Math.max(m, Number(r.count) || 0), 0);
  return (
    <div className="surface-card border border-[var(--border)]/60 bg-white/90 p-4 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
      <p className="text-sm font-semibold text-[var(--foreground)]">{title}</p>
      <div className="mt-3 space-y-2">
        {rows.length ? (
          rows.map((row) => {
            const raw = String(row[labelKey] ?? "");
            const text = labelMap ? label(labelMap, raw) : raw || "未填";
            const count = Number(row.count) || 0;
            const pct = max ? Math.round((count / max) * 100) : 0;
            return (
              <div key={raw} className="flex items-center gap-3">
                <span className="w-24 shrink-0 truncate text-xs text-[var(--muted-foreground)]">{text}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--secondary)]">
                  <div className="h-full rounded-full bg-[var(--primary)]" style={{ width: `${pct}%` }} />
                </div>
                <span className="w-8 shrink-0 text-right text-xs font-medium text-[var(--foreground)]">{count}</span>
              </div>
            );
          })
        ) : (
          <p className="text-xs text-[var(--muted-foreground)]">暂无数据</p>
        )}
      </div>
    </div>
  );
}

function ResponseRow({ item }: { item: BiLubanFeedbackResponse }) {
  const npsTone =
    item.nps === null ? "text-[var(--muted-foreground)]" : item.nps >= 9 ? "text-emerald-600" : item.nps <= 6 ? "text-rose-600" : "text-amber-600";
  const contact = [item.wechat_id ? `微信 ${item.wechat_id}` : "", item.phone ? `手机 ${item.phone}` : ""].filter(Boolean).join(" / ") || "—";
  return (
    <div className="grid grid-cols-[88px_minmax(200px,1fr)_180px_140px] gap-3 px-5 py-4 text-sm">
      <div>
        <p className={`text-lg font-semibold ${npsTone}`}>{item.nps === null ? "—" : item.nps}</p>
        <p className="text-xs text-[var(--muted-foreground)]">满意度 {item.overall_satisfaction ?? "—"}/5</p>
      </div>
      <div className="min-w-0">
        <p className="text-xs text-[var(--muted-foreground)]">
          {label(ATTEMPT_LABELS, item.attempt_count)} · {label(TIMEFRAME_LABELS, item.exam_timeframe)} · 继续：{label(WILL_CONTINUE_LABELS, item.will_continue)} · 付费：{label(PAY_LABELS, item.pay_willingness)}
        </p>
        {item.unsolved_pain ? <p className="mt-1 text-[var(--foreground)]">痛点：{item.unsolved_pain}</p> : null}
        {item.top_suggestion ? <p className="mt-1 text-[var(--foreground)]">建议：{item.top_suggestion}</p> : null}
        {item.one_word ? <p className="mt-1 text-xs italic text-[var(--muted-foreground)]">“{item.one_word}”</p> : null}
      </div>
      <div className="text-xs">
        <p className="text-[var(--foreground)]">{contact}</p>
        <p className="mt-1 text-[var(--muted-foreground)]">回访意愿：{label(REVISIT_LABELS, item.revisit_willingness)}</p>
        <p className="mt-0.5 text-[var(--muted-foreground)]">状态：{label(STATUS_LABELS, item.status)}</p>
      </div>
      <div className="text-right text-xs text-[var(--muted-foreground)]">{formatTime(item.created_at)}</div>
    </div>
  );
}

export function BiLubanFeedbackTab({
  stats,
  responses,
  total,
  loading,
  error,
  filters,
  onFilterChange,
  onRefresh,
}: BiLubanFeedbackTabProps) {
  const summary = stats?.summary;
  const storageStatus = stats?.storage_status || "unknown";

  return (
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <div className="surface-card border border-[var(--border)]/60 bg-white/90 p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <SectionHeader title="内测回访池" extra={`数据源：${storageStatus}`} />
              <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">
                这里展示内测回访问卷的真实答卷，用于读懂 NPS、满意度、分层背景，并跟进高价值用户。
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

          <div className="mt-5 grid gap-3 md:grid-cols-5">
            <LubanMetric label="回访总数" value={summary?.total_responses ?? "--"} />
            <LubanMetric
              label="NPS 分值"
              value={summary ? summary.nps_score : "--"}
              hint={summary ? `推荐 ${summary.promoters} / 贬损 ${summary.detractors}` : undefined}
              tone={summary && summary.nps_score >= 0 ? "text-emerald-600" : "text-rose-600"}
            />
            <LubanMetric label="平均满意度" value={summary ? `${summary.avg_satisfaction}/5` : "--"} hint={summary ? `${summary.satisfaction_base} 份评分` : undefined} />
            <LubanMetric label="愿意回访" value={summary?.revisit_willing_count ?? "--"} hint={formatPercent(summary?.revisit_willing_rate)} />
            <LubanMetric label="留联系方式" value={summary?.with_contact_count ?? "--"} hint={formatPercent(summary?.with_contact_rate)} />
          </div>

          <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
            <label className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" size={15} />
              <input
                value={filters.q}
                onChange={(event) => onFilterChange("q", event.target.value)}
                placeholder="搜索痛点 / 建议 / 联系方式 / 一句话"
                className="w-full rounded-2xl border bg-white px-10 py-2.5 text-sm outline-none transition focus:border-[var(--primary)]"
              />
            </label>
            <select
              value={filters.status}
              onChange={(event) => onFilterChange("status", event.target.value)}
              className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
            >
              <option value="">全部状态</option>
              <option value="submitted">待处理</option>
              <option value="contacted">已联系</option>
              <option value="interviewed">已回访</option>
              <option value="resolved">已闭环</option>
              <option value="archived">已归档</option>
            </select>
            <input
              value={filters.source_page}
              onChange={(event) => onFilterChange("source_page", event.target.value)}
              placeholder="来源页"
              className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
            />
            <div className="flex items-center justify-end text-sm text-[var(--muted-foreground)]">共 {formatNumber(total)} 条</div>
          </div>
          {error ? <p className="mt-3 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</p> : null}
        </div>

        <div className="surface-card overflow-hidden border border-[var(--border)]/60 bg-white/90 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
          <div className="grid grid-cols-[88px_minmax(200px,1fr)_180px_140px] gap-3 border-b border-[var(--border)]/60 bg-[var(--secondary)] px-5 py-3 text-xs font-medium tracking-[0.12em] text-[var(--muted-foreground)]">
            <span>NPS / 满意</span>
            <span>背景与反馈</span>
            <span>联系 / 意愿</span>
            <span className="text-right">提交时间</span>
          </div>
          <div className="divide-y divide-[var(--border)]/60">
            {loading ? (
              <p className="px-5 py-8 text-sm text-[var(--muted-foreground)]">正在加载内测回访...</p>
            ) : responses.length ? (
              responses.map((item) => <ResponseRow key={item.id || `${item.created_at}-${item.nps}`} item={item} />)
            ) : (
              <p className="px-5 py-8 text-sm text-[var(--muted-foreground)]">当前筛选下暂无回访记录。</p>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <BreakdownCard title="NPS 分布" rows={stats?.nps_breakdown ?? []} />
        <BreakdownCard title="满意度分布" rows={stats?.satisfaction_breakdown ?? []} />
        <BreakdownCard title="最有价值功能" rows={stats?.most_valuable_breakdown ?? []} labelMap={MOST_VALUABLE_LABELS} />
        <BreakdownCard title="继续使用意愿" rows={stats?.will_continue_breakdown ?? []} labelMap={WILL_CONTINUE_LABELS} />
        <BreakdownCard title="付费意愿" rows={stats?.pay_willingness_breakdown ?? []} labelMap={PAY_LABELS} />
        <BreakdownCard title="考试次数分层" rows={stats?.attempt_count_breakdown ?? []} labelMap={ATTEMPT_LABELS} />
        <BreakdownCard title="距考时间分层" rows={stats?.exam_timeframe_breakdown ?? []} labelMap={TIMEFRAME_LABELS} />
      </div>
    </section>
  );
}
