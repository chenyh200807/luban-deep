import test from 'node:test'
import assert from 'node:assert/strict'

import { isWechatHarnessEnabled } from '../lib/wechat-harness-gate.ts'

test('wechat harness stays closed in production unless server-side smoke flag is enabled', () => {
  assert.equal(
    isWechatHarnessEnabled({
      nodeEnv: 'production',
      enableWechatHarness: '',
      publicEnableWechatHarness: '',
    }),
    false,
  )

  assert.equal(
    isWechatHarnessEnabled({
      nodeEnv: 'production',
      enableWechatHarness: 'true',
      publicEnableWechatHarness: '',
    }),
    true,
  )
})

test('wechat harness ignores public alias in production so there is only one canonical flag', () => {
  assert.equal(
    isWechatHarnessEnabled({
      nodeEnv: 'production',
      enableWechatHarness: '',
      publicEnableWechatHarness: 'true',
    }),
    false,
  )
})

test('wechat harness remains available outside production without extra flags', () => {
  assert.equal(
    isWechatHarnessEnabled({
      nodeEnv: 'development',
      enableWechatHarness: '',
      publicEnableWechatHarness: '',
    }),
    true,
  )
})
