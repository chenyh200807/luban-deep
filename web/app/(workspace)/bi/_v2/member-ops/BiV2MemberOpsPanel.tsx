/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Filter, MessageSquareText, RefreshCw, Save, Settings2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import {
  BiButton,
  BiDataTable,
  BiMoneyCell,
  BiNotice,
  BiStatusPill,
  BiV2DataSourceBanner,
  BI_STATUS_PILL_TONE,
  type BiTableColumn,
} from '@/components/bi-v2'
import { Member360Drawer } from './Member360Drawer'
import { ConversationReviewDrawer } from './ConversationReviewDrawer'
import {
  getMemberDashboard,
  getMemberDetail,
  listMembers,
  type MemberDashboard,
  type MemberDetail,
  type MemberListItem,
} from '@/lib/member-api'
import {
  ALL_COLUMNS,
  DEFAULT_COLUMNS,
  DEFAULT_FILTERS,
  MOCK_MEMBERS,
  filterMembers,
  type MemberColumnKey,
  type MemberFilters,
  type MemberRow,
  type SavedView,
} from './data'
import { useAuditedAction } from '../useAuditedAction'

const STATUS_TONE = {
  active: 'emerald',
  expiring: 'amber',
  expired: 'rose',
  paused: 'slate',
} as const

const TIER_TONE = {
  trial: 'slate',
  vip: 'sky',
  svip: 'amber',
} as const

const SAVED_VIEWS_STORAGE_KEY = 'bi-v2-saved-views-v1'
const SAVED_VIEWS_EVENT = 'bi-v2-saved-views-changed'
const EMPTY_VIEWS: SavedView[] = []
let savedViewsRawSnapshot: string | null = null
let savedViewsSnapshot: SavedView[] = EMPTY_VIEWS

function readSavedViewsClient(): SavedView[] {
  try {
    const raw = window.localStorage.getItem(SAVED_VIEWS_STORAGE_KEY)
    if (!raw) {
      savedViewsRawSnapshot = null
      savedViewsSnapshot = EMPTY_VIEWS
      return savedViewsSnapshot
    }
    if (raw === savedViewsRawSnapshot) return savedViewsSnapshot
    const parsed = JSON.parse(raw) as unknown
    savedViewsRawSnapshot = raw
    savedViewsSnapshot = Array.isArray(parsed) ? (parsed as SavedView[]) : EMPTY_VIEWS
    return savedViewsSnapshot
  } catch {
    savedViewsRawSnapshot = null
    savedViewsSnapshot = EMPTY_VIEWS
    return EMPTY_VIEWS
  }
}

function readSavedViewsServer(): SavedView[] {
  return EMPTY_VIEWS
}

function subscribeSavedViews(callback: () => void) {
  window.addEventListener(SAVED_VIEWS_EVENT, callback)
  window.addEventListener('storage', callback)
  return () => {
    window.removeEventListener(SAVED_VIEWS_EVENT, callback)
    window.removeEventListener('storage', callback)
  }
}

function writeSavedViews(next: SavedView[]) {
  const raw = JSON.stringify(next)
  savedViewsRawSnapshot = raw
  savedViewsSnapshot = next
  try {
    window.localStorage.setItem(SAVED_VIEWS_STORAGE_KEY, raw)
  } catch {
    // ignore quota
  }
  window.dispatchEvent(new CustomEvent(SAVED_VIEWS_EVENT))
}

import type { BiAdminIdentity } from '../useBiAdminIdentity'

export type BiV2MemberOpsPanelProps = {
  flagEnabled: boolean
  globalQuery: string
  identity: BiAdminIdentity
}

const API_STATUS: Partial<Record<MemberFilters['status'], string>> = {
  active: 'active',
  expiring: 'expiring_soon',
  expired: 'expired',
  paused: 'revoked',
}

function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  if (digits.length < 7) return phone || '—'
  return `${digits.slice(0, 3)}****${digits.slice(-4)}`
}

function riskScore(riskLevel: string): number {
  if (riskLevel === 'high') return 0.85
  if (riskLevel === 'medium') return 0.55
  if (riskLevel === 'low') return 0.2
  return 0
}

function normalizeStatus(status: string): MemberRow['status'] {
  if (status === 'expiring_soon') return 'expiring'
  if (status === 'revoked') return 'paused'
  if (status === 'expired') return 'expired'
  return 'active'
}

function shortDate(value: string): string {
  if (!value) return '—'
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(parsed)
}

function toMemberRow(item: MemberListItem): MemberRow {
  const tier = ['trial', 'vip', 'svip'].includes(item.tier) ? item.tier : 'trial'
  return {
    user_id: item.user_id,
    phone_masked: maskPhone(item.phone),
    tier: tier as MemberRow['tier'],
    status: normalizeStatus(item.status),
    risk: riskScore(item.risk_level),
    last_active: shortDate(item.last_active_at),
    balance_points: item.points_balance,
    expires_at: shortDate(item.expire_at),
    paid_at_first: tier === 'trial' ? undefined : shortDate(item.created_at),
    region: item.segment || item.display_name,
    notes_count: item.review_due,
    feedback_count: 0,
  }
}

export function BiV2MemberOpsPanel({
  flagEnabled,
  globalQuery,
  identity,
}: BiV2MemberOpsPanelProps) {
  const [filters, setFilters] = useState<MemberFilters>(DEFAULT_FILTERS)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [columns, setColumns] = useState<MemberColumnKey[]>(DEFAULT_COLUMNS)
  const [columnPickerOpen, setColumnPickerOpen] = useState(false)
  const savedViews = useSyncExternalStore<SavedView[]>(
    subscribeSavedViews,
    readSavedViewsClient,
    readSavedViewsServer
  )
  const setSavedViews = useCallback(
    (updater: SavedView[] | ((prev: SavedView[]) => SavedView[])) => {
      writeSavedViews(typeof updater === 'function' ? updater(readSavedViewsClient()) : updater)
    },
    []
  )
  const [activeViewId, setActiveViewId] = useState<string | null>(null)
  const [selectedMember, setSelectedMember] = useState<MemberRow | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<MemberDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState('')
  const [drawer, setDrawer] = useState<'none' | 'member360' | 'conversation'>('none')
  const [conversationReturnTo, setConversationReturnTo] = useState<'none' | 'member360'>('member360')
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set())
  const [liveRows, setLiveRows] = useState<MemberRow[]>([])
  const [dashboard, setDashboard] = useState<MemberDashboard | null>(null)
  const [totalRows, setTotalRows] = useState(0)
  const [loading, setLoading] = useState(flagEnabled)
  const [error, setError] = useState('')
  const [opsActionNotice, setOpsActionNotice] = useState('')
  const lastAutoOpenedQueryRef = useRef('')
  const memberOpsAction = useAuditedAction({ actionType: 'member.ops_action.record' })
  const opsActionWriting = memberOpsAction.state.phase === 'writing'
  const opsActionError = memberOpsAction.state.phase === 'denied' ? (memberOpsAction.state.result.error ?? '') : ''

  const loadMembers = useCallback(async () => {
    if (!flagEnabled) {
      setLiveRows([])
      setDashboard(null)
      setTotalRows(0)
      setLoading(false)
      setError('')
      return
    }
    try {
      setLoading(true)
      setError('')
      const [nextDashboard, list] = await Promise.all([
        getMemberDashboard(),
        listMembers({
          page: 1,
          page_size: 100,
          sort: 'expire_at',
          order: 'asc',
          search: globalQuery.trim() || undefined,
          status: filters.status ? API_STATUS[filters.status] : undefined,
          tier: filters.tier || undefined,
          expire_within_days: filters.expiringDays || undefined,
          risk_level: filters.riskMin >= 0.7 ? 'high' : undefined,
        }),
      ])
      const nextRows = list.items.map(toMemberRow)
      setDashboard(nextDashboard)
      setLiveRows(nextRows)
      setTotalRows(list.total)
      setSelectedRows(prev => new Set([...prev].filter(id => nextRows.some(row => row.user_id === id))))
    } catch (err) {
      setError(err instanceof Error ? err.message : '会员列表加载失败')
      setLiveRows([])
      setDashboard(null)
      setTotalRows(0)
    } finally {
      setLoading(false)
    }
  }, [filters.expiringDays, filters.riskMin, filters.status, filters.tier, flagEnabled, globalQuery])

  useEffect(() => {
    void loadMembers()
  }, [loadMembers])

  const rows = useMemo(
    () => filterMembers(flagEnabled ? liveRows : MOCK_MEMBERS, filters, flagEnabled ? '' : globalQuery),
    [filters, flagEnabled, globalQuery, liveRows]
  )

  function toggleColumn(key: MemberColumnKey) {
    setColumns(prev => {
      if (prev.includes(key)) {
        if (prev.length <= 3) return prev
        return prev.filter(k => k !== key)
      }
      return [...prev, key]
    })
  }

  function applyView(view: SavedView) {
    setFilters(view.filters)
    setColumns(view.columns)
    setActiveViewId(view.id)
  }

  function saveView() {
    const name = `视图 ${savedViews.length + 1}`
    const view: SavedView = {
      id: `view_${Date.now()}`,
      name,
      filters,
      columns,
      query: globalQuery,
    }
    setSavedViews(prev => [...prev, view])
    setActiveViewId(view.id)
  }

  function removeView(id: string) {
    setSavedViews(prev => prev.filter(v => v.id !== id))
    if (activeViewId === id) setActiveViewId(null)
  }

  // P0 read-only actions: opening drawers is not an audited event; only
  // server-side writes (notes / ops-actions / conversation view-audit) are
  // audited via useAuditedAction at the call site. UI no longer fabricates
  // local audit logs (which were misleading — they suggested writes happened
  // when in fact nothing was sent to the server).
  const openMember360 = useCallback(async (row: MemberRow) => {
    setSelectedMember(row)
    setSelectedDetail(null)
    setDetailError('')
    setDrawer('member360')
    if (!flagEnabled) return
    try {
      setDetailLoading(true)
      setSelectedDetail(await getMemberDetail(row.user_id))
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : '学员 360 加载失败')
    } finally {
      setDetailLoading(false)
    }
  }, [flagEnabled])

  useEffect(() => {
    const query = globalQuery.trim()
    if (!flagEnabled || !query || loading || rows.length !== 1) return
    if (lastAutoOpenedQueryRef.current === query) return
    lastAutoOpenedQueryRef.current = query
    void openMember360(rows[0])
  }, [flagEnabled, globalQuery, loading, openMember360, rows])

  function openConversation(row?: MemberRow) {
    if (row) {
      setSelectedMember(row)
      setSelectedDetail(null)
      setDetailError('')
      setConversationReturnTo('none')
    } else {
      setConversationReturnTo('member360')
    }
    setDrawer('conversation')
  }

  async function executeMemberOpsAction(
    userId: string,
    payload: {
      status: 'done' | 'follow_up'
      result: string
      action_title: string
      next_follow_up_at?: string
    }
  ): Promise<boolean> {
    if (!flagEnabled || opsActionWriting) return false
    setOpsActionNotice('')
    const result = await memberOpsAction.execute({
      key: 'member.ops_action.record',
      params: { user_id: userId },
      body: {
        status: payload.status,
        result: payload.result,
        action_title: payload.action_title,
        next_follow_up_at: payload.next_follow_up_at ?? '',
      },
    })
    return result.ok
  }

  async function markContacted(member: MemberRow) {
    const ok = await executeMemberOpsAction(member.user_id, {
      status: 'done',
      result: 'BI 标记已联系',
      action_title: '标记已联系',
    })
    if (ok) setOpsActionNotice(`已标记 ${member.phone_masked} 为已联系`)
  }

  async function joinFollowUp(member: MemberRow) {
    const ok = await executeMemberOpsAction(member.user_id, {
      status: 'follow_up',
      result: '加入 BI 跟进队列',
      action_title: '加入跟进队列',
    })
    if (ok) setOpsActionNotice(`已把 ${member.phone_masked} 加入跟进队列`)
  }

  async function addOpsNote(member: MemberRow, note: string) {
    const ok = await executeMemberOpsAction(member.user_id, {
      status: 'done',
      result: note,
      action_title: '运营备注',
    })
    if (ok) setOpsActionNotice(`已给 ${member.phone_masked} 添加备注`)
  }

  async function runBulkAction(kind: 'contacted' | 'follow_up') {
    const selectedIds = [...selectedRows].slice(0, kind === 'contacted' ? 50 : 100)
    if (selectedIds.length === 0 || opsActionWriting) return
    let success = 0
    for (const userId of selectedIds) {
      const ok = await executeMemberOpsAction(userId, {
        status: kind === 'contacted' ? 'done' : 'follow_up',
        result: kind === 'contacted' ? 'BI 批量标记已联系' : 'BI 批量加入跟进队列',
        action_title: kind === 'contacted' ? '批量标记已联系' : '批量加入跟进队列',
      })
      if (ok) success += 1
    }
    if (success > 0) {
      setOpsActionNotice(`${success} 位会员已写入运营动作 audit`)
      setSelectedRows(new Set())
    }
  }

  const columnDefs = useMemo<BiTableColumn<MemberRow>[]>(
    () =>
      columns.map(key => {
        const def = ALL_COLUMNS.find(c => c.key === key)!
        return {
          key,
          label: def.label,
          align: def.align,
          sortable: def.sortable,
          render: row => renderCell(row, key),
        }
      }),
    [columns]
  )

  return (
    <section className="space-y-4">
      {!flagEnabled ? (
        <BiV2DataSourceBanner tone="amber">
          BI_CRM_V2_ENABLED 未开启。当前为 Batch 2 静态原型；Batch 2.5+ 接入真实
          <code className="mx-1 font-mono">/api/v1/bi/members</code> 与
          <code className="font-mono">/api/v1/member/&lt;user_id&gt;/*</code>。
        </BiV2DataSourceBanner>
      ) : (
        <BiV2DataSourceBanner
          tone="sky"
          action={
            <BiButton
              onClick={() => void loadMembers()}
              disabled={loading}
              variant="primary"
              size="xs"
              aria-label="刷新会员运营"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} aria-hidden />
              刷新
            </BiButton>
          }
        >
            BI_CRM_V2_ENABLED 已开启 · 会员列表读取{' '}
            <code className="font-mono">/api/v1/member/list</code>，学员 360 读取{' '}
            <code className="font-mono">/api/v1/member/&lt;user_id&gt;/360</code>；低风险写动作走
            member.ops_action.record audit。
        </BiV2DataSourceBanner>
      )}
      {opsActionError ? (
        <BiNotice tone="rose" role="alert">
          会员运营动作未写入：{opsActionError}
        </BiNotice>
      ) : null}
      {opsActionNotice ? (
        <BiNotice tone="emerald">
          {opsActionNotice}
        </BiNotice>
      ) : null}

      <MemberSummaryCards dashboard={dashboard} loading={loading} />

      <SavedViewsBar
        savedViews={savedViews}
        activeViewId={activeViewId}
        onApply={applyView}
        onRemove={removeView}
        onSave={saveView}
      />

      <CommonFilters filters={filters} onChange={setFilters} />

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-[26px] border border-cyan-300/20 bg-cyan-300/[0.08] px-4 py-3 text-sm text-cyan-50 shadow-lg shadow-black/10">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-cyan-200/25 bg-cyan-200/10 text-cyan-100">
            <MessageSquareText className="h-4 w-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="font-black">对话工作台已放到首屏</div>
            <div className="mt-0.5 text-xs text-cyan-100/75">
              每行直接点“对话”查看会话线索、筛选排序；查看全文仍会写入 audit。
            </div>
          </div>
        </div>
      </section>

      <div className="flex items-center justify-between text-xs text-slate-500">
        <BiButton
          onClick={() => setAdvancedOpen(v => !v)}
          variant={advancedOpen ? 'primary' : 'secondary'}
          size="xs"
          aria-expanded={advancedOpen}
          aria-controls="bi-v2-advanced-filters"
        >
          <Filter className="h-3 w-3" aria-hidden /> {advancedOpen ? '收起高级筛选' : '高级筛选'}
        </BiButton>
        <BiButton
          onClick={() => setColumnPickerOpen(v => !v)}
          variant={columnPickerOpen ? 'primary' : 'secondary'}
          size="xs"
          aria-expanded={columnPickerOpen}
          aria-controls="bi-v2-column-picker"
        >
          <Settings2 className="h-3 w-3" aria-hidden /> 列设置 ({columns.length})
        </BiButton>
      </div>

      {advancedOpen ? <AdvancedFilters filters={filters} onChange={setFilters} /> : null}
      {columnPickerOpen ? <ColumnPicker columns={columns} onToggle={toggleColumn} /> : null}

      <BiDataTable<MemberRow>
        columns={columnDefs}
        rows={rows}
        rowKey={r => r.user_id}
        status={
          loading
            ? 'loading'
            : error
              ? 'error'
              : rows.length === 0
                ? flagEnabled
                  ? 'empty'
                  : 'no-results'
                : 'ok'
        }
        errorMessage={error}
        emptyTitle="暂无会员"
        emptyHint="当前会员服务没有返回符合条件的会员。"
        noResultsHint="当前筛选未命中任何会员。尝试放宽 tier / risk / expiring 条件。"
        selectable
        selectedKeys={selectedRows}
        onToggleRow={key => {
          setSelectedRows(prev => {
            const next = new Set(prev)
            if (next.has(key)) next.delete(key)
            else next.add(key)
            return next
          })
        }}
        onToggleAll={allSelected => {
          if (allSelected) setSelectedRows(new Set())
          else setSelectedRows(new Set(rows.map(r => r.user_id)))
        }}
        rowAction={row => (
          <div className="flex justify-end gap-1.5">
            <BiButton
              onClick={() => openConversation(row)}
              variant="primary"
              size="xs"
              aria-label={`打开 ${row.user_id} 会员对话工作台`}
            >
              <MessageSquareText className="h-3 w-3" aria-hidden />
              对话
            </BiButton>
            <BiButton
              onClick={() => {
                void openMember360(row)
              }}
              variant="secondary"
              size="xs"
              aria-label={`打开 ${row.user_id} 学员 360`}
            >
              360
            </BiButton>
          </div>
        )}
        pageSize={50}
        cursorFooter={
          <>
            <span>
              {flagEnabled
                ? `服务端返回前 ${liveRows.length} / ${totalRows}，当前筛选 ${rows.length} 行`
                : `筛选后 ${rows.length} 行（dev mock total ${MOCK_MEMBERS.length}）`}
            </span>
            <span>{selectedRows.size > 0 ? `已选 ${selectedRows.size}` : ''}</span>
          </>
        }
      />

      <BulkActions
        selected={selectedRows.size}
        writing={opsActionWriting}
        onMarkContacted={() => void runBulkAction('contacted')}
        onJoinFollowUp={() => void runBulkAction('follow_up')}
      />

      <Member360Drawer
        open={drawer === 'member360'}
        member={selectedMember}
        detail={selectedDetail}
        loading={detailLoading}
        error={detailError}
        onClose={() => setDrawer('none')}
        onOpenConversation={openConversation}
        onMarkContacted={markContacted}
        onJoinFollowUp={joinFollowUp}
        onAddNote={addOpsNote}
        opsActionWriting={opsActionWriting}
      />
      <ConversationReviewDrawer
        open={drawer === 'conversation'}
        member={selectedMember}
        detail={selectedDetail}
        onClose={() => setDrawer(conversationReturnTo)}
      />
    </section>
  )
}

function MemberSummaryCards({
  dashboard,
  loading,
}: {
  dashboard: MemberDashboard | null
  loading: boolean
}) {
  const cards = [
    { label: '全部会员', value: dashboard?.total_count },
    { label: '活跃会员', value: dashboard?.active_count },
    { label: '7 日内到期', value: dashboard?.expiring_soon_count },
    { label: '高风险', value: dashboard?.churn_risk_count },
    { label: '自动续费覆盖', value: dashboard ? `${dashboard.auto_renew_coverage}%` : undefined },
  ]
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {cards.map(card => (
        <div key={card.label} className="rounded-3xl border border-white/10 bg-white/[0.045] p-3 shadow-lg shadow-black/10">
          <div className="text-[11px] font-bold text-slate-400">{card.label}</div>
          <div className="mt-1 text-2xl font-black tabular-nums text-slate-50">
            {loading && card.value === undefined ? '…' : (card.value ?? '—')}
          </div>
        </div>
      ))}
    </div>
  )
}

function SavedViewsBar({
  savedViews,
  activeViewId,
  onApply,
  onRemove,
  onSave,
}: {
  savedViews: SavedView[]
  activeViewId: string | null
  onApply: (v: SavedView) => void
  onRemove: (id: string) => void
  onSave: () => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-white/10 bg-white/[0.035] p-2 text-xs">
      <span className="text-slate-400">我的视图：</span>
      {savedViews.length === 0 ? <span className="text-slate-500">暂无（点右侧保存）</span> : null}
      {savedViews.map(v => (
        <span
          key={v.id}
          className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.06] px-2 py-1"
        >
          <button
            type="button"
            onClick={() => onApply(v)}
            className={`text-[11px] ${activeViewId === v.id ? 'font-black text-cyan-100' : 'font-bold text-slate-200'}`}
            aria-label={`应用视图 ${v.name}`}
          >
            {v.name}
          </button>
          <button
            type="button"
            onClick={() => onRemove(v.id)}
            className="text-slate-500 hover:text-rose-200"
            aria-label={`删除视图 ${v.name}`}
          >
            ×
          </button>
        </span>
      ))}
      <BiButton
        onClick={onSave}
        variant="secondary"
        size="xs"
        className="ml-auto"
        aria-label="把当前筛选与列设置保存为私有视图"
      >
        <Save className="h-3 w-3" aria-hidden /> 保存视图
      </BiButton>
    </div>
  )
}

function CommonFilters({
  filters,
  onChange,
}: {
  filters: MemberFilters
  onChange: (next: MemberFilters) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Pill
        label="全部 tier"
        active={filters.tier === ''}
        onClick={() => onChange({ ...filters, tier: '' })}
      />
      <Pill
        label="VIP"
        active={filters.tier === 'vip'}
        onClick={() => onChange({ ...filters, tier: 'vip' })}
      />
      <Pill
        label="SVIP"
        active={filters.tier === 'svip'}
        onClick={() => onChange({ ...filters, tier: 'svip' })}
      />
      <Pill
        label="高风险 ≥ 0.7"
        active={filters.riskMin >= 0.7}
        onClick={() => onChange({ ...filters, riskMin: filters.riskMin >= 0.7 ? 0 : 0.7 })}
      />
      <Pill
        label="7 日内到期"
        active={filters.expiringDays === 7}
        onClick={() => onChange({ ...filters, expiringDays: filters.expiringDays === 7 ? 0 : 7 })}
      />
      <Pill
        label="未付费"
        active={filters.notPaid}
        onClick={() => onChange({ ...filters, notPaid: !filters.notPaid })}
      />
      <BiButton
        onClick={() => onChange(DEFAULT_FILTERS)}
        variant="ghost"
        size="xs"
        aria-label="清空筛选"
      >
        清空
      </BiButton>
    </div>
  )
}

function Pill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3 py-1 font-bold transition ${
        active
          ? 'border-cyan-300/35 bg-cyan-300/15 text-cyan-50'
          : 'border-white/10 bg-white/[0.045] text-slate-300 hover:border-white/20 hover:bg-white/[0.07]'
      }`}
    >
      {label}
    </button>
  )
}

function AdvancedFilters({
  filters,
  onChange,
}: {
  filters: MemberFilters
  onChange: (next: MemberFilters) => void
}) {
  return (
    <div
      id="bi-v2-advanced-filters"
      className="rounded-2xl border border-white/10 bg-white/[0.04] p-3"
    >
      <h4 className="text-xs font-black text-slate-200">高级筛选</h4>
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
        <label className="text-xs font-bold text-slate-300">
          状态
          <select
            className="ml-2 rounded-xl border border-white/10 bg-[#151d2b] px-2 py-1 text-slate-100 outline-none focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
            value={filters.status}
            onChange={e =>
              onChange({ ...filters, status: e.target.value as MemberFilters['status'] })
            }
            aria-label="按状态筛选"
          >
            <option value="">全部</option>
            <option value="active">active</option>
            <option value="expiring">expiring</option>
            <option value="expired">expired</option>
            <option value="paused">paused</option>
          </select>
        </label>
        <label className="text-xs font-bold text-slate-300">
          风险阈值
          <input
            type="number"
            step="0.05"
            min={0}
            max={1}
            value={filters.riskMin}
            onChange={e => onChange({ ...filters, riskMin: Number(e.target.value) })}
            className="ml-2 w-20 rounded-xl border border-white/10 bg-white/[0.06] px-2 py-1 text-slate-100 outline-none focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
            aria-label="风险阈值"
          />
        </label>
        <label className="text-xs font-bold text-slate-300">
          到期天数（0 = 不限）
          <input
            type="number"
            min={0}
            max={365}
            value={filters.expiringDays}
            onChange={e => onChange({ ...filters, expiringDays: Number(e.target.value) })}
            className="ml-2 w-20 rounded-xl border border-white/10 bg-white/[0.06] px-2 py-1 text-slate-100 outline-none focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
            aria-label="到期天数阈值"
          />
        </label>
      </div>
    </div>
  )
}

function ColumnPicker({
  columns,
  onToggle,
}: {
  columns: MemberColumnKey[]
  onToggle: (key: MemberColumnKey) => void
}) {
  return (
    <div
      id="bi-v2-column-picker"
      className="rounded-2xl border border-white/10 bg-white/[0.04] p-3"
    >
      <h4 className="text-xs font-black text-slate-200">列设置</h4>
      <div className="mt-2 grid grid-cols-2 gap-1 md:grid-cols-3">
        {ALL_COLUMNS.map(c => {
          const checked = columns.includes(c.key)
          return (
            <label key={c.key} className="flex items-center gap-2 text-xs font-bold text-slate-300">
              <input
                type="checkbox"
                checked={checked}
                onChange={() => onToggle(c.key)}
                aria-label={`列 ${c.label}`}
              />
              {c.label}
            </label>
          )
        })}
      </div>
      <p className="mt-2 text-[10px] text-slate-400">
        最少保留 3 列。设置保存在私有视图（保存视图按钮）。
      </p>
    </div>
  )
}

function BulkActions({
  selected,
  writing,
  onMarkContacted,
  onJoinFollowUp,
}: {
  selected: number
  writing: boolean
  onMarkContacted: () => void
  onJoinFollowUp: () => void
}) {
  return (
    <div
      className={`flex flex-col gap-3 rounded-2xl border px-3 py-3 text-xs sm:flex-row sm:items-center sm:justify-between ${
        selected > 0
          ? 'border-cyan-300/30 bg-cyan-300/10 text-cyan-50'
          : 'border-dashed border-white/15 bg-white/[0.035] text-slate-400'
      }`}
      aria-live="polite"
    >
      <span>{selected > 0 ? `已选 ${selected} 位会员` : '选择会员后可批量执行低风险动作'}</span>
      <div className="flex flex-wrap items-center gap-2">
        <BiButton
          disabled={selected === 0 || writing}
          title="写入 ops_action_result audit"
          onClick={onMarkContacted}
          variant="secondary"
          size="xs"
          aria-label="批量标记已联系（≤ 50）"
        >
          标记已联系
        </BiButton>
        <BiButton
          disabled={selected === 0 || writing}
          title="写入 ops_action_result audit"
          onClick={onJoinFollowUp}
          variant="secondary"
          size="xs"
          aria-label="加入跟进队列（≤ 100）"
        >
          加入跟进队列
        </BiButton>
        <span className="text-[10px] text-slate-400">高危动作（撤销 / 补点 / 异常处理）暂禁用</span>
      </div>
    </div>
  )
}

function renderCell(row: MemberRow, key: MemberColumnKey): React.ReactNode {
  if (key === 'phone') return <span className="font-mono">{row.phone_masked}</span>
  if (key === 'tier')
    return <BiStatusPill tone={TIER_TONE[row.tier]} label={row.tier.toUpperCase()} />
  if (key === 'status')
    return (
      <span
        className={`${BI_STATUS_PILL_TONE[STATUS_TONE[row.status]]} rounded px-1.5 py-0.5 text-[10px]`}
      >
        {row.status}
      </span>
    )
  if (key === 'risk') return <span className="tabular-nums">{row.risk.toFixed(2)}</span>
  if (key === 'last_active') return <span className="text-slate-300">{row.last_active}</span>
  if (key === 'balance')
    return <BiMoneyCell amount={row.balance_points} currency="POINT" align="right" />
  if (key === 'expires_at') return <span className="text-slate-300">{row.expires_at}</span>
  if (key === 'paid_first')
    return <span className="text-slate-300">{row.paid_at_first ?? '—'}</span>
  if (key === 'region') return row.region ?? '—'
  if (key === 'notes') return <span className="tabular-nums">{row.notes_count ?? 0}</span>
  if (key === 'feedback') return <span className="tabular-nums">{row.feedback_count ?? 0}</span>
  return null
}
