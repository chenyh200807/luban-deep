'use client'

import { ChevronDown } from 'lucide-react'
import type { ComponentPropsWithoutRef, ReactNode } from 'react'

type BiTone = 'sky' | 'amber' | 'emerald' | 'rose' | 'slate'
type BiButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
type BiButtonSize = 'xs' | 'sm' | 'md'

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ')
}

const NOTICE_TONE: Record<BiTone, string> = {
  sky: 'border-cyan-300/25 bg-cyan-300/10 text-cyan-100',
  amber: 'border-amber-300/25 bg-amber-300/10 text-amber-100',
  emerald: 'border-emerald-300/25 bg-emerald-300/10 text-emerald-100',
  rose: 'border-rose-300/25 bg-rose-300/10 text-rose-100',
  slate: 'border-white/10 bg-white/[0.05] text-slate-200',
}

const BUTTON_VARIANT: Record<BiButtonVariant, string> = {
  primary: 'border-cyan-300/40 bg-cyan-300/15 text-cyan-50 hover:bg-cyan-300/25',
  secondary: 'border-white/10 bg-white/[0.06] text-slate-100 hover:bg-white/10',
  ghost: 'border-transparent bg-transparent text-slate-300 hover:bg-white/[0.06] hover:text-white',
  danger: 'border-rose-300/35 bg-rose-300/10 text-rose-100 hover:bg-rose-300/18',
}

const BUTTON_SIZE: Record<BiButtonSize, string> = {
  xs: 'h-7 rounded-lg px-2 text-[11px]',
  sm: 'h-9 rounded-xl px-3 text-xs',
  md: 'h-11 rounded-2xl px-4 text-sm',
}

export type BiNoticeProps = ComponentPropsWithoutRef<'div'> & {
  tone?: BiTone
  action?: ReactNode
}

export function BiNotice({ tone = 'slate', action, className = '', children, ...props }: BiNoticeProps) {
  return (
    <div
      className={cx(
        'flex flex-col gap-2 rounded-2xl border px-3 py-2 text-xs leading-5 sm:flex-row sm:items-center sm:justify-between',
        NOTICE_TONE[tone],
        className
      )}
      {...props}
    >
      <div className="min-w-0 flex-1">{children}</div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  )
}

export type BiButtonProps = ComponentPropsWithoutRef<'button'> & {
  variant?: BiButtonVariant
  size?: BiButtonSize
}

export function BiButton({
  variant = 'secondary',
  size = 'sm',
  className = '',
  type = 'button',
  ...props
}: BiButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        'inline-flex items-center justify-center gap-1.5 border font-bold transition disabled:cursor-not-allowed disabled:opacity-50',
        BUTTON_VARIANT[variant],
        BUTTON_SIZE[size],
        className
      )}
      {...props}
    />
  )
}

export type BiSelectProps = ComponentPropsWithoutRef<'select'> & {
  wrapperClassName?: string
}

export function BiSelect({ className = '', wrapperClassName = '', children, ...props }: BiSelectProps) {
  return (
    <span className={cx('relative inline-flex min-w-[8rem]', wrapperClassName)}>
      <select
        className={cx(
          'h-9 w-full appearance-none rounded-xl border border-white/10 bg-[#151d2b] px-3 pr-8 text-xs font-bold text-slate-100 outline-none [color-scheme:dark] focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20',
          className
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400"
        aria-hidden
      />
    </span>
  )
}

export function compactBiToken(value: string | number | null | undefined, head = 10, tail = 6) {
  const text = String(value ?? '').trim()
  if (!text) return '--'
  if (text.length <= head + tail + 1) return text
  return `${text.slice(0, head)}…${text.slice(-tail)}`
}

export type BiIdTokenProps = {
  value?: string | number | null
  head?: number
  tail?: number
  className?: string
}

export function BiIdToken({ value, head, tail, className = '' }: BiIdTokenProps) {
  const raw = String(value ?? '').trim()
  const label = compactBiToken(raw, head, tail)
  return (
    <code
      title={raw || undefined}
      className={cx(
        'inline-block max-w-[13rem] truncate align-bottom font-mono text-[11px] text-slate-200',
        className
      )}
    >
      {label}
    </code>
  )
}

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

export function formatBiDateTime(value?: string | null) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return dateTimeFormatter.format(date)
}

export type BiDateTimeProps = {
  value?: string | null
  className?: string
}

export function BiDateTime({ value, className = '' }: BiDateTimeProps) {
  return (
    <time
      dateTime={value || undefined}
      title={value || undefined}
      className={cx('whitespace-nowrap text-[11px] tabular-nums text-slate-300', className)}
    >
      {formatBiDateTime(value)}
    </time>
  )
}
