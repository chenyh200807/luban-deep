export type MemberRow = {
  user_id: string
  phone_masked: string
  tier: 'trial' | 'vip' | 'svip'
  status: 'active' | 'expiring' | 'expired' | 'paused'
  risk: number
  last_active: string
  balance_points: number
  expires_at: string
  paid_at_first?: string
  region?: string
  notes_count?: number
  feedback_count?: number
}

export type MemberColumnKey =
  | 'phone'
  | 'tier'
  | 'status'
  | 'risk'
  | 'last_active'
  | 'balance'
  | 'expires_at'
  | 'paid_first'
  | 'region'
  | 'notes'
  | 'feedback'

export type MemberColumnDef = {
  key: MemberColumnKey
  label: string
  sortable?: boolean
  align?: 'left' | 'right' | 'center'
}

export const ALL_COLUMNS: MemberColumnDef[] = [
  { key: 'phone', label: '手机号', sortable: true },
  { key: 'tier', label: 'Tier', sortable: true },
  { key: 'status', label: '状态' },
  { key: 'risk', label: '风险', sortable: true, align: 'right' },
  { key: 'last_active', label: '最近活跃' },
  { key: 'balance', label: '余额(点)', sortable: true, align: 'right' },
  { key: 'expires_at', label: '到期', sortable: true },
  { key: 'paid_first', label: '首充' },
  { key: 'region', label: '地区' },
  { key: 'notes', label: '备注数', align: 'right' },
  { key: 'feedback', label: '反馈数', align: 'right' },
]

export const DEFAULT_COLUMNS: MemberColumnKey[] = [
  'phone',
  'tier',
  'status',
  'risk',
  'last_active',
  'balance',
  'expires_at',
]

export type MemberFilters = {
  tier: '' | 'trial' | 'vip' | 'svip'
  status: '' | 'active' | 'expiring' | 'expired' | 'paused'
  riskMin: number
  expiringDays: number // 0 = 不限
  notPaid: boolean
}

export const DEFAULT_FILTERS: MemberFilters = {
  tier: '',
  status: '',
  riskMin: 0,
  expiringDays: 0,
  notPaid: false,
}

export type SavedView = {
  id: string
  name: string
  filters: MemberFilters
  columns: MemberColumnKey[]
  query: string
}

// Base seed list shown deterministically (8 rows) so screenshots / visual
// review remain stable. `MOCK_MEMBERS` below repeats and varies the seed to
// reach ~120 rows so BiDataTable's pageSize / cursor path runs in dev.
const SEED_MEMBERS: MemberRow[] = [
  {
    user_id: 'u_8421',
    phone_masked: '138****9821',
    tier: 'vip',
    status: 'expiring',
    risk: 0.82,
    last_active: '2 小时前',
    balance_points: 312,
    expires_at: '2026-05-25',
    paid_at_first: '2025-12-12',
    region: '浙江',
    notes_count: 2,
    feedback_count: 1,
  },
  {
    user_id: 'u_8519',
    phone_masked: '150****3300',
    tier: 'svip',
    status: 'active',
    risk: 0.41,
    last_active: '刚刚',
    balance_points: 8210,
    expires_at: '2026-12-31',
    paid_at_first: '2025-08-09',
    region: '北京',
    notes_count: 4,
    feedback_count: 0,
  },
  {
    user_id: 'u_8633',
    phone_masked: '139****0142',
    tier: 'vip',
    status: 'expired',
    risk: 0.95,
    last_active: '8 天前',
    balance_points: 0,
    expires_at: '2026-05-15',
    paid_at_first: '2025-04-22',
    region: '广东',
    notes_count: 1,
    feedback_count: 3,
  },
  {
    user_id: 'u_8702',
    phone_masked: '176****6601',
    tier: 'trial',
    status: 'active',
    risk: 0.55,
    last_active: '12 小时前',
    balance_points: 50,
    expires_at: '2026-06-02',
    region: '江苏',
    notes_count: 0,
    feedback_count: 0,
  },
  {
    user_id: 'u_8788',
    phone_masked: '187****1129',
    tier: 'vip',
    status: 'active',
    risk: 0.32,
    last_active: '3 小时前',
    balance_points: 1240,
    expires_at: '2026-07-18',
    paid_at_first: '2026-01-04',
    region: '上海',
    notes_count: 1,
    feedback_count: 1,
  },
  {
    user_id: 'u_8801',
    phone_masked: '133****8800',
    tier: 'svip',
    status: 'paused',
    risk: 0.61,
    last_active: '1 天前',
    balance_points: 4480,
    expires_at: '2026-11-09',
    paid_at_first: '2025-09-21',
    region: '四川',
    notes_count: 3,
    feedback_count: 2,
  },
  {
    user_id: 'u_8866',
    phone_masked: '152****7711',
    tier: 'trial',
    status: 'expiring',
    risk: 0.74,
    last_active: '5 小时前',
    balance_points: 20,
    expires_at: '2026-05-24',
    region: '山东',
    notes_count: 0,
    feedback_count: 0,
  },
  {
    user_id: 'u_8932',
    phone_masked: '186****4567',
    tier: 'vip',
    status: 'active',
    risk: 0.21,
    last_active: '6 小时前',
    balance_points: 980,
    expires_at: '2026-09-30',
    paid_at_first: '2026-03-01',
    region: '福建',
    notes_count: 0,
    feedback_count: 0,
  },
]

// Expand seed to ~120 rows so BiDataTable's pageSize=50 + IntersectionObserver
// pagination has data to act on. The first 8 rows remain the seed (stable for
// snapshots); rows 9+ are deterministic variants suffixed with batch idx.
function expandMockMembers(seed: MemberRow[], targetCount: number): MemberRow[] {
  const out: MemberRow[] = [...seed]
  let batch = 1
  while (out.length < targetCount) {
    for (const row of seed) {
      if (out.length >= targetCount) break
      out.push({
        ...row,
        user_id: `${row.user_id}_b${batch}`,
        phone_masked: row.phone_masked.replace(/\d{4}$/, String(batch).padStart(4, '0')),
      })
    }
    batch += 1
  }
  return out
}

// Round 4 S4 (M-B): mock data must not ship in the production bundle. Next.js
// inlines `process.env.NODE_ENV` and Terser dead-code-eliminates the unreachable
// branch in a production build, so SEED_MEMBERS / expandMockMembers / their
// literals are excluded from `.next/static/chunks/*` while still available in
// dev for design review. Panels detect the empty array and render skeleton +
// admin CTA instead of fake data.
export const MOCK_MEMBERS: MemberRow[] =
  process.env.NODE_ENV !== 'production' ? expandMockMembers(SEED_MEMBERS, 120) : []

export function filterMembers(
  rows: ReadonlyArray<MemberRow>,
  filters: MemberFilters,
  query: string
): MemberRow[] {
  const q = query.trim().toLowerCase()
  return rows.filter(row => {
    if (filters.tier && row.tier !== filters.tier) return false
    if (filters.status && row.status !== filters.status) return false
    if (filters.riskMin > 0 && row.risk < filters.riskMin) return false
    if (filters.notPaid && row.paid_at_first) return false
    if (filters.expiringDays > 0) {
      const exp = Date.parse(row.expires_at)
      const cutoff = Date.now() + filters.expiringDays * 86400000
      // 日期解析失败时保留行（让运营看到格式异常的会员），仅在能解析成功且超过 cutoff 时过滤。
      if (!Number.isNaN(exp) && exp > cutoff) return false
    }
    if (q) {
      const matches =
        row.user_id.toLowerCase().includes(q) ||
        row.phone_masked.replace(/[^0-9]/g, '').includes(q.replace(/[^0-9]/g, '')) ||
        (row.region ?? '').toLowerCase().includes(q)
      if (!matches) return false
    }
    return true
  })
}
