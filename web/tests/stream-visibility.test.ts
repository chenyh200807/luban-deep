import test from "node:test";
import assert from "node:assert/strict";
import {
  isUserVisibleStreamEvent,
  resolveStreamEventVisibility,
  shouldAppendEventContent,
} from "../lib/stream.ts";
import type { StreamEvent } from "../lib/unified-ws.ts";

function event(overrides: Partial<StreamEvent> = {}): StreamEvent {
  return {
    type: "content",
    source: "chat",
    stage: "responding",
    content: "visible answer",
    metadata: {},
    timestamp: Date.now(),
    ...overrides,
  };
}

test("stream visibility defaults to public for legacy events", () => {
  assert.equal(resolveStreamEventVisibility(event()), "public");
  assert.equal(isUserVisibleStreamEvent(event()), true);
});

test("explicit internal stream events are not user-visible", () => {
  const internal = event({ visibility: "internal" });

  assert.equal(resolveStreamEventVisibility(internal), "internal");
  assert.equal(isUserVisibleStreamEvent(internal), false);
  assert.equal(shouldAppendEventContent(internal), false);
});

test("metadata visibility is honored for older clients", () => {
  const internal = event({ metadata: { visibility: "internal" } });

  assert.equal(resolveStreamEventVisibility(internal), "internal");
  assert.equal(isUserVisibleStreamEvent(internal), false);
  assert.equal(shouldAppendEventContent(internal), false);
});

test("public final response content still appends", () => {
  const finalContent = event({
    metadata: {
      call_id: "call-final",
      call_kind: "llm_final_response",
    },
    visibility: "public",
  });

  assert.equal(shouldAppendEventContent(finalContent), true);
});

test("public non-final traced content does not append", () => {
  const tracedDraft = event({
    metadata: {
      call_id: "call-draft",
      call_kind: "tool_planning",
    },
    visibility: "public",
  });

  assert.equal(shouldAppendEventContent(tracedDraft), false);
});
