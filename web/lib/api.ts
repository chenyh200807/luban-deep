// API configuration and utility functions

const CURRENT_ORIGIN_SENTINEL = "__CURRENT_ORIGIN__";

// Keep the injected API base when it exists. Otherwise, browser surfaces fall back
// to the current origin so IP and domain entrances can both use same-origin `/api/...`.
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE?.trim() || "";
export const BI_API_TOKEN = process.env.NEXT_PUBLIC_BI_API_TOKEN?.trim() || "";

function resolveApiBaseUrl(): string {
  if (API_BASE_URL && API_BASE_URL !== CURRENT_ORIGIN_SENTINEL) {
    return API_BASE_URL;
  }

  if (typeof window !== "undefined" && window.location.origin) {
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

export function withBiApiToken(headers?: HeadersInit): HeadersInit | undefined {
  if (!BI_API_TOKEN) {
    return headers;
  }

  const merged = new Headers(headers ?? {});
  merged.set("X-Metrics-Token", BI_API_TOKEN);
  return Object.fromEntries(merged.entries());
}
