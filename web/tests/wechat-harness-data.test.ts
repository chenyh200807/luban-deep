import test from "node:test";
import assert from "node:assert/strict";

import { loadWechatHarnessCases } from "../lib/wechat-harness-data.ts";

test("wechat harness loads canonical mini-program fixtures through wx render authority", () => {
  const cases = loadWechatHarnessCases();
  assert.ok(cases.length >= 10);

  const structured = cases.find((item) => item.id.includes("structured_table"));
  assert.ok(structured);
  assert.ok(structured.finalState.hasStructuredContent);
  assert.equal(structured.expectations.historyParity, true);
  assert.equal(structured.parityWarnings.length, 0);
  assert.ok(structured.finalState.mcqCards && structured.finalState.mcqCards.length > 0);
});

test("wechat harness includes first-visible stream frames and history hydrate states", () => {
  const cases = loadWechatHarnessCases();
  for (const fixture of cases) {
    assert.ok(fixture.streamFrames.length >= 3, fixture.id);
    assert.equal(fixture.streamFrames[0].state.streamPhase, "streaming");
    assert.equal(fixture.streamFrames.at(-1)?.state.streamPhase, "complete");
    assert.equal(fixture.historyState.streamPhase, "complete");
  }
});
