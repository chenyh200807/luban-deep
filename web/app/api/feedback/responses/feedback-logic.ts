// 鲁班智考 · 内测回访问卷的纯逻辑（无 pg / next 依赖，便于 node --test 单测）：
//   1) 手机号宽松规范化与校验（兼容空格/横线/括号/国际号 +xx）
//   2) 运营通知触发判定（NPS 低分 detractor 或高回访意愿）
//   3) 通知消息文本与 webhook body 构建（自动适配企业微信 / 飞书）

const PHONE_SEPARATORS = /[\s\-()]/g

// 去除人类书写常见分隔符（空格/横线/括号），保留前导 + 与数字。
export function normalizePhone(raw: string): string {
  return raw.replace(PHONE_SEPARATORS, '')
}

// 宽松校验：选填，空即合法；非空时按 ITU E.164 取 7–15 位数字。
// 目的是只挡明显脏数据，国际号 / 带分隔符的合法号码一律放行，异常长度交运营线下核查。
export function isPlausiblePhone(phone: string): boolean {
  if (!phone) return true
  const digits = phone.replace(/\D/g, '')
  return digits.length >= 7 && digits.length <= 15
}

export type OperatorAlertInput = {
  nps: number | null
  revisitWillingness: string
  overallSatisfaction: number | null
  willContinue: string
  unsolvedPain: string
  topSuggestion: string
  phone: string
  wechatId: string
  createdAt: string
  sourcePage: string
}

// 触发运营即时跟进的两类高价值答卷：
//   - NPS ≤ 6（detractor，需止损 / 挽回）
//   - 明确愿意回访（very_willing / ok，需尽快约访谈）
export function shouldNotifyOperators(input: Pick<OperatorAlertInput, 'nps' | 'revisitWillingness'>): boolean {
  if (input.nps !== null && input.nps <= 6) return true
  if (input.revisitWillingness === 'very_willing' || input.revisitWillingness === 'ok') return true
  return false
}

function alertReason(input: Pick<OperatorAlertInput, 'nps' | 'revisitWillingness'>): string {
  const reasons: string[] = []
  if (input.nps !== null && input.nps <= 6) reasons.push('NPS 偏低，建议优先挽回')
  if (input.revisitWillingness === 'very_willing' || input.revisitWillingness === 'ok') {
    reasons.push('用户愿意回访，建议尽快约访谈')
  }
  return reasons.join('；') || '需跟进'
}

// 运营群通知文本。联系方式为回访所需，仅发往内部运营 IM 群。
export function buildOperatorMessage(input: OperatorAlertInput): string {
  const npsText = input.nps === null ? '未填' : String(input.nps)
  const satText = input.overallSatisfaction === null ? '未填' : `${input.overallSatisfaction}/5`
  const contact = [
    input.wechatId ? `微信 ${input.wechatId}` : '',
    input.phone ? `手机 ${input.phone}` : '',
  ].filter(Boolean).join(' / ') || '未留联系方式'

  const lines = [
    '🔔 鲁班回访新反馈（需跟进）',
    `原因：${alertReason(input)}`,
    `NPS：${npsText}  满意度：${satText}`,
    `继续使用：${input.willContinue || '未填'}  回访意愿：${input.revisitWillingness || '未填'}`,
    input.unsolvedPain ? `最想解决：${input.unsolvedPain}` : '',
    input.topSuggestion ? `一句话建议：${input.topSuggestion}` : '',
    `联系方式：${contact}`,
    `来源：${input.sourcePage || '未知'}  时间：${input.createdAt}`,
  ]
  return lines.filter(Boolean).join('\n')
}

export type WebhookBody =
  | { msgtype: 'text'; text: { content: string } }
  | { msg_type: 'text'; content: { text: string } }

// 按 webhook host 自动选格式：飞书/Lark 用 msg_type，其余（默认企业微信群机器人）用 msgtype。
export function buildWebhookBody(host: string, content: string): WebhookBody {
  const h = host.toLowerCase()
  if (h.includes('feishu') || h.includes('larksuite')) {
    return { msg_type: 'text', content: { text: content } }
  }
  return { msgtype: 'text', text: { content } }
}
