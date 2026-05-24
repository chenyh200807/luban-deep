import test from 'node:test'
import assert from 'node:assert/strict'

import {
  describeGlobalSearchActor,
  looksLikeCommerceQuery,
  routeForGlobalSearch,
} from '../app/(workspace)/bi/_v2/global-search-route.ts'

const BOTH_ON = { commerceEnabled: true, memberOpsEnabled: true }
const ONLY_MEMBER = { commerceEnabled: false, memberOpsEnabled: true }
const ONLY_COMMERCE = { commerceEnabled: true, memberOpsEnabled: false }
const NONE = { commerceEnabled: false, memberOpsEnabled: false }

test('empty query yields no target', () => {
  const decision = routeForGlobalSearch('', BOTH_ON)
  assert.equal(decision.section, null)
  assert.equal(decision.reason, 'empty')
  assert.equal(decision.targetLabel, null)
})

test('whitespace-only query yields no target', () => {
  const decision = routeForGlobalSearch('   \t \n', BOTH_ON)
  assert.equal(decision.section, null)
  assert.equal(decision.reason, 'empty')
})

test('phone number routes to member-ops with both flags on', () => {
  const decision = routeForGlobalSearch('13800138000', BOTH_ON)
  assert.equal(decision.section, 'member-ops')
  assert.equal(decision.reason, 'member-identity')
  assert.equal(decision.targetLabel, '会员运营')
})

test('uuid-shaped user_id routes to member-ops', () => {
  const decision = routeForGlobalSearch('2d9eac15-5d26-4e93-941b-9ec6345ce6d9', BOTH_ON)
  assert.equal(decision.section, 'member-ops')
  assert.equal(decision.targetLabel, '会员运营')
})

test('order_xxx keyword routes to commerce', () => {
  const decision = routeForGlobalSearch('order_12345', BOTH_ON)
  assert.equal(decision.section, 'commerce')
  assert.equal(decision.reason, 'commerce-keyword')
  assert.equal(decision.targetLabel, '商品账务')
})

test('ledger keyword routes to commerce', () => {
  const decision = routeForGlobalSearch('ledger:user-7', BOTH_ON)
  assert.equal(decision.section, 'commerce')
})

test('recharge keyword routes to commerce', () => {
  const decision = routeForGlobalSearch('recharge.req-xx', BOTH_ON)
  assert.equal(decision.section, 'commerce')
})

test('commerce keyword falls through to member-ops if commerce flag off', () => {
  const decision = routeForGlobalSearch('order_42', ONLY_MEMBER)
  assert.equal(decision.section, 'member-ops')
  assert.equal(decision.reason, 'member-identity')
})

test('non-commerce query routes to commerce only when member-ops flag off and commerce flag on', () => {
  // Pure identity-like query (not commerce keyword) falls through to
  // member-ops by spec. With member-ops off + commerce on, there is no
  // commerce-eligible target, so result is no-enabled-target.
  const decision = routeForGlobalSearch('alice', ONLY_COMMERCE)
  assert.equal(decision.section, null)
  assert.equal(decision.reason, 'no-enabled-target')
})

test('both flags off yields no-enabled-target', () => {
  const decision = routeForGlobalSearch('whatever', NONE)
  assert.equal(decision.section, null)
  assert.equal(decision.reason, 'no-enabled-target')
})

test('looksLikeCommerceQuery handles case and surrounding whitespace', () => {
  assert.equal(looksLikeCommerceQuery('  Order_001  '), true)
  assert.equal(looksLikeCommerceQuery('TXN-xx'), true)
  assert.equal(looksLikeCommerceQuery('alice'), false)
  assert.equal(looksLikeCommerceQuery(''), false)
})

test('describeGlobalSearchActor builds "已搜 X：跳转到 Y" for routed queries', () => {
  const decision = routeForGlobalSearch('13800138000', BOTH_ON)
  assert.equal(
    describeGlobalSearchActor('13800138000', decision),
    '已搜 13800138000：跳转到 会员运营',
  )
})

test('describeGlobalSearchActor builds commerce label after order keyword', () => {
  const decision = routeForGlobalSearch('order_42', BOTH_ON)
  assert.equal(
    describeGlobalSearchActor('order_42', decision),
    '已搜 order_42：跳转到 商品账务',
  )
})

test('describeGlobalSearchActor falls back when no target', () => {
  const decision = routeForGlobalSearch('whatever', NONE)
  assert.equal(
    describeGlobalSearchActor('whatever', decision),
    '已搜 whatever：无可用目标 panel',
  )
})

test('describeGlobalSearchActor returns null for empty query', () => {
  const decision = routeForGlobalSearch('', BOTH_ON)
  assert.equal(describeGlobalSearchActor('', decision), null)
})

test('describeGlobalSearchActor trims surrounding whitespace in the echo', () => {
  const decision = routeForGlobalSearch('  alice  ', BOTH_ON)
  assert.equal(
    describeGlobalSearchActor('  alice  ', decision),
    '已搜 alice：跳转到 会员运营',
  )
})
