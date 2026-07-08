/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { useEffect, useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import { BiButton, BiNotice, BiSidePanel } from '@/components/bi-v2'
import {
  listMemberConversations,
  type MemberConversationMessagePreview,
  type MemberConversationPreview,
  type MemberConversationViewAudit,
  type MemberDetail,
} from '@/lib/member-api'
import { useAuditedAction } from '../useAuditedAction'
import type { MemberRow } from './data'

const SimpleMarkdownRenderer = dynamic(() => import('@/components/common/SimpleMarkdownRenderer'), {
  ssr: false,
  loading: () => <span className="text-xs text-slate-500">正在渲染排版…</span>,
})

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

function normalizeConversationMarkdown(value: string): string {
  return String(value || '')
    .replace(/\r\n/g, '\n')
    .replace(/\s+---\s+/g, '\n\n---\n\n')
    .replace(/\s+(#{1,6}\s+)/g, '\n\n$1')
    .replace(/\s+(\*\*题目[一二三四五六七八九十\d]+[：:]\*\*)/g, '\n\n$1')
    .replace(/\s+(\*\*你的错因[：:]\*\*)/g, '\n\n$1')
    .replace(/\s+(\*\*踩分点[：:]\*\*)/g, '\n\n$1')
    .replace(/\s+(\*\*关键记忆点[：:]\*\*)/g, '\n\n$1')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

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
  const [query, setQuery] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [capabilityFilter, setCapabilityFilter] = useState('')
  const [sort, setSort] = useState<'updated_at' | 'created_at' | 'message_count' | 'title' | 'source' | 'capability'>('updated_at')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [reloadNonce, setReloadNonce] = useState(0)
  const [liveSessions, setLiveSessions] = useState<MemberConversationPreview[]>([])
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [loadedSessions, setLoadedSessions] = useState(false)
  const [sessionError, setSessionError] = useState('')
  const [revealedMessages, setRevealedMessages] = useState<
    Record<string, MemberConversationMessagePreview[]>
  >({})
  const audit = useAuditedAction({ actionType: 'member.conversation.view_full' })
  const auditState = audit.state.phase
  const auditError = audit.state.phase === 'denied' ? (audit.state.result.error ?? '') : ''

  const detailSessions = useMemo(() => detail?.recent_conversations ?? [], [detail?.recent_conversations])
  const memberId = member?.user_id ?? ''
  const trimmedQuery = query.trim()

  useEffect(() => {
    setExpandedId(null)
    setLiveSessions([])
    setLoadedSessions(false)
    setSessionError('')
    setRevealedMessages({})
  }, [memberId])

  useEffect(() => {
    if (!open || !memberId) return
    let cancelled = false
    async function load() {
      try {
        setLoadingSessions(true)
        setSessionError('')
        const result = await listMemberConversations(memberId, {
          limit: 20,
          message_limit: 12,
          q: trimmedQuery || undefined,
          source: sourceFilter || undefined,
          capability: capabilityFilter || undefined,
          sort,
          order,
        })
        if (!cancelled) {
          setLiveSessions(result.items ?? [])
          setLoadedSessions(true)
        }
      } catch (err) {
        if (!cancelled) {
          setLiveSessions([])
          setSessionError(err instanceof Error ? err.message : '对话列表加载失败')
          setLoadedSessions(true)
        }
      } finally {
        if (!cancelled) setLoadingSessions(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [capabilityFilter, memberId, open, order, reloadNonce, sort, sourceFilter, trimmedQuery])

  if (!member) return null
  const sessions =
    loadedSessions || loadingSessions
      ? liveSessions.length > 0
        ? liveSessions
        : loadedSessions
          ? []
          : detailSessions
      : detailSessions.length > 0
        ? detailSessions
        : MOCK_SESSIONS
  const sourceOptions = uniqueOptions([...detailSessions, ...liveSessions].map(session => session.source))
  const capabilityOptions = uniqueOptions([...detailSessions, ...liveSessions].map(session => session.capability))
  const normalizedSessions = sessions.map(normalizeSession)
  const totalMessages = normalizedSessions.reduce((sum, session) => sum + session.count, 0)
  const latestSession = normalizedSessions[0]
  const reasonBlockedMessage = !reason
    ? '选择原因后，“查看全文”会解锁并写入 audit。'
    : reason === 'other' && reasonNote.trim().length < 4
      ? '请补充至少 4 字的其他原因后再查看全文。'
      : ''

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
      const auditedMessages = getAuditedMessages(result.data)
      setRevealedMessages(prev => ({
        ...prev,
        [sessionId]: auditedMessages.length > 0 ? auditedMessages : getPreviewMessages(sessions, sessionId),
      }))
      setExpandedId(sessionId)
    }
    // 失败时 audit.state 自动转 denied，UI 通过 auditError 展示，expandedId 保持不变 = 全文不展开
  }

  function clearFilters() {
    setQuery('')
    setSourceFilter('')
    setCapabilityFilter('')
    setSort('updated_at')
    setOrder('desc')
  }

  return (
    <BiSidePanel
      open={open}
      onClose={onClose}
      title={`会员对话工作台 · ${member.phone_masked}`}
      subtitle={`摘要列表可筛选排序，全文必须选择原因并写入 audit 后展开`}
      width="lg"
    >
      <div className="space-y-3">
        {/* Round 3 C: RequireBiAdmin 保证抽屉只在已登录 admin 下渲染，
            "未登录" 状态已在 BiV2Surface 层被拦截，此处不再重复检查。 */}
        {auditState === 'denied' && auditError ? (
          <BiNotice tone="rose" role="alert">
            <div className="font-medium">audit 未写入服务端，已阻止全文展开</div>
            <p className="mt-1">原因：{auditError}</p>
          </BiNotice>
        ) : null}
        {auditState === 'writing' ? (
          <BiNotice tone="sky" aria-live="polite">
            正在写入 audit…
          </BiNotice>
        ) : null}

        <section className="overflow-hidden rounded-[28px] border border-cyan-300/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_42%),rgba(15,23,42,0.72)] shadow-2xl shadow-black/20">
          <div className="border-b border-white/10 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-[11px] font-black uppercase tracking-[0.24em] text-cyan-200/80">
                  Conversation Intelligence
                </div>
                <h3 className="mt-1 text-lg font-black text-slate-50">会话线索池</h3>
                <p className="mt-1 max-w-xl text-xs leading-5 text-slate-300">
                  优先看投诉、续费、卡点、退款和高意向对话；列表只暴露摘要，全文查看保持审计。
                </p>
              </div>
              <BiButton
                onClick={() => setReloadNonce(value => value + 1)}
                variant="secondary"
                size="xs"
                disabled={loadingSessions}
                aria-label="刷新会员对话列表"
              >
                {loadingSessions ? '刷新中…' : '刷新'}
              </BiButton>
            </div>
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              <SignalCard label="匹配会话" value={sessions.length} hint={loadedSessions ? '来自 session_store' : '360 摘要快照'} />
              <SignalCard label="可读消息" value={totalMessages} hint="全文需 audit" />
              <SignalCard label="最近更新" value={formatShortTime(latestSession?.at)} hint={latestSession?.source || '暂无来源'} />
            </div>
          </div>

          <div className="grid gap-2 p-4 md:grid-cols-[1.4fr_0.8fr_0.8fr_0.9fr_0.7fr_auto]">
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              className="min-h-10 rounded-2xl border border-white/10 bg-white/[0.06] px-3 text-xs text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
              placeholder="搜索标题 / 摘要 / session_id"
              aria-label="搜索会员对话"
            />
            <select
              value={sourceFilter}
              onChange={event => setSourceFilter(event.target.value)}
              className="min-h-10 rounded-2xl border border-white/10 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none focus:border-cyan-300/40"
              aria-label="按来源筛选会员对话"
            >
              <option value="">全部来源</option>
              {sourceOptions.map(option => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <select
              value={capabilityFilter}
              onChange={event => setCapabilityFilter(event.target.value)}
              className="min-h-10 rounded-2xl border border-white/10 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none focus:border-cyan-300/40"
              aria-label="按能力筛选会员对话"
            >
              <option value="">全部能力</option>
              {capabilityOptions.map(option => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
            <select
              value={sort}
              onChange={event => setSort(event.target.value as typeof sort)}
              className="min-h-10 rounded-2xl border border-white/10 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none focus:border-cyan-300/40"
              aria-label="会员对话排序字段"
            >
              <option value="updated_at">最近更新</option>
              <option value="created_at">创建时间</option>
              <option value="message_count">消息数</option>
              <option value="title">标题</option>
              <option value="source">来源</option>
              <option value="capability">能力</option>
            </select>
            <select
              value={order}
              onChange={event => setOrder(event.target.value as typeof order)}
              className="min-h-10 rounded-2xl border border-white/10 bg-slate-950/60 px-3 text-xs text-slate-100 outline-none focus:border-cyan-300/40"
              aria-label="会员对话排序方向"
            >
              <option value="desc">降序</option>
              <option value="asc">升序</option>
            </select>
            <BiButton onClick={clearFilters} variant="secondary" size="xs" aria-label="清空会员对话筛选">
              清空
            </BiButton>
          </div>
        </section>

        <section className="rounded-3xl border border-amber-300/25 bg-amber-300/10 p-4 text-xs text-amber-100 shadow-lg shadow-black/10">
          <div className="font-medium">查看全文必须选择原因（计划 §3.5 / §Batch 5）</div>
          <fieldset className="mt-2 grid gap-2 sm:grid-cols-2" aria-label="查看原因">
            {VIEW_REASONS.map(r => (
              <label key={r.key} className="flex items-center gap-2 rounded-2xl border border-amber-200/15 bg-amber-50/5 px-3 py-2 text-amber-100">
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
                className="w-full rounded-2xl border border-amber-300/25 bg-slate-950/35 p-3 text-amber-50 outline-none placeholder:text-amber-200/45 focus:border-amber-300/50 focus:ring-2 focus:ring-amber-300/20"
                placeholder="补充原因 (≥ 4 字)，将写入 audit"
                aria-label="其他原因补充说明"
              />
            ) : null}
          </fieldset>
          {reasonBlockedMessage ? (
            <p className="mt-2 text-[11px] leading-5 text-amber-100/75">
              {reasonBlockedMessage}
            </p>
          ) : null}
        </section>

        {loadingSessions ? (
          <BiNotice tone="sky">
            正在读取会员对话列表…
          </BiNotice>
        ) : null}
        {sessionError ? (
          <BiNotice tone="rose">
            对话列表加载失败：{sessionError}
          </BiNotice>
        ) : null}

        {/* Round 5 B3: production MOCK_SESSIONS is []; render an explicit
            empty state so admins don't see a silently blank list under the
            reason form (frontend reviewer finding). */}
        {!loadingSessions && sessions.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-white/15 bg-white/[0.035] p-6 text-xs text-slate-400">
            <div className="text-sm font-black text-slate-100">暂无匹配会话</div>
            <p className="mt-2 leading-5">
              已读取 <code className="font-mono">/api/v1/bi/member/{member.user_id}/conversations</code>。
              可能原因：当前筛选过窄、该会员没有 session_store 会话、或真实登录身份未写入
              canonical_user_id / alias_user_ids。
            </p>
            <div className="mt-3 rounded-2xl border border-white/10 bg-slate-950/30 p-3 text-[11px] leading-5">
              下一步建议：用手机号 / user_id 全局搜索确认会员身份；若学员确认聊过但此处为空，检查
              session owner_key 与 member alias 归因。
            </div>
          </div>
        ) : null}

        <ul className="space-y-2">
          {normalizedSessions.map(session => {
            const expanded = expandedId === session.id
            const messages = revealedMessages[session.id] ?? []
            return (
              <li key={session.id} className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.045] shadow-lg shadow-black/10">
                <div className="flex items-start justify-between gap-3 p-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="truncate text-sm font-black text-slate-100">{session.title}</div>
                      <span className="rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2 py-0.5 text-[10px] font-bold text-cyan-100">
                        {session.count} 条
                      </span>
                      {session.source ? (
                        <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[10px] text-slate-300">
                          {session.source}
                        </span>
                      ) : null}
                      {session.capability ? (
                        <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[10px] text-slate-300">
                          {session.capability}
                        </span>
                      ) : null}
                    </div>
                    <div className="mt-0.5 text-[11px] text-slate-400">{session.at}</div>
                    <ConversationMarkdown label="摘要" text={session.summary} />
                  </div>
                  <BiButton
                    onClick={() => {
                      void tryReveal(session.id)
                    }}
                    className="shrink-0 whitespace-nowrap"
                    disabled={
                      !reason ||
                      (reason === 'other' && reasonNote.trim().length < 4) ||
                      auditState === 'writing'
                    }
                    title={reasonBlockedMessage || `查看 ${session.title} 全文`}
                    variant="secondary"
                    size="xs"
                    aria-label={`查看 ${session.title} 全文，将写入 audit`}
                  >
                    {expanded ? '已展开' : auditState === 'writing' ? '写入中…' : '查看全文'}
                  </BiButton>
                </div>
                {expanded ? (
                  <div className="border-t border-white/10 bg-slate-950/25 px-3 py-3 text-xs leading-relaxed text-slate-300">
                    {messages.length > 0 ? (
                      <span className="mt-2 block space-y-1">
                        {messages.slice(0, 6).map(message => (
                          <span key={message.id} className="block rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2">
                            <span className="mb-1 block text-[10px] font-black uppercase tracking-[0.16em] text-cyan-200/70">
                              {message.role}
                            </span>
                            <ConversationMarkdown text={message.content} />
                          </span>
                        ))}
                      </span>
                    ) : (
                      <span className="block rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2">
                        服务端未返回可展示全文消息；请检查 session_store message writer。
                      </span>
                    )}
                    <span className="mt-3 block text-[11px] text-slate-400">
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
                    </span>
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
      source: session.source || '',
      capability: session.capability || '',
      count: Number(session.message_count) || 0,
    }
  }
  return {
    id: session.id,
    title: session.title,
    summary: session.summary,
    at: session.at,
    source: 'dev',
    capability: 'mock',
    count: 0,
  }
}

function getAuditedMessages(data: unknown): MemberConversationMessagePreview[] {
  if (!data || typeof data !== 'object') return []
  const messages = (data as MemberConversationViewAudit).messages
  return Array.isArray(messages) ? messages : []
}

function getPreviewMessages(
  sessions: Array<MemberConversationPreview | { id: string; title: string; summary: string; at: string }>,
  sessionId: string
): MemberConversationMessagePreview[] {
  const session = sessions.find(item => 'session_id' in item && item.session_id === sessionId)
  if (!session || !('messages' in session)) return []
  return Array.isArray(session.messages) ? session.messages : []
}

function uniqueOptions(values: Array<string | undefined>): string[] {
  return Array.from(
    new Set(values.map(value => String(value || '').trim()).filter(Boolean))
  ).sort()
}

function ConversationMarkdown({ label, text }: { label?: string; text: string }) {
  const content = normalizeConversationMarkdown(text)
  if (!content) return null
  return (
    <div className="mt-2 rounded-2xl border border-white/10 bg-slate-950/30 px-3 py-2">
      {label ? (
        <div className="mb-1 text-[10px] font-black uppercase tracking-[0.16em] text-cyan-200/70">
          {label}
        </div>
      ) : null}
      <SimpleMarkdownRenderer
        content={content}
        variant="compact"
        className="[--background:#0e1624] [--border:rgba(148,163,184,0.22)] [--card:rgba(15,23,42,0.72)] [--foreground:#e5edf8] [--muted:rgba(148,163,184,0.12)] [--muted-foreground:#a9b8cc] [--primary:#67e8f9] [&_h2]:!text-base [&_h3]:!text-sm [&_hr]:!my-3 [&_li]:!my-1 [&_ol]:!my-2 [&_p]:!my-2 [&_strong]:text-slate-50"
      />
    </div>
  )
}

function formatShortTime(value?: string): string {
  if (!value) return '—'
  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  } catch {
    return value
  }
}

function SignalCard({ label, value, hint }: { label: string; value: React.ReactNode; hint: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.055] p-3">
      <div className="text-[11px] text-slate-400">{label}</div>
      <div className="mt-1 text-xl font-black text-slate-50">{value}</div>
      <div className="mt-1 truncate text-[11px] text-slate-500">{hint}</div>
    </div>
  )
}
