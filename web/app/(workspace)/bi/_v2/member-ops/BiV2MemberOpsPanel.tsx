/* eslint-disable i18n/no-literal-ui-text */
'use client'

import {
  CreditCard,
  Filter,
  MessageSquareText,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Settings2,
  ShieldOff,
  UserCog,
} from 'lucide-react'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from 'react'
import {
  BiButton,
  BiDataTable,
  BiMoneyCell,
  BiNotice,
  BiSelect,
  BiSidePanel,
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
  manualPurchaseMembership,
  reverseManualMembershipPurchase,
  revokeMembership,
  updateMembership,
  type MemberDashboard,
  type MemberDetail,
  type MemberListItem,
} from '@/lib/member-api'
import { getBiCommerce, type BiCommercePackage } from '@/lib/bi-api'
import { MemberOpsCockpit } from '@/components/bi-cockpit/MemberOpsCockpit'
import {
  ALL_COLUMNS,
  DEFAULT_COLUMNS,
  DEFAULT_FILTERS,
  MOCK_MEMBERS,
  filterMembers,
  sortMembers,
  type MemberColumnKey,
  type MemberFilters,
  type MemberRow,
  type MemberSortDir,
  type MemberSortKey,
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
  supreme_svip: 'emerald',
} as const

const BEHAVIOR_COHORTS = [
  { key: '', label: '全部行为' },
  { key: 'report_high_no_action', label: '学情高频无行动' },
  { key: 'history_high_no_review', label: '历史高频无复盘' },
  { key: 'chat_only', label: '只对话不看学情' },
  { key: 'training_no_retest', label: '训练未复测' },
] as const

const BEHAVIOR_COHORT_TONE = {
  report_high_no_action: 'amber',
  history_high_no_review: 'sky',
  chat_only: 'slate',
  training_no_retest: 'rose',
} as const

const SAVED_VIEWS_STORAGE_KEY = 'bi-v2-saved-views-v1'
const SAVED_VIEWS_EVENT = 'bi-v2-saved-views-changed'
const EMPTY_VIEWS: SavedView[] = []
const EMPTY_PACKAGES: BiCommercePackage[] = []
const MEMBERSHIP_INPUT_CLASS =
  'h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60'
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

function notifyCommerceMutated(detail: { userId: string; packageId: string }) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent('bi:commerce-mutated', { detail }))
}

import type { BiAdminIdentity } from '../useBiAdminIdentity'

export type BiV2MemberOpsPanelProps = {
  flagEnabled: boolean
  globalQuery: string
  onSubmitSearch?: (value: string) => void
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

function behaviorCohortLabel(cohort?: string): string {
  return BEHAVIOR_COHORTS.find(item => item.key === cohort)?.label ?? (cohort || '正常')
}

function behaviorNextAction(cohort?: string): string {
  if (cohort === 'report_high_no_action') return '安排训练回访'
  if (cohort === 'history_high_no_review') return '发送错题复盘'
  if (cohort === 'chat_only') return '引导查看学情'
  if (cohort === 'training_no_retest') return '提醒复测'
  return '观察'
}

function toMemberRow(item: MemberListItem): MemberRow {
  const tier = normalizeMembershipTier(item.tier)
  const behavior = item.behavior
  const behaviorCohort = behavior?.cohort || ''
  return {
    user_id: item.user_id,
    phone_masked: maskPhone(item.phone),
    tier,
    status: normalizeStatus(item.status),
    risk: riskScore(item.risk_level),
    last_active: shortDate(item.last_active_at),
    balance_points: item.points_balance,
    expires_at: shortDate(item.expire_at),
    paid_at_first: tier === 'trial' ? undefined : shortDate(item.created_at),
    region: item.segment || item.display_name,
    notes_count: item.review_due,
    feedback_count: 0,
    behavior_learning_report_7d: behavior?.learning_report_open_count_7d ?? 0,
    behavior_history_7d: behavior?.history_open_count_7d ?? 0,
    behavior_cohort: behaviorCohort,
    behavior_trust: behavior?.trust_level || 'C',
    behavior_next_action: behavior?.next_action || behaviorNextAction(behaviorCohort),
    behavior_reasons: behavior?.cohort_reasons || [],
    behavior_event_count_7d: behavior?.event_count_7d ?? 0,
    behavior_last_event_at_ms: behavior?.last_event_at_ms ?? 0,
  }
}

function canUpgradeToVip(member: MemberRow): boolean {
  return member.tier !== 'vip' && member.tier !== 'svip' && member.tier !== 'supreme_svip'
}

function normalizeMembershipTier(value: string): MemberRow['tier'] {
  if (value === 'vip' || value === 'svip' || value === 'trial' || value === 'supreme_svip') {
    return value
  }
  return 'trial'
}

function tierLabel(value: string): string {
  if (value === 'trial') return '体验'
  if (value === 'vip') return 'VIP'
  if (value === 'svip') return 'SVIP'
  if (value === 'supreme_svip') return '至尊SVIP'
  return value || '未知'
}

function isActivePackage(pkg: BiCommercePackage): boolean {
  return (pkg.status || 'active') === 'active'
}

function findPackageForTier(
  packages: ReadonlyArray<BiCommercePackage>,
  tier: MemberRow['tier']
): BiCommercePackage | undefined {
  return packages.find(pkg => isActivePackage(pkg) && normalizeMembershipTier(pkg.tier) === tier)
}

function statusLabel(status: string): string {
  if (status === 'active') return '有效'
  if (status === 'expiring') return '即将到期'
  if (status === 'expired') return '已过期'
  if (status === 'paused') return '已取消'
  return status || '未知'
}

function toDateInputValue(value?: string | null): string {
  if (!value) return ''
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return ''
  return new Date(parsed).toISOString().slice(0, 10)
}

export function BiV2MemberOpsPanel({
  flagEnabled,
  globalQuery,
  onSubmitSearch,
  identity,
}: BiV2MemberOpsPanelProps) {
  const [filters, setFilters] = useState<MemberFilters>(DEFAULT_FILTERS)
  const [memberSearchDraft, setMemberSearchDraft] = useState(globalQuery)
  const [sortKey, setSortKey] = useState<MemberSortKey>('expires_at')
  const [sortDir, setSortDir] = useState<MemberSortDir>('asc')
  const [behaviorCohort, setBehaviorCohort] = useState('')
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
  const [drawer, setDrawer] = useState<'none' | 'member360' | 'conversation' | 'membershipSettings'>(
    'none'
  )
  const [conversationReturnTo, setConversationReturnTo] = useState<'none' | 'member360'>(
    'member360'
  )
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set())
  const [liveRows, setLiveRows] = useState<MemberRow[]>([])
  const [dashboard, setDashboard] = useState<MemberDashboard | null>(null)
  const [membershipPackages, setMembershipPackages] =
    useState<BiCommercePackage[]>(EMPTY_PACKAGES)
  const [totalRows, setTotalRows] = useState(0)
  const [loading, setLoading] = useState(flagEnabled)
  const [error, setError] = useState('')
  const [opsActionNotice, setOpsActionNotice] = useState('')
  const [membershipActionWriting, setMembershipActionWriting] = useState(false)
  const [membershipActionError, setMembershipActionError] = useState('')
  const lastAutoOpenedQueryRef = useRef('')
  const memberOpsAction = useAuditedAction({ actionType: 'member.ops_action.record' })
  const opsActionWriting = memberOpsAction.state.phase === 'writing'
  const opsActionError =
    memberOpsAction.state.phase === 'denied' ? (memberOpsAction.state.result.error ?? '') : ''
  const activeMemberSearchQuery = globalQuery.trim()

  useEffect(() => {
    setMemberSearchDraft(globalQuery)
  }, [globalQuery])

  const loadMembers = useCallback(async () => {
    if (!flagEnabled) {
      setLiveRows([])
      setDashboard(null)
      setMembershipPackages(EMPTY_PACKAGES)
      setTotalRows(0)
      setLoading(false)
      setError('')
      return
    }
    try {
      setLoading(true)
      setError('')
      const [nextDashboard, list, commerce] = await Promise.all([
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
        getBiCommerce({ limit: 50 }).catch(() => null),
      ])
      const nextRows = list.items.map(toMemberRow)
      setDashboard(nextDashboard)
      if (commerce) {
        setMembershipPackages(
          commerce.packages.filter(pkg => (pkg.status || 'active') !== 'archived')
        )
      }
      setLiveRows(nextRows)
      setTotalRows(list.total)
      setSelectedRows(
        prev => new Set([...prev].filter(id => nextRows.some(row => row.user_id === id)))
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : '会员列表加载失败')
      setLiveRows([])
      setDashboard(null)
      setTotalRows(0)
    } finally {
      setLoading(false)
    }
  }, [
    filters.expiringDays,
    filters.riskMin,
    filters.status,
    filters.tier,
    flagEnabled,
    globalQuery,
  ])

  useEffect(() => {
    void loadMembers()
  }, [loadMembers])

  const sourceRows = flagEnabled ? liveRows : MOCK_MEMBERS
  const rows = useMemo(() => {
    const filtered = filterMembers(sourceRows, filters, flagEnabled ? '' : globalQuery)
    const cohortRows = behaviorCohort
      ? filtered.filter(row => row.behavior_cohort === behaviorCohort)
      : filtered
    return sortMembers(cohortRows, sortKey, sortDir)
  }, [behaviorCohort, filters, flagEnabled, globalQuery, sortDir, sortKey, sourceRows])
  const hasActiveMemberSearch = Boolean(activeMemberSearchQuery)
  const hasActiveTableFilters =
    hasActiveMemberSearch ||
    Boolean(filters.tier) ||
    Boolean(filters.status) ||
    filters.riskMin > 0 ||
    filters.expiringDays > 0 ||
    filters.notPaid ||
    Boolean(behaviorCohort)

  function submitMemberSearch(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    submitMemberSearchValue(memberSearchDraft)
  }

  function submitMemberSearchValue(value: string) {
    onSubmitSearch?.(value.trim())
  }

  function clearMemberSearch() {
    setMemberSearchDraft('')
    onSubmitSearch?.('')
  }

  function handleSort(key: string) {
    const nextKey = key as MemberSortKey
    if (nextKey === sortKey) {
      setSortDir(prev => (prev === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(nextKey)
    setSortDir(nextKey === 'risk' || nextKey === 'balance' ? 'desc' : 'asc')
  }

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
  const openMember360 = useCallback(
    async (row: MemberRow) => {
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
    },
    [flagEnabled]
  )

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

  const openMembershipSettings = useCallback(
    async (row?: MemberRow) => {
      const member = row ?? selectedMember
      if (!member) return
      setSelectedMember(member)
      setSelectedDetail(null)
      setDetailError('')
      setDrawer('membershipSettings')
      if (!flagEnabled) return
      try {
        setDetailLoading(true)
        setSelectedDetail(await getMemberDetail(member.user_id))
      } catch (err) {
        setDetailError(err instanceof Error ? err.message : '会员详情加载失败')
      } finally {
        setDetailLoading(false)
      }
    },
    [flagEnabled, selectedMember]
  )

  function syncMembershipResult(member: MemberRow, detail: MemberDetail) {
    setSelectedDetail(prev =>
      prev?.user_id === member.user_id || selectedMember?.user_id === member.user_id
        ? detail
        : prev
    )
    setSelectedMember(prev =>
      prev?.user_id === member.user_id
        ? {
            ...prev,
            tier: normalizeMembershipTier(detail.tier),
            status: normalizeStatus(detail.status),
            expires_at: shortDate(detail.expire_at),
          }
        : prev
    )
  }

  async function writeMembershipChange(
    member: MemberRow,
    operation: () => Promise<MemberDetail>,
    notice: (detail: MemberDetail) => string
  ) {
    if (!flagEnabled || membershipActionWriting) return
    setOpsActionNotice('')
    setMembershipActionError('')
    try {
      setMembershipActionWriting(true)
      const detail = await operation()
      syncMembershipResult(member, detail)
      setOpsActionNotice(notice(detail))
      await loadMembers()
    } catch (err) {
      setMembershipActionError(err instanceof Error ? err.message : '会员设置写入失败')
    } finally {
      setMembershipActionWriting(false)
    }
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

  async function upgradeMemberToVip(member: MemberRow) {
    if (!canUpgradeToVip(member)) return
    const vipPackage = findPackageForTier(membershipPackages, 'vip')
    if (!vipPackage) {
      setOpsActionNotice('未找到有效 VIP 套餐，请在会员设置中选择套餐和实收金额后开通')
      await openMembershipSettings(member)
      return
    }
    await writeMembershipChange(
      member,
      async () => {
        const result = await manualPurchaseMembership({
          user_id: member.user_id,
          package_id: vipPackage.id,
          days: 365,
          reason: 'BI 会员运营快捷开通 VIP：按套餐价入账',
        })
        notifyCommerceMutated({ userId: member.user_id, packageId: vipPackage.id })
        return result.member
      },
      detail => `已将 ${member.phone_masked} 升为 VIP，有效期至 ${shortDate(detail.expire_at)}`
    )
  }

  async function paidOpenMembership(
    member: MemberRow,
    payload: { packageId: string; days: number; amountCny?: number; reason: string }
  ) {
    await writeMembershipChange(
      member,
      async () => {
        const result = await manualPurchaseMembership({
          user_id: member.user_id,
          package_id: payload.packageId,
          days: payload.days,
          amount_cny: payload.amountCny,
          reason: payload.reason,
        })
        notifyCommerceMutated({ userId: member.user_id, packageId: payload.packageId })
        return result.member
      },
      detail =>
        `已为 ${member.phone_masked} 付费开通 ${tierLabel(detail.tier)}，有效期至 ${shortDate(detail.expire_at)}`
    )
  }

  async function saveMembershipSettings(
    member: MemberRow,
    payload: { days?: number; expireAt?: string; reason: string }
  ) {
    await writeMembershipChange(
      member,
      () =>
        updateMembership({
          user_id: member.user_id,
          days: payload.days,
          expire_at: payload.expireAt,
          reason: payload.reason,
        }),
      detail =>
        `已更新 ${member.phone_masked} 为 ${tierLabel(detail.tier)}，有效期至 ${shortDate(detail.expire_at)}`
    )
  }

  async function cancelMembership(member: MemberRow, reason: string) {
    await writeMembershipChange(
      member,
      () =>
        revokeMembership({
          user_id: member.user_id,
          reason,
        }),
      detail => `已取消 ${member.phone_masked} 会员，当前状态 ${statusLabel(normalizeStatus(detail.status))}`
    )
  }

  async function reverseSupremeMembership(
    member: MemberRow,
    payload: { amountCny?: number; reason: string }
  ) {
    await writeMembershipChange(
      member,
      async () => {
        const result = await reverseManualMembershipPurchase({
          user_id: member.user_id,
          amount_cny: payload.amountCny,
          reason: payload.reason,
        })
        notifyCommerceMutated({ userId: member.user_id, packageId: 'supreme_svip' })
        return result.member
      },
      detail =>
        `已撤回 ${member.phone_masked} 至尊SVIP，并冲销 ¥${Math.abs(payload.amountCny ?? 0) || '最近一笔'}，当前状态 ${statusLabel(normalizeStatus(detail.status))}`
    )
  }

  async function convertSupremeMembershipToFree(
    member: MemberRow,
    payload: { packageId: string; days: number; reversalAmountCny?: number; reason: string }
  ) {
    await writeMembershipChange(
      member,
      async () => {
        await reverseManualMembershipPurchase({
          user_id: member.user_id,
          amount_cny: payload.reversalAmountCny,
          reason: `${payload.reason}：manual_membership_reversal 冲销误录收入`,
        })
        const result = await manualPurchaseMembership({
          user_id: member.user_id,
          package_id: payload.packageId,
          days: payload.days,
          amount_cny: 0,
          reason: `${payload.reason}：0 元重新开通至尊SVIP`,
        })
        notifyCommerceMutated({ userId: member.user_id, packageId: payload.packageId })
        return result.member
      },
      detail =>
        `已将 ${member.phone_masked} 至尊SVIP改为0元，权益有效期至 ${shortDate(detail.expire_at)}`
    )
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
      {membershipActionError ? (
        <BiNotice tone="rose" role="alert">
          会员升级未写入：{membershipActionError}
        </BiNotice>
      ) : null}
      {opsActionNotice ? <BiNotice tone="emerald">{opsActionNotice}</BiNotice> : null}

      <div data-testid="bi-member-behavior-health-strip">
        <MemberOpsCockpit dashboard={dashboard} />
      </div>

      <BehaviorCohortTabs active={behaviorCohort} onChange={setBehaviorCohort} />

      <SavedViewsBar
        savedViews={savedViews}
        activeViewId={activeViewId}
        onApply={applyView}
        onRemove={removeView}
        onSave={saveView}
      />

      <form
        data-testid="bi-member-search-form"
        onSubmit={submitMemberSearch}
        className="rounded-2xl border border-white/10 bg-white/[0.045] p-3"
      >
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <label className="flex min-h-10 flex-1 items-center gap-2 rounded-xl border border-white/10 bg-[#101622] px-3 focus-within:border-cyan-300/45 focus-within:ring-2 focus-within:ring-cyan-300/15">
            <Search className="h-4 w-4 shrink-0 text-cyan-100/70" aria-hidden />
            <input
              data-testid="bi-member-search-input"
              value={memberSearchDraft}
              onChange={event => setMemberSearchDraft(event.target.value)}
              placeholder="搜索手机号 / 账号 / user_id"
              aria-label="搜索会员手机号或账号"
              className="min-w-0 flex-1 bg-transparent text-sm font-bold text-slate-100 outline-none placeholder:text-slate-500"
              onKeyDown={event => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  submitMemberSearchValue(event.currentTarget.value)
                }
                if (event.key === 'Escape') {
                  event.preventDefault()
                  clearMemberSearch()
                }
              }}
            />
          </label>
          <div className="flex shrink-0 items-center gap-2">
            <BiButton type="submit" variant="primary" size="sm" aria-label="搜索会员">
              搜索
            </BiButton>
            <BiButton
              type="button"
              variant="secondary"
              size="sm"
              onClick={clearMemberSearch}
              disabled={!memberSearchDraft && !activeMemberSearchQuery}
              aria-label="清空会员搜索"
            >
              清空
            </BiButton>
          </div>
        </div>
        <div className="mt-2 text-[11px] leading-5 text-slate-400">
          {activeMemberSearchQuery ? (
            <>
              当前搜索：<span className="font-mono text-cyan-100">{activeMemberSearchQuery}</span>
              <span className="mx-2 text-slate-600">·</span>
              已按手机号、账号或 user_id 查询会员。
            </>
          ) : (
            '可输入完整手机号、手机号片段、账号或 user_id；回车后刷新会员列表。'
          )}
        </div>
      </form>

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
                ? flagEnabled && !hasActiveTableFilters
                  ? 'empty'
                  : 'no-results'
                : 'ok'
        }
        errorMessage={error}
        emptyTitle="暂无会员"
        emptyHint="当前会员服务没有返回符合条件的会员。"
        noResultsHint={
          activeMemberSearchQuery
            ? `当前搜索「${activeMemberSearchQuery}」未命中会员。可换手机号、账号或 user_id 重试。`
            : '当前筛选未命中任何会员。尝试放宽 tier / risk / expiring 条件。'
        }
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
        sortKey={sortKey}
        sortDir={sortDir}
        onSort={handleSort}
        onRowClick={row => {
          void openMember360(row)
        }}
        rowAriaLabel={row => `打开 ${row.phone_masked} 学员 360`}
        rowAction={row => (
          <div className="flex flex-nowrap justify-end gap-1.5">
            <BiButton
              onClick={() => void openMembershipSettings(row)}
              variant="primary"
              size="xs"
              className="min-w-[4.75rem] whitespace-nowrap"
              aria-label={`打开 ${row.user_id} 会员设置`}
              title="选择套餐、实收金额、有效期和取消会员"
            >
              <UserCog className="h-3 w-3" aria-hidden />
              会员设置
            </BiButton>
            <BiButton
              onClick={() => openConversation(row)}
              variant="secondary"
              size="xs"
              className="min-w-[3.5rem] whitespace-nowrap"
              aria-label={`打开 ${row.user_id} 会员对话工作台`}
            >
              <MessageSquareText className="h-3 w-3" aria-hidden />
              对话
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
        onUpgradeToVip={upgradeMemberToVip}
        membershipActionWriting={membershipActionWriting}
        onOpenMembershipSettings={() => void openMembershipSettings()}
      />
      <MembershipSettingsPanel
        key={[
          selectedMember?.user_id ?? 'none',
          selectedDetail?.tier ?? '',
          selectedDetail?.expire_at ?? '',
          membershipPackages.map(pkg => pkg.id).join('|'),
        ].join(':')}
        open={drawer === 'membershipSettings'}
        member={selectedMember}
        detail={selectedDetail}
        packages={membershipPackages}
        loading={detailLoading}
        error={detailError || membershipActionError}
        writing={membershipActionWriting}
        onClose={() => setDrawer('none')}
        onPaidOpen={paidOpenMembership}
        onUpdate={saveMembershipSettings}
        onRevoke={cancelMembership}
        onReverseSupreme={reverseSupremeMembership}
        onConvertSupremeToFree={convertSupremeMembershipToFree}
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

function MembershipSettingsPanel({
  open,
  member,
  detail,
  packages,
  loading,
  error,
  writing,
  onClose,
  onPaidOpen,
  onUpdate,
  onRevoke,
  onReverseSupreme,
  onConvertSupremeToFree,
}: {
  open: boolean
  member: MemberRow | null
  detail: MemberDetail | null
  packages: ReadonlyArray<BiCommercePackage>
  loading: boolean
  error: string
  writing: boolean
  onClose: () => void
  onPaidOpen: (
    member: MemberRow,
    payload: { packageId: string; days: number; amountCny?: number; reason: string }
  ) => Promise<void> | void
  onUpdate: (
    member: MemberRow,
    payload: { days?: number; expireAt?: string; reason: string }
  ) => Promise<void> | void
  onRevoke: (member: MemberRow, reason: string) => Promise<void> | void
  onReverseSupreme: (
    member: MemberRow,
    payload: { amountCny?: number; reason: string }
  ) => Promise<void> | void
  onConvertSupremeToFree: (
    member: MemberRow,
    payload: { packageId: string; days: number; reversalAmountCny?: number; reason: string }
  ) => Promise<void> | void
}) {
  const activePackages = useMemo(
    () => packages.filter(isActivePackage),
    [packages]
  )
  const initialTier = normalizeMembershipTier(detail?.tier ?? member?.tier ?? 'vip')
  const initialPackage =
    activePackages.find(pkg => normalizeMembershipTier(pkg.tier) === initialTier) ??
    activePackages[0]
  const [packageId, setPackageId] = useState(initialPackage?.id ?? '')
  const [days, setDays] = useState('365')
  const [expireAt, setExpireAt] = useState(toDateInputValue(detail?.expire_at))
  const [amountCny, setAmountCny] = useState(initialPackage ? String(initialPackage.priceCny || '') : '')
  const [reason, setReason] = useState('BI 会员设置')
  const [formError, setFormError] = useState('')
  const selectedPackage = activePackages.find(pkg => pkg.id === packageId) ?? activePackages[0]

  if (!member) return null
  const activeMember = member
  const selectedTier = normalizeMembershipTier(selectedPackage?.tier ?? detail?.tier ?? member.tier)
  const currentTier = normalizeMembershipTier(detail?.tier ?? member.tier)
  const canReverseSupreme = currentTier === 'supreme_svip'
  const supremePackage = activePackages.find(pkg => normalizeMembershipTier(pkg.tier) === 'supreme_svip')
  const selectedPackagePrice = selectedPackage ? `¥${selectedPackage.priceCny}` : '—'

  function applyPackage(nextPackageId: string) {
    const next = activePackages.find(pkg => pkg.id === nextPackageId)
    setPackageId(nextPackageId)
    if (next) {
      setAmountCny(String(next.priceCny || ''))
    }
  }

  function parseDays(): number | null {
    const parsed = Number(days)
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 3650) return null
    return Math.floor(parsed)
  }

  function parseAmount(): number | undefined | null {
    const trimmed = amountCny.trim()
    if (!trimmed) return undefined
    const parsed = Number(trimmed)
    if (!Number.isFinite(parsed) || parsed < 0) return null
    return parsed
  }

  async function submitPaidOpen() {
    const parsedDays = parseDays()
    const parsedAmount = parseAmount()
    if (!selectedPackage || !parsedDays) {
      setFormError('请选择套餐并填写有效天数')
      return
    }
    if (parsedAmount === null) {
      setFormError('实收金额必须是非负数字')
      return
    }
    setFormError('')
    await onPaidOpen(activeMember, {
      packageId: selectedPackage.id,
      days: parsedDays,
      amountCny: parsedAmount,
      reason: reason.trim() || 'BI 会员设置：按套餐开通并入账',
    })
  }

  async function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsedDays = parseDays()
    if (!expireAt && !parsedDays) {
      setFormError('请填写有效期或有效天数')
      return
    }
    setFormError('')
    await onUpdate(activeMember, {
      days: expireAt ? undefined : parsedDays ?? undefined,
      expireAt: expireAt || undefined,
      reason: reason.trim() || 'BI 会员设置：保存有效期',
    })
  }

  async function submitRevoke() {
    if (!window.confirm(`取消 ${activeMember.phone_masked} 的会员权益？`)) return
    setFormError('')
    await onRevoke(activeMember, reason.trim() || 'BI 会员设置：取消会员')
  }

  async function submitSupremeReversal() {
    if (!canReverseSupreme) {
      setFormError('只有当前为至尊SVIP的会员可以撤回')
      return
    }
    const parsedAmount = parseAmount()
    if (parsedAmount === null) {
      setFormError('冲销金额必须是非负数字')
      return
    }
    if (parsedAmount !== undefined && parsedAmount <= 0) {
      setFormError('冲销金额需大于 0；如果要按最近一笔至尊SVIP购买金额冲销，请留空')
      return
    }
    const displayAmount = parsedAmount ?? selectedPackage?.priceCny ?? '最近一笔'
    if (
      !window.confirm(
        `撤回 ${activeMember.phone_masked} 的至尊SVIP权益，并生成 ¥${displayAmount} 的负向冲销流水？`
      )
    ) {
      return
    }
    setFormError('')
    await onReverseSupreme(activeMember, {
      amountCny: parsedAmount,
      reason: reason.trim() || 'manual_membership_reversal',
    })
  }

  async function submitSupremeFreeCorrection() {
    if (!canReverseSupreme) {
      setFormError('只有当前为至尊SVIP的会员可以改为0元')
      return
    }
    const parsedDays = parseDays()
    const parsedAmount = parseAmount()
    if (!supremePackage || !parsedDays) {
      setFormError('需要有效的至尊SVIP套餐和有效天数')
      return
    }
    if (parsedAmount === null) {
      setFormError('冲销金额必须是非负数字')
      return
    }
    if (parsedAmount !== undefined && parsedAmount <= 0) {
      setFormError('冲销金额需大于 0；如果要按最近一笔至尊SVIP购买金额冲销，请留空')
      return
    }
    const displayAmount = parsedAmount ?? supremePackage.priceCny ?? '最近一笔'
    if (
      !window.confirm(
        `把 ${activeMember.phone_masked} 的至尊SVIP改为0元？系统会先冲销 ¥${displayAmount}，再以 0 元重新开通。`
      )
    ) {
      return
    }
    setFormError('')
    await onConvertSupremeToFree(activeMember, {
      packageId: supremePackage.id,
      days: parsedDays,
      reversalAmountCny: parsedAmount,
      reason: reason.trim() || 'BI 会员设置：改为0元',
    })
  }

  return (
    <BiSidePanel
      open={open}
      onClose={onClose}
      title="会员设置"
      subtitle={`${member.phone_masked} · ${member.user_id}`}
      width="lg"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <BiButton
              onClick={() => void submitRevoke()}
              disabled={writing}
              variant="danger"
              size="sm"
              className="min-w-[5.5rem] whitespace-nowrap"
              aria-label="取消会员"
              title="撤销当前会员权益，不删除历史流水"
            >
              <ShieldOff className="h-3.5 w-3.5" aria-hidden />
              取消会员
            </BiButton>
            {canReverseSupreme ? (
              <>
                <BiButton
                  onClick={() => void submitSupremeFreeCorrection()}
                  disabled={writing || !supremePackage}
                  variant="secondary"
                  size="sm"
                  className="min-w-[6rem] whitespace-nowrap"
                  aria-label="将至尊SVIP改为0元"
                  title="先冲销误录收入，再以0元重新开通至尊SVIP"
                >
                  <CreditCard className="h-3.5 w-3.5" aria-hidden />
                  改为0元
                </BiButton>
                <BiButton
                  onClick={() => void submitSupremeReversal()}
                  disabled={writing}
                  variant="danger"
                  size="sm"
                  className="min-w-[7.5rem] whitespace-nowrap"
                  aria-label="撤回至尊SVIP"
                  title="只允许撤回至尊SVIP；会生成负向账务流水冲销收入"
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                  撤回至尊SVIP
                </BiButton>
              </>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <BiButton
              onClick={() => void submitPaidOpen()}
              disabled={writing || activePackages.length === 0}
              variant="primary"
              size="sm"
              className="min-w-[6.25rem] whitespace-nowrap"
              aria-label="付费开通并入账"
              title="默认按套餐价入账；金额填 0 即 0 元开通，填其他数字即自定义收入"
            >
              <CreditCard className="h-3.5 w-3.5" aria-hidden />
              收款开通
            </BiButton>
          </div>
        </div>
      }
    >
      <form
        data-testid="bi-member-membership-settings"
        onSubmit={submitUpdate}
        className="space-y-4"
      >
        {loading ? <BiNotice tone="sky">正在加载会员状态...</BiNotice> : null}
        {error ? <BiNotice tone="rose">会员设置加载失败：{error}</BiNotice> : null}
        {formError ? <BiNotice tone="rose">{formError}</BiNotice> : null}

        <section className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <StatusTile label="当前等级" value={tierLabel(detail?.tier ?? member.tier)} tone={TIER_TONE[normalizeMembershipTier(detail?.tier ?? member.tier)]} />
          <StatusTile label="当前状态" value={statusLabel(normalizeStatus(detail?.status ?? member.status))} tone={STATUS_TONE[normalizeStatus(detail?.status ?? member.status)]} />
          <StatusTile label="当前有效期" value={toDateInputValue(detail?.expire_at) || member.expires_at || '—'} tone="sky" />
        </section>

        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-black text-white">开通套餐</h3>
              <p className="mt-0.5 text-xs text-slate-400">
                套餐是唯一选择；等级、点数、次数和默认收入都从套餐派生。
              </p>
            </div>
            <BiStatusPill tone="sky" label={`${activePackages.length} 个可用套餐`} size="sm" />
          </div>
          <div className="grid grid-cols-1 gap-3">
            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">套餐</span>
              <BiSelect
                value={selectedPackage?.id ?? ''}
                onChange={event => applyPackage(event.target.value)}
                wrapperClassName="w-full"
                aria-label="选择会员套餐"
              >
                {activePackages.map(pkg => (
                  <option key={pkg.id} value={pkg.id}>
                    {pkg.name} · {tierLabel(pkg.tier)} · {pkg.points}点
                  </option>
                ))}
                {activePackages.length === 0 ? <option value="">暂无可用套餐</option> : null}
              </BiSelect>
            </label>
          </div>
          {selectedPackage ? (
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-4">
              <PackageMetric label="默认收入" value={selectedPackagePrice} />
              <PackageMetric label="等级" value={tierLabel(selectedTier)} />
              <PackageMetric label="点数" value={`${selectedPackage.points}`} />
              <PackageMetric label="次数" value={`${selectedPackage.turns}`} />
            </div>
          ) : null}
        </section>

        <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
          <h3 className="text-sm font-black text-white">有效期与实收金额</h3>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">有效天数</span>
              <input
                type="number"
                min={1}
                max={3650}
                value={days}
                onChange={event => setDays(event.target.value)}
                className={MEMBERSHIP_INPUT_CLASS}
                aria-label="设置有效天数"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">有效期</span>
              <input
                type="date"
                value={expireAt}
                onChange={event => setExpireAt(event.target.value)}
                className={MEMBERSHIP_INPUT_CLASS}
                aria-label="设置会员有效期"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-slate-400">实收 ¥</span>
              <input
                inputMode="decimal"
                value={amountCny}
                onChange={event => setAmountCny(event.target.value)}
                className={MEMBERSHIP_INPUT_CLASS}
                aria-label="设置实收金额"
              />
            </label>
          </div>
          <p className="mt-2 text-[11px] leading-5 text-slate-400">
            不改金额时按套餐价入账；填 0 即 0 元开通，填其他数字即按人工实收金额入账。
            当前为至尊SVIP时，“撤回至尊SVIP”会按这里的金额生成负向冲销；留空则后端按最近一笔至尊SVIP购买金额推断。
            “改为0元”会先冲销误录收入，再立即以 0 元重新开通至尊SVIP。
          </p>
          <label className="mt-3 block space-y-1">
            <span className="text-[11px] text-slate-400">原因 / 备注</span>
            <input
              value={reason}
              onChange={event => setReason(event.target.value)}
              className={MEMBERSHIP_INPUT_CLASS}
              aria-label="设置会员变更原因"
            />
          </label>
        </section>

        <div className="flex justify-end">
          <BiButton
            type="submit"
            disabled={writing}
            variant="secondary"
            size="sm"
            aria-label="保存会员有效期"
          >
            <Save className="h-3.5 w-3.5" aria-hidden />
            保存有效期
          </BiButton>
        </div>
      </form>
    </BiSidePanel>
  )
}

function StatusTile({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'sky' | 'amber' | 'emerald' | 'rose' | 'slate'
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-3">
      <div className="text-[11px] font-bold text-slate-400">{label}</div>
      <div className="mt-2">
        <BiStatusPill tone={tone} label={value} size="md" />
      </div>
    </div>
  )
}

function PackageMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-slate-950/25 px-3 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-black text-slate-100">{value}</div>
    </div>
  )
}

function BehaviorCohortTabs({
  active,
  onChange,
}: {
  active: string
  onChange: (next: string) => void
}) {
  return (
    <div
      data-testid="bi-member-behavior-cohort-tabs"
      className="flex flex-wrap items-center gap-2 text-xs"
      aria-label="按行为队列筛选会员"
    >
      {BEHAVIOR_COHORTS.map(item => (
        <button
          key={item.key || 'all'}
          type="button"
          onClick={() => onChange(item.key)}
          aria-pressed={active === item.key}
          className={`rounded-full border px-3 py-1 font-bold transition ${
            active === item.key
              ? 'border-amber-300/35 bg-amber-300/15 text-amber-50'
              : 'border-white/10 bg-white/[0.045] text-slate-300 hover:border-white/20 hover:bg-white/[0.07]'
          }`}
        >
          {item.label}
        </button>
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
        label="至尊SVIP"
        active={filters.tier === 'supreme_svip'}
        onClick={() => onChange({ ...filters, tier: 'supreme_svip' })}
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
  if (key === 'phone')
    return (
      <div className="min-w-[132px]">
        <div className="font-mono font-black text-slate-100">{row.phone_masked}</div>
        <div className="mt-0.5 truncate font-mono text-[10px] text-slate-500">{row.user_id}</div>
      </div>
    )
  if (key === 'tier')
    return <BiStatusPill tone={TIER_TONE[row.tier]} label={tierLabel(row.tier)} />
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
  if (key === 'behavior_report')
    return <span className="tabular-nums">{row.behavior_learning_report_7d ?? 0}</span>
  if (key === 'behavior_history')
    return <span className="tabular-nums">{row.behavior_history_7d ?? 0}</span>
  if (key === 'behavior_cohort') {
    const cohort = row.behavior_cohort || ''
    const tone =
      cohort && cohort in BEHAVIOR_COHORT_TONE
        ? BEHAVIOR_COHORT_TONE[cohort as keyof typeof BEHAVIOR_COHORT_TONE]
        : 'emerald'
    return (
      <div className="max-w-[220px] space-y-1">
        <BiStatusPill tone={tone} label={behaviorCohortLabel(cohort)} />
        {row.behavior_reasons?.[0] ? (
          <div
            className="truncate text-[11px] text-slate-400"
            title={row.behavior_reasons.join('；')}
          >
            {row.behavior_reasons[0]}
          </div>
        ) : null}
      </div>
    )
  }
  if (key === 'behavior_next_action')
    return (
      <span className="inline-flex rounded-full border border-white/10 bg-white/[0.055] px-2 py-0.5 text-[11px] font-bold text-slate-200">
        {row.behavior_next_action ?? '观察'}
      </span>
    )
  return null
}
