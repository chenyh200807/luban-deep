/* eslint-disable i18n/no-literal-ui-text */
'use client'

import dynamic from 'next/dynamic'

import RestrictedSurface from '@/components/common/RestrictedSurface'
import { requiresWebAuth } from '@/lib/web-access'

// Lazy-load the heavy authenticated console (lucide icons, i18n, tour
// overlays, EventSource diagnostics) so the public ``/settings`` entry only
// pulls the RestrictedSurface shell. Keeps the route under its 180KB bundle
// budget enforced by ``web/scripts/route_budgets.mjs``.
const SettingsConsole = dynamic(() => import('./SettingsPageContent'), {
  ssr: false,
})

export default function SettingsPage() {
  if (!requiresWebAuth()) {
    return (
      <RestrictedSurface
        title="配置控制台暂不可用"
        message="当前 Web 端未接入登录态，配置控制台已默认关闭。请使用已鉴权入口访问。"
      />
    )
  }
  return <SettingsConsole />
}
