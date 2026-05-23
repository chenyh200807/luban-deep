/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { BiSidePanel, BiMoneyCell, BiStatusPill, BI_TRUST_TONE } from '@/components/bi-v2'
import type { MemberRow } from './data'

export type Member360DrawerProps = {
  open: boolean
  member: MemberRow | null
  onClose: () => void
  onOpenConversation: () => void
}

export function Member360Drawer({
  open,
  member,
  onClose,
  onOpenConversation,
}: Member360DrawerProps) {
  if (!member) return null
  return (
    <BiSidePanel
      open={open}
      onClose={onClose}
      title={`学员 360 · ${member.phone_masked}`}
      subtitle={`user_id: ${member.user_id} · ${member.tier.toUpperCase()} · 风险 ${member.risk.toFixed(2)}`}
      width="lg"
      footer={
        <div className="flex items-center justify-end gap-2">
          {/*
            "标记已联系" / "添加备注" 的真实写入由 Round 3 B 的 useAuditedAction
            统一注入 actor + idempotency_key 后实装。Round 3 A 阶段先禁用，避免
            UI 暗示已写入服务端（计划 §3.5 admin write 硬约束未满足前不应放行）。
          */}
          <button
            type="button"
            disabled
            className="cursor-not-allowed rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-400"
            aria-label="标记已联系（待 useAuditedAction 接入）"
            title="P1 接 useAuditedAction 后启用"
          >
            标记已联系
          </button>
          <button
            type="button"
            disabled
            className="cursor-not-allowed rounded border border-slate-200 px-3 py-1.5 text-xs text-slate-400"
            aria-label="添加备注（待 useAuditedAction 接入）"
            title="P1 接 useAuditedAction 后启用"
          >
            添加备注
          </button>
          <button
            type="button"
            onClick={onOpenConversation}
            className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white hover:bg-slate-800"
            aria-label="查看会员对话回顾"
          >
            查看对话回顾
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <Section title="账户摘要" trust="A">
          <KV label="user_id" value={<code className="font-mono">{member.user_id}</code>} />
          <KV label="手机号" value={member.phone_masked} />
          <KV label="Tier" value={member.tier.toUpperCase()} />
          <KV label="状态" value={member.status} />
          <KV label="到期" value={member.expires_at} />
          <KV label="首充" value={member.paid_at_first ?? '未付费'} />
          <KV label="最近活跃" value={member.last_active} />
        </Section>

        <Section title="钱包" trust="A">
          <KV
            label="余额"
            value={<BiMoneyCell amount={member.balance_points} currency="POINT" align="left" />}
          />
          <p className="text-[11px] text-slate-500">
            authority: WalletService.list_wallet_ledger · 流水入口由 Batch 4 商品账务接入。
          </p>
        </Section>

        <Section title="学习画像" trust="A">
          <p className="text-xs text-slate-600">
            learner_state read model 概览：掌握度、错题、近期 capability。Batch 3+ 真实接入{' '}
            <code className="font-mono">/api/v1/member/{member.user_id}/learner-state</code>。
          </p>
        </Section>

        <Section title="运营记录" trust="A">
          <KV label="备注数" value={`${member.notes_count ?? 0}`} />
          <KV label="反馈数" value={`${member.feedback_count ?? 0}`} />
          <p className="text-[11px] text-slate-500">
            运营动作写入{' '}
            <code className="font-mono">/api/v1/member/{member.user_id}/ops-actions</code>，每条均带
            audit。
          </p>
        </Section>

        <div className="rounded border border-amber-200 bg-amber-50 p-3 text-[11px] text-amber-800">
          危险动作（撤销会员 / 补点数 / 异常处理）当前禁用：等 etag / version / undo_token
          后端就绪后启用（计划 §3.5）。
        </div>
      </div>
    </BiSidePanel>
  )
}

function Section({
  title,
  trust,
  children,
}: {
  title: string
  trust: 'A' | 'B' | 'C' | 'D'
  children: React.ReactNode
}) {
  return (
    <section className="rounded border border-slate-200 bg-white p-3">
      <header className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
        <BiStatusPill tone={BI_TRUST_TONE[trust]} label={`${trust} 级`} />
      </header>
      <div className="space-y-1.5 text-xs">{children}</div>
    </section>
  )
}

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-slate-500">{label}</span>
      <span className="text-slate-800">{value}</span>
    </div>
  )
}
