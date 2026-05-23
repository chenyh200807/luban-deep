/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { CheckCircle2, MessageSquareWarning, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { BiDataTable, BiStatusPill, type BiTableColumn } from '@/components/bi-v2'
import {
  FEEDBACK_ITEMS,
  OWNER_LABELS,
  SOURCE_LABELS,
  STATUS_LABELS,
  type FeedbackItem,
  type FeedbackOwner,
  type FeedbackResolution,
  type FeedbackStatus,
} from './data'

type Filter = {
  status: '' | FeedbackStatus
  source: '' | FeedbackItem['source']
  owner: '' | FeedbackOwner
}

const DEFAULT_FILTER: Filter = { status: '', source: '', owner: '' }

const STATUS_TONE: Record<FeedbackStatus, 'amber' | 'sky' | 'slate'> = {
  open: 'amber',
  triaged: 'sky',
  ignored: 'slate',
}

const SOURCE_TONE = {
  ai_message: 'sky',
  invite_test: 'amber',
  member_note: 'slate',
} as const

export type BiV2FeedbackPanelProps = {
  flagEnabled: boolean
}

export function BiV2FeedbackPanel({ flagEnabled }: BiV2FeedbackPanelProps) {
  const [filter, setFilter] = useState<Filter>(DEFAULT_FILTER)
  const [resolutions, setResolutions] = useState<FeedbackResolution[]>([])
  const [groupByOwner, setGroupByOwner] = useState(false)

  const items = useMemo<FeedbackItem[]>(() => {
    return FEEDBACK_ITEMS.map(item => {
      const r = resolutions.find(res => res.feedbackId === item.id)
      if (!r) return item
      return { ...item, status: r.status, resolution: r.note }
    })
  }, [resolutions])

  const filtered = useMemo(
    () =>
      items.filter(i => {
        if (filter.status && i.status !== filter.status) return false
        if (filter.source && i.source !== filter.source) return false
        if (filter.owner && i.owner !== filter.owner) return false
        return true
      }),
    [items, filter]
  )

  const counts = useMemo(() => {
    return {
      total: items.length,
      open: items.filter(i => i.status === 'open').length,
      triaged: items.filter(i => i.status === 'triaged').length,
      ignored: items.filter(i => i.status === 'ignored').length,
    }
  }, [items])

  // Round 4 S3: removed window.prompt + fabricated actor='ops@deeptutor' +
  // local-only setResolutions. That trio was the canonical "fake audit" anti-
  // pattern surfaced by the spec auditor. Until backend exposes a real
  // feedback triage endpoint (registered in WRITE_ENDPOINTS), the triage
  // buttons remain disabled with an explicit "等接入 useAuditedAction" hint
  // rather than silently fabricating an audited write.
  function triage(_item: FeedbackItem, _next: Exclude<FeedbackStatus, 'open'>) {
    // intentionally no-op until backend feedback endpoint is registered.
  }

  const columns = useMemo<BiTableColumn<FeedbackItem>[]>(
    () => [
      {
        key: 'source',
        label: '来源',
        render: i => <BiStatusPill tone={SOURCE_TONE[i.source]} label={SOURCE_LABELS[i.source]} />,
      },
      {
        key: 'rating',
        label: '评分',
        align: 'right',
        render: i => <span className="tabular-nums">{i.rating} / 5</span>,
      },
      {
        key: 'reason',
        label: '原因 / 内容',
        render: i => (
          <div className="min-w-0">
            <div className="truncate text-slate-800">{i.reason}</div>
            <div className="truncate text-[11px] text-slate-500">{i.detail}</div>
          </div>
        ),
      },
      {
        key: 'member',
        label: '关联会员',
        render: i => <code className="font-mono">{i.member}</code>,
      },
      {
        key: 'status',
        label: '状态',
        render: i => <BiStatusPill tone={STATUS_TONE[i.status]} label={STATUS_LABELS[i.status]} />,
      },
      { key: 'owner', label: 'owner', render: i => OWNER_LABELS[i.owner] },
      {
        key: 'sla',
        label: 'SLA',
        render: i => (i.sla_target_hours > 0 ? `${i.sla_target_hours}h` : '—'),
      },
      {
        key: 'at',
        label: '时间',
        render: i => <span className="text-slate-500">{i.created_at}</span>,
      },
    ],
    []
  )

  const grouped = useMemo(() => {
    const map = new Map<FeedbackOwner, FeedbackItem[]>()
    for (const item of filtered) {
      const arr = map.get(item.owner) ?? []
      arr.push(item)
      map.set(item.owner, arr)
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [filtered])

  return (
    <section className="space-y-5">
      {!flagEnabled ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          BI_FEEDBACK_V2_ENABLED 未开启 · 当前 Batch 5 静态原型。P0 仅接 AI 消息反馈 / 内测申请 /
          运营备注；P1 再接教研 / 系统质量。
        </div>
      ) : (
        // Round 4 S5: triage 按钮已硬禁用（Round 4 S3 删除 window.prompt 假
        // audit 路径），banner 必须诚实反映"flag 开启但 triage 未接入 useAuditedAction"。
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-800">
          BI_FEEDBACK_V2_ENABLED flag 已开启 · 列表展示对齐；triage 写入待接入 useAuditedAction
          （registry 注册 + 后端 endpoint），当前按钮禁用。
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
        <Tile label="全部" value={counts.total} hint="近 7d" />
        <Tile label="待处理" value={counts.open} tone="amber" hint="P0 优先处理" />
        <Tile label="已分诊" value={counts.triaged} tone="sky" hint="已转 owner" />
        <Tile label="已忽略" value={counts.ignored} tone="slate" hint="带 audit 说明" />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <label className="inline-flex items-center gap-1">
          状态
          <select
            value={filter.status}
            onChange={e => setFilter({ ...filter, status: e.target.value as Filter['status'] })}
            className="rounded border border-slate-200 px-1 py-0.5"
            aria-label="按状态筛选反馈"
          >
            <option value="">全部</option>
            <option value="open">待处理</option>
            <option value="triaged">已分诊</option>
            <option value="ignored">已忽略</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          来源
          <select
            value={filter.source}
            onChange={e => setFilter({ ...filter, source: e.target.value as Filter['source'] })}
            className="rounded border border-slate-200 px-1 py-0.5"
            aria-label="按来源筛选反馈"
          >
            <option value="">全部</option>
            <option value="ai_message">AI 消息反馈</option>
            <option value="invite_test">内测申请</option>
            <option value="member_note">运营备注</option>
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          owner
          <select
            value={filter.owner}
            onChange={e => setFilter({ ...filter, owner: e.target.value as Filter['owner'] })}
            className="rounded border border-slate-200 px-1 py-0.5"
            aria-label="按 owner 筛选反馈"
          >
            <option value="">全部</option>
            <option value="quality">AI 质量</option>
            <option value="growth">增长</option>
            <option value="ops">运营</option>
            <option value="product">产品</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => setGroupByOwner(v => !v)}
          aria-pressed={groupByOwner}
          className={`rounded border px-2 py-0.5 ${
            groupByOwner
              ? 'border-slate-900 bg-slate-900 text-white'
              : 'border-slate-200 text-slate-700 hover:bg-slate-50'
          }`}
        >
          {groupByOwner ? '取消 owner 分组' : '按 owner 分组'}
        </button>
        <button
          type="button"
          onClick={() => setFilter(DEFAULT_FILTER)}
          className="ml-auto text-slate-500 hover:text-slate-900"
          aria-label="清空反馈筛选"
        >
          清空筛选
        </button>
      </div>

      {!groupByOwner ? (
        <BiDataTable<FeedbackItem>
          columns={columns}
          rows={filtered}
          rowKey={i => i.id}
          status={filtered.length === 0 ? 'no-results' : 'ok'}
          emptyTitle="暂无反馈"
          rowAction={i => (
            <div className="flex justify-end gap-1">
              <button
                type="button"
                disabled
                title="等接入 useAuditedAction 后启用（Round 4 S3 invariant）"
                className="cursor-not-allowed rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-400"
                aria-label={`分诊反馈 ${i.id}（待 useAuditedAction 接入）`}
              >
                <CheckCircle2 className="h-3 w-3" aria-hidden />
              </button>
              <button
                type="button"
                disabled
                title="等接入 useAuditedAction 后启用（Round 4 S3 invariant）"
                className="cursor-not-allowed rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-400"
                aria-label={`忽略反馈 ${i.id}（待 useAuditedAction 接入）`}
              >
                <XCircle className="h-3 w-3" aria-hidden />
              </button>
            </div>
          )}
        />
      ) : (
        <div className="space-y-4">
          {grouped.length === 0 ? (
            <div className="rounded border border-slate-200 bg-white p-6 text-center text-xs text-slate-500">
              当前筛选下无反馈
            </div>
          ) : null}
          {grouped.map(([owner, list]) => (
            <article key={owner} className="rounded-md border border-slate-200 bg-white">
              <header className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-xs">
                <h3 className="font-semibold text-slate-900">
                  {OWNER_LABELS[owner]} · {list.length}
                </h3>
              </header>
              <BiDataTable<FeedbackItem>
                columns={columns}
                rows={list}
                rowKey={i => i.id}
                status="ok"
                rowAction={i => (
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      disabled
                      title="等接入 useAuditedAction 后启用（Round 4 S3 invariant）"
                      className="cursor-not-allowed rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-400"
                      aria-label={`分诊反馈 ${i.id}（待 useAuditedAction 接入）`}
                    >
                      <CheckCircle2 className="h-3 w-3" aria-hidden />
                    </button>
                    <button
                      type="button"
                      disabled
                      title="等接入 useAuditedAction 后启用（Round 4 S3 invariant）"
                      className="cursor-not-allowed rounded border border-slate-200 px-2 py-1 text-[11px] text-slate-400"
                      aria-label={`忽略反馈 ${i.id}（待 useAuditedAction 接入）`}
                    >
                      <XCircle className="h-3 w-3" aria-hidden />
                    </button>
                  </div>
                )}
              />
            </article>
          ))}
        </div>
      )}

      {resolutions.length > 0 ? (
        <details
          className="rounded border border-slate-200 bg-white p-2 text-[11px] text-slate-600"
          open
        >
          <summary className="cursor-pointer text-slate-700">本会话 audit 预览</summary>
          <ul className="mt-2 space-y-0.5">
            {resolutions.map(r => (
              <li key={`${r.feedbackId}-${r.at}`} className="font-mono text-[10px]">
                {r.at} · {r.actor} · {r.feedbackId} → {STATUS_LABELS[r.status]} · {r.note}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <aside className="rounded border border-slate-200 bg-white p-4 text-xs text-slate-600">
        <div className="flex items-center gap-2 font-medium text-slate-800">
          <MessageSquareWarning className="h-4 w-4" aria-hidden /> 对话回顾入口
        </div>
        <p className="mt-1">
          对话回顾归入「会员运营 → 学员 360 → 查看对话回顾」。全文查看必须选择原因（合规审查 /
          投诉处理 / 模型质量 / 其他）并写入 audit。
        </p>
        <p className="mt-1 text-[11px] text-slate-500">
          authority: session store · view-audit endpoint:
          /api/v1/member/&lt;user_id&gt;/conversations/&lt;session_id&gt;/view-audit
        </p>
      </aside>
    </section>
  )
}

function Tile({
  label,
  value,
  hint,
  tone = 'slate',
}: {
  label: string
  value: number
  hint: string
  tone?: 'slate' | 'amber' | 'sky' | 'rose'
}) {
  const toneClass: Record<typeof tone, string> = {
    slate: 'border-slate-200',
    amber: 'border-amber-200 bg-amber-50',
    sky: 'border-sky-200 bg-sky-50',
    rose: 'border-rose-200 bg-rose-50',
  }
  return (
    <div className={`rounded-md border bg-white p-3 ${toneClass[tone]}`}>
      <div className="text-xs text-slate-600">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      <div className="mt-0.5 text-[11px] text-slate-500">{hint}</div>
    </div>
  )
}
