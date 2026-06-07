/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 商品账务情报驾驶舱。数据来自 BiCommerceData（summary 聚合 + packages/ledger/recharge/anomalies）。
 * 只做真实字段 -> 图表映射；表格/抽屉仍在下方保留。
 */
import { Activity, AlertTriangle, BarChart3, CreditCard, FileText, PieChart, Wallet } from 'lucide-react'
import type { BiCommerceData, BiCommerceLedgerRow, BiCommercePackage, BiCommerceRechargeRecord } from '@/lib/bi-api'
import { CockpitBar, CockpitDonut, type Datum } from './Charts'
import { CockpitBg, CockpitKpi, CockpitPanel, SectionLabel } from './Layout'
import { SEMANTIC, SERIES_COLORS } from './theme'

const num = (n: number | null | undefined) => (typeof n === 'number' && isFinite(n) ? n : 0)
const fmt = (n: number) => num(n).toLocaleString()
const top = (arr: Datum[], n: number) => [...arr].sort((a, b) => b.value - a.value).slice(0, n)

function countBy<T>(rows: ReadonlyArray<T>, pick: (r: T) => string | undefined | null): Datum[] {
  const m = new Map<string, number>()
  for (const r of rows) {
    const k = (pick(r) ?? '').trim()
    if (!k) continue
    m.set(k, (m.get(k) ?? 0) + 1)
  }
  return [...m.entries()].map(([name, value]) => ({ name, value }))
}

function Empty({ mini = false }: { mini?: boolean }) {
  return <div className={`grid place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500 ${mini ? 'h-16' : 'h-[200px]'}`}>暂无数据</div>
}

const SEV_COLOR: Record<string, string> = { critical: SEMANTIC.danger, high: SEMANTIC.danger, medium: SEMANTIC.warning, low: SEMANTIC.neutral }

export function CommerceCockpit({ data }: { data: BiCommerceData | null }) {
  const s = data?.summary
  const ledger: ReadonlyArray<BiCommerceLedgerRow> = data?.ledger ?? []
  const packages: ReadonlyArray<BiCommercePackage> = data?.packages ?? []
  const recharges: ReadonlyArray<BiCommerceRechargeRecord> = data?.rechargeRecords ?? []
  const anomalies = data?.anomalies ?? []

  const creditDebit: Datum[] = [
    { name: '入账积分', value: num(s?.creditPoints), color: SEMANTIC.positive },
    { name: '扣减积分', value: num(s?.debitPoints), color: SEMANTIC.warning },
  ].filter(x => x.value > 0)
  const ledgerKind = countBy(ledger, r => ledgerKindLabel(r.kind))
  const pkgTier = countBy(packages, p => p.tier)
  const channel = countBy(recharges, r => r.channel)
  const pkgPoints: Datum[] = top(packages.map(p => ({ name: p.name, value: num(p.points) })).filter(x => x.value > 0), 6)

  return (
    <CockpitBg className="p-4 md:p-5">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#E8915A]/90">
        <Activity className="h-3.5 w-3.5" />
        Commerce &amp; Wallet Cockpit
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <CockpitKpi label="付费会员" value={fmt(num(s?.memberCount))} tone="cyan" icon={<Wallet className="h-4 w-4" />} />
        <CockpitKpi label="套餐数" value={fmt(num(s?.packageCount))} tone="violet" icon={<FileText className="h-4 w-4" />} />
        <CockpitKpi label="入账笔数" value={fmt(num(s?.rechargeCount))} tone="emerald" icon={<CreditCard className="h-4 w-4" />} />
        <CockpitKpi label="钱包流水" value={fmt(num(s?.ledgerCount))} tone="teal" />
        <CockpitKpi label="入账积分" value={fmt(num(s?.creditPoints))} tone="gold" />
        <CockpitKpi label="扣减积分" value={fmt(num(s?.debitPoints))} tone="amber" />
        <CockpitKpi label="账务异常" value={fmt(num(s?.anomalyCount))} tone={num(s?.anomalyCount) > 0 ? 'rose' : 'emerald'} icon={<AlertTriangle className="h-4 w-4" />} />
      </div>

      <SectionLabel icon={<PieChart className="h-4 w-4" />}>积分与账本</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel glow title="积分收支" hint="入账 vs 扣减" icon={<PieChart className="h-4 w-4" />}>
          {creditDebit.length ? <CockpitDonut data={creditDebit} centerLabel="净" centerValue={fmt(num(s?.creditPoints) - num(s?.debitPoints))} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="账本类型构成" icon={<PieChart className="h-4 w-4" />}>
          {ledgerKind.length ? <CockpitDonut data={ledgerKind} centerLabel="流水" centerValue={fmt(ledger.length)} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="充值渠道" icon={<PieChart className="h-4 w-4" />}>
          {channel.length ? <CockpitDonut data={channel} centerLabel="充值" centerValue={fmt(recharges.length)} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<BarChart3 className="h-4 w-4" />}>套餐 · 异常</SectionLabel>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel title="套餐 Tier 分布" icon={<PieChart className="h-4 w-4" />}>
          {pkgTier.length ? <CockpitDonut data={pkgTier} centerLabel="套餐" centerValue={fmt(packages.length)} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="套餐点数 Top" icon={<BarChart3 className="h-4 w-4" />}>
          {pkgPoints.length ? <CockpitBar data={pkgPoints} color={SERIES_COLORS[1]} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="账务异常" icon={<AlertTriangle className="h-4 w-4" />}>
          {anomalies.length ? (
            <ul className="space-y-2">
              {anomalies.slice(0, 6).map((a, i) => (
                <li key={i} className="flex items-start gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-2.5 text-[12px]">
                  <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: SEV_COLOR[a.severity] ?? SEMANTIC.neutral }} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-bold text-slate-100">{a.description || a.ruleId}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-slate-400">影响 {fmt(num(a.affected))} · {a.owner || '—'} · {a.status || '—'}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="grid h-[200px] place-items-center rounded-xl border border-dashed border-emerald-300/15 text-[12px] text-emerald-200/80">无账务异常 ✓</div>
          )}
        </CockpitPanel>
      </div>
    </CockpitBg>
  )
}

function ledgerKindLabel(k: string): string {
  if (k === 'credit') return '入账'
  if (k === 'debit') return '扣减'
  if (k === 'refund') return '退款'
  if (k === 'manual') return '手工'
  return k || '其它'
}
