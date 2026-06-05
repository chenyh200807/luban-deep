import test from 'node:test'
import assert from 'node:assert/strict'

import { normalizeBiCostReconciliation } from '../lib/bi-cost-reconciliation.ts'

test('cost reconciliation keeps unconfigured official provider state visible', () => {
  const providers = normalizeBiCostReconciliation({
    providers: {
      deepseek: {
        internal: {
          status: 'ok',
          total_tokens: 1600,
          currency_amounts: { USD: 0.0001 },
        },
        official_usage: {
          status: 'unconfigured',
          currency_amounts: {},
        },
        reconciliation: {
          status: 'waiting_for_official_export',
          token_delta: 1600,
          warnings: ['waiting_for_official_export'],
        },
      },
    },
  })

  assert.equal(providers.length, 1)
  assert.equal(providers[0].providerName, 'deepseek')
  assert.equal(providers[0].officialStatus, 'unconfigured')
  assert.equal(providers[0].reconciliationStatus, 'waiting_for_official_export')
  assert.equal(providers[0].currency, 'USD')
  assert.equal(providers[0].internalAmount, 0.0001)
  assert.equal(providers[0].officialAmount, null)
  assert.equal(providers[0].tokenDelta, 1600)
  assert.deepEqual(providers[0].warnings, ['waiting_for_official_export'])
})

test('cost reconciliation normalizes dashscope official list price and net charge', () => {
  const providers = normalizeBiCostReconciliation({
    providers: {
      dashscope: {
        internal: {
          status: 'ok',
          total_tokens: 2200,
          currency_amounts: { CNY: 0.08 },
        },
        official_usage: {
          status: 'ok',
          total_tokens: 2000,
          list_price_cost: { CNY: 0.1 },
          net_charge_cost: { CNY: 0.07 },
        },
        reconciliation: {
          status: 'warning',
          token_delta: 200,
          amount_delta_by_currency: { CNY: -0.02 },
          warnings: ['amount_delta'],
        },
      },
    },
  })

  assert.equal(providers.length, 1)
  assert.equal(providers[0].providerName, 'dashscope')
  assert.equal(providers[0].label, '阿里云 DashScope/Bailian')
  assert.equal(providers[0].currency, 'CNY')
  assert.equal(providers[0].internalAmount, 0.08)
  assert.equal(providers[0].officialAmount, 0.1)
  assert.equal(providers[0].netOfficialAmount, 0.07)
  assert.equal(providers[0].amountDelta, -0.02)
  assert.equal(providers[0].tokenDelta, 200)
})
