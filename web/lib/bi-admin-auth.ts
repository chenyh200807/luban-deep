import { type BiAdminSession, apiUrl, setStoredBiAdminSession } from "@/lib/api";
import { ApiError } from "@/lib/api-errors";

type AuthLoginResponse = {
  user_id: string;
  token: string;
  expires_at: number;
  user?: {
    display_name?: string;
    user_id?: string;
  };
};

type AuthProfileResponse = {
  user_id: string;
  display_name?: string;
  is_admin?: boolean;
};

async function expectJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown };
      detail = String(payload.detail ?? payload.message ?? "").trim();
    } catch {
      detail = "";
    }
    throw new ApiError(response.status, detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchBiAdminProfile(token: string): Promise<AuthProfileResponse> {
  const response = await fetch(apiUrl("/api/v1/auth/profile"), {
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return expectJson<AuthProfileResponse>(response);
}

export async function loginBiAdmin(username: string, password: string): Promise<BiAdminSession> {
  const response = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const login = await expectJson<AuthLoginResponse>(response);
  const profile = await fetchBiAdminProfile(login.token);
  if (!profile.is_admin) {
    throw new ApiError(403, "当前账号不是管理员，无法解锁会员后台。");
  }

  const session: BiAdminSession = {
    token: login.token,
    userId: profile.user_id || login.user_id,
    displayName:
      profile.display_name?.trim() ||
      login.user?.display_name?.trim() ||
      login.user?.user_id?.trim() ||
      login.user_id,
    isAdmin: true,
    expiresAt: Number(login.expires_at || 0),
  };
  setStoredBiAdminSession(session);
  return session;
}
