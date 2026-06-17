/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { TrustBadge } from '@/components/bi-cockpit/TrustBadge'
import type { BiBossKpiItem } from '@/lib/bi-api'
import { createLoadingCards, metricIconByIndex, MetricCard, SectionHeader } from './BiShared'

type BiBossKpisProps = {
  loading: boolean
  kpis: BiBossKpiItem[]
  issue?: string
}

export function BiBossKpis({ loading, kpis, issue }: BiBossKpisProps) {
  const cards = loading ? createLoadingCards().slice(0, 5) : kpis.slice(0, 5)

  return (
    <section className="space-y-4">
      <SectionHeader
        title="经营 KPI"
        extra={cards.length ? `${cards.length} 项已接入` : '等待经营聚合'}
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {cards.length ? (
          cards.map((card, index) => (
            <div key={`${card.label}-${index}`} className="space-y-1.5">
              <MetricCard
                title={card.label}
                value={card.value}
                hint={card.hint ?? ''}
                delta={card.delta}
                tone={card.tone}
                icon={metricIconByIndex(index)}
              />
              {/* 可信度徽标：payload 带 metric_id 的卡（如今日成本 today_cost_usd）按注册表查询 */}
              {!loading && card.metricId ? <TrustBadge metricId={card.metricId} /> : null}
            </div>
          ))
        ) : (
          <div className="surface-card col-span-full border-0 bg-white/88 p-5 text-sm text-[var(--muted-foreground)] shadow-[0_10px_30px_rgba(45,33,25,0.06)]">
            当前没有可展示的经营 KPI，接口返回空数组不视为异常。
          </div>
        )}
      </div>
      {issue ? (
        <div className="rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-sm text-amber-800">
          经营 KPI 有部分模块未返回：{issue}
        </div>
      ) : null}
    </section>
  )
}
