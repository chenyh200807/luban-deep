<<<<<<< Updated upstream
import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
=======
import { randomUUID } from "crypto";
import { existsSync, readFileSync } from "fs";
import { mkdir, readFile, appendFile } from "fs/promises";
import path from "path";
>>>>>>> Stashed changes
import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

export const runtime = "nodejs";

type InviteApplicationPayload = {
  name?: unknown;
  phone?: unknown;
  email?: unknown;
<<<<<<< Updated upstream
  province?: unknown;
  ageRange?: unknown;
  education?: unknown;
  occupation?: unknown;
=======
>>>>>>> Stashed changes
  examType?: unknown;
  examStage?: unknown;
  preparationYears?: unknown;
  knowledgeFoundation?: unknown;
  painPoint?: unknown;
  weeklyTime?: unknown;
  dailyStudyTime?: unknown;
  currentMethod?: unknown;
  studyDifficulties?: unknown;
  wechatId?: unknown;
  isYousenMember?: unknown;
  examDate?: unknown;
  latestWrongQuestion?: unknown;
  acceptInterview?: unknown;
  consent?: unknown;
  sourcePage?: unknown;
  utmSource?: unknown;
  utmCampaign?: unknown;
};

type InviteApplicationRecord = {
  id: string;
  createdAt: string;
  sourcePage: string;
  utmSource: string;
  utmCampaign: string;
  name: string;
  phone: string;
  email: string;
<<<<<<< Updated upstream
  wechatId: string;
  examType: string;
  examStage: string;
  painPoint: string;
  weeklyTime: string;
  currentMethod: string;
  latestWrongQuestion: string;
  isYousenMember: string;
  examDate: string;
  acceptInterview: boolean;
  consent: boolean;
=======
  wechat_id: string;
  exam_type: string;
  exam_stage: string;
  pain_point: string;
  weekly_time: string;
  current_method: string;
  latest_wrong_question: string;
  is_yousen_member: string;
  exam_date: string;
  accept_interview: boolean;
  consent: true;
>>>>>>> Stashed changes
  status: "submitted";
  operatorNote: string;
  submitCount: number;
  rawPayload: InviteApplicationPayload;
};

<<<<<<< Updated upstream
const REQUIRED_FIELDS = ["name", "phone", "email", "wechatId", "examType", "examStage", "painPoint", "weeklyTime"] as const;
const MAX_LENGTHS = {
  name: 80,
  phone: 24,
  email: 160,
  province: 80,
  ageRange: 40,
  education: 80,
  occupation: 120,
  examType: 80,
  examStage: 80,
  preparationYears: 80,
  knowledgeFoundation: 80,
  painPoint: 80,
  weeklyTime: 80,
  dailyStudyTime: 80,
  currentMethod: 800,
  studyDifficulties: 1000,
  wechatId: 120,
  isYousenMember: 80,
  examDate: 80,
  latestWrongQuestion: 1400,
  sourcePage: 120,
  utmSource: 120,
  utmCampaign: 120,
};
=======
const phonePattern = /^1\d{10}$/;
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const rateLimitWindowMs = 60_000;
const maxRequestsPerWindow = 8;
const buckets = new Map<string, { count: number; resetAt: number }>();
const fallbackEnvPath = "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/.env";

let externalEnvCache: Record<string, string> | null = null;
let inviteApplicationsPool: Pool | null | undefined;
>>>>>>> Stashed changes

const rateLimitBuckets = new Map<string, { count: number; resetAt: number }>();
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 8;

let pool: Pool | null = null;

function cleanString(value: unknown, maxLength: number) {
  if (typeof value !== "string") return "";
  return value.replace(/\s+/g, " ").trim().slice(0, maxLength);
}

function extractIp(request: NextRequest) {
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) return forwardedFor.split(",")[0]?.trim() || "unknown";
  return request.headers.get("x-real-ip") ?? "unknown";
}

<<<<<<< Updated upstream
function isRateLimited(ip: string) {
=======
function parseExternalEnv(): Record<string, string> {
  if (externalEnvCache) return externalEnvCache;

  const envPath = process.env.INVITE_TEST_ENV_PATH || fallbackEnvPath;
  const values: Record<string, string> = {};

  if (!existsSync(envPath)) {
    externalEnvCache = values;
    return values;
  }

  for (const line of readFileSync(envPath, "utf8").split("\n")) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (!match) continue;

    let value = match[2].trim();
    if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    values[match[1]] = value;
  }

  externalEnvCache = values;
  return values;
}

function getInviteDatabaseUrl(): string {
  const externalEnv = parseExternalEnv();
  return (
    process.env.INVITE_TEST_DATABASE_URL ||
    process.env.SUPABASE_DB_URL ||
    process.env.DB_URL ||
    externalEnv.INVITE_TEST_DATABASE_URL ||
    externalEnv.SUPABASE_DB_URL ||
    externalEnv.DB_URL ||
    ""
  );
}

function getInviteApplicationsPool(): Pool | null {
  if (inviteApplicationsPool !== undefined) return inviteApplicationsPool;

  const connectionString = getInviteDatabaseUrl();
  if (!connectionString) {
    inviteApplicationsPool = null;
    return inviteApplicationsPool;
  }

  const requiresSsl = connectionString.includes("supabase.com") || connectionString.includes("sslmode=require");
  inviteApplicationsPool = new Pool({
    connectionString,
    max: 3,
    ssl: requiresSsl ? { rejectUnauthorized: false } : undefined,
  });

  return inviteApplicationsPool;
}

function checkRateLimit(key: string): boolean {
>>>>>>> Stashed changes
  const now = Date.now();
  const current = rateLimitBuckets.get(ip);
  if (!current || current.resetAt <= now) {
    rateLimitBuckets.set(ip, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return false;
  }
  current.count += 1;
  return current.count > RATE_LIMIT_MAX;
}

async function getDatabaseUrl() {
  return process.env.INVITE_TEST_DATABASE_URL || process.env.SUPABASE_DB_URL || process.env.DB_URL || "";
}

function isProductionRuntime() {
  return process.env.NODE_ENV === "production" || process.env.VERCEL_ENV === "production";
}

function parseDatabaseUrl(connectionString: string) {
  try {
    return new URL(connectionString);
  } catch {
    return null;
  }
}

function isLocalDatabaseUrl(connectionString: string) {
  const url = parseDatabaseUrl(connectionString);
  const hostname = url?.hostname.toLowerCase();
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function normalizeDatabaseUrl(connectionString: string) {
  const url = parseDatabaseUrl(connectionString);
  if (!url) return connectionString;

  const sslmode = (url.searchParams.get("sslmode") || "").toLowerCase();
  if (!sslmode) return connectionString;

  const insecureMode = sslmode === "disable" || sslmode === "no-verify";
  if (!insecureMode) return connectionString;

  const explicitLocalOverride = process.env.INVITE_TEST_ALLOW_INSECURE_LOCAL_DB_TLS === "1";
  if (isProductionRuntime() || !explicitLocalOverride || !isLocalDatabaseUrl(connectionString)) {
    throw new Error("Invite-test database TLS must verify certificates");
  }

  url.searchParams.delete("sslmode");
  return url.toString();
}

function getDatabaseSsl(connectionString: string) {
  if (isLocalDatabaseUrl(connectionString)) return undefined;
  const ca = process.env.INVITE_TEST_DATABASE_CA_CERT || process.env.SUPABASE_DB_CA_CERT;
  return ca ? { ca } : true;
}

async function getPool() {
  if (pool) return pool;
  const connectionString = await getDatabaseUrl();
  if (!connectionString) return null;
  const normalizedConnectionString = normalizeDatabaseUrl(connectionString);

  pool = new Pool({
    connectionString: normalizedConnectionString,
    max: 3,
    idleTimeoutMillis: 10_000,
    ssl: getDatabaseSsl(normalizedConnectionString),
  });
  return pool;
}

function validatePayload(payload: InviteApplicationPayload) {
  const record: InviteApplicationRecord = {
    id: crypto.randomUUID(),
    createdAt: new Date().toISOString(),
    sourcePage: cleanString(payload.sourcePage, MAX_LENGTHS.sourcePage),
    utmSource: cleanString(payload.utmSource, MAX_LENGTHS.utmSource),
    utmCampaign: cleanString(payload.utmCampaign, MAX_LENGTHS.utmCampaign),
    name: cleanString(payload.name, MAX_LENGTHS.name),
    phone: cleanString(payload.phone, MAX_LENGTHS.phone).replace(/\s+/g, ""),
    email: cleanString(payload.email, MAX_LENGTHS.email).toLowerCase(),
    wechatId: cleanString(payload.wechatId, MAX_LENGTHS.wechatId),
    examType: cleanString(payload.examType, MAX_LENGTHS.examType),
    examStage: cleanString(payload.examStage, MAX_LENGTHS.examStage),
    painPoint: cleanString(payload.painPoint, MAX_LENGTHS.painPoint),
    weeklyTime: cleanString(payload.weeklyTime, MAX_LENGTHS.weeklyTime),
    currentMethod: cleanString(payload.currentMethod, MAX_LENGTHS.currentMethod),
    latestWrongQuestion: cleanString(payload.latestWrongQuestion, MAX_LENGTHS.latestWrongQuestion),
    isYousenMember: cleanString(payload.isYousenMember, MAX_LENGTHS.isYousenMember),
    examDate: cleanString(payload.examDate, MAX_LENGTHS.examDate),
    acceptInterview: payload.acceptInterview === true,
    consent: payload.consent === true,
    status: "submitted",
    operatorNote: "",
    submitCount: 1,
    rawPayload: {
      name: cleanString(payload.name, MAX_LENGTHS.name),
      phone: cleanString(payload.phone, MAX_LENGTHS.phone).replace(/\s+/g, ""),
      email: cleanString(payload.email, MAX_LENGTHS.email).toLowerCase(),
      province: cleanString(payload.province, MAX_LENGTHS.province),
      ageRange: cleanString(payload.ageRange, MAX_LENGTHS.ageRange),
      education: cleanString(payload.education, MAX_LENGTHS.education),
      occupation: cleanString(payload.occupation, MAX_LENGTHS.occupation),
      wechatId: cleanString(payload.wechatId, MAX_LENGTHS.wechatId),
      examType: cleanString(payload.examType, MAX_LENGTHS.examType),
      examStage: cleanString(payload.examStage, MAX_LENGTHS.examStage),
      preparationYears: cleanString(payload.preparationYears, MAX_LENGTHS.preparationYears),
      knowledgeFoundation: cleanString(payload.knowledgeFoundation, MAX_LENGTHS.knowledgeFoundation),
      painPoint: cleanString(payload.painPoint, MAX_LENGTHS.painPoint),
      weeklyTime: cleanString(payload.weeklyTime, MAX_LENGTHS.weeklyTime),
      dailyStudyTime: cleanString(payload.dailyStudyTime, MAX_LENGTHS.dailyStudyTime),
      currentMethod: cleanString(payload.currentMethod, MAX_LENGTHS.currentMethod),
      studyDifficulties: cleanString(payload.studyDifficulties, MAX_LENGTHS.studyDifficulties),
      latestWrongQuestion: cleanString(payload.latestWrongQuestion, MAX_LENGTHS.latestWrongQuestion),
      isYousenMember: cleanString(payload.isYousenMember, MAX_LENGTHS.isYousenMember),
      examDate: cleanString(payload.examDate, MAX_LENGTHS.examDate),
      acceptInterview: payload.acceptInterview === true,
      consent: payload.consent === true,
      sourcePage: cleanString(payload.sourcePage, MAX_LENGTHS.sourcePage),
      utmSource: cleanString(payload.utmSource, MAX_LENGTHS.utmSource),
      utmCampaign: cleanString(payload.utmCampaign, MAX_LENGTHS.utmCampaign),
    },
  };

  const missingField = REQUIRED_FIELDS.find((field) => !record[field]);
  if (missingField) {
    return { error: `缺少必填字段：${missingField}` };
  }
  if (!/^1\d{10}$/.test(record.phone)) {
    return { error: "手机号格式不正确。" };
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(record.email)) {
    return { error: "邮箱格式不正确。" };
  }
  if (!record.consent) {
    return { error: "请先同意内测筛选与产品改进用途。" };
  }

  return { record };
}

async function saveToDatabase(record: InviteApplicationRecord) {
  const db = await getPool();
  if (!db) return false;

  const duplicateResult = await db.query<{ count: string }>(
    "select count(*)::text as count from public.invite_test_applications where phone = $1",
    [record.phone],
  );
  const submitCount = Number.parseInt(duplicateResult.rows[0]?.count ?? "0", 10) + 1;

  await db.query(
    `
      insert into public.invite_test_applications (
        id,
        created_at,
        source_page,
        utm_source,
        utm_campaign,
        name,
        phone,
        email,
        wechat_id,
        exam_type,
        exam_stage,
        pain_point,
        weekly_time,
        current_method,
        latest_wrong_question,
        is_yousen_member,
        exam_date,
        accept_interview,
        consent,
        status,
        operator_note,
        submit_count,
        raw_payload
      )
      values (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
        $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23
      )
    `,
    [
      record.id,
      record.createdAt,
      record.sourcePage,
      record.utmSource,
      record.utmCampaign,
      record.name,
      record.phone,
      record.email,
      record.wechatId,
      record.examType,
      record.examStage,
      record.painPoint,
      record.weeklyTime,
      record.currentMethod,
      record.latestWrongQuestion,
      record.isYousenMember,
      record.examDate,
      record.acceptInterview,
      record.consent,
      record.status,
      record.operatorNote,
      submitCount,
      record.rawPayload,
    ],
  );

  return true;
}

function getJsonlFallbackPath() {
  const configured = process.env.INVITE_TEST_APPLICATIONS_PATH;
  if (configured) return configured;
  if (isProductionRuntime()) return "";
  return path.join(process.cwd(), "tmp", "invite-test-applications.jsonl");
}

<<<<<<< Updated upstream
async function saveToJsonl(record: InviteApplicationRecord) {
  const filePath = getJsonlFallbackPath();
  if (!filePath) return false;
  await mkdir(path.dirname(filePath), { recursive: true });
  await appendFile(filePath, `${JSON.stringify(record)}\n`, "utf8");
  return true;
=======
async function countExistingSubmissions(phone: string, storagePath: string): Promise<number> {
  try {
    const content = await readFile(storagePath, "utf8");
    return content
      .split("\n")
      .filter(Boolean)
      .reduce((count, line) => {
        try {
          const record = JSON.parse(line) as Partial<InviteApplicationRecord>;
          return record.phone === phone ? count + 1 : count;
        } catch {
          return count;
        }
      }, 0);
  } catch {
    return 0;
  }
}

async function countExistingSupabaseSubmissions(pool: Pool, phone: string): Promise<number> {
  const result = await pool.query<{ count: string }>(
    "select count(*)::text as count from public.invite_test_applications where phone = $1",
    [phone],
  );
  return Number(result.rows[0]?.count || 0);
}

async function insertSupabaseApplication(pool: Pool, record: InviteApplicationRecord, rawPayload: InviteApplicationPayload) {
  await pool.query(
    `
      insert into public.invite_test_applications (
        id,
        created_at,
        source_page,
        utm_source,
        utm_campaign,
        name,
        phone,
        email,
        wechat_id,
        exam_type,
        exam_stage,
        pain_point,
        weekly_time,
        current_method,
        latest_wrong_question,
        is_yousen_member,
        exam_date,
        accept_interview,
        consent,
        status,
        operator_note,
        submit_count,
        raw_payload
      )
      values (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15, $16, $17, $18,
        $19, $20, $21, $22, $23::jsonb
      )
    `,
    [
      record.id,
      record.created_at,
      record.source_page,
      record.utm_source,
      record.utm_campaign,
      record.name,
      record.phone,
      record.email,
      record.wechat_id,
      record.exam_type,
      record.exam_stage,
      record.pain_point,
      record.weekly_time,
      record.current_method,
      record.latest_wrong_question,
      record.is_yousen_member,
      record.exam_date,
      record.accept_interview,
      record.consent,
      record.status,
      record.operator_note,
      record.submit_count,
      JSON.stringify(rawPayload),
    ],
  );
}

function buildRecord(payload: InviteApplicationPayload, submitCount: number): InviteApplicationRecord | { error: string } {
  const name = cleanText(payload.name, 40);
  const phone = cleanText(payload.phone, 20).replace(/\s+/g, "");
  const email = cleanText(payload.email, 160).toLowerCase();
  const examType = cleanText(payload.examType, 40);
  const examStage = cleanText(payload.examStage, 40);
  const painPoint = cleanText(payload.painPoint, 60);
  const weeklyTime = cleanText(payload.weeklyTime, 40);
  const consent = payload.consent === true;

  if (!name) return { error: "请输入称呼。" };
  if (!phonePattern.test(phone)) return { error: "请输入 11 位中国大陆手机号。" };
  if (!emailPattern.test(email)) return { error: "请输入有效邮箱。" };
  if (!examType) return { error: "请选择你正在准备的考试。" };
  if (!examStage) return { error: "请选择你当前的备考阶段。" };
  if (!painPoint) return { error: "请选择一个最想先解决的问题。" };
  if (!weeklyTime) return { error: "请选择每周可参与测试的时间。" };
  if (!consent) return { error: "请确认同意我们用于内测筛选与产品改进。" };

  return {
    id: randomUUID(),
    created_at: new Date().toISOString(),
    source_page: cleanText(payload.sourcePage, 80) || "invite-test",
    utm_source: cleanText(payload.utmSource, 120),
    utm_campaign: cleanText(payload.utmCampaign, 120),
    name,
    phone,
    email,
    wechat_id: cleanText(payload.wechatId, 80),
    exam_type: examType,
    exam_stage: examStage,
    pain_point: painPoint,
    weekly_time: weeklyTime,
    current_method: cleanText(payload.currentMethod, 1200),
    latest_wrong_question: cleanText(payload.latestWrongQuestion, 2200),
    is_yousen_member: cleanText(payload.isYousenMember, 40),
    exam_date: cleanText(payload.examDate, 40),
    accept_interview: payload.acceptInterview === true,
    consent: true,
    status: "submitted",
    operator_note: "",
    submit_count: submitCount,
  };
>>>>>>> Stashed changes
}

export async function POST(request: NextRequest) {
  const ip = extractIp(request);
  if (isRateLimited(ip)) {
    return NextResponse.json({ error: "提交过于频繁，请稍后再试。" }, { status: 429 });
  }

  let payload: InviteApplicationPayload;
  try {
    payload = (await request.json()) as InviteApplicationPayload;
  } catch {
    return NextResponse.json({ error: "请求内容不是有效 JSON。" }, { status: 400 });
  }

<<<<<<< Updated upstream
  const validation = validatePayload(payload);
  if ("error" in validation) {
    return NextResponse.json({ error: validation.error }, { status: 400 });
  }

  try {
    const wroteToDatabase = await saveToDatabase(validation.record);
    if (!wroteToDatabase && !(await saveToJsonl(validation.record))) {
      return NextResponse.json({ error: "申请提交通道未配置，请稍后再试。" }, { status: 503 });
    }
  } catch (error) {
    console.error("Failed to save invite test application", error);
    return NextResponse.json({ error: "申请提交失败，请稍后再试。" }, { status: 500 });
=======
  const storagePath = getStoragePath();
  const phone = cleanText(payload.phone, 20).replace(/\s+/g, "");
  const pool = getInviteApplicationsPool();
  let previousCount = 0;

  if (phonePattern.test(phone)) {
    try {
      previousCount = pool
        ? await countExistingSupabaseSubmissions(pool, phone)
        : await countExistingSubmissions(phone, storagePath);
    } catch (error) {
      console.error("Invite application duplicate check failed:", error instanceof Error ? error.message : "unknown error");
      return NextResponse.json({ ok: false, error: "申请提交失败，请稍后再试。" }, { status: 500 });
    }
  }

  const record = buildRecord(payload, previousCount + 1);

  if ("error" in record) {
    return NextResponse.json({ ok: false, error: record.error }, { status: 400 });
  }

  if (pool) {
    try {
      await insertSupabaseApplication(pool, record, payload);
    } catch (error) {
      console.error("Invite application Supabase insert failed:", error instanceof Error ? error.message : "unknown error");
      return NextResponse.json({ ok: false, error: "申请提交失败，请稍后再试。" }, { status: 500 });
    }
  } else {
    await mkdir(path.dirname(storagePath), { recursive: true });
    await appendFile(storagePath, `${JSON.stringify(record)}\n`, "utf8");
>>>>>>> Stashed changes
  }

  return NextResponse.json({ ok: true, id: validation.record.id }, { status: 201 });
}
