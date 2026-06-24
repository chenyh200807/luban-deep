import { apiUrl } from '@/lib/api'
import { ApiError } from '@/lib/api-errors'

export type MemberAccountSession = {
  token: string
  userId: string
  displayName: string
  isAdmin: boolean
  expiresAt: number
}

type AuthResponse = {
  user_id: string
  token: string
  expires_at: number
  is_admin?: boolean
  user?: {
    display_name?: string
    username?: string
    user_id?: string
    is_admin?: boolean
  }
}

export type MemberAccountActionResult = {
  success?: boolean
  message?: string
  sessions_invalidated?: number
}

async function expectJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = ''
    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown }
      detail = String(payload.detail ?? payload.message ?? '').trim()
    } catch {
      detail = ''
    }
    throw new ApiError(response.status, detail || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

function toMemberAccountSession(payload: AuthResponse): MemberAccountSession {
  return {
    token: payload.token,
    userId: payload.user?.user_id?.trim() || payload.user_id,
    displayName:
      payload.user?.display_name?.trim() ||
      payload.user?.username?.trim() ||
      payload.user?.user_id?.trim() ||
      payload.user_id,
    isAdmin: Boolean(payload.is_admin || payload.user?.is_admin),
    expiresAt: Number(payload.expires_at || 0),
  }
}

export async function loginMemberAccount(
  username: string,
  password: string
): Promise<MemberAccountSession> {
  const response = await fetch(apiUrl('/api/v1/auth/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  return toMemberAccountSession(await expectJson<AuthResponse>(response))
}

export async function registerMemberAccount(payload: {
  username: string
  password: string
  phone: string
}): Promise<MemberAccountSession> {
  const response = await fetch(apiUrl('/api/v1/auth/register'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return toMemberAccountSession(await expectJson<AuthResponse>(response))
}

export async function sendMemberAuthCode(payload: {
  username?: string
  phone: string
}): Promise<MemberAccountActionResult> {
  const response = await fetch(apiUrl('/api/v1/auth/send-code'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: payload.username ?? '', phone: payload.phone }),
  })
  return expectJson<MemberAccountActionResult>(response)
}

export async function resetMemberPassword(payload: {
  username: string
  phone: string
  code: string
  password: string
}): Promise<MemberAccountActionResult> {
  const response = await fetch(apiUrl('/api/v1/auth/reset-password'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return expectJson<MemberAccountActionResult>(response)
}

export async function changeMemberPassword(
  token: string,
  payload: {
    old_password: string
    new_password: string
  }
): Promise<MemberAccountActionResult> {
  const response = await fetch(apiUrl('/api/v1/auth/change-password'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return expectJson<MemberAccountActionResult>(response)
}

export async function deleteMemberAccount(
  token: string,
  payload: { password: string }
): Promise<MemberAccountActionResult> {
  const response = await fetch(apiUrl('/api/v1/auth/delete-account'), {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return expectJson<MemberAccountActionResult>(response)
}
