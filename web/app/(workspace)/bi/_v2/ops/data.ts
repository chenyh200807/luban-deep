export type SystemOpsTile = {
  key: string
  label: string
  status: 'ok' | 'warn' | 'fail'
  detail: string
  owner: string
  trust: 'A' | 'B' | 'C' | 'D'
  authority: string
}

// Round 4 S4 (M-B): mock data dev-only; production bundle contains [].
export const OPS_TILES: SystemOpsTile[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          key: 'cost-quality',
          label: '成本质量',
          status: 'warn',
          detail: '24h LLM 成本 +12.8%，估算未对账。',
          owner: 'platform',
          trust: 'C',
          authority: 'observability.cost_estimator',
        },
        {
          key: 'data-trust',
          label: '数据可信中心',
          status: 'ok',
          detail: 'A 12 / B 24 / C 8 / D 3 · 7 项口径文档待更新。',
          owner: 'platform',
          trust: 'A',
          authority: 'bi_service.data_trust',
        },
        {
          key: 'audit-actions',
          label: '操作审计',
          status: 'ok',
          detail: '近 24h 318 条，0 高危。',
          owner: 'ops',
          trust: 'A',
          authority: 'member_console.audit_log',
        },
        {
          key: 'audit-perm',
          label: '权限审计',
          status: 'warn',
          detail: '1 位 admin 30 天未活跃，建议复核或停用。',
          owner: 'ops',
          trust: 'A',
          authority: 'bi_admin_auth.profiles',
        },
        {
          key: 'audit-export',
          label: '导出审计',
          status: 'ok',
          detail: '近 7d 14 次导出，全部脱敏 + 限频。',
          owner: 'ops',
          trust: 'A',
          authority: 'member_console.exports',
        },
        {
          key: 'release',
          label: '上线面板',
          status: 'ok',
          detail: 'release gate 通过，contract guard 通过，benchmark 4ms。',
          owner: 'platform',
          trust: 'A',
          authority: 'launch_readiness',
        },
      ]

export type AuditLogEntry = {
  id: string
  at: string
  actor: string
  action: string
  target: string
  severity: 'low' | 'medium' | 'high'
  category: 'member' | 'wallet' | 'feedback' | 'export' | 'permission'
}

export const AUDIT_ENTRIES: AuditLogEntry[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          id: 'al_1',
          at: '今天 11:25',
          actor: 'ops@deeptutor',
          action: '添加备注',
          target: 'u_8421',
          severity: 'low',
          category: 'member',
        },
        {
          id: 'al_2',
          at: '今天 11:21',
          actor: 'ops@deeptutor',
          action: '标记已联系',
          target: 'u_8519',
          severity: 'low',
          category: 'member',
        },
        {
          id: 'al_3',
          at: '今天 10:42',
          actor: 'finance@deeptutor',
          action: '导出充值订单 CSV',
          target: 'orders/2026-05',
          severity: 'high',
          category: 'export',
        },
        {
          id: 'al_4',
          at: '今天 09:30',
          actor: 'ops@deeptutor',
          action: '查看对话全文',
          target: 'u_8633/s_002',
          severity: 'medium',
          category: 'member',
        },
        {
          id: 'al_5',
          at: '今天 09:12',
          actor: 'system',
          action: '检测异常 WALLET_NEGATIVE_BALANCE',
          target: 'wallet_ledger',
          severity: 'high',
          category: 'wallet',
        },
        {
          id: 'al_6',
          at: '昨天 22:11',
          actor: 'ops@deeptutor',
          action: '分诊反馈',
          target: 'fb_9014',
          severity: 'low',
          category: 'feedback',
        },
        {
          id: 'al_7',
          at: '昨天 18:45',
          actor: 'admin@deeptutor',
          action: '新增 admin',
          target: 'qa-2@deeptutor',
          severity: 'high',
          category: 'permission',
        },
      ]

export type ExportJob = {
  id: string
  name: string
  rows: number
  status: 'queued' | 'running' | 'done' | 'failed'
  scrubbed: boolean
  rate_limit_per_hour: number
  requested_at: string
  done_at?: string
}

export const EXPORT_JOBS: ExportJob[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          id: 'ex_001',
          name: '会员名单（脱敏）',
          rows: 5230,
          status: 'done',
          scrubbed: true,
          rate_limit_per_hour: 5,
          requested_at: '今天 10:00',
          done_at: '今天 10:02',
        },
        {
          id: 'ex_002',
          name: '充值订单 2026-05',
          rows: 142,
          status: 'done',
          scrubbed: true,
          rate_limit_per_hour: 10,
          requested_at: '今天 09:50',
          done_at: '今天 09:51',
        },
        {
          id: 'ex_003',
          name: 'AI 反馈 negative 近 30d',
          rows: 86,
          status: 'running',
          scrubbed: true,
          rate_limit_per_hour: 10,
          requested_at: '今天 11:30',
        },
      ]
