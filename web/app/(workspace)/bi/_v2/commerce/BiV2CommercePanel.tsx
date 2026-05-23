/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { AlertTriangle, Calendar, CreditCard, FileText, Receipt, Wallet } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  BiDataTable,
  BiMoneyCell,
  BiStatusPill,
  BI_SEVERITY_TONE,
  BI_TRUST_TONE,
  type BiTableColumn,
} from '@/components/bi-v2'
import {
  ANOMALIES,
  INVOICE_STATUSES,
  LEDGER,
  ORDERS,
  PACKAGES,
  PAYMENT_CHANNELS,
  type Anomaly,
  type Order,
  type Package,
  type WalletLedgerRow,
} from './data'

type Tab = 'orders' | 'ledger' | 'packages'

export type BiV2CommercePanelProps = {
  flagEnabled: boolean
}

const SEVERITY_BORDER: Record<Anomaly['severity'], string> = {
  critical: 'border-l-4 border-l-red-500',
  high: 'border-l-4 border-l-orange-500',
  medium: 'border-l-4 border-l-amber-500',
  low: 'border-l-4 border-l-slate-300',
}

const ANOMALY_STATUS_TONE = {
  new: 'rose',
  triaged: 'sky',
  resolved: 'emerald',
} as const

const CHANNEL_LABEL: Record<Order['channel'], string> = {
  alipay: '支付宝',
  wechat: '微信',
  stripe: 'Stripe',
  manual: '手工',
}

const INVOICE_LABEL: Record<Order['invoice_status'], string> = {
  none: '未申请',
  requested: '申请中',
  issued: '已开',
  void: '作废',
}

const LEDGER_KIND_TONE = {
  credit: 'emerald',
  debit: 'slate',
  refund: 'rose',
  manual: 'amber',
} as const

function monthKey(date: string) {
  return date.slice(0, 7)
}

export function BiV2CommercePanel({ flagEnabled }: BiV2CommercePanelProps) {
  const [tab, setTab] = useState<Tab>('orders')
  const [month, setMonth] = useState<string>('')
  const [channel, setChannel] = useState<'' | Order['channel']>('')
  const [invoice, setInvoice] = useState<'' | Order['invoice_status']>('')
  const [expandedOrderId, setExpandedOrderId] = useState<string | null>(null)
  const [expandedLedgerId, setExpandedLedgerId] = useState<string | null>(null)

  const months = useMemo(
    () =>
      Array.from(new Set(ORDERS.map(o => monthKey(o.created_at))))
        .sort()
        .reverse(),
    []
  )

  const filteredOrders = useMemo(
    () =>
      ORDERS.filter(o => {
        if (month && monthKey(o.created_at) !== month) return false
        if (channel && o.channel !== channel) return false
        if (invoice && o.invoice_status !== invoice) return false
        return true
      }),
    [month, channel, invoice]
  )

  const filteredLedger = useMemo(
    () =>
      LEDGER.filter(l => {
        if (month && monthKey(l.effective_at) !== month) return false
        return true
      }),
    [month]
  )

  const summary = useMemo(() => {
    const credit = LEDGER.filter(l => l.kind === 'credit').length
    const debit = LEDGER.filter(l => l.kind === 'debit').length
    const refund = LEDGER.filter(l => l.kind === 'refund').length
    const manual = LEDGER.filter(l => l.kind === 'manual').length
    return { credit, debit, refund, manual }
  }, [])

  const orderColumns = useMemo<BiTableColumn<Order>[]>(
    () => [
      {
        key: 'id',
        label: '订单 ID',
        render: o => <code className="font-mono text-[11px]">{o.id}</code>,
      },
      { key: 'user', label: '会员', render: o => <code className="font-mono">{o.user_id}</code> },
      {
        key: 'amount',
        label: '金额',
        align: 'right',
        render: o => <BiMoneyCell amount={o.amount_cny} currency="CNY" align="right" />,
      },
      { key: 'channel', label: '渠道', render: o => CHANNEL_LABEL[o.channel] },
      {
        key: 'invoice',
        label: '发票',
        render: o => (
          <BiStatusPill
            tone={
              o.invoice_status === 'issued'
                ? 'emerald'
                : o.invoice_status === 'void'
                  ? 'rose'
                  : 'amber'
            }
            label={INVOICE_LABEL[o.invoice_status]}
          />
        ),
      },
      { key: 'at', label: '时间', render: o => o.created_at },
    ],
    []
  )

  const ledgerColumns = useMemo<BiTableColumn<WalletLedgerRow>[]>(
    () => [
      {
        key: 'id',
        label: 'ledger_event_id',
        render: l => <code className="font-mono text-[11px]">{l.id}</code>,
      },
      { key: 'user', label: '会员', render: l => <code className="font-mono">{l.user_id}</code> },
      {
        key: 'kind',
        label: '类型',
        render: l => <BiStatusPill tone={LEDGER_KIND_TONE[l.kind]} label={l.kind} />,
      },
      {
        key: 'amount',
        label: '金额(点)',
        align: 'right',
        render: l => <BiMoneyCell amount={l.amount} currency="POINT" align="right" />,
      },
      {
        key: 'idem',
        label: 'idempotency_key',
        render: l => <code className="font-mono text-[10px]">{l.idempotency_key}</code>,
      },
      { key: 'at', label: '时间', render: l => l.effective_at },
    ],
    []
  )

  return (
    <section className="space-y-5">
      {!flagEnabled ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          BI_COMMERCE_V2_ENABLED 未开启 · 当前为 Batch 4 静态原型；Batch 4.5+ 接入 wallet_ledger /
          orders。P0 全部只读。
        </div>
      ) : (
        // Round 4 S5: honest banner — panel still mock until backend wires up.
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
          BI_COMMERCE_V2_ENABLED flag 已开启 · 数据源待 Batch 4.5 接入 wallet_ledger /
          orders；当前展示为 dev-only mock。
        </div>
      )}

      <AnomalyBar anomalies={ANOMALIES} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <SummaryTile
          icon={Receipt}
          label="订单 (24h)"
          value={ORDERS.length}
          hint="alipay/wechat/stripe/manual"
        />
        <SummaryTile
          icon={Wallet}
          label="钱包流水 (24h)"
          value={LEDGER.length}
          hint={`credit ${summary.credit} · debit ${summary.debit} · refund ${summary.refund} · manual ${summary.manual}`}
        />
        <SummaryTile
          icon={CreditCard}
          label="套餐数"
          value={PACKAGES.length}
          hint="P0 只读 · P1 接入 packages 表"
        />
        <SummaryTile
          icon={FileText}
          label="发票未开"
          value={ORDERS.filter(o => o.invoice_status === 'none').length}
          hint="近窗口"
        />
      </div>

      <div className="flex items-center gap-2 border-b border-slate-200">
        <TabBtn
          active={tab === 'orders'}
          onClick={() => setTab('orders')}
          label={`订单 (${filteredOrders.length})`}
        />
        <TabBtn
          active={tab === 'ledger'}
          onClick={() => setTab('ledger')}
          label={`钱包流水 (${filteredLedger.length})`}
        />
        <TabBtn
          active={tab === 'packages'}
          onClick={() => setTab('packages')}
          label={`套餐权益 (${PACKAGES.length})`}
        />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="inline-flex items-center gap-1">
          <Calendar className="h-3 w-3" aria-hidden />
          自然月
          <select
            value={month}
            onChange={e => setMonth(e.target.value)}
            className="rounded border border-slate-200 px-1 py-0.5"
            aria-label="按自然月筛选"
          >
            <option value="">全部</option>
            {months.map(m => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        {tab === 'orders' ? (
          <>
            <label className="inline-flex items-center gap-1">
              渠道
              <select
                value={channel}
                onChange={e => setChannel(e.target.value as typeof channel)}
                className="rounded border border-slate-200 px-1 py-0.5"
                aria-label="按支付渠道筛选"
              >
                <option value="">全部</option>
                {PAYMENT_CHANNELS.map(c => (
                  <option key={c} value={c}>
                    {CHANNEL_LABEL[c]}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-flex items-center gap-1">
              发票
              <select
                value={invoice}
                onChange={e => setInvoice(e.target.value as typeof invoice)}
                className="rounded border border-slate-200 px-1 py-0.5"
                aria-label="按发票状态筛选"
              >
                <option value="">全部</option>
                {INVOICE_STATUSES.map(s => (
                  <option key={s} value={s}>
                    {INVOICE_LABEL[s]}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        <button
          type="button"
          onClick={() => {
            setMonth('')
            setChannel('')
            setInvoice('')
          }}
          className="ml-auto text-slate-500 hover:text-slate-900"
          aria-label="清空账务筛选"
        >
          清空筛选
        </button>
      </div>

      {tab === 'orders' ? (
        <div>
          <BiDataTable<Order>
            columns={orderColumns}
            rows={filteredOrders}
            rowKey={o => o.id}
            status={filteredOrders.length === 0 ? 'no-results' : 'ok'}
            emptyTitle="暂无订单"
            rowAction={o => (
              <button
                type="button"
                onClick={() => setExpandedOrderId(expandedOrderId === o.id ? null : o.id)}
                className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
                aria-label={`查看订单 ${o.id} 权益变更`}
              >
                {expandedOrderId === o.id ? '收起' : '权益变更'}
              </button>
            )}
            cursorFooter={
              <>
                <span>
                  显示 {filteredOrders.length} / {ORDERS.length}（mock）
                </span>
                <span>cursor 分页待 Batch 4.5 接入</span>
              </>
            }
          />
          {expandedOrderId ? (
            <OrderDetailRow order={ORDERS.find(o => o.id === expandedOrderId)!} />
          ) : null}
        </div>
      ) : null}

      {tab === 'ledger' ? (
        <div>
          <BiDataTable<WalletLedgerRow>
            columns={ledgerColumns}
            rows={filteredLedger}
            rowKey={l => l.id}
            status={filteredLedger.length === 0 ? 'no-results' : 'ok'}
            emptyTitle="暂无钱包流水"
            rowAction={l => (
              <button
                type="button"
                onClick={() => setExpandedLedgerId(expandedLedgerId === l.id ? null : l.id)}
                className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
                aria-label={`查看 ${l.id} 元数据`}
              >
                {expandedLedgerId === l.id ? '收起' : '元数据'}
              </button>
            )}
          />
          {expandedLedgerId ? (
            <LedgerDetailRow row={LEDGER.find(l => l.id === expandedLedgerId)!} />
          ) : null}
        </div>
      ) : null}

      {tab === 'packages' ? (
        <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {PACKAGES.map(pkg => (
            <li key={pkg.id} className="rounded-md border border-slate-200 bg-white p-4 text-xs">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900">{pkg.name}</h3>
                  <p className="text-[11px] text-slate-500">{pkg.tier.toUpperCase()}</p>
                </div>
                <BiStatusPill
                  tone={
                    pkg.status === 'active' ? 'emerald' : pkg.status === 'draft' ? 'amber' : 'slate'
                  }
                  label={pkg.status}
                />
              </div>
              <div className="mt-2 flex items-baseline justify-between">
                <BiMoneyCell amount={pkg.points} currency="POINT" align="left" />
                <BiMoneyCell amount={pkg.price_cny} currency="CNY" align="right" />
              </div>
              <ul className="mt-2 space-y-0.5 text-[11px] text-slate-600">
                {pkg.features.map((f, idx) => (
                  <li key={idx}>· {f}</li>
                ))}
              </ul>
              <p className="mt-2 text-[10px] text-slate-500">
                authority: MemberConsoleService._default_packages（C 级）· P0 禁止生产编辑
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

function AnomalyBar({ anomalies }: { anomalies: ReadonlyArray<Anomaly> }) {
  if (anomalies.length === 0) return null
  return (
    <div className="rounded-md border border-rose-200 bg-rose-50/60 p-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-rose-700">
        <AlertTriangle className="h-4 w-4" aria-hidden />
        账务异常行动条 · {anomalies.reduce((sum, a) => sum + a.affected, 0)} 项待处理
      </div>
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {anomalies.map(a => (
          <article
            key={a.rule_id}
            className={`rounded bg-white px-3 py-2 text-xs ${SEVERITY_BORDER[a.severity]}`}
          >
            <div className="flex items-center justify-between gap-2">
              <code className="font-mono text-[11px] font-semibold text-slate-800">
                {a.rule_id}
              </code>
              <div className="flex gap-1">
                <BiStatusPill tone={BI_SEVERITY_TONE[a.severity]} label={a.severity} />
                <BiStatusPill tone={ANOMALY_STATUS_TONE[a.status]} label={a.status} />
                <BiStatusPill tone={BI_TRUST_TONE[a.trust]} label={a.trust} />
              </div>
            </div>
            <div className="mt-1 text-slate-700">{a.description}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {a.detected_at} · 影响 {a.affected} 项 · owner: {a.owner}
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
  icon: typeof CreditCard
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

function OrderDetailRow({ order }: { order: Order }) {
  const related = LEDGER.find(l => l.idempotency_key === order.idempotency_key)
  return (
    <div className="mt-2 rounded border border-slate-200 bg-slate-50 p-3 text-xs">
      <h4 className="text-sm font-semibold text-slate-900">订单 {order.id} 权益变更</h4>
      <ul className="mt-2 space-y-1 text-slate-700">
        <li>
          支付：
          <BiMoneyCell amount={order.amount_cny} currency="CNY" align="left" /> · 渠道{' '}
          {CHANNEL_LABEL[order.channel]}
        </li>
        <li>发票：{INVOICE_LABEL[order.invoice_status]}</li>
        <li>
          idempotency_key：<code className="font-mono">{order.idempotency_key}</code>
        </li>
        {related ? (
          <li>
            关联 ledger <code className="font-mono">{related.id}</code> · {related.kind} ·{' '}
            {related.amount} 点 · {related.effective_at}
          </li>
        ) : (
          <li className="text-rose-700">
            未找到对应钱包入账（潜在异常 WALLET_CREDIT_WITHOUT_ORDER）
          </li>
        )}
      </ul>
      <p className="mt-2 text-[11px] text-slate-500">
        authority: WalletService.list_wallet_ledger · 退款流程 P1 实装。
      </p>
    </div>
  )
}

function LedgerDetailRow({ row }: { row: WalletLedgerRow }) {
  return (
    <div className="mt-2 rounded border border-slate-200 bg-slate-50 p-3 text-xs">
      <h4 className="text-sm font-semibold text-slate-900">ledger {row.id} 元数据</h4>
      <ul className="mt-2 space-y-1 text-slate-700">
        <li>
          会员：<code className="font-mono">{row.user_id}</code>
        </li>
        <li>
          类型：{row.kind} · 金额：{row.amount} 点
        </li>
        <li>
          idempotency_key：<code className="font-mono">{row.idempotency_key}</code>
        </li>
        {row.session_id ? (
          <li>
            session：<code className="font-mono">{row.session_id}</code>
          </li>
        ) : null}
        {row.usage_event_id ? (
          <li>
            usage_event：<code className="font-mono">{row.usage_event_id}</code>
          </li>
        ) : null}
        {row.refund_origin_ledger_id ? (
          <li>
            退款关联：<code className="font-mono">{row.refund_origin_ledger_id}</code>
          </li>
        ) : null}
        {row.metadata ? (
          <li>
            metadata：
            <pre className="mt-1 rounded bg-white p-2 font-mono text-[10px] leading-snug">
              {JSON.stringify(row.metadata, null, 2)}
            </pre>
          </li>
        ) : null}
      </ul>
    </div>
  )
}
