# Product Behavior Reality Audit

- Date: 2026-06-02
- Source PRD: `docs/plan/2026-06-02-luban-product-behavior-intelligence-prd.md`
- Execution plan: `docs/plan/2026-06-02-luban-product-behavior-intelligence-execution-plan.md`
- Decision: P0 proceeds only if all hard gates below pass.

## 1. Telemetry Authority

| Item | Evidence | Decision |
| --- | --- | --- |
| Web helper | `web/lib/surface-telemetry.ts:35` posts `/api/v1/observability/surface-events` | reuse |
| WeChat helper | `wx_miniprogram/utils/surface-telemetry.js:33` posts `/api/v1/observability/surface-events` | reuse |
| Yousen helper | `yousenwebview/packageDeeptutor/utils/surface-telemetry.js:33` posts `/api/v1/observability/surface-events` | reuse |
| Backend endpoint tests | `tests/api/test_observability_router.py` covers `/api/v1/observability/surface-events` accepted/deduped/error paths | reuse |
| ACK store | `deeptutor/services/observability/surface_events.py:42` defines `SurfaceEventStore`; `:185` keeps the singleton ACK store | preserve |

Decision: `telemetry_authority=reuse_surface_events`.

P0 must not add `/api/v1/product-behavior/events` and must not create a second client behavior SDK. Product behavior persistence is a downstream writer under the existing surface-events ingestion authority.

## 2. Storage / Join Decision

Current BI member ops reads `/api/v1/member/*`, served by `MemberConsoleService`.

Evidence:

| Item | Evidence | Decision |
| --- | --- | --- |
| Web member dashboard client | `web/lib/member-api.ts:268` defines `getMemberDashboard()` | reuse |
| Member dashboard endpoint | `web/lib/member-api.ts:269` fetches `/api/v1/member/dashboard` | reuse |
| Member list endpoint | `web/lib/member-api.ts:284` fetches `/api/v1/member/list` | reuse |
| Member 360 endpoint | `web/lib/member-api.ts:292` fetches `/api/v1/member/{user_id}/360` | reuse |
| Backend member router mount | `deeptutor/api/main.py:643` mounts member router at `/api/v1/member` | reuse |
| Member ops panel | `web/app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx:436` documents `/api/v1/member/list` and `/api/v1/member/<user_id>/360` | reuse |
| BI metric authority | `deeptutor/services/bi_metrics.py:28` defines `BI_METRICS` | reuse |
| BI metric generated mirror | `web/lib/bi-v2-metric-registry.generated.ts:3` is generated from `BI_METRICS` | regenerate only |

P0 storage decision:

```yaml
p0_storage: sqlite_product_behavior_db
p0_db_file: product_behavior.db
p0_raw_table: product_behavior_events
p0_read_model: reads_raw_with_indexes
p0_aggregate_tables: deferred_until_p1_or_volume_gate
p0_bi_join: member_console_reads_behavior_batch_summaries
```

Reason: P0 must land in `/bi?tab=member-ops`; current member ops data path already uses member APIs, so same-process indexed raw reads are the lowest-risk join. Product behavior writes must use an independent sibling SQLite file (`product_behavior.db`) instead of the chat/session SQLite file, because behavior events write on the request path and must not contend with core chat/session single-writer locks.

## 3. Section Visibility

| Surface | Mechanism | P0 trust |
| --- | --- | --- |
| web | `IntersectionObserver` in product behavior helper implementation | B until source test + browser smoke |
| wechat_miniprogram | `wx.createIntersectionObserver` or component visible fallback | B until WeChat DevTools/manual smoke |
| wechat_yousenwebview | host webview observer or component-visible fallback | B until smoke |

Decision: `section_visibility_trust=B` until three-surface smoke passes.

P0 may still proceed with B-level section visibility if the UI exposes trust level and does not present section counts as A-level facts.

## 4. Identity / Session

- `visit_id`: client-generated navigation session.
- `session_id`: optional turn/chat session.
- `turn_id`: optional turn correlation.
- `user_id`: backend authenticated user id; anonymous product behavior is disabled for P0.

Decision: `anonymous_behavior=disabled_for_p0`.

Guardrail: pure navigation behavior must not use chat `session_id` as the primary navigation session. Missing `visit_id` rejects normal product behavior events; `event_error` may be accepted without `visit_id` as low-trust diagnostic evidence.

## 5. Release Field

- Web: use existing release/build field if available, otherwise `unknown_release` and trust B.
- WeChat/yousen: use `ENV_VERSION` and system version for P0; trust B.
- Release-indexed funnel is not P0; `release_id` may remain in metadata/properties until a later indexed funnel requirement.

## 6. Raw Mode / Export Boundary

P0 internal BI analysis uses raw mode because the current product request explicitly does not require desensitization. This does not remove field governance:

- forbidden payload fields still cannot enter `properties_json`;
- ordinary BI export datasets remain scrubbed;
- `product_behavior_raw` is the only P0 raw-mode behavior export dataset;
- P0 creates an audited raw export job descriptor, not actual raw CSV extraction;
- third-party projection remains disabled unless separately approved.

## 7. Hard Gate

```yaml
telemetry_authority: reuse_surface_events
product_behavior_endpoint: none
p0_storage: sqlite_product_behavior_db
p0_db_file: product_behavior.db
p0_read_model: reads_raw_with_indexes
p0_bi_join: member_console_reads_behavior_batch_summaries
section_visibility_trust: B
anonymous_behavior: disabled_for_p0
raw_mode: internal_bi_only
raw_export_dataset: product_behavior_raw_descriptor_only
```

## 8. Evidence Command

Ran:

```bash
rg -n "/api/v1/observability/surface-events|SurfaceEventStore|BI_METRICS|getMemberDashboard|/api/v1/member" \
  web wx_miniprogram yousenwebview deeptutor tests
```

Observed evidence includes:

- `web/lib/surface-telemetry.ts:35`
- `wx_miniprogram/utils/surface-telemetry.js:33`
- `yousenwebview/packageDeeptutor/utils/surface-telemetry.js:33`
- `deeptutor/services/observability/surface_events.py:42`
- `deeptutor/services/bi_metrics.py:28`
- `web/lib/member-api.ts:268-292`
- `deeptutor/api/main.py:643`
- `web/app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx:436-437`

## 9. Follow-up Gates Before Release

- Implement catalog and store tests before production code.
- Add offline replay test using `occurred_at_ms=now-3d` and `now-10d`.
- Add member list batch summary test to prevent N+1.
- Add `/bi?tab=member-ops` screenshot evidence after UI implementation.
- Add `/wechat-harness` or WeChat DevTools smoke evidence before promoting section visibility above B.

## P0 Implementation Evidence

- `pytest tests/api/test_product_behavior_p0_flow.py -q`: PASS
- `pytest tests/services/observability/test_product_behavior_catalog.py tests/services/observability/test_product_behavior_store.py tests/api/test_observability_router.py tests/services/observability/test_surface_ack_smoke.py tests/services/test_bi_metrics.py tests/api/test_product_behavior_p0_flow.py tests/web/test_bi_v2_raw_fetch_guard.py -q`: PASS
- `pytest tests/api/test_bi_router.py::test_behavior_export_job_is_raw_mode_and_audited tests/api/test_bi_write_endpoints_registry.py -q`: PASS
- `cd web && node --test tests/product-behavior-surface-telemetry.test.ts tests/bi-v2-testids.test.ts`: PASS
- `cd web && npx eslint app/(workspace)/bi/_v2/member-ops/BiV2MemberOpsPanel.tsx app/(workspace)/bi/_v2/member-ops/Member360Drawer.tsx app/(workspace)/bi/_v2/member-ops/data.ts app/(workspace)/bi/_v2/feedback/BiV2FeedbackPanel.tsx lib/member-api.ts lib/bi-api.ts tests/bi-v2-testids.test.ts`: PASS
- `cd web && BI_BACKOFFICE_V2_SHELL_ENABLED=1 BI_CRM_V2_ENABLED=1 BI_OVERVIEW_V2_ENABLED=1 NEXT_PUBLIC_BI_BACKOFFICE_V2_SHELL_ENABLED=1 NEXT_PUBLIC_BI_CRM_V2_ENABLED=1 NEXT_PUBLIC_BI_OVERVIEW_V2_ENABLED=1 NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001 npm run build -- --webpack`: PASS; build retains existing `lib/wechat-harness-data.ts` webpack warning.

## Remaining Non-Automated Gates

- Production event volume observation before enabling broader cohort automation.
- Full WeChat DevTools simulator/real-device visual smoke is still recommended before raising `wechat_miniprogram` section visibility trust above B. P0 keeps trust B and has API-level smoke evidence for both WeChat surfaces.

## Manual Acceptance Evidence

| Gate | Result | Evidence |
| --- | --- | --- |
| `/bi?tab=member-ops` desktop | PASS | `artifacts/qa/product-behavior-bi-member-ops/desktop-member-ops.png`; real page loaded through Next production server with member APIs returning 200 |
| `/bi?tab=member-ops` mobile | PASS | `artifacts/qa/product-behavior-bi-member-ops/mobile-member-ops.png`; viewport `390x844`, no console/page errors |
| Member360 behavior drawer | PASS | `artifacts/qa/product-behavior-bi-member-ops/desktop-member-360-drawer.png`; `artifacts/qa/product-behavior-bi-member-ops/mobile-member-360-drawer.png`; behavior timeline and 学情模块分布 visible |
| `/wechat-harness` mobile page smoke | PASS | `artifacts/qa/product-behavior-bi-member-ops/wechat-harness-mobile.png`; dev server returned 200, non-404 body, no console/page errors |
| `wechat_miniprogram` surface behavior smoke | PASS | Direct authenticated `POST /api/v1/observability/surface-events` smoke: `module_viewed`, `section_viewed`, `learning_action_started` returned `202 accepted` and projected summary counts |
| `wechat_yousenwebview` surface behavior smoke | PASS | Direct authenticated `POST /api/v1/observability/surface-events` smoke: `module_viewed`, `section_viewed`, `learning_action_started` returned `202 accepted` and projected summary counts |

Notes:

- Local `web` source and lint checks passed.
- Browser plugin verification was attempted first per frontend-testing workflow. The in-app Browser target opened, but page evaluation for localStorage/location was unavailable in the plugin session, so validation fell back to regular Playwright with the reason recorded here.
- Playwright browser validation used `http://127.0.0.1:3000/bi?tab=member-ops` against local FastAPI on `127.0.0.1:8001`. It seeded `qa_behavior_member_1` with 3 学情 opens, 1 历史 open, and 2 学情 section views; `/api/v1/member/list` returned `learning_report_open_count_7d=3`, `history_open_count_7d=1`, `cohort=report_high_no_action`, `trust_level=B`.
- Member360 drawer validation confirmed `/api/v1/member/qa_behavior_member_1/360` returned behavior health and section breakdown, and the rendered drawer exposed both the behavior timeline and 学情模块分布.
- `/wechat-harness` production smoke first rendered the expected fail-closed 404 body because the harness is intentionally disabled in production unless flagged before prerender. Dev server smoke was then used for this fixture page and captured the passing screenshot.
- WeChat surface API smoke posted accepted product behavior events for `wechat_miniprogram` and `wechat_yousenwebview`; the backend projected summary for the smoke user as `learning_report_open_count_7d=2`, `history_open_count_7d=2`, `action_start_count_7d=2`, `trust_level=B`, section breakdown `evidence=1`, `next_action=1`.
- Known follow-up: local `/api/v1/member/{user_id}/360` validation took about 21.5s because learner state snapshot/heartbeat reads are slow in the current local stack. This is a performance optimization follow-up, not a P0 correctness blocker.
