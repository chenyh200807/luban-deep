/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 成本卡「官方账单为锚」（方案3）。
 *
 * 大数字 = official_anchor.official_total（本月官方真实账单，权威锚，¥）；
 * 副数字 = calibrated_total（官方账单反推单价后校准的内账估算）；
 * 徽标 = calibration_health 偏差 + token_coverage_ratio 漏 token 提示。
 *
 * 后端 refresh 前 official_anchor 为空对象（归一化后字段全 undefined），
 * 此时显示「未校准」+ 刷新按钮，admin token 由 refreshBiCostCalibration 取自
 * getStoredBiAdminSession。刷新拉百炼账单较慢，按钮带 loading 态；
 * 刷新成功后重新拉取 getBiCost 回填本卡。
 */
import { useState } from 'react'
import { RefreshCw, ShieldCheck } from 'lucide-react'
import {
  getBiCost,
  refreshBiCostCalibration,
  type BiCostData,
  type BiCostOfficialAnchor,
} from '@/lib/bi-api'
import { SectionHeader } from './BiShared'

const yuan = (value?: number) =>
  value === undefined || !Number.isFinite(value)
    ? '--'
    : `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/** 校准健康度 → 偏差百分比文案 + 色调。health 越接近 1 越准。 */
function healthBadge(health?: number): { text: string; tone: string } {
  if (health === undefined || !Number.isFinite(health)) {
    return { text: '偏差未知', tone: 'bg-slate-100 text-slate-600' }
  }
  const deviationPct = Math.abs(health - 1) * 100
  const text = `校准偏差 ${deviationPct.toFixed(1)}%`
  if (deviationPct <= 5) return { text, tone: 'bg-emerald-100 text-emerald-700' }
  if (deviationPct <= 15) return { text, tone: 'bg-amber-100 text-amber-700' }
  return { text, tone: 'bg-rose-100 text-rose-700' }
}

/** token 覆盖率 → 漏 token 提示文案 + 色调。 */
function coverageBadge(ratio?: number): { text: string; tone: string } {
  if (ratio === undefined || !Number.isFinite(ratio)) {
    return { text: '覆盖率未知', tone: 'bg-slate-100 text-slate-600' }
  }
  const pct = ratio * 100
  const text = `Token 覆盖 ${pct.toFixed(0)}%`
  if (pct >= 80) return { text, tone: 'bg-emerald-100 text-emerald-700' }
  if (pct >= 50) return { text, tone: 'bg-amber-100 text-amber-700' }
  return { text, tone: 'bg-rose-100 text-rose-700' }
}

function hasAnchor(anchor: BiCostOfficialAnchor): boolean {
  return anchor.officialTotal !== undefined || anchor.calibratedTotal !== undefined
}

type Props = {
  days: 7 | 30 | 90
  cost: BiCostData
}

export function BiCostOfficialAnchorCard({ days, cost }: Props) {
  // 本卡自持 anchor 覆盖：默认来自父级 cost 注入，刷新成功后用最新 getBiCost 覆盖。
  const [override, setOverride] = useState<BiCostData | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const effective = override ?? cost
  const anchor = effective.officialAnchor
  const cycle = effective.calibrationBillingCycle
  const refreshedAt = effective.calibrationRefreshedAt

  const onRefresh = async () => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await refreshBiCostCalibration(cycle ?? undefined)
      // 刷新只写服务端校准态，重新拉取成本端点把最新 anchor 回填本卡。
      const fresh = await getBiCost({ days })
      setOverride(fresh)
    } catch (e) {
      setError(e instanceof Error ? e.message : '刷新失败')
    } finally {
      setBusy(false)
    }
  }

  const calibrated_total = anchor.calibratedTotal
  const health = healthBadge(anchor.calibrationHealth)
  const coverage = coverageBadge(anchor.tokenCoverageRatio)

  return (
    <section className="surface-card p-5">
      <SectionHeader title="成本权威锚" extra={cycle ? `账期 ${cycle}` : '官方账单为锚 · 自校准'} />

      {hasAnchor(anchor) ? (
        <div className="mt-4">
          <p className="text-xs text-[var(--muted-foreground)]">本月官方账单（权威）</p>
          <p className="mt-1 text-3xl font-semibold tracking-tight text-[var(--foreground)] tabular-nums">
            {yuan(anchor.officialTotal)}
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="text-[var(--muted-foreground)]">
              内账校准后估算 {yuan(calibrated_total)}
            </span>
            <span className={`muted-chip ${health.tone}`}>{health.text}</span>
            <span className={`muted-chip ${coverage.tone}`}>{coverage.text}</span>
          </div>

          {anchor.tokenCoverageRatio !== undefined && anchor.tokenCoverageRatio < 0.5 ? (
            <p className="mt-3 rounded-2xl bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">
              内账 token 仅覆盖官方账单约 {(anchor.tokenCoverageRatio * 100).toFixed(0)}%， 漏 token
              明显，趋势/明细仅供参考，权威成本以上方官方账单为准。
            </p>
          ) : null}

          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="text-[11px] text-[var(--muted-foreground)]">
              {refreshedAt
                ? `校准于 ${new Date(refreshedAt).toLocaleString('zh-CN')}`
                : '尚未记录校准时间'}
            </p>
            <button
              type="button"
              onClick={() => void onRefresh()}
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--foreground)] transition hover:border-[#C35A2C]/40 hover:text-[#C35A2C] disabled:opacity-50"
            >
              <RefreshCw size={13} className={busy ? 'animate-spin' : ''} />
              {busy ? '刷新中…' : '重新校准'}
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex flex-col items-start gap-3 rounded-2xl bg-[var(--secondary)] px-4 py-5">
          <div className="flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
            <ShieldCheck size={16} className="text-[#C35A2C]" />
            未校准
          </div>
          <p className="text-xs leading-5 text-[var(--muted-foreground)]">
            尚未拉取官方账单做自校准。内账（UsageLedger 估算）仅覆盖官方真实账单约 18%，
            点击下方按钮拉取本月官方账单并反推真实单价。
          </p>
          <button
            type="button"
            onClick={() => void onRefresh()}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-full bg-[#C35A2C] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#D4734B] disabled:opacity-50"
          >
            <RefreshCw size={13} className={busy ? 'animate-spin' : ''} />
            {busy ? '拉取官方账单中…' : '立即校准'}
          </button>
        </div>
      )}

      {error ? <p className="mt-3 text-xs text-rose-600">{error}</p> : null}
    </section>
  )
}
