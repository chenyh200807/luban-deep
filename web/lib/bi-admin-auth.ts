import { type BiAdminSession, apiUrl, setStoredBiAdminSession } from "./api.ts";
import { ApiError, isAuthUnavailableError } from "./api-errors.ts";

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

type BiRbacMeResponse = {
  user_id?: string;
  role?: string | null;
  role_label?: string;
  can_manage_permissions?: boolean;
  is_full_admin?: boolean;
  accessible_tabs?: string[];
  matrix?: Record<string, string[]>;
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

async function fetchBiRbacMe(token: string): Promise<BiRbacMeResponse> {
  const response = await fetch(apiUrl("/api/v1/bi/rbac/me"), {
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  return expectJson<BiRbacMeResponse>(response);
}

function buildBiSession(input: {
  token: string;
  userId: string;
  displayName: string;
  expiresAt: number;
  loginIsAdmin: boolean;
  rbac: BiRbacMeResponse;
}): BiAdminSession {
  const role = String(input.rbac.role || "").trim();
  const accessibleTabs = Array.isArray(input.rbac.accessible_tabs)
    ? input.rbac.accessible_tabs.filter(tab => typeof tab === "string" && tab.trim())
    : [];
  if (!role || accessibleTabs.length === 0) {
    throw new ApiError(403, "当前账号没有 BI 后台权限，请联系管理员授予角色。");
  }
  return {
    token: input.token,
    userId: String(input.rbac.user_id || input.userId).trim() || input.userId,
    displayName: input.displayName,
    isAdmin: Boolean(input.rbac.is_full_admin || input.loginIsAdmin),
    biRole: role,
    biRoleLabel: String(input.rbac.role_label || role),
    canManagePermissions: Boolean(input.rbac.can_manage_permissions),
    accessibleTabs,
    biMatrix: input.rbac.matrix ?? {},
    expiresAt: Number(input.expiresAt || 0),
  };
}

export async function loginBiAdmin(username: string, password: string): Promise<BiAdminSession> {
  const response = await fetch(apiUrl("/api/v1/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const login = await expectJson<AuthLoginResponse>(response);
  const loginIsAdmin = isAdminLogin(login);
  const userId = login.user?.user_id?.trim() || login.user_id;
  const displayName =
    login.user?.display_name?.trim() ||
    login.user?.user_id?.trim() ||
    login.user_id;
  const rbac = await fetchBiRbacMe(login.token);

  const session = buildBiSession({
    token: login.token,
    userId,
    displayName,
    expiresAt: Number(login.expires_at || 0),
    loginIsAdmin,
    rbac,
  });
  setStoredBiAdminSession(session);
  return session;
}

export async function restoreBiAdminSession(stored: BiAdminSession): Promise<RestoreBiAdminSessionResult> {
  try {
    const profile = await fetchBiAdminProfile(stored.token);
    const rbac = await fetchBiRbacMe(stored.token);
    const displayName = profile.display_name?.trim() || stored.displayName;
    return {
      session: buildBiSession({
        token: stored.token,
        userId: profile.user_id || stored.userId,
        displayName,
        expiresAt: stored.expiresAt,
        loginIsAdmin: Boolean(profile.is_admin || stored.isAdmin),
        rbac,
      }),
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
