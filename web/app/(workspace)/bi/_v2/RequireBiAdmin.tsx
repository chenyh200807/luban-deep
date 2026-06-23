/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { Lock, ShieldAlert } from 'lucide-react'
import { type FormEvent, type ReactNode, useState } from 'react'
import { loginBiAdmin } from '@/lib/bi-admin-auth'
import { isAdminLoginSubmitDisabled } from './admin-login-disabled'
import { useBiAdminIdentity, type BiAdminIdentity } from './useBiAdminIdentity'

export type RequireBiAdminProps = {
  // children 必接收已认证且拥有 BI 角色的 identity；未认证或无 BI 角色时 children 不会渲染。
  children: (identity: BiAdminIdentity & { authenticated: true; hasBiAccess: true }) => ReactNode
  // 兜底 fallback：未登录或权限不足时显示的内容。默认 LoginPrompt / NoBiAccessPrompt。
  unauthenticated?: ReactNode
  notAdmin?: ReactNode
}

// Single cross-cutting boundary for BI role access. BI membership is governed by
// /api/v1/bi/rbac/me, not by the legacy full-admin boolean. Children can assume
// identity.actorId is real and identity.accessibleTabs carries the tab matrix.
export function RequireBiAdmin({ children, unauthenticated, notAdmin }: RequireBiAdminProps) {
  const identity = useBiAdminIdentity()

  if (!identity.authenticated) {
    return <>{unauthenticated ?? <UnauthenticatedView />}</>
  }
  if (!identity.hasBiAccess) {
    return <>{notAdmin ?? <NotAdminView identity={identity} />}</>
  }

  // TypeScript 收窄到 authenticated:true & hasBiAccess:true 的 identity。
  return <>{children(identity as BiAdminIdentity & { authenticated: true; hasBiAccess: true })}</>
}

function UnauthenticatedView() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedUsername = username.trim()
    const trimmedPassword = password.trim()
    if (!trimmedUsername || !trimmedPassword) {
      setError('请输入管理员用户名和密码。')
      return
    }
    try {
      setSubmitting(true)
      setError('')
      await loginBiAdmin(trimmedUsername, trimmedPassword)
      setPassword('')
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : '管理员登录失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="mx-auto flex max-w-2xl flex-col items-start gap-4 rounded-md border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800"
      role="alert"
    >
      <div className="flex items-center gap-2 font-semibold">
        <Lock className="h-4 w-4" aria-hidden /> BI 后台需授权登录
      </div>
      <p className="text-xs leading-relaxed">
        BI 会员经营后台按角色授权开放。请使用已授予 BI 角色的账号登录，所有写动作都会绑定真实
        actor_id 写入服务端。
      </p>
      <form
        className="grid w-full gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
        onSubmit={handleSubmit}
      >
        <input
          value={username}
          onChange={event => setUsername(event.target.value)}
          aria-label="管理员用户名"
          placeholder="管理员用户名"
          autoComplete="username"
          className="rounded border border-rose-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-rose-400"
        />
        <input
          value={password}
          onChange={event => setPassword(event.target.value)}
          aria-label="管理员密码"
          placeholder="管理员密码"
          type="password"
          autoComplete="current-password"
          className="rounded border border-rose-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-rose-400"
        />
        <button
          type="submit"
          disabled={isAdminLoginSubmitDisabled({ submitting, username, password })}
          className="inline-flex items-center justify-center rounded bg-rose-700 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? '登录中...' : '登录后台'}
        </button>
      </form>
      {error ? <p className="text-xs font-medium text-rose-700">{error}</p> : null}
    </div>
  )
}

function NotAdminView({ identity }: { identity: BiAdminIdentity }) {
  return (
    <div
      className="mx-auto flex max-w-2xl flex-col items-start gap-3 rounded-md border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800"
      role="alert"
    >
      <div className="flex items-center gap-2 font-semibold">
        <ShieldAlert className="h-4 w-4" aria-hidden /> 当前账号权限不足
      </div>
      <p className="text-xs">
        当前账号 <code className="font-mono">{identity.actorId}</code> 已认证但没有 BI 角色。请联系权限管理员授予
        运营、分析师或管理员角色。
      </p>
    </div>
  )
}
