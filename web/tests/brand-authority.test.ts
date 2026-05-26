import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveBrandCopy } from '../lib/brand.ts'

test('brand authority defaults all user-facing copy to 鲁班智考', () => {
  const copy = resolveBrandCopy({})
  assert.equal(copy.brandName, '鲁班智考')
  assert.equal(copy.biTitle, '鲁班智考 BI 工作台')
})
