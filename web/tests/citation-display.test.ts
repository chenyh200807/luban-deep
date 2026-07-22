import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { extractCitationReferences } from "../lib/citation-display.ts";

test("extractCitationReferences reads only the structured public bundle", () => {
  assert.deepEqual(
    extractCitationReferences({
      response: "正文中即使有〔9〕也不能成为引用 authority",
      citation_bundle: {
        refs: [
          { marker: "〔1〕", title: "教材", locator: "第 2 页", public_quote: "公开摘录" },
          { marker: "〔2〕", title: "内部", visibility: "private" },
        ],
      },
    }),
    [{ marker: "〔1〕", title: "教材", locator: "第 2 页", publicQuote: "公开摘录" }],
  );
});

test("extractCitationReferences fails closed on absent or malformed bundles", () => {
  assert.deepEqual(extractCitationReferences(null), []);
  assert.deepEqual(extractCitationReferences({ citation_bundle: { refs: "bad" } }), []);
  assert.deepEqual(extractCitationReferences({ citation_bundle: { refs: [{}] } }), []);
});

test("ChatMessages renders the structured refs in a separate citation region", () => {
  const source = readFileSync(
    new URL("../components/chat/home/ChatMessages.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /extractCitationReferences\(resultEvent\?\.metadata\)/);
  assert.match(source, /aria-label=.*引用依据/);
  assert.match(source, /ref\.title/);
  assert.match(source, /ref\.locator/);
  assert.match(source, /ref\.publicQuote/);
});
