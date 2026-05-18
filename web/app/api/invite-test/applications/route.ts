import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";

export const runtime = "nodejs";

type InviteApplicationPayload = {
  name?: unknown;
  phone?: unknown;
  email?: unknown;
  province?: unknown;
  ageRange?: unknown;
  education?: unknown;
  occupation?: unknown;
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
  status: "submitted";
  operatorNote: string;
  submitCount: number;
  rawPayload: InviteApplicationPayload;
};

const REQUIRED_FIELDS = ["name", "phone", "email", "examType", "examStage", "painPoint", "weeklyTime"] as const;
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

function isRateLimited(ip: string) {
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

async function saveToJsonl(record: InviteApplicationRecord) {
  const filePath = getJsonlFallbackPath();
  if (!filePath) return false;
  await mkdir(path.dirname(filePath), { recursive: true });
  await appendFile(filePath, `${JSON.stringify(record)}\n`, "utf8");
  return true;
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
  }

  return NextResponse.json({ ok: true, id: validation.record.id }, { status: 201 });
}
