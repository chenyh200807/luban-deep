/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * KPI 可信度徽标（方向 A「指挥舱进化」轴②：数据可信度即 UI）。
 *
 * 数据单一权威：trust_level / authority / refresh_cadence / degraded_note
 * 一律按 metric_id 从后端 BI_METRICS 注册表的生成镜像
 * （lib/bi-v2-metric-registry.generated.ts）查询，UI 不自造口径。
 * 注册表外的 metric_id 自动落到 D 级 fallback——治理缺口直接上屏。
 */
import { findMetricById } from '@/lib/bi-v2-metric-registry.generated'
import { COCKPIT, TRUST_LEVEL_COLORS, alpha } from './theme'

/** authority 缩写：取点号路径最后一段（observability.usage_ledger → usage_ledger） */
function shortAuthority(authority: string): string {
  const segments = authority.split('.')
  return segments[segments.length - 1] || authority
}

export function TrustBadge({
  metricId,
  measuredValue,
  estimatedValue,
  provenance,
}: {
  metricId: string
  /** 同时传入 measured + estimated 时渲染微型分量条 */
  measuredValue?: number
  estimatedValue?: number
  /** 数据来源声明（payload 携带，如 "usage_ledger"），优先于 authority 缩写 */
  provenance?: string
}) {
  const meta = findMetricById(metricId)
  const color = TRUST_LEVEL_COLORS[meta.trust]
  const src = provenance || shortAuthority(meta.authority)
  const hasBar = typeof measuredValue === 'number' && typeof estimatedValue === 'number'

  return (
    <span className="group/trust relative inline-flex flex-col">
      <span className="inline-flex items-center gap-1.5">
        <span
          className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-px text-[10px] font-extrabold"
          style={{
            color,
            borderColor: alpha(color, 0.4),
            background: alpha(color, 0.13),
          }}
        >
          ● {meta.trust} 级
        </span>
        <span
          className="hidden whitespace-nowrap rounded-md border px-1.5 py-px text-[10px] sm:inline"
          style={{ color: COCKPIT.textFaint, borderColor: COCKPIT.border }}
        >
          src: {src}
        </span>
      </span>

      {hasBar ? (
        <MeasuredEstimatedBar
          measured={measuredValue}
          estimated={estimatedValue}
          provenance={provenance}
        />
      ) : null}

      {/* hover tooltip：定义 / 口径元数据 / 降级说明（纯 CSS，不引入弹层依赖） */}
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute right-0 top-full z-30 mt-1.5 w-64 rounded-xl border p-3 text-left opacity-0 transition group-hover/trust:visible group-hover/trust:opacity-100"
        style={{
          borderColor: alpha(color, 0.45),
          background: 'linear-gradient(165deg, rgba(34,23,16,0.97), rgba(23,15,10,0.97))',
          boxShadow: '0 16px 48px rgba(0,0,0,0.6)',
        }}
      >
        <span className="block text-[11px] font-black" style={{ color: COCKPIT.text }}>
          {meta.metric_id}
        </span>
        <span className="mt-1 block text-[11px] leading-relaxed" style={{ color: COCKPIT.textMuted }}>
          {meta.definition}
        </span>
        <span className="mt-1.5 block text-[10px]" style={{ color: COCKPIT.textFaint }}>
          authority: {meta.authority} · 更新: {meta.refresh_cadence}
        </span>
        {meta.degraded_note ? (
          <span className="mt-1 block text-[10px] leading-relaxed" style={{ color }}>
            降级: {meta.degraded_note}
          </span>
        ) : null}
      </span>
    </span>
  )
}

/**
 * measured / estimated 微型分量条：measured 实色（陶土→琥珀渐变），
 * estimated 斜纹半透明（与设计板 .mebar 一致）。
 */
export function MeasuredEstimatedBar({
  measured,
  estimated,
  provenance,
}: {
  measured: number
  estimated: number
  provenance?: string
}) {
  const total = measured + estimated
  if (!Number.isFinite(total) || total <= 0) return null
  const measuredPct = Math.round((measured / total) * 100)
  const estimatedPct = 100 - measuredPct
  const stripe = `repeating-linear-gradient(45deg, ${alpha(COCKPIT.textMuted, 0.5)} 0 4px, ${alpha(COCKPIT.textMuted, 0.2)} 4px 8px)`

  return (
    <span className="block">
      <span
        className="mt-1.5 flex h-1 overflow-hidden rounded-sm"
        style={{ background: alpha(COCKPIT.textFaint, 0.25) }}
      >
        <span
          style={{
            width: `${measuredPct}%`,
            background: `linear-gradient(90deg, ${TRUST_LEVEL_COLORS.A}, ${TRUST_LEVEL_COLORS.B})`,
          }}
        />
        <span style={{ width: `${estimatedPct}%`, background: stripe }} />
      </span>
      <span className="mt-0.5 block text-[9.5px]" style={{ color: COCKPIT.textFaint }}>
        measured {measuredPct}% · estimated {estimatedPct}%
        {provenance ? ` · src ${provenance}` : ''}
      </span>
    </span>
  )
}
