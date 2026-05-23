#!/usr/bin/env node
// Round 4 S4 — production bundle must not ship BI v2 mock fixtures.
//
// Rationale: panels under app/(workspace)/bi/_v2/* import MOCK_MEMBERS,
// ANOMALIES, FEEDBACK_ITEMS, AUDIT_ENTRIES, EXPORT_JOBS, MOCK_BUNDLE, etc.
// These are now wrapped in `process.env.NODE_ENV === 'production' ? [] : [...]`
// so Next.js + Terser should dead-code-eliminate the literal in production
// builds. This script is the post-build enforcement: after `next build`,
// grep .next/static/chunks for the SHOULD-NOT-EXIST literal strings; any hit
// means a mock fixture leaked into the production bundle and CI must fail.
//
// Usage: `npm run check:mock-boundary` (runs `next build` then this script).
//
// Why grep instead of a webpack analyzer: see spec auditor Round 3 — grep is
// 5 lines, deterministic, requires no plugin, and the question is binary
// ("string present yes/no"). Bundle analyzer would be over-engineering.

import { readdirSync, readFileSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";

const CHUNKS_DIR = join(process.cwd(), ".next", "static", "chunks");

// Distinctive strings from each MOCK fixture. Chosen so a substring match on
// minified JS still triggers (these are unusual phrases not appearing in
// production copy or labels). Add new entries here when introducing new
// mocks under a dev-only guard.
// Each literal MUST appear ONLY inside a `process.env.NODE_ENV !== 'production'`
// branch in the BI v2 codebase. Strings that double as both real UI copy and
// mock fixtures (e.g. "WALLET_NEGATIVE_BALANCE" — also used in CommercePanel
// to describe the detection rule) cannot be used here. Pick the most
// distinctive fragment from each mock literal that has no production use.
const FORBIDDEN_LITERALS = [
  // member-ops/data.ts SEED_MEMBERS — distinctive masked phone with personal digits
  "138****9821",
  // commerce/data.ts ORDERS — distinctive ord_2026 prefix used only in mock
  "ord_2026_05231042",
  // commerce/data.ts LEDGER — distinctive ledger id from seed
  '"lg_001"',
  // feedback/data.ts FEEDBACK_ITEMS — distinctive feedback id
  "fb_9012",
  // ops/data.ts AUDIT_ENTRIES — quoted al_1 id; UI never quotes raw ids in copy
  '"al_1"',
  // ops/data.ts EXPORT_JOBS — quoted ex_001 id
  '"ex_001"',
  // BiV2OverviewPanel.tsx MOCK_BUNDLE — distinctive Chinese phrase only in alerts mock
  "钱包出现负余额会员 3 位",
  // ConversationReviewDrawer.tsx MOCK_SESSIONS — distinctive session title only in mock
  "牛顿第二定律",
];

if (!existsSync(CHUNKS_DIR)) {
  console.error(
    `check:mock-boundary: ${CHUNKS_DIR} does not exist. Run \`next build\` first.`,
  );
  process.exit(2);
}

function* walkFiles(dir) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      yield* walkFiles(full);
    } else if (st.isFile() && /\.(js|mjs|cjs)$/i.test(name)) {
      yield full;
    }
  }
}

const offenders = [];
for (const file of walkFiles(CHUNKS_DIR)) {
  const content = readFileSync(file, "utf-8");
  for (const literal of FORBIDDEN_LITERALS) {
    if (content.includes(literal)) {
      offenders.push({ file, literal });
    }
  }
}

if (offenders.length > 0) {
  console.error("\nFAIL: mock fixtures leaked into production bundle:");
  for (const { file, literal } of offenders) {
    console.error(`  ${literal}  →  ${file.replace(process.cwd() + "/", "")}`);
  }
  console.error(
    "\nMock data must be guarded by `process.env.NODE_ENV === 'production' ? [] : [...]`",
  );
  console.error(
    "so Next.js + Terser dead-code-eliminates the literal. See web/app/(workspace)/bi/_v2/member-ops/data.ts for the pattern.",
  );
  process.exit(1);
}

console.log("OK · production bundle does not contain BI v2 mock fixtures");
