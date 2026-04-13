import { apiUrl } from "@/lib/api";

export interface MemberDashboard {
  total_count: number;
  active_count: number;
  expiring_soon_count: number;
  new_today_count: number;
  churn_risk_count: number;
  health_score: number;
  auto_renew_coverage: number;
  tier_breakdown: Array<{ tier: string; count: number }>;
  expiry_breakdown: Array<{ label: string; count: number }>;
  recommendations: string[];
}

export interface MemberListItem {
  user_id: string;
  display_name: string;
  phone: string;
  tier: string;
  status: string;
  segment: string;
  risk_level: string;
  auto_renew: boolean;
  expire_at: string;
  created_at: string;
  last_active_at: string;
  points_balance: number;
  review_due: number;
}

export interface MemberListResponse {
  items: MemberListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface MemberNote {
  id: string;
  content: string;
  channel: string;
  pinned: boolean;
  created_at: string;
}

export interface MemberLedgerEntry {
  id: string;
  delta: number;
  reason: string;
  created_at: string;
}

export interface MemberDetail {
  user_id: string;
  display_name: string;
  phone: string;
  tier: string;
  status: string;
  segment: string;
  risk_level: string;
  auto_renew: boolean;
  expire_at: string;
  created_at: string;
  last_active_at: string;
  wallet: {
    balance: number;
    packages: Array<{ id: string; points: number; price: string; badge: string; per: string }>;
  };
  study_days: number;
  review_due: number;
  focus_topic: string;
  exam_date: string;
  daily_target: number;
  difficulty_preference: string;
  explanation_style: string;
  review_reminder: boolean;
  earned_badge_ids: number[];
  chapter_mastery: Record<string, { name: string; mastery: number }>;
  recent_notes: MemberNote[];
  recent_ledger: MemberLedgerEntry[];
}

async function expectJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function getMemberDashboard(): Promise<MemberDashboard> {
  const response = await fetch(apiUrl("/api/v1/member/dashboard"), { cache: "no-store" });
  return expectJson<MemberDashboard>(response);
}

export async function listMembers(params: Record<string, string | number | boolean | undefined>): Promise<MemberListResponse> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === "" || value === "all") return;
    query.set(key, String(value));
  });
  const response = await fetch(apiUrl(`/api/v1/member/list?${query.toString()}`), {
    cache: "no-store",
  });
  return expectJson<MemberListResponse>(response);
}

export async function getMemberDetail(userId: string): Promise<MemberDetail> {
  const response = await fetch(apiUrl(`/api/v1/member/${userId}/360`), {
    cache: "no-store",
  });
  return expectJson<MemberDetail>(response);
}

export async function createMemberNote(userId: string, payload: { content: string; pinned?: boolean; channel?: string }): Promise<MemberNote> {
  const response = await fetch(apiUrl(`/api/v1/member/${userId}/notes`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return expectJson<MemberNote>(response);
}

export async function grantMembership(payload: { user_id: string; days: number; tier: string; reason?: string }): Promise<MemberDetail> {
  const response = await fetch(apiUrl("/api/v1/member/grant"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return expectJson<MemberDetail>(response);
}

export async function updateMembership(payload: {
  user_id: string;
  tier?: string;
  days?: number;
  expire_at?: string;
  auto_renew?: boolean;
  reason?: string;
}): Promise<MemberDetail> {
  const response = await fetch(apiUrl("/api/v1/member/update"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return expectJson<MemberDetail>(response);
}

export async function revokeMembership(payload: { user_id: string; reason?: string }): Promise<MemberDetail> {
  const response = await fetch(apiUrl("/api/v1/member/revoke"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return expectJson<MemberDetail>(response);
}
