/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Crown, RefreshCw, Search, ShieldAlert, Sparkles, Wallet } from "lucide-react";
import {
  createMemberNote,
  getMemberDashboard,
  getMemberDetail,
  grantMembership,
  listMembers,
  revokeMembership,
  updateMembership,
  type MemberDashboard,
  type MemberDetail,
  type MemberListItem,
} from "@/lib/member-api";

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function formatTime(value: string) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return dateFormatter.format(date);
}

function statusTone(status: string) {
  if (status === "active") return "bg-emerald-100 text-emerald-700";
  if (status === "expiring_soon") return "bg-amber-100 text-amber-700";
  if (status === "expired") return "bg-zinc-200 text-zinc-700";
  if (status === "revoked") return "bg-rose-100 text-rose-700";
  return "bg-[var(--muted)] text-[var(--muted-foreground)]";
}

export default function MemberPage() {
  const [dashboard, setDashboard] = useState<MemberDashboard | null>(null);
  const [members, setMembers] = useState<MemberListItem[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [selectedMember, setSelectedMember] = useState<MemberDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState("");
  const [noteDraft, setNoteDraft] = useState("");
  const [filters, setFilters] = useState({
    search: "",
    status: "all",
    tier: "all",
    risk_level: "all",
  });

  const fetchDashboard = useCallback(async () => {
    setDashboard(await getMemberDashboard());
  }, []);

  const fetchMembers = useCallback(async () => {
    const list = await listMembers({
      page: 1,
      page_size: 20,
      search: filters.search.trim() || undefined,
      status: filters.status,
      tier: filters.tier,
      risk_level: filters.risk_level,
    });
    setMembers(list.items);
    if (!selectedUserId && list.items[0]) {
      setSelectedUserId(list.items[0].user_id);
    }
    if (selectedUserId && !list.items.some((item) => item.user_id === selectedUserId)) {
      setSelectedUserId(list.items[0]?.user_id ?? "");
    }
  }, [filters.risk_level, filters.search, filters.status, filters.tier, selectedUserId]);

  useEffect(() => {
    const run = async () => {
      try {
        setLoading(true);
        setError("");
        await Promise.all([fetchDashboard(), fetchMembers()]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [fetchDashboard, fetchMembers]);

  useEffect(() => {
    if (!selectedUserId) {
      setSelectedMember(null);
      return;
    }
    const run = async () => {
      try {
        setDetailLoading(true);
        setSelectedMember(await getMemberDetail(selectedUserId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "会员详情加载失败");
      } finally {
        setDetailLoading(false);
      }
    };
    void run();
  }, [selectedUserId]);

  const refreshAll = async () => {
    try {
      setLoading(true);
      await Promise.all([fetchDashboard(), fetchMembers()]);
      if (selectedUserId) {
        setSelectedMember(await getMemberDetail(selectedUserId));
      }
    } finally {
      setLoading(false);
    }
  };

  const applyFilters = async () => {
    try {
      setLoading(true);
      await fetchMembers();
    } finally {
      setLoading(false);
    }
  };

  const handleQuickAction = async (type: "grant" | "extend" | "revoke") => {
    if (!selectedUserId) return;
    try {
      setActionLoading(true);
      if (type === "grant") {
        await grantMembership({ user_id: selectedUserId, days: 30, tier: "vip", reason: "会员工作台快捷开通" });
      } else if (type === "extend") {
        await updateMembership({ user_id: selectedUserId, days: 90, reason: "会员工作台续期 90 天" });
      } else {
        await revokeMembership({ user_id: selectedUserId, reason: "会员工作台手动撤销" });
      }
      setSelectedMember(await getMemberDetail(selectedUserId));
      await Promise.all([fetchDashboard(), fetchMembers()]);
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddNote = async () => {
    if (!selectedUserId || !noteDraft.trim()) return;
    try {
      setActionLoading(true);
      await createMemberNote(selectedUserId, { content: noteDraft.trim(), pinned: false, channel: "manual" });
      setSelectedMember(await getMemberDetail(selectedUserId));
      setNoteDraft("");
    } finally {
      setActionLoading(false);
    }
  };

  const weakTopics = useMemo(() => {
    if (!selectedMember) return [];
    return Object.values(selectedMember.chapter_mastery)
      .slice()
      .sort((a, b) => a.mastery - b.mastery)
      .slice(0, 4);
  }, [selectedMember]);

  return (
    <div className="h-full overflow-y-auto bg-[radial-gradient(circle_at_top_left,_rgba(195,90,44,0.12),_transparent_32%),linear-gradient(180deg,#faf9f6_0%,#f4efe8_100%)] px-6 py-6">
      <div className="mx-auto flex max-w-[1480px] flex-col gap-6">
        <section className="surface-card overflow-hidden border-0 bg-[linear-gradient(135deg,#1f1a17_0%,#2d2119_45%,#8f4625_100%)] text-white shadow-[0_24px_60px_rgba(31,26,23,0.25)]">
          <div className="flex flex-col gap-6 p-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs tracking-[0.2em] text-white/75">
                <Crown size={14} />
                MEMBER CONSOLE
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">会员系统迁移版工作台</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-white/75">
                参考 FastAPI20251222 项目的会员后台结构，现已接入 DeepTutor 当前后端与 Next.js 工作区。
                这里可以直接查看会员状态、续期风险、积分钱包和学习画像。
              </p>
            </div>
            <button
              onClick={() => void refreshAll()}
              disabled={loading}
              className="inline-flex items-center gap-2 self-start rounded-full bg-white px-4 py-2 text-sm font-medium text-[#2d2119] transition hover:bg-white/90 disabled:opacity-60"
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
              刷新数据
            </button>
          </div>
        </section>

        {error ? (
          <div className="surface-card border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard title="活跃会员" value={dashboard?.active_count ?? "--"} hint={`总会员 ${dashboard?.total_count ?? "--"}`} icon={<Sparkles size={18} />} />
          <MetricCard title="7 天内到期" value={dashboard?.expiring_soon_count ?? "--"} hint="建议跟进续费" icon={<ShieldAlert size={18} />} />
          <MetricCard title="今日新增" value={dashboard?.new_today_count ?? "--"} hint={`健康分 ${dashboard?.health_score ?? "--"}`} icon={<RefreshCw size={18} />} />
          <MetricCard title="流失预警" value={dashboard?.churn_risk_count ?? "--"} hint={`自动续费覆盖 ${dashboard?.auto_renew_coverage ?? "--"}%`} icon={<Wallet size={18} />} />
        </section>

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_420px]">
          <div className="space-y-6">
            <div className="surface-card p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" size={16} />
                  <input
                    value={filters.search}
                    onChange={(event) => setFilters((prev) => ({ ...prev, search: event.target.value }))}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void applyFilters();
                    }}
                    placeholder="搜索 User ID / 昵称 / 手机号"
                    className="w-full rounded-2xl border bg-white px-10 py-2.5 text-sm outline-none transition focus:border-[var(--primary)]"
                  />
                </div>
                <div className="grid flex-1 gap-3 sm:grid-cols-3">
                  <select
                    value={filters.status}
                    onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}
                    className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                  >
                    <option value="all">全部状态</option>
                    <option value="active">活跃</option>
                    <option value="expiring_soon">即将到期</option>
                    <option value="expired">已过期</option>
                    <option value="revoked">已撤销</option>
                  </select>
                  <select
                    value={filters.tier}
                    onChange={(event) => setFilters((prev) => ({ ...prev, tier: event.target.value }))}
                    className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                  >
                    <option value="all">全部层级</option>
                    <option value="trial">Trial</option>
                    <option value="vip">VIP</option>
                    <option value="svip">SVIP</option>
                  </select>
                  <select
                    value={filters.risk_level}
                    onChange={(event) => setFilters((prev) => ({ ...prev, risk_level: event.target.value }))}
                    className="rounded-2xl border bg-white px-3 py-2.5 text-sm outline-none focus:border-[var(--primary)]"
                  >
                    <option value="all">全部风险</option>
                    <option value="low">低风险</option>
                    <option value="medium">中风险</option>
                    <option value="high">高风险</option>
                  </select>
                </div>
                <button
                  onClick={() => void applyFilters()}
                  className="rounded-2xl bg-[var(--primary)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
                >
                  应用筛选
                </button>
              </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="surface-card overflow-hidden">
                <div className="flex items-center justify-between border-b px-5 py-4">
                  <div>
                    <h2 className="text-lg font-semibold">会员列表</h2>
                    <p className="text-sm text-[var(--muted-foreground)]">按当前筛选展示前 20 位会员</p>
                  </div>
                  <span className="rounded-full bg-[var(--muted)] px-3 py-1 text-xs text-[var(--muted-foreground)]">
                    {members.length} 人
                  </span>
                </div>
                <div className="divide-y">
                  {members.map((member) => {
                    const active = member.user_id === selectedUserId;
                    return (
                      <button
                        key={member.user_id}
                        onClick={() => setSelectedUserId(member.user_id)}
                        className={`flex w-full items-start gap-4 px-5 py-4 text-left transition ${
                          active ? "bg-[rgba(195,90,44,0.08)]" : "hover:bg-[var(--muted)]/60"
                        }`}
                      >
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--secondary)] text-lg font-semibold text-[var(--primary)]">
                          {member.display_name.slice(0, 1)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{member.display_name}</span>
                            <span className={`rounded-full px-2.5 py-1 text-xs ${statusTone(member.status)}`}>
                              {member.status}
                            </span>
                            <span className="rounded-full bg-[var(--secondary)] px-2.5 py-1 text-xs text-[var(--secondary-foreground)]">
                              {member.tier.toUpperCase()}
                            </span>
                          </div>
                          <p className="mt-1 text-sm text-[var(--muted-foreground)]">
                            {member.user_id} · {member.phone}
                          </p>
                          <div className="mt-3 grid gap-2 text-xs text-[var(--muted-foreground)] sm:grid-cols-3">
                            <span>积分 {member.points_balance}</span>
                            <span>待复习 {member.review_due}</span>
                            <span>到期 {formatTime(member.expire_at)}</span>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                  {!loading && members.length === 0 ? (
                    <div className="px-5 py-10 text-center text-sm text-[var(--muted-foreground)]">当前筛选下没有会员。</div>
                  ) : null}
                </div>
              </div>

              <div className="space-y-6">
                <InsightCard title="会员分层">
                  {(dashboard?.tier_breakdown ?? []).map((item) => (
                    <BarRow key={item.tier} label={item.tier.toUpperCase()} value={item.count} max={dashboard?.total_count ?? 1} />
                  ))}
                </InsightCard>
                <InsightCard title="续费建议">
                  {(dashboard?.recommendations ?? []).map((item) => (
                    <p key={item} className="rounded-2xl bg-[var(--muted)] px-3 py-3 text-sm leading-6 text-[var(--secondary-foreground)]">
                      {item}
                    </p>
                  ))}
                </InsightCard>
              </div>
            </div>
          </div>

          <aside className="space-y-6">
            <div className="surface-card min-h-[320px] p-5">
              {detailLoading ? (
                <div className="py-16 text-center text-sm text-[var(--muted-foreground)]">正在加载会员画像...</div>
              ) : selectedMember ? (
                <>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm text-[var(--muted-foreground)]">{selectedMember.user_id}</p>
                      <h2 className="mt-1 text-2xl font-semibold">{selectedMember.display_name}</h2>
                      <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                        {selectedMember.phone} · {selectedMember.segment} · 风险 {selectedMember.risk_level}
                      </p>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs ${statusTone(selectedMember.status)}`}>
                      {selectedMember.status}
                    </span>
                  </div>

                  <div className="mt-5 grid grid-cols-2 gap-3">
                    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                      <p className="text-xs text-[var(--muted-foreground)]">会员到期</p>
                      <p className="mt-1 text-sm font-medium">{formatTime(selectedMember.expire_at)}</p>
                    </div>
                    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                      <p className="text-xs text-[var(--muted-foreground)]">钱包积分</p>
                      <p className="mt-1 text-sm font-medium">{selectedMember.wallet.balance}</p>
                    </div>
                    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                      <p className="text-xs text-[var(--muted-foreground)]">学习天数</p>
                      <p className="mt-1 text-sm font-medium">{selectedMember.study_days}</p>
                    </div>
                    <div className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                      <p className="text-xs text-[var(--muted-foreground)]">日目标</p>
                      <p className="mt-1 text-sm font-medium">{selectedMember.daily_target} 题</p>
                    </div>
                  </div>

                  <div className="mt-5 flex flex-wrap gap-2">
                    <ActionButton label="开通 30 天 VIP" onClick={() => void handleQuickAction("grant")} disabled={actionLoading} />
                    <ActionButton label="续期 90 天" onClick={() => void handleQuickAction("extend")} disabled={actionLoading} />
                    <ActionButton label="撤销会员" danger onClick={() => void handleQuickAction("revoke")} disabled={actionLoading} />
                  </div>

                  <div className="mt-6">
                    <SectionTitle title="当前焦点" extra={`考试日期 ${selectedMember.exam_date || "--"}`} />
                    <p className="rounded-2xl bg-[linear-gradient(135deg,rgba(195,90,44,0.10),rgba(195,90,44,0.02))] px-4 py-4 text-sm leading-6 text-[var(--secondary-foreground)]">
                      {selectedMember.focus_topic}。当前偏好：{selectedMember.difficulty_preference} 难度、{selectedMember.explanation_style} 讲解。
                    </p>
                  </div>

                  <div className="mt-6">
                    <SectionTitle title="薄弱章节" />
                    <div className="space-y-3">
                      {weakTopics.map((topic) => (
                        <BarRow key={topic.name} label={topic.name} value={topic.mastery} max={100} suffix="%" />
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className="py-16 text-center text-sm text-[var(--muted-foreground)]">从左侧选择一位会员查看详情。</div>
              )}
            </div>

            <div className="surface-card p-5">
              <SectionTitle title="运营备注" extra={selectedMember ? `${selectedMember.recent_notes.length} 条` : ""} />
              <div className="mt-3 flex gap-2">
                <textarea
                  value={noteDraft}
                  onChange={(event) => setNoteDraft(event.target.value)}
                  placeholder="记录本次回访、续费建议或学习状态"
                  className="min-h-[92px] flex-1 rounded-2xl border bg-white px-4 py-3 text-sm outline-none focus:border-[var(--primary)]"
                />
              </div>
              <button
                onClick={() => void handleAddNote()}
                disabled={!selectedUserId || !noteDraft.trim() || actionLoading}
                className="mt-3 w-full rounded-2xl bg-[var(--foreground)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
              >
                添加备注
              </button>
              <div className="mt-4 space-y-3">
                {(selectedMember?.recent_notes ?? []).map((note) => (
                  <div key={note.id} className="rounded-2xl border bg-[var(--muted)]/40 px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs text-[var(--muted-foreground)]">{note.channel}</span>
                      <span className="text-xs text-[var(--muted-foreground)]">{formatTime(note.created_at)}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{note.content}</p>
                  </div>
                ))}
                {selectedMember && selectedMember.recent_notes.length === 0 ? (
                  <p className="text-sm text-[var(--muted-foreground)]">还没有运营备注。</p>
                ) : null}
              </div>
            </div>

            <div className="surface-card p-5">
              <SectionTitle title="最近积分流水" extra={selectedMember ? `${selectedMember.recent_ledger.length} 条` : ""} />
              <div className="mt-4 space-y-3">
                {(selectedMember?.recent_ledger ?? []).map((entry) => (
                  <div key={entry.id} className="flex items-center justify-between rounded-2xl border bg-white px-4 py-3 text-sm">
                    <div>
                      <p className="font-medium">{entry.reason}</p>
                      <p className="mt-1 text-xs text-[var(--muted-foreground)]">{formatTime(entry.created_at)}</p>
                    </div>
                    <span className={entry.delta >= 0 ? "text-emerald-600" : "text-rose-600"}>
                      {entry.delta >= 0 ? `+${entry.delta}` : entry.delta}
                    </span>
                  </div>
                ))}
                {selectedMember && selectedMember.recent_ledger.length === 0 ? (
                  <p className="text-sm text-[var(--muted-foreground)]">暂无积分记录。</p>
                ) : null}
              </div>
            </div>
          </aside>
        </section>
      </div>
    </div>
  );
}

function MetricCard({
  title,
  value,
  hint,
  icon,
}: {
  title: string;
  value: string | number;
  hint: string;
  icon: React.ReactNode;
}) {
  return (
    <article className="surface-card overflow-hidden border-0 bg-white/90 p-5 shadow-[0_10px_30px_rgba(45,33,25,0.06)]">
      <div className="flex items-center justify-between">
        <p className="text-sm text-[var(--muted-foreground)]">{title}</p>
        <div className="rounded-2xl bg-[var(--secondary)] p-2 text-[var(--primary)]">{icon}</div>
      </div>
      <p className="mt-5 text-3xl font-semibold tracking-tight">{value}</p>
      <p className="mt-2 text-sm text-[var(--muted-foreground)]">{hint}</p>
    </article>
  );
}

function InsightCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="surface-card p-5">
      <SectionTitle title={title} />
      <div className="mt-4 space-y-3">{children}</div>
    </div>
  );
}

function SectionTitle({ title, extra }: { title: string; extra?: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <h3 className="text-sm font-semibold tracking-[0.16em] text-[var(--muted-foreground)]">{title}</h3>
      {extra ? <span className="text-xs text-[var(--muted-foreground)]">{extra}</span> : null}
    </div>
  );
}

function BarRow({
  label,
  value,
  max,
  suffix = "",
}: {
  label: string;
  value: number;
  max: number;
  suffix?: string;
}) {
  const percent = Math.max(6, Math.min(100, Math.round((value / Math.max(max, 1)) * 100)));
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span>{label}</span>
        <span className="text-[var(--muted-foreground)]">
          {value}
          {suffix}
        </span>
      </div>
      <div className="h-2 rounded-full bg-[var(--muted)]">
        <div className="h-full rounded-full bg-[linear-gradient(90deg,#c35a2c,#e09554)]" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function ActionButton({
  label,
  onClick,
  disabled,
  danger = false,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full px-4 py-2 text-sm font-medium transition disabled:opacity-60 ${
        danger
          ? "bg-rose-50 text-rose-700 hover:bg-rose-100"
          : "bg-[var(--secondary)] text-[var(--secondary-foreground)] hover:bg-[var(--muted)]"
      }`}
    >
      {label}
    </button>
  );
}
