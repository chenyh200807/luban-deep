import test from 'node:test'
import assert from 'node:assert/strict'

import {
  normalizePhone,
  isPlausiblePhone,
  shouldNotifyOperators,
  buildOperatorMessage,
  buildWebhookBody,
  type OperatorAlertInput,
} from '../app/api/feedback/responses/feedback-logic.ts'

/* ---------- 手机号宽松规范化 / 校验 ---------- */

test('normalizePhone 去除空格/横线/括号，保留 + 与数字', () => {
  assert.equal(normalizePhone('138 1234 5678'), '13812345678')
  assert.equal(normalizePhone('138-1234-5678'), '13812345678')
  assert.equal(normalizePhone('(138) 1234 5678'), '13812345678')
  assert.equal(normalizePhone('+852 9123 4567'), '+85291234567')
})

test('isPlausiblePhone 选填：空串合法', () => {
  assert.equal(isPlausiblePhone(''), true)
})

test('isPlausiblePhone 放行大陆 11 位号码', () => {
  assert.equal(isPlausiblePhone('13812345678'), true)
})

test('isPlausiblePhone 放行国际号（之前会被旧 /^1\\d{10}$/ 误杀）', () => {
  assert.equal(isPlausiblePhone('+85291234567'), true)
  assert.equal(isPlausiblePhone('+1 415 555 0123'), true)
})

test('isPlausiblePhone 挡明显脏数据', () => {
  assert.equal(isPlausiblePhone('123'), false) // 太短
  assert.equal(isPlausiblePhone('1234567890123456'), false) // 16 位，超 E.164
  assert.equal(isPlausiblePhone('abc'), false) // 无数字
})

/* ---------- 运营通知触发判定 ---------- */

test('shouldNotifyOperators: NPS≤6 触发', () => {
  assert.equal(shouldNotifyOperators({ nps: 6, revisitWillingness: 'no' }), true)
  assert.equal(shouldNotifyOperators({ nps: 0, revisitWillingness: 'no' }), true)
})

test('shouldNotifyOperators: 高 NPS 且无回访意愿不触发', () => {
  assert.equal(shouldNotifyOperators({ nps: 9, revisitWillingness: 'no' }), false)
  assert.equal(shouldNotifyOperators({ nps: 10, revisitWillingness: 'depends_time' }), false)
})

test('shouldNotifyOperators: 愿意回访触发（即使 NPS 高）', () => {
  assert.equal(shouldNotifyOperators({ nps: 9, revisitWillingness: 'very_willing' }), true)
  assert.equal(shouldNotifyOperators({ nps: 8, revisitWillingness: 'ok' }), true)
})

test('shouldNotifyOperators: NPS 为 null 时仅看回访意愿', () => {
  assert.equal(shouldNotifyOperators({ nps: null, revisitWillingness: 'no' }), false)
  assert.equal(shouldNotifyOperators({ nps: null, revisitWillingness: 'very_willing' }), true)
})

/* ---------- 消息文本 ---------- */

const sampleInput: OperatorAlertInput = {
  nps: 4,
  revisitWillingness: 'very_willing',
  overallSatisfaction: 2,
  willContinue: 'depends',
  unsolvedPain: '网络图计算没人逐步纠错',
  topSuggestion: '加真题模考',
  phone: '13812345678',
  wechatId: 'luban_user',
  createdAt: '2026-05-29T10:00:00.000Z',
  sourcePage: 'luban-html-js-wechat-required',
}

test('buildOperatorMessage 含关键字段与联系方式', () => {
  const msg = buildOperatorMessage(sampleInput)
  assert.match(msg, /NPS：4/)
  assert.match(msg, /满意度：2\/5/)
  assert.match(msg, /微信 luban_user/)
  assert.match(msg, /手机 13812345678/)
  assert.match(msg, /网络图计算/)
})

test('buildOperatorMessage 无联系方式时显示占位', () => {
  const msg = buildOperatorMessage({ ...sampleInput, phone: '', wechatId: '' })
  assert.match(msg, /未留联系方式/)
})

test('buildOperatorMessage 空 NPS/满意度显示「未填」', () => {
  const msg = buildOperatorMessage({ ...sampleInput, nps: null, overallSatisfaction: null })
  assert.match(msg, /NPS：未填/)
  assert.match(msg, /满意度：未填/)
})

/* ---------- webhook body 适配 ---------- */

test('buildWebhookBody: 企业微信默认格式（msgtype）', () => {
  const body = buildWebhookBody('qyapi.weixin.qq.com', 'hi')
  assert.deepEqual(body, { msgtype: 'text', text: { content: 'hi' } })
})

test('buildWebhookBody: 飞书格式（msg_type）', () => {
  const body = buildWebhookBody('open.feishu.cn', 'hi')
  assert.deepEqual(body, { msg_type: 'text', content: { text: 'hi' } })
})

test('buildWebhookBody: Lark 海外域名也识别为飞书格式', () => {
  const body = buildWebhookBody('open.larksuite.com', 'hi')
  assert.deepEqual(body, { msg_type: 'text', content: { text: 'hi' } })
})
