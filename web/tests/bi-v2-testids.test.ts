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

test('BiDataTable supports row-level click without stealing checkbox/action clicks', async () => {
  const table = await readWeb('components/bi-v2/BiDataTable.tsx')

  assert.ok(table.includes('onRowClick?: (row: T) => void'))
  assert.ok(table.includes('rowAriaLabel?: (row: T) => string'))
  assert.ok(table.includes('onKeyDown='))
  assert.ok(table.includes('event.stopPropagation()'))
})
