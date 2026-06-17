# WeChat Markdown Parser Evaluation

## Document Info

- Created: 2026-05-13
- Status: `Decision accepted locally`
- Parent plan: [2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md](2026-05-13-wechat-renderer-markdown-authority-implementation-plan.md)
- Scope:
  - `wx_miniprogram/utils/markdown.js`
  - `wx_miniprogram/utils/markdown-normalize.js`
  - `tests/fixtures/wechat_markdown_golden_cases.json`
  - mirrored `yousenwebview/packageDeeptutor` renderer utilities

## Decision

Do **not** replace the current WeChat Markdown parser in this batch.

Keep the current in-house parser and normalizer as the single Markdown fallback authority, protected by:

1. `test_renderer_authority.js`
2. `test_renderer_parity.js`
3. `test_markdown_golden_corpus.js`
4. `test_markdown_regression_fixtures.js`

Revisit a CommonMark/GFM parser only if a future batch also designs the adapter needed to preserve DeepTutor product semantics, especially per-item source indexes such as `1 / 5 / 10`.

## Why

Industry parsers solve a different problem: spec-compliant Markdown. DeepTutor's mobile teaching renderer needs a stricter product contract:

1. Preserve visible source numbering, even when the model emits non-sequential ordered labels.
2. Normalize compact model output such as `3.标题` and `-子项`.
3. Keep `presentation.blocks` as the first-class teaching structure.
4. Keep Markdown as fallback projection, not a second teaching-content authority.

Direct parser replacement would reduce some low-level parsing risk but would reintroduce adapter complexity at the product boundary.

## Package Impact

Command:

```bash
npm view micromark version dist.unpackedSize dependencies --json
npm view markdown-it version dist.unpackedSize dependencies --json
wc -c wx_miniprogram/utils/markdown.js wx_miniprogram/utils/markdown-normalize.js wx_miniprogram/utils/ai-message-state.js wx_miniprogram/utils/render-schema.js tests/fixtures/wechat_markdown_golden_cases.json
```

Observed on 2026-05-13:

| Candidate | Version | Unpacked size | Notes |
| --- | ---: | ---: | --- |
| `micromark` | `4.0.2` | `209,635` bytes | ESM package; CommonMark-oriented tokenizer/compiler; requires adapter to produce WXML render model. |
| `markdown-it` | `14.1.1` | `767,952` bytes | Larger CommonMark-style token parser; requires token-to-render-block adapter. |
| Current `markdown.js` | local | `18,185` bytes | Already emits mini-program render blocks and preserves source ordered indexes. |
| Current `markdown-normalize.js` | local | `2,857` bytes | Handles compact model-output forms before parsing. |

Current fallback parser plus normalizer is about `21,042` bytes before minification, excluding shared render state logic.

## Mini Program Integration Impact

Package size is not the only migration cost for this project.

Current `wx_miniprogram` facts checked on 2026-05-13:

1. There is no `wx_miniprogram/package.json`.
2. There is no checked-in `wx_miniprogram/miniprogram_npm` bundle.
3. `wx_miniprogram/project.config.json` has `"packNpmManually": false` and an empty `"packNpmRelationList": []`.

That means a third-party parser migration would need an integration batch, not just `npm install`:

1. Decide between WeChat DevTools npm build output and a vendored parser bundle.
2. Handle module format differences: `micromark@4` is ESM-first, while the existing mini-program utilities are CommonJS `require` modules.
3. Build a token/HTML-to-render-block adapter for the existing WXML model.
4. Re-run DevTools preview/build to catch package-size, module-resolution, and subpackage impact.
5. Mirror the same artifact into `yousenwebview/packageDeeptutor` without creating a second parser authority.

`markdown-it` is easier to load from CommonJS, but its package footprint is larger and it still requires the same render-block adapter. `micromark` is smaller, but the ESM integration cost is higher for the current mini-program layout.

## Golden Corpus Behavior

Corpus file:

```text
tests/fixtures/wechat_markdown_golden_cases.json
```

Cases:

1. `blank_separated_management_sections`
2. `compact_technical_sections`
3. `non_sequential_exam_focus`
4. `mixed_ordered_and_compact_bullets`

### Direct Candidate Behavior

Both `micromark` and `markdown-it` were tested without project normalizer.

| Case | Expected | `micromark` direct | `markdown-it` direct | Result |
| --- | --- | --- | --- | --- |
| `blank_separated_management_sections` | ordered `7,8,9,10,11`; bullets preserved | ordered ok; compact bullets not bullet blocks | ordered ok; compact bullets not bullet blocks | Fail |
| `compact_technical_sections` | ordered `3,4,5,6` | no ordered list | no ordered list | Fail |
| `non_sequential_exam_focus` | ordered `1,5,10` | ordered `1,2,3` | ordered `1,2,3` | Fail |
| `mixed_ordered_and_compact_bullets` | ordered `1,2`; bullets preserved | ordered ok; compact bullets not bullet blocks | ordered ok; compact bullets not bullet blocks | Fail |

### Candidate + Current Normalizer Behavior

Both candidates were also tested after `normalizeMarkdownForWechat`.

| Case | `micromark` + normalizer | `markdown-it` + normalizer | Result |
| --- | --- | --- | --- |
| `blank_separated_management_sections` | Pass | Pass | Acceptable with adapter |
| `compact_technical_sections` | Pass | Pass | Acceptable with adapter |
| `non_sequential_exam_focus` | Still `1,2,3` instead of `1,5,10` | Still `1,2,3` instead of `1,5,10` | Fail |
| `mixed_ordered_and_compact_bullets` | Pass | Pass | Acceptable with adapter |

The remaining failure is not a bug in these parsers. It follows CommonMark-style ordered-list semantics: one ordered list has a start number, and later item markers do not become independent visible indexes. DeepTutor intentionally preserves each source item index because model answers often use section numbers as semantic labels.

## Reproducible Candidate Evaluation Appendix

The candidate check used a temporary npm prefix so no parser dependency was added to the project.

Command shape:

```bash
tmpdir=$(mktemp -d /tmp/deeptutor-md-eval-XXXXXX)
npm install --prefix "$tmpdir" micromark@4.0.2 markdown-it@14.1.1
MICROMARK_PATH="$tmpdir/node_modules/micromark/index.js" \
MARKDOWN_IT_ROOT="$tmpdir/node_modules/markdown-it" \
node --input-type=module <<'NODE'
import fs from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { micromark } = await import(process.env.MICROMARK_PATH);
const MarkdownIt = require(process.env.MARKDOWN_IT_ROOT);
const normalize = require("./wx_miniprogram/utils/markdown-normalize");
const corpus = JSON.parse(fs.readFileSync("./tests/fixtures/wechat_markdown_golden_cases.json", "utf8"));
const md = new MarkdownIt();

function extractIndexesFromHtml(html) {
  const indexes = [];
  html.replace(/<ol(?:\s+start="(\d+)")?[^>]*>([\s\S]*?)<\/ol>/g, (_, start, body) => {
    let next = start ? Number(start) : 1;
    body.replace(/<li\b/g, () => {
      indexes.push(next);
      next += 1;
      return "";
    });
    return "";
  });
  return indexes;
}

for (const item of corpus) {
  for (const [name, render] of [
    ["micromark direct", micromark],
    ["micromark normalized", (text) => micromark(normalize.normalizeMarkdownForWechat(text))],
    ["markdown-it direct", (text) => md.render(text)],
    ["markdown-it normalized", (text) => md.render(normalize.normalizeMarkdownForWechat(text))],
  ]) {
    const actual = extractIndexesFromHtml(render(item.content));
    console.log(item.name, name, actual.join(","));
  }
}
NODE
```

Output summary:

1. Direct candidates fail compact ordered markers and compact dash bullets.
2. Candidate plus current normalizer fixes compact markers and compact bullets.
3. Both candidates still emit `1,2,3` for `non_sequential_exam_focus`, while the product contract expects `1,5,10`.

## Adapter Requirements If We Migrate Later

A future parser migration must include all of these adapters:

1. Pre-normalize compact model output before CommonMark parsing.
2. Preserve per-item source ordered markers when labels are semantic section numbers.
3. Convert parser tokens/HTML/AST into the current mini-program render block shape.
4. Preserve `ai-message-state` as the only production consumer of Markdown parsing.
5. Keep `wx_miniprogram` and `yousenwebview/packageDeeptutor` behavior byte- or snapshot-equivalent.

Without adapter item 2, the original class of numbering regressions can return.

## Recommendation

Current batch:

1. Keep in-house parser.
2. Keep golden corpus as the migration gate.
3. Treat `micromark` as the better future candidate than `markdown-it` if a replacement is required, because it is smaller and closer to parser-token infrastructure.
4. Do not introduce either dependency until the adapter can pass `test_markdown_golden_corpus.js` and reduce net complexity.

Future revisit trigger:

1. Markdown fallback bugs exceed what the current parser can safely handle.
2. We need broader CommonMark/GFM compatibility for user-authored content, not just TutorBot teaching answers.
3. We are ready to build a token-to-render-model adapter and pay the package-size cost.

## Rollback / No-Migration Guard

This batch intentionally adds no parser dependency and changes no production parser entrypoint. The current authority remains:

```text
ai-message-state -> markdown-normalize -> markdown.parseWithIds -> WXML nodes
```

If a future migration starts and fails acceptance, rollback is:

1. Remove the parser dependency or vendored bundle.
2. Remove the parser adapter from the mini-program and mirrored webview package.
3. Restore `ai-message-state` to call the current `markdown.parseWithIds` path.
4. Keep `test_markdown_golden_corpus.js` as the release gate; rollback is not complete until the golden corpus and renderer authority tests pass again.

## Verification

Run:

```bash
node wx_miniprogram/tests/test_markdown_golden_corpus.js
```

Expected:

```text
PASS test_markdown_golden_corpus.js
```
