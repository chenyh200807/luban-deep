/* eslint-disable i18n/no-literal-ui-text */
'use client'

/**
 * 系统运维情报驾驶舱。状态带来自 opsTiles（可点击打开 OpsTileDetailPanel），
 * 审计/导出活动从当前窗口记录派生（标注「当前窗口」，不冒充全量）。
 * 审计/导出明细表仍在下方保留。
 */
import { Activity, BarChart3, FileDown, PieChart, ShieldCheck } from 'lucide-react'
import type { AuditLogEntry, ExportJob, SystemOpsTile } from '@/app/(workspace)/bi/_v2/ops/data'
import { CockpitBar, CockpitDonut, type Datum } from './Charts'
import { BiAdminConsole } from '@/app/(workspace)/bi/_components/BiAdminConsole'
import { CockpitBg, CockpitKpi, CockpitPanel, SectionLabel } from './Layout'
import { SEMANTIC, SERIES_COLORS } from './theme'

const fmt = (n: number) => (Number.isFinite(n) ? n : 0).toLocaleString()
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

function Empty() {
  return (
    <div className="grid h-[200px] place-items-center rounded-xl border border-dashed border-white/10 text-[11px] text-slate-500">
      暂无数据
    </div>
  )
}

const TILE_TONE: Record<string, { dot: string; text: string }> = {
  ok: { dot: SEMANTIC.positive, text: 'text-emerald-300' },
  warn: { dot: SEMANTIC.warning, text: 'text-amber-300' },
  fail: { dot: SEMANTIC.danger, text: 'text-rose-300' },
}

export function OpsCockpit({
  tiles,
  audit,
  exportJobs,
  auditTotal,
  onTile,
}: {
  tiles: ReadonlyArray<SystemOpsTile>
  audit: ReadonlyArray<AuditLogEntry>
  exportJobs: ReadonlyArray<ExportJob>
  auditTotal?: number
  onTile?: (tile: SystemOpsTile) => void
}) {
  const okN = tiles.filter(t => t.status === 'ok').length
  const warnN = tiles.filter(t => t.status === 'warn').length
  const failN = tiles.filter(t => t.status === 'fail').length

  const category = countBy(audit, e => categoryLabel(e.category))
  const severity = [
    { name: '高', value: audit.filter(e => e.severity === 'high').length, color: SEMANTIC.danger },
    {
      name: '中',
      value: audit.filter(e => e.severity === 'medium').length,
      color: SEMANTIC.warning,
    },
    { name: '低', value: audit.filter(e => e.severity === 'low').length, color: SEMANTIC.neutral },
  ].filter(x => x.value > 0)
  const actor = top(
    countBy(audit, e => e.actor),
    6
  )
  const action = top(
    countBy(audit, e => e.action),
    6
  )
  const exportStatus = countBy(exportJobs, j => exportStatusLabel(j.status))

  return (
    <CockpitBg className="p-4 md:p-5">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-[#E8915A]/90">
        <Activity className="h-3.5 w-3.5" />
        System Ops &amp; Audit Cockpit
      </div>

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <CockpitKpi
          label="系统检查"
          value={fmt(tiles.length)}
          tone="cyan"
          icon={<ShieldCheck className="h-4 w-4" />}
        />
        <CockpitKpi label="正常" value={fmt(okN)} tone="emerald" />
        <CockpitKpi label="警告" value={fmt(warnN)} tone="amber" />
        <CockpitKpi label="异常" value={fmt(failN)} tone={failN > 0 ? 'rose' : 'emerald'} />
        <CockpitKpi
          label="审计条数"
          value={fmt(auditTotal ?? audit.length)}
          tone="violet"
          sub="当前窗口"
        />
        <CockpitKpi
          label="导出任务"
          value={fmt(exportJobs.length)}
          tone="teal"
          icon={<FileDown className="h-4 w-4" />}
        />
      </div>

      <SectionLabel icon={<ShieldCheck className="h-4 w-4" />}>系统状态</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {tiles.length ? (
          tiles.map(tile => {
            const t = TILE_TONE[tile.status] ?? TILE_TONE.ok
            return (
              <button
                key={tile.key}
                type="button"
                onClick={onTile ? () => onTile(tile) : undefined}
                className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left transition hover:border-[#E8915A]/30 hover:bg-[#E8915A]/[0.05]"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[13px] font-bold text-slate-100">
                    {tile.label}
                  </span>
                  <span className="flex items-center gap-1.5 text-[11px] font-bold">
                    <span className="h-2 w-2 rounded-full" style={{ background: t.dot }} />
                    <span className={t.text}>{tile.status.toUpperCase()}</span>
                  </span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-[11px] leading-5 text-slate-400">
                  {tile.detail}
                </p>
                <p className="mt-1 truncate text-[10px] text-slate-500">
                  owner: {tile.owner} · 可信 {tile.trust}
                </p>
              </button>
            )
          })
        ) : (
          <Empty />
        )}
      </div>

      <SectionLabel icon={<PieChart className="h-4 w-4" />}>审计活动 · 当前窗口</SectionLabel>
      <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <CockpitPanel glow title="按类别" icon={<PieChart className="h-4 w-4" />}>
          {category.length ? (
            <CockpitDonut data={category} centerLabel="审计" centerValue={fmt(audit.length)} />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
        <CockpitPanel title="按严重度" icon={<PieChart className="h-4 w-4" />}>
          {severity.length ? (
            <CockpitDonut data={severity} centerLabel="审计" centerValue={fmt(audit.length)} />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
        <CockpitPanel title="导出任务状态" icon={<FileDown className="h-4 w-4" />}>
          {exportStatus.length ? (
            <CockpitDonut
              data={exportStatus}
              centerLabel="任务"
              centerValue={fmt(exportJobs.length)}
            />
          ) : (
            <Empty />
          )}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<BarChart3 className="h-4 w-4" />}>操作者 · 动作</SectionLabel>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <CockpitPanel title="活跃操作者 Top" icon={<BarChart3 className="h-4 w-4" />}>
          {actor.length ? <CockpitBar data={actor} color={SERIES_COLORS[0]} /> : <Empty />}
        </CockpitPanel>
        <CockpitPanel title="高频动作 Top" icon={<BarChart3 className="h-4 w-4" />}>
          {action.length ? <CockpitBar data={action} color={SERIES_COLORS[3]} /> : <Empty />}
        </CockpitPanel>
      </div>

      <SectionLabel icon={<ShieldCheck className="h-4 w-4" />}>权限管理</SectionLabel>
      <BiAdminConsole />
    </CockpitBg>
  )
}

function categoryLabel(c: string): string {
  const m: Record<string, string> = {
    member: '会员',
    wallet: '钱包',
    feedback: '反馈',
    export: '导出',
    permission: '权限',
  }
  return m[c] ?? (c || '其它')
}
function exportStatusLabel(s: string): string {
  const m: Record<string, string> = {
    queued: '排队',
    running: '运行中',
    done: '完成',
    failed: '失败',
  }
  return m[s] ?? (s || '其它')
}
