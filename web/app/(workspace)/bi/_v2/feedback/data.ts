export type FeedbackSource = 'ai_message' | 'invite_test' | 'member_note'

export type FeedbackStatus = 'open' | 'triaged' | 'ignored'

export type FeedbackOwner = 'quality' | 'growth' | 'ops' | 'product'

export type FeedbackItem = {
  id: string
  source: FeedbackSource
  rating: number
  reason: string
  detail: string
  member: string
  session_id?: string
  message_id?: string
  answer_mode?: string
  requested_response_mode?: string
  effective_response_mode?: string
  response_mode_degrade_reason?: string
  reason_tags?: string[]
  problem_type?: string
  symptom_tags?: string[]
  attachment_count?: number
  attachments?: Array<{
    id?: string
    kind?: string
    filename?: string
    mime_type?: string
    size?: number
    url?: string
    temp_path?: string
  }>
  context_snapshot?: {
    route?: string
    network_type?: string
    device_model?: string
    platform?: string
    system?: string
    wechat_version?: string
  }
  status: FeedbackStatus
  owner: FeedbackOwner
  created_at: string
  sla_target_hours: number
  resolution?: string
}

// Round 4 S4 (M-B): mock data dev-only; production bundle contains [].
export const FEEDBACK_ITEMS: FeedbackItem[] =
  process.env.NODE_ENV === 'production'
    ? []
    : [
        {
          id: 'fb_9012',
          source: 'ai_message',
          rating: 1,
          reason: '答非所问 / 公式错误',
          detail: '学员问牛顿第二定律推导，AI 答出动量守恒。',
          member: 'u_8421',
          status: 'open',
          owner: 'quality',
          created_at: '今天 10:21',
          sla_target_hours: 24,
        },
        {
          id: 'fb_9013',
          source: 'ai_message',
          rating: 1,
          reason: '解题步骤跳跃',
          detail: 'AI 中间步骤直接跳到答案，学员反馈看不懂。',
          member: 'u_8788',
          status: 'open',
          owner: 'quality',
          created_at: '今天 09:48',
          sla_target_hours: 24,
        },
        {
          id: 'fb_9014',
          source: 'invite_test',
          rating: 4,
          reason: '希望支持英语阅读',
          detail: '内测申请备注：建议加英语阅读板块。',
          member: 'u_8801',
          status: 'triaged',
          owner: 'growth',
          created_at: '昨天 20:11',
          sla_target_hours: 72,
          resolution: '已加入 P1 排期，回复用户感谢。',
        },
        {
          id: 'fb_9015',
          source: 'member_note',
          rating: 2,
          reason: '续费倾向低 / 价格敏感',
          detail: '客服记录：表示 SVIP 太贵，希望买月卡先试。',
          member: 'u_8633',
          status: 'open',
          owner: 'growth',
          created_at: '昨天 18:30',
          sla_target_hours: 48,
        },
        {
          id: 'fb_9016',
          source: 'ai_message',
          rating: 5,
          reason: '解释清晰',
          detail: '学员留言：这道题讲得真好。',
          member: 'u_8519',
          status: 'ignored',
          owner: 'quality',
          created_at: '昨天 16:02',
          sla_target_hours: 0,
          resolution: '正面反馈无需 triage，仅纳入质量报表。',
        },
        {
          id: 'fb_9017',
          source: 'invite_test',
          rating: 3,
          reason: '希望支持物理实验视频',
          detail: '内测申请填写：物理科目最好有实验视频。',
          member: 'u_8932',
          status: 'triaged',
          owner: 'product',
          created_at: '前天 14:25',
          sla_target_hours: 72,
          resolution: '已转产品 backlog，回复用户期望进度。',
        },
      ]

export const STATUS_LABELS: Record<FeedbackStatus, string> = {
  open: '待处理',
  triaged: '已分诊',
  ignored: '已忽略',
}

export const SOURCE_LABELS: Record<FeedbackSource, string> = {
  ai_message: 'AI 消息反馈',
  invite_test: '内测申请',
  member_note: '运营备注',
}

export const OWNER_LABELS: Record<FeedbackOwner, string> = {
  quality: 'AI 质量',
  growth: '增长',
  ops: '运营',
  product: '产品',
}

export type FeedbackResolution = {
  feedbackId: string
  status: Exclude<FeedbackStatus, 'open'>
  note: string
  actor: string
  at: string
}
