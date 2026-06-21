/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { KeyRound, LogIn, RotateCcw, ShieldCheck, UserPlus } from 'lucide-react'
import {
  changeMemberPassword,
  loginMemberAccount,
  registerMemberAccount,
  resetMemberPassword,
  sendMemberAuthCode,
  type MemberAccountSession,
} from '@/lib/member-account-api'
import { SectionHeader } from './BiShared'

type AccountMode = 'login' | 'register' | 'reset' | 'change'

const MEMBER_ACCOUNT_SESSION_STORAGE_KEY = 'deeptutor.bi.member.account.session'

const ACCOUNT_MODES: Array<{ key: AccountMode; label: string }> = [
  { key: 'login', label: '登录' },
  { key: 'register', label: '注册' },
  { key: 'reset', label: '找回密码' },
  { key: 'change', label: '修改密码' },
]

function loadStoredMemberSession(): MemberAccountSession | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(MEMBER_ACCOUNT_SESSION_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<MemberAccountSession>
    if (
      typeof parsed.token !== 'string' ||
      typeof parsed.userId !== 'string' ||
      typeof parsed.displayName !== 'string' ||
      typeof parsed.expiresAt !== 'number'
    ) {
      window.sessionStorage.removeItem(MEMBER_ACCOUNT_SESSION_STORAGE_KEY)
      return null
    }
    if (parsed.expiresAt > 0 && parsed.expiresAt <= Math.floor(Date.now() / 1000)) {
      window.sessionStorage.removeItem(MEMBER_ACCOUNT_SESSION_STORAGE_KEY)
      return null
    }
    return {
      token: parsed.token,
      userId: parsed.userId,
      displayName: parsed.displayName,
      isAdmin: Boolean(parsed.isAdmin),
      expiresAt: parsed.expiresAt,
    }
  } catch {
    return null
  }
}

function storeMemberSession(session: MemberAccountSession | null): void {
  if (typeof window === 'undefined') return
  if (!session) {
    window.sessionStorage.removeItem(MEMBER_ACCOUNT_SESSION_STORAGE_KEY)
    return
  }
  window.sessionStorage.setItem(MEMBER_ACCOUNT_SESSION_STORAGE_KEY, JSON.stringify(session))
}

function Field({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium text-[var(--foreground)]">
      <span>{label}</span>
      {children}
    </label>
  )
}

export function BiMemberAccountPanel() {
  const [mode, setMode] = useState<AccountMode>('login')
  const [session, setSession] = useState<MemberAccountSession | null>(null)
  const [username, setUsername] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [code, setCode] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sendingCode, setSendingCode] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    setSession(loadStoredMemberSession())
  }, [])

  const currentMode = useMemo(
    () => ACCOUNT_MODES.find(item => item.key === mode) ?? ACCOUNT_MODES[0],
    [mode]
  )

  const applySession = (nextSession: MemberAccountSession | null) => {
    setSession(nextSession)
    storeMemberSession(nextSession)
  }

  const submit = async () => {
    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      if (mode === 'login') {
        const nextSession = await loginMemberAccount(username.trim(), password)
        applySession(nextSession)
        setPassword('')
        setMessage(`已登录会员账号：${nextSession.displayName}`)
        return
      }
      if (mode === 'register') {
        const nextSession = await registerMemberAccount({
          username: username.trim(),
          password,
          phone: phone.trim(),
        })
        applySession(nextSession)
        setPassword('')
        setMessage(`已注册并登录会员账号：${nextSession.displayName}`)
        return
      }
      if (mode === 'reset') {
        const result = await resetMemberPassword({
          username: username.trim(),
          phone: phone.trim(),
          code: code.trim(),
          password,
        })
        setPassword('')
        setCode('')
        setMessage(result.message || '密码已重置，请使用新密码登录。')
        return
      }
      if (!session?.token) {
        setError('请先在本面板登录会员账号，再修改该账号密码。')
        return
      }
      const result = await changeMemberPassword(session.token, {
        old_password: oldPassword,
        new_password: newPassword,
      })
      applySession(null)
      setOldPassword('')
      setNewPassword('')
      setMessage(result.message || '密码已修改，请使用新密码重新登录。')
    } catch (err) {
      setError(err instanceof Error ? err.message : `${currentMode.label}失败`)
    } finally {
      setSubmitting(false)
    }
  }

  const requestCode = async () => {
    setSendingCode(true)
    setError('')
    setMessage('')
    try {
      const result = await sendMemberAuthCode({
        username: username.trim(),
        phone: phone.trim(),
      })
      setMessage(result.message || '验证码已发送。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '验证码发送失败')
    } finally {
      setSendingCode(false)
    }
  }

  const inputClass =
    'rounded-2xl border bg-white px-4 py-2.5 text-sm outline-none transition focus:border-[var(--primary)]'

  return (
    <section className="rounded-3xl border border-[var(--border)]/60 bg-[var(--background)] p-5 shadow-[0_12px_30px_rgba(45,33,25,0.05)]">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-2xl">
          <SectionHeader title="会员账号系统" extra="真实登录 / 注册 / 找回密码 / 修改密码" />
          <p className="mt-3 text-sm leading-6 text-[var(--muted-foreground)]">
            这里验证的是会员自助账号生命周期；管理员后台解锁仍使用上方管理员登录，不与会员登录态混用。
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl bg-white/80 p-3">
              <LogIn className="h-4 w-4 text-[var(--primary)]" />
              <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">会员登录</p>
              <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">
                调用 /auth/login，返回会员 token。
              </p>
            </div>
            <div className="rounded-2xl bg-white/80 p-3">
              <UserPlus className="h-4 w-4 text-[var(--primary)]" />
              <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">注册入库</p>
              <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">
                账号、密码、手机号进入会员 authority。
              </p>
            </div>
            <div className="rounded-2xl bg-white/80 p-3">
              <KeyRound className="h-4 w-4 text-[var(--primary)]" />
              <p className="mt-2 text-sm font-semibold text-[var(--foreground)]">密码闭环</p>
              <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">
                找回密码走短信码；修改密码只改当前登录账号。
              </p>
            </div>
          </div>
        </div>

        <div className="w-full rounded-3xl border border-[var(--border)] bg-white p-4 xl:max-w-[560px]">
          <div className="flex flex-wrap gap-2">
            {ACCOUNT_MODES.map(item => (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  setMode(item.key)
                  setError('')
                  setMessage('')
                }}
                className={`rounded-2xl px-3 py-2 text-sm font-medium transition ${
                  mode === item.key
                    ? 'bg-[var(--foreground)] text-white'
                    : 'bg-[var(--secondary)] text-[var(--foreground)] hover:bg-[var(--border)]/40'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div className="mt-4 grid gap-3">
            {mode !== 'change' ? (
              <Field label="账号">
                <input
                  value={username}
                  onChange={event => setUsername(event.target.value)}
                  placeholder="输入会员账号"
                  autoComplete="username"
                  className={inputClass}
                />
              </Field>
            ) : null}

            {mode === 'register' || mode === 'reset' ? (
              <Field label="手机号">
                <input
                  value={phone}
                  onChange={event => setPhone(event.target.value)}
                  placeholder="输入注册手机号"
                  autoComplete="tel"
                  className={inputClass}
                />
              </Field>
            ) : null}

            {mode === 'reset' ? (
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                <Field label="短信验证码">
                  <input
                    value={code}
                    onChange={event => setCode(event.target.value)}
                    placeholder="6 位验证码"
                    inputMode="numeric"
                    className={inputClass}
                  />
                </Field>
                <button
                  type="button"
                  onClick={() => void requestCode()}
                  disabled={sendingCode}
                  className="mt-6 inline-flex items-center justify-center rounded-2xl border border-[var(--border)] bg-white px-4 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-[var(--secondary)] disabled:opacity-60"
                >
                  {sendingCode ? '发送中...' : '发送验证码'}
                </button>
              </div>
            ) : null}

            {mode === 'change' ? (
              <>
                <div className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                  {session ? (
                    <span className="inline-flex items-center gap-2">
                      <ShieldCheck className="h-4 w-4" />
                      当前会员账号：{session.displayName || session.userId}
                    </span>
                  ) : (
                    '尚未登录会员账号；请先在本面板完成会员登录。'
                  )}
                </div>
                <Field label="旧密码">
                  <input
                    value={oldPassword}
                    onChange={event => setOldPassword(event.target.value)}
                    placeholder="输入旧密码"
                    type="password"
                    autoComplete="current-password"
                    className={inputClass}
                  />
                </Field>
                <Field label="新密码">
                  <input
                    value={newPassword}
                    onChange={event => setNewPassword(event.target.value)}
                    placeholder="至少 6 位，含大小写字母和数字"
                    type="password"
                    autoComplete="new-password"
                    className={inputClass}
                  />
                </Field>
              </>
            ) : (
              <Field label={mode === 'reset' ? '新密码' : '密码'}>
                <input
                  value={password}
                  onChange={event => setPassword(event.target.value)}
                  placeholder="至少 6 位，含大小写字母和数字"
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  className={inputClass}
                />
              </Field>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void submit()}
                disabled={submitting || (mode === 'change' && !session)}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-[var(--foreground)] px-4 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-60"
              >
                {mode === 'reset' ? <RotateCcw className="h-4 w-4" /> : null}
                {submitting ? '处理中...' : currentMode.label}
              </button>
              {session ? (
                <button
                  type="button"
                  onClick={() => {
                    applySession(null)
                    setMessage('已退出会员账号测试登录。')
                  }}
                  className="inline-flex items-center justify-center rounded-2xl border border-[var(--border)] bg-white px-4 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:bg-[var(--secondary)]"
                >
                  退出会员账号
                </button>
              ) : null}
            </div>

            {message ? (
              <p role="status" className="rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                {message}
              </p>
            ) : null}
            {error ? (
              <p role="alert" className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {error}
              </p>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  )
}
