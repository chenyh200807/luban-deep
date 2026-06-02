import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(__dirname, '..')
const repoRoot = resolve(webRoot, '..')

async function readRepo(path: string): Promise<string> {
  return readFile(resolve(repoRoot, path), 'utf8')
}

test('web product behavior helper reuses surface-events endpoint and visit_id', async () => {
  const source = await readRepo('web/lib/surface-telemetry.ts')
  assert.match(source, /observability\/surface-events/)
  assert.doesNotMatch(source, /product-behavior\/events/)
  assert.match(source, /visitId/)
  assert.match(source, /trackWebProductBehaviorEvent/)
})

test('wechat product behavior helper reuses surface-events endpoint and visit_id', async () => {
  const source = await readRepo('wx_miniprogram/utils/surface-telemetry.js')
  assert.match(source, /observability\/surface-events/)
  assert.doesNotMatch(source, /product-behavior\/events/)
  assert.match(source, /visitId/)
  assert.match(source, /trackProductBehavior/)
})

test('yousen product behavior helper reuses surface-events endpoint and visit_id', async () => {
  const source = await readRepo('yousenwebview/packageDeeptutor/utils/surface-telemetry.js')
  assert.match(source, /observability\/surface-events/)
  assert.doesNotMatch(source, /product-behavior\/events/)
  assert.match(source, /visitId/)
  assert.match(source, /trackProductBehavior/)
})
