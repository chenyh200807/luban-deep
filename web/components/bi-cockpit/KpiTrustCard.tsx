/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 设计板方向 A 的 KPI 徽标卡：
 * 顶行 = 指标名 + 可信度等级胶囊（右上角）；大数字行；
 * meta 行 = 环比 delta + 数据源 chip + 注册表更新节奏；
 * 成本卡附 measured/estimated 斜纹微条；底部 = payload hint 状态行。
 *
 * 徽标元数据单一权威：lib/bi-v2-metric-registry.generated.ts（经 TrustPill 查询），
 * UI 不自造口径；卡上所有数值/分量均来自 overview payload。
 */
import type { BiMetricCard } from '@/lib/bi-api'
import { findMetricById } from '@/lib/bi-v2-metric-registry.generated'
import { MeasuredEstimatedBar, TrustPill, shortAuthority } from './TrustBadge'
import { COCKPIT, SEMANTIC, alpha } from './theme'

const TONE_COLOR: Record<string, string> = {
  good: SEMANTIC.positive,
  warning: SEMANTIC.warning,
  critical: SEMANTIC.danger,
  neutral: SEMANTIC.info,
}

function deltaUp(delta?: string, tone?: string): boolean {
  if (delta && /^[+↑▲]|增|升/.test(delta.trim())) return true
  if (delta && /^[-↓▼]|降|跌/.test(delta.trim())) return false
  return tone === 'good'
}

export function KpiTrustCard({ card, onClick }: { card: BiMetricCard; onClick?: () => void }) {
  const tone = TONE_COLOR[card.tone ?? 'neutral'] ?? SEMANTIC.info
  const meta = card.metricId ? findMetricById(card.metricId) : null
  const src = card.provenance || (meta ? shortAuthority(meta.authority) : '')
  const hasBar = typeof card.measuredValue === 'number' && typeof card.estimatedValue === 'number'
  const up = deltaUp(card.delta, card.tone)

  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative w-full overflow-hidden rounded-2xl border p-3.5 text-left transition duration-150 hover:-translate-y-0.5 hover:border-[#E8915A]/45"
      style={{
        borderColor: COCKPIT.border,
        background: `linear-gradient(150deg, ${COCKPIT.bgPanel}, rgba(28,19,13,0.5))`,
        boxShadow: '0 16px 40px -20px rgba(0,0,0,0.7)',
      }}
    >
      {/* 角部光斑（设计板 .kpi .blob） */}
      <span
        aria-hidden
        className="absolute -right-4 -top-4 h-16 w-16 rounded-full opacity-35 blur-[20px]"
        style={{ background: tone }}
      />

      <span className="relative flex items-center justify-between gap-1.5">
        <span className="truncate text-[11px] font-bold" style={{ color: COCKPIT.textMuted }}>
          {card.label}
        </span>
        {card.metricId ? <TrustPill metricId={card.metricId} /> : null}
      </span>

      <span className="relative mt-1.5 flex items-baseline gap-1">
        <span
          className="text-[27px] font-black leading-none tabular-nums"
          style={{ color: COCKPIT.text, textShadow: `0 0 18px ${alpha(tone, 0.4)}` }}
        >
          {card.value}
        </span>
      </span>

      <span className="relative mt-2 flex flex-wrap items-center gap-1.5">
        {card.delta ? (
          <span
            className="text-[11px] font-extrabold"
            style={{ color: up ? SEMANTIC.positive : SEMANTIC.danger }}
          >
            {up ? '▲' : '▼'} {card.delta}
          </span>
        ) : null}
        {src ? (
          <span
            className="whitespace-nowrap rounded-md border px-1.5 py-px text-[10px]"
            style={{ color: COCKPIT.textFaint, borderColor: COCKPIT.border }}
          >
            src: {src}
          </span>
        ) : null}
        {meta?.refresh_cadence ? (
          <span className="text-[10px]" style={{ color: COCKPIT.textFaint }}>
            更新 {meta.refresh_cadence}
          </span>
        ) : null}
      </span>

      {hasBar ? (
        <span className="relative block">
          <MeasuredEstimatedBar
            measured={card.measuredValue as number}
            estimated={card.estimatedValue as number}
            provenance={card.provenance}
          />
        </span>
      ) : null}

      {card.hint ? (
        <span
          className="relative mt-2 inline-flex max-w-full items-center gap-1.5 truncate rounded-lg border px-2 py-1 text-[10.5px] font-semibold"
          style={{
            color: COCKPIT.textMuted,
            borderColor: alpha(tone, 0.3),
            background: alpha(tone, 0.07),
          }}
        >
          {card.hint}
        </span>
      ) : null}
    </button>
  )
}
