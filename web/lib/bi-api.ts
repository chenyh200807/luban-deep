import { BI_API_TOKEN, apiUrl, withAdminAuthorization, withBiApiToken } from '@/lib/api'

import { BI_WORKBENCH_TITLE } from "./brand"

export function resolveBiAttachmentUrl(url: string | undefined): string {
  const normalized = (url ?? '').trim()
  if (!normalized) return ''
  if (/^https?:\/\//.test(normalized)) return normalized
  if (normalized.startsWith('/api/')) return apiUrl(normalized)
  return normalized
}

export interface BiMetricCard {
  label: string
  value: number | string
  hint?: string
  delta?: string
  tone?: 'neutral' | 'good' | 'warning' | 'critical'
}

export interface BiTrendPoint {
  label: string
  active: number
  cost: number
  successful: number
}

export interface BiBossDailyCostPoint {
  date: string
  label: string
  costUsd: number
  tokens: number
  turns: number
}

export interface BiBossDailyCost {
  todayUsd: number
  windowTotalUsd: number
  averageDailyUsd: number
  source: string
  series: BiBossDailyCostPoint[]
}

export interface BiRetentionCohort {
  label: string
  values: number[]
}

export interface BiRankItem {
  label: string
  value: number
  rate?: number
  hint?: string
  secondary?: string
}

export interface BiMemberSample {
  user_id: string
  display_name: string
  tier?: string
  status?: string
  risk_level?: string
  last_active_at?: string
  detail?: string
}

export interface BiTutorBotItem {
  bot_id: string
  name: string
  capability?: string
  entrypoint?: string
  tier?: string
  status?: string
  last_active_at?: string
  recent_message?: string
  runs?: number
  success_rate?: number
  detail?: string
}

export interface BiLearnerSession {
  session_id: string
  title: string
  capability?: string
  status?: string
  started_at?: string
  ended_at?: string
  duration_minutes?: number
  summary?: string
}

export interface BiLearnerChapterMastery {
  chapter_id?: string
  name: string
  mastery: number
  hint?: string
  evidence?: string
}

export interface BiLearnerNoteLedgerSummary {
  notes_count?: number
  pinned_notes_count?: number
  recent_note?: string
  recent_ledger?: string
  wallet_balance?: number
  ledger_delta?: number
  summary?: string
}

export interface BiLearnerDetailData {
  user_id: string
  display_name: string
  profile: BiMetricCard[]
  recent_sessions: BiLearnerSession[]
  chapter_mastery: BiLearnerChapterMastery[]
  notes_summary: BiLearnerNoteLedgerSummary
}

export interface BiAlertItem {
  level: 'info' | 'warning' | 'critical'
  title: string
  detail?: string
}

export interface BiMetricDefinition {
  metric_id: string
  label: string
  group?: string
  definition: string
  authority: string
  trustLevel: 'A' | 'B' | 'C' | 'D' | string
  owner: string
  drilldown: string
  displayHint?: string
}

export interface BiNorthStarInput extends BiMetricDefinition {
  value?: number | string | null
}

export interface BiNorthStarPayload extends BiMetricDefinition {
  value: number
  windowDays: number
  calculation: string
  inputs: BiNorthStarInput[]
}

export interface BiGrowthFunnelStep {
  id: string
  label: string
  value: number
  conversionRate: number
  trustLevel: string
  authority: string
  drilldown: string
}

export interface BiGrowthFunnelPayload {
  title: string
  summary: string
  steps: BiGrowthFunnelStep[]
}

export interface BiMemberHealthPayload {
  score: BiMetricDefinition & { value?: number; note?: string }
  distribution: Array<{ bucket: string; label: string; count: number }>
  reasons: string[]
  samples: BiMemberSample[]
}

export interface BiOperatingRhythmAction {
  title: string
  target: string
  status: string
  reason: string
}

export interface BiOperatingRhythmPayload {
  cadences: Array<{ id: string; label: string; focus: string }>
  topActions: BiOperatingRhythmAction[]
}

export interface BiFeedbackRecord {
  feedback_id?: string
  id?: string
  user_id?: string
  session_id?: string
  message_id?: string
  rating?: number
  reason_tags?: string[]
  comment?: string
  feedback_source?: string
  answer_mode?: string
  requested_response_mode?: string
  effective_response_mode?: string
  response_mode_degrade_reason?: string
  triage_status?: 'open' | 'triaged' | 'ignored' | string
  triage_operator?: string
  triage_note?: string
  triage_updated_at?: string
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
  created_at?: string
}

export interface BiFeedbackPayload {
  window_days: number
  storage_status: string
  summary: {
    total_feedback: number
    thumbs_up: number
    thumbs_down: number
    neutral: number
    commented: number
    unique_users: number
    unique_sessions: number
    unique_messages: number
  }
  rating_breakdown: Array<{ rating: number; label: string; count: number }>
  top_reason_tags: Array<{ tag: string; count: number }>
  answer_modes: Array<{ answer_mode: string; count: number }>
  recent: BiFeedbackRecord[]
}

export interface BiTeachingChapterProgress {
  chapterId?: string
  name: string
  mastery: number
  memberCount: number
  status?: string
  evidence?: string
}

export interface BiTeachingEffectPayload {
  status: string
  summary: string
  metrics: Array<BiMetricDefinition & { value?: number | string | null; status?: string }>
  chapterProgress: BiTeachingChapterProgress[]
}

export interface BiAiQualityPayload extends BiMetricDefinition {
  engineeringSuccessRate: number
  failedTurns: number
  totalTurns: number
  teachingSuccessStatus: string
  note: string
  samples: Array<{ turn_id?: string; session_id?: string; status?: string }>
}

export interface BiUnitEconomicsPayload extends BiMetricDefinition {
  revenueStatus: string
  summary: string
  windowTotalCostUsd: number
  costPerEffectiveLearningUsd: number
  source: string
}

export interface BiDataTrustPayload {
  status: string
  trustModel: string
  degradedModules: Array<{ id: string; label: string; status: string; detail: string }>
  metricDefinitions: BiMetricDefinition[]
}

export interface BiOverviewData {
  title: string
  subtitle: string
  cards: BiMetricCard[]
  highlights: string[]
  entrypoints: BiRankItem[]
  alerts: BiAlertItem[]
  northStar?: BiNorthStarPayload
  growthFunnel?: BiGrowthFunnelPayload
  memberHealth?: BiMemberHealthPayload
  operatingRhythm?: BiOperatingRhythmPayload
  teachingEffect?: BiTeachingEffectPayload
  aiQuality?: BiAiQualityPayload
  unitEconomics?: BiUnitEconomicsPayload
  dataTrust?: BiDataTrustPayload
}

export interface BiTrendData {
  points: BiTrendPoint[]
}

export interface BiRetentionData {
  cohorts: BiRetentionCohort[]
  labels: string[]
}

export interface BiCapabilityData {
  items: BiRankItem[]
  upgradePaths: BiRankItem[]
}

export interface BiToolData {
  items: BiRankItem[]
  efficiency: BiRankItem[]
}

export interface BiKnowledgeData {
  items: BiRankItem[]
  topQueries: BiRankItem[]
  zeroHitRate?: number
}

export interface BiMemberData {
  cards: BiMetricCard[]
  tiers: BiRankItem[]
  risks: BiRankItem[]
  samples: BiMemberSample[]
}

export interface BiCostData {
  cards: BiMetricCard[]
  models: BiRankItem[]
  providers: BiRankItem[]
}

export interface BiTutorBotData {
  cards: BiMetricCard[]
  ranking: BiRankItem[]
  statusBreakdown: BiRankItem[]
  recentActive: BiTutorBotItem[]
  recentMessages: BiTutorBotItem[]
}

export interface BiAnomalyData {
  items: BiAlertItem[]
}

export interface BiInviteTestApplication {
  id: string
  created_at: string
  source_page: string
  utm_source: string
  utm_campaign: string
  name: string
  phone: string
  email: string
  province: string
  age_range: string
  education: string
  occupation: string
  wechat_id: string
  exam_type: string
  exam_stage: string
  preparation_years: string
  knowledge_foundation: string
  pain_point: string
  weekly_time: string
  daily_study_time: string
  current_method: string
  study_difficulties: string
  latest_wrong_question: string
  is_yousen_member: string
  exam_date: string
  accept_interview: boolean
  consent: boolean
  status: string
  operator_note: string
  submit_count: number
  contact_revealed: boolean
}

export interface BiInviteTestStats {
  window_days: number
  storage_status: string
  summary: {
    total_applications: number
    unique_contacts: number
    accept_interview_count: number
    accept_interview_rate: number
    with_wrong_question_count: number
    with_wrong_question_rate: number
    consented_count: number
  }
  status_breakdown: Array<{ status: string; count: number }>
  source_breakdown: Array<{ source_page: string; count: number }>
  exam_type_breakdown: Array<{ exam_type: string; count: number }>
  exam_stage_breakdown: Array<{ exam_stage: string; count: number }>
  pain_point_breakdown: Array<{ pain_point: string; count: number }>
  weekly_time_breakdown: Array<{ weekly_time: string; count: number }>
  age_range_breakdown: Array<{ age_range: string; count: number }>
  province_breakdown: Array<{ province: string; count: number }>
  education_breakdown: Array<{ education: string; count: number }>
  occupation_breakdown: Array<{ occupation: string; count: number }>
  preparation_years_breakdown: Array<{ preparation_years: string; count: number }>
  knowledge_foundation_breakdown: Array<{ knowledge_foundation: string; count: number }>
  daily_study_time_breakdown: Array<{ daily_study_time: string; count: number }>
}

export interface BiInviteTestApplicationsResponse {
  window_days: number
  storage_status: string
  total: number
  contact_revealed: boolean
  items: BiInviteTestApplication[]
}

export interface BiLubanFeedbackResponse {
  id: string
  created_at: string
  source_page: string
  survey_version: string
  nps: number | null
  overall_satisfaction: number | null
  most_valuable: string
  will_continue: string
  pay_willingness: string
  would_recommend: string
  revisit_willingness: string
  attempt_count: string
  exam_timeframe: string
  one_word: string
  feat_case_grading: string
  feat_error_coach: string
  feat_qa: string
  ease_of_use: string
  accuracy: string
  speed: string
  problems: string[]
  problems_other: string
  top_suggestion: string
  unsolved_pain: string
  wanted_features: string[]
  wanted_features_other: string
  phone: string
  wechat_id: string
  status: string
  operator_note: string
  contact_revealed: boolean
}

export interface BiLubanFeedbackStats {
  window_days: number
  storage_status: string
  summary: {
    total_responses: number
    nps_score: number
    nps_base: number
    promoters: number
    passives: number
    detractors: number
    avg_satisfaction: number
    satisfaction_base: number
    revisit_willing_count: number
    revisit_willing_rate: number
    with_contact_count: number
    with_contact_rate: number
  }
  nps_breakdown: Array<{ nps: string; count: number }>
  satisfaction_breakdown: Array<{ overall_satisfaction: string; count: number }>
  most_valuable_breakdown: Array<{ most_valuable: string; count: number }>
  will_continue_breakdown: Array<{ will_continue: string; count: number }>
  pay_willingness_breakdown: Array<{ pay_willingness: string; count: number }>
  revisit_willingness_breakdown: Array<{ revisit_willingness: string; count: number }>
  attempt_count_breakdown: Array<{ attempt_count: string; count: number }>
  exam_timeframe_breakdown: Array<{ exam_timeframe: string; count: number }>
  status_breakdown: Array<{ status: string; count: number }>
  source_breakdown: Array<{ source_page: string; count: number }>
}

export interface BiLubanFeedbackResponsesResponse {
  window_days: number
  storage_status: string
  total: number
  contact_revealed: boolean
  items: BiLubanFeedbackResponse[]
}

export interface BiCommercePackage {
  id: string
  name: string
  tier: string
  points: number
  priceCny: number
  features: string[]
  status: string
  authority: string
  trust: string
}

export interface BiCommerceRechargeRecord {
  id: string
  userId: string
  points: number
  amountCny?: number | null
  channel: string
  status: string
  createdAt: string
  ledgerEventId: string
  idempotencyKey: string
  authority: string
  trust: string
}

export type BiCommerceLedgerKind = 'credit' | 'debit' | 'refund' | 'manual' | string

export interface BiCommerceLedgerRow {
  id: string
  userId: string
  kind: BiCommerceLedgerKind
  eventType: string
  amount: number
  balanceAfter?: number | null
  referenceType: string
  referenceId: string
  idempotencyKey: string
  effectiveAt: string
  metadata: Record<string, unknown>
  authority: string
  trust: string
}

export interface BiCommerceAnomaly {
  ruleId: string
  severity: 'critical' | 'high' | 'medium' | 'low' | string
  detectedAt: string
  affected: number
  owner: string
  status: string
  trust: string
  description: string
}

export interface BiCommerceData {
  status: string
  summary: {
    memberCount: number
    packageCount: number
    rechargeCount: number
    ledgerCount: number
    anomalyCount: number
    creditPoints: number
    debitPoints: number
  }
  authority: Record<string, string>
  packages: BiCommercePackage[]
  rechargeRecords: BiCommerceRechargeRecord[]
  ledger: BiCommerceLedgerRow[]
  anomalies: BiCommerceAnomaly[]
  warnings: string[]
}

export type BiLaunchReadinessStatus = 'PASS' | 'WARN' | 'FAIL' | 'SKIP' | 'NOT_RUN' | string

export interface BiLaunchReadinessRow {
  check_id: string
  label: string
  status: BiLaunchReadinessStatus
  required: boolean
  summary: string
  evidence: string[]
  run_id: string
  recorded_at?: number | null
  source_kind: string
  blockers: string[]
}

export interface BiLaunchReadinessDashboard {
  run_id: string
  generated_at: string
  final_status: BiLaunchReadinessStatus
  recommendation: string
  release: {
    release_id: string
    git_sha: string
    deployment_environment: string
  }
  rows: BiLaunchReadinessRow[]
  blockers: string[]
  source_runs: Record<string, string | undefined>
}

export interface BiBossKpiItem {
  label: string
  value: number | string
  hint?: string
  delta?: string
  tone?: BiMetricCard['tone']
  source?: 'overview' | 'members' | 'cost'
}

export interface BiBossActionItem {
  title: string
  detail: string
  tone?: BiMetricCard['tone']
  source?: 'anomalies' | 'members' | 'cost'
  handoffFilters?: Record<string, string | number | boolean | null>
}

export interface BiBossWorkbench {
  kpis: BiBossKpiItem[]
  actionQueue: BiBossActionItem[]
  heroIssue: string
  dailyCost?: BiBossDailyCost
}

type BiBossCoreModule = 'overview' | 'active-trend' | 'members' | 'cost'
export type BiWorkbenchModuleKey =
  | 'overview'
  | 'trend'
  | 'retention'
  | 'capabilities'
  | 'tools'
  | 'knowledge'
  | 'members'
  | 'cost'
  | 'tutorbots'
  | 'anomalies'
export type BiWorkbenchModuleIssues = Partial<Record<BiWorkbenchModuleKey, string>>

export interface BiWorkbenchData {
  overview: BiOverviewData
  trend: BiTrendData
  retention: BiRetentionData
  capabilities: BiCapabilityData
  tools: BiToolData
  knowledge: BiKnowledgeData
  members: BiMemberData
  cost: BiCostData
  tutorbots: BiTutorBotData
  anomalies: BiAnomalyData
}

export interface BiWorkbenchState {
  data: BiWorkbenchData
  issues: string[]
  boss: BiBossWorkbench
  moduleIssues: BiWorkbenchModuleIssues
}

export interface BiFetchOptions {
  days?: number
  capability?: string
  entrypoint?: string
  tier?: string
}

const DEFAULT_DATA: BiWorkbenchData = {
  overview: {
    title: BI_WORKBENCH_TITLE,
    subtitle: '加载后端 BI 接口后即可查看经营、学习、能力、知识库与会员的统一视图。',
    cards: [],
    highlights: [],
    entrypoints: [],
    alerts: [],
  },
  trend: { points: [] },
  retention: { cohorts: [], labels: ['D0', 'D1', 'D7', 'D30'] },
  capabilities: { items: [], upgradePaths: [] },
  tools: { items: [], efficiency: [] },
  knowledge: { items: [], topQueries: [], zeroHitRate: undefined },
  members: { cards: [], tiers: [], risks: [], samples: [] },
  cost: { cards: [], models: [], providers: [] },
  tutorbots: { cards: [], ranking: [], statusBreakdown: [], recentActive: [], recentMessages: [] },
  anomalies: { items: [] },
}

function unwrapPayload(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object') {
    return raw
  }

  const record = raw as Record<string, unknown>
  return record.data ?? record.result ?? record.payload ?? raw
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
}

function toString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return fallback
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return fallback
}

function optionalNumber(value: unknown): number | undefined {
  if (value === undefined || value === null || value === '') {
    return undefined
  }
  return toNumber(value, Number.NaN)
}

function toArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function toFiniteNumber(value: unknown, fallback = 0): number {
  const parsed = toNumber(value, fallback)
  return Number.isFinite(parsed) ? parsed : fallback
}

function firstArray(raw: unknown, keys: string[]): unknown[] {
  const record = asRecord(raw)
  for (const key of keys) {
    const value = record[key]
    if (Array.isArray(value)) return value
  }
  return []
}

function firstRecord(raw: unknown, keys: string[]): Record<string, unknown> {
  const record = asRecord(raw)
  for (const key of keys) {
    const value = record[key]
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value as Record<string, unknown>
    }
  }
  return record
}

function normalizeMetricCard(item: unknown, fallbackLabel = ''): BiMetricCard {
  const record = asRecord(item)
  const rawValue =
    record.value ?? record.count ?? record.total ?? record.amount ?? record.rate ?? record.score
  return {
    label: toString(record.label ?? record.name ?? record.title, fallbackLabel),
    value:
      typeof rawValue === 'number' || typeof rawValue === 'string'
        ? rawValue
        : toString(rawValue, '--'),
    hint: toString(record.hint ?? record.description ?? record.note ?? record.subtitle, ''),
    delta: toString(
      record.delta ?? record.change ?? record.trend ?? record.growth ?? record.diff,
      ''
    ),
    tone:
      record.tone === 'good' || record.tone === 'warning' || record.tone === 'critical'
        ? (record.tone as BiMetricCard['tone'])
        : 'neutral',
  }
}

function normalizeRankItem(item: unknown, fallbackLabel = ''): BiRankItem {
  const record = asRecord(item)
  return {
    label: toString(record.label ?? record.name ?? record.key ?? record.title, fallbackLabel),
    value: toNumber(
      record.value ?? record.count ?? record.total ?? record.amount ?? record.score,
      0
    ),
    rate: optionalNumber(record.rate ?? record.success_rate),
    hint: toString(record.hint ?? record.description ?? record.note ?? record.subtitle, ''),
    secondary: toString(record.secondary ?? record.extra ?? record.detail, ''),
  }
}

function normalizeTrendPoint(item: unknown, fallbackLabel = ''): BiTrendPoint {
  const record = asRecord(item)
  return {
    label: toString(
      record.label ?? record.date ?? record.day ?? record.time ?? record.name,
      fallbackLabel
    ),
    active: toNumber(record.active ?? record.active_learners ?? record.value ?? record.count, 0),
    cost: toNumber(record.cost ?? record.cost_usd ?? record.amount ?? record.expense, 0),
    successful: toNumber(
      record.successful ?? record.success ?? record.success_rate ?? record.rate,
      0
    ),
  }
}

function normalizeCohort(item: unknown, fallbackLabel = ''): BiRetentionCohort {
  const record = asRecord(item)
  const values = toArray(record.values ?? record.points ?? record.rates ?? record.matrix ?? [])
  return {
    label: toString(record.label ?? record.name ?? record.cohort ?? record.key, fallbackLabel),
    values: values.map(value => toNumber(value, 0)),
  }
}

function normalizeAlert(item: unknown, fallbackLabel = ''): BiAlertItem {
  const record = asRecord(item)
  const level = record.level === 'critical' || record.level === 'warning' ? record.level : 'info'
  return {
    level,
    title: toString(record.title ?? record.label ?? record.name, fallbackLabel),
    detail: toString(record.detail ?? record.description ?? record.note ?? record.subtitle, ''),
  }
}

function normalizeInviteTestApplication(item: unknown): BiInviteTestApplication {
  const record = asRecord(item)
  return {
    id: toString(record.id, ''),
    created_at: toString(record.created_at ?? record.createdAt, ''),
    source_page: toString(record.source_page ?? record.sourcePage, ''),
    utm_source: toString(record.utm_source ?? record.utmSource, ''),
    utm_campaign: toString(record.utm_campaign ?? record.utmCampaign, ''),
    name: toString(record.name, '未命名'),
    phone: toString(record.phone, ''),
    email: toString(record.email, ''),
    province: toString(record.province, ''),
    age_range: toString(record.age_range ?? record.ageRange, ''),
    education: toString(record.education, ''),
    occupation: toString(record.occupation, ''),
    wechat_id: toString(record.wechat_id ?? record.wechatId, ''),
    exam_type: toString(record.exam_type ?? record.examType, ''),
    exam_stage: toString(record.exam_stage ?? record.examStage, ''),
    preparation_years: toString(record.preparation_years ?? record.preparationYears, ''),
    knowledge_foundation: toString(record.knowledge_foundation ?? record.knowledgeFoundation, ''),
    pain_point: toString(record.pain_point ?? record.painPoint, ''),
    weekly_time: toString(record.weekly_time ?? record.weeklyTime, ''),
    daily_study_time: toString(record.daily_study_time ?? record.dailyStudyTime, ''),
    current_method: toString(record.current_method ?? record.currentMethod, ''),
    study_difficulties: toString(record.study_difficulties ?? record.studyDifficulties, ''),
    latest_wrong_question: toString(record.latest_wrong_question ?? record.latestWrongQuestion, ''),
    is_yousen_member: toString(record.is_yousen_member ?? record.isYousenMember, ''),
    exam_date: toString(record.exam_date ?? record.examDate, ''),
    accept_interview: record.accept_interview === true || record.acceptInterview === true,
    consent: record.consent === true,
    status: toString(record.status, 'submitted'),
    operator_note: toString(record.operator_note ?? record.operatorNote, ''),
    submit_count: toNumber(record.submit_count ?? record.submitCount, 1),
    contact_revealed: record.contact_revealed === true || record.contactRevealed === true,
  }
}

function normalizeLubanFeedbackResponse(item: unknown): BiLubanFeedbackResponse {
  const record = asRecord(item)
  const nps = record.nps === null || record.nps === undefined ? null : toNumber(record.nps, 0)
  const sat =
    record.overall_satisfaction === null || record.overall_satisfaction === undefined
      ? record.overallSatisfaction === null || record.overallSatisfaction === undefined
        ? null
        : toNumber(record.overallSatisfaction, 0)
      : toNumber(record.overall_satisfaction, 0)
  return {
    id: toString(record.id, ''),
    created_at: toString(record.created_at ?? record.createdAt, ''),
    source_page: toString(record.source_page ?? record.sourcePage, ''),
    survey_version: toString(record.survey_version ?? record.surveyVersion, ''),
    nps,
    overall_satisfaction: sat,
    most_valuable: toString(record.most_valuable ?? record.mostValuable, ''),
    will_continue: toString(record.will_continue ?? record.willContinue, ''),
    pay_willingness: toString(record.pay_willingness ?? record.payWillingness, ''),
    would_recommend: toString(record.would_recommend ?? record.wouldRecommend, ''),
    revisit_willingness: toString(record.revisit_willingness ?? record.revisitWillingness, ''),
    attempt_count: toString(record.attempt_count ?? record.attemptCount, ''),
    exam_timeframe: toString(record.exam_timeframe ?? record.examTimeframe, ''),
    one_word: toString(record.one_word ?? record.oneWord, ''),
    feat_case_grading: toString(record.feat_case_grading ?? record.featCaseGrading, ''),
    feat_error_coach: toString(record.feat_error_coach ?? record.featErrorCoach, ''),
    feat_qa: toString(record.feat_qa ?? record.featQa, ''),
    ease_of_use: toString(record.ease_of_use ?? record.easeOfUse, ''),
    accuracy: toString(record.accuracy, ''),
    speed: toString(record.speed, ''),
    problems: toArray(record.problems).map(value => toString(value)).filter(Boolean),
    problems_other: toString(record.problems_other ?? record.problemsOther, ''),
    top_suggestion: toString(record.top_suggestion ?? record.topSuggestion, ''),
    unsolved_pain: toString(record.unsolved_pain ?? record.unsolvedPain, ''),
    wanted_features: toArray(record.wanted_features ?? record.wantedFeatures)
      .map(value => toString(value))
      .filter(Boolean),
    wanted_features_other: toString(record.wanted_features_other ?? record.wantedFeaturesOther, ''),
    phone: toString(record.phone, ''),
    wechat_id: toString(record.wechat_id ?? record.wechatId, ''),
    status: toString(record.status, 'submitted'),
    operator_note: toString(record.operator_note ?? record.operatorNote, ''),
    contact_revealed: record.contact_revealed === true || record.contactRevealed === true,
  }
}

function normalizeCommercePackage(item: unknown): BiCommercePackage {
  const record = asRecord(item)
  return {
    id: toString(record.id ?? record.package_id ?? record.packageId, ''),
    name: toString(record.name ?? record.label, '未命名套餐'),
    tier: toString(record.tier ?? record.plan ?? record.level, ''),
    points: toNumber(record.points, 0),
    priceCny: toNumber(record.price_cny ?? record.priceCny ?? record.price, 0),
    features: toArray(record.features)
      .map(value => toString(value))
      .filter(Boolean),
    status: toString(record.status ?? record.state, ''),
    authority: toString(record.authority ?? record.source, ''),
    trust: toString(record.trust ?? record.trust_level ?? record.trustLevel, ''),
  }
}

function normalizeCommerceRechargeRecord(item: unknown): BiCommerceRechargeRecord {
  const record = asRecord(item)
  return {
    id: toString(record.id ?? record.order_id ?? record.orderId, ''),
    userId: toString(record.user_id ?? record.userId, ''),
    points: toNumber(record.points ?? record.amount, 0),
    amountCny:
      record.amount_cny === null || record.amountCny === null
        ? null
        : optionalNumber(record.amount_cny ?? record.amountCny),
    channel: toString(record.channel, 'unknown'),
    status: toString(record.status ?? record.state, ''),
    createdAt: toString(record.created_at ?? record.createdAt, ''),
    ledgerEventId: toString(record.ledger_event_id ?? record.ledgerEventId, ''),
    idempotencyKey: toString(record.idempotency_key ?? record.idempotencyKey, ''),
    authority: toString(record.authority ?? record.source, ''),
    trust: toString(record.trust ?? record.trust_level ?? record.trustLevel, ''),
  }
}

function normalizeCommerceLedgerRow(item: unknown): BiCommerceLedgerRow {
  const record = asRecord(item)
  return {
    id: toString(record.id, ''),
    userId: toString(record.user_id ?? record.userId, ''),
    kind: toString(record.kind ?? record.event_type ?? record.eventType, ''),
    eventType: toString(record.event_type ?? record.eventType, ''),
    amount: toNumber(record.amount ?? record.delta, 0),
    balanceAfter:
      record.balance_after === null || record.balanceAfter === null
        ? null
        : optionalNumber(record.balance_after ?? record.balanceAfter),
    referenceType: toString(record.reference_type ?? record.referenceType, ''),
    referenceId: toString(record.reference_id ?? record.referenceId, ''),
    idempotencyKey: toString(record.idempotency_key ?? record.idempotencyKey, ''),
    effectiveAt: toString(
      record.effective_at ?? record.effectiveAt ?? record.created_at ?? record.createdAt,
      ''
    ),
    metadata: asRecord(record.metadata),
    authority: toString(record.authority ?? record.source, ''),
    trust: toString(record.trust ?? record.trust_level ?? record.trustLevel, ''),
  }
}

function normalizeCommerceAnomaly(item: unknown): BiCommerceAnomaly {
  const record = asRecord(item)
  return {
    ruleId: toString(record.rule_id ?? record.ruleId, ''),
    severity: toString(record.severity ?? record.level, 'low'),
    detectedAt: toString(record.detected_at ?? record.detectedAt, ''),
    affected: toNumber(record.affected ?? record.count, 0),
    owner: toString(record.owner, ''),
    status: toString(record.status ?? record.state, ''),
    trust: toString(record.trust ?? record.trust_level ?? record.trustLevel, ''),
    description: toString(record.description ?? record.detail ?? record.note, ''),
  }
}

function normalizeLaunchReadinessRow(item: unknown): BiLaunchReadinessRow {
  const record = asRecord(item)
  return {
    check_id: toString(record.check_id ?? record.checkId, ''),
    label: toString(record.label ?? record.name, ''),
    status: toString(record.status, 'NOT_RUN'),
    required: record.required !== false,
    summary: toString(record.summary ?? record.detail, ''),
    evidence: toArray(record.evidence)
      .map(value => toString(value))
      .filter(Boolean),
    run_id: toString(record.run_id ?? record.runId, ''),
    recorded_at:
      record.recorded_at === null ? null : optionalNumber(record.recorded_at ?? record.recordedAt),
    source_kind: toString(record.source_kind ?? record.sourceKind, ''),
    blockers: toArray(record.blockers)
      .map(value => toString(value))
      .filter(Boolean),
  }
}

function normalizeCountRows(
  raw: unknown,
  keys: string[],
  labelKey: string
): Array<Record<string, string | number>> {
  return firstArray(raw, keys).map(item => {
    const record = asRecord(item)
    return {
      [labelKey]: toString(record[labelKey] ?? record.label ?? record.name ?? record.key, ''),
      count: toNumber(record.count ?? record.value ?? record.total, 0),
    }
  })
}

function normalizeMetricDefinition(item: unknown, fallbackLabel = ''): BiMetricDefinition {
  const record = asRecord(item)
  return {
    metric_id: toString(record.metric_id ?? record.metricId ?? record.id, ''),
    label: toString(record.label ?? record.name ?? record.title, fallbackLabel),
    group: toString(record.group ?? record.category, ''),
    definition: toString(record.definition ?? record.description ?? record.note, ''),
    authority: toString(record.authority ?? record.source, ''),
    trustLevel: toString(record.trust_level ?? record.trustLevel ?? record.trust, ''),
    owner: toString(record.owner ?? record.responsible, ''),
    drilldown: toString(record.drilldown ?? record.drill_down ?? record.target, ''),
    displayHint: toString(record.display_hint ?? record.displayHint ?? record.hint, ''),
  }
}

function normalizeNorthStarPayload(raw: unknown): BiNorthStarPayload | undefined {
  const record = asRecord(firstRecord(raw, ['north_star', 'northStar']))
  if (!Object.keys(record).length) return undefined
  const metric = normalizeMetricDefinition(record, '有效学习成功会员数')
  return {
    ...metric,
    value: toNumber(record.value, 0),
    windowDays: toNumber(record.window_days ?? record.windowDays, 30),
    calculation: toString(record.calculation ?? record.formula, ''),
    inputs: firstArray(record, ['inputs', 'drivers', 'tree']).map((item, index) => {
      const inputRecord = asRecord(item)
      return {
        ...normalizeMetricDefinition(item, `输入 ${index + 1}`),
        value:
          inputRecord.value === null
            ? null
            : typeof inputRecord.value === 'number' || typeof inputRecord.value === 'string'
              ? inputRecord.value
              : undefined,
      }
    }),
  }
}

function normalizeGrowthFunnelPayload(raw: unknown): BiGrowthFunnelPayload | undefined {
  const record = asRecord(firstRecord(raw, ['growth_funnel', 'growthFunnel']))
  if (!Object.keys(record).length) return undefined
  return {
    title: toString(record.title, '增长漏斗'),
    summary: toString(record.summary ?? record.description, ''),
    steps: firstArray(record, ['steps', 'items', 'funnel']).map((item, index) => {
      const step = asRecord(item)
      return {
        id: toString(step.id ?? step.metric_id ?? step.metricId, `step-${index + 1}`),
        label: toString(step.label ?? step.name ?? step.title, `步骤 ${index + 1}`),
        value: toNumber(step.value ?? step.count, 0),
        conversionRate: toNumber(step.conversion_rate ?? step.conversionRate ?? step.rate, 0),
        trustLevel: toString(step.trust_level ?? step.trustLevel, ''),
        authority: toString(step.authority ?? step.source, ''),
        drilldown: toString(step.drilldown ?? step.target, ''),
      }
    }),
  }
}

function normalizeMemberHealthPayload(raw: unknown): BiMemberHealthPayload | undefined {
  const record = asRecord(firstRecord(raw, ['member_health', 'memberHealth']))
  if (!Object.keys(record).length) return undefined
  const scoreRecord = asRecord(record.score)
  return {
    score: {
      ...normalizeMetricDefinition(scoreRecord, '会员健康评分'),
      value: optionalNumber(scoreRecord.value),
      note: toString(scoreRecord.note ?? scoreRecord.summary, ''),
    },
    distribution: firstArray(record, ['distribution', 'buckets']).map((item, index) => {
      const bucket = asRecord(item)
      return {
        bucket: toString(bucket.bucket ?? bucket.id, `bucket-${index + 1}`),
        label: toString(bucket.label ?? bucket.name, `分层 ${index + 1}`),
        count: toNumber(bucket.count ?? bucket.value, 0),
      }
    }),
    reasons: firstArray(record, ['reasons', 'recommendations'])
      .map(item => toString(item))
      .filter(Boolean),
    samples: firstArray(record, ['samples', 'members', 'items']).map(item => {
      const row = asRecord(item)
      return {
        user_id: toString(row.user_id ?? row.id ?? row.key),
        display_name: toString(row.display_name ?? row.name ?? row.nickname, '未命名用户'),
        tier: toString(row.tier ?? row.plan ?? row.level, ''),
        status: toString(row.status ?? row.state, ''),
        risk_level: toString(row.risk_level ?? row.risk, ''),
        last_active_at: toString(row.last_active_at ?? row.updated_at ?? row.created_at, ''),
        detail: toString(row.detail ?? row.subtitle ?? row.note, ''),
      }
    }),
  }
}

function normalizeOperatingRhythmPayload(raw: unknown): BiOperatingRhythmPayload | undefined {
  const record = asRecord(firstRecord(raw, ['operating_rhythm', 'operatingRhythm']))
  if (!Object.keys(record).length) return undefined
  return {
    cadences: firstArray(record, ['cadences', 'rhythms']).map((item, index) => {
      const cadence = asRecord(item)
      return {
        id: toString(cadence.id, `cadence-${index + 1}`),
        label: toString(cadence.label ?? cadence.name, `节奏 ${index + 1}`),
        focus: toString(cadence.focus ?? cadence.detail, ''),
      }
    }),
    topActions: firstArray(record, ['top_actions', 'topActions', 'actions']).map((item, index) => {
      const action = asRecord(item)
      return {
        title: toString(action.title ?? action.label, `动作 ${index + 1}`),
        target: toString(action.target ?? action.drilldown, ''),
        status: toString(action.status ?? action.state, ''),
        reason: toString(action.reason ?? action.detail, ''),
      }
    }),
  }
}

function normalizeTeachingEffectPayload(raw: unknown): BiTeachingEffectPayload | undefined {
  const record = asRecord(firstRecord(raw, ['teaching_effect', 'teachingEffect']))
  if (!Object.keys(record).length) return undefined
  return {
    status: toString(record.status, ''),
    summary: toString(record.summary ?? record.description, ''),
    chapterProgress: firstArray(record, ['chapter_progress', 'chapterProgress', 'chapters']).map(
      (item, index) => {
        const chapter = asRecord(item)
        return {
          chapterId: toString(
            chapter.chapter_id ?? chapter.chapterId ?? chapter.id,
            `chapter-${index + 1}`
          ),
          name: toString(chapter.name ?? chapter.label ?? chapter.title, `章节 ${index + 1}`),
          mastery: toNumber(chapter.mastery ?? chapter.score ?? chapter.value, 0),
          memberCount: toNumber(chapter.member_count ?? chapter.memberCount ?? chapter.members, 0),
          status: toString(chapter.status ?? chapter.state, ''),
          evidence: toString(chapter.evidence ?? chapter.detail ?? chapter.note, ''),
        }
      }
    ),
    metrics: firstArray(record, ['metrics', 'items']).map((item, index) => {
      const metric = asRecord(item)
      return {
        ...normalizeMetricDefinition(item, `教学指标 ${index + 1}`),
        value:
          metric.value === null
            ? null
            : typeof metric.value === 'number' || typeof metric.value === 'string'
              ? metric.value
              : undefined,
        status: toString(metric.status, ''),
      }
    }),
  }
}

function normalizeAiQualityPayload(raw: unknown): BiAiQualityPayload | undefined {
  const record = asRecord(firstRecord(raw, ['ai_quality', 'aiQuality']))
  if (!Object.keys(record).length) return undefined
  return {
    ...normalizeMetricDefinition(record, 'AI 教学质量分'),
    engineeringSuccessRate: toNumber(
      record.engineering_success_rate ?? record.engineeringSuccessRate,
      0
    ),
    failedTurns: toNumber(record.failed_turns ?? record.failedTurns, 0),
    totalTurns: toNumber(record.total_turns ?? record.totalTurns, 0),
    teachingSuccessStatus: toString(
      record.teaching_success_status ?? record.teachingSuccessStatus,
      ''
    ),
    note: toString(record.note ?? record.summary, ''),
    samples: firstArray(record, ['samples', 'items']).map(item => {
      const sample = asRecord(item)
      return {
        turn_id: toString(sample.turn_id ?? sample.turnId ?? sample.id, ''),
        session_id: toString(sample.session_id ?? sample.sessionId, ''),
        status: toString(sample.status, ''),
      }
    }),
  }
}

function normalizeUnitEconomicsPayload(raw: unknown): BiUnitEconomicsPayload | undefined {
  const record = asRecord(firstRecord(raw, ['unit_economics', 'unitEconomics']))
  if (!Object.keys(record).length) return undefined
  return {
    ...normalizeMetricDefinition(record, '单有效学习成本'),
    revenueStatus: toString(record.revenue_status ?? record.revenueStatus, ''),
    summary: toString(record.summary ?? record.description, ''),
    windowTotalCostUsd: toNumber(record.window_total_cost_usd ?? record.windowTotalCostUsd, 0),
    costPerEffectiveLearningUsd: toNumber(
      record.cost_per_effective_learning_usd ?? record.costPerEffectiveLearningUsd,
      0
    ),
    source: toString(record.source, ''),
  }
}

function normalizeDataTrustPayload(raw: unknown): BiDataTrustPayload | undefined {
  const record = asRecord(firstRecord(raw, ['data_trust', 'dataTrust']))
  if (!Object.keys(record).length) return undefined
  return {
    status: toString(record.status, ''),
    trustModel: toString(record.trust_model ?? record.trustModel, ''),
    degradedModules: firstArray(record, ['degraded_modules', 'degradedModules']).map(
      (item, index) => {
        const degradedModule = asRecord(item)
        return {
          id: toString(degradedModule.id, `module-${index + 1}`),
          label: toString(degradedModule.label ?? degradedModule.name, `模块 ${index + 1}`),
          status: toString(degradedModule.status, ''),
          detail: toString(degradedModule.detail ?? degradedModule.description, ''),
        }
      }
    ),
    metricDefinitions: firstArray(record, [
      'metric_definitions',
      'metricDefinitions',
      'metrics',
    ]).map((item, index) => normalizeMetricDefinition(item, `指标 ${index + 1}`)),
  }
}

function toBossTone(level: BiAlertItem['level']): BiMetricCard['tone'] {
  if (level === 'critical') return 'critical'
  if (level === 'warning') return 'warning'
  return 'neutral'
}

function normalizeBossActionSource(record: Record<string, unknown>): BiBossActionItem['source'] {
  const direct = record.source
  if (direct === 'anomalies' || direct === 'members' || direct === 'cost') {
    return direct
  }
  const bucket = toString(record.bucket, '')
  if (bucket === 'high_risk' || bucket === 'expiring_soon') {
    return 'members'
  }
  if (bucket === 'cost' || bucket === 'daily_cost') {
    return 'cost'
  }
  return 'anomalies'
}

function normalizeBossActionItem(item: unknown, fallbackLabel = ''): BiBossActionItem {
  const record = asRecord(item)
  const handoffRecord = asRecord(record.handoff_filters ?? record.handoffFilters)
  const handoffFilters: Record<string, string | number | boolean | null> = {}

  Object.entries(handoffRecord).forEach(([key, value]) => {
    if (
      typeof value === 'string' ||
      typeof value === 'number' ||
      typeof value === 'boolean' ||
      value === null
    ) {
      handoffFilters[key] = value
    }
  })

  return {
    title: toString(record.title ?? record.label ?? record.name ?? record.bucket, fallbackLabel),
    detail: toString(record.detail ?? record.description ?? record.hint ?? record.note, ''),
    tone:
      record.tone === 'good' || record.tone === 'warning' || record.tone === 'critical'
        ? (record.tone as BiMetricCard['tone'])
        : 'neutral',
    source: normalizeBossActionSource(record),
    handoffFilters: Object.keys(handoffFilters).length ? handoffFilters : undefined,
  }
}

function normalizeBossDailyCost(raw: unknown): BiBossDailyCost | undefined {
  const record = asRecord(firstRecord(raw, ['daily_cost', 'dailyCost', 'cost_daily']))
  const hasDailyCost =
    Object.keys(record).length > 0 &&
    ('today_usd' in record ||
      'todayUsd' in record ||
      'window_total_usd' in record ||
      'series' in record)
  if (!hasDailyCost) {
    return undefined
  }
  const series = firstArray(record, ['series', 'points', 'items']).map((item, index) => {
    const point = asRecord(item)
    return {
      date: toString(point.date ?? point.day ?? point.label, ''),
      label: toString(point.label ?? point.date ?? point.day, `Day ${index + 1}`),
      costUsd: toNumber(point.cost_usd ?? point.costUsd ?? point.cost ?? point.amount, 0),
      tokens: toNumber(point.tokens ?? point.total_tokens ?? point.totalTokens, 0),
      turns: toNumber(point.turns ?? point.count ?? point.requests, 0),
    }
  })
  return {
    todayUsd: toNumber(record.today_usd ?? record.todayUsd ?? record.today ?? record.cost_today, 0),
    windowTotalUsd: toNumber(
      record.window_total_usd ?? record.windowTotalUsd ?? record.total_usd ?? record.total,
      0
    ),
    averageDailyUsd: toNumber(
      record.average_daily_usd ?? record.averageDailyUsd ?? record.avg_daily_usd ?? record.average,
      0
    ),
    source: toString(record.source ?? record.provider, ''),
    series,
  }
}

function normalizeBossWorkbench(raw: unknown, fallbackHeroIssue = ''): BiBossWorkbench | undefined {
  const record = asRecord(firstRecord(raw, ['boss_workbench', 'boss', 'workbench']))
  const hasBossPayload =
    Object.keys(record).length > 0 &&
    ('kpis' in record || 'risk_queue' in record || 'hero_issue' in record)
  if (!hasBossPayload) {
    return undefined
  }

  return {
    kpis: firstArray(record, ['kpis', 'cards', 'metrics']).map((item, index) =>
      normalizeMetricCard(item, `老板 KPI ${index + 1}`)
    ),
    actionQueue: firstArray(record, ['risk_queue', 'actionQueue', 'action_queue', 'queue']).map(
      (item, index) => normalizeBossActionItem(item, `待办 ${index + 1}`)
    ),
    heroIssue: toString(record.hero_issue ?? record.heroIssue ?? record.issue, fallbackHeroIssue),
    dailyCost: normalizeBossDailyCost(record),
  }
}

function normalizeTutorBot(item: unknown, fallbackLabel = ''): BiTutorBotItem {
  const record = asRecord(item)
  return {
    bot_id: toString(record.bot_id ?? record.id ?? record.key, fallbackLabel),
    name: toString(record.name ?? record.title ?? record.label, fallbackLabel),
    capability: toString(record.capability ?? record.mode, ''),
    entrypoint: toString(record.entrypoint ?? record.source ?? record.channel, ''),
    tier: toString(record.tier ?? record.plan ?? record.level, ''),
    status: toString(record.status ?? record.state ?? record.running_state, ''),
    last_active_at: toString(record.last_active_at ?? record.updated_at ?? record.last_seen_at, ''),
    recent_message: toString(
      record.recent_message ?? record.message_preview ?? record.preview ?? record.detail,
      ''
    ),
    runs: optionalNumber(record.runs ?? record.run_count ?? record.count),
    success_rate: optionalNumber(record.success_rate ?? record.success ?? record.rate),
    detail: toString(record.detail ?? record.description ?? record.note, ''),
  }
}

function buildBiUrl(
  path: string,
  params?: Record<string, string | number | boolean | undefined>
): string {
  const url = new URL(apiUrl(path))
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    url.searchParams.set(key, String(value))
  })
  return url.toString()
}

async function fetchBiJson(
  path: string,
  params?: Record<string, string | number | boolean | undefined>
): Promise<unknown> {
  const response = await fetch(buildBiUrl(path, params), {
    cache: 'no-store',
    headers: withAdminAuthorization(BI_API_TOKEN ? withBiApiToken() : undefined),
  })
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${path}`)
  }
  return response.json()
}

function normalizeLearnerProfile(raw: unknown): BiMetricCard[] {
  return firstArray(raw, ['profile', 'summary', 'cards', 'metrics', 'kpis']).map((item, index) =>
    normalizeMetricCard(item, `画像 ${index + 1}`)
  )
}

function normalizeLearnerSessions(raw: unknown): BiLearnerSession[] {
  return firstArray(raw, [
    'recent_sessions',
    'sessions',
    'conversation_history',
    'history',
    'items',
  ]).map((item, index) => {
    const record = asRecord(item)
    return {
      session_id: toString(record.session_id ?? record.id ?? record.key, `session-${index + 1}`),
      title: toString(
        record.title ?? record.name ?? record.topic ?? record.summary,
        `会话 ${index + 1}`
      ),
      capability: toString(record.capability ?? record.mode, ''),
      status: toString(record.status ?? record.state, ''),
      started_at: toString(record.started_at ?? record.start_at ?? record.created_at, ''),
      ended_at: toString(record.ended_at ?? record.end_at ?? record.updated_at, ''),
      duration_minutes: optionalNumber(
        record.duration_minutes ?? record.duration_min ?? record.minutes
      ),
      summary: toString(record.summary ?? record.detail ?? record.note, ''),
    }
  })
}

function normalizeLearnerMastery(raw: unknown): BiLearnerChapterMastery[] {
  return firstArray(raw, ['chapter_mastery', 'mastery', 'chapters', 'items']).map((item, index) => {
    const record = asRecord(item)
    return {
      chapter_id: toString(record.chapter_id ?? record.id ?? record.key, ''),
      name: toString(
        record.name ?? record.title ?? record.chapter ?? record.label,
        `章节 ${index + 1}`
      ),
      mastery: toFiniteNumber(record.mastery ?? record.score ?? record.rate ?? record.value, 0),
      hint: toString(record.hint ?? record.description ?? record.note, ''),
      evidence: toString(record.evidence ?? record.example ?? record.detail, ''),
    }
  })
}

function normalizeLearnerNotes(raw: unknown): BiLearnerNoteLedgerSummary {
  const record = asRecord(
    firstRecord(raw, ['notes_summary', 'summary', 'ledger', 'wallet', 'data'])
  )
  return {
    notes_count: optionalNumber(record.notes_count ?? record.note_count ?? record.total_notes),
    pinned_notes_count: optionalNumber(record.pinned_notes_count ?? record.pinned_count),
    recent_note: toString(record.recent_note ?? record.latest_note ?? record.note_preview, ''),
    recent_ledger: toString(
      record.recent_ledger ?? record.latest_ledger ?? record.ledger_preview,
      ''
    ),
    wallet_balance: optionalNumber(
      record.wallet_balance ?? record.balance ?? record.points_balance
    ),
    ledger_delta: optionalNumber(record.ledger_delta ?? record.delta),
    summary: toString(record.summary ?? record.detail ?? record.note, ''),
  }
}

const BOSS_ACTION_COPY = {
  anomalyDetail: '建议尽快复核该异常信号。',
  memberRiskDetail: '建议跟进高风险会员变化。',
  costDetail: '建议持续观察成本波动。',
} as const

function buildBossKpis(data: BiWorkbenchData): BiBossKpiItem[] {
  const kpis: BiBossKpiItem[] = []
  const seen = new Set<string>()

  const append = (items: BiMetricCard[], source: BiBossKpiItem['source']) => {
    for (const item of items) {
      const label = item.label.trim()
      if (!label || seen.has(label)) continue
      seen.add(label)
      kpis.push({ ...item, source })
      if (kpis.length >= 5) return
    }
  }

  append(data.overview.cards, 'overview')
  if (kpis.length < 5) append(data.members.cards, 'members')
  if (kpis.length < 5) append(data.cost.cards, 'cost')

  return kpis
}

function buildBossActionQueue(data: BiWorkbenchData): BiBossActionItem[] {
  const queue: BiBossActionItem[] = []
  const seen = new Set<string>()

  const append = (
    title: string,
    detail: string,
    tone: BiMetricCard['tone'],
    source: BiBossActionItem['source']
  ) => {
    const key = `${title}::${detail}`
    if (!title || seen.has(key)) return
    seen.add(key)
    queue.push({ title, detail, tone, source })
  }

  for (const item of data.anomalies.items) {
    append(
      item.title,
      item.detail || BOSS_ACTION_COPY.anomalyDetail,
      toBossTone(item.level),
      'anomalies'
    )
    if (queue.length >= 4) break
  }

  if (queue.length < 4) {
    for (const item of data.members.risks) {
      append(
        `会员风险：${item.label}`,
        item.hint || item.secondary || BOSS_ACTION_COPY.memberRiskDetail,
        'warning',
        'members'
      )
      if (queue.length >= 4) break
    }
  }

  if (queue.length < 4) {
    for (const item of data.cost.cards) {
      append(
        `成本关注：${item.label}`,
        item.hint || item.delta || BOSS_ACTION_COPY.costDetail,
        item.tone ?? 'neutral',
        'cost'
      )
      if (queue.length >= 4) break
    }
  }

  return queue
}

function buildBossDailyCost(data: BiWorkbenchData): BiBossDailyCost {
  const series = data.trend.points.map(point => ({
    date: point.label,
    label: point.label,
    costUsd: point.cost,
    tokens: 0,
    turns: point.successful,
  }))
  const windowTotalUsd = series.reduce((sum, point) => sum + point.costUsd, 0)
  return {
    todayUsd: series.length ? series[series.length - 1].costUsd : 0,
    windowTotalUsd,
    averageDailyUsd: series.length ? windowTotalUsd / series.length : 0,
    source: 'active_trend_fallback',
    series,
  }
}

function buildBossHeroIssue(missingCoreModules: BiBossCoreModule[]): string {
  if (missingCoreModules.length === 0) {
    return ''
  }

  const scope = missingCoreModules.length === 1 ? '1 个' : `${missingCoreModules.length} 个`
  return `有 ${scope}核心经营模块暂未返回，老板首页先基于已成功模块装配。`
}

function buildBiBossWorkbench(
  data: BiWorkbenchData,
  missingCoreModules: BiBossCoreModule[]
): BiBossWorkbench {
  return {
    kpis: buildBossKpis(data),
    actionQueue: buildBossActionQueue(data),
    heroIssue: buildBossHeroIssue(missingCoreModules),
    dailyCost: buildBossDailyCost(data),
  }
}

type BiOverviewBundle = {
  overview: BiOverviewData
  bossWorkbench?: BiBossWorkbench
}

function parseBiOverviewBundle(raw: unknown): BiOverviewBundle {
  const record = asRecord(firstRecord(raw, ['overview', 'data', 'summary']))
  const cards = firstArray(raw, ['cards', 'kpis', 'metrics']).map((item, index) =>
    normalizeMetricCard(item, `KPI ${index + 1}`)
  )
  const highlights = firstArray(raw, ['highlights', 'recommendations', 'insights', 'summary']).map(
    item => toString(item)
  )
  const entrypoints = firstArray(raw, ['entrypoints', 'channels', 'sources']).map((item, index) =>
    normalizeRankItem(item, `入口 ${index + 1}`)
  )
  const alerts = firstArray(raw, ['alerts', 'warnings', 'anomalies']).map((item, index) =>
    normalizeAlert(item, `告警 ${index + 1}`)
  )
  const overview: BiOverviewData = {
    title: toString(record.title ?? record.name, BI_WORKBENCH_TITLE),
    subtitle: toString(
      record.subtitle ?? record.description ?? record.summary,
      '加载后端 BI 接口后即可查看经营、学习、能力、知识库与会员的统一视图。'
    ),
    cards,
    highlights,
    entrypoints,
    alerts,
    northStar: normalizeNorthStarPayload(raw),
    growthFunnel: normalizeGrowthFunnelPayload(raw),
    memberHealth: normalizeMemberHealthPayload(raw),
    operatingRhythm: normalizeOperatingRhythmPayload(raw),
    teachingEffect: normalizeTeachingEffectPayload(raw),
    aiQuality: normalizeAiQualityPayload(raw),
    unitEconomics: normalizeUnitEconomicsPayload(raw),
    dataTrust: normalizeDataTrustPayload(raw),
  }

  return {
    overview,
    bossWorkbench: normalizeBossWorkbench(raw),
  }
}

export async function getBiOverview(options: BiFetchOptions = {}): Promise<BiOverviewData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/overview', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  return parseBiOverviewBundle(raw).overview
}

export async function getBiActiveTrend(options: BiFetchOptions = {}): Promise<BiTrendData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/active-trend', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  const points = firstArray(raw, ['points', 'series', 'items', 'trend']).map((item, index) =>
    normalizeTrendPoint(item, `Day ${index + 1}`)
  )
  return { points }
}

export async function getBiRetention(options: BiFetchOptions = {}): Promise<BiRetentionData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/retention', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  const record = asRecord(firstRecord(raw, ['retention', 'data', 'summary']))
  const cohorts = firstArray(raw, ['cohorts', 'rows', 'items', 'matrix']).map((item, index) =>
    normalizeCohort(item, `Cohort ${index + 1}`)
  )
  const labels =
    firstArray(raw, ['labels', 'columns', 'days', 'periods']).map(item => toString(item)) || []

  return {
    cohorts,
    labels: labels.length
      ? labels
      : toArray(record.labels)
          .map(item => toString(item))
          .filter(Boolean),
  }
}

export async function getBiCapabilities(options: BiFetchOptions = {}): Promise<BiCapabilityData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/capabilities', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  return {
    items: firstArray(raw, ['items', 'capabilities', 'rows', 'series']).map((item, index) =>
      normalizeRankItem(item, `Capability ${index + 1}`)
    ),
    upgradePaths: firstArray(raw, ['upgrade_paths', 'paths', 'funnels', 'conversions']).map(
      (item, index) => normalizeRankItem(item, `Path ${index + 1}`)
    ),
  }
}

export async function getBiTools(options: BiFetchOptions = {}): Promise<BiToolData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/tools', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  return {
    items: firstArray(raw, ['items', 'tools', 'rows', 'series']).map((item, index) =>
      normalizeRankItem(item, `Tool ${index + 1}`)
    ),
    efficiency: firstArray(raw, ['efficiency', 'quadrants', 'value_lines', 'roi']).map(
      (item, index) => normalizeRankItem(item, `Efficiency ${index + 1}`)
    ),
  }
}

export async function getBiKnowledge(options: BiFetchOptions = {}): Promise<BiKnowledgeData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/knowledge', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  const record = asRecord(firstRecord(raw, ['knowledge', 'data', 'summary']))
  return {
    items: firstArray(raw, ['items', 'kbs', 'knowledge_bases', 'rows']).map((item, index) =>
      normalizeRankItem(item, `KB ${index + 1}`)
    ),
    topQueries: firstArray(raw, ['top_queries', 'queries', 'hot_queries', 'items']).map(
      (item, index) => normalizeRankItem(item, `Query ${index + 1}`)
    ),
    zeroHitRate: optionalNumber(record.zero_hit_rate ?? record.zero_result_rate),
  }
}

export async function getBiMembers(options: BiFetchOptions = {}): Promise<BiMemberData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/members', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  const samples = firstArray(raw, ['samples', 'items', 'recent', 'list']).map(item => {
    const row = asRecord(item)
    return {
      user_id: toString(row.user_id ?? row.id ?? row.key),
      display_name: toString(row.display_name ?? row.name ?? row.nickname, '未命名用户'),
      tier: toString(row.tier ?? row.plan ?? row.level, ''),
      status: toString(row.status ?? row.state, ''),
      risk_level: toString(row.risk_level ?? row.risk, ''),
      last_active_at: toString(row.last_active_at ?? row.updated_at ?? row.created_at, ''),
      detail: toString(row.detail ?? row.subtitle ?? row.note, ''),
    }
  })

  return {
    cards: firstArray(raw, ['cards', 'metrics', 'kpis']).map((item, index) =>
      normalizeMetricCard(item, `Member KPI ${index + 1}`)
    ),
    tiers: firstArray(raw, ['tiers', 'tier_breakdown', 'segments']).map((item, index) =>
      normalizeRankItem(item, `Tier ${index + 1}`)
    ),
    risks: firstArray(raw, ['risks', 'risk_breakdown', 'risk_levels']).map((item, index) =>
      normalizeRankItem(item, `Risk ${index + 1}`)
    ),
    samples,
  }
}

export async function getBiCost(options: BiFetchOptions = {}): Promise<BiCostData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/cost', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  return {
    cards: firstArray(raw, ['cards', 'metrics', 'kpis']).map((item, index) =>
      normalizeMetricCard(item, `Cost KPI ${index + 1}`)
    ),
    models: firstArray(raw, ['models', 'model_breakdown', 'providers']).map((item, index) =>
      normalizeRankItem(item, `Model ${index + 1}`)
    ),
    providers: firstArray(raw, ['providers', 'sources', 'usage_sources']).map((item, index) =>
      normalizeRankItem(item, `Provider ${index + 1}`)
    ),
  }
}

export async function getBiTutorBots(options: BiFetchOptions = {}): Promise<BiTutorBotData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/tutorbots', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )

  return {
    cards: firstArray(raw, ['cards', 'metrics', 'kpis']).map((item, index) =>
      normalizeMetricCard(item, `TutorBot KPI ${index + 1}`)
    ),
    ranking: firstArray(raw, ['ranking', 'items', 'bots', 'rows', 'series']).map((item, index) =>
      normalizeRankItem(item, `Bot ${index + 1}`)
    ),
    statusBreakdown: firstArray(raw, [
      'status_breakdown',
      'status',
      'states',
      'running_status',
    ]).map((item, index) => normalizeRankItem(item, `状态 ${index + 1}`)),
    recentActive: firstArray(raw, ['recent_active', 'active', 'samples', 'recent', 'list']).map(
      (item, index) => normalizeTutorBot(item, `Bot ${index + 1}`)
    ),
    recentMessages: firstArray(raw, [
      'recent_messages',
      'messages',
      'message_previews',
      'previews',
    ]).map((item, index) => normalizeTutorBot(item, `Message ${index + 1}`)),
  }
}

export async function getBiAnomalies(options: BiFetchOptions = {}): Promise<BiAnomalyData> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/anomalies', {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    })
  )
  return {
    items: firstArray(raw, ['items', 'alerts', 'warnings', 'anomalies']).map((item, index) =>
      normalizeAlert(item, `异常 ${index + 1}`)
    ),
  }
}

export async function getBiCommerce(options: { limit?: number } = {}): Promise<BiCommerceData> {
  const raw = unwrapPayload(await fetchBiJson('/api/v1/bi/commerce', { limit: options.limit }))
  const record = asRecord(raw)
  const summary = asRecord(record.summary)
  const authority = asRecord(record.authority)
  return {
    status: toString(record.status, ''),
    summary: {
      memberCount: toNumber(summary.member_count ?? summary.memberCount, 0),
      packageCount: toNumber(summary.package_count ?? summary.packageCount, 0),
      rechargeCount: toNumber(summary.recharge_count ?? summary.rechargeCount, 0),
      ledgerCount: toNumber(summary.ledger_count ?? summary.ledgerCount, 0),
      anomalyCount: toNumber(summary.anomaly_count ?? summary.anomalyCount, 0),
      creditPoints: toNumber(summary.credit_points ?? summary.creditPoints, 0),
      debitPoints: toNumber(summary.debit_points ?? summary.debitPoints, 0),
    },
    authority: Object.fromEntries(
      Object.entries(authority).map(([key, value]) => [key, toString(value, '')])
    ),
    packages: firstArray(raw, ['packages', 'package_items']).map(item =>
      normalizeCommercePackage(item)
    ),
    rechargeRecords: firstArray(raw, ['recharge_records', 'rechargeRecords', 'orders']).map(item =>
      normalizeCommerceRechargeRecord(item)
    ),
    ledger: firstArray(raw, ['ledger', 'wallet_ledger', 'walletLedger']).map(item =>
      normalizeCommerceLedgerRow(item)
    ),
    anomalies: firstArray(raw, ['anomalies', 'alerts', 'warnings']).map(item =>
      normalizeCommerceAnomaly(item)
    ),
    warnings: firstArray(raw, ['warnings', 'notes'])
      .map(item => toString(item))
      .filter(Boolean),
  }
}

export async function getBiInviteTestStats(
  options: Pick<BiFetchOptions, 'days'> = {}
): Promise<BiInviteTestStats> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/invite-test/stats', { days: options.days })
  )
  const record = asRecord(raw)
  const summary = asRecord(record.summary)
  return {
    window_days: toNumber(record.window_days ?? record.windowDays, options.days ?? 365),
    storage_status: toString(record.storage_status ?? record.storageStatus, ''),
    summary: {
      total_applications: toNumber(summary.total_applications ?? summary.totalApplications, 0),
      unique_contacts: toNumber(summary.unique_contacts ?? summary.uniqueContacts, 0),
      accept_interview_count: toNumber(
        summary.accept_interview_count ?? summary.acceptInterviewCount,
        0
      ),
      accept_interview_rate: toNumber(
        summary.accept_interview_rate ?? summary.acceptInterviewRate,
        0
      ),
      with_wrong_question_count: toNumber(
        summary.with_wrong_question_count ?? summary.withWrongQuestionCount,
        0
      ),
      with_wrong_question_rate: toNumber(
        summary.with_wrong_question_rate ?? summary.withWrongQuestionRate,
        0
      ),
      consented_count: toNumber(summary.consented_count ?? summary.consentedCount, 0),
    },
    status_breakdown: normalizeCountRows(
      raw,
      ['status_breakdown', 'statusBreakdown'],
      'status'
    ) as BiInviteTestStats['status_breakdown'],
    source_breakdown: normalizeCountRows(
      raw,
      ['source_breakdown', 'sourceBreakdown'],
      'source_page'
    ) as BiInviteTestStats['source_breakdown'],
    exam_type_breakdown: normalizeCountRows(
      raw,
      ['exam_type_breakdown', 'examTypeBreakdown'],
      'exam_type'
    ) as BiInviteTestStats['exam_type_breakdown'],
    exam_stage_breakdown: normalizeCountRows(
      raw,
      ['exam_stage_breakdown', 'examStageBreakdown'],
      'exam_stage'
    ) as BiInviteTestStats['exam_stage_breakdown'],
    pain_point_breakdown: normalizeCountRows(
      raw,
      ['pain_point_breakdown', 'painPointBreakdown'],
      'pain_point'
    ) as BiInviteTestStats['pain_point_breakdown'],
    weekly_time_breakdown: normalizeCountRows(
      raw,
      ['weekly_time_breakdown', 'weeklyTimeBreakdown'],
      'weekly_time'
    ) as BiInviteTestStats['weekly_time_breakdown'],
    age_range_breakdown: normalizeCountRows(
      raw,
      ['age_range_breakdown', 'ageRangeBreakdown'],
      'age_range'
    ) as BiInviteTestStats['age_range_breakdown'],
    province_breakdown: normalizeCountRows(
      raw,
      ['province_breakdown', 'provinceBreakdown'],
      'province'
    ) as BiInviteTestStats['province_breakdown'],
    education_breakdown: normalizeCountRows(
      raw,
      ['education_breakdown', 'educationBreakdown'],
      'education'
    ) as BiInviteTestStats['education_breakdown'],
    occupation_breakdown: normalizeCountRows(
      raw,
      ['occupation_breakdown', 'occupationBreakdown'],
      'occupation'
    ) as BiInviteTestStats['occupation_breakdown'],
    preparation_years_breakdown: normalizeCountRows(
      raw,
      ['preparation_years_breakdown', 'preparationYearsBreakdown'],
      'preparation_years'
    ) as BiInviteTestStats['preparation_years_breakdown'],
    knowledge_foundation_breakdown: normalizeCountRows(
      raw,
      ['knowledge_foundation_breakdown', 'knowledgeFoundationBreakdown'],
      'knowledge_foundation'
    ) as BiInviteTestStats['knowledge_foundation_breakdown'],
    daily_study_time_breakdown: normalizeCountRows(
      raw,
      ['daily_study_time_breakdown', 'dailyStudyTimeBreakdown'],
      'daily_study_time'
    ) as BiInviteTestStats['daily_study_time_breakdown'],
  }
}

export async function getBiInviteTestApplications(
  options: {
    days?: number
    limit?: number
    status?: string
    source_page?: string
    q?: string
  } = {}
): Promise<BiInviteTestApplicationsResponse> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/invite-test/applications', {
      days: options.days,
      limit: options.limit,
      status: options.status,
      source_page: options.source_page,
      q: options.q,
    })
  )
  const record = asRecord(raw)
  return {
    window_days: toNumber(record.window_days ?? record.windowDays, options.days ?? 365),
    storage_status: toString(record.storage_status ?? record.storageStatus, ''),
    total: toNumber(record.total, 0),
    contact_revealed: record.contact_revealed === true || record.contactRevealed === true,
    items: firstArray(raw, ['items', 'applications', 'rows', 'list']).map(item =>
      normalizeInviteTestApplication(item)
    ),
  }
}

export async function getBiLubanFeedbackStats(
  options: Pick<BiFetchOptions, 'days'> = {}
): Promise<BiLubanFeedbackStats> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/luban-feedback/stats', { days: options.days })
  )
  const record = asRecord(raw)
  const summary = asRecord(record.summary)
  return {
    window_days: toNumber(record.window_days ?? record.windowDays, options.days ?? 365),
    storage_status: toString(record.storage_status ?? record.storageStatus, ''),
    summary: {
      total_responses: toNumber(summary.total_responses ?? summary.totalResponses, 0),
      nps_score: toNumber(summary.nps_score ?? summary.npsScore, 0),
      nps_base: toNumber(summary.nps_base ?? summary.npsBase, 0),
      promoters: toNumber(summary.promoters, 0),
      passives: toNumber(summary.passives, 0),
      detractors: toNumber(summary.detractors, 0),
      avg_satisfaction: toNumber(summary.avg_satisfaction ?? summary.avgSatisfaction, 0),
      satisfaction_base: toNumber(summary.satisfaction_base ?? summary.satisfactionBase, 0),
      revisit_willing_count: toNumber(
        summary.revisit_willing_count ?? summary.revisitWillingCount,
        0
      ),
      revisit_willing_rate: toNumber(summary.revisit_willing_rate ?? summary.revisitWillingRate, 0),
      with_contact_count: toNumber(summary.with_contact_count ?? summary.withContactCount, 0),
      with_contact_rate: toNumber(summary.with_contact_rate ?? summary.withContactRate, 0),
    },
    nps_breakdown: normalizeCountRows(
      raw,
      ['nps_breakdown', 'npsBreakdown'],
      'nps'
    ) as BiLubanFeedbackStats['nps_breakdown'],
    satisfaction_breakdown: normalizeCountRows(
      raw,
      ['satisfaction_breakdown', 'satisfactionBreakdown'],
      'overall_satisfaction'
    ) as BiLubanFeedbackStats['satisfaction_breakdown'],
    most_valuable_breakdown: normalizeCountRows(
      raw,
      ['most_valuable_breakdown', 'mostValuableBreakdown'],
      'most_valuable'
    ) as BiLubanFeedbackStats['most_valuable_breakdown'],
    will_continue_breakdown: normalizeCountRows(
      raw,
      ['will_continue_breakdown', 'willContinueBreakdown'],
      'will_continue'
    ) as BiLubanFeedbackStats['will_continue_breakdown'],
    pay_willingness_breakdown: normalizeCountRows(
      raw,
      ['pay_willingness_breakdown', 'payWillingnessBreakdown'],
      'pay_willingness'
    ) as BiLubanFeedbackStats['pay_willingness_breakdown'],
    revisit_willingness_breakdown: normalizeCountRows(
      raw,
      ['revisit_willingness_breakdown', 'revisitWillingnessBreakdown'],
      'revisit_willingness'
    ) as BiLubanFeedbackStats['revisit_willingness_breakdown'],
    attempt_count_breakdown: normalizeCountRows(
      raw,
      ['attempt_count_breakdown', 'attemptCountBreakdown'],
      'attempt_count'
    ) as BiLubanFeedbackStats['attempt_count_breakdown'],
    exam_timeframe_breakdown: normalizeCountRows(
      raw,
      ['exam_timeframe_breakdown', 'examTimeframeBreakdown'],
      'exam_timeframe'
    ) as BiLubanFeedbackStats['exam_timeframe_breakdown'],
    status_breakdown: normalizeCountRows(
      raw,
      ['status_breakdown', 'statusBreakdown'],
      'status'
    ) as BiLubanFeedbackStats['status_breakdown'],
    source_breakdown: normalizeCountRows(
      raw,
      ['source_breakdown', 'sourceBreakdown'],
      'source_page'
    ) as BiLubanFeedbackStats['source_breakdown'],
  }
}

export async function getBiLubanFeedbackResponses(
  options: {
    days?: number
    limit?: number
    status?: string
    source_page?: string
    q?: string
  } = {}
): Promise<BiLubanFeedbackResponsesResponse> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/luban-feedback/responses', {
      days: options.days,
      limit: options.limit,
      status: options.status,
      source_page: options.source_page,
      q: options.q,
    })
  )
  const record = asRecord(raw)
  return {
    window_days: toNumber(record.window_days ?? record.windowDays, options.days ?? 365),
    storage_status: toString(record.storage_status ?? record.storageStatus, ''),
    total: toNumber(record.total, 0),
    contact_revealed: record.contact_revealed === true || record.contactRevealed === true,
    items: firstArray(raw, ['items', 'responses', 'rows', 'list']).map(item =>
      normalizeLubanFeedbackResponse(item)
    ),
  }
}

export async function getBiFeedback(
  options: { days?: number; limit?: number } = {}
): Promise<BiFeedbackPayload> {
  const raw = unwrapPayload(
    await fetchBiJson('/api/v1/bi/feedback', {
      days: options.days ?? 30,
      limit: options.limit ?? 50,
    })
  )
  const record = asRecord(raw)
  const summary = asRecord(record.summary)
  return {
    window_days: toFiniteNumber(record.window_days ?? record.windowDays, options.days ?? 30),
    storage_status: toString(record.storage_status ?? record.storageStatus, 'unknown'),
    summary: {
      total_feedback: toFiniteNumber(summary.total_feedback ?? summary.totalFeedback, 0),
      thumbs_up: toFiniteNumber(summary.thumbs_up ?? summary.thumbsUp, 0),
      thumbs_down: toFiniteNumber(summary.thumbs_down ?? summary.thumbsDown, 0),
      neutral: toFiniteNumber(summary.neutral, 0),
      commented: toFiniteNumber(summary.commented, 0),
      unique_users: toFiniteNumber(summary.unique_users ?? summary.uniqueUsers, 0),
      unique_sessions: toFiniteNumber(summary.unique_sessions ?? summary.uniqueSessions, 0),
      unique_messages: toFiniteNumber(summary.unique_messages ?? summary.uniqueMessages, 0),
    },
    rating_breakdown: firstArray(record, ['rating_breakdown', 'ratingBreakdown']).map(item => {
      const itemRecord = asRecord(item)
      return {
        rating: toFiniteNumber(itemRecord.rating, 0),
        label: toString(itemRecord.label, ''),
        count: toFiniteNumber(itemRecord.count, 0),
      }
    }),
    top_reason_tags: firstArray(record, ['top_reason_tags', 'topReasonTags']).map(item => {
      const itemRecord = asRecord(item)
      return {
        tag: toString(itemRecord.tag, ''),
        count: toFiniteNumber(itemRecord.count, 0),
      }
    }),
    answer_modes: firstArray(record, ['answer_modes', 'answerModes']).map(item => {
      const itemRecord = asRecord(item)
      return {
        answer_mode: toString(itemRecord.answer_mode ?? itemRecord.answerMode, ''),
        count: toFiniteNumber(itemRecord.count, 0),
      }
    }),
    recent: firstArray(record, ['recent', 'items', 'records']).map((item, index) => {
      const itemRecord = asRecord(item)
      return {
        feedback_id: toString(itemRecord.feedback_id ?? itemRecord.feedbackId, ''),
        id: toString(itemRecord.id, `feedback-${index + 1}`),
        user_id: toString(itemRecord.user_id ?? itemRecord.userId, ''),
        session_id: toString(itemRecord.session_id ?? itemRecord.sessionId, ''),
        message_id: toString(itemRecord.message_id ?? itemRecord.messageId, ''),
        rating: toFiniteNumber(itemRecord.rating, 0),
        reason_tags: toArray(itemRecord.reason_tags ?? itemRecord.reasonTags)
          .map(value => toString(value))
          .filter(Boolean),
        comment: toString(itemRecord.comment, ''),
        feedback_source: toString(itemRecord.feedback_source ?? itemRecord.feedbackSource, ''),
        answer_mode: toString(itemRecord.answer_mode ?? itemRecord.answerMode, ''),
        requested_response_mode: toString(
          itemRecord.requested_response_mode ?? itemRecord.requestedResponseMode,
          ''
        ),
        effective_response_mode: toString(
          itemRecord.effective_response_mode ?? itemRecord.effectiveResponseMode,
          ''
        ),
        response_mode_degrade_reason: toString(
          itemRecord.response_mode_degrade_reason ?? itemRecord.responseModeDegradeReason,
          ''
        ),
        triage_status: toString(itemRecord.triage_status ?? itemRecord.triageStatus, ''),
        triage_operator: toString(itemRecord.triage_operator ?? itemRecord.triageOperator, ''),
        triage_note: toString(itemRecord.triage_note ?? itemRecord.triageNote, ''),
        triage_updated_at: toString(itemRecord.triage_updated_at ?? itemRecord.triageUpdatedAt, ''),
        problem_type: toString(itemRecord.problem_type ?? itemRecord.problemType, ''),
        symptom_tags: toArray(itemRecord.symptom_tags ?? itemRecord.symptomTags)
          .map(value => toString(value))
          .filter(Boolean),
        attachment_count: toFiniteNumber(
          itemRecord.attachment_count ?? itemRecord.attachmentCount,
          0
        ),
        attachments: toArray(itemRecord.attachments).map(attachment => {
          const attachmentRecord = asRecord(attachment)
          return {
            id: toString(
              attachmentRecord.id ??
                attachmentRecord.attachment_id ??
                attachmentRecord.attachmentId,
              ''
            ),
            kind: toString(attachmentRecord.kind ?? attachmentRecord.fileType, ''),
            filename: toString(attachmentRecord.filename ?? attachmentRecord.name, ''),
            mime_type: toString(attachmentRecord.mime_type ?? attachmentRecord.mimeType, ''),
            size: toFiniteNumber(attachmentRecord.size, 0),
            url: toString(attachmentRecord.url, ''),
            temp_path: toString(attachmentRecord.temp_path ?? attachmentRecord.tempFilePath, ''),
          }
        }),
        context_snapshot: (() => {
          const context = asRecord(itemRecord.context_snapshot ?? itemRecord.contextSnapshot)
          return {
            route: toString(context.route, ''),
            network_type: toString(context.network_type ?? context.networkType, ''),
            device_model: toString(context.device_model ?? context.deviceModel, ''),
            platform: toString(context.platform, ''),
            system: toString(context.system, ''),
            wechat_version: toString(context.wechat_version ?? context.wechatVersion, ''),
          }
        })(),
        created_at: toString(itemRecord.created_at ?? itemRecord.createdAt, ''),
      }
    }),
  }
}

export async function getBiLaunchReadiness(): Promise<BiLaunchReadinessDashboard> {
  const raw = unwrapPayload(await fetchBiJson('/api/v1/observability/launch-readiness'))
  const record = asRecord(raw)
  const release = asRecord(record.release)
  const sourceRuns = asRecord(record.source_runs ?? record.sourceRuns)
  return {
    run_id: toString(record.run_id ?? record.runId, ''),
    generated_at: toString(record.generated_at ?? record.generatedAt, ''),
    final_status: toString(record.final_status ?? record.finalStatus, 'NOT_RUN'),
    recommendation: toString(record.recommendation, 'hold'),
    release: {
      release_id: toString(release.release_id ?? release.releaseId, ''),
      git_sha: toString(release.git_sha ?? release.gitSha, ''),
      deployment_environment: toString(
        release.deployment_environment ?? release.deploymentEnvironment,
        ''
      ),
    },
    rows: firstArray(raw, ['rows', 'checks', 'items']).map(item =>
      normalizeLaunchReadinessRow(item)
    ),
    blockers: toArray(record.blockers)
      .map(value => toString(value))
      .filter(Boolean),
    source_runs: Object.fromEntries(
      Object.entries(sourceRuns).map(([key, value]) => [
        key,
        value === undefined ? undefined : toString(value),
      ])
    ),
  }
}

export async function getBiLearnerDetail(
  userId: string,
  options: BiFetchOptions = {}
): Promise<BiLearnerDetailData> {
  const raw = unwrapPayload(
    await fetchBiJson(`/api/v1/bi/learner/${encodeURIComponent(userId)}`, { days: options.days })
  )
  const record = asRecord(firstRecord(raw, ['learner', 'data', 'detail', 'profile', 'summary']))
  const notesSummary = normalizeLearnerNotes(raw)
  const displayName = toString(record.display_name ?? record.name ?? record.nickname, '未命名用户')

  return {
    user_id: toString(record.user_id ?? record.id ?? userId, userId),
    display_name: displayName,
    profile: normalizeLearnerProfile(raw),
    recent_sessions: normalizeLearnerSessions(raw),
    chapter_mastery: normalizeLearnerMastery(raw),
    notes_summary: {
      ...notesSummary,
      summary: toString(notesSummary.summary, ''),
    },
  }
}

export async function loadBiWorkbench(options: BiFetchOptions = {}): Promise<BiWorkbenchState> {
  const results = await Promise.allSettled([
    (async () => {
      const raw = unwrapPayload(
        await fetchBiJson('/api/v1/bi/overview', {
          days: options.days,
          capability: options.capability,
          entrypoint: options.entrypoint,
          tier: options.tier,
        })
      )
      return parseBiOverviewBundle(raw)
    })(),
    getBiActiveTrend(options),
    getBiRetention(options),
    getBiCapabilities(options),
    getBiTools(options),
    getBiKnowledge(options),
    getBiMembers(options),
    getBiCost(options),
    getBiTutorBots(options),
    getBiAnomalies(options),
  ])

  const issues: string[] = []
  const moduleIssues: BiWorkbenchModuleIssues = {}
  const missingCoreModules: BiBossCoreModule[] = []
  const data = structuredClone(DEFAULT_DATA)
  const [
    overview,
    trend,
    retention,
    capabilities,
    tools,
    knowledge,
    members,
    cost,
    tutorbots,
    anomalies,
  ] = results
  let overviewBossWorkbench: BiBossWorkbench | undefined

  if (overview.status === 'fulfilled') {
    data.overview = overview.value.overview
    overviewBossWorkbench = overview.value.bossWorkbench
  } else {
    missingCoreModules.push('overview')
    moduleIssues.overview =
      overview.reason instanceof Error ? overview.reason.message : '概览加载失败'
    issues.push(moduleIssues.overview)
  }

  if (trend.status === 'fulfilled') data.trend = trend.value
  else {
    missingCoreModules.push('active-trend')
    moduleIssues.trend = trend.reason instanceof Error ? trend.reason.message : '趋势加载失败'
    issues.push(moduleIssues.trend)
  }

  if (retention.status === 'fulfilled') data.retention = retention.value
  else {
    moduleIssues.retention =
      retention.reason instanceof Error ? retention.reason.message : '留存加载失败'
    issues.push(moduleIssues.retention)
  }

  if (capabilities.status === 'fulfilled') data.capabilities = capabilities.value
  else {
    moduleIssues.capabilities =
      capabilities.reason instanceof Error ? capabilities.reason.message : '能力加载失败'
    issues.push(moduleIssues.capabilities)
  }

  if (tools.status === 'fulfilled') data.tools = tools.value
  else {
    moduleIssues.tools = tools.reason instanceof Error ? tools.reason.message : '工具加载失败'
    issues.push(moduleIssues.tools)
  }

  if (knowledge.status === 'fulfilled') data.knowledge = knowledge.value
  else {
    moduleIssues.knowledge =
      knowledge.reason instanceof Error ? knowledge.reason.message : '知识库加载失败'
    issues.push(moduleIssues.knowledge)
  }

  if (members.status === 'fulfilled') data.members = members.value
  else {
    missingCoreModules.push('members')
    moduleIssues.members = members.reason instanceof Error ? members.reason.message : '会员加载失败'
    issues.push(moduleIssues.members)
  }

  if (cost.status === 'fulfilled') data.cost = cost.value
  else {
    missingCoreModules.push('cost')
    moduleIssues.cost = cost.reason instanceof Error ? cost.reason.message : '成本加载失败'
    issues.push(moduleIssues.cost)
  }

  if (tutorbots.status === 'fulfilled') data.tutorbots = tutorbots.value
  else {
    moduleIssues.tutorbots =
      tutorbots.reason instanceof Error ? tutorbots.reason.message : 'TutorBot 加载失败'
    issues.push(moduleIssues.tutorbots)
  }

  if (anomalies.status === 'fulfilled') data.anomalies = anomalies.value
  else {
    moduleIssues.anomalies =
      anomalies.reason instanceof Error ? anomalies.reason.message : '异常加载失败'
    issues.push(moduleIssues.anomalies)
  }

  return {
    data,
    issues,
    boss: overviewBossWorkbench ?? buildBiBossWorkbench(data, missingCoreModules),
    moduleIssues,
  }
}
