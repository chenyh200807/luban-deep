/* eslint-disable i18n/no-literal-ui-text */
'use client'

import {
  CheckCircle2,
  ClipboardList,
  Filter,
  Eye,
  Mail,
  MessageSquareWarning,
  Pencil,
  Phone,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  XCircle,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  BiButton,
  BiDataTable,
  BiDateTime,
  BiIdToken,
  BiSelect,
  BiSidePanel,
  BiStatusPill,
  BiV2DataSourceBanner,
  type BiStatusTone,
  type BiTableColumn,
} from '@/components/bi-v2'
import {
  getBiFeedback,
  getBiInviteTestApplications,
  getBiInviteTestStats,
  type BiFeedbackPayload,
  type BiFeedbackRecord,
  type BiInviteTestApplication,
  type BiInviteTestStats,
} from '@/lib/bi-api'
import { useAuditedAction } from '../useAuditedAction'
import {
  FEEDBACK_ITEMS,
  OWNER_LABELS,
  SOURCE_LABELS,
  STATUS_LABELS,
  type FeedbackItem,
  type FeedbackOwner,
  type FeedbackStatus,
} from './data'
import { FEEDBACK_WINDOW_DAYS, feedbackWindowHint } from './feedback-window'

type Filter = {
  status: '' | FeedbackStatus
  source: '' | FeedbackItem['source']
  owner: '' | FeedbackOwner
}

const DEFAULT_FILTER: Filter = { status: '', source: '', owner: '' }

type FeedbackWorkspaceView = 'feedback' | 'invite-test'

type InviteTestFilter = {
  q: string
  status: string
  source_page: string
}

type InviteApplicationFormState = {
  status: string
  operator_note: string
  name: string
  phone: string
  email: string
  wechat_id: string
  exam_type: string
  exam_stage: string
  pain_point: string
  weekly_time: string
  current_method: string
  study_difficulties: string
  latest_wrong_question: string
  is_yousen_member: string
  exam_date: string
  accept_interview: boolean
  province: string
  age_range: string
  education: string
  occupation: string
  preparation_years: string
  knowledge_foundation: string
  daily_study_time: string
}

const DEFAULT_INVITE_FILTER: InviteTestFilter = { q: '', status: '', source_page: '' }
const INVITE_TEST_WINDOW_DAYS = 365

function readFeedbackWorkspaceView(): FeedbackWorkspaceView {
  if (typeof window === 'undefined') return 'feedback'
  const search = new URLSearchParams(window.location.search)
  const tab = search.get('tab') ?? ''
  const panel = search.get('panel') ?? search.get('feedback') ?? ''
  return tab === 'invite-test' || panel === 'invite-test' ? 'invite-test' : 'feedback'
}

const STATUS_TONE: Record<FeedbackStatus, 'amber' | 'sky' | 'slate'> = {
  open: 'amber',
  triaged: 'sky',
  ignored: 'slate',
}

const SOURCE_TONE = {
  ai_message: 'sky',
  invite_test: 'amber',
  member_note: 'slate',
} as const

export type BiV2FeedbackPanelProps = {
  flagEnabled: boolean
}

export function BiV2FeedbackPanel({ flagEnabled }: BiV2FeedbackPanelProps) {
  const [workspaceView, setWorkspaceView] =
    useState<FeedbackWorkspaceView>(readFeedbackWorkspaceView)
  const [filter, setFilter] = useState<Filter>(DEFAULT_FILTER)
  const [groupByOwner, setGroupByOwner] = useState(false)
  const [payload, setPayload] = useState<BiFeedbackPayload | null>(null)
  const [loading, setLoading] = useState(flagEnabled)
  const [error, setError] = useState('')
  const [selectedFeedback, setSelectedFeedback] = useState<FeedbackItem | null>(null)
  const [inviteFilter, setInviteFilter] = useState<InviteTestFilter>(DEFAULT_INVITE_FILTER)
  const [inviteStats, setInviteStats] = useState<BiInviteTestStats | null>(null)
  const [inviteApplications, setInviteApplications] = useState<BiInviteTestApplication[]>([])
  const [inviteTotal, setInviteTotal] = useState(0)
  const [inviteLoading, setInviteLoading] = useState(flagEnabled)
  const [inviteError, setInviteError] = useState('')
  const [selectedInvite, setSelectedInvite] = useState<BiInviteTestApplication | null>(null)
  const [pendingInviteDeleteId, setPendingInviteDeleteId] = useState('')
  const [feedbackStatusOverrides, setFeedbackStatusOverrides] = useState<
    Record<string, FeedbackStatus>
  >({})
  const feedbackTriage = useAuditedAction({ actionType: 'feedback.ai.triage' })
  const inviteApplicationUpdate = useAuditedAction({
    actionType: 'feedback.invite_test.update',
  })
  const inviteApplicationDelete = useAuditedAction({
    actionType: 'feedback.invite_test.delete',
  })
  const triageWriting = feedbackTriage.state.phase === 'writing'
  const triageError =
    feedbackTriage.state.phase === 'denied' ? (feedbackTriage.state.result.error ?? '') : ''
  const inviteWriting = inviteApplicationUpdate.state.phase === 'writing'
  const inviteWriteError =
    inviteApplicationUpdate.state.phase === 'denied'
      ? (inviteApplicationUpdate.state.result.error ?? '')
      : ''
  const inviteDeleting = inviteApplicationDelete.state.phase === 'writing'

  const loadFeedback = useCallback(async () => {
    if (!flagEnabled) {
      setPayload(null)
      setLoading(false)
      setError('')
      return
    }
    try {
      setLoading(true)
      setError('')
      setPayload(await getBiFeedback({ days: FEEDBACK_WINDOW_DAYS, limit: 100 }))
      setFeedbackStatusOverrides({})
    } catch (err) {
      setError(err instanceof Error ? err.message : '反馈中心加载失败')
      setPayload(null)
    } finally {
      setLoading(false)
    }
  }, [flagEnabled])

  const loadInviteTest = useCallback(async () => {
    if (!flagEnabled) {
      setInviteStats(null)
      setInviteApplications([])
      setInviteTotal(0)
      setInviteLoading(false)
      setInviteError('')
      return
    }
    try {
      setInviteLoading(true)
      setInviteError('')
      const [stats, list] = await Promise.all([
        getBiInviteTestStats({ days: INVITE_TEST_WINDOW_DAYS }),
        getBiInviteTestApplications({
          days: INVITE_TEST_WINDOW_DAYS,
          limit: 100,
          q: inviteFilter.q.trim() || undefined,
          status: inviteFilter.status || undefined,
          source_page: inviteFilter.source_page.trim() || undefined,
        }),
      ])
      setInviteStats(stats)
      setInviteApplications(list.items)
      setInviteTotal(list.total)
    } catch (err) {
      setInviteStats(null)
      setInviteApplications([])
      setInviteTotal(0)
      setInviteError(err instanceof Error ? err.message : '内测申请加载失败')
    } finally {
      setInviteLoading(false)
    }
  }, [flagEnabled, inviteFilter.q, inviteFilter.source_page, inviteFilter.status])

  useEffect(() => {
    void loadFeedback()
  }, [loadFeedback])

  useEffect(() => {
    void loadInviteTest()
  }, [loadInviteTest])

  function switchWorkspaceView(next: FeedbackWorkspaceView) {
    setWorkspaceView(next)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.set('tab', 'feedback')
      if (next === 'invite-test') url.searchParams.set('panel', 'invite-test')
      else url.searchParams.delete('panel')
      window.history.replaceState(null, '', url)
    }
  }

  const items = useMemo<FeedbackItem[]>(() => {
    const base = flagEnabled ? (payload?.recent ?? []).map(mapFeedbackRecord) : FEEDBACK_ITEMS
    return base.map(item => ({
      ...item,
      status: feedbackStatusOverrides[item.id] ?? item.status,
    }))
  }, [feedbackStatusOverrides, flagEnabled, payload])

  const filtered = useMemo(
    () =>
      items.filter(i => {
        if (filter.status && i.status !== filter.status) return false
        if (filter.source && i.source !== filter.source) return false
        if (filter.owner && i.owner !== filter.owner) return false
        return true
      }),
    [items, filter]
  )

  const counts = useMemo(() => {
    return {
      total: payload?.summary.total_feedback ?? items.length,
      open: items.filter(i => i.status === 'open').length,
      triaged: items.filter(i => i.status === 'triaged').length,
      ignored: items.filter(i => i.status === 'ignored').length,
    }
  }, [items, payload])

  const columns = useMemo<BiTableColumn<FeedbackItem>[]>(
    () => [
      {
        key: 'source',
        label: '来源',
        render: i => <BiStatusPill tone={SOURCE_TONE[i.source]} label={SOURCE_LABELS[i.source]} />,
      },
      {
        key: 'rating',
        label: '评分',
        align: 'right',
        render: i => <span className="tabular-nums">{renderRating(i.rating)}</span>,
      },
      {
        key: 'reason',
        label: '原因 / 内容',
        render: i => (
          <div className="min-w-0">
            <div className="truncate text-slate-100">{i.reason}</div>
            <div className="truncate text-[11px] text-slate-400">{i.detail}</div>
          </div>
        ),
      },
      {
        key: 'member',
        label: '关联会员',
        render: i => <BiIdToken value={i.member} head={8} tail={5} />,
      },
      {
        key: 'status',
        label: '状态',
        render: i => <BiStatusPill tone={STATUS_TONE[i.status]} label={STATUS_LABELS[i.status]} />,
      },
      { key: 'owner', label: 'owner', render: i => OWNER_LABELS[i.owner] },
      {
        key: 'sla',
        label: 'SLA',
        render: i => (i.sla_target_hours > 0 ? `${i.sla_target_hours}h` : '—'),
      },
      {
        key: 'at',
        label: '时间',
        render: i => <BiDateTime value={i.created_at} />,
      },
    ],
    []
  )

  const grouped = useMemo(() => {
    const map = new Map<FeedbackOwner, FeedbackItem[]>()
    for (const item of filtered) {
      const arr = map.get(item.owner) ?? []
      arr.push(item)
      map.set(item.owner, arr)
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [filtered])

  async function handleFeedbackTriage(item: FeedbackItem, status: Exclude<FeedbackStatus, 'open'>) {
    if (!flagEnabled || triageWriting) return
    const result = await feedbackTriage.execute({
      key: 'feedback.ai.triage',
      params: { feedback_id: item.id },
      body: {
        status,
        note: status === 'triaged' ? 'BI feedback triage' : 'BI feedback ignored',
      },
    })
    if (!result.ok) return
    const nextStatus = extractFeedbackTriageStatus(result.data) ?? status
    setFeedbackStatusOverrides(prev => ({ ...prev, [item.id]: nextStatus }))
  }

  function renderFeedbackActions(item: FeedbackItem) {
    return (
      <div className="flex justify-end gap-1">
        <BiButton
          onClick={() => setSelectedFeedback(item)}
          variant="secondary"
          size="xs"
          aria-label={`查看反馈 ${item.id} 详情`}
        >
          <Eye className="h-3 w-3" aria-hidden />
          查看
        </BiButton>
        <BiButton
          disabled={!flagEnabled || triageWriting || item.status === 'triaged'}
          title="写入 feedback_triage audit；完整派单工作流待接入"
          onClick={() => void handleFeedbackTriage(item, 'triaged')}
          variant="secondary"
          size="xs"
          aria-label={`标记已看反馈 ${item.id}`}
        >
          <CheckCircle2 className="h-3 w-3" aria-hidden />
          已看
        </BiButton>
        <BiButton
          disabled={!flagEnabled || triageWriting || item.status === 'ignored'}
          title="写入 feedback_triage audit"
          onClick={() => void handleFeedbackTriage(item, 'ignored')}
          variant="secondary"
          size="xs"
          aria-label={`忽略反馈 ${item.id}`}
        >
          <XCircle className="h-3 w-3" aria-hidden />
          忽略
        </BiButton>
      </div>
    )
  }

  async function handleInviteApplicationSave(
    item: BiInviteTestApplication,
    patch: InviteApplicationFormState
  ) {
    if (!flagEnabled || inviteWriting || !item.id) return
    const result = await inviteApplicationUpdate.execute({
      key: 'feedback.invite_test.update',
      params: { application_id: item.id },
      body: patch,
    })
    if (!result.ok) return
    const updated = extractInviteApplicationFromUpdate(result.data, item)
    setInviteApplications(prev =>
      prev.map(candidate => (candidate.id === item.id ? updated : candidate))
    )
    setSelectedInvite(updated)
    void loadInviteTest()
  }

  async function handleInviteApplicationDelete(item: BiInviteTestApplication) {
    if (!flagEnabled || inviteDeleting || !item.id) return
    if (pendingInviteDeleteId !== item.id) {
      setPendingInviteDeleteId(item.id)
      return
    }
    setPendingInviteDeleteId('')
    const result = await inviteApplicationDelete.execute({
      key: 'feedback.invite_test.delete',
      params: { application_id: item.id },
      body: { reason: 'admin_deleted_from_bi' },
    })
    if (!result.ok) {
      setInviteError(result.error || '归档内测申请失败')
      return
    }
    setInviteApplications(prev => prev.filter(candidate => candidate.id !== item.id))
    setInviteTotal(prev => Math.max(0, prev - 1))
    if (selectedInvite?.id === item.id) setSelectedInvite(null)
    void loadInviteTest()
  }

  return (
    <section className="space-y-5">
      {!flagEnabled ? (
        <BiV2DataSourceBanner tone="amber">
          BI_FEEDBACK_V2_ENABLED 未开启 · 当前 Batch 5 静态原型。P0 仅接 AI 消息反馈 / 内测申请 /
          运营备注；P1 再接教研 / 系统质量。
        </BiV2DataSourceBanner>
      ) : (
        <BiV2DataSourceBanner
          tone="sky"
          action={
            <BiButton
              onClick={() => {
                void loadFeedback()
                void loadInviteTest()
              }}
              disabled={loading || inviteLoading}
              variant="primary"
              size="xs"
              aria-label="刷新反馈中心"
            >
              <RefreshCw
                className={`h-3 w-3 ${loading || inviteLoading ? 'animate-spin' : ''}`}
                aria-hidden
              />
              刷新
            </BiButton>
          }
        >
          反馈中心已接入真实读模型 · AI 消息反馈与内测申请池分区管理
          {payload ? ` · storage=${payload.storage_status}` : ''}；已看 / 忽略 / 归档写入审计。
        </BiV2DataSourceBanner>
      )}
      {triageError ? (
        <div
          className="rounded-2xl border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-xs text-rose-100"
          role="alert"
        >
          反馈处理未写入：{triageError}
        </div>
      ) : null}
      {triageWriting ? (
        <div
          className="rounded-2xl border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-xs text-cyan-100"
          aria-live="polite"
        >
          正在写入反馈处理 audit…
        </div>
      ) : null}
      {inviteWriteError ? (
        <div
          className="rounded-2xl border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-xs text-rose-100"
          role="alert"
        >
          内测申请未保存：{inviteWriteError}
        </div>
      ) : null}
      {inviteWriting ? (
        <div
          className="rounded-2xl border border-cyan-300/25 bg-cyan-300/10 px-3 py-2 text-xs text-cyan-100"
          aria-live="polite"
        >
          正在保存内测申请并写入 audit…
        </div>
      ) : null}

      <FeedbackWorkspaceSwitcher
        current={workspaceView}
        feedbackCount={counts.total}
        inviteCount={inviteStats?.summary.total_applications ?? inviteTotal}
        onSelect={switchWorkspaceView}
      />

      {workspaceView === 'feedback' ? (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <Tile label="全部" value={counts.total} hint={feedbackWindowHint()} />
            <Tile label="待处理" value={counts.open} tone="amber" hint="P0 优先处理" />
            <Tile label="已看" value={counts.triaged} tone="sky" hint="派单工作流待接入" />
            <Tile label="已忽略" value={counts.ignored} tone="slate" hint="带 audit 说明" />
          </div>

          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.035] p-2 text-xs text-slate-300">
            <label className="inline-flex items-center gap-1 font-bold">
              状态
              <BiSelect
                value={filter.status}
                onChange={e => setFilter({ ...filter, status: e.target.value as Filter['status'] })}
                className="h-8"
                aria-label="按状态筛选反馈"
              >
                <option value="">全部</option>
                <option value="open">待处理</option>
                <option value="triaged">已看</option>
                <option value="ignored">已忽略</option>
              </BiSelect>
            </label>
            <label className="inline-flex items-center gap-1 font-bold">
              来源
              <BiSelect
                value={filter.source}
                onChange={e => setFilter({ ...filter, source: e.target.value as Filter['source'] })}
                className="h-8"
                aria-label="按来源筛选反馈"
              >
                <option value="">全部</option>
                <option value="ai_message">AI 消息反馈</option>
                <option value="invite_test">内测申请</option>
                <option value="member_note">运营备注</option>
              </BiSelect>
            </label>
            <label className="inline-flex items-center gap-1 font-bold">
              owner
              <BiSelect
                value={filter.owner}
                onChange={e => setFilter({ ...filter, owner: e.target.value as Filter['owner'] })}
                className="h-8"
                aria-label="按 owner 筛选反馈"
              >
                <option value="">全部</option>
                <option value="quality">AI 质量</option>
                <option value="growth">增长</option>
                <option value="ops">运营</option>
                <option value="product">产品</option>
              </BiSelect>
            </label>
            <button
              type="button"
              onClick={() => setGroupByOwner(v => !v)}
              aria-pressed={groupByOwner}
              className={`h-8 rounded-xl border px-3 text-xs font-black ${
                groupByOwner
                  ? 'border-cyan-300/30 bg-cyan-300/15 text-cyan-100'
                  : 'border-white/10 text-slate-300 hover:bg-white/[0.06]'
              }`}
            >
              {groupByOwner ? '取消 owner 分组' : '按 owner 分组'}
            </button>
            <button
              type="button"
              onClick={() => setFilter(DEFAULT_FILTER)}
              className="ml-auto h-8 rounded-xl px-2 text-xs font-bold text-slate-400 hover:bg-white/[0.06] hover:text-slate-100"
              aria-label="清空反馈筛选"
            >
              清空筛选
            </button>
          </div>

          {!groupByOwner ? (
            <BiDataTable<FeedbackItem>
              columns={columns}
              rows={filtered}
              rowKey={i => i.id}
              status={
                loading
                  ? 'loading'
                  : error
                    ? 'error'
                    : filtered.length === 0
                      ? items.length === 0
                        ? 'empty'
                        : 'no-results'
                      : 'ok'
              }
              errorMessage={error}
              emptyTitle="暂无反馈"
              emptyHint={
                flagEnabled
                  ? '当前窗口内没有 ai_feedback 记录。'
                  : '开启 BI_FEEDBACK_V2_ENABLED 后读取真实反馈。'
              }
              rowAction={renderFeedbackActions}
            />
          ) : (
            <div className="space-y-4">
              {grouped.length === 0 ? (
                <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 text-center text-xs text-slate-400">
                  {loading ? '加载反馈中…' : error || '当前筛选下无反馈'}
                </div>
              ) : null}
              {grouped.map(([owner, list]) => (
                <article
                  key={owner}
                  className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.04] shadow-lg shadow-black/10"
                >
                  <header className="flex items-center justify-between border-b border-white/10 px-3 py-2 text-xs">
                    <h3 className="font-black text-slate-100">
                      {OWNER_LABELS[owner]} · {list.length}
                    </h3>
                  </header>
                  <BiDataTable<FeedbackItem>
                    columns={columns}
                    rows={list}
                    rowKey={i => i.id}
                    status="ok"
                    rowAction={renderFeedbackActions}
                  />
                </article>
              ))}
            </div>
          )}

          <aside className="rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-4 text-xs text-slate-300">
            <div className="flex items-center gap-2 font-black text-cyan-100">
              <MessageSquareWarning className="h-4 w-4" aria-hidden /> 对话回顾入口
            </div>
            <p className="mt-1">
              对话回顾归入「会员运营 → 学员 360 → 查看对话回顾」。全文查看必须选择原因（合规审查 /
              投诉处理 / 模型质量 / 其他）并写入 audit。
            </p>
            <p className="mt-1 text-[11px] text-slate-400">
              authority: session store · view-audit endpoint:
              /api/v1/member/&lt;user_id&gt;/conversations/&lt;session_id&gt;/view-audit
            </p>
          </aside>
        </>
      ) : (
        <InviteTestPanel
          stats={inviteStats}
          applications={inviteApplications}
          total={inviteTotal}
          loading={inviteLoading}
          error={inviteError}
          filters={inviteFilter}
          onFilterChange={(field, value) => setInviteFilter(prev => ({ ...prev, [field]: value }))}
          onRefresh={() => void loadInviteTest()}
          onOpenApplication={setSelectedInvite}
          onDeleteApplication={handleInviteApplicationDelete}
          deleting={inviteDeleting}
          pendingDeleteId={pendingInviteDeleteId}
        />
      )}
      <FeedbackDetailPanel item={selectedFeedback} onClose={() => setSelectedFeedback(null)} />
      <InviteApplicationDetailPanel
        key={
          selectedInvite
            ? `${selectedInvite.id}:${selectedInvite.status}:${selectedInvite.operator_note}`
            : 'invite-application-empty'
        }
        item={selectedInvite}
        saving={inviteWriting}
        saveError={inviteWriteError}
        onClose={() => setSelectedInvite(null)}
        onSave={handleInviteApplicationSave}
      />
    </section>
  )
}

function mapFeedbackRecord(record: BiFeedbackRecord, index: number): FeedbackItem {
  const source = normalizeSource(record.feedback_source)
  const tags = record.reason_tags ?? []
  const comment = record.comment?.trim() ?? ''
  const rating = Number.isFinite(record.rating) ? Number(record.rating) : 0
  const negative = rating < 0
  const positive = rating > 0
  const triageStatus = normalizeFeedbackStatus(record.triage_status)
  return {
    id:
      record.feedback_id ||
      record.id ||
      record.message_id ||
      `${record.session_id || 'feedback'}-${record.created_at || index}`,
    source,
    rating,
    reason: tags.length > 0 ? tags.join(' / ') : renderRating(rating),
    detail:
      comment ||
      [record.effective_response_mode || record.answer_mode, record.response_mode_degrade_reason]
        .filter(Boolean)
        .join(' · ') ||
      '无文字备注',
    member: record.user_id || record.session_id || 'unknown',
    session_id: record.session_id,
    message_id: record.message_id,
    answer_mode: record.answer_mode,
    requested_response_mode: record.requested_response_mode,
    effective_response_mode: record.effective_response_mode,
    response_mode_degrade_reason: record.response_mode_degrade_reason,
    reason_tags: tags,
    status: triageStatus ?? (negative || comment ? 'open' : positive ? 'ignored' : 'triaged'),
    owner: inferOwner(source, tags, comment, negative),
    created_at: record.created_at || '—',
    sla_target_hours: negative ? 24 : comment ? 72 : 0,
  }
}

function FeedbackWorkspaceSwitcher({
  current,
  feedbackCount,
  inviteCount,
  onSelect,
}: {
  current: FeedbackWorkspaceView
  feedbackCount: number
  inviteCount: number
  onSelect: (next: FeedbackWorkspaceView) => void
}) {
  const items: Array<{
    key: FeedbackWorkspaceView
    label: string
    count: number
    hint: string
  }> = [
    {
      key: 'feedback',
      label: 'AI 消息反馈',
      count: feedbackCount,
      hint: '点赞 / 点踩 / 文字反馈',
    },
    {
      key: 'invite-test',
      label: '内测申请',
      count: inviteCount,
      hint: '申请池 / 联系方式 / 痛点筛选',
    },
  ]
  return (
    <div
      className="grid grid-cols-1 gap-2 rounded-2xl border border-white/10 bg-white/[0.04] p-1.5 shadow-lg shadow-black/10 md:grid-cols-2"
      role="tablist"
      aria-label="反馈中心子模块"
    >
      {items.map(item => {
        const active = item.key === current
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(item.key)}
            className={`rounded border px-3 py-2.5 text-left transition ${
              active
                ? 'border-cyan-300/25 bg-gradient-to-br from-cyan-500/20 to-slate-900/70 text-white shadow-sm'
                : 'border-transparent bg-transparent text-slate-300 hover:border-white/10 hover:bg-white/[0.05]'
            }`}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="text-sm font-semibold">{item.label}</span>
              <span
                className={`rounded px-1.5 py-0.5 text-[11px] ${
                  active ? 'bg-white/15 text-white' : 'bg-white/10 text-slate-300'
                }`}
              >
                {formatCount(item.count)}
              </span>
            </span>
            <span
              className={`mt-0.5 block text-[11px] ${active ? 'text-slate-300' : 'text-slate-400'}`}
            >
              {item.hint}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function InviteTestPanel({
  stats,
  applications,
  total,
  loading,
  error,
  filters,
  onFilterChange,
  onRefresh,
  onOpenApplication,
  onDeleteApplication,
  deleting,
  pendingDeleteId,
}: {
  stats: BiInviteTestStats | null
  applications: BiInviteTestApplication[]
  total: number
  loading: boolean
  error: string
  filters: InviteTestFilter
  onFilterChange: (field: keyof InviteTestFilter, value: string) => void
  onRefresh: () => void
  onOpenApplication: (item: BiInviteTestApplication) => void
  onDeleteApplication: (item: BiInviteTestApplication) => void
  deleting: boolean
  pendingDeleteId: string
}) {
  const priorityCount = countPriorityInviteApplications(applications)
  const currentStats = summarizeVisibleInviteApplications(applications)

  return (
    <div className="space-y-4">
      <InvitePrescriptionHero
        priorityCount={priorityCount}
        total={total}
        acceptInterviewCount={currentStats.acceptInterviewCount}
        painPoint={topInvitePainPoint(stats)}
        onStartQueue={() => {
          onFilterChange('status', 'submitted')
          onFilterChange('q', '')
        }}
        onExplain={() => {
          document.getElementById('bi-v2-invite-ops-playbook')?.scrollIntoView({
            behavior: 'smooth',
            block: 'nearest',
          })
        }}
      />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <Tile
          label="申请总数"
          value={total}
          hint={`当前筛选 · 近 ${INVITE_TEST_WINDOW_DAYS}d`}
        />
        <Tile label="可联系人数" value={currentStats.uniqueContacts} hint="当前筛选去重联系方式" />
        <Tile
          label="愿意回访"
          value={currentStats.acceptInterviewCount}
          tone="sky"
          hint={formatRate(currentStats.acceptInterviewRate)}
        />
        <Tile
          label="带错题样本"
          value={currentStats.wrongQuestionCount}
          tone="amber"
          hint={formatRate(currentStats.wrongQuestionRate)}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.04] shadow-xl shadow-black/20">
          <div className="border-b border-white/10 p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="inline-flex items-center gap-1.5 rounded-full border border-cyan-300/25 bg-cyan-300/10 px-2.5 py-1 text-[11px] font-black text-cyan-100">
                  <Sparkles className="h-3 w-3" aria-hidden />
                  真实申请池
                </div>
                <h3 className="mt-2 text-xl font-black text-white">内测申请池</h3>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  authority: <code className="font-mono">public.invite_test_applications</code> ·
                  从卡片进入编辑、归档和回访，不再只有查看按钮。
                </p>
              </div>
              <button
                type="button"
                onClick={onRefresh}
                disabled={loading}
                className="inline-flex h-11 items-center justify-center gap-1.5 rounded-2xl border border-white/10 bg-white/[0.06] px-3 text-xs font-bold text-slate-100 hover:bg-white/10 disabled:opacity-50"
                aria-label="刷新内测申请"
              >
                <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} aria-hidden />
                刷新
              </button>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-2 rounded-2xl border border-white/10 bg-white/[0.035] p-2 lg:grid-cols-[minmax(0,1fr)_150px_150px_auto]">
              <label className="relative">
                <Search
                  className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                  aria-hidden
                />
                <input
                  value={filters.q}
                  onChange={event => onFilterChange('q', event.target.value)}
                  placeholder="搜索姓名 / 手机 / 邮箱 / 考试 / 痛点"
                  className="h-11 w-full rounded-xl border border-white/10 bg-white/[0.06] px-9 text-xs text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
                  aria-label="搜索内测申请"
                />
              </label>
              <BiSelect
                value={filters.status}
                onChange={event => onFilterChange('status', event.target.value)}
                className="h-11"
                aria-label="按内测申请状态筛选"
              >
                <option value="">全部状态</option>
                <option value="submitted">已提交</option>
                <option value="contacted">已联系</option>
                <option value="accepted">已入选</option>
                <option value="rejected">未入选</option>
                <option value="archived">已归档</option>
              </BiSelect>
              <input
                value={filters.source_page}
                onChange={event => onFilterChange('source_page', event.target.value)}
                placeholder="来源页"
                className="h-11 rounded-xl border border-white/10 bg-white/[0.06] px-3 text-xs text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
                aria-label="按来源页筛选内测申请"
              />
              <div className="flex h-11 items-center justify-end gap-1.5 text-xs font-bold text-slate-400">
                <Filter className="h-3.5 w-3.5" aria-hidden />共 {formatCount(total)} 条
              </div>
            </div>
            {error ? (
              <p className="mt-3 rounded-2xl border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-xs text-rose-100">
                {error}
              </p>
            ) : null}
          </div>

          <div className="grid gap-3 p-4">
            {loading ? (
              <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-10 text-center text-sm text-slate-400">
                正在加载内测申请…
              </div>
            ) : null}
            {!loading && !error && applications.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.035] px-4 py-10 text-center">
                <div className="font-bold text-slate-100">暂无内测申请</div>
                <div className="mt-1 text-xs text-slate-400">
                  当前筛选下没有申请记录，或内测申请存储暂未返回数据。
                </div>
              </div>
            ) : null}
            {!loading && !error
              ? applications.map(item => (
                  <InviteApplicationCard
                    key={item.id || `${item.phone}-${item.created_at}`}
                    item={item}
                    onOpenApplication={onOpenApplication}
                    onDeleteApplication={onDeleteApplication}
                    deleting={deleting}
                    pendingDeleteId={pendingDeleteId}
                  />
                ))
              : null}
          </div>
          <div className="flex flex-wrap justify-between gap-2 border-t border-white/10 px-4 py-3 text-[11px] font-bold text-slate-400">
            <span>
              显示 {applications.length} / {total}
            </span>
            <span>服务端返回前 {applications.length} / {total}</span>
          </div>
        </section>

        <aside className="space-y-3">
          <InviteOpsSignal
            label="优先处理"
            value={priorityCount}
            hint="愿意回访 / 已留联系方式 / 待联系"
            tone="sky"
          />
          <InviteOpsSignal
            label="当前筛选"
            value={applications.length}
            hint={`服务端总数 ${formatCount(total)}`}
            tone="slate"
          />
          <InviteOpsSignal
            label="主来源"
            value={topInviteSource(stats)}
            hint="按来源页聚合"
            tone="amber"
          />
          <InviteOpsPlaybook />
        </aside>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <BreakdownCard
          title="考试类型"
          items={(stats?.exam_type_breakdown ?? []).slice(0, 5).map(item => ({
            label: item.exam_type,
            count: item.count,
          }))}
        />
        <BreakdownCard
          title="最想解决的问题"
          items={(stats?.pain_point_breakdown ?? []).slice(0, 5).map(item => ({
            label: item.pain_point,
            count: item.count,
          }))}
        />
      </div>
    </div>
  )
}

function InvitePrescriptionHero({
  priorityCount,
  total,
  acceptInterviewCount,
  painPoint,
  onStartQueue,
  onExplain,
}: {
  priorityCount: number
  total: number
  acceptInterviewCount: number
  painPoint: string
  onStartQueue: () => void
  onExplain: () => void
}) {
  const queueStrength =
    total > 0 ? Math.min(92, Math.max(54, Math.round((priorityCount / total) * 100 + 52))) : 54
  return (
    <section className="grid gap-5 rounded-3xl border border-sky-300/20 bg-gradient-to-br from-[#1f2959]/90 to-[#141c36]/95 p-5 shadow-xl shadow-black/20 md:grid-cols-[minmax(0,1fr)_170px] md:p-7">
      <div className="min-w-0">
        <div className="text-xs font-black text-orange-300">当前筛选提示</div>
        <h3 className="mt-2 max-w-4xl text-3xl font-black leading-tight tracking-normal text-white md:text-4xl">
          优先回访「{painPoint || '案例题不会写'}」的高意向申请人
        </h3>
        <p className="mt-4 max-w-4xl text-sm leading-7 text-slate-300/85">
          {formatCount(total)} 条内测申请里，有 {formatCount(acceptInterviewCount)} 条愿意回访，
          {formatCount(priorityCount)} 条适合立即进入跟进队列。先处理联系方式完整、痛点明确的人，再补齐样本缺口。
        </p>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onStartQueue}
            className="inline-flex h-11 items-center rounded-2xl border border-cyan-200/40 bg-cyan-300 px-4 text-sm font-black text-sky-950 shadow-lg shadow-cyan-300/10"
          >
            开始回访队列
          </button>
          <button
            type="button"
            onClick={onExplain}
            className="inline-flex h-11 items-center rounded-2xl border border-orange-300/35 bg-orange-300/10 px-4 text-sm font-black text-orange-200"
          >
            为什么推荐
          </button>
        </div>
      </div>
      <div className="relative flex min-h-[150px] items-center justify-center md:min-h-0">
        <div
          className="grid h-36 w-36 place-items-center rounded-full shadow-[0_0_0_14px_rgba(125,211,252,0.04)]"
          style={{
            background: `conic-gradient(#34d399 0 ${queueStrength * 3.6}deg, rgba(255,226,186,0.9) ${queueStrength * 3.6}deg 360deg)`,
          }}
          aria-label={`队列强度 ${queueStrength}%`}
        >
          <div className="grid h-24 w-24 place-items-center rounded-full bg-[#172141]">
            <span className="text-4xl font-black text-cyan-200">{queueStrength}</span>
          </div>
        </div>
        <div className="absolute bottom-0 text-center text-[11px] font-black text-slate-300/70">
          队列强度 · 前端筛选
        </div>
      </div>
    </section>
  )
}

function InviteApplicationCard({
  item,
  onOpenApplication,
  onDeleteApplication,
  deleting,
  pendingDeleteId,
}: {
  item: BiInviteTestApplication
  onOpenApplication: (item: BiInviteTestApplication) => void
  onDeleteApplication: (item: BiInviteTestApplication) => void
  deleting: boolean
  pendingDeleteId: string
}) {
  const rowId = item.id || item.phone
  const pending = pendingDeleteId === item.id
  const priority = invitePriority(item)
  return (
    <article className="grid min-h-[116px] grid-cols-[38px_minmax(0,1fr)] gap-3 rounded-2xl border border-white/10 bg-white/[0.045] p-3 transition hover:border-cyan-300/25 hover:bg-cyan-300/[0.06] md:grid-cols-[38px_minmax(0,1fr)_auto]">
      <div className="grid h-10 w-10 place-items-center rounded-2xl bg-white/10 text-sm font-black text-cyan-200">
        {(item.name || item.phone || '?').slice(0, 1)}
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-black text-white">{item.name || '未命名'}</span>
          <BiStatusPill tone={priority.tone} label={priority.label} ariaLabel={priority.hint} />
          <BiStatusPill
            tone={inviteStatusTone(item.status)}
            label={item.status || 'submitted'}
          />
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs font-bold text-slate-300">
          <ContactLine icon={<Phone className="h-3 w-3" aria-hidden />} value={item.phone || '—'} />
          <ContactLine icon={<Mail className="h-3 w-3" aria-hidden />} value={item.email || '—'} />
          <span>{item.exam_type || '未填写考试'}</span>
          <span>{joinNonEmpty([item.exam_stage, item.weekly_time]) || '未填写阶段'}</span>
        </div>
        <div className="mt-2 text-xs leading-5 text-slate-400">
          <span className="font-bold text-slate-200">{item.pain_point || '未填写痛点'}</span>
          <span> · </span>
          <span>
            {item.study_difficulties ||
              item.latest_wrong_question ||
              item.current_method ||
              '未填写补充材料'}
          </span>
        </div>
      </div>
      <div className="col-span-2 flex items-center justify-stretch gap-2 md:col-span-1 md:justify-end">
        <button
          type="button"
          onClick={() => onOpenApplication(item)}
          className="inline-flex h-11 flex-1 items-center justify-center gap-1 rounded-2xl border border-white/10 bg-white/[0.06] px-3 text-xs font-black text-slate-100 hover:bg-white/10 md:flex-none"
          aria-label={`编辑内测申请 ${rowId}`}
        >
          <Pencil className="h-3.5 w-3.5" aria-hidden />
          编辑
        </button>
        <button
          type="button"
          onClick={() => onDeleteApplication(item)}
          disabled={deleting}
          className={`inline-flex h-11 flex-1 items-center justify-center gap-1 rounded-2xl border px-3 text-xs font-black disabled:cursor-not-allowed disabled:opacity-50 md:flex-none ${
            pending
              ? 'border-rose-300/60 bg-rose-500 text-white'
              : 'border-rose-300/25 bg-rose-300/10 text-rose-100 hover:bg-rose-300/15'
          }`}
          aria-label={`${pending ? '确认归档' : '归档'}内测申请 ${rowId}`}
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden />
          {pending ? '确认归档' : '归档'}
        </button>
      </div>
    </article>
  )
}

function InviteOpsPlaybook() {
  return (
    <section
      id="bi-v2-invite-ops-playbook"
      className="scroll-mt-24 rounded-3xl border border-white/10 bg-gradient-to-br from-emerald-400/10 to-slate-900/60 p-4 shadow-lg shadow-black/15"
    >
      <div className="text-xs font-black text-cyan-200">运营闭环</div>
      <h3 className="mt-1 text-lg font-black text-white">像学情页一样推进</h3>
      <div className="mt-3 grid gap-2 text-xs text-slate-300">
        <div className="rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2">
          1. 看处方：先处理高意向申请
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2">
          2. 看证据：痛点、阶段、来源页
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2">
          3. 执行动作：编辑、入队、归档
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2">
          4. 回看审计：actor + idempotency
        </div>
      </div>
    </section>
  )
}

function InviteApplicationDetailPanel({
  item,
  saving,
  saveError,
  onClose,
  onSave,
}: {
  item: BiInviteTestApplication | null
  saving: boolean
  saveError: string
  onClose: () => void
  onSave: (item: BiInviteTestApplication, patch: InviteApplicationFormState) => Promise<void>
}) {
  const [form, setForm] = useState<InviteApplicationFormState>(() =>
    item ? formFromInviteApplication(item) : emptyInviteApplicationForm()
  )
  const formId = 'bi-invite-edit-form'

  function updateField<K extends keyof InviteApplicationFormState>(
    field: K,
    value: InviteApplicationFormState[K]
  ) {
    setForm(prev => ({ ...prev, [field]: value }))
  }

  return (
    <BiSidePanel
      open={Boolean(item)}
      onClose={onClose}
      title={item ? `编辑内测申请 · ${item.name || item.phone || item.id}` : '编辑内测申请'}
      subtitle={
        item
          ? `${item.status || 'submitted'} · ${formatBiDate(item.created_at)} · 保存写入 audit`
          : undefined
      }
      width="lg"
      footer={
        item ? (
          <div className="flex items-center justify-end gap-2">
            <BiButton onClick={onClose} variant="secondary" size="sm">
              关闭
            </BiButton>
            <BiButton
              type="submit"
              form={formId}
              disabled={saving}
              variant="primary"
              size="sm"
            >
              {saving ? '保存中…' : '保存并审计'}
            </BiButton>
          </div>
        ) : undefined
      }
    >
      {item ? (
        <form
          id={formId}
          className="space-y-4 text-sm"
          onSubmit={event => {
            event.preventDefault()
            void onSave(item, form)
          }}
        >
          <section className="rounded-3xl border border-cyan-300/25 bg-cyan-300/10 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <BiStatusPill tone="amber" label="内测申请" />
              <BiStatusPill
                tone={item.accept_interview ? 'emerald' : 'slate'}
                label={item.accept_interview ? '愿意回访' : '未勾选回访'}
              />
              <InvitePriorityPill item={item} />
              <span className="text-xs text-slate-400">
                提交 {formatCount(item.submit_count)} 次
              </span>
            </div>
            <p className="mt-3 text-base font-black text-white">
              {item.pain_point || '未填写痛点'}
            </p>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
              {item.study_difficulties ||
                item.latest_wrong_question ||
                item.current_method ||
                '未填写补充材料'}
            </p>
          </section>

          <section className="space-y-3 rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-xs font-black uppercase text-cyan-200">处理状态</h3>
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2 py-1 text-[11px] font-bold text-emerald-100">
                <ShieldCheck className="h-3 w-3" aria-hidden />
                保存写入 audit
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-xs font-bold text-slate-300">
                状态
                <BiSelect
                  value={form.status}
                  onChange={event => updateField('status', event.target.value)}
                  className="h-10 w-full text-sm"
                  wrapperClassName="w-full"
                >
                  <option value="submitted">已提交</option>
                  <option value="contacted">已联系</option>
                  <option value="accepted">已入选</option>
                  <option value="rejected">未入选</option>
                  <option value="waitlisted">候补</option>
                  <option value="archived">归档</option>
                </BiSelect>
              </label>
              <label className="flex min-h-10 items-center gap-2 self-end rounded-xl border border-white/10 bg-white/[0.035] px-2 py-2 text-xs font-bold text-slate-200">
                <input
                  type="checkbox"
                  checked={form.accept_interview}
                  onChange={event => updateField('accept_interview', event.target.checked)}
                  className="h-4 w-4 rounded border-slate-500 bg-slate-900"
                />
                愿意回访
              </label>
            </div>
            <label className="space-y-1 text-xs font-bold text-slate-300">
              运营备注
              <textarea
                value={form.operator_note}
                onChange={event => updateField('operator_note', event.target.value)}
                rows={3}
                maxLength={1000}
                className="w-full resize-y rounded-xl border border-white/10 bg-white/[0.06] px-2 py-1.5 text-sm leading-6 text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
                placeholder="记录联系结果、下次跟进时间、是否进入首批体验"
              />
            </label>
          </section>

          <section className="space-y-3 rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <h3 className="text-xs font-black uppercase text-cyan-200">申请人与联系方式</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TextField
                label="姓名"
                value={form.name}
                onChange={value => updateField('name', value)}
              />
              <TextField
                label="手机号"
                value={form.phone}
                onChange={value => updateField('phone', value)}
              />
              <TextField
                label="邮箱"
                value={form.email}
                onChange={value => updateField('email', value)}
              />
              <TextField
                label="微信"
                value={form.wechat_id}
                onChange={value => updateField('wechat_id', value)}
              />
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <KV label="来源页" value={item.source_page || '—'} />
              <KV label="UTM" value={joinNonEmpty([item.utm_source, item.utm_campaign]) || '—'} />
            </div>
          </section>

          <section className="space-y-3 rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <h3 className="text-xs font-black uppercase text-cyan-200">备考画像</h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <TextField
                label="考试类型"
                value={form.exam_type}
                onChange={value => updateField('exam_type', value)}
              />
              <TextField
                label="备考阶段"
                value={form.exam_stage}
                onChange={value => updateField('exam_stage', value)}
              />
              <TextField
                label="每周学习时间"
                value={form.weekly_time}
                onChange={value => updateField('weekly_time', value)}
              />
              <TextField
                label="每日学习时间"
                value={form.daily_study_time}
                onChange={value => updateField('daily_study_time', value)}
              />
              <TextField
                label="是否佑森会员"
                value={form.is_yousen_member}
                onChange={value => updateField('is_yousen_member', value)}
              />
              <TextField
                label="考试日期"
                value={form.exam_date}
                onChange={value => updateField('exam_date', value)}
              />
              <TextField
                label="省份"
                value={form.province}
                onChange={value => updateField('province', value)}
              />
              <TextField
                label="年龄段"
                value={form.age_range}
                onChange={value => updateField('age_range', value)}
              />
              <TextField
                label="学历"
                value={form.education}
                onChange={value => updateField('education', value)}
              />
              <TextField
                label="职业"
                value={form.occupation}
                onChange={value => updateField('occupation', value)}
              />
              <TextField
                label="备考年限"
                value={form.preparation_years}
                onChange={value => updateField('preparation_years', value)}
              />
              <TextField
                label="知识基础"
                value={form.knowledge_foundation}
                onChange={value => updateField('knowledge_foundation', value)}
              />
            </div>
          </section>

          <section className="space-y-3 rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <h3 className="text-xs font-black uppercase text-cyan-200">学习痛点</h3>
            <TextField
              label="主要痛点"
              value={form.pain_point}
              onChange={value => updateField('pain_point', value)}
            />
            <TextAreaField
              label="当前学习方法"
              value={form.current_method}
              onChange={value => updateField('current_method', value)}
              rows={3}
            />
            <TextAreaField
              label="学习困难"
              value={form.study_difficulties}
              onChange={value => updateField('study_difficulties', value)}
              rows={3}
            />
            <TextAreaField
              label="最近错题 / 样本"
              value={form.latest_wrong_question}
              onChange={value => updateField('latest_wrong_question', value)}
              rows={4}
            />
          </section>

          {saveError ? (
            <p className="rounded-2xl border border-rose-300/25 bg-rose-300/10 p-3 text-xs text-rose-100">
              {saveError}
            </p>
          ) : null}
        </form>
      ) : null}
    </BiSidePanel>
  )
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="space-y-1 text-xs font-bold text-slate-300">
      {label}
      <input
        value={value}
        onChange={event => onChange(event.target.value)}
        className="h-10 w-full rounded-xl border border-white/10 bg-white/[0.06] px-2 text-sm text-slate-100 outline-none focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
      />
    </label>
  )
}

function TextAreaField({
  label,
  value,
  onChange,
  rows,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  rows: number
}) {
  return (
    <label className="space-y-1 text-xs font-bold text-slate-300">
      {label}
      <textarea
        value={value}
        onChange={event => onChange(event.target.value)}
        rows={rows}
        className="w-full resize-y rounded-xl border border-white/10 bg-white/[0.06] px-2 py-1.5 text-sm leading-6 text-slate-100 outline-none focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
      />
    </label>
  )
}

function FeedbackDetailPanel({
  item,
  onClose,
}: {
  item: FeedbackItem | null
  onClose: () => void
}) {
  return (
    <BiSidePanel
      open={Boolean(item)}
      onClose={onClose}
      title={item ? `反馈详情 · ${item.id}` : '反馈详情'}
      subtitle={item ? `${SOURCE_LABELS[item.source]} · ${STATUS_LABELS[item.status]}` : undefined}
      width="md"
    >
      {item ? (
        <div className="space-y-4 text-sm">
          <div className="rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <div className="flex flex-wrap items-center gap-2">
              <BiStatusPill tone={SOURCE_TONE[item.source]} label={SOURCE_LABELS[item.source]} />
              <BiStatusPill tone={STATUS_TONE[item.status]} label={STATUS_LABELS[item.status]} />
              <span className="text-xs font-bold text-slate-400">
                owner: {OWNER_LABELS[item.owner]}
              </span>
            </div>
            <div className="mt-3 text-base font-black text-white">{item.reason}</div>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
              {item.detail}
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <KV label="关联会员" value={item.member} />
            <KV label="评分" value={renderRating(item.rating)} />
            <KV label="创建时间" value={item.created_at} />
            <KV
              label="SLA"
              value={item.sla_target_hours > 0 ? `${item.sla_target_hours}h` : '无'}
            />
            <KV label="session_id" value={item.session_id || '—'} />
            <KV label="message_id" value={item.message_id || '—'} />
            <KV label="answer_mode" value={item.answer_mode || '—'} />
            <KV label="effective_mode" value={item.effective_response_mode || '—'} />
          </div>
          <KV label="reason_tags" value={(item.reason_tags ?? []).join(' / ') || '—'} />
          <KV label="degrade_reason" value={item.response_mode_degrade_reason || '—'} />
          <p className="rounded-2xl border border-amber-300/25 bg-amber-300/10 p-3 text-xs leading-relaxed text-amber-100">
            分诊 / 忽略会通过 feedback.ai.triage 写入 feedback_triage audit；派单与 owner 工作流仍属
            P1。
          </p>
        </div>
      ) : null}
    </BiSidePanel>
  )
}

function normalizeSource(value: string | undefined): FeedbackItem['source'] {
  const lower = (value ?? '').toLowerCase()
  if (lower.includes('invite')) return 'invite_test'
  if (lower.includes('note')) return 'member_note'
  return 'ai_message'
}

function normalizeFeedbackStatus(value: unknown): FeedbackStatus | null {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
  if (normalized === 'open' || normalized === 'triaged' || normalized === 'ignored')
    return normalized
  return null
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function stringValue(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return fallback
}

function boolValue(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'string') return ['1', 'true', 'yes', 'on'].includes(value.toLowerCase())
  return fallback
}

function emptyInviteApplicationForm(): InviteApplicationFormState {
  return {
    status: 'submitted',
    operator_note: '',
    name: '',
    phone: '',
    email: '',
    wechat_id: '',
    exam_type: '',
    exam_stage: '',
    pain_point: '',
    weekly_time: '',
    current_method: '',
    study_difficulties: '',
    latest_wrong_question: '',
    is_yousen_member: '',
    exam_date: '',
    accept_interview: false,
    province: '',
    age_range: '',
    education: '',
    occupation: '',
    preparation_years: '',
    knowledge_foundation: '',
    daily_study_time: '',
  }
}

function formFromInviteApplication(item: BiInviteTestApplication): InviteApplicationFormState {
  return {
    status: item.status || 'submitted',
    operator_note: item.operator_note || '',
    name: item.name || '',
    phone: item.phone || '',
    email: item.email || '',
    wechat_id: item.wechat_id || '',
    exam_type: item.exam_type || '',
    exam_stage: item.exam_stage || '',
    pain_point: item.pain_point || '',
    weekly_time: item.weekly_time || '',
    current_method: item.current_method || '',
    study_difficulties: item.study_difficulties || '',
    latest_wrong_question: item.latest_wrong_question || '',
    is_yousen_member: item.is_yousen_member || '',
    exam_date: item.exam_date || '',
    accept_interview: item.accept_interview,
    province: item.province || '',
    age_range: item.age_range || '',
    education: item.education || '',
    occupation: item.occupation || '',
    preparation_years: item.preparation_years || '',
    knowledge_foundation: item.knowledge_foundation || '',
    daily_study_time: item.daily_study_time || '',
  }
}

function extractInviteApplicationFromUpdate(
  data: unknown,
  fallback: BiInviteTestApplication
): BiInviteTestApplication {
  const root = asObject(data)
  const application = asObject(root.application)
  if (!Object.keys(application).length) return fallback
  return {
    ...fallback,
    id: stringValue(application.id, fallback.id),
    created_at: stringValue(application.created_at ?? application.createdAt, fallback.created_at),
    source_page: stringValue(
      application.source_page ?? application.sourcePage,
      fallback.source_page
    ),
    utm_source: stringValue(application.utm_source ?? application.utmSource, fallback.utm_source),
    utm_campaign: stringValue(
      application.utm_campaign ?? application.utmCampaign,
      fallback.utm_campaign
    ),
    name: stringValue(application.name, fallback.name),
    phone: stringValue(application.phone, fallback.phone),
    email: stringValue(application.email, fallback.email),
    province: stringValue(application.province, fallback.province),
    age_range: stringValue(application.age_range ?? application.ageRange, fallback.age_range),
    education: stringValue(application.education, fallback.education),
    occupation: stringValue(application.occupation, fallback.occupation),
    wechat_id: stringValue(application.wechat_id ?? application.wechatId, fallback.wechat_id),
    exam_type: stringValue(application.exam_type ?? application.examType, fallback.exam_type),
    exam_stage: stringValue(application.exam_stage ?? application.examStage, fallback.exam_stage),
    preparation_years: stringValue(
      application.preparation_years ?? application.preparationYears,
      fallback.preparation_years
    ),
    knowledge_foundation: stringValue(
      application.knowledge_foundation ?? application.knowledgeFoundation,
      fallback.knowledge_foundation
    ),
    pain_point: stringValue(application.pain_point ?? application.painPoint, fallback.pain_point),
    weekly_time: stringValue(
      application.weekly_time ?? application.weeklyTime,
      fallback.weekly_time
    ),
    daily_study_time: stringValue(
      application.daily_study_time ?? application.dailyStudyTime,
      fallback.daily_study_time
    ),
    current_method: stringValue(
      application.current_method ?? application.currentMethod,
      fallback.current_method
    ),
    study_difficulties: stringValue(
      application.study_difficulties ?? application.studyDifficulties,
      fallback.study_difficulties
    ),
    latest_wrong_question: stringValue(
      application.latest_wrong_question ?? application.latestWrongQuestion,
      fallback.latest_wrong_question
    ),
    is_yousen_member: stringValue(
      application.is_yousen_member ?? application.isYousenMember,
      fallback.is_yousen_member
    ),
    exam_date: stringValue(application.exam_date ?? application.examDate, fallback.exam_date),
    accept_interview: boolValue(
      application.accept_interview ?? application.acceptInterview,
      fallback.accept_interview
    ),
    consent: boolValue(application.consent, fallback.consent),
    status: stringValue(application.status, fallback.status),
    operator_note: stringValue(
      application.operator_note ?? application.operatorNote,
      fallback.operator_note
    ),
    submit_count: Number(
      application.submit_count ?? application.submitCount ?? fallback.submit_count
    ),
    contact_revealed: boolValue(
      application.contact_revealed ?? application.contactRevealed,
      fallback.contact_revealed
    ),
  }
}

function extractFeedbackTriageStatus(data: unknown): Exclude<FeedbackStatus, 'open'> | null {
  const root = asObject(data)
  const feedback = asObject(root.feedback)
  const status = normalizeFeedbackStatus(feedback.triage_status ?? feedback.triageStatus)
  return status === 'triaged' || status === 'ignored' ? status : null
}

function inferOwner(
  source: FeedbackItem['source'],
  tags: string[],
  comment: string,
  negative: boolean
): FeedbackOwner {
  const text = `${tags.join(' ')} ${comment}`.toLowerCase()
  if (source === 'invite_test') return 'growth'
  if (text.includes('价格') || text.includes('续费') || text.includes('会员')) return 'growth'
  if (text.includes('产品') || text.includes('功能') || text.includes('建议')) return 'product'
  if (negative) return 'quality'
  return 'ops'
}

function renderRating(value: number): string {
  if (value > 0) return '赞'
  if (value < 0) return '踩'
  return '中性'
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
      <div className="text-[11px] font-black uppercase text-slate-400">{label}</div>
      <div className="mt-1 break-words text-sm text-slate-100">{value || '—'}</div>
    </div>
  )
}

function ContactLine({ icon, value }: { icon: ReactNode; value: string }) {
  return (
    <span className="flex min-w-0 items-center gap-1">
      <span className="shrink-0 text-slate-400">{icon}</span>
      <span className="truncate">{value || '—'}</span>
    </span>
  )
}

function BreakdownCard({
  title,
  items,
}: {
  title: string
  items: Array<{ label: string; count: number }>
}) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-4 shadow-lg shadow-black/10">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-black text-white">{title}</h3>
        <ClipboardList className="h-4 w-4 text-cyan-300/70" aria-hidden />
      </div>
      <div className="mt-3 space-y-2">
        {items.length > 0 ? (
          items.map(item => (
            <div
              key={`${title}-${item.label}`}
              className="flex items-start justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2 text-xs"
            >
              <span className="min-w-0 text-slate-300">{item.label || 'unknown'}</span>
              <span className="font-black tabular-nums text-white">
                {formatCount(item.count)}
              </span>
            </div>
          ))
        ) : (
          <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.035] px-3 py-4 text-center text-xs text-slate-400">
            暂无数据
          </div>
        )}
      </div>
    </section>
  )
}

function InviteOpsSignal({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: string | number
  hint: string
  tone: 'slate' | 'sky' | 'amber'
}) {
  const toneClass = {
    slate: 'border-white/10 bg-white/[0.045]',
    sky: 'border-cyan-300/20 bg-cyan-300/10',
    amber: 'border-amber-300/20 bg-amber-300/10',
  }[tone]
  return (
    <div className={`rounded-3xl border px-4 py-4 shadow-lg shadow-black/10 ${toneClass}`}>
      <div className="text-[11px] font-black uppercase text-slate-400">{label}</div>
      <div className="mt-1 truncate text-2xl font-black tabular-nums text-white">
        {typeof value === 'number' ? formatCount(value) : value || '—'}
      </div>
      <div className="mt-1 truncate text-[11px] font-bold text-slate-400">{hint}</div>
    </div>
  )
}

function InvitePriorityPill({ item }: { item: BiInviteTestApplication }) {
  const priority = invitePriority(item)
  return <BiStatusPill tone={priority.tone} label={priority.label} ariaLabel={priority.hint} />
}

function invitePriority(item: BiInviteTestApplication): {
  label: string
  hint: string
  tone: BiStatusTone
} {
  const hasContact = Boolean(item.phone || item.email || item.wechat_id)
  if (!hasContact) return { label: '信息不足', hint: '缺少电话、邮箱或微信', tone: 'rose' }
  if (item.status === 'accepted') return { label: '已入选', hint: '已进入体验池', tone: 'emerald' }
  if (item.status === 'contacted') return { label: '跟进中', hint: '已联系，等待结果', tone: 'sky' }
  if (item.accept_interview) return { label: '优先回访', hint: '愿意回访且可联系', tone: 'amber' }
  if (item.latest_wrong_question) return { label: '有样本', hint: '提交了错题或样本', tone: 'sky' }
  if (item.status === 'rejected' || item.status === 'archived') {
    return { label: '低优先', hint: '已拒绝或已归档', tone: 'slate' }
  }
  return { label: '待筛选', hint: '待增长或运营判断', tone: 'slate' }
}

function inviteStatusTone(status: string | undefined): BiStatusTone {
  if (status === 'accepted') return 'emerald'
  if (status === 'contacted' || status === 'waitlisted') return 'sky'
  if (status === 'rejected' || status === 'archived') return 'slate'
  return 'amber'
}

function countPriorityInviteApplications(applications: BiInviteTestApplication[]): number {
  return applications.filter(item => {
    const hasContact = Boolean(item.phone || item.email || item.wechat_id)
    return (
      hasContact &&
      item.accept_interview &&
      ['submitted', 'waitlisted', 'contacted'].includes(item.status || 'submitted')
    )
  }).length
}

function summarizeVisibleInviteApplications(applications: BiInviteTestApplication[]) {
  const contacts = new Set<string>()
  let acceptInterviewCount = 0
  let wrongQuestionCount = 0

  for (const item of applications) {
    const contact = [item.phone, item.email, item.wechat_id]
      .map(value => value.trim().toLowerCase())
      .find(Boolean)
    if (contact) contacts.add(contact)
    if (item.accept_interview) acceptInterviewCount += 1
    if (item.latest_wrong_question.trim()) wrongQuestionCount += 1
  }

  const total = applications.length
  return {
    uniqueContacts: contacts.size,
    acceptInterviewCount,
    wrongQuestionCount,
    acceptInterviewRate: total > 0 ? acceptInterviewCount / total : undefined,
    wrongQuestionRate: total > 0 ? wrongQuestionCount / total : undefined,
  }
}

function topInviteSource(stats: BiInviteTestStats | null): string {
  const top = [...(stats?.source_breakdown ?? [])].sort((a, b) => b.count - a.count)[0]
  return top?.source_page || '—'
}

function topInvitePainPoint(stats: BiInviteTestStats | null): string {
  const top = [...(stats?.pain_point_breakdown ?? [])].sort((a, b) => b.count - a.count)[0]
  return top?.pain_point || '案例题不会写'
}

const countFormatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 })
const inviteDateFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

function formatCount(value: number | string | undefined): string {
  if (value === undefined || value === '') return '—'
  if (typeof value === 'string') return value
  if (!Number.isFinite(value)) return '—'
  return countFormatter.format(value)
}

function formatRate(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return '—'
  return `${countFormatter.format(value > 1 ? value : value * 100)}%`
}

function formatBiDate(value: string | undefined): string {
  if (!value) return '—'
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return value
  return inviteDateFormatter.format(parsed)
}

function joinNonEmpty(values: Array<string | undefined>): string {
  return values
    .map(v => (v ?? '').trim())
    .filter(Boolean)
    .join(' / ')
}

function Tile({
  label,
  value,
  hint,
  tone = 'slate',
}: {
  label: string
  value: number
  hint: string
  tone?: 'slate' | 'amber' | 'sky' | 'rose'
}) {
  const toneClass: Record<typeof tone, string> = {
    slate: 'border-white/10 bg-white/[0.045]',
    amber: 'border-amber-300/20 bg-amber-300/10',
    sky: 'border-cyan-300/20 bg-cyan-300/10',
    rose: 'border-rose-300/20 bg-rose-300/10',
  }
  return (
    <div className={`rounded-3xl border p-4 shadow-lg shadow-black/10 ${toneClass[tone]}`}>
      <div className="text-xs font-black text-slate-400">{label}</div>
      <div className="mt-1 text-3xl font-black tabular-nums text-white">{value}</div>
      <div className="mt-1 text-[11px] font-bold text-slate-400">{hint}</div>
    </div>
  )
}
