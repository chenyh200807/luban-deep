import { appendFile, mkdir } from 'node:fs/promises'
import path from 'node:path'
import { NextRequest, NextResponse } from 'next/server'
import { Pool } from 'pg'

export const runtime = 'nodejs'

// 鲁班智考 · 内测回访问卷答卷接收。
// 与 app/api/invite-test/applications/route.ts 同构：pg 直连 Supabase Postgres，
// 服务端写入绕过 RLS；限流 + 校验 + 文件兜底。匿名友好，不强制身份。

type FeedbackPayload = {
  survey?: unknown
  version?: unknown
  submitted_at?: unknown
  user_agent?: unknown
  source_page?: unknown
  answers?: Record<string, unknown>
}

type FeedbackRecord = {
  id: string
  createdAt: string
  sourcePage: string
  surveyVersion: string
  nps: number | null
  overallSatisfaction: number | null
  mostValuable: string
  willContinue: string
  payWillingness: string
  wouldRecommend: string
  revisitWillingness: string
  topSuggestion: string
  unsolvedPain: string
  phone: string
  wechatId: string
  userAgent: string
  status: 'submitted'
  operatorNote: string
  rawPayload: Record<string, unknown>
}

const MAX_LENGTHS = {
  sourcePage: 120,
  surveyVersion: 40,
  shortText: 120,
  openText: 1000,
  userAgent: 400,
  phone: 24,
  wechatId: 120,
  enum: 80,
  arrayItem: 80,
}
const MAX_ARRAY_ITEMS = 30

const rateLimitBuckets = new Map<string, { count: number; resetAt: number }>()
const RATE_LIMIT_WINDOW_MS = 60_000
const RATE_LIMIT_MAX = 8

let pool: Pool | null = null

function cleanString(value: unknown, maxLength: number) {
  if (typeof value !== 'string') return ''
  return value.replace(/\s+/g, ' ').trim().slice(0, maxLength)
}

function cleanScalar(value: unknown, maxLength: number) {
  // 单选/量表答案可能是字符串或数字
  if (typeof value === 'number' && Number.isFinite(value)) return String(value).slice(0, maxLength)
  return cleanString(value, maxLength)
}

function cleanArray(value: unknown) {
  if (!Array.isArray(value)) return [] as string[]
  return value
    .slice(0, MAX_ARRAY_ITEMS)
    .map(item => cleanString(item, MAX_LENGTHS.arrayItem))
    .filter(Boolean)
}

function parseRating(value: unknown, min: number, max: number): number | null {
  const raw =
    typeof value === 'number' ? value : typeof value === 'string' ? Number.parseInt(value, 10) : NaN
  if (!Number.isFinite(raw)) return null
  if (raw < min || raw > max) return null
  return raw
}

function extractIp(request: NextRequest) {
  const forwardedFor = request.headers.get('x-forwarded-for')
  if (forwardedFor) return forwardedFor.split(',')[0]?.trim() || 'unknown'
  return request.headers.get('x-real-ip') ?? 'unknown'
}

function isRateLimited(ip: string) {
  const now = Date.now()
  const current = rateLimitBuckets.get(ip)
  if (!current || current.resetAt <= now) {
    rateLimitBuckets.set(ip, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS })
    return false
  }
  current.count += 1
  return current.count > RATE_LIMIT_MAX
}

async function getDatabaseUrl() {
  return (
    process.env.FEEDBACK_DATABASE_URL || process.env.SUPABASE_DB_URL || process.env.DB_URL || ''
  )
}

function isProductionRuntime() {
  return process.env.NODE_ENV === 'production' || process.env.VERCEL_ENV === 'production'
}

function parseDatabaseUrl(connectionString: string) {
  try {
    return new URL(connectionString)
  } catch {
    return null
  }
}

function isLocalDatabaseUrl(connectionString: string) {
  const url = parseDatabaseUrl(connectionString)
  const hostname = url?.hostname.toLowerCase()
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
}

function normalizeDatabaseUrl(connectionString: string) {
  const url = parseDatabaseUrl(connectionString)
  if (!url) return connectionString

  const sslmode = (url.searchParams.get('sslmode') || '').toLowerCase()
  if (!sslmode) return connectionString

  const insecureMode = sslmode === 'disable' || sslmode === 'no-verify'
  if (!insecureMode) return connectionString

  const explicitLocalOverride = process.env.FEEDBACK_ALLOW_INSECURE_LOCAL_DB_TLS === '1'
  if (isProductionRuntime() || !explicitLocalOverride || !isLocalDatabaseUrl(connectionString)) {
    throw new Error('Feedback database TLS must verify certificates')
  }

  url.searchParams.delete('sslmode')
  return url.toString()
}

function getDatabaseSsl(connectionString: string) {
  if (isLocalDatabaseUrl(connectionString)) return undefined
  const ca = process.env.FEEDBACK_DATABASE_CA_CERT || process.env.SUPABASE_DB_CA_CERT
  if (ca) return { ca }
  // Explicit opt-in only: set FEEDBACK_ALLOW_UNVERIFIED_SSL=1 when the Supabase
  // pooler cert chain is not trusted by the container CA bundle.
  // TODO: replace with SUPABASE_DB_CA_CERT once cert is provisioned from
  //       Supabase Dashboard → Settings → Database → SSL Certificate.
  if (process.env.FEEDBACK_ALLOW_UNVERIFIED_SSL === '1') return { rejectUnauthorized: false }
  return true
}

async function getPool() {
  if (pool) return pool
  const connectionString = await getDatabaseUrl()
  if (!connectionString) return null
  const normalizedConnectionString = normalizeDatabaseUrl(connectionString)

  pool = new Pool({
    connectionString: normalizedConnectionString,
    max: 3,
    idleTimeoutMillis: 10_000,
    ssl: getDatabaseSsl(normalizedConnectionString),
  })
  return pool
}

function buildRawPayload(answers: Record<string, unknown>) {
  // 全量保存，但逐项清洗，避免存入超长/异常内容
  const raw: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(answers)) {
    if (Array.isArray(value)) raw[key] = cleanArray(value)
    else if (value && typeof value === 'object') {
      const obj: Record<string, string> = {}
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
        obj[cleanString(k, 40)] = cleanString(v, MAX_LENGTHS.openText)
      }
      raw[key] = obj
    } else if (typeof value === 'number' && Number.isFinite(value)) raw[key] = value
    else raw[key] = cleanString(value, MAX_LENGTHS.openText)
  }
  return raw
}

function validatePayload(payload: FeedbackPayload) {
  const answers = (
    payload.answers && typeof payload.answers === 'object' ? payload.answers : null
  ) as Record<string, unknown> | null
  if (!answers || Object.keys(answers).length === 0) {
    return { error: '答卷内容为空。' }
  }

  const contact = (
    answers.contact && typeof answers.contact === 'object' ? answers.contact : {}
  ) as Record<string, unknown>

  const record: FeedbackRecord = {
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    sourcePage: cleanString(payload.source_page, MAX_LENGTHS.sourcePage),
    surveyVersion: cleanString(payload.version, MAX_LENGTHS.surveyVersion),
    nps: parseRating(answers.nps, 0, 10),
    overallSatisfaction: parseRating(answers.overall_satisfaction, 1, 5),
    mostValuable: cleanScalar(answers.most_valuable, MAX_LENGTHS.enum),
    willContinue: cleanScalar(answers.will_continue, MAX_LENGTHS.enum),
    payWillingness: cleanScalar(answers.pay_willingness, MAX_LENGTHS.enum),
    wouldRecommend: cleanScalar(answers.would_recommend, MAX_LENGTHS.enum),
    revisitWillingness: cleanScalar(answers.revisit_willingness, MAX_LENGTHS.enum),
    topSuggestion: cleanString(answers.top_suggestion, MAX_LENGTHS.openText),
    unsolvedPain: cleanString(answers.unsolved_pain, MAX_LENGTHS.openText),
    phone: cleanString(contact.phone, MAX_LENGTHS.phone).replace(/\s+/g, ''),
    wechatId: cleanString(contact.wechat, MAX_LENGTHS.wechatId),
    userAgent: cleanString(payload.user_agent, MAX_LENGTHS.userAgent),
    status: 'submitted',
    operatorNote: '',
    rawPayload: buildRawPayload(answers),
  }

  // 匿名友好：仅要求最关键的 NPS 已作答，其余宽松存储。
  if (record.nps === null) {
    return { error: '缺少推荐意愿(NPS)评分。' }
  }
  // 留了手机号则校验格式（避免脏数据），但不强制填写。
  if (record.phone && !/^1\d{10}$/.test(record.phone)) {
    return { error: '手机号格式不正确。' }
  }

  return { record }
}

async function saveToDatabase(record: FeedbackRecord) {
  const db = await getPool()
  if (!db) return false

  await db.query(
    `
      insert into public.luban_feedback (
        id,
        created_at,
        source_page,
        survey_version,
        nps,
        overall_satisfaction,
        most_valuable,
        will_continue,
        pay_willingness,
        would_recommend,
        revisit_willingness,
        top_suggestion,
        unsolved_pain,
        phone,
        wechat_id,
        user_agent,
        status,
        operator_note,
        raw_payload
      )
      values (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15, $16, $17, $18, $19
      )
    `,
    [
      record.id,
      record.createdAt,
      record.sourcePage,
      record.surveyVersion,
      record.nps,
      record.overallSatisfaction,
      record.mostValuable,
      record.willContinue,
      record.payWillingness,
      record.wouldRecommend,
      record.revisitWillingness,
      record.topSuggestion,
      record.unsolvedPain,
      record.phone,
      record.wechatId,
      record.userAgent,
      record.status,
      record.operatorNote,
      record.rawPayload,
    ]
  )

  return true
}

function getJsonlFallbackPath() {
  const configured = process.env.FEEDBACK_RESPONSES_PATH
  if (configured) return configured
  if (isProductionRuntime()) return ''
  return path.join(process.cwd(), 'tmp', 'luban-feedback-responses.jsonl')
}

async function saveToJsonl(record: FeedbackRecord) {
  const filePath = getJsonlFallbackPath()
  if (!filePath) return false
  await mkdir(path.dirname(filePath), { recursive: true })
  await appendFile(filePath, `${JSON.stringify(record)}\n`, 'utf8')
  return true
}

export async function POST(request: NextRequest) {
  const ip = extractIp(request)
  if (isRateLimited(ip)) {
    return NextResponse.json({ error: '提交过于频繁，请稍后再试。' }, { status: 429 })
  }

  let payload: FeedbackPayload
  try {
    payload = (await request.json()) as FeedbackPayload
  } catch {
    return NextResponse.json({ error: '请求内容不是有效 JSON。' }, { status: 400 })
  }

  const validation = validatePayload(payload)
  if ('error' in validation) {
    return NextResponse.json({ error: validation.error }, { status: 400 })
  }

  try {
    const wroteToDatabase = await saveToDatabase(validation.record)
    if (!wroteToDatabase && !(await saveToJsonl(validation.record))) {
      return NextResponse.json({ error: '反馈提交通道未配置，请稍后再试。' }, { status: 503 })
    }
  } catch (error) {
    console.error('Failed to save luban feedback response', error)
    return NextResponse.json({ error: '反馈提交失败，请稍后再试。' }, { status: 500 })
  }

  return NextResponse.json({ ok: true, id: validation.record.id }, { status: 201 })
}
