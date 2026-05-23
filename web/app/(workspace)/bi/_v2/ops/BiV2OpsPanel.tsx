/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Download, History, Lock, Rocket, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useMemo, useState } from 'react'
import { BiDataTable, BiStatusPill, BI_TRUST_TONE, type BiTableColumn } from '@/components/bi-v2'
import {
  AUDIT_ENTRIES,
  EXPORT_JOBS,
  OPS_TILES,
  type AuditLogEntry,
  type ExportJob,
  type SystemOpsTile,
} from './data'

const OPS_ICON: Record<string, typeof ShieldCheck> = {
  'cost-quality': ShieldAlert,
  'data-trust': ShieldCheck,
  'audit-actions': History,
  'audit-perm': Lock,
  'audit-export': Download,
  release: Rocket,
}

const STATUS_TONE: Record<SystemOpsTile['status'], 'emerald' | 'amber' | 'rose'> = {
  ok: 'emerald',
  warn: 'amber',
  fail: 'rose',
}

const SEVERITY_TONE: Record<AuditLogEntry['severity'], 'slate' | 'amber' | 'rose'> = {
  low: 'slate',
  medium: 'amber',
  high: 'rose',
}

const CATEGORY_LABEL: Record<AuditLogEntry['category'], string> = {
  member: '会员',
  wallet: '钱包',
  feedback: '反馈',
  export: '导出',
  permission: '权限',
}

const JOB_TONE: Record<ExportJob['status'], 'sky' | 'amber' | 'emerald' | 'rose'> = {
  queued: 'amber',
  running: 'sky',
  done: 'emerald',
  failed: 'rose',
}

type AuditFilter = {
  actor: string
  target: string
  category: '' | AuditLogEntry['category']
  severity: '' | AuditLogEntry['severity']
}

const DEFAULT_AUDIT_FILTER: AuditFilter = { actor: '', target: '', category: '', severity: '' }

export type BiV2OpsPanelProps = {
  flagEnabled: boolean
}

export function BiV2OpsPanel({ flagEnabled }: BiV2OpsPanelProps) {
  const [auditFilter, setAuditFilter] = useState<AuditFilter>(DEFAULT_AUDIT_FILTER)
  const [composingActor, setComposingActor] = useState(false)
  const [composingTarget, setComposingTarget] = useState(false)

  const filteredAudit = useMemo(
    () =>
      AUDIT_ENTRIES.filter(e => {
        if (auditFilter.actor && !e.actor.toLowerCase().includes(auditFilter.actor.toLowerCase()))
          return false
        if (
          auditFilter.target &&
          !e.target.toLowerCase().includes(auditFilter.target.toLowerCase())
        )
          return false
        if (auditFilter.category && e.category !== auditFilter.category) return false
        if (auditFilter.severity && e.severity !== auditFilter.severity) return false
        return true
      }),
    [auditFilter]
  )

  const auditColumns = useMemo<BiTableColumn<AuditLogEntry>[]>(
    () => [
      { key: 'at', label: '时间', render: e => e.at },
      {
        key: 'actor',
        label: '操作人',
        render: e => <code className="font-mono text-[11px]">{e.actor}</code>,
      },
      { key: 'action', label: '动作', render: e => e.action },
      {
        key: 'target',
        label: '目标',
        render: e => <code className="font-mono text-[11px]">{e.target}</code>,
      },
      { key: 'category', label: '分类', render: e => CATEGORY_LABEL[e.category] },
      {
        key: 'severity',
        label: '敏感级别',
        render: e => <BiStatusPill tone={SEVERITY_TONE[e.severity]} label={e.severity} />,
      },
    ],
    []
  )

  const exportColumns = useMemo<BiTableColumn<ExportJob>[]>(
    () => [
      { key: 'name', label: '导出任务', render: j => j.name },
      {
        key: 'rows',
        label: '行数',
        align: 'right',
        render: j => <span className="tabular-nums">{j.rows.toLocaleString('zh-CN')}</span>,
      },
      {
        key: 'status',
        label: '状态',
        render: j => <BiStatusPill tone={JOB_TONE[j.status]} label={j.status} />,
      },
      { key: 'scrub', label: '脱敏', render: j => (j.scrubbed ? '✓' : '✗') },
      {
        key: 'rate',
        label: '限频/小时',
        align: 'right',
        render: j => <span className="tabular-nums">{j.rate_limit_per_hour}</span>,
      },
      { key: 'at', label: '申请时间', render: j => j.requested_at },
    ],
    []
  )

  return (
    <section className="space-y-5">
      {!flagEnabled ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          BI_SYSTEM_OPS_V2_ENABLED 未开启 · 当前 Batch 6 静态原型。审计与导出已写后端接口路径，UI
          已对齐。
        </div>
      ) : (
        // Round 4 S5: banner must not claim "已接 / 已写入 真实 service" while
        // the panel still renders mock data. Honest copy + skeleton state
        // until the audit-log / exports endpoints are wired through
        // useAuditedAction in Batch 6.
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
          BI_SYSTEM_OPS_V2_ENABLED flag 已开启 · UI 已对齐 audit_log / exports 形状；真实 service
          接入待 Batch 6 实装（当前展示为 skeleton / dev-only mock）。
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {OPS_TILES.map(tile => {
          const Icon = OPS_ICON[tile.key] ?? ShieldCheck
          return (
            <article
              key={tile.key}
              className="rounded-md border border-slate-200 bg-white p-4"
              title={`${tile.label} · authority: ${tile.authority} · owner: ${tile.owner}`}
            >
              <header className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium text-slate-800">
                  <Icon className="h-4 w-4" aria-hidden /> {tile.label}
                </div>
                <div className="flex gap-1">
                  <BiStatusPill tone={STATUS_TONE[tile.status]} label={tile.status} />
                  <BiStatusPill tone={BI_TRUST_TONE[tile.trust]} label={`${tile.trust} 级`} />
                </div>
              </header>
              <p className="mt-2 text-xs text-slate-600">{tile.detail}</p>
              <p className="mt-2 text-[11px] text-slate-500">
                authority: {tile.authority} · owner: {tile.owner}
              </p>
            </article>
          )
        })}
      </div>

      <section className="rounded-md border border-slate-200 bg-white">
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">操作审计</h3>
            <p className="text-[11px] text-slate-500">
              authority: member_console.audit_log · 按操作人 / 目标 / 时间 / 动作类型 /
              敏感级别筛选。
            </p>
          </div>
          <span className="text-[11px] text-slate-500">
            {filteredAudit.length} / {AUDIT_ENTRIES.length}
          </span>
        </header>
        <div className="flex flex-wrap items-center gap-2 px-4 py-2 text-xs">
          <label className="inline-flex items-center gap-1">
            操作人
            <input
              type="text"
              value={auditFilter.actor}
              onChange={e => {
                if (composingActor) return
                setAuditFilter(f => ({ ...f, actor: e.target.value }))
              }}
              onCompositionStart={() => setComposingActor(true)}
              onCompositionEnd={e => {
                setComposingActor(false)
                setAuditFilter(f => ({ ...f, actor: e.currentTarget.value }))
              }}
              placeholder="ops@…"
              className="rounded border border-slate-200 px-1 py-0.5"
              aria-label="按操作人筛选"
            />
          </label>
          <label className="inline-flex items-center gap-1">
            目标
            <input
              type="text"
              value={auditFilter.target}
              onChange={e => {
                if (composingTarget) return
                setAuditFilter(f => ({ ...f, target: e.target.value }))
              }}
              onCompositionStart={() => setComposingTarget(true)}
              onCompositionEnd={e => {
                setComposingTarget(false)
                setAuditFilter(f => ({ ...f, target: e.currentTarget.value }))
              }}
              placeholder="u_… / ord_…"
              className="rounded border border-slate-200 px-1 py-0.5"
              aria-label="按目标筛选"
            />
          </label>
          <label className="inline-flex items-center gap-1">
            分类
            <select
              value={auditFilter.category}
              onChange={e =>
                setAuditFilter(f => ({ ...f, category: e.target.value as AuditFilter['category'] }))
              }
              className="rounded border border-slate-200 px-1 py-0.5"
              aria-label="按审计分类筛选"
            >
              <option value="">全部</option>
              {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label className="inline-flex items-center gap-1">
            敏感级别
            <select
              value={auditFilter.severity}
              onChange={e =>
                setAuditFilter(f => ({ ...f, severity: e.target.value as AuditFilter['severity'] }))
              }
              className="rounded border border-slate-200 px-1 py-0.5"
              aria-label="按敏感级别筛选"
            >
              <option value="">全部</option>
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => setAuditFilter(DEFAULT_AUDIT_FILTER)}
            className="ml-auto text-slate-500 hover:text-slate-900"
            aria-label="清空审计筛选"
          >
            清空
          </button>
        </div>
        <BiDataTable<AuditLogEntry>
          columns={auditColumns}
          rows={filteredAudit}
          rowKey={e => e.id}
          status={filteredAudit.length === 0 ? 'no-results' : 'ok'}
          emptyTitle="暂无审计"
        />
      </section>

      <section className="rounded-md border border-slate-200 bg-white">
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-2">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">导出任务</h3>
            <p className="text-[11px] text-slate-500">
              大数据导出走异步任务，必须脱敏 + 限频 + audit。
            </p>
          </div>
          <span className="text-[11px] text-slate-500">queued + running 即可见</span>
        </header>
        <BiDataTable<ExportJob>
          columns={exportColumns}
          rows={EXPORT_JOBS}
          rowKey={j => j.id}
          status="ok"
        />
      </section>
    </section>
  )
}
