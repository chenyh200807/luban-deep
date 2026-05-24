/* eslint-disable i18n/no-literal-ui-text */
'use client'

import {
  AlertTriangle,
  Calendar,
  CreditCard,
  FileText,
  RefreshCw,
  Wallet,
  type LucideIcon,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BiDataTable,
  BiMoneyCell,
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
  return values.some(value => String(value ?? '').toLowerCase().includes(normalized))
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
  }, [filteredLedger.length, filteredPackages.length, filteredRecharges.length, normalizedGlobalQuery])

  const rechargeColumns = useMemo<BiTableColumn<BiCommerceRechargeRecord>[]>(
    () => [
      {
        key: 'id',
        label: '记录 ID',
        render: row => <code className="font-mono text-[11px]">{row.id || row.ledgerEventId}</code>,
      },
      { key: 'user', label: '会员', render: row => <code className="font-mono">{row.userId}</code> },
      {
        key: 'points',
        label: '入账(点)',
        align: 'right',
        render: row => <BiMoneyCell amount={row.points} currency="POINT" trust={row.trust as 'A' | 'B' | 'C' | 'D'} />,
      },
      { key: 'channel', label: '来源', render: row => row.channel },
      {
        key: 'status',
        label: '状态',
        render: row => <BiStatusPill tone={STATUS_TONE[row.status] ?? 'slate'} label={row.status || 'unknown'} />,
      },
      { key: 'at', label: '时间', render: row => row.createdAt || '--' },
    ],
    []
  )

  const ledgerColumns = useMemo<BiTableColumn<BiCommerceLedgerRow>[]>(
    () => [
      {
        key: 'id',
        label: 'ledger_event_id',
        render: row => <code className="font-mono text-[11px]">{row.id}</code>,
      },
      { key: 'user', label: '会员', render: row => <code className="font-mono">{row.userId}</code> },
      {
        key: 'kind',
        label: '类型',
        render: row => <BiStatusPill tone={KIND_TONE[row.kind] ?? 'slate'} label={row.kind || row.eventType} />,
      },
      {
        key: 'amount',
        label: '金额(点)',
        align: 'right',
        render: row => <BiMoneyCell amount={row.amount} currency="POINT" trust={row.trust as 'A' | 'B' | 'C' | 'D'} />,
      },
      {
        key: 'authority',
        label: 'authority',
        render: row => <BiStatusPill tone={trustTone(row.trust)} label={row.authority || '--'} />,
      },
      { key: 'at', label: '时间', render: row => row.effectiveAt || '--' },
    ],
    []
  )

  if (!flagEnabled) {
    return (
      <section className="space-y-4">
        <BiV2DataSourceBanner tone="amber">
          BI_COMMERCE_V2_ENABLED 未开启 · 商品账务不会展示半成品数据。开启前需完成只读 API、
          admin 鉴权、mock 边界与前端 smoke。
        </BiV2DataSourceBanner>
      </section>
    )
  }

  return (
    <section className="space-y-5">
      <BiV2DataSourceBanner
        tone="sky"
        action={
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1 rounded border border-sky-200 bg-white px-2 py-1 text-sky-800 hover:bg-sky-100"
            aria-label="刷新商品账务"
          >
            <RefreshCw className="h-3 w-3" aria-hidden />
            刷新
          </button>
        }
      >
          BI_COMMERCE_V2_ENABLED 已开启 · 套餐读取 {data?.authority.packages ?? 'loading'}，充值/流水读取{' '}
          {data?.authority.wallet_ledger ?? 'loading'}；订单 authority 仍为{' '}
          {data?.authority.orders ?? 'pending'}，所有修账写动作禁用。
      </BiV2DataSourceBanner>

      {error ? (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
          商品账务 API 不可用：{error}。当前不会回退到 mock。
        </div>
      ) : null}

      {data?.warnings.length ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {data.warnings.join(' · ')}
        </div>
      ) : null}

      {globalQuery.trim() ? (
        <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
          全局搜索：<code className="font-mono">{globalQuery.trim()}</code> · 当前按订单 /
          流水 / 会员 / 套餐字段过滤商品账务读模型。
        </div>
      ) : null}

      <AnomalyBar anomalies={data?.anomalies ?? []} loading={loading} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <SummaryTile
          icon={CreditCard}
          label="充值记录"
          value={summary?.rechargeCount ?? 0}
          hint={`入账 ${summary?.creditPoints ?? 0} 点`}
        />
        <SummaryTile
          icon={Wallet}
          label="钱包流水"
          value={summary?.ledgerCount ?? 0}
          hint={`扣减 ${summary?.debitPoints ?? 0} 点`}
        />
        <SummaryTile
          icon={FileText}
          label="套餐权益"
          value={summary?.packageCount ?? 0}
          hint={data?.authority.packages ?? '加载中'}
        />
        <SummaryTile
          icon={AlertTriangle}
          label="账务异常"
          value={summary?.anomalyCount ?? 0}
          hint={data?.authority.anomalies ?? '规则加载中'}
        />
      </div>

      <div className="flex items-center gap-2 border-b border-slate-200">
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

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="inline-flex items-center gap-1">
          <Calendar className="h-3 w-3" aria-hidden />
          自然月
          <select
            value={month}
            onChange={event => setMonth(event.target.value)}
            className="rounded border border-slate-200 px-1 py-0.5"
            aria-label="按自然月筛选"
          >
            <option value="">全部</option>
            {months.map(item => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setMonth('')}
          className="ml-auto text-slate-500 hover:text-slate-900"
          aria-label="清空账务筛选"
        >
          清空筛选
        </button>
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
            emptyHint="订单 authority 未接入时，只展示 wallet_ledger / member_console 中可证明的入账。"
            rowAction={row => (
              <button
                type="button"
                onClick={() => setExpandedRechargeId(expandedRechargeId === row.ledgerEventId ? null : row.ledgerEventId)}
                className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
                aria-label={`查看充值记录 ${row.id || row.ledgerEventId} 详情`}
              >
                {expandedRechargeId === row.ledgerEventId ? '收起' : '详情'}
              </button>
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
              <button
                type="button"
                onClick={() => setExpandedLedgerId(expandedLedgerId === row.id ? null : row.id)}
                className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
                aria-label={`查看 ${row.id} 元数据`}
              >
                {expandedLedgerId === row.id ? '收起' : '元数据'}
              </button>
            )}
          />
          {expandedLedgerId ? (
            <LedgerDetailRow row={ledgerRows.find(row => row.id === expandedLedgerId)} />
          ) : null}
        </div>
      ) : null}

      {tab === 'packages' ? (
        <PackageGrid packages={filteredPackages} loading={loading} error={error} />
      ) : null}
    </section>
  )
}

function AnomalyBar({ anomalies, loading }: { anomalies: ReadonlyArray<BiCommerceAnomaly>; loading: boolean }) {
  if (loading) {
    return (
      <div className="rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-500">
        正在加载账务异常规则…
      </div>
    )
  }
  if (anomalies.length === 0) {
    return (
      <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
        当前未发现账务异常；高危修账动作仍保持禁用。
      </div>
    )
  }
  return (
    <div className="rounded-md border border-rose-200 bg-rose-50/60 p-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-rose-700">
        <AlertTriangle className="h-4 w-4" aria-hidden />
        账务异常行动条 · {anomalies.reduce((sum, item) => sum + item.affected, 0)} 项待复核
      </div>
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {anomalies.map(item => (
          <article key={item.ruleId} className="rounded bg-white px-3 py-2 text-xs ring-1 ring-rose-100">
            <div className="flex items-center justify-between gap-2">
              <code className="font-mono text-[11px] font-semibold text-slate-800">{item.ruleId}</code>
              <div className="flex gap-1">
                <BiStatusPill tone={severityTone(item.severity)} label={item.severity} />
                <BiStatusPill tone={trustTone(item.trust)} label={item.trust || 'N/A'} />
              </div>
            </div>
            <div className="mt-1 text-slate-700">{item.description}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {item.detectedAt || '实时'} · 影响 {item.affected} 项 · owner: {item.owner || '--'}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}

function SummaryTile({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: LucideIcon
  label: string
  value: number
  hint: string
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex items-center gap-2 text-xs text-slate-700">
        <Icon className="h-3.5 w-3.5" aria-hidden /> {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      <div className="mt-1 text-[11px] text-slate-500">{hint}</div>
    </div>
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
          ? 'border-slate-900 text-slate-900'
          : 'border-transparent text-slate-500 hover:text-slate-900'
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
    <div className="mt-2 rounded border border-slate-200 bg-slate-50 p-3 text-xs">
      <h4 className="text-sm font-semibold text-slate-900">充值记录 {row.id || row.ledgerEventId}</h4>
      <ul className="mt-2 space-y-1 text-slate-700">
        <li>
          会员：<code className="font-mono">{row.userId}</code>
        </li>
        <li>
          入账：<BiMoneyCell amount={row.points} currency="POINT" align="left" trust={row.trust as 'A' | 'B' | 'C' | 'D'} />
        </li>
        <li>来源：{row.channel} · 状态：{row.status}</li>
        <li>
          idempotency_key：<code className="font-mono">{row.idempotencyKey || '--'}</code>
        </li>
        <li>
          authority：{row.authority || '--'} · trust {row.trust || '--'}
        </li>
        {ledger ? (
          <li>
            关联 ledger：<code className="font-mono">{ledger.id}</code> · {ledger.referenceType || '--'} /{' '}
            {ledger.referenceId || '--'}
          </li>
        ) : null}
      </ul>
    </div>
  )
}

function LedgerDetailRow({ row }: { row?: BiCommerceLedgerRow }) {
  if (!row) return null
  return (
    <div className="mt-2 rounded border border-slate-200 bg-slate-50 p-3 text-xs">
      <h4 className="text-sm font-semibold text-slate-900">ledger {row.id} 元数据</h4>
      <ul className="mt-2 space-y-1 text-slate-700">
        <li>
          会员：<code className="font-mono">{row.userId}</code>
        </li>
        <li>
          类型：{row.kind} · 金额：
          <BiMoneyCell amount={row.amount} currency="POINT" align="left" trust={row.trust as 'A' | 'B' | 'C' | 'D'} />
        </li>
        <li>
          reference：{row.referenceType || '--'} / <code className="font-mono">{row.referenceId || '--'}</code>
        </li>
        <li>
          idempotency_key：<code className="font-mono">{row.idempotencyKey || '--'}</code>
        </li>
        <li>
          authority：{row.authority || '--'} · trust {row.trust || '--'}
        </li>
        <li>
          metadata：
          <pre className="mt-1 max-h-48 overflow-auto rounded bg-white p-2 font-mono text-[10px] leading-snug">
            {JSON.stringify(row.metadata, null, 2)}
          </pre>
        </li>
      </ul>
    </div>
  )
}

function PackageGrid({
  packages,
  loading,
  error,
}: {
  packages: ReadonlyArray<BiCommercePackage>
  loading: boolean
  error: string
}) {
  if (loading) {
    return <div className="rounded-md border border-slate-200 bg-white p-6 text-center text-xs text-slate-500">套餐加载中…</div>
  }
  if (error) {
    return <div className="rounded-md border border-rose-200 bg-rose-50 p-6 text-center text-xs text-rose-700">套餐加载失败：{error}</div>
  }
  if (packages.length === 0) {
    return <div className="rounded-md border border-slate-200 bg-white p-6 text-center text-xs text-slate-500">暂无套餐权益数据。</div>
  }
  return (
    <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {packages.map(pkg => (
        <li key={pkg.id} className="rounded-md border border-slate-200 bg-white p-4 text-xs">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">{pkg.name}</h3>
              <p className="text-[11px] text-slate-500">{pkg.tier.toUpperCase()}</p>
            </div>
            <BiStatusPill tone={STATUS_TONE[pkg.status] ?? 'slate'} label={pkg.status || 'unknown'} />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <BiMoneyCell amount={pkg.points} currency="POINT" align="left" trust={pkg.trust as 'A' | 'B' | 'C' | 'D'} />
            <BiMoneyCell amount={pkg.priceCny} currency="CNY" align="right" trust={pkg.trust as 'A' | 'B' | 'C' | 'D'} />
          </div>
          <ul className="mt-2 space-y-0.5 text-[11px] text-slate-600">
            {pkg.features.map((feature, index) => (
              <li key={`${pkg.id}-${index}`}>· {feature}</li>
            ))}
          </ul>
          <p className="mt-2 text-[10px] text-slate-500">
            authority: {pkg.authority || '--'} · trust {pkg.trust || '--'} · P0 只读
          </p>
        </li>
      ))}
    </ul>
  )
}
