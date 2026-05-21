# DeepTutor Web System QA — 2026-05-22

| Field | Value |
| --- | --- |
| Worktree | `/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor-gstack-system-qa-20260522-004708` |
| Branch | `codex/gstack-system-qa-20260522-004708` |
| Baseline | `origin/main` @ `b1b92f10` (Merge PR #8 — includes 22a153a0 dynamic-split + 5cd9caca layout-aware perf) |
| Mode | `/qa` Standard (full sweep, fix Web/CI P0/P1/P2 within scope) |
| Backend | FastAPI offline (port 8001 not bound) — by design; expected 500s on `/api/v1/*` are not bugs |
| Final HEAD | `9627f4f8 fix(qa): /notebook anon RestrictedSurface title to zh for utility-group consistency` |

## 1. Required Automated Checks

| Check | Result |
| --- | --- |
| `cd web && npm run lint` | **0 errors / 66 warnings** (pre-existing i18n / next-image; unchanged before/after) |
| `cd web && npm run build:perf` | **PASS** — all 16 routes under budget; `/settings 5KB / 180KB`, `/notebook 25KB`, `/wechat-harness 194KB`, root-shell `191KB / 220KB` |
| `cd web && node --test tests/wechat-harness-data.test.ts` | **4/4 pass** |
| Playwright `--project=wechat-harness` (dev @ 127.0.0.1:3055) | **11/11 pass** (incl. mobile viewports, tag-chip filter, SSR grading authority leak guard, intro mobile scroll) |
| `node wx_miniprogram/tests/test_answer_leak_attack.js` | **PASS** (8 vectors) |
| `node wx_miniprogram/tests/test_progressive_disclosure_render.js` | **PASS** (6 groups) |
| `node wx_miniprogram/tests/test_ai_message_state.js` | **PASS** (114 assertions) |
| `node wx_miniprogram/tests/test_ws_stream_pure_contract.js` | **PASS** (65 assertions) |
| `node wx_miniprogram/tests/test_stream_token_boundary.js` | **PASS** (2208 assertions, 6 fixtures × 4 chunking strategies) |
| `pytest -q tests/api/test_unified_ws_public_redaction.py` | **13/13 pass** |
| `tsc --noEmit` (web) | clean |

## 2. Browser Sweep — 9 surfaces × 2 viewports

```
PASS desktop /                    status=200
PASS desktop /intro               status=200
PASS desktop /wechat-harness      status=200
PASS desktop /member              status=200
PASS desktop /bi                  status=200
PASS desktop /settings            status=200
PASS desktop /knowledge           status=200
PASS desktop /memory              status=200
PASS desktop /notebook            status=200
PASS mobile  /                    status=200
PASS mobile  /intro               status=200
PASS mobile  /wechat-harness      status=200
PASS mobile  /member              status=200
PASS mobile  /bi                  status=200
PASS mobile  /settings            status=200
PASS mobile  /knowledge           status=200
PASS mobile  /memory              status=200
PASS mobile  /notebook            status=200

SUMMARY: pass=18 warn=0 fail=0
```

Screenshots in `.gstack/qa-reports/screenshots/` (`desktop_<route>.png`, `mobile_<route>.png`, plus `desktop_notebook_after.png` for the fix verification).

### Per-surface observations

| Surface | desktop | mobile | Notes |
| --- | --- | --- | --- |
| `/` | 200 / shell ok | 200 / shell ok | Backend offline → "Models unavailable" pill + disabled send button (graceful degrade). Console 500s on `/api/v1/knowledge/list` + `/api/v1/system/public-capabilities` are backend-absence noise, not web bugs. |
| `/intro` | 200 / scroll=900 | 200 / scroll=812 | Landing renders; mobile viewport flows correctly (intro-page-scroll testid intact per Playwright spec at line 292). |
| `/wechat-harness` | 200 / parity=16/16 | 200 / phone-shell visible | Fixture replay panel, MCQ interaction, learning-brain QA path all functional. SSR-leak Playwright guard at spec:228 passes. |
| `/member` | 200 / BI workbench shell | 200 | Renders BI dashboard shell with KPI placeholders ("等待 BI 接口"). |
| `/bi` | 200 | 200 | Same workbench; shows "401 已读取凭证已加密落盘" pill — expected without admin auth. |
| `/settings` | 200 / RestrictedSurface 中文 | 200 / RestrictedSurface 中文 | Anon path renders dynamic-split `RestrictedSurface` shell only (22a153a0 effect: console chunk not loaded — page entry 5KB). |
| `/knowledge` | 200 / RestrictedSurface 中文 | 200 / RestrictedSurface 中文 | "知识库工作台暂不可用". |
| `/memory` | 200 / RestrictedSurface 中文 | 200 / RestrictedSurface 中文 | "记忆工作台暂不可用". |
| `/notebook` | 200 / **fixed** to 中文 | 200 / **fixed** | "题本工作台暂不可用" (was: "Question notebook unavailable" — see ISSUE-001). |

## 3. Issues Found

### ISSUE-001 — `/notebook` anon RestrictedSurface title is English while all sibling utility routes are Chinese

| Field | Value |
| --- | --- |
| Severity | **P2** |
| Category | i18n / consistency |
| Scope | Web / utility group |
| Root cause | `web/app/(utility)/notebook/page.tsx:594` hard-codes `title="Question notebook unavailable"`, while the paired message and the three sibling routes (`/settings`, `/knowledge`, `/memory`) all render Chinese. Project default voice is zh-CN. |
| Evidence | `desktop_notebook.png` (before, English title) vs `desktop_notebook_after.png` (after, 中文 title). |
| Fix | One-line change to `title="题本工作台暂不可用"`. |
| Commit | `9627f4f8 fix(qa): /notebook anon RestrictedSurface title to zh for utility-group consistency` |
| Files changed | `web/app/(utility)/notebook/page.tsx` (+1 / −1) |
| Verification | HMR probe returns `题本工作台暂不可用`; lint 0 errors; tsc clean; harness data 4/4; Playwright 11/11; build:perf all green; full 9×2 sweep 18/18 PASS after fix. |
| Status | **verified** |

### ISSUE-002 — Workspace-group siblings have the same English-title pattern (deferred)

Same drift in three more files, but the routes sit under a different access gate (legacy-surface flag) and are not in this `/qa` session's target list (user task scope: `/`, `/intro`, `/wechat-harness`, `/member`, `/bi`, `/settings`, `/knowledge`, `/memory`, `/notebook`):

| File | Line | Title |
| --- | --- | --- |
| `web/app/(workspace)/guide/page.tsx` | 428 | `"Guide unavailable"` |
| `web/app/(workspace)/agents/page.tsx` | 155 | `"TutorBot agents unavailable"` |
| `web/app/(workspace)/co-writer/page.tsx` | 1450 | `"Co-writer unavailable"` |

| Field | Value |
| --- | --- |
| Severity | P2 |
| Status | **deferred** — out of `/qa` session target list; can be fixed in a follow-up dedicated to legacy-surface i18n alignment. |

### ISSUE-003 — Turbopack workspace-root inference can fail under nested-worktree layouts (unreproducible on second pass)

Captured once during the initial QA sweep but not reproducible on re-run after the worktree was rebuilt. Originally manifested as `/memory` and `/notebook` returning `ERR_CONNECTION_REFUSED` because Turbopack hit:

```
Error: Next.js inferred your workspace root, but it may not be correct.
   We couldn't find the Next.js package (next/package.json) from the
   project directory: …deeptutor-gstack-system-qa-…/web
○ Compiling /_not-found/page ...
Error: Turbopack build failed with 1 errors
```

Likely root cause: no `package.json` at the worktree root, so Turbopack walks up the filesystem and either (a) finds an unrelated `everything-claude-code/package.json` two levels up, or (b) gives up. On the second run with a fresh `node_modules` the walk succeeded.

| Field | Value |
| --- | --- |
| Severity | P3 (DX flake; only affects dev server under specific timing/state) |
| Status | **monitor** — would harden by setting `turbopack.root` in `web/next.config.js` to `__dirname`. Single-line preventive change but did not reproduce in this session; deferred pending a second sighting. |

## 4. Environment Notes (not bugs)

- **FastAPI backend offline** during this session → `/` and `/bi` show graceful degrade banners; not in scope for `/qa`.
- **Tailwind warning** `content option missing or empty` appeared in dev startup output. Pre-existing; not in scope.
- **Network 4xx/5xx** on anon-gated APIs (`/api/v1/legacy-web/*`, `/api/v1/knowledge/*`) are expected — protect routes are working as designed.

## 5. WeChat Real-Device Release Gates (record only)

Per task scope, this session does NOT touch wx release gates (S3 / S5 / S6 / S8 / S10 / Y1 / Y2). Recorded as still-pending follow-ups. Three known content-redaction gaps remain unresolved (also out of scope):
- `fallback_text_markdown → fallback_text_contains_correct_answer`
- `mcq.options[].text → mcq_option_text_contains_scoring_points`
- `callout_block.content → callout_block_explanation`

## 6. 22a153a0 (settings dynamic-split) Verdict

Already merged via PR #8 to main; `b1b92f10` includes it. `/settings` entry chunk = 5KB (was 32KB before split; was 271KB before layout-aware perf measure + split combined). No new follow-up PR needed.

## 7. Health Score

| Category | Score | Notes |
| --- | --- | --- |
| Console | 100 | 0 errors on 16/18 surfaces; only `/` desktop+mobile has 2 expected backend-absence 500s |
| Links / nav | 100 | All 9 target paths reachable; sidebar nav (新对话 / 聊天 / BI) consistent |
| Visual | 95 | Found 1 outlier title (ISSUE-001) — **fixed** |
| Functional | 100 | Playwright 11/11; harness MCQ flow, parity, scroll, SSR-leak guard all green |
| UX | 95 | RestrictedSurface fallbacks now uniform; intro mobile scroll works |
| Performance | 100 | All routes ≤ budget after layout-aware measure + dynamic-split (PR #7 / #8) |
| Content | 95 | `/notebook` title was English (fixed); `/guide /agents /co-writer` deferred |
| Accessibility | n/a | Not exercised this round |

**Before:** ~95 — surface inconsistency, `/notebook` title English.
**After:** ~99 — issue fixed; one P2 deferred; one P3 flake to monitor.

## 8. Commits in this branch

```
9627f4f8 fix(qa): /notebook anon RestrictedSurface title to zh for utility-group consistency
b1b92f10 Merge pull request #8 from chenyh200807/codex/gstack-qa-web-fix-203011 (= origin/main baseline)
```

`main` is **untouched** beyond `origin/main`. No new PR opened — branch sits unpushed on local worktree pending user decision.

## 9. Recommendation

- Open a small PR for `9627f4f8` (one-line i18n consistency fix) — low risk, atomic, no formatter sprawl.
- Optional follow-up: a dedicated PR to align `/guide /agents /co-writer` legacy-gate titles (ISSUE-002), batched with whatever `legacy-surface` gating cleanup is already planned.
- Watch for ISSUE-003 (Turbopack workspace-root warning) on next `/qa`; if it returns, add `turbopack.root: __dirname` to `web/next.config.js`.
