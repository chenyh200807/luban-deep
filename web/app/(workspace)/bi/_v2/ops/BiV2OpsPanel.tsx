/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Download, Eye, History, Lock, RefreshCw, Rocket, ShieldAlert, ShieldCheck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  BiDataTable,
  BiSidePanel,
  BiStatusPill,
  BI_TRUST_TONE,
  type BiTableColumn,
} from '@/components/bi-v2'
import { getMemberAuditLog, type MemberAuditLogItem } from '@/lib/member-api'
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

function auditCategory(action: string): AuditLogEntry['category'] {
  const lower = action.toLowerCase()
  if (lower.includes('wallet') || lower.includes('ledger') || lower.includes('point')) return 'wallet'
  if (lower.includes('feedback')) return 'feedback'
  if (lower.includes('export')) return 'export'
  if (lower.includes('admin') || lower.includes('permission')) return 'permission'
  return 'member'
}

function auditSeverity(action: string): AuditLogEntry['severity'] {
  const lower = action.toLowerCase()
  if (lower.includes('revoke') || lower.includes('export') || lower.includes('admin')) return 'high'
  if (lower.includes('view') || lower.includes('conversation')) return 'medium'
  return 'low'
}

function mapAuditLogItem(item: MemberAuditLogItem, index: number): AuditLogEntry {
  const action = item.action || 'unknown'
  return {
    id: item.id || `audit-${index + 1}`,
    at: item.created_at || '—',
    actor: item.operator || 'system',
    action,
    target: item.target_user || '—',
    reason: item.reason,
    before: item.before,
    after: item.after,
    severity: auditSeverity(action),
    category: auditCategory(action),
  }
}

export function BiV2OpsPanel({ flagEnabled }: BiV2OpsPanelProps) {
  const [auditFilter, setAuditFilter] = useState<AuditFilter>(DEFAULT_AUDIT_FILTER)
  const [composingActor, setComposingActor] = useState(false)
  const [composingTarget, setComposingTarget] = useState(false)
  const [liveAudit, setLiveAudit] = useState<AuditLogEntry[]>([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditLoading, setAuditLoading] = useState(flagEnabled)
  const [auditError, setAuditError] = useState('')
  const [selectedTile, setSelectedTile] = useState<SystemOpsTile | null>(null)
  const [selectedAudit, setSelectedAudit] = useState<AuditLogEntry | null>(null)

  const loadAudit = useCallback(async () => {
    if (!flagEnabled) {
      setLiveAudit([])
      setAuditTotal(0)
      setAuditLoading(false)
      setAuditError('')
      return
    }
    try {
      setAuditLoading(true)
      setAuditError('')
      const response = await getMemberAuditLog({
        page: 1,
        page_size: 100,
        operator: auditFilter.actor.trim() || undefined,
        target_user: auditFilter.target.trim() || undefined,
      })
      setLiveAudit(response.items.map(mapAuditLogItem))
      setAuditTotal(response.total)
    } catch (err) {
      setAuditError(err instanceof Error ? err.message : '操作审计加载失败')
      setLiveAudit([])
      setAuditTotal(0)
    } finally {
      setAuditLoading(false)
    }
  }, [auditFilter.actor, auditFilter.target, flagEnabled])

  useEffect(() => {
    void loadAudit()
  }, [loadAudit])

  const filteredAudit = useMemo(
    () =>
      (flagEnabled ? liveAudit : AUDIT_ENTRIES).filter(e => {
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
    [auditFilter, flagEnabled, liveAudit]
  )

  const opsTiles = useMemo<SystemOpsTile[]>(() => {
    if (!flagEnabled) return OPS_TILES
    return [
      {
        key: 'audit-actions',
        label: '操作审计',
        status: auditError ? 'fail' : auditLoading ? 'warn' : 'ok',
        detail: auditError || `已接 member_console.audit_log，当前窗口返回 ${liveAudit.length} / ${auditTotal} 条。`,
        owner: 'ops',
        trust: 'A',
        authority: 'member_console.audit_log',
      },
      {
        key: 'data-trust',
        label: '数据可信中心',
        status: 'ok',
        detail: 'BI v2 只读模块已收敛到真实 API；无真实 endpoint 的模块保持不可点击。',
        owner: 'platform',
        trust: 'A',
        authority: 'bi_feature_flags + source guards',
      },
      {
        key: 'audit-export',
        label: '导出审计',
        status: 'warn',
        detail: '导出任务队列数据源待接入；当前不展示 dev mock。',
        owner: 'ops',
        trust: 'B',
        authority: 'member_console.export_members_csv',
      },
    ]
  }, [auditError, auditLoading, auditTotal, flagEnabled, liveAudit.length])

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
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
          <span>
            BI_SYSTEM_OPS_V2_ENABLED 已开启 · 操作审计读取{' '}
            <code className="font-mono">/api/v1/member/audit-log</code>；导出任务队列数据源待接入，
            不展示 mock。
          </span>
          <button
            type="button"
            onClick={() => void loadAudit()}
            disabled={auditLoading}
            className="inline-flex items-center gap-1 rounded border border-sky-200 bg-white px-2 py-1 text-sky-800 disabled:opacity-50"
            aria-label="刷新操作审计"
          >
            <RefreshCw className={`h-3 w-3 ${auditLoading ? 'animate-spin' : ''}`} aria-hidden />
            刷新
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {opsTiles.map(tile => {
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
              <button
                type="button"
                onClick={() => setSelectedTile(tile)}
                className="mt-3 inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-300"
                aria-label={`查看 ${tile.label} 详情`}
              >
                <Eye className="h-3 w-3" aria-hidden />
                查看详情
              </button>
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
            {filteredAudit.length} / {flagEnabled ? auditTotal : AUDIT_ENTRIES.length}
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
          status={
            auditLoading
              ? 'loading'
              : auditError
                ? 'error'
                : filteredAudit.length === 0
                  ? flagEnabled
                    ? 'empty'
                    : 'no-results'
                  : 'ok'
          }
          errorMessage={auditError}
          emptyTitle="暂无审计"
          emptyHint="当前 audit_log 没有返回记录。"
          rowAction={entry => (
            <button
              type="button"
              onClick={() => setSelectedAudit(entry)}
              className="rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-50"
              aria-label={`查看审计 ${entry.id} 详情`}
            >
              <Eye className="h-3 w-3" aria-hidden />
            </button>
          )}
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
          rows={flagEnabled ? [] : EXPORT_JOBS}
          rowKey={j => j.id}
          status={flagEnabled ? 'empty' : 'ok'}
          emptyTitle="暂无导出任务"
          emptyHint="导出任务队列 endpoint 尚未存在；当前只保留脱敏导出的设计入口。"
        />
      </section>
      <OpsTileDetailPanel tile={selectedTile} onClose={() => setSelectedTile(null)} />
      <AuditDetailPanel entry={selectedAudit} onClose={() => setSelectedAudit(null)} />
    </section>
  )
}

function OpsTileDetailPanel({
  tile,
  onClose,
}: {
  tile: SystemOpsTile | null
  onClose: () => void
}) {
  return (
    <BiSidePanel
      open={Boolean(tile)}
      onClose={onClose}
      title={tile ? `运维详情 · ${tile.label}` : '运维详情'}
      subtitle={tile ? `${tile.status} · ${tile.trust} 级可信` : undefined}
      width="md"
    >
      {tile ? (
        <div className="space-y-4 text-sm">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center gap-2">
              <BiStatusPill tone={STATUS_TONE[tile.status]} label={tile.status} />
              <BiStatusPill tone={BI_TRUST_TONE[tile.trust]} label={`${tile.trust} 级`} />
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-700">{tile.detail}</p>
          </div>
          <KV label="authority" value={tile.authority} />
          <KV label="owner" value={tile.owner} />
          <KV
            label="处理原则"
            value="只读状态可直接展示；导出、权限变更、派单等写动作必须经过 audited endpoint。"
          />
        </div>
      ) : null}
    </BiSidePanel>
  )
}

function AuditDetailPanel({
  entry,
  onClose,
}: {
  entry: AuditLogEntry | null
  onClose: () => void
}) {
  return (
    <BiSidePanel
      open={Boolean(entry)}
      onClose={onClose}
      title={entry ? `审计详情 · ${entry.id}` : '审计详情'}
      subtitle={entry ? `${CATEGORY_LABEL[entry.category]} · ${entry.severity}` : undefined}
      width="lg"
    >
      {entry ? (
        <div className="space-y-4 text-sm">
          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <BiStatusPill tone={SEVERITY_TONE[entry.severity]} label={entry.severity} />
              <span className="font-medium text-slate-900">{entry.action}</span>
            </div>
            <p className="mt-2 text-xs text-slate-600">
              {entry.actor} → {entry.target}
            </p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <KV label="时间" value={entry.at} />
            <KV label="操作人" value={entry.actor} />
            <KV label="目标" value={entry.target} />
            <KV label="分类" value={CATEGORY_LABEL[entry.category]} />
            <KV label="原因" value={entry.reason || '—'} />
            <KV label="audit_id" value={entry.id} />
          </div>
          <JsonBlock label="before" value={entry.before} />
          <JsonBlock label="after" value={entry.after} />
        </div>
      ) : null}
    </BiSidePanel>
  )
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="text-[11px] font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 break-words text-sm text-slate-800">{value || '—'}</div>
    </div>
  )
}

function JsonBlock({ label, value }: { label: string; value?: Record<string, unknown> }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="text-[11px] font-medium uppercase text-slate-500">{label}</div>
      <pre className="mt-2 max-h-60 overflow-auto rounded bg-slate-950 p-3 text-xs leading-relaxed text-slate-100">
        {value && Object.keys(value).length > 0 ? JSON.stringify(value, null, 2) : '—'}
      </pre>
    </div>
  )
}
