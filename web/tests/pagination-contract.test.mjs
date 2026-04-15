import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSessionPageSearchParams,
  buildNotebookEntrySearchParams,
} from "../lib/pagination-contract.ts";

test("buildSessionPageSearchParams includes keyset cursor when present", () => {
  const params = buildSessionPageSearchParams(50, 0, {
    before_updated_at: 1710000000,
    before_session_id: "sess_123",
  });

  assert.equal(params.get("limit"), "50");
  assert.equal(params.get("offset"), "0");
  assert.equal(params.get("before_updated_at"), "1710000000");
  assert.equal(params.get("before_session_id"), "sess_123");
});

test("buildNotebookEntrySearchParams includes keyset cursor when present", () => {
  const params = buildNotebookEntrySearchParams({
    category_id: 42,
    bookmarked: true,
    limit: 50,
    before_created_at: 1710001234,
    before_entry_id: 998,
  });

  assert.equal(params.get("category_id"), "42");
  assert.equal(params.get("bookmarked"), "true");
  assert.equal(params.get("limit"), "50");
  assert.equal(params.get("before_created_at"), "1710001234");
  assert.equal(params.get("before_entry_id"), "998");
});
