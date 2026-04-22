import { type BiAdminSession, apiUrl, setStoredBiAdminSession } from "@/lib/api";
import { ApiError, isAuthUnavailableError } from "@/lib/api-errors";

type AuthLoginResponse = {
  user_id: string;
  token: string;
  expires_at: number;
  is_admin?: boolean;
  user?: {
    display_name?: string;
    user_id?: string;
    is_admin?: boolean;
  };
};

type AuthProfileResponse = {
  user_id: string;
  display_name?: string;
  is_admin?: boolean;
};

export type RestoreBiAdminSessionResult = {
  session: BiAdminSession | null;
  clearStoredSession: boolean;
  errorMessage: string;
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

function isAdminLogin(login: AuthLoginResponse): boolean {
  return Boolean(login.is_admin || login.user?.is_admin);
}

export async function loginBiAdmin(username: string, password: string): Promise<BiAdminSession> {
  const response = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const login = await expectJson<AuthLoginResponse>(response);
  if (!isAdminLogin(login)) {
    throw new ApiError(403, "当前账号不是管理员，无法解锁会员后台。");
  }

  const session: BiAdminSession = {
    token: login.token,
    userId: login.user?.user_id?.trim() || login.user_id,
    displayName:
      login.user?.display_name?.trim() ||
      login.user?.user_id?.trim() ||
      login.user_id,
    isAdmin: true,
    expiresAt: Number(login.expires_at || 0),
  };
  setStoredBiAdminSession(session);
  return session;
}

export async function restoreBiAdminSession(stored: BiAdminSession): Promise<RestoreBiAdminSessionResult> {
  try {
    const profile = await fetchBiAdminProfile(stored.token);
    if (!profile.is_admin) {
      return {
        session: null,
        clearStoredSession: true,
        errorMessage: "当前账号不是管理员，无法解锁会员后台。",
      };
    }
    return {
      session: {
        ...stored,
        userId: profile.user_id || stored.userId,
        displayName: profile.display_name?.trim() || stored.displayName,
        isAdmin: true,
      },
      clearStoredSession: false,
      errorMessage: "",
    };
  } catch (error) {
    if (isAuthUnavailableError(error)) {
      return {
        session: null,
        clearStoredSession: true,
        errorMessage: error.message || "管理员登录已失效，请重新登录。",
      };
    }
    return {
      session: stored,
      clearStoredSession: false,
      errorMessage: "管理员会话校验暂时失败，请稍后重试。",
    };
  }
}
