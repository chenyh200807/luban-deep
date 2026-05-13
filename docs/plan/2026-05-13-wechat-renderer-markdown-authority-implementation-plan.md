# WeChat Renderer Markdown Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WeChat teaching-answer rendering behave like one governed renderer, not a pile of Markdown fixes across pages and package mirrors.

**Architecture:** `presentation.blocks` remains the first-class teaching structure. Markdown is a compatibility projection that must pass through one parser/normalizer authority, then fan out to WXML display, copy text, history preview, DevTools fixtures, and the `yousenwebview/packageDeeptutor` mirror. The near-term solution is contract + golden corpus + authority gates; a full CommonMark/GFM parser replacement is a later measured migration, not a blind dependency swap.

**Tech Stack:** WeChat Mini Program JavaScript/WXML, `wx_miniprogram/utils/ai-message-state.js`, `wx_miniprogram/utils/markdown.js`, `wx_miniprogram/utils/markdown-normalize.js`, `wx_miniprogram/utils/render-schema.js`, mirrored `yousenwebview/packageDeeptutor` utilities, Node-based regression tests, WeChat DevTools CLI.

---

## Status

- Status: `Implemented locally for P0-P1 / Proposed for P2-P3`
- Created: 2026-05-13
- Parent plan: [2026-04-16-wechat-structured-teaching-renderer-prd.md](2026-04-16-wechat-structured-teaching-renderer-prd.md)
- Scope:
  - `wx_miniprogram/`
  - `yousenwebview/packageDeeptutor/`
  - teaching-answer Markdown projection and structured renderer authority
- Out of scope:
  - Changing `/api/v1/ws`
  - Upgrading `presentation.blocks` into a public contract
  - Shipping a new Markdown dependency without package-size and behavior evaluation
  - Aliyun backend deployment

## Root-Cause Frame

- One business fact: a generated teaching answer must have one canonical mobile render state, and every visible projection must preserve the intended section structure.
- One authority: `ai-message-state` derives `renderableContent`, `blocks`, `mcqCards`, `hasStructuredContent`, and related render fields. Page code renders or serializes this state; page code must not independently parse Markdown.
- Competing authorities to demote:
  - Page-level Markdown parsing
  - Template-level ordered-list index synthesis
  - Divergent `wx_miniprogram` and `yousenwebview/packageDeeptutor` parser copies
  - Copy or history serializers that reinterpret structure instead of consuming render state
- Canonical path:
  - `presentation.blocks` if present
  - otherwise normalized Markdown text
  - `ai-message-state`
  - `render model blocks`
  - WXML display / copy serializer / history preview / DevTools fixture
- Why not keep patching regex:
  - Regex is acceptable only inside the one compatibility normalizer/parser.
  - Regex must not spread into pages or multiple projection layers.
  - New Markdown shapes must enter a golden corpus before implementation changes.

## Industry Reference

Top Markdown surfaces do not chase every dialect ad hoc:

1. GitHub formalized GitHub Flavored Markdown on top of CommonMark and uses a reference implementation (`cmark-gfm`).
2. CommonMark-style parsers build a block tree and inline tree before rendering, rather than replacing strings directly in templates.
3. Modern parser stacks such as `micromark` expose token/AST-style pipelines and extension points while preserving one parser authority.

DeepTutor should apply the same governance shape at mini-program scale:

1. `presentation.blocks` for first-class teaching structure.
2. A declared Markdown compatibility subset for fallback text.
3. Golden corpus for real production bad cases.
4. One parser/normalizer authority.
5. A measured parser migration plan only after package and behavior gates pass.

## Files

- Modify: `docs/plan/INDEX.md`
- Create: `docs/plan/2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md`
- Create: `tests/fixtures/wechat_markdown_golden_cases.json`
- Create: `wx_miniprogram/tests/test_markdown_golden_corpus.js`
- Already modified in P0:
  - `wx_miniprogram/utils/markdown.js`
  - `wx_miniprogram/utils/markdown-normalize.js`
  - `wx_miniprogram/utils/devtools-markdown-fixtures.js`
  - `wx_miniprogram/tests/test_renderer_authority.js`
  - `wx_miniprogram/tests/test_renderer_parity.js`
  - `wx_miniprogram/tests/test_markdown_regression_fixtures.js`
  - `wx_miniprogram/tests/test_chat_copy_authority.js`
  - mirrored `yousenwebview/packageDeeptutor/utils/*`

## Task 1: Authority Gate

**Files:**
- Test: `wx_miniprogram/tests/test_renderer_authority.js`

- [x] **Step 1: Add a structural test**

Test must assert:

```js
// Page code must import ai-message-state.
source.indexOf('require("../../utils/ai-message-state")') >= 0

// Page code must not import markdown or markdown-normalize directly.
source.indexOf('require("../../utils/markdown")') < 0
source.indexOf('require("../../utils/markdown-normalize")') < 0

// Ordered list labels must come from li.index.
source.indexOf("{{li.index}}.") >= 0
```

- [x] **Step 2: Run authority test**

Run:

```bash
node wx_miniprogram/tests/test_renderer_authority.js
```

Expected:

```text
PASS test_renderer_authority.js
```

## Task 2: Markdown Golden Corpus

**Files:**
- Create: `tests/fixtures/wechat_markdown_golden_cases.json`
- Create: `wx_miniprogram/tests/test_markdown_golden_corpus.js`

- [x] **Step 1: Create corpus with real failure shapes**

Include cases for:

1. Blank-separated ordered sections.
2. Compact ordered markers such as `3.地基与基础工程`.
3. Compact dash bullets such as `-危险源辨识`.
4. Non-sequential source indexes such as `1, 5, 10`.
5. Mixed ordered and unordered sections in one answer.

- [x] **Step 2: Add corpus test**

Test must derive render state through both mini-program surfaces:

```js
var wxState = wxAiState.deriveAiMessageRenderState({ content: input, parseBlocks: true });
var webState = webAiState.deriveAiMessageRenderState({ content: input, parseBlocks: true });
```

It must verify:

1. `wxState` equals `webState`.
2. Ordered indexes match expected indexes.
3. Required text survives in normalized/rendered content.
4. Compact bullet text becomes bullet blocks.

- [x] **Step 3: Run corpus test**

Run:

```bash
node wx_miniprogram/tests/test_markdown_golden_corpus.js
```

Expected:

```text
PASS test_markdown_golden_corpus.js
```

## Task 3: Existing Projection Gates

**Files:**
- Test: `wx_miniprogram/tests/test_renderer_parity.js`
- Test: `wx_miniprogram/tests/test_markdown_regression_fixtures.js`
- Test: `wx_miniprogram/tests/test_chat_copy_authority.js`
- Test: `wx_miniprogram/tests/test_history_display_authority.js`
- Test: `wx_miniprogram/tests/test_structured_block_layout.js`

- [x] **Step 1: Keep wx/WebView renderer parity**

Run:

```bash
node wx_miniprogram/tests/test_renderer_parity.js
```

Expected:

```text
PASS test_renderer_parity.js
```

- [x] **Step 2: Keep DevTools regression samples executable**

Run:

```bash
node wx_miniprogram/tests/test_markdown_regression_fixtures.js
```

Expected:

```text
PASS test_markdown_regression_fixtures.js
```

- [x] **Step 3: Keep copy projection aligned with visible content**

Run:

```bash
node wx_miniprogram/tests/test_chat_copy_authority.js
```

Expected:

```text
PASS test_chat_copy_authority.js
```

- [x] **Step 4: Keep history preview in simplified projection only**

Run:

```bash
node wx_miniprogram/tests/test_history_display_authority.js
```

Expected:

```text
PASS test_history_display_authority.js
```

## Task 4: Parser Replacement Evaluation

**Files:**
- Output: `docs/plan/2026-05-13-wechat-markdown-parser-evaluation.md`

- [x] **Step 1: Measure package impact**

Evaluate `micromark`, `markdown-it`, and current in-house parser against WeChat package size and runtime constraints.

Command shape:

```bash
npm view micromark version dist.unpackedSize
npm view markdown-it version dist.unpackedSize
```

Expected output:

```text
Record exact versions and package-size estimates in the evaluation document.
```

- [x] **Step 2: Compare behavior against corpus**

For each candidate parser, render the same `tests/fixtures/wechat_markdown_golden_cases.json` inputs into a neutral AST or token model.

Expected:

```text
Candidate either preserves expected ordered indexes and bullet boundaries, or documents the adapter needed.
```

- [x] **Step 3: Decide migration**

Only migrate if all are true:

1. Bundle-size increase is acceptable.
2. WXML adapter remains simpler than current parser.
3. Golden corpus passes.
4. Structured `presentation.blocks` remains primary authority.

Decision: do not migrate in this batch. Keep the current in-house parser and normalizer as the single Markdown fallback authority. `micromark` is the better future candidate than `markdown-it` if a replacement is later required, but both candidates need an adapter to preserve DeepTutor's per-item source numbering semantics. See [2026-05-13-wechat-markdown-parser-evaluation.md](2026-05-13-wechat-markdown-parser-evaluation.md).

## Task 5: Release Gate

**Files:**
- Test commands only

- [x] **Step 1: Run focused renderer gate**

Run:

```bash
node wx_miniprogram/tests/test_markdown.js
node wx_miniprogram/tests/test_markdown_normalize.js
node wx_miniprogram/tests/test_markdown_golden_corpus.js
node wx_miniprogram/tests/test_renderer_authority.js
node wx_miniprogram/tests/test_renderer_parity.js
node wx_miniprogram/tests/test_markdown_regression_fixtures.js
node wx_miniprogram/tests/test_ai_message_state.js
node wx_miniprogram/tests/test_chat_copy_authority.js
node wx_miniprogram/tests/test_history_display_authority.js
node wx_miniprogram/tests/test_structured_block_layout.js
```

Expected:

```text
All tests PASS.
```

- [x] **Step 2: Run WeChat DevTools preview**

Run:

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli preview --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/wx_miniprogram --compile-condition '{"pathName":"pages/chat/chat"}'
```

Expected:

```text
preview succeeds with no compile error.
```

## Acceptance Criteria

P0 is accepted when:

1. The original numbered-section bug is fixed in `wx_miniprogram` and `yousenwebview/packageDeeptutor`.
2. Page code cannot bypass `ai-message-state` without failing `test_renderer_authority.js`.
3. Golden corpus validates real production-style Markdown failures.
4. Copy and history projections remain covered.
5. `docs/plan/INDEX.md` points future agents to this plan.
6. WeChat DevTools preview succeeds.

P1 is accepted when:

1. Parser replacement evaluation is written.
2. A decision is made: keep in-house parser, adapt a CommonMark/GFM parser, or defer.
3. The decision includes bundle-size, behavior, adapter complexity, and rollback notes.

P1 status: accepted locally. The decision is to keep the in-house parser for now and defer migration until a token-to-render-model adapter can pass the golden corpus without increasing net complexity.

## Current Verification Evidence

Latest local verification target:

```bash
node wx_miniprogram/tests/test_markdown.js &&
node wx_miniprogram/tests/test_markdown_normalize.js &&
node wx_miniprogram/tests/test_markdown_golden_corpus.js &&
node wx_miniprogram/tests/test_renderer_authority.js &&
node wx_miniprogram/tests/test_renderer_parity.js &&
node wx_miniprogram/tests/test_markdown_regression_fixtures.js &&
node wx_miniprogram/tests/test_ai_message_state.js &&
node wx_miniprogram/tests/test_chat_copy_authority.js &&
node wx_miniprogram/tests/test_history_display_authority.js &&
node wx_miniprogram/tests/test_structured_block_layout.js
```

DevTools verification target:

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli preview --project /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/wx_miniprogram --compile-condition '{"pathName":"pages/chat/chat"}'
```
