/* eslint-disable i18n/no-literal-ui-text */
"use client";

import { useState } from "react";
import { Bot, ChevronDown, Clock3, MessageSquareMore, StickyNote } from "lucide-react";
import type { BotOverlaySummary, HeartbeatJob, MemberConversationPreview, MemberDetail } from "@/lib/member-api";
import { InfoLine, SectionHeader, formatTime } from "./BiShared";

type BiMember360PanelProps = {
  member: MemberDetail | null;
  loading?: boolean;
  error?: string;
  actionLoading?: boolean;
  onGrant: () => void;
  onExtend: () => void;
  onRevoke: () => void;
  onAddNote: (content: string) => void;
  onRecordOpsAction: (payload: {
    status: "open" | "in_progress" | "done" | "follow_up";
    result: string;
    action_title?: string;
    next_follow_up_at?: string;
  }) => Promise<void>;
  onRecordConversationView: (conversation: MemberConversationPreview) => Promise<void>;
  onToggleHeartbeat: (job: HeartbeatJob) => void;
  onApplyOverlay: (overlay: BotOverlaySummary) => void;
};

export function BiMember360Panel({
  member,
  loading = false,
  error = "",
  actionLoading = false,
  onGrant,
  onExtend,
  onRevoke,
  onAddNote,
  onRecordOpsAction,
  onRecordConversationView,
  onToggleHeartbeat,
  onApplyOverlay,
}: BiMember360PanelProps) {
  const memberUserId = member?.user_id || "";
  const [expandedConversation, setExpandedConversation] = useState<{
    userId: string;
    conversationId: string | null;
  }>({ userId: "", conversationId: null });
  const expandedConversationId =
    expandedConversation.userId === memberUserId ? expandedConversation.conversationId : null;
  const [viewAuditError, setViewAuditError] = useState("");

  if (loading) {
    return <div className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] px-5 py-10 text-sm text-[var(--muted-foreground)]">正在加载学员 360...</div>;
  }

  if (error) {
    return <div className="rounded-3xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>;
  }

  if (!member) {
    return <div className="rounded-3xl border border-dashed border-[var(--border)]/70 bg-[var(--background)] px-5 py-10 text-sm text-[var(--muted-foreground)]">请选择一个会员查看学员 360。</div>;
  }

  const weakTopics = Object.values(member.chapter_mastery ?? {})
    .slice()
    .sort((a, b) => a.mastery - b.mastery)
    .slice(0, 4);
  const heartbeatJobs = member.heartbeat?.jobs ?? [];
  const overlays = member.bot_overlays ?? [];
  const recentConversations = member.recent_conversations ?? [];

  const toggleConversation = async (conversation: MemberConversationPreview, isExpanded: boolean) => {
    setViewAuditError("");
    if (isExpanded) {
      setExpandedConversation({ userId: memberUserId, conversationId: null });
      return;
    }
    try {
      await onRecordConversationView(conversation);
      setExpandedConversation({ userId: memberUserId, conversationId: conversation.session_id });
    } catch (error) {
      setViewAuditError(error instanceof Error ? error.message : "聊天查看审计失败，已阻止展开全文。");
    }
  };

  return (
    <div className="space-y-5">
      <section className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs tracking-[0.18em] text-[var(--muted-foreground)]">LEARNER 360</p>
            <h2 className="mt-2 text-2xl font-semibold text-[var(--foreground)]">{member.display_name}</h2>
            <p className="mt-2 text-sm text-[var(--muted-foreground)]">
              {member.user_id} · {member.phone}
            </p>
          </div>
          <div className="grid gap-2 text-right text-sm text-[var(--muted-foreground)]">
            <span>状态：{member.status}</span>
            <span>等级：{member.tier.toUpperCase()}</span>
            <span>到期：{formatTime(member.expire_at)}</span>
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <InfoLine label="钱包积分" value={String(member.wallet.balance)} />
          <InfoLine label="学习天数" value={String(member.study_days)} />
          <InfoLine label="待复习" value={String(member.review_due)} />
          <InfoLine label="当前焦点" value={member.focus_topic || "--"} />
        </div>

        <div className="mt-5 flex flex-wrap gap-3">
          <button type="button" onClick={onGrant} disabled={actionLoading} className="rounded-full bg-[var(--primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
            开通 30 天 VIP
          </button>
          <button type="button" onClick={onExtend} disabled={actionLoading} className="rounded-full bg-[var(--secondary)] px-4 py-2 text-sm font-medium text-[var(--secondary-foreground)] disabled:opacity-60">
            续期 90 天
          </button>
          <button type="button" onClick={onRevoke} disabled={actionLoading} className="rounded-full bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 disabled:opacity-60">
            撤销会员
          </button>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
        <div className="space-y-5">
          <div className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5">
            <SectionHeader title="学习画像" extra={`考试日期 ${member.exam_date || "--"}`} />
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <InfoLine label="讲解风格" value={member.explanation_style} />
              <InfoLine label="难度偏好" value={member.difficulty_preference} />
              <InfoLine label="每日目标" value={`${member.daily_target} 题`} />
              <InfoLine label="最近活跃" value={formatTime(member.last_active_at)} />
            </div>
            <div className="mt-4 rounded-2xl bg-[var(--secondary)]/60 px-4 py-4 text-sm leading-6 text-[var(--secondary-foreground)]">
              {member.focus_topic || "暂无焦点主题"}。当前 focus query：{member.focus_query || "未设置"}。
            </div>
            <div className="mt-4 space-y-3">
              {weakTopics.map((topic) => (
                <div key={topic.name} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-[var(--foreground)]">{topic.name}</span>
                    <span className="text-xs text-[var(--muted-foreground)]">{topic.mastery}%</span>
                  </div>
                </div>
              ))}
              {weakTopics.length === 0 ? (
                <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">暂无章节掌握度数据。</div>
              ) : null}
            </div>
          </div>

          <div className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5">
            <SectionHeader title="运营记录" extra={`${member.recent_notes.length} 条备注`} />
            <div className="mt-4 space-y-3">
              <OpsActionComposer onSubmit={onRecordOpsAction} disabled={actionLoading} />
              <NoteComposer onSubmit={onAddNote} disabled={actionLoading} />
              {(member.recent_notes ?? []).slice(0, 5).map((note) => (
                <div key={note.id} className="rounded-2xl bg-[var(--secondary)] px-4 py-3">
                  <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                    <StickyNote size={13} />
                    {note.channel} · {formatTime(note.created_at)}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--secondary-foreground)]">{note.content}</p>
                </div>
              ))}
              {member.recent_notes.length === 0 ? (
                <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">暂无运营备注。</div>
              ) : null}
            </div>
          </div>

          <div className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5">
            <SectionHeader title="最近聊天记录" extra={`${recentConversations.length} 个会话`} />
            {viewAuditError ? <p className="mt-3 rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{viewAuditError}</p> : null}
            <div className="mt-4 space-y-4">
              {recentConversations.map((conversation) => {
                const isExpanded = expandedConversationId === conversation.session_id;
                const preview = conversation.last_message || conversation.messages.at(-1)?.content || "点击查看完整聊天内容";
                return (
                  <div key={conversation.session_id} className="rounded-2xl border border-[var(--border)]/60 bg-white px-4 py-4">
                    <button
                      type="button"
                      aria-expanded={isExpanded}
                      onClick={() => void toggleConversation(conversation, isExpanded)}
                      className="w-full text-left"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-[var(--foreground)]">
                            <MessageSquareMore size={14} className="mr-2 inline-flex" />
                            {conversation.title}
                          </p>
                          <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                            {conversation.capability} · {conversation.message_count} 条消息 · 最近更新 {formatTime(conversation.updated_at)}
                          </p>
                        </div>
                        <span className="max-w-full break-all text-xs text-[var(--muted-foreground)] sm:max-w-[46%]">{conversation.session_id}</span>
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-3 rounded-2xl bg-[var(--secondary)]/45 px-3 py-2 text-xs text-[var(--muted-foreground)]">
                        <span className="line-clamp-1">最近一句：{preview}</span>
                        <span className="inline-flex shrink-0 items-center gap-1 font-medium text-[var(--foreground)]">
                          {isExpanded ? "收起全文" : "查看全文"}
                          <ChevronDown size={14} className={isExpanded ? "rotate-180 transition-transform" : "transition-transform"} />
                        </span>
                      </div>
                    </button>
                    {isExpanded ? (
                      <div className="mt-3 space-y-2">
                        {conversation.messages.map((message) => (
                          <div key={message.id} className="rounded-2xl bg-[var(--secondary)]/70 px-3 py-3 text-sm">
                            <div className="flex items-center justify-between gap-3 text-xs text-[var(--muted-foreground)]">
                              <span>{message.role === "assistant" ? "AI" : "学员"}</span>
                              <span>{formatTime(message.created_at)}</span>
                            </div>
                            <p className="mt-2 whitespace-pre-wrap break-words leading-6 text-[var(--secondary-foreground)]">
                              {message.content}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
              {recentConversations.length === 0 ? (
                <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">
                  当前没有可展示的聊天记录。
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="space-y-5">
          <div className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5">
            <SectionHeader title="Heartbeat Jobs" extra={`${heartbeatJobs.length} 个`} />
            <div className="mt-4 space-y-3">
              {heartbeatJobs.map((job) => (
                <button
                  key={job.job_id}
                  type="button"
                  onClick={() => onToggleHeartbeat(job)}
                  className="w-full rounded-2xl bg-[var(--secondary)] px-4 py-3 text-left"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-[var(--foreground)]">{job.bot_id}</p>
                      <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                        <Clock3 size={12} className="mr-1 inline-flex" />
                        下次运行 {formatTime(job.next_run_at ?? "")}
                      </p>
                    </div>
                    <span className="text-xs text-[var(--muted-foreground)]">{job.status === "active" ? "点击暂停" : "点击恢复"}</span>
                  </div>
                </button>
              ))}
              {heartbeatJobs.length === 0 ? (
                <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">当前没有 heartbeat job。</div>
              ) : null}
            </div>
          </div>

          <div className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5">
            <SectionHeader title="Overlay / TutorBot" extra={`${overlays.length} 个 bot`} />
            <div className="mt-4 space-y-3">
              {overlays.map((overlay) => (
                <button
                  key={overlay.bot_id}
                  type="button"
                  onClick={() => onApplyOverlay(overlay)}
                  className="w-full rounded-2xl bg-[var(--secondary)] px-4 py-3 text-left"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-[var(--foreground)]">
                        <Bot size={14} className="mr-2 inline-flex" />
                        {overlay.bot_id}
                      </p>
                      <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                        promotion candidates {(overlay.promotion_candidates ?? []).length}
                      </p>
                    </div>
                    <span className="text-xs text-[var(--muted-foreground)]">执行 promotion</span>
                  </div>
                </button>
              ))}
              {overlays.length === 0 ? (
                <div className="rounded-2xl bg-[var(--secondary)] px-4 py-4 text-sm text-[var(--muted-foreground)]">当前没有 overlay 数据。</div>
              ) : null}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function OpsActionComposer({
  onSubmit,
  disabled = false,
}: {
  onSubmit: (payload: {
    status: "open" | "in_progress" | "done" | "follow_up";
    result: string;
    action_title?: string;
    next_follow_up_at?: string;
  }) => Promise<void>;
  disabled?: boolean;
}) {
  const [submitError, setSubmitError] = useState("");

  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const formData = new FormData(form);
        const result = String(formData.get("result") || "").trim();
        if (!result) return;
        setSubmitError("");
        try {
          await onSubmit({
            status: String(formData.get("status") || "done") as "open" | "in_progress" | "done" | "follow_up",
            action_title: String(formData.get("action_title") || "").trim(),
            next_follow_up_at: String(formData.get("next_follow_up_at") || "").trim(),
            result,
          });
          form.reset();
        } catch (error) {
          setSubmitError(error instanceof Error ? error.message : "处理结果提交失败，请保留内容后重试。");
        }
      }}
      className="rounded-2xl border border-emerald-200/70 bg-emerald-50/60 p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-emerald-950">处理结果闭环</p>
          <p className="mt-1 text-xs text-emerald-800/80">记录状态和结果后，会同步进入会员备注与经营审计。</p>
        </div>
        <select
          name="status"
          defaultValue="done"
          className="rounded-full border border-emerald-200 bg-white px-3 py-2 text-xs text-emerald-900 outline-none"
        >
          <option value="done">已处理</option>
          <option value="follow_up">需跟进</option>
          <option value="in_progress">处理中</option>
          <option value="open">待处理</option>
        </select>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_150px]">
        <input
          name="action_title"
          placeholder="处理事项，例如：即将到期会员"
          className="rounded-2xl border border-emerald-100 bg-white px-3 py-2 text-sm outline-none"
        />
        <input
          name="next_follow_up_at"
          placeholder="下次跟进"
          className="rounded-2xl border border-emerald-100 bg-white px-3 py-2 text-sm outline-none"
        />
      </div>
      <textarea
        name="result"
        rows={3}
        placeholder="写清楚处理结果，例如：已电话回访，确认本周续费；仍需周五复查学习进度。"
        className="mt-2 w-full resize-none rounded-2xl border border-emerald-100 bg-white px-3 py-2 text-sm outline-none"
      />
      <div className="mt-3 flex justify-end">
        <button type="submit" disabled={disabled} className="rounded-full bg-emerald-800 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
          记录处理结果
        </button>
      </div>
      {submitError ? <p className="mt-2 text-xs text-rose-700">{submitError}</p> : null}
    </form>
  );
}

function NoteComposer({ onSubmit, disabled = false }: { onSubmit: (content: string) => void; disabled?: boolean }) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        const formData = new FormData(event.currentTarget);
        const content = String(formData.get("content") || "").trim();
        if (!content) return;
        onSubmit(content);
        event.currentTarget.reset();
      }}
      className="rounded-2xl border border-[var(--border)]/60 bg-white p-3"
    >
      <textarea
        name="content"
        rows={3}
        placeholder="添加运营备注"
        className="w-full resize-none rounded-2xl bg-transparent px-1 py-1 text-sm outline-none"
      />
      <div className="mt-3 flex justify-end">
        <button type="submit" disabled={disabled} className="rounded-full bg-[var(--foreground)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
          添加备注
        </button>
      </div>
    </form>
  );
}
