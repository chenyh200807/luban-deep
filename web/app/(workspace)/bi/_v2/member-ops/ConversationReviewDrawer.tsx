/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { useEffect, useMemo, useState } from 'react'
import { BiSidePanel } from '@/components/bi-v2'
import {
  listMemberConversations,
  type MemberConversationMessagePreview,
  type MemberConversationPreview,
  type MemberConversationViewAudit,
  type MemberDetail,
} from '@/lib/member-api'
import { useAuditedAction } from '../useAuditedAction'
import type { MemberRow } from './data'

export type ConversationReviewDrawerProps = {
  open: boolean
  member: MemberRow | null
  detail?: MemberDetail | null
  onClose: () => void
}

// Plan §6 列了 6 个原因；此处实装全部，"其他" 必须补充 ≥ 4 字符的说明。
const VIEW_REASONS = [
  { key: 'complaint', label: '客服投诉' },
  { key: 'ops', label: '运营跟进' },
  { key: 'teaching', label: '教研复核' },
  { key: 'engineering', label: '工程排障' },
  { key: 'finance', label: '财务核对' },
  { key: 'other', label: '其他（需补充说明）' },
]

// Round 4 S4 (M-B): mock session list dev-only. Production build returns []
// and the drawer shows "session 列表待接入" state instead of fake conversation
// titles. Real list comes from session_store in Batch 5.
const MOCK_SESSIONS =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          id: 's_001',
          title: '高中物理 · 牛顿第二定律',
          summary: '学员 3 次追问，最终掌握。',
          at: '今天 11:02',
        },
        {
          id: 's_002',
          title: '化学 · 元素周期表',
          summary: '学员卡在记忆环节，AI 给出口诀。',
          at: '昨天 22:30',
        },
        {
          id: 's_003',
          title: '英语 · 完形填空',
          summary: '学员 5 次错答，AI 多步引导。',
          at: '昨天 19:14',
        },
      ]

export function ConversationReviewDrawer({
  open,
  member,
  detail,
  onClose,
}: ConversationReviewDrawerProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [reason, setReason] = useState<string>('')
  const [reasonNote, setReasonNote] = useState('')
  const [liveSessions, setLiveSessions] = useState<MemberConversationPreview[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [sessionError, setSessionError] = useState('')
  const [revealedMessages, setRevealedMessages] = useState<
    Record<string, MemberConversationMessagePreview[]>
  >({})
  const audit = useAuditedAction({ actionType: 'member.conversation.view_full' })
  const auditState = audit.state.phase
  const auditError = audit.state.phase === 'denied' ? (audit.state.result.error ?? '') : ''

  const detailSessions = useMemo(() => detail?.recent_conversations ?? [], [detail?.recent_conversations])

  useEffect(() => {
    if (!open || !member) return
    if (detailSessions.length > 0) {
      setLiveSessions([])
      setSessionError('')
      setLoadingSessions(false)
      return
    }
    let cancelled = false
    async function load() {
      if (!member) return
      try {
        setLoadingSessions(true)
        setSessionError('')
        setLiveSessions([])
        const result = await listMemberConversations(member.user_id, {
          limit: 20,
          message_limit: 12,
        })
        if (!cancelled) setLiveSessions(result.items ?? [])
      } catch (err) {
        if (!cancelled) {
          setLiveSessions([])
          setSessionError(err instanceof Error ? err.message : '对话列表加载失败')
        }
      } finally {
        if (!cancelled) setLoadingSessions(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [detailSessions.length, member, open])

  if (!member) return null
  const sessions = detailSessions.length > 0 ? detailSessions : liveSessions.length > 0 ? liveSessions : MOCK_SESSIONS

  async function tryReveal(sessionId: string) {
    if (!member) return
    if (!reason) return
    if (reason === 'other' && reasonNote.trim().length < 4) return
    const fullReason = reason === 'other' ? `other:${reasonNote.trim()}` : reason
    // useAuditedAction injects actor (via withAdminAuthorization) and
    // X-Idempotency-Key automatically; ConversationReviewDrawer never builds
    // these by hand. Reason is passed in body for forward-compat with backend
    // (current backend only ingests it via query for access logs).
    // Round 4 S2: endpoint is referenced by its registered key, not a
    // hand-built URL. Method + path template are resolved from the generated
    // registry — drift between frontend and backend is impossible.
    const result = await audit.execute({
      key: 'member.conversation.view_full',
      params: { user_id: member.user_id, session_id: sessionId },
      query: { reason: fullReason },
      body: { reason: fullReason },
    })
    if (result.ok) {
      setRevealedMessages(prev => ({
        ...prev,
        [sessionId]: getAuditedMessages(result.data),
      }))
      setExpandedId(sessionId)
    }
    // 失败时 audit.state 自动转 denied，UI 通过 auditError 展示，expandedId 保持不变 = 全文不展开
  }

  return (
    <BiSidePanel
      open={open}
      onClose={onClose}
      title={`对话回顾 · ${member.phone_masked}`}
      subtitle={`session 摘要默认展示，全文需选原因写入 audit 后展开`}
      width="lg"
    >
      <div className="space-y-3">
        {/* Round 3 C: RequireBiAdmin 保证抽屉只在已登录 admin 下渲染，
            "未登录" 状态已在 BiV2Surface 层被拦截，此处不再重复检查。 */}
        {auditState === 'denied' && auditError ? (
          <section
            className="rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800"
            role="alert"
          >
            <div className="font-medium">audit 未写入服务端，已阻止全文展开</div>
            <p className="mt-1">原因：{auditError}</p>
          </section>
        ) : null}
        {auditState === 'writing' ? (
          <section
            className="rounded border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800"
            aria-live="polite"
          >
            正在写入 audit…
          </section>
        ) : null}
        <section className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          <div className="font-medium">查看全文必须选择原因（计划 §3.5 / §Batch 5）</div>
          <fieldset className="mt-2 space-y-1" aria-label="查看原因">
            {VIEW_REASONS.map(r => (
              <label key={r.key} className="flex items-center gap-2 text-amber-900">
                <input
                  type="radio"
                  name="reason"
                  value={r.key}
                  checked={reason === r.key}
                  onChange={() => setReason(r.key)}
                  aria-label={r.label}
                />
                {r.label}
              </label>
            ))}
            {reason === 'other' ? (
              <textarea
                value={reasonNote}
                onChange={e => setReasonNote(e.target.value)}
                rows={2}
                className="w-full rounded border border-amber-300 bg-white p-2 text-amber-900 outline-none focus:border-amber-500"
                placeholder="补充原因 (≥ 4 字)，将写入 audit"
                aria-label="其他原因补充说明"
              />
            ) : null}
          </fieldset>
        </section>

        {loadingSessions ? (
          <div className="rounded border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800">
            正在读取会员对话列表…
          </div>
        ) : null}
        {sessionError ? (
          <div className="rounded border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
            对话列表加载失败：{sessionError}
          </div>
        ) : null}

        {/* Round 5 B3: production MOCK_SESSIONS is []; render an explicit
            empty state so admins don't see a silently blank list under the
            reason form (frontend reviewer finding). */}
        {!loadingSessions && sessions.length === 0 ? (
          <div className="rounded border border-dashed border-slate-300 bg-slate-50 p-4 text-center text-xs text-slate-500">
            暂无可展示对话。已读取{' '}
            <code className="font-mono">/api/v1/member/{member.user_id}/conversations</code>，当前会员没有
            session_store 对话记录或会话无可展示消息。
          </div>
        ) : null}

        <ul className="space-y-2">
          {sessions.map(s => {
            const session = normalizeSession(s)
            const expanded = expandedId === session.id
            const messages = revealedMessages[session.id] ?? []
            return (
              <li key={session.id} className="rounded border border-slate-200 bg-white">
                <div className="flex items-start justify-between gap-3 p-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-slate-800">{session.title}</div>
                    <div className="mt-0.5 text-[11px] text-slate-500">{session.at}</div>
                    <p className="mt-1 text-xs text-slate-700">摘要：{session.summary}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      void tryReveal(session.id)
                    }}
                    disabled={
                      !reason ||
                      (reason === 'other' && reasonNote.trim().length < 4) ||
                      auditState === 'writing'
                    }
                    className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    aria-label={`查看 ${session.title} 全文，将写入 audit`}
                  >
                    {expanded ? '已展开' : auditState === 'writing' ? '写入中…' : '查看全文'}
                  </button>
                </div>
                {expanded ? (
                  <div className="border-t border-slate-200 bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-700">
                    [全文按需加载占位 · authority: session store · 仅限本次审计可见]
                    <br />
                    {messages.length > 0 ? (
                      <span className="mt-2 block space-y-1">
                        {messages.slice(0, 6).map(message => (
                          <span key={message.id} className="block rounded bg-white px-2 py-1">
                            <span className="font-semibold">{message.role}: </span>
                            {message.content}
                          </span>
                        ))}
                      </span>
                    ) : null}
                    服务端 audit 已写入（reason=
                    <code className="font-mono">
                      {reason === 'other' ? `other:${reasonNote.slice(0, 20)}` : reason}
                    </code>
                    , session=<code className="font-mono">{session.id}</code>
                    {audit.state.phase === 'ok' ? (
                      <>
                        , idempotency_key=
                        <code className="font-mono text-[10px]">
                          {audit.state.result.idempotencyKey.slice(0, 8)}
                        </code>
                        {audit.state.result.auditId ? (
                          <>
                            , audit_id=
                            <code className="font-mono text-[10px]">
                              {audit.state.result.auditId}
                            </code>
                          </>
                        ) : null}
                      </>
                    ) : null}
                    ）。actor 由服务端 audit_log 记录，不在前端展示。
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>
      </div>
    </BiSidePanel>
  )
}

function normalizeSession(
  session:
    | MemberConversationPreview
    | { id: string; title: string; summary: string; at: string }
) {
  if ('session_id' in session) {
    return {
      id: session.session_id,
      title: session.title || session.session_id,
      summary: session.last_message || `${session.message_count} 条消息`,
      at: session.updated_at || session.created_at || '—',
    }
  }
  return {
    id: session.id,
    title: session.title,
    summary: session.summary,
    at: session.at,
  }
}

function getAuditedMessages(data: unknown): MemberConversationMessagePreview[] {
  if (!data || typeof data !== 'object') return []
  const messages = (data as MemberConversationViewAudit).messages
  return Array.isArray(messages) ? messages : []
}
