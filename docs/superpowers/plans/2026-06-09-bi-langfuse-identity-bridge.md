# BI Langfuse Identity Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new Langfuse trace metadata resolve to the same canonical member identity used by BI, while preserving raw trace identity for diagnostics.

**Architecture:** `MemberConsoleService` remains the single authority for member identity. A small identity projection helper resolves raw trace metadata to a canonical BI member id, and turn/TutorBot trace writers add resolution status and raw identity metadata before Langfuse receives the observation. BI can then compare canonical trace activity with member-console members without treating Langfuse as a second member table.

**Tech Stack:** Python services, pytest, existing Langfuse observability adapter, existing BI/member-console identity fields.

---

### Task 1: Add Member Identity Resolution Projection

**Files:**
- Modify: `deeptutor/services/member_console/service.py`
- Test: `tests/services/member_console/test_service.py`

- [x] **Step 1: Write failing tests**
  Add tests that create a phone-backed member with `external_auth_user_id`, `wx_openid`, `wx_unionid`, and alias ids, then assert a new resolver maps each raw identity to the canonical member id while returning `unmapped` for unknown trace ids.

- [x] **Step 2: Verify RED**
  Run: `pytest tests/services/member_console/test_service.py -k "trace_identity_resolution" -q`
  Expected: FAIL because the resolver does not exist.

- [x] **Step 3: Implement minimal resolver**
  Add a read-only method that builds on existing `_members_for_bi()`, `_registered_phone_for_bi()`, and identity key normalization. It must not create members, mutate wallets, or expose phone as a Langfuse user id.

- [x] **Step 4: Verify GREEN**
  Run: `pytest tests/services/member_console/test_service.py -k "trace_identity_resolution" -q`
  Expected: PASS.

### Task 2: Inject Canonical Identity Into Trace Metadata

**Files:**
- Modify: `deeptutor/services/session/turn_runtime.py`
- Modify: `deeptutor/services/tutorbot/manager.py`
- Test: `tests/api/test_unified_ws_turn_runtime.py` or a focused service-level test if an existing fake member service can cover the trace path.

- [x] **Step 1: Write failing tests**
  Add tests proving trace metadata keeps `raw_user_id`, sets `user_id` to canonical id when resolved, and marks `identity_resolution_status` as `resolved` or `unmapped`.

- [x] **Step 2: Verify RED**
  Run the focused tests and confirm they fail on missing metadata.

- [x] **Step 3: Implement minimal metadata enrichment**
  Add a small local helper near trace metadata creation that calls the member resolver best-effort. On failure, keep existing behavior and mark no trace as resolved.

- [x] **Step 4: Verify GREEN**
  Run the focused tests and existing member-console tests.

### Task 3: Add BI/Observability Guard Coverage

**Files:**
- Test: `tests/services/test_bi_service_limits.py`
- Test: `tests/services/observability/test_turn_runtime_observer_event.py` if needed

- [x] **Step 1: Add regression tests**
  Assert BI registered member identity index accepts canonical ids and raw aliases but still ignores unmapped Langfuse-only ids.

- [x] **Step 2: Run contract-focused tests**
  Run: `pytest tests/services/member_console/test_service.py tests/services/test_bi_service_limits.py tests/services/observability/test_turn_runtime_observer_event.py -q`

- [x] **Step 3: Run contract guard**
  Run: `python scripts/check_contract_guard.py`

### Out of Scope

- Historical Langfuse backfill.
- Writing phone numbers into Langfuse metadata.
- Creating members from Langfuse users.
- Changing wallet or learner-state authority.
