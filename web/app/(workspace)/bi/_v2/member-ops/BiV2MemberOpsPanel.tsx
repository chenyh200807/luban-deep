/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Filter, Save, Settings2 } from 'lucide-react'
import { useCallback, useMemo, useState, useSyncExternalStore } from 'react'
import {
  BiDataTable,
  BiMoneyCell,
  BiStatusPill,
  BI_STATUS_PILL_TONE,
  type BiTableColumn,
} from '@/components/bi-v2'
import { Member360Drawer } from './Member360Drawer'
import { ConversationReviewDrawer } from './ConversationReviewDrawer'
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

function readSavedViewsClient(): SavedView[] {
  try {
    const raw = window.localStorage.getItem(SAVED_VIEWS_STORAGE_KEY)
    if (!raw) return EMPTY_VIEWS
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? (parsed as SavedView[]) : EMPTY_VIEWS
  } catch {
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
  try {
    window.localStorage.setItem(SAVED_VIEWS_STORAGE_KEY, JSON.stringify(next))
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
  const [drawer, setDrawer] = useState<'none' | 'member360' | 'conversation'>('none')
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set())

  const rows = useMemo(
    () => filterMembers(MOCK_MEMBERS, filters, globalQuery),
    [filters, globalQuery]
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
    const name = window.prompt('保存当前视图为：', `自定义视图 ${savedViews.length + 1}`)
    if (!name) return
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
  function openMember360(row: MemberRow) {
    setSelectedMember(row)
    setDrawer('member360')
  }

  function openConversation() {
    setDrawer('conversation')
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
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          BI_CRM_V2_ENABLED 未开启。当前为 Batch 2 静态原型；Batch 2.5+ 接入真实
          <code className="mx-1 font-mono">/api/v1/bi/members</code> 与
          <code className="font-mono">/api/v1/member/&lt;user_id&gt;/*</code>。
        </div>
      ) : (
        // Round 4 S5: honest copy — list/360/conversation-view path is the
        // only one actually wired to backend (via useAuditedAction). Member
        // table still mock until /api/v1/bi/members ships.
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
          BI_CRM_V2_ENABLED flag 已开启 · 数据源待接入 /api/v1/bi/members（当前列表为 dev-only
          mock）；对话回顾 view-audit 已通过 useAuditedAction 真实写入。
        </div>
      )}

      <SavedViewsBar
        savedViews={savedViews}
        activeViewId={activeViewId}
        onApply={applyView}
        onRemove={removeView}
        onSave={saveView}
      />

      <CommonFilters filters={filters} onChange={setFilters} />

      <div className="flex items-center justify-between text-xs text-slate-500">
        <button
          type="button"
          onClick={() => setAdvancedOpen(v => !v)}
          className="inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-1 hover:bg-slate-50"
          aria-expanded={advancedOpen}
          aria-controls="bi-v2-advanced-filters"
        >
          <Filter className="h-3 w-3" aria-hidden /> {advancedOpen ? '收起高级筛选' : '高级筛选'}
        </button>
        <button
          type="button"
          onClick={() => setColumnPickerOpen(v => !v)}
          className="inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-1 hover:bg-slate-50"
          aria-expanded={columnPickerOpen}
          aria-controls="bi-v2-column-picker"
        >
          <Settings2 className="h-3 w-3" aria-hidden /> 列设置 ({columns.length})
        </button>
      </div>

      {advancedOpen ? <AdvancedFilters filters={filters} onChange={setFilters} /> : null}
      {columnPickerOpen ? <ColumnPicker columns={columns} onToggle={toggleColumn} /> : null}

      <BiDataTable<MemberRow>
        columns={columnDefs}
        rows={rows}
        rowKey={r => r.user_id}
        status={rows.length === 0 ? 'no-results' : 'ok'}
        emptyTitle="暂无会员"
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
          <div className="flex justify-end gap-1">
            <button
              type="button"
              onClick={() => openMember360(row)}
              className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
              aria-label={`打开 ${row.user_id} 学员 360`}
            >
              360
            </button>
          </div>
        )}
        pageSize={50}
        cursorFooter={
          <>
            <span>
              筛选后 {rows.length} 行（mock total {MOCK_MEMBERS.length}）· 真实 cursor 分页由 Batch
              2.5 接 /api/v1/bi/members 启用
            </span>
            <span>{selectedRows.size > 0 ? `已选 ${selectedRows.size}` : ''}</span>
          </>
        }
      />

      <BulkActions
        selected={selectedRows.size}
        // Bulk actions are not connected to a real audited write yet — Round 3 B
        // will replace these stubs with useAuditedAction. For now they only
        // clear local selection so the UI no longer falsely implies a server
        // write occurred.
        onAddToFollowup={() => setSelectedRows(new Set())}
        onMarkContacted={() => setSelectedRows(new Set())}
      />

      <Member360Drawer
        open={drawer === 'member360'}
        member={selectedMember}
        onClose={() => setDrawer('none')}
        onOpenConversation={openConversation}
      />
      <ConversationReviewDrawer
        open={drawer === 'conversation'}
        member={selectedMember}
        onClose={() => setDrawer('member360')}
      />
    </section>
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
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-slate-500">我的视图：</span>
      {savedViews.length === 0 ? <span className="text-slate-400">暂无（点右侧保存）</span> : null}
      {savedViews.map(v => (
        <span
          key={v.id}
          className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5"
        >
          <button
            type="button"
            onClick={() => onApply(v)}
            className={`text-[11px] ${activeViewId === v.id ? 'font-semibold text-slate-900' : 'text-slate-700'}`}
            aria-label={`应用视图 ${v.name}`}
          >
            {v.name}
          </button>
          <button
            type="button"
            onClick={() => onRemove(v.id)}
            className="text-slate-400 hover:text-rose-600"
            aria-label={`删除视图 ${v.name}`}
          >
            ×
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={onSave}
        className="ml-auto inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-slate-700 hover:bg-slate-50"
        aria-label="把当前筛选与列设置保存为私有视图"
      >
        <Save className="h-3 w-3" aria-hidden /> 保存视图
      </button>
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
      <button
        type="button"
        onClick={() => onChange(DEFAULT_FILTERS)}
        className="text-[11px] text-slate-500 hover:text-slate-900"
        aria-label="清空筛选"
      >
        清空
      </button>
    </div>
  )
}

function Pill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full px-3 py-1 ${
        active
          ? 'bg-slate-900 text-white'
          : 'border border-slate-200 bg-white text-slate-700 hover:border-slate-400'
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
    <div id="bi-v2-advanced-filters" className="rounded border border-slate-200 bg-white p-3">
      <h4 className="text-xs font-semibold text-slate-700">高级筛选</h4>
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-3">
        <label className="text-xs text-slate-600">
          状态
          <select
            className="ml-2 rounded border border-slate-200 px-1 py-0.5"
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
        <label className="text-xs text-slate-600">
          风险阈值
          <input
            type="number"
            step="0.05"
            min={0}
            max={1}
            value={filters.riskMin}
            onChange={e => onChange({ ...filters, riskMin: Number(e.target.value) })}
            className="ml-2 w-20 rounded border border-slate-200 px-1 py-0.5"
            aria-label="风险阈值"
          />
        </label>
        <label className="text-xs text-slate-600">
          到期天数（0 = 不限）
          <input
            type="number"
            min={0}
            max={365}
            value={filters.expiringDays}
            onChange={e => onChange({ ...filters, expiringDays: Number(e.target.value) })}
            className="ml-2 w-20 rounded border border-slate-200 px-1 py-0.5"
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
    <div id="bi-v2-column-picker" className="rounded border border-slate-200 bg-white p-3">
      <h4 className="text-xs font-semibold text-slate-700">列设置</h4>
      <div className="mt-2 grid grid-cols-2 gap-1 md:grid-cols-3">
        {ALL_COLUMNS.map(c => {
          const checked = columns.includes(c.key)
          return (
            <label key={c.key} className="flex items-center gap-2 text-xs text-slate-700">
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
      <p className="mt-2 text-[10px] text-slate-500">
        最少保留 3 列。设置保存在私有视图（保存视图按钮）。
      </p>
    </div>
  )
}

function BulkActions({
  selected,
  onAddToFollowup,
  onMarkContacted,
}: {
  selected: number
  onAddToFollowup: () => void
  onMarkContacted: () => void
}) {
  return (
    <div
      className={`flex items-center justify-between rounded border px-3 py-2 text-xs ${
        selected > 0
          ? 'border-slate-300 bg-slate-50'
          : 'border-dashed border-slate-200 bg-white text-slate-400'
      }`}
      aria-live="polite"
    >
      <span>{selected > 0 ? `已选 ${selected} 位会员` : '选择会员后可批量执行低风险动作'}</span>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={selected === 0 || selected > 50}
          onClick={onMarkContacted}
          className="rounded border border-slate-200 px-2 py-1 text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="批量标记已联系（≤ 50）"
        >
          标记已联系
        </button>
        <button
          type="button"
          disabled={selected === 0 || selected > 100}
          onClick={onAddToFollowup}
          className="rounded border border-slate-200 px-2 py-1 text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="加入跟进队列（≤ 100）"
        >
          加入跟进队列
        </button>
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
  if (key === 'last_active') return <span className="text-slate-600">{row.last_active}</span>
  if (key === 'balance')
    return <BiMoneyCell amount={row.balance_points} currency="POINT" align="right" />
  if (key === 'expires_at') return <span className="text-slate-600">{row.expires_at}</span>
  if (key === 'paid_first')
    return <span className="text-slate-600">{row.paid_at_first ?? '—'}</span>
  if (key === 'region') return row.region ?? '—'
  if (key === 'notes') return <span className="tabular-nums">{row.notes_count ?? 0}</span>
  if (key === 'feedback') return <span className="tabular-nums">{row.feedback_count ?? 0}</span>
  return null
}
