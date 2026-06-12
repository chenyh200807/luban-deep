import { apiUrl, getStoredBiAdminSession } from '@/lib/api'

export interface BiAdminEntry {
  user_id: string
  source: 'env' | 'runtime'
  removable: boolean
}

function authHeaders(): HeadersInit {
  const token = getStoredBiAdminSession()?.token ?? ''
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function parse(response: Response): Promise<BiAdminEntry[]> {
  const payload = (await response.json()) as { admins?: BiAdminEntry[]; detail?: string }
  if (!response.ok) {
    throw new Error(payload.detail || `请求失败：${response.status}`)
  }
  return payload.admins ?? []
}

export async function listBiAdmins(): Promise<BiAdminEntry[]> {
  return parse(await fetch(apiUrl('/api/v1/bi/admins'), { cache: 'no-store', headers: authHeaders() }))
}

export async function addBiAdmin(userId: string): Promise<BiAdminEntry[]> {
  return parse(
    await fetch(apiUrl('/api/v1/bi/admins'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ user_id: userId }),
    }),
  )
}

export async function removeBiAdmin(userId: string): Promise<BiAdminEntry[]> {
  return parse(
    await fetch(apiUrl(`/api/v1/bi/admins/${encodeURIComponent(userId)}`), {
      method: 'DELETE',
      headers: authHeaders(),
    }),
  )
}
