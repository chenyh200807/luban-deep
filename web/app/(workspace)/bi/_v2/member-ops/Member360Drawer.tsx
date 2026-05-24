/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { useState } from 'react'
import { BiSidePanel, BiMoneyCell, BiStatusPill, BI_TRUST_TONE } from '@/components/bi-v2'
import type { MemberDetail } from '@/lib/member-api'
import type { MemberRow } from './data'

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
}: Member360DrawerProps) {
  const [noteDraft, setNoteDraft] = useState('')
  if (!member) return null
  const conversations = detail?.recent_conversations ?? []
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
      subtitle={`user_id: ${member.user_id} · ${member.tier.toUpperCase()} · 风险 ${member.risk.toFixed(2)}`}
      width="lg"
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            disabled={opsActionWriting}
            onClick={() => void onMarkContacted(member)}
            className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="标记已联系"
            title="写入 ops_action_result audit"
          >
            标记已联系
          </button>
          <button
            type="button"
            disabled={opsActionWriting}
            onClick={() => void onJoinFollowUp(member)}
            className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="加入跟进队列"
            title="写入 ops_action_result audit"
          >
            加入跟进
          </button>
          <button
            type="button"
            onClick={onOpenConversation}
            className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white hover:bg-slate-800"
            aria-label="查看会员对话回顾"
          >
            查看对话回顾
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {loading ? (
          <div className="rounded border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800">
            正在加载真实学员 360…
          </div>
        ) : null}
        {error ? (
          <div className="rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
            学员 360 加载失败：{error}
          </div>
        ) : null}
        <section className="rounded border border-slate-200 bg-white p-3">
          <div className="text-xs font-semibold text-slate-900">运营备注</div>
          <textarea
            value={noteDraft}
            onChange={event => setNoteDraft(event.target.value)}
            rows={3}
            maxLength={500}
            className="mt-2 w-full resize-none rounded border border-slate-200 p-2 text-xs text-slate-800 outline-none focus:border-slate-400"
            placeholder="输入本次联系结果、续费意向或投诉摘要"
            aria-label="运营备注内容"
          />
          <div className="mt-2 flex justify-end">
            <button
              type="button"
              disabled={opsActionWriting || noteDraft.trim().length === 0}
              onClick={() => void submitNote()}
              className="rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="添加运营备注"
              title="写入 ops_action_result audit"
            >
              添加备注
            </button>
          </div>
        </section>
        <Section title="账户摘要" trust="A">
          <KV label="user_id" value={<code className="font-mono">{detail?.user_id ?? member.user_id}</code>} />
          <KV label="昵称" value={detail?.display_name ?? '—'} />
          <KV label="手机号" value={member.phone_masked} />
          <KV label="Tier" value={(detail?.tier ?? member.tier).toUpperCase()} />
          <KV label="状态" value={detail?.status ?? member.status} />
          <KV label="到期" value={detail?.expire_at ?? member.expires_at} />
          <KV label="首充" value={member.paid_at_first ?? '未付费'} />
          <KV label="最近活跃" value={detail?.last_active_at ?? member.last_active} />
        </Section>

        <Section title="钱包" trust="A">
          <KV
            label="余额"
            value={
              <BiMoneyCell
                amount={detail?.wallet?.balance ?? member.balance_points}
                currency="POINT"
                align="left"
              />
            }
          />
          {detail?.recent_ledger?.slice(0, 3).map(entry => (
            <KV
              key={entry.id}
              label={entry.reason || entry.id}
              value={`${entry.delta > 0 ? '+' : ''}${entry.delta}`}
            />
          ))}
          <p className="text-[11px] text-slate-500">
            authority: WalletService.list_wallet_ledger · 流水入口由 Batch 4 商品账务接入。
          </p>
        </Section>

        <Section title="学习画像" trust="A">
          <KV label="学习天数" value={`${detail?.study_days ?? '—'}`} />
          <KV label="待复习" value={`${detail?.review_due ?? member.notes_count ?? 0}`} />
          <KV label="今日目标" value={`${detail?.daily_target ?? '—'}`} />
          <p className="text-xs text-slate-600">
            {detail?.learner_state?.summary ||
              'learner_state read model 暂无摘要；打开详情时仍保留账户 / 钱包 / 会话事实。'}
          </p>
        </Section>

        <Section title="最近对话" trust="A">
          {conversations.length === 0 ? (
            <p className="text-xs text-slate-500">暂无 recent_conversations。</p>
          ) : (
            <ul className="space-y-2">
              {conversations.slice(0, 3).map(session => (
                <li key={session.session_id} className="rounded border border-slate-100 bg-slate-50 p-2">
                  <div className="font-medium text-slate-800">{session.title || session.session_id}</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    {session.updated_at || session.created_at} · {session.message_count} 条
                  </div>
                  {session.last_message ? (
                    <p className="mt-1 line-clamp-2 text-xs text-slate-600">{session.last_message}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="运营记录" trust="A">
          <KV label="备注数" value={`${detail?.recent_notes?.length ?? member.notes_count ?? 0}`} />
          <KV label="反馈数" value={`${member.feedback_count ?? 0}`} />
          {detail?.recent_notes?.slice(0, 2).map(note => (
            <p key={note.id} className="rounded bg-slate-50 p-2 text-xs text-slate-600">
              {note.content}
            </p>
          ))}
          <p className="text-[11px] text-slate-500">
            运营动作写入{' '}
            <code className="font-mono">/api/v1/member/{member.user_id}/ops-actions</code>，每条均带
            audit。
          </p>
        </Section>

        <div className="rounded border border-amber-200 bg-amber-50 p-3 text-[11px] text-amber-800">
          危险动作（撤销会员 / 补点数 / 异常处理）当前禁用：等 etag / version / undo_token
          后端就绪后启用（计划 §3.5）。
        </div>
      </div>
    </BiSidePanel>
  )
}

function Section({
  title,
  trust,
  children,
}: {
  title: string
  trust: 'A' | 'B' | 'C' | 'D'
  children: React.ReactNode
}) {
  return (
    <section className="rounded border border-slate-200 bg-white p-3">
      <header className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <BiStatusPill tone={BI_TRUST_TONE[trust]} label={`${trust} 级`} />
      </header>
      <div className="space-y-1.5 text-xs">{children}</div>
    </section>
  )
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-800">{value}</span>
    </div>
  )
}
