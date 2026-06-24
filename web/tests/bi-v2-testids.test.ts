import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(__dirname, '..')

async function readWeb(path: string): Promise<string> {
  return readFile(resolve(webRoot, path), 'utf8')
}

test('BiTopBar input has stable data-testid="bi-topbar-search"', async () => {
  const source = await readWeb('components/bi-v2/BiTopBar.tsx')
  assert.ok(
    source.includes('data-testid="bi-topbar-search"'),
    'expected BiTopBar.tsx to include data-testid="bi-topbar-search" on its search input',
  )
})

test('BiTopBar actor span has stable data-testid="bi-topbar-actor"', async () => {
  const source = await readWeb('components/bi-v2/BiTopBar.tsx')
  assert.ok(
    source.includes('data-testid="bi-topbar-actor"'),
    'expected BiTopBar.tsx to include data-testid="bi-topbar-actor" on its actor slot',
  )
})

test('BiSideNav nav button has data-testid template `bi-sidenav-item-${key}`', async () => {
  const source = await readWeb('components/bi-v2/BiSideNav.tsx')
  // Match either `data-testid={`bi-sidenav-item-...`} or escaped/quoted variants.
  const matched =
    /data-testid=\{`bi-sidenav-item-\$\{[^}]+\}`\}/.test(source) ||
    /data-testid=\{['"`]bi-sidenav-item-\$\{[^}]+\}['"`]\}/.test(source)
  assert.ok(
    matched,
    'expected BiSideNav.tsx to include data-testid={`bi-sidenav-item-${...}`} on each nav button',
  )
})

test('member ops exposes product behavior UI anchors', async () => {
  const panel = await readWeb('app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx')
  const drawer = await readWeb('app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx')

  assert.ok(panel.includes('data-testid="bi-member-behavior-health-strip"'))
  assert.ok(panel.includes('data-testid="bi-member-behavior-cohort-tabs"'))
  assert.ok(panel.includes('report_high_no_action'))
  assert.ok(panel.includes('onRowClick={row =>'))
  assert.ok(panel.includes('rowAriaLabel={row => `打开 ${row.phone_masked} 学员 360`}'))
  assert.ok(drawer.includes('data-testid="bi-member-behavior-timeline"'))
  assert.ok(drawer.includes('data-testid="bi-member-learning-report-breakdown"'))
  assert.ok(drawer.includes('data-testid="bi-member-360-summary"'))
})

test('member ops exposes member search by phone or account', async () => {
  const panel = await readWeb('app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx')
  const surface = await readWeb('app/(workspace)/bi/_v2/BiV2Surface.tsx')
  const api = await readWeb('lib/member-api.ts')

  assert.ok(panel.includes('data-testid="bi-member-search-form"'))
  assert.ok(panel.includes('data-testid="bi-member-search-input"'))
  assert.ok(panel.includes('placeholder="搜索手机号 / 账号 / user_id"'))
  assert.ok(panel.includes('aria-label="搜索会员手机号或账号"'))
  assert.ok(panel.includes('submitMemberSearchValue(memberSearchDraft)'))
  assert.ok(panel.includes('onSubmitSearch?.(value.trim())'))
  assert.ok(panel.includes("event.key === 'Enter'"))
  assert.ok(panel.includes('submitMemberSearchValue(event.currentTarget.value)'))
  assert.ok(panel.includes('search: globalQuery.trim() || undefined'))
  assert.ok(surface.includes('onSubmitSearch={submitGlobalSearch}'))
  assert.ok(api.includes('/api/v1/bi/member/list?'))
})

test('member ops exposes member account lifecycle panel', async () => {
  const page = await readWeb('app/(workspace)/bi/BiPageClient.tsx')
  const panel = await readWeb('app/(workspace)/bi/_components/BiMemberAccountPanel.tsx')
  const api = await readWeb('lib/member-account-api.ts')

  assert.ok(page.includes('BiMemberAccountPanel'))
  assert.ok(panel.includes('会员账号系统'))
  assert.ok(panel.includes('真实登录 / 注册 / 找回密码 / 修改密码'))
  assert.ok(panel.includes('loginMemberAccount'))
  assert.ok(panel.includes('registerMemberAccount'))
  assert.ok(panel.includes('resetMemberPassword'))
  assert.ok(panel.includes('changeMemberPassword(session.token'))
  assert.ok(api.includes('/api/v1/auth/login'))
  assert.ok(api.includes('/api/v1/auth/register'))
  assert.ok(api.includes('/api/v1/auth/reset-password'))
  assert.ok(api.includes('/api/v1/auth/change-password'))
})

test('member ops exposes member account lifecycle panel', async () => {
  const page = await readWeb('app/(workspace)/bi/BiPageClient.tsx')
  const panel = await readWeb('app/(workspace)/bi/_components/BiMemberAccountPanel.tsx')
  const api = await readWeb('lib/member-account-api.ts')

  assert.ok(page.includes('BiMemberAccountPanel'))
  assert.ok(panel.includes('会员账号系统'))
  assert.ok(panel.includes('真实登录 / 注册 / 找回密码 / 修改密码'))
  assert.ok(panel.includes('loginMemberAccount'))
  assert.ok(panel.includes('registerMemberAccount'))
  assert.ok(panel.includes('resetMemberPassword'))
  assert.ok(panel.includes('changeMemberPassword(session.token'))
  assert.ok(api.includes('/api/v1/auth/login'))
  assert.ok(api.includes('/api/v1/auth/register'))
  assert.ok(api.includes('/api/v1/auth/reset-password'))
  assert.ok(api.includes('/api/v1/auth/change-password'))
})

test('member ops exposes membership settings as the visible row action', async () => {
  const panel = await readWeb('app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx')
  const drawer = await readWeb('app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx')

  assert.ok(panel.includes('manualPurchaseMembership'))
  assert.ok(panel.includes('upgradeMemberToVip'))
  assert.ok(panel.includes('findPackageForTier(membershipPackages, \'vip\')'))
  assert.ok(panel.includes('aria-label={`打开 ${row.user_id} 会员设置`}'))
  assert.ok(panel.includes('选择套餐、实收金额、有效期和取消会员'))
  assert.ok(panel.includes('variant="primary"'))
  assert.ok(!panel.includes('grantMembership'))
  assert.ok(drawer.includes('onUpgradeToVip'))
  assert.ok(drawer.includes('aria-label="将当前会员升级为 VIP"'))
})

test('member ops exposes package-led cashier membership settings', async () => {
  const panel = await readWeb('app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx')
  const api = await readWeb('lib/member-api.ts')

  assert.ok(panel.includes('getBiCommerce'))
  assert.ok(panel.includes('manualPurchaseMembership'))
  assert.ok(panel.includes('reverseManualMembershipPurchase'))
  assert.ok(panel.includes('updateMembership'))
  assert.ok(panel.includes('revokeMembership'))
  assert.ok(panel.includes('data-testid="bi-member-membership-settings"'))
  assert.ok(panel.includes('会员设置'))
  assert.ok(panel.includes('VIP'))
  assert.ok(panel.includes('SVIP'))
  assert.ok(panel.includes('至尊SVIP'))
  assert.ok(panel.includes('套餐是唯一选择；等级、点数、次数和默认收入都从套餐派生。'))
  assert.ok(panel.includes('不改金额时按套餐价入账；填 0 即 0 元开通，填其他数字即按人工实收金额入账。'))
  assert.ok(panel.includes('只冲销下方展示的原始购买流水'))
  assert.ok(panel.includes('reversible_supreme_purchase'))
  assert.ok(panel.includes('有效期'))
  assert.ok(panel.includes('付费开通并入账'))
  assert.ok(panel.includes('收款开通'))
  assert.ok(panel.includes('保存有效期'))
  assert.ok(panel.includes('取消会员'))
  assert.ok(panel.includes('删除账号'))
  assert.ok(panel.includes('deleteMemberAccount'))
  assert.ok(panel.includes('aria-label="删除会员账号"'))
  assert.ok(panel.includes('撤回至尊SVIP'))
  assert.ok(panel.includes('改为0元'))
  assert.ok(panel.includes('convertSupremeMembershipToFree'))
  assert.ok(panel.includes('manual_membership_reversal'))
  assert.ok(api.includes('/api/v1/bi/member/manual-purchase/reverse'))
  assert.ok(api.includes('reverseManualMembershipPurchase'))
  assert.ok(api.includes('/api/v1/bi/member/'))
  assert.ok(api.includes('deleteMemberAccount'))
  assert.equal(panel.includes('aria-label="选择会员等级"'), false)
  assert.equal(panel.includes('运营授予权益'), false)
})

test('commerce cockpit exposes yuan revenue summary from wallet ledger', async () => {
  const cockpit = await readWeb('components/bi-cockpit/CommerceCockpit.tsx')
  const api = await readWeb('lib/bi-api.ts')
  const service = await readWeb('../deeptutor/services/bi_service.py')

  assert.ok(api.includes('revenueCny: number'))
  assert.ok(api.includes('todayRevenueCny: number'))
  assert.ok(api.includes('recentRevenueCny: number'))
  assert.ok(api.includes('latestRevenueAmountCny: number'))
  assert.ok(api.includes('latestRevenueMemberId: string'))
  assert.ok(api.includes('reversalCount: number'))
  assert.ok(cockpit.includes('最近收入'))
  assert.ok(cockpit.includes('今日收入'))
  assert.ok(cockpit.includes('最新一笔'))
  assert.ok(cockpit.includes('¥'))
  assert.ok(service.includes('"revenue_cny"'))
  assert.ok(service.includes('"latest_revenue_amount_cny"'))
  assert.ok(service.includes('"reversal_count"'))
})

test('membership purchase broadcasts commerce reload event', async () => {
  const memberOps = await readWeb('app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx')
  const commerce = await readWeb('app/(workspace)/bi/_v2/commerce/BiV2CommercePanel.tsx')

  assert.ok(memberOps.includes("window.dispatchEvent(new CustomEvent('bi:commerce-mutated'"))
  assert.ok(commerce.includes("window.addEventListener('bi:commerce-mutated'"))
  assert.ok(commerce.includes("window.removeEventListener('bi:commerce-mutated'"))
})

test('member ops row actions stay readable in the sticky action column', async () => {
  const panel = await readWeb('app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx')
  const table = await readWeb('components/bi-v2/BiDataTable.tsx')

  assert.ok(table.includes('min-w-[9.25rem]'))
  assert.ok(panel.includes('flex flex-nowrap justify-end gap-1.5'))
  assert.ok(panel.includes('min-w-[4.75rem] whitespace-nowrap'))
  assert.ok(panel.includes('min-w-[3.5rem] whitespace-nowrap'))
})

test('BiDataTable supports row-level click without stealing checkbox/action clicks', async () => {
  const table = await readWeb('components/bi-v2/BiDataTable.tsx')

  assert.ok(table.includes('onRowClick?: (row: T) => void'))
  assert.ok(table.includes('rowAriaLabel?: (row: T) => string'))
  assert.ok(table.includes('onKeyDown='))
  assert.ok(table.includes('event.stopPropagation()'))
})
