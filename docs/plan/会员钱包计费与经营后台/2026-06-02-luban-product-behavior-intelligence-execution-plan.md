# 鲁班 Product Behavior Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build P0 Product Behavior Intelligence so BI 会员运营页 can answer how often learners open 历史/学情, which 学情 sections are used most, and which users need follow-up, without creating a second telemetry authority.

**Architecture:** Reuse the existing `surface-telemetry` helpers and `POST /api/v1/observability/surface-events` as the single transport/ingestion authority. Add a product behavior catalog and an independent SQLite-backed P0 raw ledger (`product_behavior.db`) with indexed raw reads, then project behavior health/cohorts into the existing `/api/v1/member/*` read APIs consumed by `/bi?tab=member-ops`. Keep `SurfaceEventStore` as the existing in-memory ACK smoke path.

**Tech Stack:** FastAPI, Pydantic, Python services, independent SQLite behavior store, React/Next.js, existing BI v2 components, Node test runner, pytest.

---

## Current Execution Status

- Task 1-11 implementation, automated verification, and local visual acceptance evidence completed on 2026-06-02.
- Commit steps in this plan were intentionally not executed in this Codex run because the user did not request commits and the worktree contains unrelated Golden/source-compiler changes.
- Task 11 local evidence is recorded in `docs/qa/2026-06-02-product-behavior-reality-audit.md`: `/bi?tab=member-ops` desktop/mobile screenshots, Member360 behavior drawer screenshots, and API-level smoke for both `wechat_miniprogram` and `wechat_yousenwebview` behavior events.
- Browser plugin verification was attempted first. Because the plugin session could not evaluate page `window.localStorage`/`location`, local visual validation fell back to regular Playwright against a production Next server and FastAPI backend; screenshots were captured under `artifacts/qa/product-behavior-bi-member-ops/`.
- `/wechat-harness` page-level smoke passed on the local dev fixture server and produced `artifacts/qa/product-behavior-bi-member-ops/wechat-harness-mobile.png`. The production route correctly fails closed unless the harness is explicitly enabled before prerender.
- P0 keeps WeChat section visibility trust at B until a full WeChat DevTools simulator or real-device visual smoke is run. API-level smoke for both WeChat surfaces passed.
- Known follow-up: `/api/v1/member/{user_id}/360` local validation took about 21.5s due slow learner-state downstream reads. This is a performance follow-up, not a P0 behavior correctness blocker.

Automated verification completed:

```bash
pytest tests/services/observability/test_product_behavior_catalog.py tests/services/observability/test_product_behavior_store.py tests/api/test_observability_router.py tests/services/observability/test_surface_ack_smoke.py tests/services/test_bi_metrics.py tests/api/test_product_behavior_p0_flow.py tests/web/test_bi_v2_raw_fetch_guard.py -q
# 42 passed

pytest tests/api/test_bi_router.py::test_behavior_export_job_is_raw_mode_and_audited tests/api/test_bi_write_endpoints_registry.py -q
# 9 passed

cd web && node --test tests/product-behavior-surface-telemetry.test.ts tests/bi-v2-testids.test.ts
# 7 passed

cd web && BI_BACKOFFICE_V2_SHELL_ENABLED=1 BI_CRM_V2_ENABLED=1 BI_OVERVIEW_V2_ENABLED=1 NEXT_PUBLIC_BI_BACKOFFICE_V2_SHELL_ENABLED=1 NEXT_PUBLIC_BI_CRM_V2_ENABLED=1 NEXT_PUBLIC_BI_OVERVIEW_V2_ENABLED=1 NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001 npm run build -- --webpack
# PASS; existing lib/wechat-harness-data.ts webpack warning remains
```

Local acceptance evidence:

```text
artifacts/qa/product-behavior-bi-member-ops/desktop-member-ops.png
artifacts/qa/product-behavior-bi-member-ops/mobile-member-ops.png
artifacts/qa/product-behavior-bi-member-ops/desktop-member-360-drawer.png
artifacts/qa/product-behavior-bi-member-ops/mobile-member-360-drawer.png
artifacts/qa/product-behavior-bi-member-ops/wechat-harness-mobile.png
```

## Source PRD

- PRD: `docs/plan/2026-06-02-luban-product-behavior-intelligence-prd.md`
- Current status: `Proposed v0.4`
- P0 BI surface: `/bi?tab=member-ops`
- Main code facts:
  - Surface telemetry endpoint already exists: `deeptutor/api/routers/observability.py`
  - In-memory surface ACK store already exists: `deeptutor/services/observability/surface_events.py`
  - Web helper already exists: `web/lib/surface-telemetry.ts`
  - WeChat helper already exists: `wx_miniprogram/utils/surface-telemetry.js`
  - `yousenwebview` helper already exists: `yousenwebview/packageDeeptutor/utils/surface-telemetry.js`
  - BI member ops page reads member APIs from `web/lib/member-api.ts`, not `/api/v1/bi/*`
  - Member APIs are served by `deeptutor/api/routers/member.py` and `deeptutor/services/member_console/service.py`
  - BI metrics registry is `deeptutor/services/bi_metrics.py`

## Execution Constraints

- Do not add `/api/v1/product-behavior/events`.
- Do not create a second client behavior SDK.
- Do not write product behavior into `learner_state`, `learning_evidence`, wallet, billing, or TutorBot state.
- Do not add a top-level BI `behavior` tab for P0.
- Do not make `/api/v1/ws` changes.
- Raw mode is allowed for internal BI, but forbidden fields still stay out of event payloads.
- Current worktree is dirty with unrelated Golden/source-compiler files. Stage only files touched by this plan.

## File Structure

Create:

- `deeptutor/services/observability/product_behavior_catalog.py`
  Product event/module/section/action allowlists and metadata validation. This is the product behavior semantic authority.

- `deeptutor/services/observability/product_behavior_store.py`
  SQLite-backed P0 raw ledger, indexed raw read model, batch cohort reader, and member timeline reader. This is the P0 behavior persistence/read authority.

- `tests/services/observability/test_product_behavior_catalog.py`
  Catalog validation tests.

- `tests/services/observability/test_product_behavior_store.py`
  SQLite persistence, dedupe, raw indexed summary, batch summary, offline replay, cohort, and timeline tests.

- `web/tests/product-behavior-surface-telemetry.test.ts`
  Source-level guard that web helper keeps using `/api/v1/observability/surface-events`, includes `visit_id`, and does not introduce a product-behavior endpoint.

Modify:

- `deeptutor/services/observability/surface_events.py`
  Expand allowed event names to include P0 product behavior events and call product behavior persistence writer after existing dedupe.

- `deeptutor/api/routers/observability.py`
  Accept optional product behavior fields through metadata, preserve auth/rate-limit/payload-size guard, and keep existing ACK behavior.

- `deeptutor/services/observability/__init__.py`
  Export the product behavior store getter/resetter for tests and service wiring.

- `deeptutor/services/bi_metrics.py`
  Register behavior metrics in `BI_METRICS`.

- `web/lib/bi-v2-metric-registry.generated.ts`
  Regenerate from `BI_METRICS`; do not edit by hand.

- `deeptutor/services/member_console/service.py`
  Attach behavior dashboard summary to `get_dashboard()`, behavior columns to `list_members()`, and behavior timeline/section breakdown to `get_member_360()`.

- `web/lib/member-api.ts`
  Add behavior types and normalizers.

- `web/app/(workspace)/bi/_v2/member-ops/data.ts`
  Add behavior fields and behavior column keys.

- `web/app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx`
  Add health strip, cohort tabs, behavior columns, and filter mapping.

- `web/app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx`
  Add behavior timeline, 学情 section breakdown, trust badge, and raw events drilldown section.

- `wx_miniprogram/utils/surface-telemetry.js`
  Add `visit_id` support and product behavior convenience wrapper.

- `yousenwebview/packageDeeptutor/utils/surface-telemetry.js`
  Add `visit_id` support and product behavior convenience wrapper.

- `tests/api/test_observability_router.py`
  Extend existing endpoint tests for product behavior events.

- `tests/services/test_bi_metrics.py`
  Assert behavior metrics are registered.

- `tests/api/test_member_router_auth.py` or `tests/services/member_console/test_service.py`
  Add member API/service behavior projection tests.

- `tests/web/test_bi_v2_raw_fetch_guard.py`
  Keep guard passing; no raw `fetch` inside BI v2 panels.

- `docs/qa/2026-06-02-product-behavior-reality-audit.md`
  Phase -1 evidence report.

## Phase Gate

Implementation may proceed past Task 1 only if the Phase -1 audit records these decisions:

```yaml
telemetry_authority: reuse_surface_events
product_behavior_endpoint: none
p0_storage: sqlite_product_behavior_db
p0_db_file: product_behavior.db
p0_read_model: reads_raw_with_indexes
p0_bi_join: member_console_reads_behavior_batch_summaries
section_visibility_trust: A_or_B_explicit
anonymous_behavior: disabled_for_p0
```

If any value differs, stop and revise this plan before coding Tasks 2-9.

## Task 1: Phase -1 Reality Audit

**Files:**
- Create: `docs/qa/2026-06-02-product-behavior-reality-audit.md`

- [ ] **Step 1: Create the audit document**

Add:

```markdown
# Product Behavior Reality Audit

- Date: 2026-06-02
- Source PRD: `docs/plan/2026-06-02-luban-product-behavior-intelligence-prd.md`
- Decision: P0 proceeds only if all hard gates below pass.

## 1. Telemetry Authority

| Item | Evidence | Decision |
| --- | --- | --- |
| Web helper | `web/lib/surface-telemetry.ts` posts `/api/v1/observability/surface-events` | reuse |
| WeChat helper | `wx_miniprogram/utils/surface-telemetry.js` posts `/api/v1/observability/surface-events` | reuse |
| Yousen helper | `yousenwebview/packageDeeptutor/utils/surface-telemetry.js` posts `/api/v1/observability/surface-events` | reuse |
| Backend endpoint | `deeptutor/api/routers/observability.py` has auth, rate limit, metadata cap | reuse |
| ACK store | `SurfaceEventStore` dedupes and snapshots current surface ACK events | preserve |

Decision: `telemetry_authority=reuse_surface_events`.

## 2. Storage / Join Decision

Current BI member ops reads `/api/v1/member/*`, served by `MemberConsoleService`.

P0 storage decision:

```yaml
p0_storage: sqlite_product_behavior_db
p0_db_file: product_behavior.db
p0_raw_table: product_behavior_events
p0_read_model: reads_raw_with_indexes
p0_aggregate_tables: deferred_until_p1_or_volume_gate
p0_bi_join: member_console_reads_behavior_batch_summaries
```

Reason: P0 must land in `/bi?tab=member-ops`; current member ops data path already uses member APIs, so same-process indexed raw reads are the lowest-risk join. The behavior store must use an independent sibling SQLite file (`product_behavior.db`) instead of the chat/session SQLite file, because product behavior writes happen on the request path and must not contend with core chat/session single-writer locks.

## 3. Section Visibility

| Surface | Mechanism | P0 trust |
| --- | --- | --- |
| web | `IntersectionObserver` | A if tested |
| wechat_miniprogram | `wx.createIntersectionObserver` | B until DevTools/manual smoke |
| wechat_yousenwebview | host webview observer or component-visible fallback | B until smoke |

Decision: `section_visibility_trust=B` until three-surface smoke passes.

## 4. Identity / Session

- `visit_id`: client-generated navigation session.
- `session_id`: optional turn/chat session.
- `turn_id`: optional turn correlation.
- anonymous behavior: disabled for P0.

Decision: `anonymous_behavior=disabled_for_p0`.

## 5. Release Field

- Web: use existing release/build field if available, otherwise `unknown_release` and trust B.
- WeChat/yousen: use `ENV_VERSION` and system version for P0; trust B.

## 6. Hard Gate

```yaml
telemetry_authority: reuse_surface_events
product_behavior_endpoint: none
p0_storage: sqlite_product_behavior_db
p0_db_file: product_behavior.db
p0_read_model: reads_raw_with_indexes
p0_bi_join: member_console_reads_behavior_batch_summaries
section_visibility_trust: B
anonymous_behavior: disabled_for_p0
```
```

- [ ] **Step 2: Verify source evidence**

Run:

```bash
rg -n "/api/v1/observability/surface-events|SurfaceEventStore|BI_METRICS|getMemberDashboard|/api/v1/member" \
  web wx_miniprogram yousenwebview deeptutor tests
```

Expected: output includes existing surface helpers, `SurfaceEventStore`, `BI_METRICS`, `web/lib/member-api.ts`, and member router/service paths.

- [ ] **Step 3: Commit the audit only**

```bash
git add docs/qa/2026-06-02-product-behavior-reality-audit.md
git commit -m "docs: audit product behavior execution prerequisites"
```

## Task 2: Product Behavior Catalog

**Files:**
- Create: `deeptutor/services/observability/product_behavior_catalog.py`
- Create: `tests/services/observability/test_product_behavior_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

Create `tests/services/observability/test_product_behavior_catalog.py`:

```python
from __future__ import annotations

import pytest

from deeptutor.services.observability.product_behavior_catalog import (
    PRODUCT_BEHAVIOR_EVENT_NAMES,
    validate_product_behavior_event,
)


def test_product_behavior_catalog_includes_p0_events() -> None:
    assert {
        "module_viewed",
        "section_viewed",
        "section_expanded",
        "learning_action_started",
        "learning_action_completed",
        "module_returned",
        "module_exited",
        "event_error",
    }.issubset(PRODUCT_BEHAVIOR_EVENT_NAMES)


def test_validate_product_behavior_event_accepts_learning_report_section() -> None:
    event = validate_product_behavior_event(
        event_name="section_viewed",
        metadata={
            "visit_id": "visit-u1-1",
            "module": "learning_report",
            "section": "next_action",
            "action": "view",
            "surface": "web",
            "visible_ms": 1400,
        },
    )

    assert event["module"] == "learning_report"
    assert event["section"] == "next_action"
    assert event["visit_id"] == "visit-u1-1"


def test_validate_product_behavior_event_rejects_unknown_module() -> None:
    with pytest.raises(ValueError, match="Unsupported module"):
        validate_product_behavior_event(
            event_name="module_viewed",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "random_page",
                "action": "view",
                "surface": "web",
            },
        )


def test_validate_product_behavior_event_rejects_unknown_product_like_event_name() -> None:
    with pytest.raises(ValueError, match="Unsupported product behavior event_name"):
        validate_product_behavior_event(
            event_name="module_clicked",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "history",
                "action": "view",
                "surface": "web",
            },
        )


def test_validate_product_behavior_event_allows_error_without_visit_id() -> None:
    event = validate_product_behavior_event(
        event_name="event_error",
        metadata={
            "module": "learning_report",
            "action": "error",
            "surface": "web",
            "error_code": "observer_unavailable",
        },
    )

    assert event["event_name"] == "event_error"
    assert event["visit_id"] == ""
    assert event["error_code"] == "observer_unavailable"


def test_validate_product_behavior_event_rejects_forbidden_payload_fields() -> None:
    with pytest.raises(ValueError, match="Forbidden product behavior field"):
        validate_product_behavior_event(
            event_name="module_viewed",
            metadata={
                "visit_id": "visit-u1-1",
                "module": "history",
                "action": "view",
                "surface": "web",
                "full_answer_text": "should not be stored",
            },
        )
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/services/observability/test_product_behavior_catalog.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `product_behavior_catalog`.

- [ ] **Step 3: Implement the catalog**

Create `deeptutor/services/observability/product_behavior_catalog.py`:

```python
from __future__ import annotations

from typing import Any

PRODUCT_BEHAVIOR_EVENT_NAMES = frozenset(
    {
        "module_viewed",
        "section_viewed",
        "section_expanded",
        "learning_action_started",
        "learning_action_completed",
        "module_returned",
        "module_exited",
        "event_error",
    }
)

PRODUCT_BEHAVIOR_MODULES = frozenset(
    {
        "learning",
        "history",
        "chat",
        "learning_report",
        "notebook",
        "practice",
        "assessment",
        "profile",
    }
)

LEARNING_REPORT_SECTIONS = frozenset(
    {
        "current_state",
        "why",
        "next_action",
        "evidence",
        "wrong_items",
        "score_points",
        "weakness_map",
        "trend",
        "study_plan",
        "retest",
    }
)

PRODUCT_BEHAVIOR_ACTIONS = frozenset(
    {
        "view",
        "expand",
        "open_detail",
        "start_training",
        "start_review",
        "start_retest",
        "save_note",
        "dismiss",
        "return",
        "complete",
        "error",
    }
)

ALLOWED_SURFACES = frozenset({"web", "wechat_miniprogram", "wechat_yousenwebview"})

FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS = frozenset(
    {
        "password",
        "verification_code",
        "id_card",
        "bank_card",
        "payment_credential",
        "full_chat_text",
        "full_answer_text",
        "complete_subjective_answer",
    }
)


def _clean_string(value: Any, *, max_length: int = 128) -> str:
    return str(value or "").strip()[:max_length]


def validate_product_behavior_event(event_name: str, metadata: dict[str, Any]) -> dict[str, Any]:
    normalized_event = _clean_string(event_name, max_length=64)
    if normalized_event not in PRODUCT_BEHAVIOR_EVENT_NAMES:
        raise ValueError(f"Unsupported product behavior event_name: {event_name!r}")

    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    forbidden = sorted(set(metadata) & FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS)
    if forbidden:
        raise ValueError(f"Forbidden product behavior field: {forbidden[0]}")

    module = _clean_string(metadata.get("module"), max_length=64)
    if module not in PRODUCT_BEHAVIOR_MODULES:
        raise ValueError(f"Unsupported module: {module!r}")

    action = _clean_string(metadata.get("action"), max_length=64)
    if action not in PRODUCT_BEHAVIOR_ACTIONS:
        raise ValueError(f"Unsupported action: {action!r}")

    surface = _clean_string(metadata.get("surface"), max_length=64)
    if surface and surface not in ALLOWED_SURFACES:
        raise ValueError(f"Unsupported surface: {surface!r}")

    section = _clean_string(metadata.get("section"), max_length=64)
    if module == "learning_report" and section and section not in LEARNING_REPORT_SECTIONS:
        raise ValueError(f"Unsupported learning_report section: {section!r}")

    visit_id = _clean_string(metadata.get("visit_id"), max_length=128)
    if not visit_id and normalized_event != "event_error":
        raise ValueError("visit_id is required for product behavior events")

    return {
        "event_name": normalized_event,
        "visit_id": visit_id,
        "module": module,
        "section": section,
        "action": action,
        "surface": surface,
        "object_type": _clean_string(metadata.get("object_type"), max_length=64),
        "object_id": _clean_string(metadata.get("object_id"), max_length=128),
        "entry_source": _clean_string(metadata.get("entry_source"), max_length=64),
        "referrer_module": _clean_string(metadata.get("referrer_module"), max_length=64),
        "duration_ms": int(metadata.get("duration_ms") or 0),
        "visible_ms": int(metadata.get("visible_ms") or 0),
        "result": _clean_string(metadata.get("result"), max_length=64),
        "error_code": _clean_string(metadata.get("error_code"), max_length=64),
        "release_id": _clean_string(metadata.get("release_id"), max_length=128),
        "app_version": _clean_string(metadata.get("app_version"), max_length=64),
        "platform": _clean_string(metadata.get("platform"), max_length=64),
        "device_model": _clean_string(metadata.get("device_model"), max_length=128),
        "network_type": _clean_string(metadata.get("network_type"), max_length=64),
    }
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
pytest tests/services/observability/test_product_behavior_catalog.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/observability/product_behavior_catalog.py tests/services/observability/test_product_behavior_catalog.py
git commit -m "feat: add product behavior event catalog"
```

## Task 3: SQLite Product Behavior Store

**Files:**
- Create: `deeptutor/services/observability/product_behavior_store.py`
- Create: `tests/services/observability/test_product_behavior_store.py`
- Modify: `deeptutor/services/observability/__init__.py`

- [ ] **Step 1: Write failing store tests**

Create `tests/services/observability/test_product_behavior_store.py`:

```python
from __future__ import annotations

import time
from pathlib import Path

import pytest

from deeptutor.services.observability.product_behavior_store import SQLiteProductBehaviorStore


def test_store_dedupes_events_and_builds_member_summary(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    event = {
        "event_id": "evt-1",
        "event_name": "module_viewed",
        "event_version": 1,
        "occurred_at_ms": now_ms,
        "received_at_ms": now_ms + 100,
        "user_id": "u1",
        "visit_id": "visit-1",
        "session_id": "",
        "turn_id": "",
        "surface": "web",
        "module": "learning_report",
        "section": "",
        "action": "view",
        "properties_json": {"module": "learning_report"},
    }

    assert store.record_event(event)["status"] == "accepted"
    assert store.record_event(event)["status"] == "duplicate"

    summary = store.get_member_behavior_summary("u1", days=7)
    assert summary["learning_report_open_count_7d"] == 1
    assert summary["history_open_count_7d"] == 0
    assert summary["trust_level"] == "B"


def test_store_builds_learning_report_section_breakdown(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for index, section in enumerate(["next_action", "next_action", "evidence"]):
        store.record_event(
            {
                "event_id": f"evt-section-{index}",
                "event_name": "section_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms + index,
                "received_at_ms": now_ms + 100 + index,
                "user_id": "u1",
                "visit_id": "visit-1",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "learning_report",
                "section": section,
                "action": "view",
                "properties_json": {"section": section},
            }
        )

    breakdown = store.get_learning_report_section_breakdown("u1", days=7)
    assert breakdown[0] == {"section": "next_action", "view_count": 2}
    assert breakdown[1] == {"section": "evidence", "view_count": 1}


def test_store_detects_report_high_no_action_cohort(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for index in range(3):
        store.record_event(
            {
                "event_id": f"evt-report-{index}",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms + index,
                "received_at_ms": now_ms + 100 + index,
                "user_id": "u1",
                "visit_id": f"visit-{index}",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "learning_report",
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    assert store.get_member_behavior_summary("u1", days=7)["cohort"] == "report_high_no_action"


def test_store_uses_occurred_at_for_offline_replay_window(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for event_id, occurred_at_ms in [
        ("evt-replay-3d", now_ms - 3 * 86400 * 1000),
        ("evt-replay-10d", now_ms - 10 * 86400 * 1000),
    ]:
        store.record_event(
            {
                "event_id": event_id,
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": occurred_at_ms,
                "received_at_ms": now_ms,
                "user_id": "u1",
                "visit_id": "visit-replay",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "history",
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    summary = store.get_member_behavior_summary("u1", days=7)
    assert summary["history_open_count_7d"] == 1


def test_store_rejects_forbidden_properties_for_direct_callers(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)

    with pytest.raises(ValueError, match="Forbidden product behavior property"):
        store.record_event(
            {
                "event_id": "evt-forbidden-direct",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms,
                "received_at_ms": now_ms,
                "user_id": "u1",
                "visit_id": "visit-1",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": "history",
                "section": "",
                "action": "view",
                "properties_json": {"full_answer_text": "do not store"},
            }
        )


def test_store_builds_batch_member_summaries_with_one_query_shape(tmp_path: Path) -> None:
    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    now_ms = int(time.time() * 1000)
    for user_id, module in [("u1", "history"), ("u2", "learning_report")]:
        store.record_event(
            {
                "event_id": f"evt-{user_id}",
                "event_name": "module_viewed",
                "event_version": 1,
                "occurred_at_ms": now_ms,
                "received_at_ms": now_ms,
                "user_id": user_id,
                "visit_id": f"visit-{user_id}",
                "session_id": "",
                "turn_id": "",
                "surface": "web",
                "module": module,
                "section": "",
                "action": "view",
                "properties_json": {},
            }
        )

    summaries = store.get_member_behavior_summaries(["u1", "u2"], days=7)
    assert summaries["u1"]["history_open_count_7d"] == 1
    assert summaries["u2"]["learning_report_open_count_7d"] == 1


def test_default_product_behavior_store_uses_independent_sibling_db(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from deeptutor.services import observability
    from deeptutor.services.session import sqlite_store

    session_db = tmp_path / "chat_history.db"
    monkeypatch.setattr(
        sqlite_store,
        "get_sqlite_session_store",
        lambda: SimpleNamespace(db_path=session_db),
    )

    store = observability.reset_product_behavior_store()

    assert Path(store.db_path) == tmp_path / "product_behavior.db"
    assert Path(store.db_path) != session_db
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/services/observability/test_product_behavior_store.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement SQLite store**

Create `deeptutor/services/observability/product_behavior_store.py`:

```python
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from deeptutor.services.observability.product_behavior_catalog import FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS


def _safe_properties_json(value: Any) -> str:
    if isinstance(value, str):
        try:
            raw = json.loads(value or "{}")
        except json.JSONDecodeError:
            raw = {}
    elif isinstance(value, dict):
        raw = value
    else:
        raw = {}

    forbidden = sorted(set(raw) & FORBIDDEN_PRODUCT_BEHAVIOR_FIELDS)
    if forbidden:
        raise ValueError(f"Forbidden product behavior property: {forbidden[0]}")
    return json.dumps(raw, ensure_ascii=False, sort_keys=True)


class SQLiteProductBehaviorStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists product_behavior_events (
                  event_id text primary key,
                  event_name text not null,
                  event_version integer not null,
                  occurred_at_ms integer not null,
                  received_at_ms integer not null,
                  user_id text not null,
                  visit_id text not null,
                  session_id text not null default '',
                  turn_id text not null default '',
                  surface text not null,
                  module text not null,
                  section text not null default '',
                  action text not null,
                  properties_json text not null default '{}'
                )
                """
            )
            conn.execute("create index if not exists idx_pbe_user_time on product_behavior_events(user_id, occurred_at_ms)")
            conn.execute("create index if not exists idx_pbe_module_time on product_behavior_events(module, occurred_at_ms)")
            conn.execute("create index if not exists idx_pbe_section_time on product_behavior_events(module, section, occurred_at_ms)")

    def record_event(self, event: dict[str, Any]) -> dict[str, Any]:
        properties = _safe_properties_json(event.get("properties_json"))
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    insert into product_behavior_events (
                      event_id, event_name, event_version, occurred_at_ms, received_at_ms,
                      user_id, visit_id, session_id, turn_id, surface, module, section, action, properties_json
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(event["event_id"]),
                        str(event["event_name"]),
                        int(event.get("event_version") or 1),
                        int(event.get("occurred_at_ms") or 0),
                        int(event.get("received_at_ms") or int(time.time() * 1000)),
                        str(event["user_id"]),
                        str(event["visit_id"]),
                        str(event.get("session_id") or ""),
                        str(event.get("turn_id") or ""),
                        str(event["surface"]),
                        str(event["module"]),
                        str(event.get("section") or ""),
                        str(event["action"]),
                        properties,
                    ),
                )
            return {"accepted": True, "status": "accepted", "event_id": str(event["event_id"])}
        except sqlite3.IntegrityError:
            return {"accepted": False, "status": "duplicate", "event_id": str(event["event_id"])}

    def _since_ms(self, days: int) -> int:
        return int((time.time() - max(1, days) * 86400) * 1000)

    def _empty_summary(self) -> dict[str, Any]:
        return {
            "learning_report_open_count_7d": 0,
            "history_open_count_7d": 0,
            "action_start_count_7d": 0,
            "cohort": "",
            "trust_level": "B",
        }

    def get_member_behavior_summaries(self, user_ids: list[str], *, days: int = 7) -> dict[str, dict[str, Any]]:
        unique_user_ids = sorted({str(user_id) for user_id in user_ids if str(user_id)})
        if not unique_user_ids:
            return {}
        since = self._since_ms(days)
        placeholders = ",".join("?" for _ in unique_user_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                select user_id, module, event_name, count(*) as count
                from product_behavior_events
                where user_id in ({placeholders}) and occurred_at_ms >= ?
                group by user_id, module, event_name
                """,
                (*unique_user_ids, since),
            ).fetchall()
        counts_by_user: dict[str, dict[tuple[str, str], int]] = {user_id: {} for user_id in unique_user_ids}
        for row in rows:
            counts_by_user[str(row["user_id"])][(str(row["module"]), str(row["event_name"]))] = int(row["count"])

        summaries: dict[str, dict[str, Any]] = {}
        for user_id, counts in counts_by_user.items():
            report_count = counts.get(("learning_report", "module_viewed"), 0)
            history_count = counts.get(("history", "module_viewed"), 0)
            action_count = sum(
                count
                for (_module, event_name), count in counts.items()
                if event_name == "learning_action_started"
            )
            cohort = "report_high_no_action" if report_count >= 3 and action_count == 0 else ""
            summaries[user_id] = {
                "learning_report_open_count_7d": report_count,
                "history_open_count_7d": history_count,
                "action_start_count_7d": action_count,
                "cohort": cohort,
                "trust_level": "B",
            }
        return summaries

    def get_member_behavior_summary(self, user_id: str, *, days: int = 7) -> dict[str, Any]:
        return self.get_member_behavior_summaries([user_id], days=days).get(user_id, self._empty_summary())

    def get_learning_report_section_breakdown(self, user_id: str, *, days: int = 7) -> list[dict[str, Any]]:
        since = self._since_ms(days)
        with self._connect() as conn:
            rows = conn.execute(
                """
                select section, count(*) as view_count
                from product_behavior_events
                where user_id = ?
                  and occurred_at_ms >= ?
                  and module = 'learning_report'
                  and event_name = 'section_viewed'
                  and section != ''
                group by section
                order by view_count desc, section asc
                """,
                (user_id, since),
            ).fetchall()
        return [{"section": str(row["section"]), "view_count": int(row["view_count"])} for row in rows]

    def get_member_timeline(self, user_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select event_id, event_name, occurred_at_ms, surface, module, section, action
                from product_behavior_events
                where user_id = ?
                order by occurred_at_ms desc
                limit ?
                """,
                (user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]
```

- [ ] **Step 4: Export singleton helpers**

Modify `deeptutor/services/observability/__init__.py` to expose:

```python
from pathlib import Path

from deeptutor.services.observability.product_behavior_store import SQLiteProductBehaviorStore

_product_behavior_store: SQLiteProductBehaviorStore | None = None


def get_product_behavior_store() -> SQLiteProductBehaviorStore:
    global _product_behavior_store
    if _product_behavior_store is None:
        from deeptutor.services.session.sqlite_store import get_sqlite_session_store

        session_db_path = Path(get_sqlite_session_store().db_path)
        _product_behavior_store = SQLiteProductBehaviorStore(session_db_path.with_name("product_behavior.db"))
    return _product_behavior_store


def reset_product_behavior_store(db_path=None) -> SQLiteProductBehaviorStore:
    global _product_behavior_store
    if db_path is None:
        from deeptutor.services.session.sqlite_store import get_sqlite_session_store

        session_db_path = Path(get_sqlite_session_store().db_path)
        db_path = session_db_path.with_name("product_behavior.db")
    _product_behavior_store = SQLiteProductBehaviorStore(db_path)
    return _product_behavior_store
```

Keep existing exports intact.

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/services/observability/test_product_behavior_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deeptutor/services/observability/product_behavior_store.py deeptutor/services/observability/__init__.py tests/services/observability/test_product_behavior_store.py
git commit -m "feat: add product behavior sqlite store"
```

## Task 4: Extend Surface Events Ingestion

**Files:**
- Modify: `deeptutor/services/observability/surface_events.py`
- Modify: `deeptutor/api/routers/observability.py`
- Modify: `tests/api/test_observability_router.py`

- [ ] **Step 1: Add failing router tests**

Append to `tests/api/test_observability_router.py`:

```python
def test_surface_event_router_persists_product_behavior_event(tmp_path) -> None:
    observability_module.reset_product_behavior_store(tmp_path / "behavior.db")
    app = _build_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/observability/surface-events",
            json={
                "event_id": "evt-product-1",
                "surface": "web",
                "event_name": "module_viewed",
                "collected_at_ms": 1710000000000,
                "sent_at_ms": 1710000000100,
                "metadata": {
                    "visit_id": "visit-u1-1",
                    "module": "learning_report",
                    "action": "view",
                    "release_id": "rel-web-1",
                },
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    summary = observability_module.get_product_behavior_store().get_member_behavior_summary("admin_demo")
    assert summary["learning_report_open_count_7d"] == 1


def test_surface_event_router_rejects_product_behavior_without_visit_id(tmp_path) -> None:
    observability_module.reset_product_behavior_store(tmp_path / "behavior.db")
    app = _build_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/observability/surface-events",
            json={
                "event_id": "evt-product-no-visit",
                "surface": "web",
                "event_name": "module_viewed",
                "metadata": {
                    "module": "learning_report",
                    "action": "view",
                },
            },
        )

    assert response.status_code == 400
    assert "visit_id is required" in response.json()["detail"]


def test_surface_event_router_accepts_error_event_without_visit_id(tmp_path) -> None:
    observability_module.reset_product_behavior_store(tmp_path / "behavior.db")
    app = _build_app()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/observability/surface-events",
            json={
                "event_id": "evt-product-error-no-visit",
                "surface": "web",
                "event_name": "event_error",
                "metadata": {
                    "module": "learning_report",
                    "action": "error",
                    "error_code": "observer_unavailable",
                },
            },
        )

    assert response.status_code == 202
    timeline = observability_module.get_product_behavior_store().get_member_timeline("admin_demo")
    assert timeline[0]["event_name"] == "event_error"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/api/test_observability_router.py::test_surface_event_router_persists_product_behavior_event tests/api/test_observability_router.py::test_surface_event_router_rejects_product_behavior_without_visit_id tests/api/test_observability_router.py::test_surface_event_router_accepts_error_event_without_visit_id -q
```

Expected: FAIL because `reset_product_behavior_store` is not yet imported/exported or product events are unsupported.

- [ ] **Step 3: Extend `SurfaceEventStore.ingest` without breaking ACK smoke**

Modify `deeptutor/services/observability/surface_events.py`:

```python
from deeptutor.services.observability.product_behavior_catalog import (
    PRODUCT_BEHAVIOR_EVENT_NAMES,
    validate_product_behavior_event,
)
```

Extend `_ALLOWED_EVENT_NAMES`:

```python
_ALLOWED_EVENT_NAMES = {
    "ws_connected",
    "start_turn_sent",
    "session_event_received",
    "first_visible_content_rendered",
    "done_rendered",
    "user_cancelled",
    "resume_attempted",
    "resume_succeeded",
    "surface_render_failed",
    *PRODUCT_BEHAVIOR_EVENT_NAMES,
}
```

After appending to `_recent_events`, add:

```python
            if event_name in PRODUCT_BEHAVIOR_EVENT_NAMES:
                from deeptutor.services.observability import get_product_behavior_store

                product_event = validate_product_behavior_event(
                    event_name,
                    {
                        **normalized_metadata,
                        "surface": surface,
                    },
                )
                get_product_behavior_store().record_event(
                    {
                        "event_id": event_id,
                        "event_name": event_name,
                        "event_version": int(normalized_metadata.get("event_version") or 1),
                        "occurred_at_ms": collected_at_ms or ingested_at_ms,
                        "received_at_ms": ingested_at_ms,
                        "user_id": user_id,
                        "visit_id": product_event["visit_id"],
                        "session_id": session_id,
                        "turn_id": turn_id,
                        "surface": surface,
                        "module": product_event["module"],
                        "section": product_event["section"],
                        "action": product_event["action"],
                        "properties_json": normalized_metadata,
                    }
                )
```

- [ ] **Step 4: Preserve router metadata guard**

Do not increase `_SURFACE_EVENT_METADATA_MAX_BYTES`. Do not add `extra="allow"` to `SurfaceEventIngestRequest`; product behavior fields stay inside `metadata`.

- [ ] **Step 5: Run observability tests**

Run:

```bash
pytest tests/api/test_observability_router.py tests/services/observability/test_surface_ack_smoke.py -q
```

Expected: PASS. Existing ACK snapshot tests must still pass.

- [ ] **Step 6: Commit**

```bash
git add deeptutor/services/observability/surface_events.py deeptutor/api/routers/observability.py tests/api/test_observability_router.py
git commit -m "feat: persist product behavior via surface events"
```

## Task 5: Client `visit_id` and Product Behavior Helpers

**Files:**
- Modify: `web/lib/surface-telemetry.ts`
- Modify: `wx_miniprogram/utils/surface-telemetry.js`
- Modify: `yousenwebview/packageDeeptutor/utils/surface-telemetry.js`
- Create: `web/tests/product-behavior-surface-telemetry.test.ts`

- [ ] **Step 1: Add source guard test**

Create `web/tests/product-behavior-surface-telemetry.test.ts`:

```typescript
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const webRoot = resolve(import.meta.dirname, '..')
const repoRoot = resolve(webRoot, '..')

async function readRepo(path: string): Promise<string> {
  return readFile(resolve(repoRoot, path), 'utf8')
}

test('web product behavior helper reuses surface-events endpoint and visit_id', async () => {
  const source = await readRepo('web/lib/surface-telemetry.ts')
  assert.match(source, /observability\\/surface-events/)
  assert.doesNotMatch(source, /product-behavior\\/events/)
  assert.match(source, /visitId/)
  assert.match(source, /trackWebProductBehaviorEvent/)
})

test('wechat product behavior helper reuses surface-events endpoint and visit_id', async () => {
  const source = await readRepo('wx_miniprogram/utils/surface-telemetry.js')
  assert.match(source, /observability\\/surface-events/)
  assert.doesNotMatch(source, /product-behavior\\/events/)
  assert.match(source, /visitId/)
  assert.match(source, /trackProductBehavior/)
})

test('yousen product behavior helper reuses surface-events endpoint and visit_id', async () => {
  const source = await readRepo('yousenwebview/packageDeeptutor/utils/surface-telemetry.js')
  assert.match(source, /observability\\/surface-events/)
  assert.doesNotMatch(source, /product-behavior\\/events/)
  assert.match(source, /visitId/)
  assert.match(source, /trackProductBehavior/)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd web && node --test tests/product-behavior-surface-telemetry.test.ts
```

Expected: FAIL because helpers do not yet include `visitId` or product behavior wrappers.

- [ ] **Step 3: Extend web helper**

Modify `web/lib/surface-telemetry.ts`:

```typescript
type ProductBehaviorEventName =
  | "module_viewed"
  | "section_viewed"
  | "section_expanded"
  | "learning_action_started"
  | "learning_action_completed"
  | "module_returned"
  | "module_exited"
  | "event_error";

type ProductBehaviorPayload = {
  eventName: ProductBehaviorEventName;
  visitId: string;
  module: string;
  action: string;
  section?: string;
  objectType?: string;
  objectId?: string;
  entrySource?: string;
  referrerModule?: string;
  durationMs?: number;
  visibleMs?: number;
  result?: string;
  errorCode?: string;
  releaseId?: string;
  appVersion?: string;
  platform?: string;
  deviceModel?: string;
  networkType?: string;
};

export function getOrCreateWebBehaviorVisitId(): string {
  const key = "deeptutor_behavior_visit_id";
  const now = Date.now();
  const maxAgeMs = 30 * 60 * 1000;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw) {
      const parsed = JSON.parse(raw) as { id?: string; touchedAt?: number };
      if (parsed.id && parsed.touchedAt && now - parsed.touchedAt < maxAgeMs) {
        window.localStorage.setItem(key, JSON.stringify({ id: parsed.id, touchedAt: now }));
        return parsed.id;
      }
    }
    const id = `web-visit-${buildEventId()}`;
    window.localStorage.setItem(key, JSON.stringify({ id, touchedAt: now }));
    return id;
  } catch (_) {
    return `web-visit-${buildEventId()}`;
  }
}

export async function trackWebProductBehaviorEvent(payload: ProductBehaviorPayload): Promise<void> {
  await trackWebSurfaceEvent({
    eventName: payload.eventName,
    metadata: {
      visit_id: payload.visitId,
      module: payload.module,
      section: payload.section || "",
      action: payload.action,
      object_type: payload.objectType || "",
      object_id: payload.objectId || "",
      entry_source: payload.entrySource || "",
      referrer_module: payload.referrerModule || "",
      duration_ms: payload.durationMs || 0,
      visible_ms: payload.visibleMs || 0,
      result: payload.result || "",
      error_code: payload.errorCode || "",
      release_id: payload.releaseId || "",
      app_version: payload.appVersion || "",
      platform: payload.platform || "web",
      device_model: payload.deviceModel || "",
      network_type: payload.networkType || "",
    },
  });
}
```

- [ ] **Step 4: Extend WeChat and yousen helpers**

Add to both JS helpers:

```javascript
function getOrCreateVisitId() {
  var key = "deeptutor_behavior_visit_id";
  var now = Date.now();
  var maxAgeMs = 30 * 60 * 1000;
  try {
    var raw = wx.getStorageSync(key);
    if (raw && raw.id && raw.touchedAt && now - raw.touchedAt < maxAgeMs) {
      wx.setStorageSync(key, { id: raw.id, touchedAt: now });
      return raw.id;
    }
    var id = "wx_visit_" + buildEventId();
    wx.setStorageSync(key, { id: id, touchedAt: now });
    return id;
  } catch (_) {
    return "wx_visit_" + buildEventId();
  }
}

function trackProductBehavior(eventName, payload) {
  var data = payload && typeof payload === "object" ? payload : {};
  var visitId = data.visitId || getOrCreateVisitId();
  track(eventName, {
    sessionId: data.sessionId || "",
    turnId: data.turnId || "",
    metadata: {
      visit_id: visitId,
      module: data.module || "",
      section: data.section || "",
      action: data.action || "",
      object_type: data.objectType || "",
      object_id: data.objectId || "",
      entry_source: data.entrySource || "",
      referrer_module: data.referrerModule || "",
      duration_ms: data.durationMs || 0,
      visible_ms: data.visibleMs || 0,
      result: data.result || "",
      error_code: data.errorCode || "",
      release_id: data.releaseId || "",
      app_version: data.appVersion || "",
      platform: data.platform || "",
      device_model: data.deviceModel || "",
      network_type: data.networkType || "",
    },
  });
}
```

Export `getOrCreateVisitId` and `trackProductBehavior`.

- [ ] **Step 5: Run client tests**

Run:

```bash
cd web && node --test tests/product-behavior-surface-telemetry.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/lib/surface-telemetry.ts wx_miniprogram/utils/surface-telemetry.js yousenwebview/packageDeeptutor/utils/surface-telemetry.js web/tests/product-behavior-surface-telemetry.test.ts
git commit -m "feat: add product behavior tracking helpers"
```

## Task 6: BI Metrics Registry

**Files:**
- Modify: `deeptutor/services/bi_metrics.py`
- Modify: `web/lib/bi-v2-metric-registry.generated.ts`
- Modify: `tests/services/test_bi_metrics.py`

- [ ] **Step 1: Add failing metric tests**

Append to `tests/services/test_bi_metrics.py`:

```python
def test_bi_metric_dictionary_includes_product_behavior_metrics() -> None:
    ids = {metric.metric_id for metric in BI_METRICS}

    assert {
        "behavior.module.open_count",
        "behavior.learning_report.section_view_count",
        "behavior.funnel.report_to_training",
        "behavior.member_ops.report_high_no_action",
    }.issubset(ids)


def test_product_behavior_metrics_drill_into_member_ops() -> None:
    for metric_id in [
        "behavior.module.open_count",
        "behavior.learning_report.section_view_count",
        "behavior.funnel.report_to_training",
        "behavior.member_ops.report_high_no_action",
    ]:
        metric = metric_by_id(metric_id)
        assert metric.group == "product_behavior"
        assert metric.drilldown == "member_ops"
        assert metric.owner in {"product", "ops"}
        assert metric.trust_level in {"A", "B"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/services/test_bi_metrics.py::test_bi_metric_dictionary_includes_product_behavior_metrics tests/services/test_bi_metrics.py::test_product_behavior_metrics_drill_into_member_ops -q
```

Expected: FAIL because metrics are not registered.

- [ ] **Step 3: Add metric definitions**

Append four `BIMetricDefinition(...)` entries to `BI_METRICS`:

```python
BIMetricDefinition(
    metric_id="behavior.module.open_count",
    label="模块打开次数",
    group="product_behavior",
    definition="窗口内用户进入学习产品模块的次数，来自 product_behavior_events indexed raw read model。",
    authority="product_behavior_store",
    trust_level="B",
    owner="product",
    drilldown="member_ops",
    refresh_cadence="近实时 indexed raw read",
    degraded_note="visit_id、release_id 或 section visibility 缺失时降级为 B/C。",
),
BIMetricDefinition(
    metric_id="behavior.learning_report.section_view_count",
    label="学情 section 浏览次数",
    group="product_behavior",
    definition="窗口内学情页 section 进入视口或 fallback 渲染曝光次数。",
    authority="product_behavior_store",
    trust_level="B",
    owner="product",
    drilldown="member_ops",
    refresh_cadence="近实时 indexed raw read",
    degraded_note="小程序/yousen 曝光口径未完成三端一致 smoke 前保持 B 级。",
),
BIMetricDefinition(
    metric_id="behavior.funnel.report_to_training",
    label="学情到训练转化",
    group="product_behavior",
    definition="学情浏览后进入训练的用户或 visit 占比。",
    authority="product_behavior_store",
    trust_level="B",
    owner="product",
    drilldown="member_ops",
    refresh_cadence="近实时 indexed raw read",
    degraded_note="缺 visit_id 时不进入 A 级漏斗。",
),
BIMetricDefinition(
    metric_id="behavior.member_ops.report_high_no_action",
    label="学情高频无行动",
    group="product_behavior",
    definition="7 天学情打开不少于 3 次且训练/复测开始为 0 的会员队列。",
    authority="product_behavior_store",
    trust_level="B",
    owner="ops",
    drilldown="member_ops",
    refresh_cadence="近实时 indexed raw read",
    degraded_note="低可信 cohort 只允许人工参考，不进入自动运营队列。",
),
```

- [ ] **Step 4: Regenerate TypeScript registry**

Run:

```bash
python -m scripts.gen_bi_metrics_ts
```

Expected: updates `web/lib/bi-v2-metric-registry.generated.ts`.

- [ ] **Step 5: Run registry tests**

Run:

```bash
pytest tests/services/test_bi_metrics.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deeptutor/services/bi_metrics.py web/lib/bi-v2-metric-registry.generated.ts tests/services/test_bi_metrics.py
git commit -m "feat: register product behavior BI metrics"
```

## Task 7: Member Console Behavior Projection

**Files:**
- Modify: `deeptutor/services/member_console/service.py`
- Modify: `tests/services/member_console/test_service.py`
- Modify: `tests/api/test_member_router_auth.py`

- [ ] **Step 1: Add service tests**

Append to `tests/services/member_console/test_service.py`:

```python
def test_member_360_includes_product_behavior_snapshot(tmp_path, monkeypatch):
    import time

    from deeptutor.services.observability.product_behavior_store import SQLiteProductBehaviorStore
    from deeptutor.services import observability

    store = SQLiteProductBehaviorStore(tmp_path / "behavior.db")
    monkeypatch.setattr(observability, "get_product_behavior_store", lambda: store)
    now_ms = int(time.time() * 1000)
    store.record_event(
        {
            "event_id": "evt-member-360-1",
            "event_name": "section_viewed",
            "event_version": 1,
            "occurred_at_ms": now_ms,
            "received_at_ms": now_ms + 100,
            "user_id": "student_demo",
            "visit_id": "visit-u1-1",
            "session_id": "",
            "turn_id": "",
            "surface": "web",
            "module": "learning_report",
            "section": "next_action",
            "action": "view",
            "properties_json": {},
        }
    )

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    payload = service.get_member_360("student_demo")

    assert payload["behavior"]["summary"]["learning_report_open_count_7d"] == 0
    assert payload["behavior"]["learning_report_sections"][0]["section"] == "next_action"
    assert payload["behavior"]["timeline"][0]["event_name"] == "section_viewed"


def test_list_members_loads_behavior_summaries_in_one_batch(tmp_path, monkeypatch):
    from deeptutor.services import observability

    class FakeBehaviorStore:
        def __init__(self):
            self.batch_calls = 0
            self.single_calls = 0

        def get_member_behavior_summaries(self, user_ids, *, days=7):
            self.batch_calls += 1
            return {
                str(user_id): {
                    "learning_report_open_count_7d": 1,
                    "history_open_count_7d": 0,
                    "action_start_count_7d": 0,
                    "cohort": "",
                    "trust_level": "B",
                }
                for user_id in user_ids
            }

        def get_member_behavior_summary(self, user_id, *, days=7):
            self.single_calls += 1
            raise AssertionError("list_members must use get_member_behavior_summaries")

    fake_store = FakeBehaviorStore()
    monkeypatch.setattr(observability, "get_product_behavior_store", lambda: fake_store)

    service = MemberConsoleService()
    service._data_path = tmp_path / "member_console.json"
    payload = service.list_members(page=1, page_size=20)

    assert fake_store.batch_calls == 1
    assert fake_store.single_calls == 0
    assert payload["items"]
    assert payload["items"][0]["behavior"]["learning_report_open_count_7d"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/services/member_console/test_service.py -q
```

Expected: FAIL on missing `behavior` payload.

- [ ] **Step 3: Add behavior projection helpers to member console service**

In `deeptutor/services/member_console/service.py`, add helper methods:

```python
def _get_product_behavior_store(self):
    from deeptutor.services.observability import get_product_behavior_store

    return get_product_behavior_store()


def _load_member_behavior_payload(self, user_id: str) -> dict[str, Any]:
    try:
        store = self._get_product_behavior_store()
        return {
            "summary": store.get_member_behavior_summary(user_id, days=7),
            "learning_report_sections": store.get_learning_report_section_breakdown(user_id, days=7),
            "timeline": store.get_member_timeline(user_id, limit=20),
        }
    except Exception:
        logger.warning("Failed to load product behavior for member: user_id=%s", user_id, exc_info=True)
        return {
            "summary": {
                "learning_report_open_count_7d": 0,
                "history_open_count_7d": 0,
                "action_start_count_7d": 0,
                "cohort": "",
                "trust_level": "C",
            },
            "learning_report_sections": [],
            "timeline": [],
        }
```

Add a page-level batch helper for member lists:

```python
def _load_member_behavior_summaries(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
    try:
        return self._get_product_behavior_store().get_member_behavior_summaries(user_ids, days=7)
    except Exception:
        logger.warning("Failed to load product behavior summaries for member list", exc_info=True)
        return {
            user_id: {
                "learning_report_open_count_7d": 0,
                "history_open_count_7d": 0,
                "action_start_count_7d": 0,
                "cohort": "",
                "trust_level": "C",
            }
            for user_id in user_ids
        }
```

Then:

- In `get_dashboard()`, add `behavior_health` with indexed raw summary counts from the behavior store if available.
- In `list_members()`, build `page_items = filtered[start:end]`, call `_load_member_behavior_summaries([item["user_id"] for item in page_items])` once, then attach `behavior` per member item from the returned dict. Do not call `get_member_behavior_summary()` inside the item loop.
- In `get_member_360()`, add `member["behavior"] = self._load_member_behavior_payload(user_id)`.

- [ ] **Step 4: Add member router regression**

In `tests/api/test_member_router_auth.py`, add a test that authenticated admin `GET /api/v1/member/u1/360` returns `behavior.summary.trust_level`.

Expected assertion:

```python
assert response.status_code == 200
assert "behavior" in response.json()
assert "summary" in response.json()["behavior"]
```

- [ ] **Step 5: Run member tests**

Run:

```bash
pytest tests/services/member_console/test_service.py tests/api/test_member_router_auth.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deeptutor/services/member_console/service.py tests/services/member_console/test_service.py tests/api/test_member_router_auth.py
git commit -m "feat: project product behavior into member console"
```

## Task 8: BI Member Ops UI

**Files:**
- Modify: `web/lib/member-api.ts`
- Modify: `web/app/(workspace)/bi/_v2/member-ops/data.ts`
- Modify: `web/app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx`
- Modify: `web/app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx`
- Modify: `web/tests/bi-v2-testids.test.ts`

- [ ] **Step 1: Add source-level UI test**

Append to `web/tests/bi-v2-testids.test.ts`:

```typescript
test('member ops exposes product behavior UI anchors', async () => {
  const panel = await readWeb('app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx')
  const drawer = await readWeb('app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx')

  assert.ok(panel.includes('data-testid="bi-member-behavior-health-strip"'))
  assert.ok(panel.includes('data-testid="bi-member-behavior-cohort-tabs"'))
  assert.ok(panel.includes('report_high_no_action'))
  assert.ok(drawer.includes('data-testid="bi-member-behavior-timeline"'))
  assert.ok(drawer.includes('data-testid="bi-member-learning-report-breakdown"'))
})
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd web && node --test tests/bi-v2-testids.test.ts
```

Expected: FAIL on missing anchors.

- [ ] **Step 3: Extend member API types**

In `web/lib/member-api.ts`, add:

```typescript
export type MemberBehaviorSummary = {
  learning_report_open_count_7d: number
  history_open_count_7d: number
  action_start_count_7d: number
  cohort: string
  trust_level: 'A' | 'B' | 'C' | string
}

export type MemberBehaviorTimelineEvent = {
  event_id: string
  event_name: string
  occurred_at_ms: number
  surface: string
  module: string
  section: string
  action: string
}

export type MemberBehaviorPayload = {
  summary: MemberBehaviorSummary
  learning_report_sections: Array<{ section: string; view_count: number }>
  timeline: MemberBehaviorTimelineEvent[]
}
```

Add `behavior?: MemberBehaviorPayload` to `MemberDetail` and `behavior?: MemberBehaviorSummary` to list item type.

- [ ] **Step 4: Extend member row model**

In `web/app/(workspace)/bi/_v2/member-ops/data.ts`, add fields:

```typescript
behavior_learning_report_7d?: number
behavior_history_7d?: number
behavior_cohort?: string
behavior_trust?: string
behavior_next_action?: string
```

Add column keys:

```typescript
| 'behavior_report'
| 'behavior_history'
| 'behavior_cohort'
| 'behavior_next_action'
```

Add default behavior columns after `risk`:

```typescript
'behavior_report',
'behavior_history',
'behavior_cohort',
```

- [ ] **Step 5: Add health strip and cohort tabs**

In `BiV2MemberOpsPanel.tsx`, add:

```tsx
const BEHAVIOR_COHORTS = [
  { key: '', label: '全部行为' },
  { key: 'report_high_no_action', label: '学情高频无行动' },
  { key: 'history_high_no_review', label: '历史高频无复盘' },
  { key: 'chat_only', label: '只对话不看学情' },
  { key: 'training_no_retest', label: '训练未复测' },
] as const
```

Render before the table:

```tsx
const behaviorCards = [
  { label: '学情打开', value: behaviorTotals.report, hint: '7 日 module_viewed' },
  { label: '历史打开', value: behaviorTotals.history, hint: '7 日 module_viewed' },
  { label: '行动开始', value: behaviorTotals.actions, hint: '训练 / 复盘 / 复测' },
  { label: '数据可信', value: behaviorTotals.trust, hint: 'product_behavior_store' },
] as const
```

Render the cards using the existing `MemberSummaryCards` visual pattern in the same file:

```tsx
<section data-testid="bi-member-behavior-health-strip" className="grid grid-cols-2 gap-3 md:grid-cols-4">
  {behaviorCards.map(card => (
    <div key={card.label} className="rounded-3xl border border-white/10 bg-white/[0.045] p-3 shadow-lg shadow-black/10">
      <div className="text-[11px] font-bold text-slate-400">{card.label}</div>
      <div className="mt-1 text-2xl font-black tabular-nums text-slate-50">
        {loading && card.value === undefined ? '…' : (card.value ?? '—')}
      </div>
      <div className="mt-1 text-[11px] font-semibold text-slate-500">{card.hint}</div>
    </div>
  ))}
</section>

<div data-testid="bi-member-behavior-cohort-tabs" className="flex flex-wrap gap-2">
  {BEHAVIOR_COHORTS.map(item => (
    <button key={item.key} type="button" onClick={() => setBehaviorCohort(item.key)}>
      {item.label}
    </button>
  ))}
</div>
```

Use existing local state/filter style from the panel; do not add raw `fetch`.

- [ ] **Step 6: Render behavior columns**

Extend existing cell renderer:

```tsx
if (key === 'behavior_report') return <span>{row.behavior_learning_report_7d ?? 0}</span>
if (key === 'behavior_history') return <span>{row.behavior_history_7d ?? 0}</span>
if (key === 'behavior_cohort') return <BiStatusPill tone={row.behavior_cohort ? 'amber' : 'slate'}>{row.behavior_cohort || '正常'}</BiStatusPill>
if (key === 'behavior_next_action') return <span>{row.behavior_next_action || '观察'}</span>
```

- [ ] **Step 7: Add drawer behavior sections**

In `Member360Drawer.tsx`, add:

```tsx
<Section title="行为时间线" trust={detail?.behavior?.summary?.trust_level || 'C'}>
  <div data-testid="bi-member-behavior-timeline" className="space-y-2">
    {(detail?.behavior?.timeline || []).slice(0, 8).map(event => (
      <KV
        key={event.event_id}
        label={event.module}
        value={`${event.event_name}${event.section ? ` · ${event.section}` : ''}`}
      />
    ))}
    {(detail?.behavior?.timeline || []).length === 0 ? <p className="text-xs text-slate-400">暂无行为样本</p> : null}
  </div>
</Section>

<Section title="学情 section" trust={detail?.behavior?.summary?.trust_level || 'C'}>
  <div data-testid="bi-member-learning-report-breakdown" className="space-y-2">
    {(detail?.behavior?.learning_report_sections || []).slice(0, 8).map(item => (
      <KV key={item.section} label={item.section} value={`${item.view_count} 次`} />
    ))}
    {(detail?.behavior?.learning_report_sections || []).length === 0 ? <p className="text-xs text-slate-400">暂无学情 section 样本</p> : null}
  </div>
</Section>
```

- [ ] **Step 8: Run UI source tests and raw fetch guard**

Run:

```bash
cd web && node --test tests/bi-v2-testids.test.ts
cd .. && pytest tests/web/test_bi_v2_raw_fetch_guard.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add web/lib/member-api.ts web/app/'(workspace)'/bi/_v2/member-ops/data.ts web/app/'(workspace)'/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx web/app/'(workspace)'/bi/_v2/member-ops/Member360Drawer.tsx web/tests/bi-v2-testids.test.ts
git commit -m "feat: surface behavior cohorts in member ops"
```

## Task 9: Raw Export Guard

**Files:**
- Modify: `deeptutor/services/bi_service.py`
- Modify: `deeptutor/contracts/bi_v2_write_endpoints.py`
- Modify: `web/lib/bi-v2-write-endpoints.generated.ts`
- Modify: `tests/api/test_bi_write_endpoints_registry.py`
- Modify: `tests/api/test_bi_router.py`

- [ ] **Step 1: Add API tests for behavior raw export**

Add to `tests/api/test_bi_router.py`:

```python
def test_behavior_export_job_is_raw_mode_and_audited(bi_service: BIService) -> None:
    result = asyncio.run(
        bi_service.request_export_job(
            dataset="product_behavior_raw",
            export_format="csv",
            filters={"cohort": "report_high_no_action"},
            operator="admin_demo",
            idempotency_key="behavior-export-1",
        )
    )

    job = result["export_job"]
    assert job["dataset"] == "product_behavior_raw"
    assert job["scrubbed"] is False
    assert job["raw_mode"] is True
    assert result["audit_id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/api/test_bi_router.py::test_behavior_export_job_is_raw_mode_and_audited -q
```

Expected: FAIL because dataset is not allowed.

- [ ] **Step 3: Add raw behavior export dataset**

In `deeptutor/services/bi_service.py`, extend `_EXPORT_DATASET_LABELS`:

```python
"product_behavior_raw": "产品行为 raw events",
```

In `request_export_job`, set:

```python
is_behavior_raw = normalized_dataset == "product_behavior_raw"
...
"scrubbed": not is_behavior_raw,
"raw_mode": is_behavior_raw,
```

Apply the same `scrubbed` / `raw_mode` values both to the audit payload and to the returned `export_job`. P0 creates an audited export job descriptor only; it does not need to extract actual raw CSV rows until the existing export worker is extended.

- [ ] **Step 4: Update write endpoint contract**

In `deeptutor/contracts/bi_v2_write_endpoints.py`, update export description to state:

```python
"product_behavior_raw is the only P0 raw_mode=true dataset; all other datasets remain scrubbed. P0 records the raw export job and audit trail; actual raw CSV extraction is deferred until the export worker supports behavior rows."
```

Regenerate `web/lib/bi-v2-write-endpoints.generated.ts` with the existing project generator:

```bash
python -m scripts.gen_bi_write_endpoints_ts
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/api/test_bi_router.py::test_behavior_export_job_is_raw_mode_and_audited tests/api/test_bi_write_endpoints_registry.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deeptutor/services/bi_service.py deeptutor/contracts/bi_v2_write_endpoints.py web/lib/bi-v2-write-endpoints.generated.ts tests/api/test_bi_write_endpoints_registry.py tests/api/test_bi_router.py
git commit -m "feat: add audited raw behavior export"
```

## Task 10: End-to-End P0 Guard Suite

**Files:**
- Create: `tests/api/test_product_behavior_p0_flow.py`
- Modify: `docs/qa/2026-06-02-product-behavior-reality-audit.md`

- [ ] **Step 1: Add end-to-end API test**

Create `tests/api/test_product_behavior_p0_flow.py`:

```python
from __future__ import annotations

import importlib
import time

import pytest

pytest.importorskip("fastapi")
FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

from deeptutor.api.dependencies import AuthContext, get_current_user

observability_router = importlib.import_module("deeptutor.api.routers.observability").router
observability_module = importlib.import_module("deeptutor.services.observability")


def _ctx() -> AuthContext:
    return AuthContext(
        user_id="u_behavior_p0",
        provider="test",
        token="test-token",
        claims={"uid": "u_behavior_p0"},
        is_admin=True,
    )


def test_product_behavior_p0_surface_event_to_member_summary(tmp_path) -> None:
    observability_module.reset_surface_event_store()
    observability_module.reset_product_behavior_store(tmp_path / "behavior.db")
    app = FastAPI()
    app.include_router(observability_router, prefix="/api/v1/observability")
    app.dependency_overrides[get_current_user] = _ctx

    now_ms = int(time.time() * 1000)
    events = [
        ("evt-1", "module_viewed", {"visit_id": "visit-1", "module": "learning_report", "action": "view"}),
        ("evt-2", "section_viewed", {"visit_id": "visit-1", "module": "learning_report", "section": "next_action", "action": "view"}),
        ("evt-3", "module_viewed", {"visit_id": "visit-2", "module": "history", "action": "view"}),
    ]
    with TestClient(app) as client:
        for event_id, event_name, metadata in events:
            response = client.post(
                "/api/v1/observability/surface-events",
                json={
                    "event_id": event_id,
                    "surface": "web",
                    "event_name": event_name,
                    "collected_at_ms": now_ms,
                    "sent_at_ms": now_ms + 100,
                    "metadata": metadata,
                },
            )
            assert response.status_code == 202

    store = observability_module.get_product_behavior_store()
    summary = store.get_member_behavior_summary("u_behavior_p0", days=7)
    sections = store.get_learning_report_section_breakdown("u_behavior_p0", days=7)

    assert summary["learning_report_open_count_7d"] == 1
    assert summary["history_open_count_7d"] == 1
    assert sections == [{"section": "next_action", "view_count": 1}]
```

- [ ] **Step 2: Run P0 API guard**

Run:

```bash
pytest tests/api/test_product_behavior_p0_flow.py -q
```

Expected: PASS.

- [ ] **Step 3: Run required regression set**

Run:

```bash
pytest \
  tests/services/observability/test_product_behavior_catalog.py \
  tests/services/observability/test_product_behavior_store.py \
  tests/api/test_observability_router.py \
  tests/services/observability/test_surface_ack_smoke.py \
  tests/services/test_bi_metrics.py \
  tests/api/test_product_behavior_p0_flow.py \
  tests/web/test_bi_v2_raw_fetch_guard.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Run web source tests**

Run:

```bash
cd web && node --test tests/product-behavior-surface-telemetry.test.ts tests/bi-v2-testids.test.ts
```

Expected: PASS.

- [ ] **Step 5: Update QA evidence**

Append to `docs/qa/2026-06-02-product-behavior-reality-audit.md`:

```markdown
## P0 Implementation Evidence

- `pytest tests/api/test_product_behavior_p0_flow.py -q`: PASS
- `pytest tests/api/test_observability_router.py tests/services/observability/test_surface_ack_smoke.py -q`: PASS
- `pytest tests/services/test_bi_metrics.py -q`: PASS
- `pytest tests/web/test_bi_v2_raw_fetch_guard.py -q`: PASS
- `cd web && node --test tests/product-behavior-surface-telemetry.test.ts tests/bi-v2-testids.test.ts`: PASS

## Remaining Non-Automated Gates

- WeChat DevTools / `/wechat-harness` visible section smoke.
- Real BI visual check at `/bi?tab=member-ops`.
- Production event volume observation before enabling broader cohort automation.
```

- [ ] **Step 6: Commit**

```bash
git add tests/api/test_product_behavior_p0_flow.py docs/qa/2026-06-02-product-behavior-reality-audit.md
git commit -m "test: add product behavior p0 guard"
```

## Task 11: Manual BI and WeChat Acceptance

**Files:**
- Modify: `docs/qa/2026-06-02-product-behavior-reality-audit.md`

- [ ] **Step 1: Start local backend and web app**

Run:

```bash
deeptutor serve --port 8001
```

In a second terminal, run:

```bash
cd web && npm run dev
```

Expected: web server starts and `/bi?tab=member-ops` is reachable.

- [ ] **Step 2: Open BI member ops page**

Use Browser plugin or Playwright to open:

```text
http://localhost:3000/bi?tab=member-ops
```

Expected visible elements:

- behavior health strip
- cohort tabs
- behavior columns in member table
- Member360 drawer behavior timeline
- 学情 section breakdown
- trust level badge

- [ ] **Step 3: Capture screenshots**

Save screenshots under:

```text
artifacts/qa/product-behavior-bi-member-ops/
```

Required screenshots:

- desktop member ops first viewport
- desktop member 360 drawer
- mobile member ops first viewport
- mobile member 360 drawer

- [ ] **Step 4: WeChat/yousen smoke**

Run `/wechat-harness` or WeChat DevTools smoke for:

- `learning_report.module_viewed`
- `learning_report.section_viewed`
- `history.module_viewed`
- `learning_action_started:start_training`

Expected: endpoint accepts events and product behavior store summary updates.

- [ ] **Step 5: Record manual evidence**

Append to QA doc:

```markdown
## Manual Acceptance Evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| `/bi?tab=member-ops` desktop | pending_manual_until_recorded | `artifacts/qa/product-behavior-bi-member-ops/desktop-member-ops.png` |
| `/bi?tab=member-ops` mobile | pending_manual_until_recorded | `artifacts/qa/product-behavior-bi-member-ops/mobile-member-ops.png` |
| Member360 behavior drawer | pending_manual_until_recorded | `artifacts/qa/product-behavior-bi-member-ops/member-360-drawer.png` |
| `/wechat-harness` behavior smoke | pending_manual_until_recorded | command output or screenshot path |
| WeChat DevTools behavior smoke | pending_manual_until_recorded | screenshot path and notes |
```

- [ ] **Step 6: Commit QA evidence**

```bash
git add docs/qa/2026-06-02-product-behavior-reality-audit.md artifacts/qa/product-behavior-bi-member-ops
git commit -m "docs: add product behavior acceptance evidence"
```

## Final Verification

Run:

```bash
pytest \
  tests/services/observability/test_product_behavior_catalog.py \
  tests/services/observability/test_product_behavior_store.py \
  tests/api/test_observability_router.py \
  tests/services/observability/test_surface_ack_smoke.py \
  tests/services/test_bi_metrics.py \
  tests/api/test_product_behavior_p0_flow.py \
  tests/web/test_bi_v2_raw_fetch_guard.py \
  -q
```

Run:

```bash
cd web && node --test tests/product-behavior-surface-telemetry.test.ts tests/bi-v2-testids.test.ts
```

Run after frontend changes:

```bash
cd web && npm run lint
```

Manual:

- `/bi?tab=member-ops` visual check.
- Member360 drawer check.
- `/wechat-harness` or WeChat DevTools smoke.

## Rollback Plan

- Disable UI behavior columns by removing them from `DEFAULT_COLUMNS`; keep backend data harmless.
- Stop product behavior persistence by not invoking product behavior writer inside `SurfaceEventStore.ingest`; existing ACK smoke remains intact.
- Keep raw ledger tables in SQLite until a cleanup migration is explicitly approved.

## Self-Review

Spec coverage:

- Records history/report opens: Task 3 + Task 10.
- Records learning report section usage: Task 3 + Task 10.
- Uses existing surface telemetry authority: Task 4 + Task 5.
- Connects to BI member ops page: Task 7 + Task 8.
- Raw mode with audit boundary: Task 9.
- Avoids anonymous P0 behavior: Task 1 + Task 2.
- Avoids second endpoint/SDK: Task 4 + Task 5 guards.
- Data trust and BI metric registry: Task 6 + Task 8.

Placeholder scan:

- No unresolved placeholder tokens.
- No deferred implementation markers.
- Every code-changing task has a concrete test and command.

Known residual risks:

- P0 independent SQLite storage (`product_behavior.db`) is a deliberate pilot decision. If Phase -1 audit finds event volume or p95 member-ops reads exceed the indexed raw read budget, stop after Task 1 and revise this plan toward aggregate/outbox storage.
- Section visibility cannot be fully validated by source tests; it needs `/wechat-harness` / WeChat DevTools smoke.
