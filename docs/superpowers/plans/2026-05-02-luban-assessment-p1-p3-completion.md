# Luban Assessment P1-P3 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Assessment Blueprint PRD Phase 1-3 by making the server assessment flow blueprint-owned, profile-aware, Teaching Policy-ready, and observable.

**Architecture:** Keep one canonical assessment path inside `MemberConsoleService`: `AssessmentBlueprintService` creates a versioned 20-unit session, submit scores only scored items, profile probes create non-clinical teaching seeds, and the same session/profile projection feeds report/chat/BI. Supabase `questions_bank` is the preferred scored item source; `_ASSESSMENT_BANK` is demoted to explicit non-production fallback.

**Tech Stack:** Python 3.11 dataclasses/stdlib urllib, existing JSON member store, existing LearnerStateService and BotLearnerOverlayService, existing mini-program assessment pages, pytest, Node tests for mini-program contracts.

---

## File Structure

- Create `deeptutor/services/assessment/profile_probes.py`
  - Owns four built-in versioned non-scored profile probe questions.
- Create `deeptutor/services/assessment/blueprint_service.py`
  - Builds blueprint sessions from Supabase rows or explicit dev fallback.
  - Normalizes question rendering payloads and stores session provenance.
- Create `deeptutor/services/assessment/teaching_policy.py`
  - Converts scored results + profile probe answers + confidence signals into low-risk `teaching_policy_seed`.
- Modify `deeptutor/services/member_console/service.py`
  - Replace direct `_ASSESSMENT_BANK` production authority with `AssessmentBlueprintService`.
  - Persist `blueprint_version`, `sections`, `provenance`, `profile_probe_count`, `measurement_confidence`, `teaching_policy_seed`, and `assessment_observability`.
  - Write Learner State memory event and bot overlay Teaching Policy seed after submit.
- Modify `tests/services/assessment/test_blueprint_coverage.py`
  - Add service-level tests for 20-unit create and profile probe shape.
- Modify `tests/services/member_console/test_service.py`
  - Add P1-P3 integration tests for create/submit/profile/observability/seed writeback.
- Modify `wx_miniprogram/pages/assessment/assessment.js` and `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
  - Display backend-delivered blueprint counts and section metadata.
  - Stop client fallback profile synthesis when backend seed/profile exists.
- Modify corresponding JS contract tests.
- Modify `docs/plan/2026-05-02-luban-assessment-blueprint-prd.md` and `docs/plan/INDEX.md`
  - Mark P1-P3 implementation evidence and remaining production rollout gates.

---

## Task 1: Blueprint Service And Profile Probes

**Files:**
- Create: `deeptutor/services/assessment/profile_probes.py`
- Create: `deeptutor/services/assessment/blueprint_service.py`
- Modify: `deeptutor/services/assessment/__init__.py`
- Test: `tests/services/assessment/test_blueprint_coverage.py`

- [ ] Add tests that `AssessmentBlueprintService.create_session(user_id, count=20)` returns 20 questions, 16 scored items, 4 profile probes, section metadata, and no shortfall.
- [ ] Add tests that a fake scored provider with fewer than 16 scored items raises `AssessmentBlueprintUnavailable` rather than silently returning fewer questions.
- [ ] Implement four built-in `profile_probe` questions with neutral wording:
  - learning habits / review rhythm
  - learning habits / planning style
  - pressure state / recovery support
  - teaching preference / explanation density
- [ ] Implement `AssessmentBlueprintService`:
  - Uses `diagnostic_v1` by default.
  - Builds one item per blueprint unit.
  - Uses provider rows for scored sections and built-in probes for non-scored sections.
  - Produces `client_questions` and `session_questions`.
  - Saves per-item `section_id`, `scored`, `provenance`, and `answer`.
  - Raises fail-closed error when scored items are short.
- [ ] Run `pytest tests/services/assessment/test_blueprint_coverage.py -q`.

## Task 2: MemberConsole Create/Submit Authority

**Files:**
- Modify: `deeptutor/services/member_console/service.py`
- Test: `tests/services/member_console/test_service.py`

- [ ] Add tests that `create_assessment("student_demo", 20)` stores `blueprint_version=diagnostic_v1`, `delivered_count=20`, `scored_count=16`, `profile_count=4`, `shortfall_count=0`, and per-question provenance.
- [ ] Add tests that submitting all scored answers plus profile probe choices scores only 16 scored items and returns `knowledge_score`, `profile_probe_count`, and `diagnostic_feedback.profile_projection`.
- [ ] Implement `MemberConsoleService._build_assessment_blueprint_service()` with explicit dev fallback enabled outside production.
- [ ] Replace direct `_ASSESSMENT_BANK` slicing in `create_assessment` with the blueprint service result.
- [ ] Update `submit_assessment` to:
  - score only `scored=True` questions,
  - keep unanswered profile probes out of score denominator,
  - persist `last_assessment.blueprint_version`,
  - persist `last_assessment.sections`,
  - persist `last_assessment.provenance_summary`,
  - return report-ready `diagnostic_feedback`.
- [ ] Run targeted member console tests.

## Task 3: Teaching Policy Seed And Learner State Writeback

**Files:**
- Create: `deeptutor/services/assessment/teaching_policy.py`
- Modify: `deeptutor/services/member_console/service.py`
- Test: `tests/services/member_console/test_service.py`

- [ ] Add tests with fake learner state and fake overlay services:
  - submit appends one Learner State memory event with `memory_kind=assessment`.
  - submit patches bot `construction-exam-coach` overlay `teaching_policy_override`.
  - low-confidence seconds-per-question marks seed as weak and does not promote profile labels.
- [ ] Implement `build_teaching_policy_seed(session, answers, score_report, time_spent_seconds)`.
- [ ] Seed must only use low-risk action fields:
  - `recommended_action`
  - `pace`
  - `scaffold_level`
  - `review_rhythm`
  - `priority_chapters`
  - `measurement_confidence`
  - `source_assessment`
- [ ] Write Learner State event via `append_memory_event` with `source_feature=assessment`, `memory_kind=assessment`.
- [ ] Patch overlay via `patch_overlay(... field=teaching_policy_override op=merge ...)`.
- [ ] Swallow writeback/overlay failures with warning logs; assessment submit must still return.

## Task 4: Observability, Report Projection, And BI Inputs

**Files:**
- Modify: `deeptutor/services/member_console/service.py`
- Test: `tests/services/member_console/test_service.py`

- [ ] Add tests that profile API exposes:
  - `assessment_observability`
  - `teaching_policy_seed`
  - `measurement_confidence`
  - `blueprint_version`
  - `completion_rate`
- [ ] Persist observability in `last_assessment`:
  - start/submit timestamps,
  - requested/delivered/scored/profile counts,
  - answered/scored/profile answered counts,
  - time spent,
  - low confidence reason,
  - section empty counts,
  - policy seed status.
- [ ] Ensure `get_assessment_profile` reads the stored projection, not recomputing profile labels independently.
- [ ] Keep existing radar/mastery fallback for users without assessment.
- [ ] Run targeted member console tests.

## Task 5: Mini-Program Truth And Client Contract

**Files:**
- Modify: `wx_miniprogram/pages/assessment/assessment.js`
- Modify: `yousenwebview/packageDeeptutor/pages/assessment/assessment.js`
- Modify: `wx_miniprogram/tests/test_assessment_contract.js`
- Modify: `yousenwebview/tests/test_package_assessment_contract.js`

- [ ] Add JS tests that client stores and displays `blueprint_version`, `scored_count`, and `profile_count` from backend payload.
- [ ] Add JS tests that delivered 20 questions produce no shortfall notice and submit checks only delivered questions.
- [ ] Remove client-generated archetype fallback when backend returns `diagnostic_feedback.learner_profile`.
- [ ] Run both Node contract tests.

## Task 6: PRD Evidence, Verification, And Merge

**Files:**
- Modify: `docs/plan/2026-05-02-luban-assessment-blueprint-prd.md`
- Modify: `docs/plan/INDEX.md`

- [ ] Add P1-P3 implementation evidence with exact code/test entry points.
- [ ] Update status to `Implemented locally` if all tests pass.
- [ ] Run:
  - `pytest tests/services/assessment/test_blueprint_coverage.py tests/services/member_console/test_service.py -k "assessment or teaching_policy" -q`
  - `node wx_miniprogram/tests/test_assessment_contract.js`
  - `node yousenwebview/tests/test_package_assessment_contract.js`
  - `python scripts/audit_assessment_blueprint_coverage.py --env-file /Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.env --output tmp/assessment_blueprint_coverage_diagnostic_v1.json`
- [ ] Merge back to local `main` only after all targeted checks pass.

