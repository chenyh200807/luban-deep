// API configuration and utility functions

const CURRENT_ORIGIN_SENTINEL = "__CURRENT_ORIGIN__";

// Keep the injected API base when it exists. Local development can still fall
// back to the current origin; production must receive an explicit API base.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE?.trim() || "";
const BI_ADMIN_SESSION_STORAGE_KEY = "deeptutor.bi.admin.session";
export const BI_ADMIN_SESSION_CHANGED_EVENT = "deeptutor.bi.admin.session.changed";

export type BiAdminSession = {
  token: string;
  userId: string;
  displayName: string;
  /** Legacy full-admin flag. BI workspace access is determined by biRole/access. */
  isAdmin: boolean;
  biRole?: string;
  biRoleLabel?: string;
  canManagePermissions?: boolean;
  accessibleTabs?: string[];
  biMatrix?: Record<string, string[]>;
  expiresAt: number;
};

function isBiAdminSession(value: unknown): value is BiAdminSession {
  if (!value || typeof value !== "object") {
    return false;
  }

  const record = value as Record<string, unknown>;
  const accessibleTabs = record.accessibleTabs;
  return (
    typeof record.token === "string" &&
    typeof record.userId === "string" &&
    typeof record.displayName === "string" &&
    typeof record.isAdmin === "boolean" &&
    typeof record.biRole === "string" &&
    record.biRole.trim().length > 0 &&
    Array.isArray(accessibleTabs) &&
    accessibleTabs.length > 0 &&
    accessibleTabs.every(tab => typeof tab === "string" && tab.trim().length > 0) &&
    typeof record.expiresAt === "number"
  );
}

function resolveApiBaseUrl(): string {
  if (API_BASE_URL && API_BASE_URL !== CURRENT_ORIGIN_SENTINEL) {
    return API_BASE_URL;
  }

  if (
    process.env.NODE_ENV !== "production" &&
    typeof window !== "undefined" &&
    window.location.origin
  ) {
    return window.location.origin;
  }

  throw new Error(
    "NEXT_PUBLIC_API_BASE is not configured. Please set it in your environment and restart.",
  );
}

/**
 * Construct a full API URL from a path
 * @param path - API path (e.g., '/api/v1/knowledge/list')
 * @returns Full URL (e.g., 'http://localhost:8001/api/v1/knowledge/list')
 */
export function apiUrl(path: string): string {
  // Remove leading slash if present to avoid double slashes
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  // Remove trailing slash from base URL if present
  const resolvedBase = resolveApiBaseUrl();
  const base = resolvedBase.endsWith("/")
    ? resolvedBase.slice(0, -1)
    : resolvedBase;

  return `${base}${normalizedPath}`;
}

/**
 * Construct a WebSocket URL from a path
 * @param path - WebSocket path (e.g., '/api/v1/solve')
 * @returns WebSocket URL (e.g., 'ws://localhost:8001/api/v1/ws')
 */
export function wsUrl(path: string): string {
  // Security Hardening: Convert http to ws and https to wss.
  // In production environments (where API_BASE_URL starts with https), this ensures secure websockets.
  const resolvedBase = resolveApiBaseUrl();
  const base = resolvedBase.replace(/^http:/, "ws:").replace(/^https:/, "wss:");

  // Remove leading slash if present to avoid double slashes
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  // Remove trailing slash from base URL if present
  const normalizedBase = base.endsWith("/") ? base.slice(0, -1) : base;

  return `${normalizedBase}${normalizedPath}`;
}

export function getStoredBiAdminSession(): BiAdminSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(BI_ADMIN_SESSION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!isBiAdminSession(parsed)) {
      window.localStorage.removeItem(BI_ADMIN_SESSION_STORAGE_KEY);
      return null;
    }
    if (parsed.expiresAt > 0 && parsed.expiresAt <= Math.floor(Date.now() / 1000)) {
      window.localStorage.removeItem(BI_ADMIN_SESSION_STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function setStoredBiAdminSession(session: BiAdminSession): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(BI_ADMIN_SESSION_STORAGE_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(BI_ADMIN_SESSION_CHANGED_EVENT));
}

export function clearStoredBiAdminSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(BI_ADMIN_SESSION_STORAGE_KEY);
  window.dispatchEvent(new Event(BI_ADMIN_SESSION_CHANGED_EVENT));
}

export function withAdminAuthorization(headers?: HeadersInit): HeadersInit | undefined {
  const session = getStoredBiAdminSession();
  const token = session?.token?.trim();
  if (!token) {
    return headers;
  }

  const merged = new Headers(headers ?? {});
  merged.set("Authorization", `Bearer ${token}`);
  return Object.fromEntries(merged.entries());
}
