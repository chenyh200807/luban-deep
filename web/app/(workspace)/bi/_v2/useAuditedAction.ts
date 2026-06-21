'use client'

import { useCallback, useState } from 'react'
import { apiUrl, withAdminAuthorization } from '@/lib/api'
import { ApiError } from '@/lib/api-errors'
import { resolveWritePath, type BiV2WriteEndpointKey } from '@/lib/bi-v2-write-endpoints.generated'

// Single audited-action write gate. Plan §3.5 硬约束：
//   1. idempotency_key on every admin write
//   2. etag/version (optional, surfaced when backend returns one)
//   3. undo_window for dangerous actions (returned by backend as undo_token)
//
// BI v2 panels must not build raw write fetches inline. Panel-owned write
// paths go through useAuditedAction; member-console writes go through the
// tested member-api.ts helper authority, which binds BI RBAC + idempotency at
// the backend route. UI must NEVER fabricate a local audit log to imply a
// write happened. This hook guarantees:
//   - actor = identity.actorId (caller can't override; comes from session)
//   - X-Idempotency-Key = generated UUID per execute() call
//   - If-Match = etag prop when supplied
//   - Response captures audit_id / undo_token / etag for callers
//
// Round 3 reviewer 找出的 root cause："BiV2MemberOpsPanel.recordAudit() 写本地
// setAuditLog 但 UI 自称已写入 audit log" — 这是 thin wrapper 的反面。useAuditedAction
// 是把 audit / idempotency / undo 拉到服务层的 fat skill，UI 退回 thin wrapper。

// Round 4 S2: callers cannot pass a free-form URL — they must reference a
// `BiV2WriteEndpointKey` registered in
// `deeptutor/contracts/bi_v2_write_endpoints.py`. The codegen step propagates
// that registry into `web/lib/bi-v2-write-endpoints.generated.ts`, so an
// unregistered key fails to compile. This converts useAuditedAction from an
// advisory helper into a typed, single-entry write gate.
export type AuditedActionEndpoint = {
  // Registered endpoint key (e.g. "member.conversation.view_full"). Method +
  // path template are resolved from the generated registry — callers cannot
  // override them, preventing URL drift between frontend and backend.
  key: BiV2WriteEndpointKey
  // Path template params (e.g. { user_id: "u_1", session_id: "s_1" }).
  params: Record<string, string | number>
  // Optional query string appended after path resolution.
  query?: Record<string, string | number | undefined>
  // Caller-defined body. actor / idempotency_key are injected as headers,
  // NOT in body (so callers can't accidentally override them).
  body?: unknown
  // Optional etag for optimistic concurrency control (sent as If-Match).
  etag?: string
}

export type AuditedActionResult = {
  ok: boolean
  status: number
  // Server-issued audit record id when available.
  auditId?: string
  // Server-issued undo token for dangerous actions (5 min window per §3.5).
  undoToken?: string
  // New etag returned by server after write.
  etag?: string
  // Idempotency key used (for retry safety + audit cross-reference).
  idempotencyKey: string
  // Raw response payload (may be {} for 204).
  data: unknown
  // Error message when !ok.
  error?: string
}

export type AuditedActionState =
  | { phase: 'idle' }
  | { phase: 'writing'; idempotencyKey: string }
  | { phase: 'ok'; result: AuditedActionResult }
  | { phase: 'denied'; result: AuditedActionResult }

export type UseAuditedActionInput = {
  // Human-readable identifier (e.g. "member.note.add"). Used in error messages
  // and contract tests. NOT used as part of audit payload — the URL+method is
  // canonical; this string is for client-side logging only.
  actionType: string
}

function makeIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // Fallback: not cryptographically strong but unique enough for client retries.
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function buildQueryString(query: Record<string, string | number | undefined> | undefined): string {
  if (!query) return ''
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue
    params.append(k, String(v))
  }
  const s = params.toString()
  return s ? `?${s}` : ''
}

export function useAuditedAction({ actionType }: UseAuditedActionInput) {
  const [state, setState] = useState<AuditedActionState>({ phase: 'idle' })

  const execute = useCallback(
    async (endpoint: AuditedActionEndpoint): Promise<AuditedActionResult> => {
      const idempotencyKey = makeIdempotencyKey()
      setState({ phase: 'writing', idempotencyKey })

      const baseHeaders: Record<string, string> = {
        'X-Idempotency-Key': idempotencyKey,
      }
      if (endpoint.body !== undefined) baseHeaders['Content-Type'] = 'application/json'
      if (endpoint.etag) baseHeaders['If-Match'] = endpoint.etag

      const headers = withAdminAuthorization(baseHeaders) ?? baseHeaders

      // Resolve path template + method from the generated registry — single
      // source of truth shared with backend WRITE_ENDPOINTS.
      const resolved = resolveWritePath(endpoint.key, endpoint.params)
      const url = apiUrl(resolved.path) + buildQueryString(endpoint.query)
      let response: Response
      try {
        response = await fetch(url, {
          method: resolved.method,
          headers,
          body: endpoint.body === undefined ? undefined : JSON.stringify(endpoint.body),
        })
      } catch (err) {
        const result: AuditedActionResult = {
          ok: false,
          status: 0,
          idempotencyKey,
          data: null,
          error: `${actionType}: 网络异常 ${(err as Error).message ?? ''}`,
        }
        setState({ phase: 'denied', result })
        return result
      }

      let data: unknown = null
      const text = await response.text()
      if (text) {
        try {
          data = JSON.parse(text)
        } catch {
          data = text
        }
      }

      const auditId =
        data && typeof data === 'object' && 'audit_id' in data
          ? String((data as Record<string, unknown>).audit_id ?? '')
          : undefined
      const undoToken =
        data && typeof data === 'object' && 'undo_token' in data
          ? String((data as Record<string, unknown>).undo_token ?? '')
          : undefined
      const responseEtag = response.headers.get('ETag') ?? undefined

      if (!response.ok) {
        let errMsg = `${actionType}: ${response.status}`
        if (typeof data === 'object' && data && 'detail' in data) {
          errMsg = `${actionType}: ${(data as Record<string, unknown>).detail}`
        } else if (typeof data === 'string') {
          errMsg = `${actionType}: ${data}`
        }
        const result: AuditedActionResult = {
          ok: false,
          status: response.status,
          auditId,
          undoToken,
          etag: responseEtag,
          idempotencyKey,
          data,
          error: errMsg,
        }
        setState({ phase: 'denied', result })
        return result
      }

      const result: AuditedActionResult = {
        ok: true,
        status: response.status,
        auditId,
        undoToken,
        etag: responseEtag,
        idempotencyKey,
        data,
      }
      setState({ phase: 'ok', result })
      return result
    },
    [actionType]
  )

  const reset = useCallback(() => setState({ phase: 'idle' }), [])

  return { state, execute, reset }
}

// Re-export ApiError so callers can narrow errors without re-importing from
// a separate module (less is more — keep hook self-contained).
export { ApiError }
