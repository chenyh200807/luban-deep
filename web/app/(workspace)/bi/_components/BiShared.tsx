/* eslint-disable i18n/no-literal-ui-text */
"use client";

import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  CircleAlert,
  RefreshCw,
  ShieldAlert,
  Target,
  Wallet,
  Bot,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import type { BiAlertItem, BiMetricCard, BiRankItem } from "@/lib/bi-api";

export const BI_PRIMARY_TABS = [
  {
    key: "overview",
    label: "总览",
    summary: "当前先保留现有全量内容，作为老板工作台的总览入口。",
  },
  {
    key: "quality",
    label: "质量",
    summary: "质量主线聚焦趋势波动、异常中心与当前数据完整性。",
  },
  {
    key: "member-ops",
    label: "会员运营",
    summary: "会员运营分区会在后续任务中独立收口，不在本次 shell 内展开。",
  },
  {
    key: "tutorbot",
    label: "TutorBot",
    summary: "TutorBot 主线会在后续任务中拆成独立视图与操作面板。",
  },
] as const;

export type BiPrimaryTab = (typeof BI_PRIMARY_TABS)[number]["key"];

export type BiFilterState = {
  capability: string;
  entrypoint: string;
  tier: string;
};

export type BiFilterField = keyof BiFilterState;

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

export function normalizeBiPrimaryTab(value: string | null | undefined): BiPrimaryTab {
  if (value === "quality" || value === "member-ops" || value === "tutorbot") {
    return value;
  }
  return "overview";
}

export function getBiPrimaryTabHref(tab: BiPrimaryTab) {
  return tab === "overview" ? "/bi" : `/bi?tab=${tab}`;
}

export function formatNumber(value: number | string) {
  if (typeof value === "string") return value;
  if (!Number.isFinite(value)) return "--";
  if (Math.abs(value) >= 1000) return numberFormatter.format(value);
  return String(Math.round(value * 10) / 10);
}

export function formatPercent(value?: number) {
  if (value === undefined || Number.isNaN(value)) return "--";
  if (value > 1) return `${numberFormatter.format(value)}%`;
  return `${numberFormatter.format(value * 100)}%`;
}

export function formatCurrency(value?: number) {
  if (value === undefined || Number.isNaN(value)) return "--";
  return `¥${currencyFormatter.format(value)}`;
}

export function formatTime(value?: string) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateFormatter.format(date);
}

export function formatDuration(minutes?: number) {
  if (minutes === undefined || Number.isNaN(minutes)) return "--";
  if (minutes < 60) return `${Math.round(minutes)} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return `${hours} 小时${rest ? ` ${rest} 分钟` : ""}`;
}

export function toneClasses(level?: string) {
  if (level === "critical") return "bg-rose-100 text-rose-700";
  if (level === "warning") return "bg-amber-100 text-amber-700";
  return "bg-slate-100 text-slate-700";
}

export function metricToneClasses(tone?: string) {
  if (tone === "good") return "text-emerald-600";
  if (tone === "warning") return "text-amber-600";
  if (tone === "critical") return "text-rose-600";
  return "text-[var(--foreground)]";
}

export function sparkPath(values: number[], width = 240, height = 72) {
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

export function createLoadingCards(): BiMetricCard[] {
  return Array.from({ length: 6 }, (_, index) => ({
    label: `加载中 ${index + 1}`,
    value: "--",
    hint: "等待 BI 接口",
    delta: "",
    tone: "neutral" as const,
  }));
}

export function metricIconByIndex(index: number) {
  const icons: LucideIcon[] = [BarChart3, Bot, Sparkles, Target, Wallet, CircleAlert];
  return icons[index % icons.length];
}

export function SectionHeader({ title, extra }: { title: string; extra?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h2 className="text-sm font-semibold tracking-[0.18em] text-[var(--muted-foreground)]">{title}</h2>
      {extra ? <span className="text-xs text-[var(--muted-foreground)]">{extra}</span> : null}
    </div>
  );
}

export function MetricCard({
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

export function MiniStatCard({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
      <p className="text-xs text-[var(--muted-foreground)]">{label}</p>
      <p className="mt-1 text-lg font-semibold tracking-tight text-[var(--foreground)]">{formatNumber(value)}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
  );
}

export function RankingCard({
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
  items: BiRankItem[];
  emptyText: string;
  icon?: ReactNode;
  headerMeta?: string;
  footerItems?: BiRankItem[];
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

export function SimpleListCard({
  title,
  items,
  emptyText,
  icon,
  footer,
}: {
  title: string;
  items: Array<Pick<BiRankItem, "label" | "value" | "hint">>;
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

export function AlertCard({ item }: { item: BiAlertItem }) {
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

export function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-2xl bg-[var(--secondary)] px-4 py-3">
      <span className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">{label}</span>
      <span className="max-w-[70%] text-right text-sm text-[var(--secondary-foreground)]">{value}</span>
    </div>
  );
}

export function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

export function BiFiltersPanel({
  filters,
  activeFilters,
  onChange,
  onReset,
}: {
  filters: BiFilterState;
  activeFilters: string[];
  onChange: (field: BiFilterField, value: string) => void;
  onReset: () => void;
}) {
  return (
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
          onChange={(value) => onChange("capability", value)}
        />
        <FilterSelect
          label="Entrypoint"
          value={filters.entrypoint}
          options={FILTER_OPTIONS.entrypoint}
          onChange={(value) => onChange("entrypoint", value)}
        />
        <FilterSelect
          label="Tier"
          value={filters.tier}
          options={FILTER_OPTIONS.tier}
          onChange={(value) => onChange("tier", value)}
        />
        <div className="flex items-end">
          <button
            type="button"
            onClick={onReset}
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
  );
}

export function BiIssuesBanner({ issues }: { issues: string[] }) {
  if (!issues.length) return null;

  return (
    <div className="rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-sm text-amber-800">
      <div className="flex items-start gap-2.5">
        <ShieldAlert size={15} className="mt-0.5 shrink-0" />
        <div>
          <p className="font-medium">部分 BI 接口未完全加载，页面已降级展示。</p>
          <p className="mt-1 text-xs leading-5 text-amber-700">{issues[0]}</p>
          {issues.length > 1 ? (
            <p className="mt-1 text-[11px] leading-5 text-amber-700/90">其余 {issues.length - 1} 条已折叠，不在首页堆叠展示。</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function BiTabShell({ title, summary }: { title: string; summary: string }) {
  return (
    <section className="surface-card overflow-hidden border-0 bg-[linear-gradient(135deg,rgba(21,19,18,0.95),rgba(42,33,29,0.94),rgba(143,70,37,0.88))] p-6 text-white shadow-[0_24px_60px_rgba(31,26,23,0.16)]">
      <div className="max-w-3xl">
        <p className="text-xs tracking-[0.24em] text-white/70">COMMAND DECK SHELL</p>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight">{title}</h2>
        <p className="mt-3 text-sm leading-6 text-white/75">{summary}</p>
        <p className="mt-5 text-sm leading-6 text-white/70">
          本次任务只先完成 BI Command Deck 的统一壳层与主分区骨架；该分区的完整内容拆分会在后续任务继续实现。
        </p>
      </div>
    </section>
  );
}

function RankRow({
  item,
  compact = false,
}: {
  item: Pick<BiRankItem, "label" | "value" | "rate" | "hint" | "secondary">;
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
