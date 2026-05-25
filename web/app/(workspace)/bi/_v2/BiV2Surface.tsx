/* eslint-disable i18n/no-literal-ui-text */
'use client'

import { LayoutDashboard, Users, ShoppingBag, MessageSquareWarning, Wrench } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { BiAppShell, BiSideNav, BiTopBar, type BiSideNavItem } from '@/components/bi-v2'
import type { BiFlagSnapshot } from '@/lib/bi-feature-flags'
import { BiV2OverviewPanel } from './BiV2OverviewPanel'
import { BiV2MemberOpsPanel } from './member-ops/BiV2MemberOpsPanel'
import { BiV2CommercePanel } from './commerce/BiV2CommercePanel'
import { BiV2FeedbackPanel } from './feedback/BiV2FeedbackPanel'
import { BiV2OpsPanel } from './ops/BiV2OpsPanel'
import { RequireBiAdmin } from './RequireBiAdmin'
import { describeGlobalSearchActor, routeForGlobalSearch } from './global-search-route'
import type { BiAdminIdentity } from './useBiAdminIdentity'

export type BiV2Section = 'overview' | 'member-ops' | 'commerce' | 'feedback' | 'ops'

const SECTIONS: BiSideNavItem<BiV2Section>[] = [
  {
    key: 'overview',
    label: '经营总览',
    summary: '北极星、付费、留存、成本、风险与今日行动队列。',
    icon: LayoutDashboard,
  },
  {
    key: 'member-ops',
    label: '会员运营',
    summary: '高密会员表、学员 360、对话回顾、全局搜索、运营动作。',
    icon: Users,
  },
  {
    key: 'commerce',
    label: '商品账务',
    summary: '套餐权益、入账流水、钱包流水、账务异常队列。',
    icon: ShoppingBag,
  },
  {
    key: 'feedback',
    label: '反馈中心',
    summary: 'AI 消息反馈与内测申请池，标记已看 / 忽略 / 归档。',
    icon: MessageSquareWarning,
  },
  {
    key: 'ops',
    label: '系统运维',
    summary: '成本质量、数据可信、操作审计、权限审计、上线面板。',
    icon: Wrench,
  },
]

function isSectionEnabled(section: BiV2Section, flags: BiFlagSnapshot) {
  if (section === 'overview') return flags.BI_OVERVIEW_V2_ENABLED
  if (section === 'member-ops') return flags.BI_CRM_V2_ENABLED
  if (section === 'commerce') return flags.BI_COMMERCE_V2_ENABLED
  if (section === 'feedback') return flags.BI_FEEDBACK_V2_ENABLED
  return flags.BI_SYSTEM_OPS_V2_ENABLED
}

function readSectionFromUrl(): BiV2Section {
  if (typeof window === 'undefined') return 'overview'
  const search = new URLSearchParams(window.location.search)
  const tab = search.get('tab') ?? search.get('section') ?? ''
  if (tab) {
    if (tab === 'invite-test') return 'feedback'
    const match = SECTIONS.find(s => s.key === tab)
    if (match) return match.key
  }
  const raw = window.location.hash.replace(/^#/, '')
  return SECTIONS.find(s => s.key === raw)?.key ?? 'overview'
}

function firstEnabledSection(flags: BiFlagSnapshot): BiV2Section {
  return SECTIONS.find(item => isSectionEnabled(item.key, flags))?.key ?? 'overview'
}

function resolveEnabledSection(section: BiV2Section, flags: BiFlagSnapshot): BiV2Section {
  return isSectionEnabled(section, flags) ? section : firstEnabledSection(flags)
}

export type BiV2SurfaceProps = {
  flags: BiFlagSnapshot
}

// Outer shell: gates the entire BI v2 work area behind RequireBiAdmin so all
// downstream panels can safely assume identity is authenticated + admin.
// Cross-cutting "未登录显示什么" logic lives in exactly one place (Round 2
// reviewer 找出的 6 处重复终止于此)。
export default function BiV2Surface({ flags }: BiV2SurfaceProps) {
  return (
    <RequireBiAdmin>
      {identity => <BiV2AuthenticatedSurface flags={flags} identity={identity} />}
    </RequireBiAdmin>
  )
}

// Inner shell: identity 已收窄为 authenticated admin，panel 可放心使用。
function BiV2AuthenticatedSurface({
  flags,
  identity,
}: {
  flags: BiFlagSnapshot
  identity: BiAdminIdentity & { authenticated: true; isAdmin: true }
}) {
  const [section, setSection] = useState<BiV2Section>('overview')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const navItems = useMemo(
    () =>
      SECTIONS.map(item => {
        const enabled = isSectionEnabled(item.key, flags)
        return {
          ...item,
          disabled: !enabled,
          statusLabel: enabled ? '可用' : '待接入',
        }
      }),
    [flags]
  )

  useEffect(() => {
    const sync = () => {
      setSection(prev => {
        const next = resolveEnabledSection(readSectionFromUrl(), flags)
        return prev === next ? prev : next
      })
    }
    sync()
    window.addEventListener('hashchange', sync)
    window.addEventListener('popstate', sync)
    return () => {
      window.removeEventListener('hashchange', sync)
      window.removeEventListener('popstate', sync)
    }
  }, [flags])

  const go = useCallback(
    (target: BiV2Section) => {
      if (!isSectionEnabled(target, flags)) return
      setSection(target)
      if (typeof window !== 'undefined') {
        const url = new URL(window.location.href)
        url.searchParams.set('tab', target)
        url.hash = ''
        window.history.replaceState(null, '', url)
      }
    },
    [flags]
  )

  const searchFlagSnapshot = useMemo(
    () => ({
      commerceEnabled: isSectionEnabled('commerce', flags),
      memberOpsEnabled: isSectionEnabled('member-ops', flags),
    }),
    [flags]
  )

  const submitGlobalSearch = useCallback(
    (value: string) => {
      const query = value.trim()
      setSubmittedQuery(query)
      if (!query) return
      const decision = routeForGlobalSearch(query, searchFlagSnapshot)
      if (decision.section) {
        go(decision.section)
      }
    },
    [searchFlagSnapshot, go]
  )

  const currentSearchDecision = useMemo(
    () => routeForGlobalSearch(submittedQuery, searchFlagSnapshot),
    [submittedQuery, searchFlagSnapshot]
  )
  const currentSearchActor = describeGlobalSearchActor(submittedQuery, currentSearchDecision)

  const current = SECTIONS.find(s => s.key === section) ?? SECTIONS[0]

  let panel: React.ReactNode = null
  if (section === 'overview') {
    panel = <BiV2OverviewPanel flagEnabled={flags.BI_OVERVIEW_V2_ENABLED} />
  } else if (section === 'member-ops') {
    panel = (
      <BiV2MemberOpsPanel
        flagEnabled={flags.BI_CRM_V2_ENABLED}
        globalQuery={submittedQuery}
        identity={identity}
      />
    )
  } else if (section === 'commerce') {
    panel = (
      <BiV2CommercePanel flagEnabled={flags.BI_COMMERCE_V2_ENABLED} globalQuery={submittedQuery} />
    )
  } else if (section === 'feedback') {
    panel = <BiV2FeedbackPanel flagEnabled={flags.BI_FEEDBACK_V2_ENABLED} />
  } else if (section === 'ops') {
    panel = <BiV2OpsPanel flagEnabled={flags.BI_SYSTEM_OPS_V2_ENABLED} />
  }

  return (
    <div data-bi-v2-root data-section={section}>
      <BiAppShell
        topbar={api => (
          <BiTopBar
            leftSlot={api.hamburger}
            brand={
              <>
                <span className="rounded-lg bg-white px-1.5 py-0.5 text-[10px] font-black text-slate-950">
                  BI v2
                </span>
                <span className="hidden text-slate-100 sm:inline">会员经营后台</span>
              </>
            }
            actor={currentSearchActor ?? `actor: ${identity.displayName} · admin`}
            onSubmitSearch={submitGlobalSearch}
          />
        )}
        sidenav={api => (
          <BiSideNav
            items={navItems}
            current={section}
            onSelect={key => {
              go(key)
              if (isSectionEnabled(key, flags)) api.closeNav()
            }}
            footer={
              <div className="rounded-2xl border border-amber-300/20 bg-amber-300/10 px-3 py-3 text-[11px] leading-snug text-amber-100">
                <span className="font-semibold">BI v2 Shell</span>
                <span className="mt-0.5 block">
                  仅可用模块允许进入，待接入模块不会展示半成品数据。
                </span>
              </div>
            }
          />
        )}
        pageTitle={current.label}
        pageSummary={current.summary}
        footer="一级导航固定 5 主区 · 当前仅展示已接入的真实读模型，技术口径在模块详情中查看。"
      >
        {panel}
      </BiAppShell>
    </div>
  )
}
