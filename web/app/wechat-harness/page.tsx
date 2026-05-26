import type { Metadata } from 'next'
import { notFound } from 'next/navigation'

import { isWechatHarnessEnabled } from '@/lib/wechat-harness-gate'
import WechatHarnessClient from './WechatHarnessClient'

export const metadata: Metadata = {
  title: '微信小程序影子测试 | 鲁班智考',
  description: 'Replay mini-program rendering contracts in a Web test harness.',
}

export default async function WechatHarnessPage() {
  if (
    !isWechatHarnessEnabled({
      nodeEnv: process.env.NODE_ENV,
      enableWechatHarness: process.env.DEEPTUTOR_ENABLE_WECHAT_HARNESS,
    })
  ) {
    notFound()
  }
  const { loadWechatHarnessCases } = await import('@/lib/wechat-harness-data')
  const cases = loadWechatHarnessCases()
  return <WechatHarnessClient cases={cases} />
}
