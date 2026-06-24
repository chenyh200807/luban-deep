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

test('member account api uses canonical auth lifecycle endpoints', async () => {
  const api = await readWeb('lib/member-account-api.ts')

  assert.ok(api.includes("apiUrl('/api/v1/auth/login')"))
  assert.ok(api.includes("apiUrl('/api/v1/auth/register')"))
  assert.ok(api.includes("apiUrl('/api/v1/auth/send-code')"))
  assert.ok(api.includes("apiUrl('/api/v1/auth/reset-password')"))
  assert.ok(api.includes("apiUrl('/api/v1/auth/change-password')"))
  assert.ok(api.includes("apiUrl('/api/v1/auth/delete-account')"))
  assert.ok(api.includes('Authorization: `Bearer ${token}`'))
  assert.ok(api.includes('old_password: string'))
  assert.ok(api.includes('new_password: string'))
  assert.ok(api.includes('deleteMemberAccount'))
})

test('member account panel keeps member session separate from BI admin session', async () => {
  const panel = await readWeb('app/(workspace)/bi/_components/BiMemberAccountPanel.tsx')

  assert.ok(panel.includes("MEMBER_ACCOUNT_SESSION_STORAGE_KEY = 'deeptutor.bi.member.account.session'"))
  assert.ok(panel.includes('window.sessionStorage'))
  assert.ok(panel.includes('请先在本面板登录会员账号，再修改该账号密码。'))
  assert.ok(panel.includes('管理员后台解锁仍使用上方管理员登录，不与会员登录态混用。'))
  assert.ok(panel.includes('changeMemberPassword(session.token'))
  assert.ok(panel.includes('deleteMemberAccount(session.token'))
  assert.ok(panel.includes('注销账号'))
  assert.ok(panel.includes('注销后该会员账号将无法登录，BI 仍保留审计、账务与学习历史。'))
  assert.equal(panel.includes('deeptutor.bi.admin.session'), false)
})
