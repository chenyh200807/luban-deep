export type Package = {
  id: string
  name: string
  tier: 'trial' | 'vip' | 'svip'
  points: number
  price_cny: number
  features: string[]
  status: 'active' | 'draft' | 'archived'
}

export type Order = {
  id: string
  user_id: string
  amount_cny: number
  channel: 'alipay' | 'wechat' | 'stripe' | 'manual'
  invoice_status: 'none' | 'requested' | 'issued' | 'void'
  created_at: string
  ledger_event_id?: string
  idempotency_key?: string
}

export type WalletLedgerRow = {
  id: string
  user_id: string
  kind: 'credit' | 'debit' | 'refund' | 'manual'
  amount: number
  idempotency_key: string
  session_id?: string
  usage_event_id?: string
  effective_at: string
  refund_origin_ledger_id?: string
  metadata?: Record<string, string>
}

export type Anomaly = {
  rule_id: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  detected_at: string
  affected: number
  owner: string
  status: 'new' | 'triaged' | 'resolved'
  trust: 'A' | 'B' | 'C' | 'D'
  description: string
}

// Round 4 S4 (M-B): mock data dev-only; production bundle contains [] and the
// panel renders skeleton + admin CTA instead.
export const PACKAGES: Package[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          id: 'pkg_trial',
          name: '试用 trial',
          tier: 'trial',
          points: 50,
          price_cny: 0,
          features: ['5 次会话', '基础学习卡'],
          status: 'active',
        },
        {
          id: 'pkg_vip_month',
          name: 'VIP 月卡',
          tier: 'vip',
          points: 1200,
          price_cny: 99,
          features: ['无限会话', '学习卡 + 笔记 + 测评'],
          status: 'active',
        },
        {
          id: 'pkg_svip_quarter',
          name: 'SVIP 季卡',
          tier: 'svip',
          points: 8000,
          price_cny: 499,
          features: ['全功能', '优先工单', '1v1 体验官'],
          status: 'active',
        },
        {
          id: 'pkg_svip_year',
          name: 'SVIP 年卡',
          tier: 'svip',
          points: 36000,
          price_cny: 1799,
          features: ['全功能', '优先工单', '1v1 体验官', '学习教练'],
          status: 'draft',
        },
      ]

export const ORDERS: Order[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          id: 'ord_2026_05231042',
          user_id: 'u_8519',
          amount_cny: 499,
          channel: 'alipay',
          invoice_status: 'issued',
          created_at: '2026-05-23 10:42',
          ledger_event_id: 'lg_001',
          idempotency_key: 'order:ord_2026_05231042',
        },
        {
          id: 'ord_2026_05230918',
          user_id: 'u_8788',
          amount_cny: 99,
          channel: 'wechat',
          invoice_status: 'requested',
          created_at: '2026-05-23 09:18',
          ledger_event_id: 'lg_002',
          idempotency_key: 'order:ord_2026_05230918',
        },
        {
          id: 'ord_2026_05222115',
          user_id: 'u_8421',
          amount_cny: 99,
          channel: 'alipay',
          invoice_status: 'none',
          created_at: '2026-05-22 21:15',
          ledger_event_id: 'lg_003',
          idempotency_key: 'order:ord_2026_05222115',
        },
        {
          id: 'ord_2026_05221830',
          user_id: 'u_8633',
          amount_cny: 1799,
          channel: 'stripe',
          invoice_status: 'void',
          created_at: '2026-05-22 18:30',
          ledger_event_id: 'lg_004',
          idempotency_key: 'order:ord_2026_05221830',
        },
      ]

export const LEDGER: WalletLedgerRow[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          id: 'lg_001',
          user_id: 'u_8519',
          kind: 'credit',
          amount: 8000,
          idempotency_key: 'order:ord_2026_05231042',
          effective_at: '2026-05-23 10:42',
          metadata: { channel: 'alipay', source: 'order' },
        },
        {
          id: 'lg_002',
          user_id: 'u_8788',
          kind: 'credit',
          amount: 1200,
          idempotency_key: 'order:ord_2026_05230918',
          effective_at: '2026-05-23 09:18',
          metadata: { channel: 'wechat', source: 'order' },
        },
        {
          id: 'lg_010',
          user_id: 'u_8519',
          kind: 'debit',
          amount: -120,
          idempotency_key: 'usage:s_92211',
          session_id: 's_92211',
          usage_event_id: 'ue_55001',
          effective_at: '2026-05-23 11:02',
          metadata: { capability: 'deep_solve' },
        },
        {
          id: 'lg_011',
          user_id: 'u_8421',
          kind: 'manual',
          amount: 100,
          idempotency_key: 'manual:ops-2026-0523-001',
          effective_at: '2026-05-23 09:45',
          metadata: { actor_id: 'ops@deeptutor', reason: '客服补偿' },
        },
        {
          id: 'lg_012',
          user_id: 'u_8633',
          kind: 'refund',
          amount: -8000,
          idempotency_key: 'refund:ord_2026_05221830',
          refund_origin_ledger_id: 'lg_004',
          effective_at: '2026-05-22 19:00',
          metadata: { reason: '退款 / 信用卡争议' },
        },
        {
          id: 'lg_013',
          user_id: 'u_8702',
          kind: 'debit',
          amount: -8,
          idempotency_key: 'usage:s_93302',
          effective_at: '2026-05-23 12:01',
          metadata: { capability: 'chat' },
        },
        {
          id: 'lg_014',
          user_id: 'u_8800',
          kind: 'credit',
          amount: 50,
          idempotency_key: 'promo:campaign_2026q2',
          effective_at: '2026-05-23 08:20',
          metadata: { source: 'promo' },
        },
      ]

export const ANOMALIES: Anomaly[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          rule_id: 'WALLET_NEGATIVE_BALANCE',
          severity: 'critical',
          detected_at: '今天 09:12',
          affected: 3,
          owner: 'wallet',
          status: 'new',
          trust: 'A',
          description: '近 1h 内单会员钱包余额计算为负。',
        },
        {
          rule_id: 'WALLET_CREDIT_WITHOUT_ORDER',
          severity: 'high',
          detected_at: '今天 04:00',
          affected: 7,
          owner: 'finance',
          status: 'triaged',
          trust: 'B',
          description: '近 7d credit 类入账缺 order:%idempotency_key。',
        },
        {
          rule_id: 'WALLET_DUPLICATE_IDEMPOTENCY',
          severity: 'critical',
          detected_at: '昨天 22:30',
          affected: 1,
          owner: 'wallet',
          status: 'new',
          trust: 'A',
          description: '同 idempotency_key 但 amount 不同。',
        },
        {
          rule_id: 'PACKAGE_GRANT_WITHOUT_AUDIT',
          severity: 'medium',
          detected_at: '近 3 天',
          affected: 5,
          owner: 'finance',
          status: 'new',
          trust: 'B',
          description: 'manual credit 但 audit_log 无对应条目。',
        },
        {
          rule_id: 'REFUND_WITHOUT_REVERSAL',
          severity: 'high',
          detected_at: '近 7 天',
          affected: 2,
          owner: 'finance',
          status: 'new',
          trust: 'B',
          description: 'refund 标记但 refund_origin 缺反向 debit。',
        },
      ]

export const PAYMENT_CHANNELS = ['alipay', 'wechat', 'stripe', 'manual'] as const
export const INVOICE_STATUSES = ['none', 'requested', 'issued', 'void'] as const
