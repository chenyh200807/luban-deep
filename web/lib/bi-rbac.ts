import { apiUrl, getStoredBiAdminSession } from '@/lib/api'

/**
 * BI RBAC API 层 — 对接后端 /api/v1/bi/ RBAC 端点（SHA 236af02）。
 *
 * 单一 token 来源：getStoredBiAdminSession()?.token。
 * 写操作（POST/PATCH/DELETE）+ audit/search 需要 super_admin 角色，否则后端 403。
 * 列表/矩阵/me 为只读，普通 admin 也能读。
 *
 * 不可变约束：所有解析返回新对象/数组，调用方不得就地修改后端 payload。
 */

export type BiRoleKey = 'super_admin' | 'admin' | 'operator' | 'analyst'
export type BiAdminSource = 'env' | 'runtime'

export interface BiRbacLabeled {
  key: string
  label: string
}

/** 角色权限矩阵：tab -> 该角色在此 tab 上允许的 action 列表 */
export type BiRoleMatrix = Record<string, string[]>

export interface BiRoleDefinition {
  key: BiRoleKey
  label: string
  description: string
  can_manage_permissions: boolean
  is_full_admin: boolean
  matrix: BiRoleMatrix
}

export interface BiRbacRoles {
  tabs: BiRbacLabeled[]
  actions: BiRbacLabeled[]
  roles: BiRoleDefinition[]
}

export interface BiRbacMe {
  user_id: string
  role: BiRoleKey
  role_label: string
  can_manage_permissions: boolean
  is_full_admin: boolean
  accessible_tabs: string[]
  matrix: BiRoleMatrix
}

export interface BiAdminRecord {
  user_id: string
  role: BiRoleKey
  role_label: string
  display_name: string
  granted_by?: string
  granted_at?: string
  source: BiAdminSource
  removable: boolean
  editable: boolean
  accessible_tabs: string[]
}

export type BiAdminAuditAction = 'add_admin' | 'set_role' | 'remove_admin'

export interface BiAdminAuditEntry {
  ts: string
  actor: string
  action: BiAdminAuditAction | string
  target: string
  from_role?: string | null
  to_role?: string | null
  detail?: string | null
}

export interface BiMemberSearchResult {
  user_id: string
  display_name: string
  phone_masked: string
  current_role?: BiRoleKey | null
}

function authHeaders(): HeadersInit {
  const token = getStoredBiAdminSession()?.token ?? ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => ({}))) as T & { detail?: string }
  if (!response.ok) {
    const detail = (payload as { detail?: string }).detail
    throw new Error(detail || `请求失败：${response.status}`)
  }
  return payload
}

/** GET /rbac/roles — 全量角色 / tab / action 定义与权限矩阵（只读）。 */
export async function listRoles(): Promise<BiRbacRoles> {
  const data = await readJson<Partial<BiRbacRoles>>(
    await fetch(apiUrl('/api/v1/bi/rbac/roles'), { cache: 'no-store', headers: authHeaders() })
  )
  return {
    tabs: data.tabs ?? [],
    actions: data.actions ?? [],
    roles: data.roles ?? [],
  }
}

/** GET /rbac/me — 当前登录者的角色与可访问范围（只读）。 */
export async function getMyRbac(): Promise<BiRbacMe> {
  return readJson<BiRbacMe>(
    await fetch(apiUrl('/api/v1/bi/rbac/me'), { cache: 'no-store', headers: authHeaders() })
  )
}

async function parseAdmins(response: Response): Promise<BiAdminRecord[]> {
  const data = await readJson<{ admins?: BiAdminRecord[] }>(response)
  return data.admins ?? []
}

/** GET /admins — 管理员清单（只读）。 */
export async function listAdmins(): Promise<BiAdminRecord[]> {
  return parseAdmins(
    await fetch(apiUrl('/api/v1/bi/admins'), { cache: 'no-store', headers: authHeaders() })
  )
}

/** GET /admins/audit — 权限变更审计，最新在前（super_admin）。 */
export async function listAdminAudit(limit = 200): Promise<BiAdminAuditEntry[]> {
  const data = await readJson<{ audit?: BiAdminAuditEntry[] }>(
    await fetch(apiUrl(`/api/v1/bi/admins/audit?limit=${encodeURIComponent(String(limit))}`), {
      cache: 'no-store',
      headers: authHeaders(),
    })
  )
  return data.audit ?? []
}

/** GET /admins/search-members — 按手机号 / 姓名 / user_id 搜会员选人（super_admin）。 */
export async function searchMembers(q: string, limit = 10): Promise<BiMemberSearchResult[]> {
  const query = q.trim()
  if (!query) return []
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const data = await readJson<{ members?: BiMemberSearchResult[] }>(
    await fetch(apiUrl(`/api/v1/bi/admins/search-members?${params.toString()}`), {
      cache: 'no-store',
      headers: authHeaders(),
    })
  )
  return data.members ?? []
}

/** POST /admins — 添加管理员并定角色。返回最新清单。 */
export async function addAdmin(input: {
  user_id: string
  role: BiRoleKey
  display_name?: string
}): Promise<BiAdminRecord[]> {
  return parseAdmins(
    await fetch(apiUrl('/api/v1/bi/admins'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(input),
    })
  )
}

/** PATCH /admins/{user_id} — 改角色。返回最新清单。 */
export async function setRole(userId: string, role: BiRoleKey): Promise<BiAdminRecord[]> {
  return parseAdmins(
    await fetch(apiUrl(`/api/v1/bi/admins/${encodeURIComponent(userId)}`), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ role }),
    })
  )
}

/** DELETE /admins/{user_id} — 移除管理员。返回最新清单。 */
export async function removeAdmin(userId: string): Promise<BiAdminRecord[]> {
  return parseAdmins(
    await fetch(apiUrl(`/api/v1/bi/admins/${encodeURIComponent(userId)}`), {
      method: 'DELETE',
      headers: authHeaders(),
    })
  )
}
