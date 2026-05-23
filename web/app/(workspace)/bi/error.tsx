/* eslint-disable i18n/no-literal-ui-text */
'use client'

import Link from 'next/link'
import { useEffect } from 'react'

// Round 5 B4: Next.js segment-level error boundary for /bi.
//
// Without this, any client-side throw inside BiV2Surface / panels collapses
// the whole route to a blank Next.js error page (Frontend reviewer HIGH-2).
// The boundary keeps the shell visible, shows the error in plain language,
// and offers two recovery paths:
//   - "重试" — Next.js reset() re-renders the segment
//   - "回到旧 /bi" — instructs the operator to flip the flag off (1-second
//     rollback as advertised in the runbook)
//
// Errors are logged to console so existing monitoring (Sentry / browser
// devtools) keeps working. Audit logs are NOT written here because the
// boundary catches *client* errors, which by definition haven't reached the
// server — there's nothing audited to record.

export default function BiSegmentError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('[BI v2 segment error]', error)
  }, [error])

  return (
    <div className="mx-auto mt-12 max-w-2xl rounded-md border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
      <div className="text-base font-semibold">BI 后台暂时不可用</div>
      <p className="mt-2 text-xs leading-relaxed">
        {`BI v2 客户端渲染出现错误。请先点击下方"重试"。若仍失败，请将`}
        <code className="mx-1 rounded bg-white px-1 py-0.5 font-mono text-[11px]">
          BI_BACKOFFICE_V2_SHELL_ENABLED
        </code>
        关闭以回到旧 /bi（1 秒回滚 — 见 docs/zh/bi/bi-backoffice-v2-rollout-runbook.md §3）。
      </p>
      <details className="mt-3 rounded bg-white p-2 text-[11px]">
        <summary className="cursor-pointer text-rose-900">
          技术细节（请复制反馈给 engineering）
        </summary>
        <pre className="mt-2 overflow-auto whitespace-pre-wrap font-mono text-[10px] text-slate-700">
          {error.message}
          {error.digest ? `\nDigest: ${error.digest}` : ''}
          {error.stack ? `\n${error.stack.split('\n').slice(0, 6).join('\n')}` : ''}
        </pre>
      </details>
      <div className="mt-4 flex items-center gap-2">
        <button
          type="button"
          onClick={() => reset()}
          className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white hover:bg-slate-800"
          aria-label="重试加载 BI 后台"
        >
          重试
        </button>
        <Link
          href="/"
          className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-white"
          aria-label="返回工作区首页"
        >
          返回首页
        </Link>
      </div>
    </div>
  )
}
