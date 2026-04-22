import test from "node:test";
import assert from "node:assert/strict";

import { ApiError } from "../lib/api-errors";
import { getMemberDashboard } from "../lib/member-api";
import { clearStoredBiAdminSession, getStoredBiAdminSession } from "../lib/api";
import {
  loginBiAdmin,
  restoreBiAdminSession,
  type RestoreBiAdminSessionResult,
} from "../lib/bi-admin-auth";

type MockResponseInit = {
  ok: boolean;
  status: number;
  json: unknown;
};

function createStorage() {
  const store = new Map<string, string>();
  return {
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null;
    },
    setItem(key: string, value: string) {
      store.set(key, String(value));
    },
    removeItem(key: string) {
      store.delete(key);
    },
    clear() {
      store.clear();
    },
  };
}

function installWindow() {
  const localStorage = createStorage();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: { origin: "https://test2.yousenjiaoyu.com" },
      localStorage,
    },
  });
  return localStorage;
}

function mockJsonResponse(init: MockResponseInit): Response {
  return {
    ok: init.ok,
    status: init.status,
    async json() {
      return init.json;
    },
  } as Response;
}

async function withMockFetch<T>(
  impl: (input: string | URL | Request, init?: RequestInit) => Promise<Response>,
  fn: () => Promise<T>,
): Promise<T> {
  const original = globalThis.fetch;
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: impl,
  });
  try {
    return await fn();
  } finally {
    Object.defineProperty(globalThis, "fetch", {
      configurable: true,
      value: original,
    });
  }
}

function assertRestoreResult(
  actual: RestoreBiAdminSessionResult,
  expected: RestoreBiAdminSessionResult,
) {
  assert.deepEqual(actual, expected);
}

test("loginBiAdmin establishes admin session from auth login only", async () => {
  installWindow();
  const calls: string[] = [];

  const session = await withMockFetch(async (input) => {
    calls.push(String(input));
    return mockJsonResponse({
      ok: true,
      status: 200,
      json: {
        user_id: "admin_demo",
        token: "token-1",
        expires_at: 9999999999,
        is_admin: true,
        user: {
          user_id: "admin_demo",
          display_name: "管理员",
          is_admin: true,
        },
      },
    });
  }, () => loginBiAdmin("admin_demo", "good-password"));

  assert.equal(calls.length, 1);
  assert.match(calls[0], /\/api\/v1\/auth\/login$/);
  assert.equal(session.userId, "admin_demo");
  assert.equal(session.displayName, "管理员");
  assert.equal(session.isAdmin, true);
  assert.equal(getStoredBiAdminSession()?.token, "token-1");
  clearStoredBiAdminSession();
});

test("loginBiAdmin rejects non-admin accounts", async () => {
  installWindow();

  await assert.rejects(
    () =>
      withMockFetch(
        async () =>
          mockJsonResponse({
            ok: true,
            status: 200,
            json: {
              user_id: "student_demo",
              token: "token-1",
              expires_at: 9999999999,
              is_admin: false,
              user: {
                user_id: "student_demo",
                display_name: "学生",
                is_admin: false,
              },
            },
          }),
        () => loginBiAdmin("student_demo", "good-password"),
      ),
    (error: unknown) => error instanceof ApiError && error.status === 403,
  );
});

test("restoreBiAdminSession preserves stored session on transient upstream failure", async () => {
  installWindow();
  const stored = {
    token: "token-1",
    userId: "admin_demo",
    displayName: "管理员",
    isAdmin: true,
    expiresAt: 9999999999,
  };

  const result = await withMockFetch(
    async () => {
      throw new ApiError(503, "Wallet service unavailable");
    },
    () => restoreBiAdminSession(stored),
  );

  assertRestoreResult(result, {
    session: stored,
    clearStoredSession: false,
    errorMessage: "管理员会话校验暂时失败，请稍后重试。",
  });
});

test("restoreBiAdminSession clears stored session on auth failure", async () => {
  installWindow();
  const stored = {
    token: "token-1",
    userId: "admin_demo",
    displayName: "管理员",
    isAdmin: true,
    expiresAt: 9999999999,
  };

  const result = await withMockFetch(
    async () => {
      throw new ApiError(401, "Invalid or expired token");
    },
    () => restoreBiAdminSession(stored),
  );

  assertRestoreResult(result, {
    session: null,
    clearStoredSession: true,
    errorMessage: "Invalid or expired token",
  });
});

test("member api attaches Authorization header from stored admin session", async () => {
  installWindow();
  const localStorage = window.localStorage;
  localStorage.setItem(
    "deeptutor.bi.admin.session",
    JSON.stringify({
      token: "token-1",
      userId: "admin_demo",
      displayName: "管理员",
      isAdmin: true,
      expiresAt: 9999999999,
    }),
  );

  let capturedAuthorization = "";
  await withMockFetch(async (_input, init) => {
    const headers = new Headers(init?.headers ?? {});
    capturedAuthorization = headers.get("Authorization") || "";
    return mockJsonResponse({
      ok: true,
      status: 200,
      json: {
        total_count: 1,
        active_count: 1,
        expiring_soon_count: 0,
        new_today_count: 0,
        churn_risk_count: 0,
        health_score: 100,
        auto_renew_coverage: 1,
        tier_breakdown: [],
        expiry_breakdown: [],
        recommendations: [],
      },
    });
  }, async () => {
    await getMemberDashboard();
  });

  assert.equal(capturedAuthorization, "Bearer token-1");
});
