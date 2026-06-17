/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 增长与质量区（从 OverviewCockpit 拆出，payload 消费逻辑保持原样）：
 * growthFunnel / memberHealth / aiQuality 三块，视觉对齐方向 A 暖色语言。
 */
import type { EChartsOption } from 'echarts'
import { Filter, Gauge, HeartPulse } from 'lucide-react'
import type { ReactNode } from 'react'
import type { BiOverviewData } from '@/lib/bi-api'
import { CockpitDonut, CockpitGauge, type Datum } from './Charts'
import { EChart } from './EChart'
import { CockpitPanel, SectionLabel } from './Layout'
import { COCKPIT, COCKPIT_FONT, COCKPIT_TOOLTIP, SEMANTIC, SERIES_COLORS } from './theme'

const fmtNum = (n: number) => new Intl.NumberFormat('en-US').format(Math.round(n))

export function GrowthQualitySection({ overview }: { overview: BiOverviewData }) {
  const funnel: Datum[] = (overview.growthFunnel?.steps ?? []).map(s => ({
    name: s.label,
    value: Number(s.value) || 0,
  }))
  const health: Datum[] = (overview.memberHealth?.distribution ?? [])
    .map(b => ({ name: b.label, value: Number(b.count) || 0 }))
    .filter(d => d.value > 0)
  const healthScore = Number(overview.memberHealth?.score?.value ?? NaN)
  const aiRate0 = overview.aiQuality?.engineeringSuccessRate
  const aiRate =
    typeof aiRate0 === 'number'
      ? aiRate0 <= 1
        ? Math.round(aiRate0 * 100)
        : Math.round(aiRate0)
      : null

  if (!funnel.length && !health.length && aiRate == null) return null

  const funnelOption = {
    tooltip: {
      ...COCKPIT_TOOLTIP,
      trigger: 'item' as const,
      formatter: (p: any) => `${p.name}<br/><b>${fmtNum(p.value)}</b>`,
    },
    series: [
      {
        type: 'funnel' as const,
        left: '6%',
        right: '6%',
        top: 12,
        bottom: 8,
        minSize: '16%',
        maxSize: '100%',
        sort: 'descending' as const,
        gap: 3,
        color: SERIES_COLORS as unknown as string[],
        itemStyle: {
          borderColor: COCKPIT.bgPanelSolid,
          borderWidth: 2,
          shadowBlur: 10,
          shadowColor: 'rgba(0,0,0,0.35)',
        },
        label: {
          show: true,
          position: 'inside' as const,
          color: '#1a120c',
          fontWeight: 700,
          fontFamily: COCKPIT_FONT,
          fontSize: 11,
          formatter: '{b}  {c}',
        },
        data: funnel.map(d => ({ name: d.name, value: d.value })),
      },
    ],
  }

  return (
    <>
      <SectionLabel icon={<Filter className="h-4 w-4" />}>增长与质量</SectionLabel>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel
          glow
          title="增长漏斗"
          hint={overview.growthFunnel?.summary || 'growth funnel'}
          icon={<Filter className="h-4 w-4" />}
        >
          {funnel.length ? (
            <EChart option={funnelOption as EChartsOption} height={240} />
          ) : (
            <SectionEmpty />
          )}
        </CockpitPanel>
        <CockpitPanel
          title="会员健康分布"
          hint={overview.memberHealth?.score?.note}
          icon={<HeartPulse className="h-4 w-4" />}
        >
          {health.length ? (
            <CockpitDonut
              data={health}
              centerLabel="健康分"
              centerValue={Number.isFinite(healthScore) ? String(healthScore) : '—'}
            />
          ) : (
            <SectionEmpty />
          )}
        </CockpitPanel>
        <CockpitPanel
          title="AI 工程成功率"
          hint={overview.aiQuality?.note}
          icon={<Gauge className="h-4 w-4" />}
        >
          {aiRate != null ? (
            <CockpitGauge
              value={aiRate}
              label={`失败 ${fmtNum(Number(overview.aiQuality?.failedTurns ?? 0))}/${fmtNum(Number(overview.aiQuality?.totalTurns ?? 0))}`}
              color={SEMANTIC.positive}
            />
          ) : (
            <SectionEmpty />
          )}
        </CockpitPanel>
      </div>
    </>
  )
}

function SectionEmpty(): ReactNode {
  return (
    <div className="grid h-[200px] place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500">
      暂无数据
    </div>
  )
}
