import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')

test('BI workspace does not mount the chat runtime provider', async () => {
  const source = await readFile(resolve(webRoot, 'app/(workspace)/WorkspaceFrame.tsx'), 'utf8')

  assert.match(source, /if \(isBiWorkspace\) return frame/)
  assert.match(source, /return <UnifiedChatProvider>\{frame\}<\/UnifiedChatProvider>/)
  assert.doesNotMatch(source, /return \(\s*<UnifiedChatProvider>[\s\S]*isBiWorkspace/)
})

test('BI overview consumes one page-level server snapshot and keeps confirmed data on refresh', async () => {
  const source = await readFile(
    resolve(webRoot, 'app/(workspace)/bi/_v2/BiV2OverviewPanel.tsx'),
    'utf8'
  )

  assert.match(source, /const overview = await getBiOverview\(\{ days \}\)/)
  assert.doesNotMatch(source, /getBiActiveTrend|getBiAnomalies|Promise\.allSettled/)
  assert.match(source, /setBundle\(current => \(\{ \.\.\.current, partial: true/)
  assert.match(source, /AI 回合成功率/)
  assert.doesNotMatch(source, /经营健康度/)
})

test('feedback loads only the active workspace instead of all three datasets', async () => {
  const source = await readFile(
    resolve(webRoot, 'app/(workspace)/bi/_v2/feedback/BiV2FeedbackPanel.tsx'),
    'utf8'
  )

  assert.match(source, /workspaceView === 'feedback'\) void loadFeedback\(\)/)
  assert.match(source, /workspaceView === 'invite-test'\) void loadInviteTest\(\)/)
  assert.match(source, /workspaceView === 'luban-feedback'\) void loadLubanFeedback\(\)/)
})

test('BI owns its loading language and navigation count', async () => {
  const loading = await readFile(resolve(webRoot, 'app/(workspace)/bi/loading.tsx'), 'utf8')
  const surface = await readFile(
    resolve(webRoot, 'app/(workspace)/bi/_v2/BiV2Surface.tsx'),
    'utf8'
  )

  assert.match(loading, /正在读取经营快照/)
  assert.doesNotMatch(loading, /Chat|聊天/)
  assert.match(surface, /当前 7 个可用主区/)
})
