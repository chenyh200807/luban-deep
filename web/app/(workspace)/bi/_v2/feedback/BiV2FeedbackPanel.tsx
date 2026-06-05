/* eslint-disable i18n/no-literal-ui-text */
'use client'

import {
  CheckCircle2,
  ClipboardList,
  Download,
  Filter,
  Eye,
  Image as ImageIcon,
  Mail,
  MapPin,
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
  getBiLubanFeedbackResponses,
  getBiLubanFeedbackStats,
  resolveBiAttachmentUrl,
  type BiFeedbackPayload,
  type BiFeedbackRecord,
  type BiInviteTestApplication,
  type BiInviteTestStats,
  type BiLubanFeedbackResponse,
  type BiLubanFeedbackStats,
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

type FeedbackWorkspaceView = 'feedback' | 'invite-test' | 'luban-feedback'

type InviteTestFilter = {
  q: string
  status: string
  source_page: string
}

type LubanFeedbackFilter = {
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
const DEFAULT_LUBAN_FEEDBACK_FILTER: LubanFeedbackFilter = { q: '', status: '', source_page: '' }
const INVITE_TEST_WINDOW_DAYS = 365
const LUBAN_FEEDBACK_WINDOW_DAYS = 365

function readFeedbackWorkspaceView(): FeedbackWorkspaceView {
  if (typeof window === 'undefined') return 'feedback'
  const search = new URLSearchParams(window.location.search)
  const tab = search.get('tab') ?? ''
  const panel = search.get('panel') ?? search.get('feedback') ?? ''
  if (tab === 'luban-feedback' || panel === 'luban-feedback') return 'luban-feedback'
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

const LUBAN_STATUS_LABELS: Record<string, string> = {
  submitted: '待处理',
  contacted: '已联系',
  interviewed: '已回访',
  resolved: '已闭环',
  archived: '已归档',
  unknown: '未知',
}

const LUBAN_REVISIT_LABELS: Record<string, string> = {
  very_willing: '非常愿意',
  ok: '可以约',
  depends_time: '看时间',
  no: '不方便',
  unknown: '未填',
}

const LUBAN_WILL_CONTINUE_LABELS: Record<string, string> = {
  definitely: '一定会用',
  probably: '大概率用',
  depends: '看后续',
  probably_not: '可能不会',
  no: '不会再用',
  unknown: '未填',
}

const LUBAN_PAY_LABELS: Record<string, string> = {
  happy_to_pay: '愿意付费',
  if_priced_right: '价格合适会付',
  free_only: '只用免费',
  no_pay: '不会付费',
  unsure: '说不好',
  unknown: '未填',
}

const LUBAN_RECOMMEND_LABELS: Record<string, string> = {
  already_did: '已推荐',
  will: '会推荐',
  maybe: '看情况',
  wont: '暂不推荐',
  unknown: '未填',
}

const LUBAN_ATTEMPT_LABELS: Record<string, string> = {
  first: '第一次',
  second: '第二次',
  third_plus: '三次及以上',
  unknown: '未填',
}

const LUBAN_TIMEFRAME_LABELS: Record<string, string> = {
  within_1m: '1 个月内',
  '1to3m': '1-3 个月',
  '3to6m': '3-6 个月',
  over_6m: '半年以上',
  passed: '已考完',
  unknown: '未填',
}

const LUBAN_FEATURE_LABELS: Record<string, string> = {
  case_grading: '案例题 AI 阅卷官',
  error_coach: '错因驱动陪练',
  qa: 'AI 答疑',
  none_yet: '暂时没帮到',
  unknown: '未填',
}

const LUBAN_PROBLEM_LABELS: Record<string, string> = {
  slow_loading: '加载 / 等待太久',
  off_topic: '答非所问',
  grading_inaccurate: '批改不准',
  hard_to_understand: '回答太长或看不懂',
  cant_find: '入口不好找',
  miniprogram_laggy: '小程序卡顿 / 登录问题',
  none: '基本没遇到问题',
  unknown: '未填',
}

const LUBAN_WANTED_FEATURE_LABELS: Record<string, string> = {
  mock_exam: '真题 / 全真模考',
  more_cases: '更多案例题批改额度',
  concept_explain: '知识点精讲与图解',
  spec_lookup: '规范条文速查与解读',
  study_plan: '个性化学习计划',
  mistake_book: '智能错题本',
  memory_aid: '记忆 / 背诵辅助',
  video: '配套视频精讲',
  unknown: '未填',
}

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
  const [inviteExportNotice, setInviteExportNotice] = useState('')
  const [inviteExportError, setInviteExportError] = useState('')
  const [lubanFilter, setLubanFilter] = useState<LubanFeedbackFilter>(DEFAULT_LUBAN_FEEDBACK_FILTER)
  const [lubanStats, setLubanStats] = useState<BiLubanFeedbackStats | null>(null)
  const [lubanResponses, setLubanResponses] = useState<BiLubanFeedbackResponse[]>([])
  const [lubanTotal, setLubanTotal] = useState(0)
  const [lubanLoading, setLubanLoading] = useState(flagEnabled)
  const [lubanError, setLubanError] = useState('')
  const [selectedLubanFeedback, setSelectedLubanFeedback] =
    useState<BiLubanFeedbackResponse | null>(null)
  const [pendingLubanDeleteId, setPendingLubanDeleteId] = useState('')
  const [lubanExportNotice, setLubanExportNotice] = useState('')
  const [lubanExportError, setLubanExportError] = useState('')
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
  const inviteExportRequest = useAuditedAction({ actionType: 'bi.export.request' })
  const lubanFeedbackUpdate = useAuditedAction({
    actionType: 'feedback.luban_feedback.update',
  })
  const lubanExportRequest = useAuditedAction({ actionType: 'bi.export.request' })
  const triageWriting = feedbackTriage.state.phase === 'writing'
  const triageError =
    feedbackTriage.state.phase === 'denied' ? (feedbackTriage.state.result.error ?? '') : ''
  const inviteWriting = inviteApplicationUpdate.state.phase === 'writing'
  const inviteWriteError =
    inviteApplicationUpdate.state.phase === 'denied'
      ? (inviteApplicationUpdate.state.result.error ?? '')
      : ''
  const inviteDeleting = inviteApplicationDelete.state.phase === 'writing'
  const inviteExporting = inviteExportRequest.state.phase === 'writing'
  const lubanWriting = lubanFeedbackUpdate.state.phase === 'writing'
  const lubanExporting = lubanExportRequest.state.phase === 'writing'

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

  const loadLubanFeedback = useCallback(async () => {
    if (!flagEnabled) {
      setLubanStats(null)
      setLubanResponses([])
      setLubanTotal(0)
      setLubanLoading(false)
      setLubanError('')
      return
    }
    try {
      setLubanLoading(true)
      setLubanError('')
      const [stats, list] = await Promise.all([
        getBiLubanFeedbackStats({ days: LUBAN_FEEDBACK_WINDOW_DAYS }),
        getBiLubanFeedbackResponses({
          days: LUBAN_FEEDBACK_WINDOW_DAYS,
          limit: 100,
          q: lubanFilter.q.trim() || undefined,
          status: lubanFilter.status || undefined,
          source_page: lubanFilter.source_page.trim() || undefined,
        }),
      ])
      setLubanStats(stats)
      setLubanResponses(list.items)
      setLubanTotal(list.total)
    } catch (err) {
      setLubanStats(null)
      setLubanResponses([])
      setLubanTotal(0)
      setLubanError(err instanceof Error ? err.message : '内测回访加载失败')
    } finally {
      setLubanLoading(false)
    }
  }, [flagEnabled, lubanFilter.q, lubanFilter.source_page, lubanFilter.status])

  useEffect(() => {
    void loadFeedback()
  }, [loadFeedback])

  useEffect(() => {
    void loadInviteTest()
  }, [loadInviteTest])

  useEffect(() => {
    void loadLubanFeedback()
  }, [loadLubanFeedback])

  function switchWorkspaceView(next: FeedbackWorkspaceView) {
    setWorkspaceView(next)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      url.searchParams.set('tab', 'feedback')
      if (next === 'feedback') url.searchParams.delete('panel')
      else url.searchParams.set('panel', next)
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
        label: '定位 / 内容',
        render: i => (
          <div className="min-w-0">
            <div className="truncate text-slate-100">{i.reason}</div>
            <div className="truncate text-[11px] text-slate-400">
              {i.detail}
              {i.attachment_count ? ` · ${i.attachment_count} 个截图/录屏` : ''}
            </div>
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

  async function handleInviteApplicationExport() {
    if (!flagEnabled || inviteExporting) return
    setInviteExportError('')
    setInviteExportNotice('')
    let exportRows: BiInviteTestApplication[] = []
    let exportTotal = 0
    try {
      const exportPayload = await getBiInviteTestApplications({
        days: INVITE_TEST_WINDOW_DAYS,
        limit: 500,
        q: inviteFilter.q.trim() || undefined,
        status: inviteFilter.status || undefined,
        source_page: inviteFilter.source_page.trim() || undefined,
      })
      exportRows = exportPayload.items
      exportTotal = exportPayload.total
    } catch (err) {
      setInviteExportError(err instanceof Error ? err.message : '导出数据拉取失败')
      return
    }
    const result = await inviteExportRequest.execute({
      key: 'bi.export.request',
      params: {},
      body: {
        dataset: 'invite_test_applications',
        format: 'csv',
        filters: {
          days: INVITE_TEST_WINDOW_DAYS,
          q: inviteFilter.q.trim(),
          status: inviteFilter.status,
          source_page: inviteFilter.source_page.trim(),
          visible_rows: exportRows.length,
          total: exportTotal,
        },
      },
    })
    if (!result.ok) {
      setInviteExportError(result.error || '导出审计写入失败')
      return
    }
    const content = buildInviteApplicationCsv(exportRows)
    const notice =
      exportTotal > exportRows.length
        ? `已导出当前筛选前 ${exportRows.length} / ${exportTotal} 条；后端单次导出上限 500，审计 ${result.auditId || '已写入'}`
        : `已导出当前筛选全部 ${exportRows.length} 条；审计 ${result.auditId || '已写入'}`
    setInviteExportNotice(notice)
    try {
      downloadCsv(
        `invite-test-applications-${new Date().toISOString().slice(0, 10)}.csv`,
        content
      )
    } catch (err) {
      setInviteExportError(err instanceof Error ? err.message : 'CSV 下载启动失败')
    }
  }

  async function handleLubanFeedbackDelete(item: BiLubanFeedbackResponse) {
    if (!flagEnabled || lubanWriting || !item.id || item.status === 'archived') return
    if (pendingLubanDeleteId !== item.id) {
      setPendingLubanDeleteId(item.id)
      return
    }
    setPendingLubanDeleteId('')
    setLubanError('')
    const result = await lubanFeedbackUpdate.execute({
      key: 'feedback.luban_feedback.update',
      params: { response_id: item.id },
      body: {
        status: 'archived',
        operator_note: item.operator_note || 'BI 删除：已归档隐藏',
      },
    })
    if (!result.ok) {
      setLubanError(result.error || '删除内测回访失败')
      return
    }
    const updated = extractLubanFeedbackFromUpdate(result.data, item)
    if (lubanFilter.status === 'archived') {
      setLubanResponses(prev =>
        prev.map(candidate => (candidate.id === item.id ? updated : candidate))
      )
    } else {
      setLubanResponses(prev => prev.filter(candidate => candidate.id !== item.id))
      setLubanTotal(prev => Math.max(0, prev - 1))
    }
    if (selectedLubanFeedback?.id === item.id) setSelectedLubanFeedback(null)
    void loadLubanFeedback()
  }

  async function handleLubanFeedbackExport() {
    if (!flagEnabled || lubanExporting) return
    setLubanExportError('')
    setLubanExportNotice('')
    let exportRows: BiLubanFeedbackResponse[] = []
    let exportTotal = 0
    try {
      const exportPayload = await getBiLubanFeedbackResponses({
        days: LUBAN_FEEDBACK_WINDOW_DAYS,
        limit: 500,
        q: lubanFilter.q.trim() || undefined,
        status: lubanFilter.status || undefined,
        source_page: lubanFilter.source_page.trim() || undefined,
      })
      exportRows = exportPayload.items
      exportTotal = exportPayload.total
    } catch (err) {
      setLubanExportError(err instanceof Error ? err.message : '导出数据拉取失败')
      return
    }
    const result = await lubanExportRequest.execute({
      key: 'bi.export.request',
      params: {},
      body: {
        dataset: 'luban_feedback',
        format: 'csv',
        filters: {
          days: LUBAN_FEEDBACK_WINDOW_DAYS,
          q: lubanFilter.q.trim(),
          status: lubanFilter.status,
          source_page: lubanFilter.source_page.trim(),
          visible_rows: exportRows.length,
          total: exportTotal,
        },
      },
    })
    if (!result.ok) {
      setLubanExportError(result.error || '导出审计写入失败')
      return
    }
    const content = buildLubanFeedbackCsv(exportRows)
    const notice =
      exportTotal > exportRows.length
        ? `已导出当前筛选前 ${exportRows.length} / ${exportTotal} 条；后端单次导出上限 500，审计 ${result.auditId || '已写入'}`
        : `已导出当前筛选全部 ${exportRows.length} 条；审计 ${result.auditId || '已写入'}`
    setLubanExportNotice(notice)
    try {
      downloadCsv(`luban-feedback-${new Date().toISOString().slice(0, 10)}.csv`, content)
    } catch (err) {
      setLubanExportError(err instanceof Error ? err.message : 'CSV 下载启动失败')
    }
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
                void loadLubanFeedback()
              }}
              disabled={loading || inviteLoading || lubanLoading}
              variant="primary"
              size="xs"
              aria-label="刷新反馈中心"
            >
              <RefreshCw
                className={`h-3 w-3 ${
                  loading || inviteLoading || lubanLoading ? 'animate-spin' : ''
                }`}
                aria-hidden
              />
              刷新
            </BiButton>
          }
        >
          反馈中心已接入真实读模型 · AI 消息反馈 / 内测申请 / 内测回访分区管理
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
        lubanCount={lubanStats?.summary.total_responses ?? lubanTotal}
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
      ) : workspaceView === 'invite-test' ? (
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
          onExport={() => void handleInviteApplicationExport()}
          exporting={inviteExporting}
          exportNotice={inviteExportNotice}
          exportError={inviteExportError}
        />
      ) : (
        <LubanFeedbackPanel
          stats={lubanStats}
          responses={lubanResponses}
          total={lubanTotal}
          loading={lubanLoading}
          error={lubanError}
          filters={lubanFilter}
          onFilterChange={(field, value) => setLubanFilter(prev => ({ ...prev, [field]: value }))}
          onRefresh={() => void loadLubanFeedback()}
          onOpenResponse={setSelectedLubanFeedback}
          onDeleteResponse={handleLubanFeedbackDelete}
          deleting={lubanWriting}
          pendingDeleteId={pendingLubanDeleteId}
          onExport={() => void handleLubanFeedbackExport()}
          exporting={lubanExporting}
          exportNotice={lubanExportNotice}
          exportError={lubanExportError}
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
      <LubanFeedbackDetailPanel
        key={
          selectedLubanFeedback
            ? `${selectedLubanFeedback.id}:${selectedLubanFeedback.status}:${selectedLubanFeedback.operator_note}`
            : 'luban-feedback-empty'
        }
        item={selectedLubanFeedback}
        onClose={() => setSelectedLubanFeedback(null)}
        onDelete={handleLubanFeedbackDelete}
        deleting={lubanWriting}
        pendingDeleteId={pendingLubanDeleteId}
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
  const problemLabel = feedbackProblemLabel(record.problem_type)
  const symptomLabels = (record.symptom_tags ?? []).map(feedbackSymptomLabel).filter(Boolean)
  const attachmentCount = record.attachment_count ?? record.attachments?.length ?? 0
  return {
    id:
      record.feedback_id ||
      record.id ||
      record.message_id ||
      `${record.session_id || 'feedback'}-${record.created_at || index}`,
    source,
    rating,
    reason:
      [problemLabel, symptomLabels.slice(0, 2).join(' / ')].filter(Boolean).join(' · ') ||
      (tags.length > 0 ? tags.join(' / ') : renderRating(rating)),
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
    problem_type: record.problem_type,
    symptom_tags: record.symptom_tags,
    attachment_count: attachmentCount,
    attachments: record.attachments,
    context_snapshot: record.context_snapshot,
    status: triageStatus ?? (negative || comment ? 'open' : positive ? 'ignored' : 'triaged'),
    owner: inferOwner(source, [...tags, record.problem_type ?? '', ...(record.symptom_tags ?? [])], comment, negative),
    created_at: record.created_at || '—',
    sla_target_hours: negative ? 24 : comment ? 72 : 0,
  }
}

function FeedbackWorkspaceSwitcher({
  current,
  feedbackCount,
  inviteCount,
  lubanCount,
  onSelect,
}: {
  current: FeedbackWorkspaceView
  feedbackCount: number
  inviteCount: number
  lubanCount: number
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
    {
      key: 'luban-feedback',
      label: '内测回访',
      count: lubanCount,
      hint: 'NPS / 满意度 / 回访线索',
    },
  ]
  return (
    <div
      className="grid grid-cols-1 gap-2 rounded-2xl border border-white/10 bg-white/[0.04] p-1.5 shadow-lg shadow-black/10 md:grid-cols-3"
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
  onExport,
  exporting,
  exportNotice,
  exportError,
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
  onExport: () => void
  exporting: boolean
  exportNotice: string
  exportError: string
}) {
  const priorityCount = countPriorityInviteApplications(applications)
  const currentStats = summarizeVisibleInviteApplications(applications)
  const profileTotal = stats?.summary.total_applications ?? total

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
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={onExport}
                  disabled={exporting || total === 0}
                  className="inline-flex h-11 items-center justify-center gap-1.5 rounded-2xl border border-emerald-300/25 bg-emerald-300/12 px-3 text-xs font-black text-emerald-100 hover:bg-emerald-300/18 disabled:opacity-50"
                  aria-label="导出内测申请"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden />
                  {exporting ? '审计中…' : '导出 CSV'}
                </button>
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
            {exportError ? (
              <p className="mt-3 rounded-2xl border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-xs text-rose-100">
                {exportError}
              </p>
            ) : null}
            {exportNotice ? (
              <p className="mt-3 rounded-2xl border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-xs text-emerald-100">
                {exportNotice}
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

      <section
        className="rounded-3xl border border-white/10 bg-white/[0.04] p-4 shadow-lg shadow-black/10"
        aria-label="内测申请画像汇总"
      >
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h3 className="text-lg font-black text-white">申请画像汇总</h3>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              以服务端 stats 为准，汇总年龄、地区、备考阶段、学习时间和痛点；当前列表筛选不改写画像 authority。
            </p>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2 text-right text-xs">
            <div className="font-black tabular-nums text-white">{formatCount(profileTotal)}</div>
            <div className="mt-0.5 text-slate-400">画像样本</div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(280px,0.82fr)_minmax(0,1.18fr)]">
          <AgeCompositionCard
            title="年龄占比"
            total={profileTotal}
            items={(stats?.age_range_breakdown ?? []).slice(0, 6).map(item => ({
              label: item.age_range,
              count: item.count,
            }))}
          />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <BreakdownCard
              title="最想解决的问题"
              total={profileTotal}
              items={(stats?.pain_point_breakdown ?? []).slice(0, 6).map(item => ({
                label: item.pain_point,
                count: item.count,
              }))}
            />
            <BreakdownCard
              title="备考阶段"
              total={profileTotal}
              items={(stats?.exam_stage_breakdown ?? []).slice(0, 6).map(item => ({
                label: item.exam_stage,
                count: item.count,
              }))}
            />
          </div>
        </div>

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <BreakdownCard
            title="考试类型"
            total={profileTotal}
            items={(stats?.exam_type_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.exam_type,
              count: item.count,
            }))}
          />
          <BreakdownCard
            title="省份"
            total={profileTotal}
            items={(stats?.province_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.province,
              count: item.count,
            }))}
          />
          <BreakdownCard
            title="学历"
            total={profileTotal}
            items={(stats?.education_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.education,
              count: item.count,
            }))}
          />
          <BreakdownCard
            title="职业"
            total={profileTotal}
            items={(stats?.occupation_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.occupation,
              count: item.count,
            }))}
          />
          <BreakdownCard
            title="每周学习时间"
            total={profileTotal}
            items={(stats?.weekly_time_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.weekly_time,
              count: item.count,
            }))}
          />
          <BreakdownCard
            title="每日学习时间"
            total={profileTotal}
            items={(stats?.daily_study_time_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.daily_study_time,
              count: item.count,
            }))}
          />
          <BreakdownCard
            title="备考年限"
            total={profileTotal}
            items={(stats?.preparation_years_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.preparation_years,
              count: item.count,
            }))}
          />
          <BreakdownCard
            title="知识基础"
            total={profileTotal}
            items={(stats?.knowledge_foundation_breakdown ?? []).slice(0, 5).map(item => ({
              label: item.knowledge_foundation,
              count: item.count,
            }))}
          />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <BreakdownCard
          title="来源页"
          total={profileTotal}
          items={(stats?.source_breakdown ?? []).slice(0, 5).map(item => ({
            label: item.source_page,
            count: item.count,
          }))}
        />
        <BreakdownCard
          title="状态"
          total={profileTotal}
          items={(stats?.status_breakdown ?? []).slice(0, 5).map(item => ({
            label: item.status,
            count: item.count,
          }))}
        />
      </div>
    </div>
  )
}

function LubanFeedbackPanel({
  stats,
  responses,
  total,
  loading,
  error,
  filters,
  onFilterChange,
  onRefresh,
  onOpenResponse,
  onDeleteResponse,
  deleting,
  pendingDeleteId,
  onExport,
  exporting,
  exportNotice,
  exportError,
}: {
  stats: BiLubanFeedbackStats | null
  responses: BiLubanFeedbackResponse[]
  total: number
  loading: boolean
  error: string
  filters: LubanFeedbackFilter
  onFilterChange: (field: keyof LubanFeedbackFilter, value: string) => void
  onRefresh: () => void
  onOpenResponse: (item: BiLubanFeedbackResponse) => void
  onDeleteResponse: (item: BiLubanFeedbackResponse) => void
  deleting: boolean
  pendingDeleteId: string
  onExport: () => void
  exporting: boolean
  exportNotice: string
  exportError: string
}) {
  const summary = stats?.summary
  const highIntentCount = responses.filter(item =>
    ['very_willing', 'ok'].includes(item.revisit_willingness)
  ).length
  const contactCount = responses.filter(item => item.phone || item.wechat_id).length
  const topSource = stats?.source_breakdown?.[0]?.source_page || '—'

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl border border-emerald-300/20 bg-gradient-to-br from-emerald-300/12 via-cyan-300/8 to-white/[0.035] p-5 shadow-xl shadow-black/20">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2.5 py-1 text-[11px] font-black text-emerald-100">
              <ClipboardList className="h-3 w-3" aria-hidden />
              来自 luban-survey
            </div>
            <h3 className="mt-2 text-2xl font-black text-white">内测回访池</h3>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-300">
              authority: <code className="font-mono">public.luban_feedback</code> · 展示
              <code className="mx-1 font-mono">/luban-survey/index.html</code>
              提交后的 NPS、满意度、痛点、建议和可回访联系方式。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onExport}
              disabled={exporting || responses.length === 0}
              className="inline-flex h-11 items-center justify-center gap-1.5 rounded-2xl border border-emerald-300/25 bg-emerald-300/12 px-3 text-xs font-black text-emerald-100 hover:bg-emerald-300/18 disabled:opacity-50"
              aria-label="导出内测回访"
            >
              <Download className="h-3.5 w-3.5" aria-hidden />
              {exporting ? '审计中…' : '导出 CSV'}
            </button>
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              className="inline-flex h-11 items-center justify-center gap-1.5 rounded-2xl border border-white/10 bg-white/[0.06] px-3 text-xs font-bold text-slate-100 hover:bg-white/10 disabled:opacity-50"
              aria-label="刷新内测回访"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} aria-hidden />
              刷新
            </button>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-5">
          <Tile
            label="回访总数"
            value={summary?.total_responses ?? total}
            hint={`近 ${LUBAN_FEEDBACK_WINDOW_DAYS}d`}
          />
          <Tile
            label="NPS"
            value={summary?.nps_score ?? 0}
            tone={(summary?.nps_score ?? 0) >= 0 ? 'sky' : 'rose'}
            hint={summary ? `推荐 ${summary.promoters} / 贬损 ${summary.detractors}` : '等待数据'}
          />
          <Tile
            label="平均满意度"
            value={summary?.avg_satisfaction ?? 0}
            tone="amber"
            hint={summary ? `${summary.satisfaction_base} 份评分` : '1-5 分'}
          />
          <Tile label="高意向回访" value={highIntentCount} tone="sky" hint="非常愿意 / 可以约" />
          <Tile label="可联系" value={contactCount} tone="amber" hint={`主来源 ${topSource}`} />
        </div>
      </section>

      <section className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.04] shadow-xl shadow-black/20">
        <div className="border-b border-white/10 p-4">
          <div className="grid grid-cols-1 gap-2 rounded-2xl border border-white/10 bg-white/[0.035] p-2 lg:grid-cols-[minmax(0,1fr)_150px_150px_auto]">
            <label className="relative">
              <Search
                className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                aria-hidden
              />
              <input
                value={filters.q}
                onChange={event => onFilterChange('q', event.target.value)}
                placeholder="搜索痛点 / 建议 / 微信 / 手机 / 一句话"
                className="h-11 w-full rounded-xl border border-white/10 bg-white/[0.06] px-9 text-xs text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
                aria-label="搜索内测回访"
              />
            </label>
            <BiSelect
              value={filters.status}
              onChange={event => onFilterChange('status', event.target.value)}
              className="h-11"
              aria-label="按内测回访状态筛选"
            >
              <option value="">全部状态</option>
              <option value="submitted">待处理</option>
              <option value="contacted">已联系</option>
              <option value="interviewed">已回访</option>
              <option value="resolved">已闭环</option>
              <option value="archived">已归档</option>
            </BiSelect>
            <input
              value={filters.source_page}
              onChange={event => onFilterChange('source_page', event.target.value)}
              placeholder="来源页"
              className="h-11 rounded-xl border border-white/10 bg-white/[0.06] px-3 text-xs text-slate-100 outline-none placeholder:text-slate-500 focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
              aria-label="按来源页筛选内测回访"
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
          {exportError ? (
            <p className="mt-3 rounded-2xl border border-rose-300/25 bg-rose-300/10 px-3 py-2 text-xs text-rose-100">
              {exportError}
            </p>
          ) : null}
          {exportNotice ? (
            <p className="mt-3 rounded-2xl border border-emerald-300/25 bg-emerald-300/10 px-3 py-2 text-xs text-emerald-100">
              {exportNotice}
            </p>
          ) : null}
        </div>

        <div className="grid gap-3 p-4">
          {loading ? (
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-10 text-center text-sm text-slate-400">
              正在加载内测回访…
            </div>
          ) : null}
          {!loading && !error && responses.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.035] px-4 py-10 text-center">
              <div className="font-bold text-slate-100">暂无内测回访</div>
              <div className="mt-1 text-xs text-slate-400">
                当前筛选下没有问卷记录，或 luban_feedback 存储暂未返回数据。
              </div>
            </div>
          ) : null}
          {!loading && !error
            ? responses.map(item => (
                <LubanFeedbackCard
                  key={item.id}
                  item={item}
                  onOpen={onOpenResponse}
                  onDelete={onDeleteResponse}
                  deleting={deleting}
                  pendingDeleteId={pendingDeleteId}
                />
              ))
            : null}
        </div>
        <div className="flex flex-wrap justify-between gap-2 border-t border-white/10 px-4 py-3 text-[11px] font-bold text-slate-400">
          <span>
            显示 {responses.length} / {total}
          </span>
          <span>服务端返回前 {responses.length} / {total}</span>
        </div>
      </section>
    </div>
  )
}

function LubanFeedbackCard({
  item,
  onOpen,
  onDelete,
  deleting,
  pendingDeleteId,
}: {
  item: BiLubanFeedbackResponse
  onOpen: (item: BiLubanFeedbackResponse) => void
  onDelete: (item: BiLubanFeedbackResponse) => void
  deleting: boolean
  pendingDeleteId: string
}) {
  const contact = joinNonEmpty([
    item.wechat_id ? `微信 ${item.wechat_id}` : '',
    item.phone ? `手机 ${item.phone}` : '',
  ])
  const npsTone =
    item.nps === null
      ? 'text-slate-400'
      : item.nps >= 9
        ? 'text-emerald-200'
        : item.nps <= 6
          ? 'text-rose-200'
          : 'text-amber-200'
  return (
    <article className="grid gap-3 rounded-2xl border border-white/10 bg-white/[0.045] p-4 transition hover:border-emerald-300/25 hover:bg-emerald-300/[0.06] lg:grid-cols-[88px_minmax(0,1fr)_260px]">
      <div>
        <div className={`text-4xl font-black tabular-nums ${npsTone}`}>
          {item.nps === null ? '—' : item.nps}
        </div>
        <div className="mt-1 text-[11px] font-bold text-slate-400">
          满意度 {item.overall_satisfaction ?? '—'}/5
        </div>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <BiStatusPill tone={lubanStatusTone(item.status)} label={lubanLabel(LUBAN_STATUS_LABELS, item.status)} />
          <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[11px] font-bold text-slate-300">
            继续：{lubanLabel(LUBAN_WILL_CONTINUE_LABELS, item.will_continue)}
          </span>
          <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-0.5 text-[11px] font-bold text-slate-300">
            回访：{lubanLabel(LUBAN_REVISIT_LABELS, item.revisit_willingness)}
          </span>
        </div>
        {item.unsolved_pain ? (
          <p className="mt-2 text-sm font-bold leading-6 text-slate-100">痛点：{item.unsolved_pain}</p>
        ) : null}
        {item.top_suggestion ? (
          <p className="mt-1 text-sm leading-6 text-slate-300">建议：{item.top_suggestion}</p>
        ) : null}
        {item.one_word ? (
          <p className="mt-1 text-xs italic text-slate-400">“{item.one_word}”</p>
        ) : null}
        <div className="mt-3 grid gap-2 text-[11px] leading-5 text-slate-400 md:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-white/[0.035] px-2.5 py-2">
            <span className="font-black text-slate-200">功能评分：</span>
            案例 {item.feat_case_grading || '—'} · 错因 {item.feat_error_coach || '—'} · 答疑{' '}
            {item.feat_qa || '—'}
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.035] px-2.5 py-2">
            <span className="font-black text-slate-200">体验：</span>
            上手 {item.ease_of_use || '—'} · 准确 {item.accuracy || '—'} · 速度 {item.speed || '—'}
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.035] px-2.5 py-2 md:col-span-2">
            <span className="font-black text-slate-200">遇到问题：</span>
            {formatLubanList(item.problems, LUBAN_PROBLEM_LABELS, item.problems_other)}
          </div>
        </div>
      </div>
      <div className="text-xs leading-5 text-slate-400 lg:text-right">
        <div className="font-bold text-slate-200">{contact || '未留联系方式'}</div>
        <div className="mt-1">{joinNonEmpty([item.attempt_count, item.exam_timeframe]) || '未填写考试背景'}</div>
        <div>{item.source_page || 'unknown-source'}</div>
        <div>{formatBiDate(item.created_at)}</div>
        {item.operator_note ? (
          <div className="mt-2 rounded-xl border border-white/10 bg-white/[0.04] px-2 py-1 text-left text-slate-300 lg:text-right">
            备注：{item.operator_note}
          </div>
        ) : null}
        <button
          type="button"
          onClick={() => onOpen(item)}
          className="mt-3 inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-cyan-300/25 bg-cyan-300/10 px-3 text-[11px] font-black text-cyan-100 hover:bg-cyan-300/16"
          aria-label={`查看内测回访 ${item.id} 完整反馈`}
        >
          <Eye className="h-3 w-3" aria-hidden />
          查看完整反馈
        </button>
        <button
          type="button"
          onClick={() => onDelete(item)}
          disabled={deleting || item.status === 'archived'}
          className="ml-2 mt-3 inline-flex h-9 items-center justify-center gap-1.5 rounded-xl border border-rose-300/25 bg-rose-300/10 px-3 text-[11px] font-black text-rose-100 hover:bg-rose-300/16 disabled:opacity-45"
          aria-label={`删除内测回访 ${item.id}`}
          title="删除会归档隐藏并写入 audit；不会物理删除原始问卷"
        >
          <Trash2 className="h-3 w-3" aria-hidden />
          {pendingDeleteId === item.id ? '确认删除' : '删除'}
        </button>
      </div>
    </article>
  )
}

function LubanFeedbackDetailPanel({
  item,
  onClose,
  onDelete,
  deleting,
  pendingDeleteId,
}: {
  item: BiLubanFeedbackResponse | null
  onClose: () => void
  onDelete: (item: BiLubanFeedbackResponse) => void
  deleting: boolean
  pendingDeleteId: string
}) {
  return (
    <BiSidePanel
      open={Boolean(item)}
      onClose={onClose}
      title={item ? `内测回访详情 · NPS ${item.nps ?? '—'}` : '内测回访详情'}
      subtitle={
        item
          ? `${lubanLabel(LUBAN_STATUS_LABELS, item.status)} · ${formatBiDate(item.created_at)} · 只读完整问卷`
          : undefined
      }
      width="lg"
      footer={
        item ? (
          <div className="flex items-center justify-end gap-2">
            <BiButton
              onClick={() => onDelete(item)}
              disabled={deleting || item.status === 'archived'}
              variant="secondary"
              size="sm"
              title="删除会归档隐藏并写入 audit；不会物理删除原始问卷"
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden />
              {pendingDeleteId === item.id ? '确认删除' : '删除'}
            </BiButton>
            <BiButton onClick={onClose} variant="secondary" size="sm">
              关闭
            </BiButton>
          </div>
        ) : undefined
      }
    >
      {item ? (
        <div className="space-y-4 text-sm">
          <section className="rounded-3xl border border-cyan-300/25 bg-cyan-300/10 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <BiStatusPill tone={lubanStatusTone(item.status)} label={lubanLabel(LUBAN_STATUS_LABELS, item.status)} />
              <BiStatusPill
                tone={item.revisit_willingness === 'very_willing' ? 'emerald' : 'slate'}
                label={`回访：${lubanLabel(LUBAN_REVISIT_LABELS, item.revisit_willingness)}`}
              />
              <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-1 text-xs font-bold text-slate-300">
                满意度 {item.overall_satisfaction ?? '—'}/5
              </span>
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-300">
              原始问卷答案保持只读，避免污染真实用户提交；当前仅保留删除/归档动作。
            </p>
          </section>

          <div className="grid gap-3 md:grid-cols-2">
            <Field label="NPS">{item.nps ?? '—'}</Field>
            <Field label="继续使用">{lubanLabel(LUBAN_WILL_CONTINUE_LABELS, item.will_continue)}</Field>
            <Field label="回访意愿">{lubanLabel(LUBAN_REVISIT_LABELS, item.revisit_willingness)}</Field>
            <Field label="联系方式">{joinNonEmpty([item.wechat_id, item.phone]) || '未留'}</Field>
          </div>

          <section className="space-y-3 rounded-3xl border border-white/10 bg-white/[0.045] p-4 shadow-lg shadow-black/10">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-xs font-black uppercase text-cyan-200">完整问卷反馈</h3>
              <span className="rounded-full border border-white/10 bg-white/[0.05] px-2 py-1 text-[11px] font-bold text-slate-400">
                只读 · 来自用户原始提交
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="考试次数">{lubanLabel(LUBAN_ATTEMPT_LABELS, item.attempt_count)}</Field>
              <Field label="考试时间">{lubanLabel(LUBAN_TIMEFRAME_LABELS, item.exam_timeframe)}</Field>
              <Field label="最有价值功能">{lubanLabel(LUBAN_FEATURE_LABELS, item.most_valuable)}</Field>
              <Field label="付费意愿">{lubanLabel(LUBAN_PAY_LABELS, item.pay_willingness)}</Field>
              <Field label="主动推荐">{lubanLabel(LUBAN_RECOMMEND_LABELS, item.would_recommend)}</Field>
              <Field label="来源页">{item.source_page || '—'}</Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="案例题阅卷">{item.feat_case_grading || '—'}</Field>
              <Field label="错因陪练">{item.feat_error_coach || '—'}</Field>
              <Field label="AI 答疑">{item.feat_qa || '—'}</Field>
              <Field label="上手难易">{item.ease_of_use || '—'}</Field>
              <Field label="准确度">{item.accuracy || '—'}</Field>
              <Field label="响应速度">{item.speed || '—'}</Field>
            </div>
            <ReadonlyBlock label="一句话评价" value={item.one_word} />
            <ReadonlyBlock
              label="遇到的问题"
              value={formatLubanList(item.problems, LUBAN_PROBLEM_LABELS, item.problems_other)}
            />
            <ReadonlyBlock label="未解决痛点" value={item.unsolved_pain} />
            <ReadonlyBlock
              label="希望增加能力"
              value={formatLubanList(
                item.wanted_features,
                LUBAN_WANTED_FEATURE_LABELS,
                item.wanted_features_other
              )}
            />
            <ReadonlyBlock label="最重要建议" value={item.top_suggestion} />
          </section>
        </div>
      ) : null}
    </BiSidePanel>
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2">
      <div className="text-[11px] font-black text-slate-500">{label}</div>
      <div className="mt-1 break-words text-sm font-bold text-slate-100">{children ?? '—'}</div>
    </div>
  )
}

function ReadonlyBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2">
      <div className="text-[11px] font-black text-slate-500">{label}</div>
      <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-slate-200">
        {value || '未填写'}
      </p>
    </div>
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
          <section className="rounded-3xl border border-cyan-300/20 bg-cyan-300/10 p-4">
            <div className="flex items-center gap-2 text-xs font-black text-cyan-100">
              <MapPin className="h-4 w-4" aria-hidden />
              小程序问题定位
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="rounded-xl border border-white/10 bg-white/10 px-2.5 py-1 text-xs font-bold text-white">
                {feedbackProblemLabel(item.problem_type) || '未选择模块'}
              </span>
              {(item.symptom_tags ?? []).length > 0 ? (
                item.symptom_tags?.map(tag => (
                  <span
                    key={tag}
                    className="rounded-xl border border-white/10 bg-slate-950/30 px-2.5 py-1 text-xs text-slate-200"
                  >
                    {feedbackSymptomLabel(tag)}
                  </span>
                ))
              ) : (
                <span className="rounded-xl border border-white/10 bg-slate-950/30 px-2.5 py-1 text-xs text-slate-400">
                  未选择具体现象
                </span>
              )}
            </div>
            <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-slate-300 sm:grid-cols-2">
              <span>页面：{item.context_snapshot?.route || '—'}</span>
              <span>网络：{item.context_snapshot?.network_type || '—'}</span>
              <span>设备：{item.context_snapshot?.device_model || '—'}</span>
              <span>系统：{item.context_snapshot?.system || item.context_snapshot?.platform || '—'}</span>
            </div>
          </section>
          <FeedbackAttachmentGrid attachments={item.attachments ?? []} />
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

function FeedbackAttachmentGrid({ attachments }: { attachments: NonNullable<FeedbackItem['attachments']> }) {
  if (attachments.length === 0) {
    return (
      <section className="rounded-3xl border border-white/10 bg-white/[0.035] p-4 text-xs text-slate-400">
        <div className="flex items-center gap-2 font-black text-slate-200">
          <ImageIcon className="h-4 w-4" aria-hidden />
          截图 / 录屏
        </div>
        <p className="mt-2">这条反馈没有可查看附件。</p>
      </section>
    )
  }
  return (
    <section className="rounded-3xl border border-emerald-300/20 bg-emerald-300/10 p-4">
      <div className="flex items-center gap-2 text-xs font-black text-emerald-100">
        <ImageIcon className="h-4 w-4" aria-hidden />
        截图 / 录屏 · {attachments.length}
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {attachments.map((attachment, index) => {
          const href = resolveFeedbackAttachmentUrl(attachment.url)
          const isImage =
            (attachment.kind || '').toLowerCase() === 'image' ||
            (attachment.mime_type || '').startsWith('image/')
          return (
            <a
              key={attachment.id || attachment.url || index}
              href={href || undefined}
              target="_blank"
              rel="noreferrer"
              aria-label={`查看反馈附件 ${attachment.filename || index + 1}`}
              className="group overflow-hidden rounded-2xl border border-white/10 bg-slate-950/35 text-left transition hover:border-emerald-200/40 hover:bg-emerald-300/10"
            >
              <div className="grid aspect-[4/3] place-items-center bg-slate-950/50">
                {href && isImage ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={href}
                    alt={attachment.filename || '反馈截图'}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex flex-col items-center gap-2 text-slate-300">
                    <ImageIcon className="h-7 w-7" aria-hidden />
                    <span className="text-xs font-bold">
                      {(attachment.kind || '附件').toUpperCase()}
                    </span>
                  </div>
                )}
              </div>
              <div className="space-y-1 p-3">
                <div className="truncate text-xs font-black text-white">
                  {attachment.filename || attachment.id || '未命名附件'}
                </div>
                <div className="text-[11px] text-slate-400">
                  {formatAttachmentSize(attachment.size)} · {href ? '可打开' : '缺少可访问 URL'}
                </div>
              </div>
            </a>
          )
        })}
      </div>
    </section>
  )
}

function resolveFeedbackAttachmentUrl(url: string | undefined): string {
  return resolveBiAttachmentUrl(url)
}

function formatAttachmentSize(value: number | undefined): string {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '未知大小'
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

function feedbackProblemLabel(value: string | undefined): string {
  const labels: Record<string, string> = {
    chat: '对话答疑',
    learning_report: '学情模块',
    assessment: '摸底测试',
    diagnostic_report: '摸底报告',
    history: '历史记录',
    billing: '会员额度',
    profile: '我的/登录',
    content: '题目/答案',
    system: '系统问题',
  }
  return labels[(value ?? '').trim()] ?? (value ?? '').trim()
}

function feedbackSymptomLabel(value: string | undefined): string {
  const labels: Record<string, string> = {
    no_response: '没有回复',
    stream_stuck: '回复卡住',
    answer_quality: '答非所问',
    format_broken: '排版错乱',
    copy_failed: '复制失败',
    data_wrong: '数据不对',
    missing_evidence: '证据缺失',
    prescription_wrong: '今日处方不准',
    trend_wrong: '掌握趋势异常',
    card_tap_failed: '卡片点不开',
    question_wrong: '题目不合适',
    submit_failed: '提交失败',
    result_missing: '结果没生成',
    timer_problem: '计时异常',
    page_stuck: '页面卡住',
    conclusion_wrong: '结论不准',
    weakness_wrong: '薄弱点不准',
    reason_unclear: '依据不清',
    report_missing: '报告丢失',
    layout_broken: '展示错乱',
    record_missing: '记录丢失',
    record_open_failed: '打不开',
    sync_delay: '同步延迟',
    wrong_order: '顺序不对',
    delete_failed: '删除失败',
    balance_wrong: '余额不对',
    pay_failed: '支付失败',
    benefit_missing: '权益没到账',
    order_missing: '订单缺失',
    quota_wrong: '扣费异常',
    login_failed: '登录异常',
    profile_save_failed: '资料保存失败',
    feedback_failed: '反馈提交失败',
    navigation_wrong: '入口跳错',
    avatar_failed: '头像失败',
    answer_wrong: '答案错误',
    explanation_wrong: '解析错误',
    source_unclear: '依据不清',
    stem_wrong: '题干错误',
    image_missing: '图片缺失',
  }
  return labels[(value ?? '').trim()] ?? (value ?? '').trim()
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

function stringArrayValue(value: unknown, fallback: string[]): string[] {
  if (!Array.isArray(value)) return fallback
  return value.map(item => stringValue(item)).filter(Boolean)
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

function extractLubanFeedbackFromUpdate(
  data: unknown,
  fallback: BiLubanFeedbackResponse
): BiLubanFeedbackResponse {
  const root = asObject(data)
  const response = asObject(root.response)
  if (!Object.keys(response).length) return fallback
  return {
    ...fallback,
    id: stringValue(response.id, fallback.id),
    created_at: stringValue(response.created_at ?? response.createdAt, fallback.created_at),
    source_page: stringValue(response.source_page ?? response.sourcePage, fallback.source_page),
    survey_version: stringValue(
      response.survey_version ?? response.surveyVersion,
      fallback.survey_version
    ),
    nps:
      response.nps === null || response.nps === undefined
        ? fallback.nps
        : Number(response.nps),
    overall_satisfaction:
      response.overall_satisfaction === null || response.overall_satisfaction === undefined
        ? response.overallSatisfaction === null || response.overallSatisfaction === undefined
          ? fallback.overall_satisfaction
          : Number(response.overallSatisfaction)
        : Number(response.overall_satisfaction),
    most_valuable: stringValue(
      response.most_valuable ?? response.mostValuable,
      fallback.most_valuable
    ),
    will_continue: stringValue(
      response.will_continue ?? response.willContinue,
      fallback.will_continue
    ),
    pay_willingness: stringValue(
      response.pay_willingness ?? response.payWillingness,
      fallback.pay_willingness
    ),
    would_recommend: stringValue(
      response.would_recommend ?? response.wouldRecommend,
      fallback.would_recommend
    ),
    revisit_willingness: stringValue(
      response.revisit_willingness ?? response.revisitWillingness,
      fallback.revisit_willingness
    ),
    attempt_count: stringValue(
      response.attempt_count ?? response.attemptCount,
      fallback.attempt_count
    ),
    exam_timeframe: stringValue(
      response.exam_timeframe ?? response.examTimeframe,
      fallback.exam_timeframe
    ),
    one_word: stringValue(response.one_word ?? response.oneWord, fallback.one_word),
    feat_case_grading: stringValue(
      response.feat_case_grading ?? response.featCaseGrading,
      fallback.feat_case_grading
    ),
    feat_error_coach: stringValue(
      response.feat_error_coach ?? response.featErrorCoach,
      fallback.feat_error_coach
    ),
    feat_qa: stringValue(response.feat_qa ?? response.featQa, fallback.feat_qa),
    ease_of_use: stringValue(response.ease_of_use ?? response.easeOfUse, fallback.ease_of_use),
    accuracy: stringValue(response.accuracy, fallback.accuracy),
    speed: stringValue(response.speed, fallback.speed),
    problems: stringArrayValue(response.problems, fallback.problems),
    problems_other: stringValue(
      response.problems_other ?? response.problemsOther,
      fallback.problems_other
    ),
    top_suggestion: stringValue(
      response.top_suggestion ?? response.topSuggestion,
      fallback.top_suggestion
    ),
    unsolved_pain: stringValue(
      response.unsolved_pain ?? response.unsolvedPain,
      fallback.unsolved_pain
    ),
    wanted_features: stringArrayValue(
      response.wanted_features ?? response.wantedFeatures,
      fallback.wanted_features
    ),
    wanted_features_other: stringValue(
      response.wanted_features_other ?? response.wantedFeaturesOther,
      fallback.wanted_features_other
    ),
    phone: stringValue(response.phone, fallback.phone),
    wechat_id: stringValue(response.wechat_id ?? response.wechatId, fallback.wechat_id),
    status: stringValue(response.status, fallback.status),
    operator_note: stringValue(
      response.operator_note ?? response.operatorNote,
      fallback.operator_note
    ),
    contact_revealed: boolValue(
      response.contact_revealed ?? response.contactRevealed,
      fallback.contact_revealed
    ),
  }
}

function buildLubanFeedbackCsv(items: BiLubanFeedbackResponse[]): string {
  const headers = [
    'id',
    'created_at',
    'status',
    'nps',
    'overall_satisfaction',
    'attempt_count',
    'exam_timeframe',
    'most_valuable',
    'feat_case_grading',
    'feat_error_coach',
    'feat_qa',
    'ease_of_use',
    'accuracy',
    'speed',
    'problems',
    'problems_other',
    'revisit_willingness',
    'will_continue',
    'pay_willingness',
    'would_recommend',
    'wanted_features',
    'wanted_features_other',
    'phone',
    'wechat_id',
    'unsolved_pain',
    'top_suggestion',
    'one_word',
    'operator_note',
    'source_page',
  ]
  const rows = items.map(item => [
    item.id,
    item.created_at,
    item.status,
    item.nps ?? '',
    item.overall_satisfaction ?? '',
    lubanLabel(LUBAN_ATTEMPT_LABELS, item.attempt_count),
    lubanLabel(LUBAN_TIMEFRAME_LABELS, item.exam_timeframe),
    lubanLabel(LUBAN_FEATURE_LABELS, item.most_valuable),
    item.feat_case_grading,
    item.feat_error_coach,
    item.feat_qa,
    item.ease_of_use,
    item.accuracy,
    item.speed,
    formatLubanList(item.problems, LUBAN_PROBLEM_LABELS),
    item.problems_other,
    lubanLabel(LUBAN_REVISIT_LABELS, item.revisit_willingness),
    lubanLabel(LUBAN_WILL_CONTINUE_LABELS, item.will_continue),
    lubanLabel(LUBAN_PAY_LABELS, item.pay_willingness),
    lubanLabel(LUBAN_RECOMMEND_LABELS, item.would_recommend),
    formatLubanList(item.wanted_features, LUBAN_WANTED_FEATURE_LABELS),
    item.wanted_features_other,
    item.phone,
    item.wechat_id,
    item.unsolved_pain,
    item.top_suggestion,
    item.one_word,
    item.operator_note,
    item.source_page,
  ])
  return [headers, ...rows].map(row => row.map(csvCell).join(',')).join('\n')
}

function buildInviteApplicationCsv(items: BiInviteTestApplication[]): string {
  const headers = [
    'id',
    'created_at',
    'status',
    'name',
    'phone',
    'email',
    'wechat_id',
    'province',
    'age_range',
    'education',
    'occupation',
    'exam_type',
    'exam_stage',
    'preparation_years',
    'knowledge_foundation',
    'pain_point',
    'weekly_time',
    'daily_study_time',
    'current_method',
    'study_difficulties',
    'latest_wrong_question',
    'is_yousen_member',
    'exam_date',
    'accept_interview',
    'consent',
    'operator_note',
    'source_page',
    'utm_source',
    'utm_campaign',
  ]
  const rows = items.map(item => [
    item.id,
    item.created_at,
    item.status,
    item.name,
    item.phone,
    item.email,
    item.wechat_id,
    item.province,
    item.age_range,
    item.education,
    item.occupation,
    item.exam_type,
    item.exam_stage,
    item.preparation_years,
    item.knowledge_foundation,
    item.pain_point,
    item.weekly_time,
    item.daily_study_time,
    item.current_method,
    item.study_difficulties,
    item.latest_wrong_question,
    item.is_yousen_member,
    item.exam_date,
    item.accept_interview ? 'yes' : 'no',
    item.consent ? 'yes' : 'no',
    item.operator_note,
    item.source_page,
    item.utm_source,
    item.utm_campaign,
  ])
  return [headers, ...rows].map(row => row.map(csvCell).join(',')).join('\n')
}

function csvCell(value: string | number | boolean | null | undefined): string {
  const text = String(value ?? '')
  if (!/[",\n\r]/.test(text)) return text
  return `"${text.replaceAll('"', '""')}"`
}

function downloadCsv(filename: string, content: string) {
  const blob = new Blob([`\uFEFF${content}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
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
  total,
}: {
  title: string
  items: Array<{ label: string; count: number }>
  total?: number
}) {
  const denominator =
    typeof total === 'number' && Number.isFinite(total) && total > 0
      ? total
      : items.reduce((sum, item) => sum + item.count, 0)
  const maxCount = Math.max(1, ...items.map(item => item.count))
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-4 shadow-lg shadow-black/10">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-black text-white">{title}</h3>
        <ClipboardList className="h-4 w-4 text-cyan-300/70" aria-hidden />
      </div>
      <div className="mt-3 space-y-2">
        {items.length > 0 ? (
          items.map(item => {
            const width = Math.max(8, Math.round((item.count / maxCount) * 100))
            const share = denominator > 0 ? item.count / denominator : undefined
            return (
                <div
                  key={`${title}-${item.label}`}
                  className="rounded-2xl border border-white/10 bg-white/[0.045] px-3 py-2 text-xs"
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="min-w-0 break-words text-slate-300">
                      {item.label || 'unknown'}
                    </span>
                    <span className="shrink-0 font-black tabular-nums text-white">
                      {formatCount(item.count)}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                    <div
                      className="h-full rounded-full bg-cyan-300/70"
                      style={{ width: `${width}%` }}
                      aria-hidden
                    />
                  </div>
                  {share !== undefined ? (
                    <div className="mt-1 text-[10px] font-bold text-slate-500">
                      {formatRate(share)}
                    </div>
                  ) : null}
                </div>
            )
          })
        ) : (
          <div className="rounded-2xl border border-dashed border-white/15 bg-white/[0.035] px-3 py-4 text-center text-xs text-slate-400">
            暂无数据
          </div>
        )}
      </div>
    </section>
  )
}

function AgeCompositionCard({
  title,
  total,
  items,
}: {
  title: string
  total: number
  items: Array<{ label: string; count: number }>
}) {
  const denominator =
    Number.isFinite(total) && total > 0 ? total : items.reduce((sum, item) => sum + item.count, 0)
  return (
    <section className="rounded-3xl border border-cyan-300/20 bg-cyan-300/10 p-4 shadow-lg shadow-black/10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-black text-white">{title}</h3>
          <p className="mt-1 text-[11px] leading-5 text-slate-400">
            按服务端画像字段汇总；未填写会落到 unknown。
          </p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.06] px-3 py-2 text-right">
          <div className="text-xl font-black tabular-nums text-cyan-100">
            {formatCount(denominator)}
          </div>
          <div className="text-[10px] font-bold text-slate-400">样本</div>
        </div>
      </div>
      <div
        className="mt-4 flex h-8 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.05]"
        aria-label={`${title}堆叠占比`}
      >
        {items.length > 0 && denominator > 0 ? (
          items.map((item, index) => {
            const width = Math.max(4, (item.count / denominator) * 100)
            const palette = [
              'bg-emerald-300',
              'bg-cyan-300',
              'bg-amber-300',
              'bg-sky-400',
              'bg-rose-300',
              'bg-slate-300',
            ]
            return (
              <div
                key={`${title}-segment-${item.label}`}
                className={`${palette[index % palette.length]} h-full`}
                style={{ width: `${width}%` }}
                title={`${item.label || 'unknown'} ${formatCount(item.count)} (${formatRate(
                  item.count / denominator
                )})`}
                aria-label={`${item.label || 'unknown'} ${formatRate(item.count / denominator)}`}
              />
            )
          })
        ) : (
          <div className="grid h-full w-full place-items-center text-[11px] font-bold text-slate-400">
            暂无年龄数据
          </div>
        )}
      </div>
      <div className="mt-3 grid gap-2">
        {items.length > 0 ? (
          items.map((item, index) => {
            const share = denominator > 0 ? item.count / denominator : 0
            return (
              <div
                key={`${title}-${item.label}`}
                className="grid grid-cols-[14px_minmax(0,1fr)_auto] items-center gap-2 text-xs"
              >
                <span
                  className={
                    [
                      'h-2.5 w-2.5 rounded-full bg-emerald-300',
                      'h-2.5 w-2.5 rounded-full bg-cyan-300',
                      'h-2.5 w-2.5 rounded-full bg-amber-300',
                      'h-2.5 w-2.5 rounded-full bg-sky-400',
                      'h-2.5 w-2.5 rounded-full bg-rose-300',
                      'h-2.5 w-2.5 rounded-full bg-slate-300',
                    ][index % 6]
                  }
                  aria-hidden
                />
                <span className="min-w-0 truncate text-slate-300">{item.label || 'unknown'}</span>
                <span className="font-black tabular-nums text-white">
                  {formatCount(item.count)} · {formatRate(share)}
                </span>
              </div>
            )
          })
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

function lubanLabel(map: Record<string, string>, value: string | undefined): string {
  const key = (value ?? '').trim() || 'unknown'
  return map[key] || key
}

function formatLubanList(
  values: string[] | undefined,
  map: Record<string, string>,
  other = ''
): string {
  const labels = (values ?? []).map(value => lubanLabel(map, value)).filter(Boolean)
  if (other.trim()) labels.push(`其他：${other.trim()}`)
  return labels.length ? labels.join(' / ') : '未填写'
}

function lubanStatusTone(status: string | undefined): BiStatusTone {
  if (status === 'resolved' || status === 'interviewed') return 'emerald'
  if (status === 'contacted') return 'sky'
  if (status === 'archived') return 'slate'
  return 'amber'
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
