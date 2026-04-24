import { BI_API_TOKEN, apiUrl, withAdminAuthorization, withBiApiToken } from "@/lib/api";

export interface BiMetricCard {
  label: string;
  value: number | string;
  hint?: string;
  delta?: string;
  tone?: "neutral" | "good" | "warning" | "critical";
}

export interface BiTrendPoint {
  label: string;
  active: number;
  cost: number;
  successful: number;
}

export interface BiBossDailyCostPoint {
  date: string;
  label: string;
  costUsd: number;
  tokens: number;
  turns: number;
}

export interface BiBossDailyCost {
  todayUsd: number;
  windowTotalUsd: number;
  averageDailyUsd: number;
  source: string;
  series: BiBossDailyCostPoint[];
}

export interface BiRetentionCohort {
  label: string;
  values: number[];
}

export interface BiRankItem {
  label: string;
  value: number;
  rate?: number;
  hint?: string;
  secondary?: string;
}

export interface BiMemberSample {
  user_id: string;
  display_name: string;
  tier?: string;
  status?: string;
  risk_level?: string;
  last_active_at?: string;
  detail?: string;
}

export interface BiTutorBotItem {
  bot_id: string;
  name: string;
  capability?: string;
  entrypoint?: string;
  tier?: string;
  status?: string;
  last_active_at?: string;
  recent_message?: string;
  runs?: number;
  success_rate?: number;
  detail?: string;
}

export interface BiLearnerSession {
  session_id: string;
  title: string;
  capability?: string;
  status?: string;
  started_at?: string;
  ended_at?: string;
  duration_minutes?: number;
  summary?: string;
}

export interface BiLearnerChapterMastery {
  chapter_id?: string;
  name: string;
  mastery: number;
  hint?: string;
  evidence?: string;
}

export interface BiLearnerNoteLedgerSummary {
  notes_count?: number;
  pinned_notes_count?: number;
  recent_note?: string;
  recent_ledger?: string;
  wallet_balance?: number;
  ledger_delta?: number;
  summary?: string;
}

export interface BiLearnerDetailData {
  user_id: string;
  display_name: string;
  profile: BiMetricCard[];
  recent_sessions: BiLearnerSession[];
  chapter_mastery: BiLearnerChapterMastery[];
  notes_summary: BiLearnerNoteLedgerSummary;
}

export interface BiAlertItem {
  level: "info" | "warning" | "critical";
  title: string;
  detail?: string;
}

export interface BiMetricDefinition {
  metric_id: string;
  label: string;
  group?: string;
  definition: string;
  authority: string;
  trustLevel: "A" | "B" | "C" | "D" | string;
  owner: string;
  drilldown: string;
  displayHint?: string;
}

export interface BiNorthStarInput extends BiMetricDefinition {
  value?: number | string | null;
}

export interface BiNorthStarPayload extends BiMetricDefinition {
  value: number;
  windowDays: number;
  calculation: string;
  inputs: BiNorthStarInput[];
}

export interface BiGrowthFunnelStep {
  id: string;
  label: string;
  value: number;
  conversionRate: number;
  trustLevel: string;
  authority: string;
  drilldown: string;
}

export interface BiGrowthFunnelPayload {
  title: string;
  summary: string;
  steps: BiGrowthFunnelStep[];
}

export interface BiMemberHealthPayload {
  score: BiMetricDefinition & { value?: number; note?: string };
  distribution: Array<{ bucket: string; label: string; count: number }>;
  reasons: string[];
  samples: BiMemberSample[];
}

export interface BiOperatingRhythmAction {
  title: string;
  target: string;
  status: string;
  reason: string;
}

export interface BiOperatingRhythmPayload {
  cadences: Array<{ id: string; label: string; focus: string }>;
  topActions: BiOperatingRhythmAction[];
}

export interface BiTeachingChapterProgress {
  chapterId?: string;
  name: string;
  mastery: number;
  memberCount: number;
  status?: string;
  evidence?: string;
}

export interface BiTeachingEffectPayload {
  status: string;
  summary: string;
  metrics: Array<BiMetricDefinition & { value?: number | string | null; status?: string }>;
  chapterProgress: BiTeachingChapterProgress[];
}

export interface BiAiQualityPayload extends BiMetricDefinition {
  engineeringSuccessRate: number;
  failedTurns: number;
  totalTurns: number;
  teachingSuccessStatus: string;
  note: string;
  samples: Array<{ turn_id?: string; session_id?: string; status?: string }>;
}

export interface BiUnitEconomicsPayload extends BiMetricDefinition {
  revenueStatus: string;
  summary: string;
  windowTotalCostUsd: number;
  costPerEffectiveLearningUsd: number;
  source: string;
}

export interface BiDataTrustPayload {
  status: string;
  trustModel: string;
  degradedModules: Array<{ id: string; label: string; status: string; detail: string }>;
  metricDefinitions: BiMetricDefinition[];
}

export interface BiOverviewData {
  title: string;
  subtitle: string;
  cards: BiMetricCard[];
  highlights: string[];
  entrypoints: BiRankItem[];
  alerts: BiAlertItem[];
  northStar?: BiNorthStarPayload;
  growthFunnel?: BiGrowthFunnelPayload;
  memberHealth?: BiMemberHealthPayload;
  operatingRhythm?: BiOperatingRhythmPayload;
  teachingEffect?: BiTeachingEffectPayload;
  aiQuality?: BiAiQualityPayload;
  unitEconomics?: BiUnitEconomicsPayload;
  dataTrust?: BiDataTrustPayload;
}

export interface BiTrendData {
  points: BiTrendPoint[];
}

export interface BiRetentionData {
  cohorts: BiRetentionCohort[];
  labels: string[];
}

export interface BiCapabilityData {
  items: BiRankItem[];
  upgradePaths: BiRankItem[];
}

export interface BiToolData {
  items: BiRankItem[];
  efficiency: BiRankItem[];
}

export interface BiKnowledgeData {
  items: BiRankItem[];
  topQueries: BiRankItem[];
  zeroHitRate?: number;
}

export interface BiMemberData {
  cards: BiMetricCard[];
  tiers: BiRankItem[];
  risks: BiRankItem[];
  samples: BiMemberSample[];
}

export interface BiCostData {
  cards: BiMetricCard[];
  models: BiRankItem[];
  providers: BiRankItem[];
}

export interface BiTutorBotData {
  cards: BiMetricCard[];
  ranking: BiRankItem[];
  statusBreakdown: BiRankItem[];
  recentActive: BiTutorBotItem[];
  recentMessages: BiTutorBotItem[];
}

export interface BiAnomalyData {
  items: BiAlertItem[];
}

export interface BiBossKpiItem {
  label: string;
  value: number | string;
  hint?: string;
  delta?: string;
  tone?: BiMetricCard["tone"];
  source?: "overview" | "members" | "cost";
}

export interface BiBossActionItem {
  title: string;
  detail: string;
  tone?: BiMetricCard["tone"];
  source?: "anomalies" | "members" | "cost";
  handoffFilters?: Record<string, string | number | boolean | null>;
}

export interface BiBossWorkbench {
  kpis: BiBossKpiItem[];
  actionQueue: BiBossActionItem[];
  heroIssue: string;
  dailyCost?: BiBossDailyCost;
}

type BiBossCoreModule = "overview" | "active-trend" | "members" | "cost";
export type BiWorkbenchModuleKey =
  | "overview"
  | "trend"
  | "retention"
  | "capabilities"
  | "tools"
  | "knowledge"
  | "members"
  | "cost"
  | "tutorbots"
  | "anomalies";
export type BiWorkbenchModuleIssues = Partial<Record<BiWorkbenchModuleKey, string>>;

export interface BiWorkbenchData {
  overview: BiOverviewData;
  trend: BiTrendData;
  retention: BiRetentionData;
  capabilities: BiCapabilityData;
  tools: BiToolData;
  knowledge: BiKnowledgeData;
  members: BiMemberData;
  cost: BiCostData;
  tutorbots: BiTutorBotData;
  anomalies: BiAnomalyData;
}

export interface BiWorkbenchState {
  data: BiWorkbenchData;
  issues: string[];
  boss: BiBossWorkbench;
  moduleIssues: BiWorkbenchModuleIssues;
}

export interface BiFetchOptions {
  days?: number;
  capability?: string;
  entrypoint?: string;
  tier?: string;
}

const DEFAULT_DATA: BiWorkbenchData = {
  overview: {
    title: "DeepTutor BI 工作台",
    subtitle: "加载后端 BI 接口后即可查看经营、学习、能力、知识库与会员的统一视图。",
    cards: [],
    highlights: [],
    entrypoints: [],
    alerts: [],
  },
  trend: { points: [] },
  retention: { cohorts: [], labels: ["D0", "D1", "D7", "D30"] },
  capabilities: { items: [], upgradePaths: [] },
  tools: { items: [], efficiency: [] },
  knowledge: { items: [], topQueries: [], zeroHitRate: undefined },
  members: { cards: [], tiers: [], risks: [], samples: [] },
  cost: { cards: [], models: [], providers: [] },
  tutorbots: { cards: [], ranking: [], statusBreakdown: [], recentActive: [], recentMessages: [] },
  anomalies: { items: [] },
};

function unwrapPayload(raw: unknown): unknown {
  if (!raw || typeof raw !== "object") {
    return raw;
  }

  const record = raw as Record<string, unknown>;
  return record.data ?? record.result ?? record.payload ?? raw;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function toString(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return fallback;
}

function toNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function optionalNumber(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") {
    return undefined;
  }
  return toNumber(value, Number.NaN);
}

function toArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function toFiniteNumber(value: unknown, fallback = 0): number {
  const parsed = toNumber(value, fallback);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function firstArray(raw: unknown, keys: string[]): unknown[] {
  const record = asRecord(raw);
  for (const key of keys) {
    const value = record[key];
    if (Array.isArray(value)) return value;
  }
  return [];
}

function firstRecord(raw: unknown, keys: string[]): Record<string, unknown> {
  const record = asRecord(raw);
  for (const key of keys) {
    const value = record[key];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }
  }
  return record;
}

function normalizeMetricCard(item: unknown, fallbackLabel = ""): BiMetricCard {
  const record = asRecord(item);
  const rawValue = record.value ?? record.count ?? record.total ?? record.amount ?? record.rate ?? record.score;
  return {
    label: toString(record.label ?? record.name ?? record.title, fallbackLabel),
    value:
      typeof rawValue === "number" || typeof rawValue === "string"
        ? rawValue
        : toString(rawValue, "--"),
    hint: toString(record.hint ?? record.description ?? record.note ?? record.subtitle, ""),
    delta: toString(record.delta ?? record.change ?? record.trend ?? record.growth ?? record.diff, ""),
    tone:
      record.tone === "good" || record.tone === "warning" || record.tone === "critical"
        ? (record.tone as BiMetricCard["tone"])
        : "neutral",
  };
}

function normalizeRankItem(item: unknown, fallbackLabel = ""): BiRankItem {
  const record = asRecord(item);
  return {
    label: toString(record.label ?? record.name ?? record.key ?? record.title, fallbackLabel),
    value: toNumber(record.value ?? record.count ?? record.total ?? record.amount ?? record.score, 0),
    rate: optionalNumber(record.rate ?? record.success_rate),
    hint: toString(record.hint ?? record.description ?? record.note ?? record.subtitle, ""),
    secondary: toString(record.secondary ?? record.extra ?? record.detail, ""),
  };
}

function normalizeTrendPoint(item: unknown, fallbackLabel = ""): BiTrendPoint {
  const record = asRecord(item);
  return {
    label: toString(record.label ?? record.date ?? record.day ?? record.time ?? record.name, fallbackLabel),
    active: toNumber(record.active ?? record.active_learners ?? record.value ?? record.count, 0),
    cost: toNumber(record.cost ?? record.cost_usd ?? record.amount ?? record.expense, 0),
    successful: toNumber(record.successful ?? record.success ?? record.success_rate ?? record.rate, 0),
  };
}

function normalizeCohort(item: unknown, fallbackLabel = ""): BiRetentionCohort {
  const record = asRecord(item);
  const values = toArray(record.values ?? record.points ?? record.rates ?? record.matrix ?? []);
  return {
    label: toString(record.label ?? record.name ?? record.cohort ?? record.key, fallbackLabel),
    values: values.map((value) => toNumber(value, 0)),
  };
}

function normalizeAlert(item: unknown, fallbackLabel = ""): BiAlertItem {
  const record = asRecord(item);
  const level = record.level === "critical" || record.level === "warning" ? record.level : "info";
  return {
    level,
    title: toString(record.title ?? record.label ?? record.name, fallbackLabel),
    detail: toString(record.detail ?? record.description ?? record.note ?? record.subtitle, ""),
  };
}

function normalizeMetricDefinition(item: unknown, fallbackLabel = ""): BiMetricDefinition {
  const record = asRecord(item);
  return {
    metric_id: toString(record.metric_id ?? record.metricId ?? record.id, ""),
    label: toString(record.label ?? record.name ?? record.title, fallbackLabel),
    group: toString(record.group ?? record.category, ""),
    definition: toString(record.definition ?? record.description ?? record.note, ""),
    authority: toString(record.authority ?? record.source, ""),
    trustLevel: toString(record.trust_level ?? record.trustLevel ?? record.trust, ""),
    owner: toString(record.owner ?? record.responsible, ""),
    drilldown: toString(record.drilldown ?? record.drill_down ?? record.target, ""),
    displayHint: toString(record.display_hint ?? record.displayHint ?? record.hint, ""),
  };
}

function normalizeNorthStarPayload(raw: unknown): BiNorthStarPayload | undefined {
  const record = asRecord(firstRecord(raw, ["north_star", "northStar"]));
  if (!Object.keys(record).length) return undefined;
  const metric = normalizeMetricDefinition(record, "有效学习成功会员数");
  return {
    ...metric,
    value: toNumber(record.value, 0),
    windowDays: toNumber(record.window_days ?? record.windowDays, 30),
    calculation: toString(record.calculation ?? record.formula, ""),
    inputs: firstArray(record, ["inputs", "drivers", "tree"]).map((item, index) => {
      const inputRecord = asRecord(item);
      return {
        ...normalizeMetricDefinition(item, `输入 ${index + 1}`),
        value:
          inputRecord.value === null
            ? null
            : typeof inputRecord.value === "number" || typeof inputRecord.value === "string"
              ? inputRecord.value
              : undefined,
      };
    }),
  };
}

function normalizeGrowthFunnelPayload(raw: unknown): BiGrowthFunnelPayload | undefined {
  const record = asRecord(firstRecord(raw, ["growth_funnel", "growthFunnel"]));
  if (!Object.keys(record).length) return undefined;
  return {
    title: toString(record.title, "增长漏斗"),
    summary: toString(record.summary ?? record.description, ""),
    steps: firstArray(record, ["steps", "items", "funnel"]).map((item, index) => {
      const step = asRecord(item);
      return {
        id: toString(step.id ?? step.metric_id ?? step.metricId, `step-${index + 1}`),
        label: toString(step.label ?? step.name ?? step.title, `步骤 ${index + 1}`),
        value: toNumber(step.value ?? step.count, 0),
        conversionRate: toNumber(step.conversion_rate ?? step.conversionRate ?? step.rate, 0),
        trustLevel: toString(step.trust_level ?? step.trustLevel, ""),
        authority: toString(step.authority ?? step.source, ""),
        drilldown: toString(step.drilldown ?? step.target, ""),
      };
    }),
  };
}

function normalizeMemberHealthPayload(raw: unknown): BiMemberHealthPayload | undefined {
  const record = asRecord(firstRecord(raw, ["member_health", "memberHealth"]));
  if (!Object.keys(record).length) return undefined;
  const scoreRecord = asRecord(record.score);
  return {
    score: {
      ...normalizeMetricDefinition(scoreRecord, "会员健康评分"),
      value: optionalNumber(scoreRecord.value),
      note: toString(scoreRecord.note ?? scoreRecord.summary, ""),
    },
    distribution: firstArray(record, ["distribution", "buckets"]).map((item, index) => {
      const bucket = asRecord(item);
      return {
        bucket: toString(bucket.bucket ?? bucket.id, `bucket-${index + 1}`),
        label: toString(bucket.label ?? bucket.name, `分层 ${index + 1}`),
        count: toNumber(bucket.count ?? bucket.value, 0),
      };
    }),
    reasons: firstArray(record, ["reasons", "recommendations"]).map((item) => toString(item)).filter(Boolean),
    samples: firstArray(record, ["samples", "members", "items"]).map((item) => {
      const row = asRecord(item);
      return {
        user_id: toString(row.user_id ?? row.id ?? row.key),
        display_name: toString(row.display_name ?? row.name ?? row.nickname, "未命名用户"),
        tier: toString(row.tier ?? row.plan ?? row.level, ""),
        status: toString(row.status ?? row.state, ""),
        risk_level: toString(row.risk_level ?? row.risk, ""),
        last_active_at: toString(row.last_active_at ?? row.updated_at ?? row.created_at, ""),
        detail: toString(row.detail ?? row.subtitle ?? row.note, ""),
      };
    }),
  };
}

function normalizeOperatingRhythmPayload(raw: unknown): BiOperatingRhythmPayload | undefined {
  const record = asRecord(firstRecord(raw, ["operating_rhythm", "operatingRhythm"]));
  if (!Object.keys(record).length) return undefined;
  return {
    cadences: firstArray(record, ["cadences", "rhythms"]).map((item, index) => {
      const cadence = asRecord(item);
      return {
        id: toString(cadence.id, `cadence-${index + 1}`),
        label: toString(cadence.label ?? cadence.name, `节奏 ${index + 1}`),
        focus: toString(cadence.focus ?? cadence.detail, ""),
      };
    }),
    topActions: firstArray(record, ["top_actions", "topActions", "actions"]).map((item, index) => {
      const action = asRecord(item);
      return {
        title: toString(action.title ?? action.label, `动作 ${index + 1}`),
        target: toString(action.target ?? action.drilldown, ""),
        status: toString(action.status ?? action.state, ""),
        reason: toString(action.reason ?? action.detail, ""),
      };
    }),
  };
}

function normalizeTeachingEffectPayload(raw: unknown): BiTeachingEffectPayload | undefined {
  const record = asRecord(firstRecord(raw, ["teaching_effect", "teachingEffect"]));
  if (!Object.keys(record).length) return undefined;
  return {
    status: toString(record.status, ""),
    summary: toString(record.summary ?? record.description, ""),
    chapterProgress: firstArray(record, ["chapter_progress", "chapterProgress", "chapters"]).map((item, index) => {
      const chapter = asRecord(item);
      return {
        chapterId: toString(chapter.chapter_id ?? chapter.chapterId ?? chapter.id, `chapter-${index + 1}`),
        name: toString(chapter.name ?? chapter.label ?? chapter.title, `章节 ${index + 1}`),
        mastery: toNumber(chapter.mastery ?? chapter.score ?? chapter.value, 0),
        memberCount: toNumber(chapter.member_count ?? chapter.memberCount ?? chapter.members, 0),
        status: toString(chapter.status ?? chapter.state, ""),
        evidence: toString(chapter.evidence ?? chapter.detail ?? chapter.note, ""),
      };
    }),
    metrics: firstArray(record, ["metrics", "items"]).map((item, index) => {
      const metric = asRecord(item);
      return {
        ...normalizeMetricDefinition(item, `教学指标 ${index + 1}`),
        value:
          metric.value === null
            ? null
            : typeof metric.value === "number" || typeof metric.value === "string"
              ? metric.value
              : undefined,
        status: toString(metric.status, ""),
      };
    }),
  };
}

function normalizeAiQualityPayload(raw: unknown): BiAiQualityPayload | undefined {
  const record = asRecord(firstRecord(raw, ["ai_quality", "aiQuality"]));
  if (!Object.keys(record).length) return undefined;
  return {
    ...normalizeMetricDefinition(record, "AI 教学质量分"),
    engineeringSuccessRate: toNumber(record.engineering_success_rate ?? record.engineeringSuccessRate, 0),
    failedTurns: toNumber(record.failed_turns ?? record.failedTurns, 0),
    totalTurns: toNumber(record.total_turns ?? record.totalTurns, 0),
    teachingSuccessStatus: toString(record.teaching_success_status ?? record.teachingSuccessStatus, ""),
    note: toString(record.note ?? record.summary, ""),
    samples: firstArray(record, ["samples", "items"]).map((item) => {
      const sample = asRecord(item);
      return {
        turn_id: toString(sample.turn_id ?? sample.turnId ?? sample.id, ""),
        session_id: toString(sample.session_id ?? sample.sessionId, ""),
        status: toString(sample.status, ""),
      };
    }),
  };
}

function normalizeUnitEconomicsPayload(raw: unknown): BiUnitEconomicsPayload | undefined {
  const record = asRecord(firstRecord(raw, ["unit_economics", "unitEconomics"]));
  if (!Object.keys(record).length) return undefined;
  return {
    ...normalizeMetricDefinition(record, "单有效学习成本"),
    revenueStatus: toString(record.revenue_status ?? record.revenueStatus, ""),
    summary: toString(record.summary ?? record.description, ""),
    windowTotalCostUsd: toNumber(record.window_total_cost_usd ?? record.windowTotalCostUsd, 0),
    costPerEffectiveLearningUsd: toNumber(
      record.cost_per_effective_learning_usd ?? record.costPerEffectiveLearningUsd,
      0,
    ),
    source: toString(record.source, ""),
  };
}

function normalizeDataTrustPayload(raw: unknown): BiDataTrustPayload | undefined {
  const record = asRecord(firstRecord(raw, ["data_trust", "dataTrust"]));
  if (!Object.keys(record).length) return undefined;
  return {
    status: toString(record.status, ""),
    trustModel: toString(record.trust_model ?? record.trustModel, ""),
    degradedModules: firstArray(record, ["degraded_modules", "degradedModules"]).map((item, index) => {
      const degradedModule = asRecord(item);
      return {
        id: toString(degradedModule.id, `module-${index + 1}`),
        label: toString(degradedModule.label ?? degradedModule.name, `模块 ${index + 1}`),
        status: toString(degradedModule.status, ""),
        detail: toString(degradedModule.detail ?? degradedModule.description, ""),
      };
    }),
    metricDefinitions: firstArray(record, ["metric_definitions", "metricDefinitions", "metrics"]).map((item, index) =>
      normalizeMetricDefinition(item, `指标 ${index + 1}`),
    ),
  };
}

function toBossTone(level: BiAlertItem["level"]): BiMetricCard["tone"] {
  if (level === "critical") return "critical";
  if (level === "warning") return "warning";
  return "neutral";
}

function normalizeBossActionSource(record: Record<string, unknown>): BiBossActionItem["source"] {
  const direct = record.source;
  if (direct === "anomalies" || direct === "members" || direct === "cost") {
    return direct;
  }
  const bucket = toString(record.bucket, "");
  if (bucket === "high_risk" || bucket === "expiring_soon") {
    return "members";
  }
  if (bucket === "cost" || bucket === "daily_cost") {
    return "cost";
  }
  return "anomalies";
}

function normalizeBossActionItem(item: unknown, fallbackLabel = ""): BiBossActionItem {
  const record = asRecord(item);
  const handoffRecord = asRecord(record.handoff_filters ?? record.handoffFilters);
  const handoffFilters: Record<string, string | number | boolean | null> = {};

  Object.entries(handoffRecord).forEach(([key, value]) => {
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean" ||
      value === null
    ) {
      handoffFilters[key] = value;
    }
  });

  return {
    title: toString(record.title ?? record.label ?? record.name ?? record.bucket, fallbackLabel),
    detail: toString(record.detail ?? record.description ?? record.hint ?? record.note, ""),
    tone:
      record.tone === "good" || record.tone === "warning" || record.tone === "critical"
        ? (record.tone as BiMetricCard["tone"])
        : "neutral",
    source: normalizeBossActionSource(record),
    handoffFilters: Object.keys(handoffFilters).length ? handoffFilters : undefined,
  };
}

function normalizeBossDailyCost(raw: unknown): BiBossDailyCost | undefined {
  const record = asRecord(firstRecord(raw, ["daily_cost", "dailyCost", "cost_daily"]));
  const hasDailyCost =
    Object.keys(record).length > 0 &&
    ("today_usd" in record || "todayUsd" in record || "window_total_usd" in record || "series" in record);
  if (!hasDailyCost) {
    return undefined;
  }
  const series = firstArray(record, ["series", "points", "items"]).map((item, index) => {
    const point = asRecord(item);
    return {
      date: toString(point.date ?? point.day ?? point.label, ""),
      label: toString(point.label ?? point.date ?? point.day, `Day ${index + 1}`),
      costUsd: toNumber(point.cost_usd ?? point.costUsd ?? point.cost ?? point.amount, 0),
      tokens: toNumber(point.tokens ?? point.total_tokens ?? point.totalTokens, 0),
      turns: toNumber(point.turns ?? point.count ?? point.requests, 0),
    };
  });
  return {
    todayUsd: toNumber(record.today_usd ?? record.todayUsd ?? record.today ?? record.cost_today, 0),
    windowTotalUsd: toNumber(record.window_total_usd ?? record.windowTotalUsd ?? record.total_usd ?? record.total, 0),
    averageDailyUsd: toNumber(record.average_daily_usd ?? record.averageDailyUsd ?? record.avg_daily_usd ?? record.average, 0),
    source: toString(record.source ?? record.provider, ""),
    series,
  };
}

function normalizeBossWorkbench(raw: unknown, fallbackHeroIssue = ""): BiBossWorkbench | undefined {
  const record = asRecord(firstRecord(raw, ["boss_workbench", "boss", "workbench"]));
  const hasBossPayload = Object.keys(record).length > 0 && ("kpis" in record || "risk_queue" in record || "hero_issue" in record);
  if (!hasBossPayload) {
    return undefined;
  }

  return {
    kpis: firstArray(record, ["kpis", "cards", "metrics"]).map((item, index) => normalizeMetricCard(item, `老板 KPI ${index + 1}`)),
    actionQueue: firstArray(record, ["risk_queue", "actionQueue", "action_queue", "queue"]).map((item, index) =>
      normalizeBossActionItem(item, `待办 ${index + 1}`),
    ),
    heroIssue: toString(record.hero_issue ?? record.heroIssue ?? record.issue, fallbackHeroIssue),
    dailyCost: normalizeBossDailyCost(record),
  };
}

function normalizeTutorBot(item: unknown, fallbackLabel = ""): BiTutorBotItem {
  const record = asRecord(item);
  return {
    bot_id: toString(record.bot_id ?? record.id ?? record.key, fallbackLabel),
    name: toString(record.name ?? record.title ?? record.label, fallbackLabel),
    capability: toString(record.capability ?? record.mode, ""),
    entrypoint: toString(record.entrypoint ?? record.source ?? record.channel, ""),
    tier: toString(record.tier ?? record.plan ?? record.level, ""),
    status: toString(record.status ?? record.state ?? record.running_state, ""),
    last_active_at: toString(record.last_active_at ?? record.updated_at ?? record.last_seen_at, ""),
    recent_message: toString(record.recent_message ?? record.message_preview ?? record.preview ?? record.detail, ""),
    runs: optionalNumber(record.runs ?? record.run_count ?? record.count),
    success_rate: optionalNumber(record.success_rate ?? record.success ?? record.rate),
    detail: toString(record.detail ?? record.description ?? record.note, ""),
  };
}

function buildBiUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const url = new URL(apiUrl(path));
  Object.entries(params ?? {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    url.searchParams.set(key, String(value));
  });
  return url.toString();
}

async function fetchBiJson(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<unknown> {
  const response = await fetch(buildBiUrl(path, params), {
    cache: "no-store",
    headers: withAdminAuthorization(BI_API_TOKEN ? withBiApiToken() : undefined),
  });
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status} ${path}`);
  }
  return response.json();
}

function normalizeLearnerProfile(raw: unknown): BiMetricCard[] {
  return firstArray(raw, ["profile", "summary", "cards", "metrics", "kpis"]).map((item, index) =>
    normalizeMetricCard(item, `画像 ${index + 1}`),
  );
}

function normalizeLearnerSessions(raw: unknown): BiLearnerSession[] {
  return firstArray(raw, ["recent_sessions", "sessions", "conversation_history", "history", "items"]).map((item, index) => {
    const record = asRecord(item);
    return {
      session_id: toString(record.session_id ?? record.id ?? record.key, `session-${index + 1}`),
      title: toString(record.title ?? record.name ?? record.topic ?? record.summary, `会话 ${index + 1}`),
      capability: toString(record.capability ?? record.mode, ""),
      status: toString(record.status ?? record.state, ""),
      started_at: toString(record.started_at ?? record.start_at ?? record.created_at, ""),
      ended_at: toString(record.ended_at ?? record.end_at ?? record.updated_at, ""),
      duration_minutes: optionalNumber(record.duration_minutes ?? record.duration_min ?? record.minutes),
      summary: toString(record.summary ?? record.detail ?? record.note, ""),
    };
  });
}

function normalizeLearnerMastery(raw: unknown): BiLearnerChapterMastery[] {
  return firstArray(raw, ["chapter_mastery", "mastery", "chapters", "items"]).map((item, index) => {
    const record = asRecord(item);
    return {
      chapter_id: toString(record.chapter_id ?? record.id ?? record.key, ""),
      name: toString(record.name ?? record.title ?? record.chapter ?? record.label, `章节 ${index + 1}`),
      mastery: toFiniteNumber(record.mastery ?? record.score ?? record.rate ?? record.value, 0),
      hint: toString(record.hint ?? record.description ?? record.note, ""),
      evidence: toString(record.evidence ?? record.example ?? record.detail, ""),
    };
  });
}

function normalizeLearnerNotes(raw: unknown): BiLearnerNoteLedgerSummary {
  const record = asRecord(firstRecord(raw, ["notes_summary", "summary", "ledger", "wallet", "data"]));
  return {
    notes_count: optionalNumber(record.notes_count ?? record.note_count ?? record.total_notes),
    pinned_notes_count: optionalNumber(record.pinned_notes_count ?? record.pinned_count),
    recent_note: toString(record.recent_note ?? record.latest_note ?? record.note_preview, ""),
    recent_ledger: toString(record.recent_ledger ?? record.latest_ledger ?? record.ledger_preview, ""),
    wallet_balance: optionalNumber(record.wallet_balance ?? record.balance ?? record.points_balance),
    ledger_delta: optionalNumber(record.ledger_delta ?? record.delta),
    summary: toString(record.summary ?? record.detail ?? record.note, ""),
  };
}

const BOSS_ACTION_COPY = {
  anomalyDetail: "建议尽快复核该异常信号。",
  memberRiskDetail: "建议跟进高风险会员变化。",
  costDetail: "建议持续观察成本波动。",
} as const;

function buildBossKpis(data: BiWorkbenchData): BiBossKpiItem[] {
  const kpis: BiBossKpiItem[] = [];
  const seen = new Set<string>();

  const append = (items: BiMetricCard[], source: BiBossKpiItem["source"]) => {
    for (const item of items) {
      const label = item.label.trim();
      if (!label || seen.has(label)) continue;
      seen.add(label);
      kpis.push({ ...item, source });
      if (kpis.length >= 5) return;
    }
  };

  append(data.overview.cards, "overview");
  if (kpis.length < 5) append(data.members.cards, "members");
  if (kpis.length < 5) append(data.cost.cards, "cost");

  return kpis;
}

function buildBossActionQueue(data: BiWorkbenchData): BiBossActionItem[] {
  const queue: BiBossActionItem[] = [];
  const seen = new Set<string>();

  const append = (title: string, detail: string, tone: BiMetricCard["tone"], source: BiBossActionItem["source"]) => {
    const key = `${title}::${detail}`;
    if (!title || seen.has(key)) return;
    seen.add(key);
    queue.push({ title, detail, tone, source });
  };

  for (const item of data.anomalies.items) {
    append(
      item.title,
      item.detail || BOSS_ACTION_COPY.anomalyDetail,
      toBossTone(item.level),
      "anomalies",
    );
    if (queue.length >= 4) break;
  }

  if (queue.length < 4) {
    for (const item of data.members.risks) {
      append(
        `会员风险：${item.label}`,
        item.hint || item.secondary || BOSS_ACTION_COPY.memberRiskDetail,
        "warning",
        "members",
      );
      if (queue.length >= 4) break;
    }
  }

  if (queue.length < 4) {
    for (const item of data.cost.cards) {
      append(
        `成本关注：${item.label}`,
        item.hint || item.delta || BOSS_ACTION_COPY.costDetail,
        item.tone ?? "neutral",
        "cost",
      );
      if (queue.length >= 4) break;
    }
  }

  return queue;
}

function buildBossDailyCost(data: BiWorkbenchData): BiBossDailyCost {
  const series = data.trend.points.map((point) => ({
    date: point.label,
    label: point.label,
    costUsd: point.cost,
    tokens: 0,
    turns: point.successful,
  }));
  const windowTotalUsd = series.reduce((sum, point) => sum + point.costUsd, 0);
  return {
    todayUsd: series.length ? series[series.length - 1].costUsd : 0,
    windowTotalUsd,
    averageDailyUsd: series.length ? windowTotalUsd / series.length : 0,
    source: "active_trend_fallback",
    series,
  };
}

function buildBossHeroIssue(missingCoreModules: BiBossCoreModule[]): string {
  if (missingCoreModules.length === 0) {
    return "";
  }

  const scope = missingCoreModules.length === 1 ? "1 个" : `${missingCoreModules.length} 个`;
  return `有 ${scope}核心经营模块暂未返回，老板首页先基于已成功模块装配。`;
}

function buildBiBossWorkbench(data: BiWorkbenchData, missingCoreModules: BiBossCoreModule[]): BiBossWorkbench {
  return {
    kpis: buildBossKpis(data),
    actionQueue: buildBossActionQueue(data),
    heroIssue: buildBossHeroIssue(missingCoreModules),
    dailyCost: buildBossDailyCost(data),
  };
}

type BiOverviewBundle = {
  overview: BiOverviewData;
  bossWorkbench?: BiBossWorkbench;
};

function parseBiOverviewBundle(raw: unknown): BiOverviewBundle {
  const record = asRecord(firstRecord(raw, ["overview", "data", "summary"]));
  const cards = firstArray(raw, ["cards", "kpis", "metrics"]).map((item, index) =>
    normalizeMetricCard(item, `KPI ${index + 1}`),
  );
  const highlights = firstArray(raw, ["highlights", "recommendations", "insights", "summary"]).map((item) =>
    toString(item),
  );
  const entrypoints = firstArray(raw, ["entrypoints", "channels", "sources"]).map((item, index) =>
    normalizeRankItem(item, `入口 ${index + 1}`),
  );
  const alerts = firstArray(raw, ["alerts", "warnings", "anomalies"]).map((item, index) =>
    normalizeAlert(item, `告警 ${index + 1}`),
  );
  const overview: BiOverviewData = {
    title: toString(record.title ?? record.name, "DeepTutor BI 工作台"),
    subtitle: toString(
      record.subtitle ?? record.description ?? record.summary,
      "加载后端 BI 接口后即可查看经营、学习、能力、知识库与会员的统一视图。",
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
  };

  return {
    overview,
    bossWorkbench: normalizeBossWorkbench(raw),
  };
}

export async function getBiOverview(options: BiFetchOptions = {}): Promise<BiOverviewData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/overview", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  return parseBiOverviewBundle(raw).overview;
}

export async function getBiActiveTrend(options: BiFetchOptions = {}): Promise<BiTrendData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/active-trend", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  const points = firstArray(raw, ["points", "series", "items", "trend"]).map((item, index) =>
    normalizeTrendPoint(item, `Day ${index + 1}`),
  );
  return { points };
}

export async function getBiRetention(options: BiFetchOptions = {}): Promise<BiRetentionData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/retention", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  const record = asRecord(firstRecord(raw, ["retention", "data", "summary"]));
  const cohorts = firstArray(raw, ["cohorts", "rows", "items", "matrix"]).map((item, index) =>
    normalizeCohort(item, `Cohort ${index + 1}`),
  );
  const labels =
    firstArray(raw, ["labels", "columns", "days", "periods"]).map((item) => toString(item)) ||
    [];

  return {
    cohorts,
    labels: labels.length
      ? labels
      : toArray(record.labels).map((item) => toString(item)).filter(Boolean),
  };
}

export async function getBiCapabilities(options: BiFetchOptions = {}): Promise<BiCapabilityData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/capabilities", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  return {
    items: firstArray(raw, ["items", "capabilities", "rows", "series"]).map((item, index) =>
      normalizeRankItem(item, `Capability ${index + 1}`),
    ),
    upgradePaths: firstArray(raw, ["upgrade_paths", "paths", "funnels", "conversions"]).map((item, index) =>
      normalizeRankItem(item, `Path ${index + 1}`),
    ),
  };
}

export async function getBiTools(options: BiFetchOptions = {}): Promise<BiToolData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/tools", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  return {
    items: firstArray(raw, ["items", "tools", "rows", "series"]).map((item, index) =>
      normalizeRankItem(item, `Tool ${index + 1}`),
    ),
    efficiency: firstArray(raw, ["efficiency", "quadrants", "value_lines", "roi"]).map((item, index) =>
      normalizeRankItem(item, `Efficiency ${index + 1}`),
    ),
  };
}

export async function getBiKnowledge(options: BiFetchOptions = {}): Promise<BiKnowledgeData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/knowledge", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  const record = asRecord(firstRecord(raw, ["knowledge", "data", "summary"]));
  return {
    items: firstArray(raw, ["items", "kbs", "knowledge_bases", "rows"]).map((item, index) =>
      normalizeRankItem(item, `KB ${index + 1}`),
    ),
    topQueries: firstArray(raw, ["top_queries", "queries", "hot_queries", "items"]).map((item, index) =>
      normalizeRankItem(item, `Query ${index + 1}`),
    ),
    zeroHitRate: optionalNumber(record.zero_hit_rate ?? record.zero_result_rate),
  };
}

export async function getBiMembers(options: BiFetchOptions = {}): Promise<BiMemberData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/members", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  const samples = firstArray(raw, ["samples", "items", "recent", "list"]).map((item) => {
    const row = asRecord(item);
    return {
      user_id: toString(row.user_id ?? row.id ?? row.key),
      display_name: toString(row.display_name ?? row.name ?? row.nickname, "未命名用户"),
      tier: toString(row.tier ?? row.plan ?? row.level, ""),
      status: toString(row.status ?? row.state, ""),
      risk_level: toString(row.risk_level ?? row.risk, ""),
      last_active_at: toString(row.last_active_at ?? row.updated_at ?? row.created_at, ""),
      detail: toString(row.detail ?? row.subtitle ?? row.note, ""),
    };
  });

  return {
    cards: firstArray(raw, ["cards", "metrics", "kpis"]).map((item, index) =>
      normalizeMetricCard(item, `Member KPI ${index + 1}`),
    ),
    tiers: firstArray(raw, ["tiers", "tier_breakdown", "segments"]).map((item, index) =>
      normalizeRankItem(item, `Tier ${index + 1}`),
    ),
    risks: firstArray(raw, ["risks", "risk_breakdown", "risk_levels"]).map((item, index) =>
      normalizeRankItem(item, `Risk ${index + 1}`),
    ),
    samples,
  };
}

export async function getBiCost(options: BiFetchOptions = {}): Promise<BiCostData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/cost", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  return {
    cards: firstArray(raw, ["cards", "metrics", "kpis"]).map((item, index) =>
      normalizeMetricCard(item, `Cost KPI ${index + 1}`),
    ),
    models: firstArray(raw, ["models", "model_breakdown", "providers"]).map((item, index) =>
      normalizeRankItem(item, `Model ${index + 1}`),
    ),
    providers: firstArray(raw, ["providers", "sources", "usage_sources"]).map((item, index) =>
      normalizeRankItem(item, `Provider ${index + 1}`),
    ),
  };
}

export async function getBiTutorBots(options: BiFetchOptions = {}): Promise<BiTutorBotData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/tutorbots", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );

  return {
    cards: firstArray(raw, ["cards", "metrics", "kpis"]).map((item, index) =>
      normalizeMetricCard(item, `TutorBot KPI ${index + 1}`),
    ),
    ranking: firstArray(raw, ["ranking", "items", "bots", "rows", "series"]).map((item, index) =>
      normalizeRankItem(item, `Bot ${index + 1}`),
    ),
    statusBreakdown: firstArray(raw, ["status_breakdown", "status", "states", "running_status"]).map((item, index) =>
      normalizeRankItem(item, `状态 ${index + 1}`),
    ),
    recentActive: firstArray(raw, ["recent_active", "active", "samples", "recent", "list"]).map((item, index) =>
      normalizeTutorBot(item, `Bot ${index + 1}`),
    ),
    recentMessages: firstArray(raw, ["recent_messages", "messages", "message_previews", "previews"]).map((item, index) =>
      normalizeTutorBot(item, `Message ${index + 1}`),
    ),
  };
}

export async function getBiAnomalies(options: BiFetchOptions = {}): Promise<BiAnomalyData> {
  const raw = unwrapPayload(
    await fetchBiJson("/api/v1/bi/anomalies", {
      days: options.days,
      capability: options.capability,
      entrypoint: options.entrypoint,
      tier: options.tier,
    }),
  );
  return {
    items: firstArray(raw, ["items", "alerts", "warnings", "anomalies"]).map((item, index) =>
      normalizeAlert(item, `异常 ${index + 1}`),
    ),
  };
}

export async function getBiLearnerDetail(userId: string, options: BiFetchOptions = {}): Promise<BiLearnerDetailData> {
  const raw = unwrapPayload(await fetchBiJson(`/api/v1/bi/learner/${encodeURIComponent(userId)}`, { days: options.days }));
  const record = asRecord(firstRecord(raw, ["learner", "data", "detail", "profile", "summary"]));
  const notesSummary = normalizeLearnerNotes(raw);
  const displayName = toString(record.display_name ?? record.name ?? record.nickname, "未命名用户");

  return {
    user_id: toString(record.user_id ?? record.id ?? userId, userId),
    display_name: displayName,
    profile: normalizeLearnerProfile(raw),
    recent_sessions: normalizeLearnerSessions(raw),
    chapter_mastery: normalizeLearnerMastery(raw),
    notes_summary: {
      ...notesSummary,
      summary: toString(notesSummary.summary, ""),
    },
  };
}

export async function loadBiWorkbench(options: BiFetchOptions = {}): Promise<BiWorkbenchState> {
  const results = await Promise.allSettled([
    (async () => {
      const raw = unwrapPayload(
        await fetchBiJson("/api/v1/bi/overview", {
          days: options.days,
          capability: options.capability,
          entrypoint: options.entrypoint,
          tier: options.tier,
        }),
      );
      return parseBiOverviewBundle(raw);
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
  ]);

  const issues: string[] = [];
  const moduleIssues: BiWorkbenchModuleIssues = {};
  const missingCoreModules: BiBossCoreModule[] = [];
  const data = structuredClone(DEFAULT_DATA);
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
  ] = results;
  let overviewBossWorkbench: BiBossWorkbench | undefined;

  if (overview.status === "fulfilled") {
    data.overview = overview.value.overview;
    overviewBossWorkbench = overview.value.bossWorkbench;
  }
  else {
    missingCoreModules.push("overview");
    moduleIssues.overview = overview.reason instanceof Error ? overview.reason.message : "概览加载失败";
    issues.push(moduleIssues.overview);
  }

  if (trend.status === "fulfilled") data.trend = trend.value;
  else {
    missingCoreModules.push("active-trend");
    moduleIssues.trend = trend.reason instanceof Error ? trend.reason.message : "趋势加载失败";
    issues.push(moduleIssues.trend);
  }

  if (retention.status === "fulfilled") data.retention = retention.value;
  else {
    moduleIssues.retention = retention.reason instanceof Error ? retention.reason.message : "留存加载失败";
    issues.push(moduleIssues.retention);
  }

  if (capabilities.status === "fulfilled") data.capabilities = capabilities.value;
  else {
    moduleIssues.capabilities = capabilities.reason instanceof Error ? capabilities.reason.message : "能力加载失败";
    issues.push(moduleIssues.capabilities);
  }

  if (tools.status === "fulfilled") data.tools = tools.value;
  else {
    moduleIssues.tools = tools.reason instanceof Error ? tools.reason.message : "工具加载失败";
    issues.push(moduleIssues.tools);
  }

  if (knowledge.status === "fulfilled") data.knowledge = knowledge.value;
  else {
    moduleIssues.knowledge = knowledge.reason instanceof Error ? knowledge.reason.message : "知识库加载失败";
    issues.push(moduleIssues.knowledge);
  }

  if (members.status === "fulfilled") data.members = members.value;
  else {
    missingCoreModules.push("members");
    moduleIssues.members = members.reason instanceof Error ? members.reason.message : "会员加载失败";
    issues.push(moduleIssues.members);
  }

  if (cost.status === "fulfilled") data.cost = cost.value;
  else {
    missingCoreModules.push("cost");
    moduleIssues.cost = cost.reason instanceof Error ? cost.reason.message : "成本加载失败";
    issues.push(moduleIssues.cost);
  }

  if (tutorbots.status === "fulfilled") data.tutorbots = tutorbots.value;
  else {
    moduleIssues.tutorbots = tutorbots.reason instanceof Error ? tutorbots.reason.message : "TutorBot 加载失败";
    issues.push(moduleIssues.tutorbots);
  }

  if (anomalies.status === "fulfilled") data.anomalies = anomalies.value;
  else {
    moduleIssues.anomalies = anomalies.reason instanceof Error ? anomalies.reason.message : "异常加载失败";
    issues.push(moduleIssues.anomalies);
  }

  return {
    data,
    issues,
    boss: overviewBossWorkbench ?? buildBiBossWorkbench(data, missingCoreModules),
    moduleIssues,
  };
}
