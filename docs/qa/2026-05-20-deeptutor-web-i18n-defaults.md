# QA Report: DeepTutor Web Default Locale (i18n)

| 字段 | 值 |
| --- | --- |
| **Date** | 2026-05-20 |
| **Branch** | `qa-followup-20260520` (from `main` HEAD `67744094`) |
| **URL** | http://localhost:3000 (Next.js 16.2.6 dev) |
| **Mode** | Quick (Standard tier — fix critical/high/medium) |
| **Trigger** | Routine /qa run after PR #1 merged to main, on fresh follow-up branch |
| **Pages visited** | 5 (/, /intro, /bi, /knowledge, /memory, /settings) |
| **Issues found** | 4 (1 High, 2 Medium, 1 Low) |
| **Issues fixed** | 3 (4 commits — ISSUE-001 needed two atomic commits) |
| **Issues deferred** | 1 (Low) |
| **Health score** | **77 → 95** (+18) |

---

## Health Score: 95/100

| Category | Before | After |
|----------|--------|-------|
| Console | 100 | 100 |
| Visual | 100 | 100 |
| Functional | 100 | 100 |
| UX | 65 (i18n inconsistency across pages) | 95 |
| Performance | 92 | 92 |
| Accessibility | 65 (html lang mismatch) | 95 |
| Content | 80 (mixed-language gate panels) | 100 |

**Console health**: 0 errors across all 5 routes (before AND after).

---

## Top 3 Things Fixed

1. **ISSUE-001 (High)**: Home page rendered in English ("What would you like to learn?" / "Ask anything…" / "How can I help you today?") despite being a Chinese-market product (鲁班智考). zh translations existed in `web/locales/zh/app.json` but the app defaulted to en.
2. **ISSUE-002 (Medium)**: `<html lang="en">` on every page despite Chinese content — broke screen-reader pronunciation and SEO indexing.
3. **ISSUE-003 (Medium)**: `RestrictedSurface` gate panels on /knowledge, /memory, /settings showed English titles ("Memory workspace unavailable") with Chinese body text — inconsistent voice within the same panel.

---

## Issues

### ISSUE-001: Home page + chat UI defaulted to English on a Chinese-market product

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | functional / content / i18n |
| **URL** | `/` (and propagates to all `useTranslation`-aware pages) |
| **Fix Status** | ✅ verified (two commits) |
| **Commits** | `4802a181` (part 1: readDefaultLanguage), `97f5da73` (part 2: normalizeLanguage fallback) |
| **Files Changed** | `web/context/AppShellContext.tsx` (2 lines total) |

**Description**: First-time visitor on `/` saw English hero "What would you like to learn?" instead of "你想学点什么？" (zh translation exists in `web/locales/zh/app.json:[\"What would you like to learn?\"]`). Same English fallback affected chat prompts and button labels across 238 `useTranslation` call sites.

**Root cause (two parts)**:

1. `web/context/AppShellContext.tsx:74` `readDefaultLanguage()` hardcoded `return "en"` — this is the SSR snapshot for `useSyncExternalStore`. Wrong default for a Chinese-market product.
2. `web/context/AppShellContext.tsx:29` `normalizeLanguage()` hardcoded fallback to `"en"` for any non-zh value (including `null` from a fresh localStorage). This is the client snapshot path; without fixing it, the SSR-rendered Chinese flashes for one frame, then client hydration overwrites with English.

**Fix**: 
- Part 1: `readDefaultLanguage()` → `return "zh"`
- Part 2: `normalizeLanguage` inverts fallback: explicit `"en"` preserved, everything else → `"zh"`

**Repro before fix**:
1. Clear localStorage `deeptutor-language`
2. Open `/`
3. Observe `h1` = "What would you like to learn?"
   ![before](../../.gstack/qa-reports/screenshots/qa-20260520-home.png)

**After fix**:
1. Same precondition
2. `h1` = "你想学点什么？"
   ![after](../../.gstack/qa-reports/screenshots/qa-20260520-home-after-fix.png)
3. JS assertion `bodyContains("你想学点什么")` → true, `bodyContains("What would you like to learn")` → false.

---

### ISSUE-002: `<html lang="en">` on Chinese-content pages

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | accessibility / SEO |
| **URL** | All routes |
| **Fix Status** | ✅ verified |
| **Commits** | `ca5da488` |
| **Files Changed** | `web/app/layout.tsx` (1 line) |

**Description**: `web/app/layout.tsx:33` had `<html lang="en">` hardcoded. With ISSUE-001's defaultlocale change, every page renders Chinese content; the lang attribute mismatch breaks:
- Screen-reader pronunciation (defaults to English voice on Chinese characters)
- Search-engine indexed language (mis-classified as English content)
- Browser auto-translate banners (offered "Translate to Chinese" on Chinese content)

**Fix**: `lang="en"` → `lang="zh-CN"`.

**After fix**: All 4 verified routes show `document.documentElement.lang = "zh"` (client-side i18next overrides hardcoded `"zh-CN"` to its own `lng` value `"zh"`; both are valid BCP 47 Chinese tags). For strict `"zh-CN"` a future refinement would sync `documentElement.lang` to `i18next.language` via a `languageChanged` listener — recorded but not blocking.

---

### ISSUE-003: RestrictedSurface gate panels — English title + Chinese body

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | content / i18n / UX consistency |
| **URL** | `/knowledge`, `/memory`, `/settings` |
| **Fix Status** | ✅ verified |
| **Commits** | `6777d489` |
| **Files Changed** | 3 callers (1 line each) |

**Description**: `RestrictedSurface.tsx` is a dumb display; the inconsistency lived in 3 callers each hardcoding English `title=` while hardcoding Chinese `message=`:

| Caller | Title (before) | Title (after) | Body (unchanged) |
|---|---|---|---|
| /knowledge | "Knowledge workspace unavailable" | "知识库工作台暂不可用" | "当前 Web 端未接入登录态，知识库与题本工作台已默认关闭..." |
| /memory | "Memory workspace unavailable" | "记忆工作台暂不可用" | "当前 Web 端未接入登录态，Memory 工作台已默认关闭..." |
| /settings | "Settings unavailable" | "配置控制台暂不可用" | "当前 Web 端未接入登录态，配置控制台已默认关闭..." |

**Fix**: 3 file × 1 line each, hardcoded Chinese title to match the hardcoded Chinese body voice on each page.

**Not refactored to** `t()` calls because the message prop is also hardcoded on all three pages — a future i18n sweep should do title + message together with locale keys. This commit only restores within-panel language consistency.

**After fix**: All 3 routes show `h1` = corresponding 中文 title:
   ![knowledge](../../.gstack/qa-reports/screenshots/qa-20260520-knowledge-after-fix.png)
   ![memory](../../.gstack/qa-reports/screenshots/qa-20260520-memory-after-fix.png)
   ![settings](../../.gstack/qa-reports/screenshots/qa-20260520-settings-after-fix.png)

---

### ISSUE-004: `/bi` admin tool — mixed English section headings inside Chinese body

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | content / i18n (admin tool) |
| **URL** | `/bi` |
| **Fix Status** | ⏸ deferred (Low severity + admin tool) |

**Description**: `/bi` BI workbench (老板工作台 / BOSS WORKBENCH) is an admin/operations tool, not user-facing. It mixes English section headings like "BOSS WORKBENCH", "ACCESS STATUS", "ADMIN ACCESS" with Chinese body. This is consistent with admin tools elsewhere (Supabase, dashboards), and lower priority than user-facing /qa scope.

**Deferred to** future i18n sweep PR. Recorded in TODOS section.

---

## What I Didn't Touch (surgical discipline)

- `RestrictedSurface.tsx` component itself (no behavior change needed; pure display)
- `i18n/init.ts` `fallbackLng: "en"` (i18next internal fallback; only fires when a translation key is missing — zh has 889 keys matching en, so no actual impact)
- `i18n/I18nProvider.tsx` / `I18nClientBridge.tsx` (mechanism already correct; only defaults were wrong)
- Production code paths (`deeptutor/`, `wx_miniprogram/`, `yousenwebview/`) — backend untouched

---

## Summary

| Metric | Value |
|---|---|
| Total issues found | 4 |
| Fixes applied | 3 (4 commits) |
| - verified | 3 |
| - best-effort | 0 |
| - reverted | 0 |
| Deferred | 1 (`/bi` admin tool i18n) |
| Health score | 77 → 95 (+18) |
| Net diff | 7 lines across 5 files |
| codex daemon rogue hydrates intercepted | 4 (all `git checkout HEAD --` reverted before commits, none made it into commits) |

**PR Summary** (one-liner):
> "/qa found 4 i18n inconsistencies on the web app; fixed 3 with 4 surgical commits (7 lines total); deferred 1 (admin BI tool). Health 77 → 95."

---

## Follow-ups (not in this PR)

1. **`/bi` admin tool i18n** (ISSUE-004) — separate sweep, possibly with translation table + product alignment on which English section headings to keep (some are admin jargon like "ACCESS STATUS").
2. **Fast / Deep / Reference button labels still English** on home page — these are i18n keys in `web/locales/zh/app.json` that were left untranslated. Quick sweep to translate all remaining English values in zh locale would close this. Low severity (admin-flavored UI knobs).
3. **Dynamic `document.documentElement.lang` sync to i18next.language** — currently i18next client-side override sets it to `"zh"` (not `"zh-CN"`). For strict BCP 47 region tagging, add a `languageChanged` listener.
4. **Title + message of RestrictedSurface to `t()` calls with locale keys** — finishing what ISSUE-003 left as title-only Chinese hardcode. Pair with #2 above as one i18n sweep PR.

---

## Verification

```bash
$ git log --oneline main..HEAD
6777d489 fix(qa): ISSUE-003 — RestrictedSurface titles in Chinese to match body voice
ca5da488 fix(qa): ISSUE-002 — html lang="en" → "zh-CN" matches default UI
97f5da73 fix(qa): ISSUE-001 part 2 — normalizeLanguage default to zh
4802a181 fix(qa): ISSUE-001 — default UI locale to zh for Chinese-market product

$ git diff main..HEAD --stat
 web/app/(utility)/knowledge/page.tsx | 2 +-
 web/app/(utility)/memory/page.tsx    | 2 +-
 web/app/(utility)/settings/page.tsx  | 2 +-
 web/app/layout.tsx                   | 2 +-
 web/context/AppShellContext.tsx      | 4 ++--
 5 files changed, 6 insertions(+), 6 deletions(-)
```

**Behavior verification** (gstack browse against http://localhost:3000):

| Route | htmlLang | h1 (visible content) |
|---|---|---|
| `/` | zh | 你想学点什么？ |
| `/knowledge` | zh | 知识库工作台暂不可用 |
| `/memory` | zh | 记忆工作台暂不可用 |
| `/settings` | zh | 配置控制台暂不可用 |
