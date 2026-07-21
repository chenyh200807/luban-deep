// BI v2 feature flags. Each key is a public boolean — values are surfaced to the
// browser via page.tsx → BiV2Surface props. Never reuse these names for secrets.
//
// Server reads `BI_<KEY>` env (operator ergonomic, dev-friendly). Client-side
// code (if any) must only use `NEXT_PUBLIC_BI_<KEY>` so Next.js compiles the
// value into the bundle. The two helpers below are explicit about who reads what.

export type BiFlagKey =
  | "BI_BACKOFFICE_V2_SHELL_ENABLED"
  | "BI_CRM_V2_ENABLED"
  | "BI_OVERVIEW_V2_ENABLED"
  | "BI_COMMERCE_V2_ENABLED"
  | "BI_FEEDBACK_V2_ENABLED"
  | "BI_SYSTEM_OPS_V2_ENABLED"
  | "BI_LEARNING_PREF_V2_ENABLED";

export type BiFlagSnapshot = Record<BiFlagKey, boolean>;

const FLAG_KEYS: readonly BiFlagKey[] = [
  "BI_BACKOFFICE_V2_SHELL_ENABLED",
  "BI_CRM_V2_ENABLED",
  "BI_OVERVIEW_V2_ENABLED",
  "BI_COMMERCE_V2_ENABLED",
  "BI_FEEDBACK_V2_ENABLED",
  "BI_SYSTEM_OPS_V2_ENABLED",
  "BI_LEARNING_PREF_V2_ENABLED",
] as const;

const TRUE_TOKENS = new Set(["1", "true", "yes", "on"]);

function isTrueToken(value: string | undefined): boolean {
  return TRUE_TOKENS.has(String(value ?? "").toLowerCase());
}

// Server-only. Call from a Server Component (page.tsx) or build script. Reads
// both `BI_<KEY>` (operator convenience) and `NEXT_PUBLIC_BI_<KEY>` (CI / Vercel
// preview parity). Result is forwarded to client as plain booleans — never an
// arbitrary env string — so there is no leak of unrelated server vars even if
// they share a name (the BiFlagKey union is closed and explicit).
export function readBiFlagsFromEnv(env: NodeJS.ProcessEnv = process.env): BiFlagSnapshot {
  const snapshot = {} as BiFlagSnapshot;
  for (const key of FLAG_KEYS) {
    snapshot[key] = isTrueToken(env[`NEXT_PUBLIC_${key}`]) || isTrueToken(env[key]);
  }
  return snapshot;
}

// Client-safe. Only reads `NEXT_PUBLIC_BI_<KEY>` so Next.js can inline the value
// into the client bundle. Use this if any future client-only path needs to
// inspect flags without prop drilling.
export function readBiFlagsFromClientEnv(env: NodeJS.ProcessEnv = process.env): BiFlagSnapshot {
  const snapshot = {} as BiFlagSnapshot;
  for (const key of FLAG_KEYS) {
    snapshot[key] = isTrueToken(env[`NEXT_PUBLIC_${key}`]);
  }
  return snapshot;
}

export function defaultBiFlags(): BiFlagSnapshot {
  return {
    BI_BACKOFFICE_V2_SHELL_ENABLED: false,
    BI_CRM_V2_ENABLED: false,
    BI_OVERVIEW_V2_ENABLED: false,
    BI_COMMERCE_V2_ENABLED: false,
    BI_FEEDBACK_V2_ENABLED: false,
    BI_SYSTEM_OPS_V2_ENABLED: false,
    BI_LEARNING_PREF_V2_ENABLED: false,
  };
}

export const BI_FLAG_KEYS = FLAG_KEYS;
