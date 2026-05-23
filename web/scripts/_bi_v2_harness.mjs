// Shared harness for BI v2 smoke / contract tests.
//
// Round 3 introduces a `<RequireBiAdmin>` boundary that hides every panel
// behind an authentication check. Tests must inject a fake admin session via
// localStorage BEFORE any navigation, otherwise the page only renders the
// "login required" prompt and panel selectors will time out. This module
// centralises that setup so per-test scripts stay thin.

const SESSION_STORAGE_KEY = "deeptutor.bi.admin.session";

// Minimal session shape compatible with `isBiAdminSession` in web/lib/api.ts.
// Fields chosen to make audits / smoke reports easy to spot:
//   - userId = "smoke@admin"  → distinguishable from real production actors
//   - isAdmin = true          → passes RequireBiAdmin gate
//   - expiresAt = +1 day      → safely in future for the run
export function buildFakeAdminSession({
  userId = "smoke@admin",
  displayName = "Smoke Admin",
  token = "smoke-token",
} = {}) {
  return {
    token,
    userId,
    displayName,
    isAdmin: true,
    expiresAt: Date.now() + 24 * 3600 * 1000,
  };
}

// Inject the session before the document loads. Using addInitScript ensures
// useSyncExternalStore's `getClientSnapshot` sees it on mount, so the very
// first render passes RequireBiAdmin.
export async function withAdminSession(context, session = buildFakeAdminSession()) {
  await context.addInitScript(
    ({ key, value }) => {
      try {
        window.localStorage.setItem(key, value);
      } catch {
        // ignore quota / privacy mode in tests
      }
    },
    { key: SESSION_STORAGE_KEY, value: JSON.stringify(session) },
  );
}

// Default tolerable console filter — used by all smoke. dev / unauthenticated
// backend returns 4xx/5xx for /api/v1/bi/* which is by design; tests should
// not fail on those.
export function tolerableConsole(text) {
  if (/Failed to load resource: the server responded with a status of (4\d\d|5\d\d)/.test(text)) {
    return true;
  }
  if (text.includes("/api/v1/bi/") || text.includes("/api/v1/member/")) return true;
  return false;
}
