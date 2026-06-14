/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { useState } from 'react'
import { Crown } from 'lucide-react'
import {
  BiButton,
  BiMoneyCell,
  BiNotice,
  BiSidePanel,
  BiStatusPill,
  BI_STATUS_PILL_TONE,
  BI_TRUST_TONE,
  type BiStatusTone,
} from '@/components/bi-v2'
import type { MemberDetail } from '@/lib/member-api'
import type { MemberRow } from './data'

type TrustLevel = 'A' | 'B' | 'C' | 'D'

export type Member360DrawerProps = {
  open: boolean
  member: MemberRow | null
  detail?: MemberDetail | null
  loading?: boolean
  error?: string
  onClose: () => void
  onOpenConversation: () => void
  onMarkContacted: (member: MemberRow) => Promise<void> | void
  onJoinFollowUp: (member: MemberRow) => Promise<void> | void
  onAddNote: (member: MemberRow, note: string) => Promise<void> | void
  opsActionWriting?: boolean
  onUpgradeToVip: (member: MemberRow) => Promise<void> | void
  membershipActionWriting?: boolean
}

export function Member360Drawer({
  open,
  member,
  detail,
  loading = false,
  error = '',
  onClose,
  onOpenConversation,
  onMarkContacted,
  onJoinFollowUp,
  onAddNote,
  opsActionWriting = false,
  onUpgradeToVip,
  membershipActionWriting = false,
}: Member360DrawerProps) {
  const [noteDraft, setNoteDraft] = useState('')
  if (!member) return null

  const conversations = detail?.recent_conversations ?? []
  const behavior = detail?.behavior
  const behaviorSummary = behavior?.summary
  const behaviorTrust = normalizeTrust(behaviorSummary?.trust_level ?? member.behavior_trust)
  const tier = (detail?.tier ?? member.tier).toUpperCase()
  const status = detail?.status ?? member.status
  const displayName = detail?.display_name || member.region || '未命名学员'
  const risk = member.risk
  const cohort = behaviorSummary?.cohort ?? member.behavior_cohort ?? ''
  const nextAction = behaviorSummary?.next_action ?? member.behavior_next_action ?? behaviorNextAction(cohort)
  const learningReportCount = behaviorSummary?.learning_report_open_count_7d ?? member.behavior_learning_report_7d ?? 0
  const historyCount = behaviorSummary?.history_open_count_7d ?? member.behavior_history_7d ?? 0
  const actionCount = behaviorSummary?.action_start_count_7d ?? 0
  const eventCount = behaviorSummary?.event_count_7d ?? member.behavior_event_count_7d ?? 0
  const notes = detail?.recent_notes ?? []
  const ledger = detail?.recent_ledger ?? []
  const canUpgradeToVip = tier !== 'VIP' && tier !== 'SVIP'

  async function submitNote() {
    if (!member) return
    const note = noteDraft.trim()
    if (!note) return
    await onAddNote(member, note)
    setNoteDraft('')
  }

  return (
    <BiSidePanel
      open={open}
      onClose={onClose}
      title={`学员 360 · ${member.phone_masked}`}
      subtitle={`${displayName} · ${member.user_id}`}
      width="lg"
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          {canUpgradeToVip ? (
            <BiButton
              disabled={membershipActionWriting}
              onClick={() => void onUpgradeToVip(member)}
              variant="secondary"
              size="sm"
              aria-label="将当前会员升级为 VIP"
              title="运营授予 VIP；付费补录请使用商品账务"
            >
              <Crown className="h-3.5 w-3.5" aria-hidden />
              升VIP
            </BiButton>
          ) : null}
          <BiButton
            disabled={opsActionWriting}
            onClick={() => void onMarkContacted(member)}
            variant="secondary"
            size="sm"
            aria-label="标记已联系"
            title="写入 ops_action_result audit"
          >
            标记已联系
          </BiButton>
          <BiButton
            disabled={opsActionWriting}
            onClick={() => void onJoinFollowUp(member)}
            variant="secondary"
            size="sm"
            aria-label="加入跟进队列"
            title="写入 ops_action_result audit"
          >
            加入跟进
          </BiButton>
          <BiButton
            onClick={onOpenConversation}
            variant="primary"
            size="sm"
            aria-label="查看会员对话回顾"
          >
            对话回顾
          </BiButton>
        </div>
      }
    >
      <div className="space-y-4">
        {loading ? <BiNotice tone="sky">正在加载真实学员 360...</BiNotice> : null}
        {error ? <BiNotice tone="rose">学员 360 加载失败：{error}</BiNotice> : null}

        <section
          data-testid="bi-member-360-summary"
          className="rounded-2xl border border-cyan-300/18 bg-cyan-300/[0.065] p-4 shadow-lg shadow-black/10"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-lg font-black text-slate-50">{member.phone_masked}</h3>
                <BiStatusPill tone={statusTone(status)} label={statusLabel(status)} size="md" />
                <BiStatusPill tone={tierTone(tier)} label={tier} size="md" />
              </div>
              <div className="mt-1 font-mono text-[11px] text-cyan-100/70">{member.user_id}</div>
            </div>
            <div className="rounded-2xl border border-amber-200/25 bg-amber-200/[0.08] px-3 py-2 text-right">
              <div className="text-[11px] font-bold text-amber-100/75">建议动作</div>
              <div className="mt-0.5 max-w-[220px] text-sm font-black text-amber-50">{nextAction}</div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3">
            <DecisionTile label="行为队列" value={behaviorCohortLabel(cohort)} tone={BI_TRUST_TONE[behaviorTrust]} />
            <DecisionTile label="风险" value={`${riskLabel(risk)} · ${risk.toFixed(2)}`} tone={BI_STATUS_PILL_TONE[riskTone(risk)]} />
            <DecisionTile label="行为可信度" value={`${behaviorTrust} 级`} tone={BI_TRUST_TONE[behaviorTrust]} />
          </div>

          {member.behavior_reasons?.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {member.behavior_reasons.slice(0, 3).map(reason => (
                <span
                  key={reason}
                  className="rounded-full border border-white/10 bg-white/[0.055] px-2 py-1 text-[11px] text-slate-300"
                >
                  {reason}
                </span>
              ))}
            </div>
          ) : null}
        </section>

        <section className="grid grid-cols-2 gap-2 lg:grid-cols-4" aria-label="会员关键指标">
          <MetricTile
            label="余额"
            value={<BiMoneyCell amount={detail?.wallet?.balance ?? member.balance_points} currency="POINT" align="left" />}
          />
          <MetricTile label="学习天数" value={String(detail?.study_days ?? '—')} />
          <MetricTile label="待复习" value={String(detail?.review_due ?? member.notes_count ?? 0)} />
          <MetricTile label="最近活跃" value={formatDateTime(detail?.last_active_at) || member.last_active} />
        </section>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
          <Section title="行为证据" trust={behaviorTrust}>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <EvidenceStat label="行为样本" value={eventCount} />
              <EvidenceStat label="学情" value={learningReportCount} />
              <EvidenceStat label="历史" value={historyCount} />
              <EvidenceStat label="行动" value={actionCount} />
            </div>

            <div data-testid="bi-member-learning-report-breakdown" className="space-y-2">
              <Subhead title="学情模块" />
              {behavior?.learning_report_sections?.length ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  {behavior.learning_report_sections.slice(0, 8).map(section => (
                    <KV
                      key={section.section}
                      label={section.section || 'unknown'}
                      value={`${section.view_count} 次`}
                    />
                  ))}
                </div>
              ) : (
                <EmptyBlock>暂无学情模块访问记录。</EmptyBlock>
              )}
            </div>

            <div data-testid="bi-member-behavior-timeline" className="space-y-2">
              <Subhead title="最近行为" />
              {behavior?.timeline?.length ? (
                <div className="space-y-2">
                  {behavior.timeline.slice(0, 8).map(event => (
                    <div
                      key={event.event_id}
                      className="rounded-2xl border border-white/10 bg-white/[0.04] p-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-bold text-slate-100">{event.event_name}</span>
                        <span className="text-[11px] text-slate-500">
                          {formatBehaviorTime(event.occurred_at_ms)}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] text-slate-400">
                        {event.surface || 'unknown'} / {event.module || 'unknown'} / {event.section || 'unknown'} / {event.action || 'unknown'}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-slate-500">
                        {event.object_type || event.object_id ? (
                          <span>对象 {event.object_type || 'unknown'}:{event.object_id || 'unknown'}</span>
                        ) : null}
                        {event.duration_ms ? <span>停留 {event.duration_ms}ms</span> : null}
                        {event.result ? <span>结果 {event.result}</span> : null}
                        {event.error_code ? <span>错误 {event.error_code}</span> : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyBlock>暂无行为事件。</EmptyBlock>
              )}
            </div>
          </Section>

          <div className="space-y-4">
            <Section title="最近对话" trust="A">
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-cyan-300/15 bg-cyan-300/[0.06] p-3">
                <div>
                  <div className="text-2xl font-black tabular-nums text-slate-50">{conversations.length}</div>
                  <div className="text-[11px] text-slate-400">最近会话</div>
                </div>
                <BiButton onClick={onOpenConversation} variant="secondary" size="xs" aria-label="打开会员对话工作台">
                  打开工作台
                </BiButton>
              </div>
              {conversations.length === 0 ? (
                <EmptyBlock>当前 360 快照没有最近会话。</EmptyBlock>
              ) : (
                <ul className="space-y-2">
                  {conversations.slice(0, 3).map(session => (
                    <li key={session.session_id} className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="min-w-0 flex-1 truncate font-bold text-slate-100">
                          {session.title || session.session_id}
                        </div>
                        {session.capability ? <BiStatusPill tone="slate" label={session.capability} /> : null}
                      </div>
                      <div className="mt-1 text-[11px] text-slate-400">
                        {formatDateTime(session.updated_at || session.created_at)} · {session.message_count} 条
                      </div>
                      {session.last_message ? (
                        <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-300">{session.last_message}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <section className="rounded-2xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
              <div className="text-sm font-black text-slate-100">运营备注</div>
              <textarea
                value={noteDraft}
                onChange={event => setNoteDraft(event.target.value)}
                rows={4}
                maxLength={500}
                className="mt-2 w-full resize-none rounded-2xl border border-white/10 bg-white/[0.06] p-3 text-xs leading-5 text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
                placeholder="输入本次联系结果、续费意向或投诉摘要"
                aria-label="运营备注内容"
              />
              <div className="mt-2 flex justify-end">
                <BiButton
                  disabled={opsActionWriting || noteDraft.trim().length === 0}
                  onClick={() => void submitNote()}
                  variant="secondary"
                  size="sm"
                  aria-label="添加运营备注"
                  title="写入 ops_action_result audit"
                >
                  添加备注
                </BiButton>
              </div>
            </section>
          </div>
        </div>

        <section className="grid gap-4 lg:grid-cols-2">
          <Section title="账户与学习" trust="A">
            <div className="grid gap-2 sm:grid-cols-2">
              <KV label="昵称" value={displayName} />
              <KV label="手机号" value={member.phone_masked} />
              <KV label="Tier" value={tier} />
              <KV label="状态" value={statusLabel(status)} />
              <KV label="到期" value={formatDate(detail?.expire_at) || member.expires_at} />
              <KV label="首充" value={formatDate(detail?.created_at) || member.paid_at_first || '未付费'} />
              <KV label="今日目标" value={`${detail?.daily_target ?? '—'}`} />
              <KV label="考试日期" value={formatDate(detail?.exam_date) || '—'} />
            </div>
            {detail?.learner_state?.summary ? (
              <p className="rounded-2xl border border-white/10 bg-white/[0.035] p-3 text-xs leading-5 text-slate-300">
                {detail.learner_state.summary}
              </p>
            ) : null}
          </Section>

          <Section title="钱包与运营记录" trust="A">
            <div className="space-y-3">
              <div className="space-y-1.5">
                <Subhead title="最近流水" />
                {ledger.length ? (
                  ledger.slice(0, 3).map(entry => (
                    <KV
                      key={entry.id}
                      label={entry.reason || entry.id}
                      value={formatDelta(entry.delta)}
                    />
                  ))
                ) : (
                  <EmptyBlock>暂无近期积分流水。</EmptyBlock>
                )}
              </div>
              <div className="space-y-1.5">
                <Subhead title="最近备注" />
                {notes.length ? (
                  notes.slice(0, 3).map(note => (
                    <p key={note.id} className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 text-xs leading-5 text-slate-300">
                      {note.content}
                    </p>
                  ))
                ) : (
                  <EmptyBlock>暂无运营备注。</EmptyBlock>
                )}
              </div>
            </div>
          </Section>
        </section>

        <BiNotice tone="amber">
          危险动作（撤销会员 / 补点数 / 异常处理）当前禁用：等 etag / version / undo_token
          后端就绪后启用。
        </BiNotice>
      </div>
    </BiSidePanel>
  )
}

function normalizeTrust(value?: string): TrustLevel {
  if (value === 'A' || value === 'B' || value === 'C' || value === 'D') return value
  return 'C'
}

function formatBehaviorTime(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(value)
}

function formatDateTime(value?: string): string {
  if (!value) return ''
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

function formatDate(value?: string): string {
  if (!value) return ''
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(parsed)
}

function formatDelta(value: number): string {
  return `${value > 0 ? '+' : ''}${value}`
}

function statusLabel(status: string): string {
  if (status === 'active') return '活跃'
  if (status === 'expiring' || status === 'expiring_soon') return '将到期'
  if (status === 'expired') return '已到期'
  if (status === 'paused' || status === 'revoked') return '暂停'
  return status || '未知'
}

function statusTone(status: string): BiStatusTone {
  if (status === 'active') return 'emerald'
  if (status === 'expiring' || status === 'expiring_soon') return 'amber'
  if (status === 'expired') return 'rose'
  return 'slate'
}

function tierTone(tier: string): BiStatusTone {
  if (tier === 'SVIP') return 'amber'
  if (tier === 'VIP') return 'sky'
  return 'slate'
}

function riskLabel(value: number): string {
  if (value >= 0.7) return '高'
  if (value >= 0.4) return '中'
  return '低'
}

function riskTone(value: number): BiStatusTone {
  if (value >= 0.7) return 'rose'
  if (value >= 0.4) return 'amber'
  return 'emerald'
}

function behaviorCohortLabel(cohort?: string): string {
  if (cohort === 'report_high_no_action') return '学情高频无行动'
  if (cohort === 'history_high_no_review') return '历史高频无复盘'
  if (cohort === 'chat_only') return '只对话不看学情'
  if (cohort === 'training_no_retest') return '训练未复测'
  return cohort || '正常观察'
}

function behaviorNextAction(cohort?: string): string {
  if (cohort === 'report_high_no_action') return '安排训练回访'
  if (cohort === 'history_high_no_review') return '发送错题复盘'
  if (cohort === 'chat_only') return '引导查看学情'
  if (cohort === 'training_no_retest') return '提醒复测'
  return '观察'
}

function Section({
  title,
  trust,
  children,
}: {
  title: string
  trust: TrustLevel
  children: React.ReactNode
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
      <header className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-black text-slate-100">{title}</h3>
        <BiStatusPill tone={BI_TRUST_TONE[trust]} label={`${trust} 级`} />
      </header>
      <div className="space-y-3 text-xs">{children}</div>
    </section>
  )
}

function DecisionTile({
  label,
  value,
  tone,
}: {
  label: string
  value: React.ReactNode
  tone: string
}) {
  return (
    <div className={`rounded-2xl border px-3 py-2 ${tone}`}>
      <div className="text-[11px] font-bold opacity-75">{label}</div>
      <div className="mt-1 text-sm font-black">{value}</div>
    </div>
  )
}

function MetricTile({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-3 shadow-lg shadow-black/10">
      <div className="text-[11px] font-bold text-slate-400">{label}</div>
      <div className="mt-1 min-h-7 text-xl font-black tabular-nums text-slate-50">{value}</div>
    </div>
  )
}

function EvidenceStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-cyan-300/15 bg-cyan-300/[0.055] p-3">
      <div className="text-[11px] font-bold text-cyan-100/75">{label}</div>
      <div className="mt-1 text-xl font-black tabular-nums text-slate-50">{value}</div>
    </div>
  )
}

function Subhead({ title }: { title: string }) {
  return <div className="text-[11px] font-black uppercase text-slate-500">{title}</div>
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2">
      <span className="shrink-0 text-slate-400">{label}</span>
      <span className="min-w-0 break-words text-right font-bold text-slate-100">{value}</span>
    </div>
  )
}

function EmptyBlock({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.035] p-3 text-xs leading-5 text-slate-400">
      {children}
    </div>
  )
}
