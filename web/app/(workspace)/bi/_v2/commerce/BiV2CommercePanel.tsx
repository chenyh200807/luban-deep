/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Calendar, Pencil, Plus, RefreshCw, Save, Trash2, UserPlus, X } from 'lucide-react'
import type { FormEvent, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BiButton,
  BiDataTable,
  BiDateTime,
  BiIdToken,
  BiMoneyCell,
  BiNotice,
  BiSelect,
  BiStatusPill,
  BiV2DataSourceBanner,
  BI_SEVERITY_TONE,
  BI_TRUST_TONE,
  type BiStatusTone,
  type BiTableColumn,
} from '@/components/bi-v2'
import {
  getBiCommerce,
  type BiCommerceAnomaly,
  type BiCommerceData,
  type BiCommerceLedgerRow,
  type BiCommercePackage,
  type BiCommerceRechargeRecord,
} from '@/lib/bi-api'
import { deleteMembershipPackage, manualPurchaseMembership, upsertMembershipPackage } from '@/lib/member-api'
import { CommerceCockpit } from '@/components/bi-cockpit/CommerceCockpit'

type Tab = 'recharges' | 'ledger' | 'packages'

export type BiV2CommercePanelProps = {
  flagEnabled: boolean
  globalQuery?: string
}

const KIND_TONE: Record<string, BiStatusTone> = {
  credit: 'emerald',
  debit: 'slate',
  refund: 'rose',
  manual: 'amber',
}

const STATUS_TONE: Record<string, BiStatusTone> = {
  confirmed: 'emerald',
  legacy: 'amber',
  active: 'emerald',
  draft: 'amber',
  archived: 'slate',
}

const EMPTY_RECHARGES: BiCommerceRechargeRecord[] = []
const EMPTY_WALLET_ROWS: BiCommerceLedgerRow[] = []
const EMPTY_PACKAGE_ROWS: BiCommercePackage[] = []
const EMPTY_PACKAGE_FORM = {
  id: '',
  label: '',
  tier: 'vip',
  points: '9000',
  turns: '450',
  price: '198',
  originalPrice: '',
  badge: '',
  per: '',
  desc: '',
  status: 'active',
  reason: '',
}

type PackageFormState = typeof EMPTY_PACKAGE_FORM

function commerceSourceLabel(value: string) {
  if (!value) return '--'
  if (value === 'member_console_auth_bootstrap') return 'auth bootstrap'
  return value.replace(/_/g, ' ')
}

function monthKey(value: string) {
  return value ? value.slice(0, 7) : ''
}

function trustTone(value: string): BiStatusTone {
  return value === 'A' || value === 'B' || value === 'C' || value === 'D'
    ? BI_TRUST_TONE[value]
    : 'slate'
}

function severityTone(value: string): BiStatusTone {
  return value === 'critical' || value === 'high' || value === 'medium' || value === 'low'
    ? BI_SEVERITY_TONE[value]
    : 'slate'
}

function tableStatus(loading: boolean, error: string, rowCount: number) {
  if (loading) return 'loading' as const
  if (error) return 'error' as const
  return rowCount === 0 ? ('empty' as const) : ('ok' as const)
}

function matchesQuery(values: Array<string | number | null | undefined>, query: string) {
  if (!query) return true
  const normalized = query.toLowerCase()
  return values.some(value =>
    String(value ?? '')
      .toLowerCase()
      .includes(normalized)
  )
}

export function BiV2CommercePanel({ flagEnabled, globalQuery = '' }: BiV2CommercePanelProps) {
  const [tab, setTab] = useState<Tab>('recharges')
  const [month, setMonth] = useState('')
  const [expandedRechargeId, setExpandedRechargeId] = useState<string | null>(null)
  const [expandedLedgerId, setExpandedLedgerId] = useState<string | null>(null)
  const [data, setData] = useState<BiCommerceData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!flagEnabled) return
    setLoading(true)
    setError('')
    try {
      setData(await getBiCommerce({ limit: 150 }))
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '商品账务 API 加载失败')
    } finally {
      setLoading(false)
    }
  }, [flagEnabled])

  useEffect(() => {
    if (!flagEnabled) {
      setData(null)
      setError('')
      return
    }
    void load()
  }, [flagEnabled, load])

  const rechargeRows = useMemo(
    () => data?.rechargeRecords ?? EMPTY_RECHARGES,
    [data?.rechargeRecords]
  )
  const ledgerRows = useMemo(() => data?.ledger ?? EMPTY_WALLET_ROWS, [data?.ledger])
  const packageRows = useMemo(() => data?.packages ?? EMPTY_PACKAGE_ROWS, [data?.packages])
  const activePackageRows = useMemo(
    () => packageRows.filter(row => (row.status || 'active') === 'active'),
    [packageRows]
  )
  const summary = data?.summary
  const normalizedGlobalQuery = globalQuery.trim().toLowerCase()

  const months = useMemo(() => {
    const keys = [
      ...rechargeRows.map(row => monthKey(row.createdAt)),
      ...ledgerRows.map(row => monthKey(row.effectiveAt)),
    ].filter(Boolean)
    return Array.from(new Set(keys)).sort().reverse()
  }, [ledgerRows, rechargeRows])

  const filteredRecharges = useMemo(
    () =>
      rechargeRows.filter(
        row =>
          (!month || monthKey(row.createdAt) === month) &&
          matchesQuery(
            [
              row.id,
              row.userId,
              row.channel,
              row.status,
              row.ledgerEventId,
              row.idempotencyKey,
              row.amountCny ?? undefined,
              row.points,
            ],
            normalizedGlobalQuery
          )
      ),
    [month, normalizedGlobalQuery, rechargeRows]
  )
  const filteredLedger = useMemo(
    () =>
      ledgerRows.filter(
        row =>
          (!month || monthKey(row.effectiveAt) === month) &&
          matchesQuery(
            [
              row.id,
              row.userId,
              row.kind,
              row.eventType,
              row.referenceType,
              row.referenceId,
              row.idempotencyKey,
              row.amount,
            ],
            normalizedGlobalQuery
          )
      ),
    [ledgerRows, month, normalizedGlobalQuery]
  )
  const filteredPackages = useMemo(
    () =>
      packageRows.filter(row =>
        matchesQuery([row.id, row.name, row.tier, row.status, row.authority], normalizedGlobalQuery)
      ),
    [normalizedGlobalQuery, packageRows]
  )

  useEffect(() => {
    if (!normalizedGlobalQuery) return
    if (filteredRecharges.length > 0) {
      setTab('recharges')
    } else if (filteredLedger.length > 0) {
      setTab('ledger')
    } else if (filteredPackages.length > 0) {
      setTab('packages')
    }
  }, [
    filteredLedger.length,
    filteredPackages.length,
    filteredRecharges.length,
    normalizedGlobalQuery,
  ])

  const rechargeColumns = useMemo<BiTableColumn<BiCommerceRechargeRecord>[]>(
    () => [
      {
        key: 'id',
        label: '记录 ID',
        render: row => <BiIdToken value={row.id || row.ledgerEventId} />,
      },
      {
        key: 'user',
        label: '会员',
        render: row => <BiIdToken value={row.userId} head={8} tail={5} />,
      },
      {
        key: 'points',
        label: '入账(点)',
        align: 'right',
        render: row => (
          <BiMoneyCell
            amount={row.points}
            currency="POINT"
            trust={row.trust as 'A' | 'B' | 'C' | 'D'}
          />
        ),
      },
      { key: 'channel', label: '来源', render: row => commerceSourceLabel(row.channel) },
      {
        key: 'status',
        label: '状态',
        render: row => (
          <BiStatusPill tone={STATUS_TONE[row.status] ?? 'slate'} label={row.status || 'unknown'} />
        ),
      },
      { key: 'at', label: '时间', render: row => <BiDateTime value={row.createdAt} /> },
    ],
    []
  )

  const ledgerColumns = useMemo<BiTableColumn<BiCommerceLedgerRow>[]>(
    () => [
      {
        key: 'id',
        label: 'ledger_event_id',
        render: row => <BiIdToken value={row.id} />,
      },
      {
        key: 'user',
        label: '会员',
        render: row => <BiIdToken value={row.userId} head={8} tail={5} />,
      },
      {
        key: 'kind',
        label: '类型',
        render: row => (
          <BiStatusPill tone={KIND_TONE[row.kind] ?? 'slate'} label={row.kind || row.eventType} />
        ),
      },
      {
        key: 'amount',
        label: '金额(点)',
        align: 'right',
        render: row => (
          <BiMoneyCell
            amount={row.amount}
            currency="POINT"
            trust={row.trust as 'A' | 'B' | 'C' | 'D'}
          />
        ),
      },
      {
        key: 'authority',
        label: 'authority',
        render: row => <BiIdToken value={row.authority || '--'} head={16} tail={0} />,
      },
      { key: 'at', label: '时间', render: row => <BiDateTime value={row.effectiveAt} /> },
    ],
    []
  )

  if (!flagEnabled) {
    return (
      <section className="space-y-4">
        <BiV2DataSourceBanner tone="amber">
          BI_COMMERCE_V2_ENABLED 未开启 · 商品账务不会展示半成品数据。开启前需完成只读 API、 admin
          鉴权、mock 边界与前端 smoke。
        </BiV2DataSourceBanner>
      </section>
    )
  }

  return (
    <section className="space-y-5">
      <BiV2DataSourceBanner
        tone="sky"
        action={
          <BiButton
            onClick={() => void load()}
            variant="primary"
            size="xs"
            aria-label="刷新商品账务"
          >
            <RefreshCw className="h-3 w-3" aria-hidden />
            刷新
          </BiButton>
        }
      >
        BI_COMMERCE_V2_ENABLED 已开启 · 套餐读取 {data?.authority.packages ?? 'loading'}
        ，充值记录读取 {data?.authority.recharge_records ?? 'loading'}，钱包流水读取{' '}
        {data?.authority.wallet_ledger ?? 'loading'}；订单 authority 仍为{' '}
        {data?.authority.orders ?? 'pending'}，所有修账写动作禁用。
      </BiV2DataSourceBanner>

      {error ? (
        <BiNotice tone="rose">商品账务 API 不可用：{error}。当前不会回退到 mock。</BiNotice>
      ) : null}

      {data?.warnings.length ? <BiNotice tone="amber">{data.warnings.join(' · ')}</BiNotice> : null}

      {globalQuery.trim() ? (
        <BiNotice tone="slate">
          全局搜索：<code className="font-mono">{globalQuery.trim()}</code> · 当前按订单 / 流水 /
          会员 / 套餐字段过滤商品账务读模型。
        </BiNotice>
      ) : null}

      <CommerceCockpit data={data} />

      <ManualMembershipPurchasePanel
        packages={activePackageRows}
        onCreated={async () => {
          setTab('recharges')
          await load()
        }}
      />

      <div className="flex items-center gap-2 border-b border-white/10">
        <TabBtn
          active={tab === 'recharges'}
          onClick={() => setTab('recharges')}
          label={`充值记录 (${filteredRecharges.length})`}
        />
        <TabBtn
          active={tab === 'ledger'}
          onClick={() => setTab('ledger')}
          label={`钱包流水 (${filteredLedger.length})`}
        />
        <TabBtn
          active={tab === 'packages'}
          onClick={() => setTab('packages')}
          label={`套餐权益 (${filteredPackages.length})`}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-300">
        <label className="inline-flex items-center gap-2">
          <Calendar className="h-3 w-3" aria-hidden />
          自然月
          <BiSelect
            value={month}
            onChange={event => setMonth(event.target.value)}
            aria-label="按自然月筛选"
          >
            <option value="">全部</option>
            {months.map(item => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </BiSelect>
        </label>
        <BiButton
          onClick={() => setMonth('')}
          variant="ghost"
          size="xs"
          className="ml-auto"
          aria-label="清空账务筛选"
        >
          清空筛选
        </BiButton>
      </div>

      {tab === 'recharges' ? (
        <div>
          <BiDataTable<BiCommerceRechargeRecord>
            columns={rechargeColumns}
            rows={filteredRecharges}
            rowKey={row => row.ledgerEventId || row.id}
            status={tableStatus(loading, error, filteredRecharges.length)}
            errorMessage={error}
            emptyTitle="暂无充值记录"
            emptyHint="支付/订单 authority 未上线或无订单写入；赠点、初始化、人工授信只在钱包流水中展示。"
            rowAction={row => (
              <BiButton
                onClick={() =>
                  setExpandedRechargeId(
                    expandedRechargeId === row.ledgerEventId ? null : row.ledgerEventId
                  )
                }
                variant="secondary"
                size="xs"
                aria-label={`查看充值记录 ${row.id || row.ledgerEventId} 详情`}
              >
                {expandedRechargeId === row.ledgerEventId ? '收起' : '详情'}
              </BiButton>
            )}
          />
          {expandedRechargeId ? (
            <RechargeDetailRow
              row={rechargeRows.find(row => row.ledgerEventId === expandedRechargeId)}
              ledger={ledgerRows.find(row => row.id === expandedRechargeId)}
            />
          ) : null}
        </div>
      ) : null}

      {tab === 'ledger' ? (
        <div>
          <BiDataTable<BiCommerceLedgerRow>
            columns={ledgerColumns}
            rows={filteredLedger}
            rowKey={row => row.id}
            status={tableStatus(loading, error, filteredLedger.length)}
            errorMessage={error}
            emptyTitle="暂无钱包流水"
            emptyHint="wallet_ledger 与 legacy ledger 均无可展示记录。"
            rowAction={row => (
              <BiButton
                onClick={() => setExpandedLedgerId(expandedLedgerId === row.id ? null : row.id)}
                variant="secondary"
                size="xs"
                aria-label={`查看 ${row.id} 元数据`}
              >
                {expandedLedgerId === row.id ? '收起' : '元数据'}
              </BiButton>
            )}
          />
          {expandedLedgerId ? (
            <LedgerDetailRow row={ledgerRows.find(row => row.id === expandedLedgerId)} />
          ) : null}
        </div>
      ) : null}

      {tab === 'packages' ? (
        <PackageManagementPanel
          packages={filteredPackages}
          loading={loading}
          error={error}
          onChanged={async () => {
            setTab('packages')
            await load()
          }}
        />
      ) : null}
    </section>
  )
}

function ManualMembershipPurchasePanel({
  packages,
  onCreated,
}: {
  packages: ReadonlyArray<BiCommercePackage>
  onCreated: () => Promise<void> | void
}) {
  const [userId, setUserId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [phone, setPhone] = useState('')
  const [packageId, setPackageId] = useState('')
  const [days, setDays] = useState('365')
  const [amountCny, setAmountCny] = useState('')
  const [reason, setReason] = useState('线下收款')
  const [submitting, setSubmitting] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const selectedPackage = useMemo(
    () => packages.find(item => item.id === packageId) ?? packages[0],
    [packageId, packages]
  )

  useEffect(() => {
    if (!selectedPackage) return
    if (!packageId) setPackageId(selectedPackage.id)
    if (!amountCny) setAmountCny(String(selectedPackage.priceCny || ''))
  }, [amountCny, packageId, selectedPackage])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const parsedDays = Number(days)
    const parsedAmount = amountCny.trim() ? Number(amountCny) : undefined
    if (!userId.trim() || !selectedPackage || !Number.isFinite(parsedDays) || parsedDays <= 0) {
      setError('请填写会员 ID、套餐和有效天数')
      return
    }
    if (parsedAmount !== undefined && (!Number.isFinite(parsedAmount) || parsedAmount < 0)) {
      setError('实收金额必须是非负数字')
      return
    }
    setSubmitting(true)
    setError('')
    setNotice('')
    try {
      const result = await manualPurchaseMembership({
        user_id: userId.trim(),
        package_id: selectedPackage.id,
        days: Math.floor(parsedDays),
        reason: reason.trim(),
        phone: phone.trim() || undefined,
        display_name: displayName.trim() || undefined,
        amount_cny: parsedAmount,
      })
      setNotice(`已开通 ${result.member.tier}，收入流水 ${result.ledger_event_id || result.purchase_id}`)
      setUserId('')
      setDisplayName('')
      setPhone('')
      await Promise.resolve(onCreated())
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : '人工开通失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.06] p-4 text-xs shadow-lg shadow-black/10"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-black text-white">
            <UserPlus className="h-4 w-4 text-cyan-200" aria-hidden />
            人工开通会员
          </h3>
        </div>
        <BiButton
          type="submit"
          variant="primary"
          size="xs"
          disabled={submitting || packages.length === 0}
          aria-label="提交人工开通会员"
        >
          {submitting ? '写入中' : '开通'}
        </BiButton>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3 xl:grid-cols-6">
        <label className="space-y-1">
          <span className="text-[11px] text-slate-400">会员 ID</span>
          <input
            value={userId}
            onChange={event => setUserId(event.target.value)}
            className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
            placeholder="user_id / 手机号"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-slate-400">姓名</span>
          <input
            value={displayName}
            onChange={event => setDisplayName(event.target.value)}
            className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
            placeholder="选填"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-slate-400">手机号</span>
          <input
            value={phone}
            onChange={event => setPhone(event.target.value)}
            className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
            placeholder="选填"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-slate-400">套餐</span>
          <BiSelect
            value={selectedPackage?.id ?? ''}
            onChange={event => {
              const next = packages.find(item => item.id === event.target.value)
              setPackageId(event.target.value)
              setAmountCny(next ? String(next.priceCny || '') : '')
            }}
            aria-label="选择人工开通套餐"
          >
            {packages.map(item => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.points}点
              </option>
            ))}
          </BiSelect>
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-slate-400">有效天数</span>
          <input
            type="number"
            min={1}
            max={3650}
            value={days}
            onChange={event => setDays(event.target.value)}
            className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
          />
        </label>
        <label className="space-y-1">
          <span className="text-[11px] text-slate-400">实收 ¥</span>
          <input
            type="number"
            min={0}
            step="0.01"
            value={amountCny}
            onChange={event => setAmountCny(event.target.value)}
            className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
          />
        </label>
      </div>

      <label className="mt-2 block space-y-1">
        <span className="text-[11px] text-slate-400">备注</span>
        <input
          value={reason}
          onChange={event => setReason(event.target.value)}
          className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
          placeholder="线下收款、补录、企业转账"
        />
      </label>

      {selectedPackage ? (
        <p className="mt-2 text-[11px] text-slate-400">
          当前套餐：{selectedPackage.name} · {selectedPackage.points} 点 · ¥
          {selectedPackage.priceCny}
        </p>
      ) : null}
      {notice ? <BiNotice tone="emerald">{notice}</BiNotice> : null}
      {error ? <BiNotice tone="rose">{error}</BiNotice> : null}
    </form>
  )
}

function TabBtn({
  active,
  onClick,
  label,
}: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className={`-mb-px border-b-2 px-3 py-2 text-xs ${
        active
          ? 'border-cyan-300 text-cyan-100'
          : 'border-transparent text-slate-400 hover:text-slate-100'
      }`}
    >
      {label}
    </button>
  )
}

function RechargeDetailRow({
  row,
  ledger,
}: {
  row?: BiCommerceRechargeRecord
  ledger?: BiCommerceLedgerRow
}) {
  if (!row) return null
  return (
    <div className="mt-2 rounded-2xl border border-white/10 bg-white/[0.045] p-3 text-xs">
      <h4 className="text-sm font-black text-white">充值记录 {row.id || row.ledgerEventId}</h4>
      <ul className="mt-2 space-y-1 text-slate-300">
        <li>
          会员：
          <BiIdToken value={row.userId} />
        </li>
        <li>
          充值：
          <BiMoneyCell
            amount={row.points}
            currency="POINT"
            align="left"
            trust={row.trust as 'A' | 'B' | 'C' | 'D'}
          />
        </li>
        <li>
          来源：{commerceSourceLabel(row.channel)} · 状态：{row.status}
        </li>
        <li>
          idempotency_key：
          <BiIdToken value={row.idempotencyKey || '--'} />
        </li>
        <li>
          authority：{row.authority || '--'} · trust {row.trust || '--'}
        </li>
        {ledger ? (
          <li>
            关联 ledger：
            <BiIdToken value={ledger.id} /> · {ledger.referenceType || '--'} /{' '}
            <BiIdToken value={ledger.referenceId || '--'} />
          </li>
        ) : null}
      </ul>
    </div>
  )
}

function LedgerDetailRow({ row }: { row?: BiCommerceLedgerRow }) {
  if (!row) return null
  return (
    <div className="mt-2 rounded-2xl border border-white/10 bg-white/[0.045] p-3 text-xs">
      <h4 className="text-sm font-black text-white">
        ledger <BiIdToken value={row.id} /> 元数据
      </h4>
      <ul className="mt-2 space-y-1 text-slate-300">
        <li>
          会员：
          <BiIdToken value={row.userId} />
        </li>
        <li>
          类型：{row.kind} · 金额：
          <BiMoneyCell
            amount={row.amount}
            currency="POINT"
            align="left"
            trust={row.trust as 'A' | 'B' | 'C' | 'D'}
          />
        </li>
        <li>
          reference：{row.referenceType || '--'} / <BiIdToken value={row.referenceId || '--'} />
        </li>
        <li>
          idempotency_key：
          <BiIdToken value={row.idempotencyKey || '--'} />
        </li>
        <li>
          authority：{row.authority || '--'} · trust {row.trust || '--'}
        </li>
        <li>
          metadata：
          <pre className="mt-1 max-h-48 overflow-auto rounded-2xl border border-white/10 bg-[#0e1624] p-2 font-mono text-[10px] leading-snug text-slate-300">
            {JSON.stringify(row.metadata, null, 2)}
          </pre>
        </li>
      </ul>
    </div>
  )
}

function PackageManagementPanel({
  packages,
  loading,
  error,
  onChanged,
}: {
  packages: ReadonlyArray<BiCommercePackage>
  loading: boolean
  error: string
  onChanged: () => Promise<void> | void
}) {
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingPackageId, setEditingPackageId] = useState<string | null>(null)
  const [form, setForm] = useState<PackageFormState>(EMPTY_PACKAGE_FORM)
  const [submitting, setSubmitting] = useState(false)
  const [notice, setNotice] = useState('')
  const [formError, setFormError] = useState('')

  function patchForm<K extends keyof PackageFormState>(key: K, value: PackageFormState[K]) {
    setForm(current => ({ ...current, [key]: value }))
  }

  function openCreate() {
    setEditingPackageId(null)
    setForm({ ...EMPTY_PACKAGE_FORM })
    setFormError('')
    setNotice('')
    setEditorOpen(true)
  }

  function openEdit(pkg: BiCommercePackage) {
    setEditingPackageId(pkg.id)
    setForm({
      id: pkg.id,
      label: pkg.name,
      tier: pkg.tier || pkg.id,
      points: String(pkg.points || ''),
      turns: String(pkg.turns || ''),
      price: String(pkg.priceCny || ''),
      originalPrice: pkg.originalPriceCny ? String(pkg.originalPriceCny) : '',
      badge: pkg.badge || '',
      per: pkg.per || '',
      desc: pkg.desc || pkg.features.join('、'),
      status: pkg.status || 'active',
      reason: '',
    })
    setFormError('')
    setNotice('')
    setEditorOpen(true)
  }

  async function savePackage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const packageId = form.id.trim()
    const points = Number(form.points)
    const turns = Number(form.turns)
    if (!packageId || !form.label.trim() || !form.tier.trim()) {
      setFormError('请填写套餐 ID、名称和层级')
      return
    }
    if (!Number.isFinite(points) || points <= 0 || !Number.isFinite(turns) || turns <= 0) {
      setFormError('点数和次数必须是正数')
      return
    }
    setSubmitting(true)
    setFormError('')
    setNotice('')
    try {
      await upsertMembershipPackage(packageId, {
        label: form.label.trim(),
        tier: form.tier.trim(),
        points: Math.floor(points),
        turns: Math.floor(turns),
        price: form.price.trim(),
        original_price: form.originalPrice.trim(),
        badge: form.badge.trim(),
        per: form.per.trim(),
        desc: form.desc.trim(),
        status: form.status as 'active' | 'draft' | 'archived',
        reason: form.reason.trim() || (editingPackageId ? '编辑套餐' : '新增套餐'),
      })
      setNotice(editingPackageId ? '套餐已更新' : '套餐已新增')
      setEditorOpen(false)
      await Promise.resolve(onChanged())
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : '套餐保存失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function removePackage(pkg: BiCommercePackage) {
    if (!window.confirm(`删除套餐 ${pkg.name}？历史收入流水不会删除。`)) return
    setSubmitting(true)
    setFormError('')
    setNotice('')
    try {
      await deleteMembershipPackage(pkg.id, '删除套餐')
      setNotice('套餐已删除')
      if (editingPackageId === pkg.id) setEditorOpen(false)
      await Promise.resolve(onChanged())
    } catch (exc) {
      setFormError(exc instanceof Error ? exc.message : '套餐删除失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-slate-400">
          member_console.packages · {packages.length} 个套餐
        </div>
        <BiButton onClick={openCreate} variant="primary" size="xs" aria-label="新增会员套餐">
          <Plus className="h-3 w-3" aria-hidden />
          新增套餐
        </BiButton>
      </div>

      {loading ? (
        <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-6 text-center text-xs text-slate-400">
          套餐加载中…
        </div>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-rose-300/25 bg-rose-300/10 p-6 text-center text-xs text-rose-100">
          套餐加载失败：{error}
        </div>
      ) : null}

      {notice ? <BiNotice tone="emerald">{notice}</BiNotice> : null}
      {formError ? <BiNotice tone="rose">{formError}</BiNotice> : null}

      {editorOpen ? (
        <form
          onSubmit={savePackage}
          className="rounded-2xl border border-cyan-300/25 bg-[#0d1828] p-4 text-xs shadow-lg shadow-black/15"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-black text-white">
              {editingPackageId ? `编辑 ${editingPackageId}` : '新增套餐'}
            </h3>
            <div className="flex items-center gap-2">
              <BiButton
                type="button"
                onClick={() => setEditorOpen(false)}
                variant="ghost"
                size="xs"
                aria-label="关闭套餐编辑"
              >
                <X className="h-3 w-3" aria-hidden />
                关闭
              </BiButton>
              <BiButton
                type="submit"
                variant="primary"
                size="xs"
                disabled={submitting}
                aria-label="保存套餐"
              >
                <Save className="h-3 w-3" aria-hidden />
                {submitting ? '保存中' : '保存'}
              </BiButton>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3 xl:grid-cols-6">
            <PackageField label="套餐 ID">
              <input
                value={form.id}
                onChange={event => patchForm('id', event.target.value)}
                disabled={Boolean(editingPackageId)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60 disabled:text-slate-500"
                placeholder="svip_plus"
              />
            </PackageField>
            <PackageField label="名称">
              <input
                value={form.label}
                onChange={event => patchForm('label', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
                placeholder="SVIP Plus"
              />
            </PackageField>
            <PackageField label="层级">
              <input
                value={form.tier}
                onChange={event => patchForm('tier', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
                placeholder="svip"
              />
            </PackageField>
            <PackageField label="点数">
              <input
                type="number"
                min={1}
                value={form.points}
                onChange={event => patchForm('points', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
              />
            </PackageField>
            <PackageField label="次数">
              <input
                type="number"
                min={1}
                value={form.turns}
                onChange={event => patchForm('turns', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
              />
            </PackageField>
            <PackageField label="状态">
              <BiSelect
                value={form.status}
                onChange={event => patchForm('status', event.target.value)}
                aria-label="套餐状态"
              >
                <option value="active">active</option>
                <option value="draft">draft</option>
                <option value="archived">archived</option>
              </BiSelect>
            </PackageField>
            <PackageField label="现价 ¥">
              <input
                value={form.price}
                onChange={event => patchForm('price', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
                placeholder="598"
              />
            </PackageField>
            <PackageField label="原价 ¥">
              <input
                value={form.originalPrice}
                onChange={event => patchForm('originalPrice', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
                placeholder="798"
              />
            </PackageField>
            <PackageField label="标签">
              <input
                value={form.badge}
                onChange={event => patchForm('badge', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
                placeholder="班主任督学"
              />
            </PackageField>
            <PackageField label="每次说明">
              <input
                value={form.per}
                onChange={event => patchForm('per', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
                placeholder="1400 次 AI 学习额度"
              />
            </PackageField>
            <PackageField label="备注">
              <input
                value={form.reason}
                onChange={event => patchForm('reason', event.target.value)}
                className="h-9 w-full rounded-lg border border-white/10 bg-[#0e1624] px-3 text-xs text-white outline-none focus:border-cyan-300/60"
                placeholder="新增/调价原因"
              />
            </PackageField>
          </div>

          <PackageField label="权益描述" className="mt-2 block">
            <textarea
              value={form.desc}
              onChange={event => patchForm('desc', event.target.value)}
              className="min-h-[72px] w-full resize-y rounded-lg border border-white/10 bg-[#0e1624] px-3 py-2 text-xs text-white outline-none focus:border-cyan-300/60"
              placeholder="AI答疑、案例批改、错因专训、班主任督学服务"
            />
          </PackageField>
        </form>
      ) : null}

      {packages.length === 0 && !loading && !error ? (
        <div className="rounded-2xl border border-white/10 bg-white/[0.045] p-6 text-center text-xs text-slate-400">
          暂无套餐权益数据。
        </div>
      ) : null}

      <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {packages.map(pkg => (
          <li
            key={pkg.id}
            className="rounded-2xl border border-white/10 bg-white/[0.045] p-4 text-xs shadow-lg shadow-black/15"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-black text-white">{pkg.name}</h3>
                  {pkg.badge ? (
                    <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-2 py-0.5 text-[10px] font-bold text-amber-100">
                      {pkg.badge}
                    </span>
                  ) : null}
                </div>
                <p className="text-[11px] text-slate-400">
                  {pkg.id} · {pkg.tier.toUpperCase()}
                </p>
              </div>
              <BiStatusPill
                tone={STATUS_TONE[pkg.status] ?? 'slate'}
                label={pkg.status || 'active'}
              />
            </div>
            <div className="mt-2 flex items-baseline justify-between">
              <BiMoneyCell
                amount={pkg.points}
                currency="POINT"
                align="left"
                trust={pkg.trust as 'A' | 'B' | 'C' | 'D'}
              />
              <BiMoneyCell
                amount={pkg.priceCny}
                currency="CNY"
                align="right"
                trust={pkg.trust as 'A' | 'B' | 'C' | 'D'}
              />
            </div>
            <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-400">
              <span>{pkg.turns || 0} 次</span>
              {pkg.originalPriceCny ? <span>原价 ¥{pkg.originalPriceCny}</span> : null}
              {pkg.per ? <span>{pkg.per}</span> : null}
            </div>
            <ul className="mt-2 space-y-0.5 text-[11px] text-slate-300">
              {(pkg.features.length ? pkg.features : pkg.desc ? [pkg.desc] : []).map((feature, index) => (
                <li key={`${pkg.id}-${index}`}>· {feature}</li>
              ))}
            </ul>
            <div className="mt-3 flex items-center gap-2">
              <BiButton
                onClick={() => openEdit(pkg)}
                variant="secondary"
                size="xs"
                aria-label={`编辑套餐 ${pkg.name}`}
                title="编辑套餐"
              >
                <Pencil className="h-3 w-3" aria-hidden />
                编辑
              </BiButton>
              <BiButton
                onClick={() => void removePackage(pkg)}
                variant="ghost"
                size="xs"
                disabled={submitting}
                aria-label={`删除套餐 ${pkg.name}`}
                title="删除套餐"
              >
                <Trash2 className="h-3 w-3" aria-hidden />
                删除
              </BiButton>
            </div>
            <p
              className="mt-2 truncate text-[10px] text-slate-400"
              title={`authority: ${pkg.authority || '--'} · trust ${pkg.trust || '--'}`}
            >
              authority: {pkg.authority || '--'} · trust {pkg.trust || '--'}
            </p>
          </li>
        ))}
      </ul>
    </div>
  )
}

function PackageField({
  label,
  className = 'space-y-1',
  children,
}: {
  label: string
  className?: string
  children: ReactNode
}) {
  return (
    <label className={className}>
      <span className="text-[11px] text-slate-400">{label}</span>
      {children}
    </label>
  )
}
