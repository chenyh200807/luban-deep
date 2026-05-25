import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import WechatHarnessClient from './WechatHarnessClient'

export const metadata: Metadata = {
  title: '微信小程序影子测试 | 鲁班智考',
  description: 'Replay mini-program rendering contracts in a Web test harness.',
}

// Harness is a fixture-replay test surface. It must never default-open in
// production builds; only enable when explicitly flagged via server env.
function isHarnessEnabled(): boolean {
  if (process.env.NODE_ENV !== 'production') return true
  return (
    process.env.DEEPTUTOR_ENABLE_WECHAT_HARNESS === 'true' ||
    process.env.NEXT_PUBLIC_ENABLE_WECHAT_HARNESS === 'true'
  )
}

export default async function WechatHarnessPage() {
  if (!isHarnessEnabled()) {
    notFound()
  }
  const { loadWechatHarnessCases } = await import('@/lib/wechat-harness-data')
  const cases = loadWechatHarnessCases()
  return <WechatHarnessClient cases={cases} />
}
