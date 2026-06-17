export type MemberRow = {
  user_id: string
  phone_masked: string
  tier: 'trial' | 'vip' | 'svip' | 'supreme_svip'
  status: 'active' | 'expiring' | 'expired' | 'paused'
  risk: number
  last_active: string
  balance_points: number
  expires_at: string
  paid_at_first?: string
  region?: string
  notes_count?: number
  feedback_count?: number
  behavior_learning_report_7d?: number
  behavior_history_7d?: number
  behavior_cohort?: string
  behavior_trust?: string
  behavior_next_action?: string
  behavior_reasons?: string[]
  behavior_event_count_7d?: number
  behavior_last_event_at_ms?: number
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
  | 'behavior_report'
  | 'behavior_history'
  | 'behavior_cohort'
  | 'behavior_next_action'

export type MemberColumnDef = {
  key: MemberColumnKey
  label: string
  sortable?: boolean
  align?: 'left' | 'right' | 'center'
}

export const ALL_COLUMNS: MemberColumnDef[] = [
  { key: 'phone', label: '手机号', sortable: true },
  { key: 'tier', label: 'Tier', sortable: true },
  { key: 'status', label: '状态', sortable: true },
  { key: 'risk', label: '风险', sortable: true, align: 'right' },
  { key: 'last_active', label: '最近活跃', sortable: true },
  { key: 'balance', label: '余额(点)', sortable: true, align: 'right' },
  { key: 'expires_at', label: '到期', sortable: true },
  { key: 'paid_first', label: '首充' },
  { key: 'region', label: '地区' },
  { key: 'notes', label: '备注数', align: 'right' },
  { key: 'feedback', label: '反馈数', align: 'right' },
  { key: 'behavior_report', label: '学情7日', sortable: true, align: 'right' },
  { key: 'behavior_history', label: '历史7日', sortable: true, align: 'right' },
  { key: 'behavior_cohort', label: '行为队列' },
  { key: 'behavior_next_action', label: '建议动作' },
]

export const DEFAULT_COLUMNS: MemberColumnKey[] = [
  'phone',
  'tier',
  'status',
  'risk',
  'behavior_report',
  'behavior_history',
  'behavior_cohort',
  'behavior_next_action',
  'last_active',
  'balance',
  'expires_at',
]

export type MemberFilters = {
  tier: '' | 'trial' | 'vip' | 'svip' | 'supreme_svip'
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

export type MemberSortDir = 'asc' | 'desc'
export type MemberSortKey = Extract<
  MemberColumnKey,
  'phone' | 'tier' | 'status' | 'risk' | 'last_active' | 'balance' | 'expires_at' | 'paid_first' | 'region' | 'notes' | 'feedback'
>

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
// Round 5 M5: polarity standardised to `=== 'production' ? [] : ...` across
// all BI v2 mock fixtures so a future editor copy-pasting between files
// cannot accidentally flip the guard direction.
export const MOCK_MEMBERS: MemberRow[] =
  process.env.NODE_ENV === 'production' ? [] : expandMockMembers(SEED_MEMBERS, 120)

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

export function sortMembers(
  rows: ReadonlyArray<MemberRow>,
  key: MemberSortKey,
  dir: MemberSortDir
): MemberRow[] {
  const direction = dir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => compareMemberRows(a, b, key) * direction)
}

function compareMemberRows(a: MemberRow, b: MemberRow, key: MemberSortKey): number {
  if (key === 'risk') return a.risk - b.risk
  if (key === 'balance') return a.balance_points - b.balance_points
  if (key === 'notes') return (a.notes_count ?? 0) - (b.notes_count ?? 0)
  if (key === 'feedback') return (a.feedback_count ?? 0) - (b.feedback_count ?? 0)
  if (key === 'expires_at') return compareDateLike(a.expires_at, b.expires_at)
  if (key === 'paid_first') return compareDateLike(a.paid_at_first ?? '', b.paid_at_first ?? '')
  if (key === 'last_active') return compareDateLike(a.last_active, b.last_active)
  if (key === 'phone') return compareText(a.phone_masked, b.phone_masked)
  return compareText(String(a[key] ?? ''), String(b[key] ?? ''))
}

function compareText(a: string, b: string): number {
  return a.localeCompare(b, 'zh-CN', { numeric: true, sensitivity: 'base' })
}

function compareDateLike(a: string, b: string): number {
  return normalizeDateLike(a) - normalizeDateLike(b)
}

function normalizeDateLike(value: string): number {
  if (!value || value === '—') return 0
  const parsed = Date.parse(value)
  if (!Number.isNaN(parsed)) return parsed
  const monthDay = /^(\d{2})\/(\d{2})$/.exec(value)
  if (monthDay) {
    const year = new Date().getFullYear()
    return Date.UTC(year, Number(monthDay[1]) - 1, Number(monthDay[2]))
  }
  if (value.includes('刚刚')) return Date.now()
  const relative = /(\d+)\s*(分钟|小时|天)前/.exec(value)
  if (!relative) return 0
  const amount = Number(relative[1])
  const unit = relative[2]
  const factor = unit === '分钟' ? 60000 : unit === '小时' ? 3600000 : 86400000
  return Date.now() - amount * factor
}
