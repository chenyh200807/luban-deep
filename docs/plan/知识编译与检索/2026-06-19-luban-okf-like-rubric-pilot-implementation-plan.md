# Luban OKF-like Rubric Pilot Implementation Plan

> **For agentic workers:** this plan is intentionally a small pilot. Do not turn it into a generic knowledge platform, graph system, runtime default, or production scoring authority.

**Goal:** Build a reproducible OKF-like generated review projection for one canonical rubric slice, then compile it into small JSON inspection artifacts without touching runtime scoring.

**Architecture:** `docs/原始数据/数据盘点/extractions/case_rubric_canonical.json` remains the scoring-context authority. A thin deterministic compiler emits human-reviewable Markdown projections plus compiled JSON inspection artifacts. Runtime grading, official score decisions, learner truth, and citation policy remain owned by existing fat skills/kernels.

**Tech Stack:** Python 3 standard library, Markdown + YAML-compatible frontmatter, JSON artifacts, pytest for script validation.

## Global Constraints

- Thin wrappers and fat skills: the pilot writer/parser only formats, validates, and exports; it must not judge student answers.
- First principles: the one business fact is traceable scoring context, not the existence of an OKF directory.
- Less is more: one 2021 case slice only; no graph viewer, no GradeQL, no runtime integration, no bulk conversion.
- Authority boundary: `training_org_analysis_yousen` and `engine_rule_derived` are not official scoring authority; every generated artifact must preserve `not_official: true` and `official_score_allowed: false`.
- Runtime boundary: no loader, environment flag, `/api/v1/ws`, `CaseGradingSkillKernel`, LearnerState, or production `runtime_supply` write is in scope.
- Dirty workspace boundary: stage/commit is out of scope unless explicitly requested; do not sweep unrelated diagram/Web/WeChat files.
- Projection boundary: Markdown files under `okf_pilot/rubric_v0/` are generated review projections, not canonical source truth; review corrections must flow back to canonical extraction or a separate review patch, then be regenerated.

---

## File Structure

- Create `docs/原始数据/数据盘点/scripts/build_okf_rubric_pilot.py`
  - Reads the canonical rubric extraction.
  - Selects a single year/case.
  - Writes OKF-like Markdown review projections and compiled JSON inspection artifacts.
  - Runs fail-closed validation on required authority fields.
- Create `docs/原始数据/数据盘点/okf_pilot/rubric_v0/`
  - Generated Markdown review projections. These are human-reviewable views, not canonical source truth or runtime truth.
- Create `docs/原始数据/数据盘点/extractions/okf_rubric_pilot_v0/`
  - Generated compiled JSON artifacts for inspection.
- Create `tests/scripts/test_okf_rubric_pilot.py`
  - Verifies deterministic output, path safety, authority preservation, non-runtime guardrails, context provenance, and required files.
- Modify `docs/原始数据/数据盘点/INDEX.md`
  - Register the pilot and explain it is candidate/source-layer only.
- Modify `docs/plan/INDEX.md`
  - Add this plan under knowledge compilation and fix the data inventory link to the current `docs/原始数据/数据盘点/` path.

## Task 1: Pilot Generator

**Files:**
- Create: `docs/原始数据/数据盘点/scripts/build_okf_rubric_pilot.py`

**Interfaces:**
- Consumes: `case_rubric_canonical.json` with `_meta` and `rubric[year][case][sub_question]`.
- Produces:
  - `build_pilot(source_path: Path, source_root: Path, compiled_root: Path, year: str, case_no: str) -> dict`
  - Markdown docs under `source_root`.
  - JSON artifacts under `compiled_root`.

**Steps:**

- [x] Read canonical extraction and fail if `_meta.NOT_official` is not true.
- [x] Build deterministic ids: `case_2021_1`, `rubric_2021_1_q01`, `sp_2021_1_q01_01`.
- [x] Generate one `CaseQuestion`, five `Rubric`, and fifteen `ScoringPoint` docs for 2021 case 1.
- [x] Generate `manifest.json`, `question_context_pack.json`, and `scoring_point_index.json`.
- [x] Validate every case/rubric/scoring point has `authority`, `not_official`, `source_ref`, and `official_score_allowed=false`.
- [x] Reject dangerous output roots, source paths inside generated output, and overlapping output roots before any directory reset.
- [x] Preserve question context provenance separately from rubric provenance: page 16 question chunk plus page 17 rubric JSONL/canonical source.
- [x] Add machine-readable runtime guard fields: `runtime_consumable=false`, `installed_runtime_supply=false`, `canonical_write_allowed=false`, `learner_truth_write_allowed=false`, `gbrain_write_allowed=false`, `production_registry_write_allowed=false`.

## Task 2: Generated Pilot Artifacts

**Files:**
- Create: `docs/原始数据/数据盘点/okf_pilot/rubric_v0/**`
- Create: `docs/原始数据/数据盘点/extractions/okf_rubric_pilot_v0/**`

**Interfaces:**
- Consumes: Task 1 script.
- Produces: generated review projections and compiled inspection JSON.

**Steps:**

- [x] Run:

```bash
python3 docs/原始数据/数据盘点/scripts/build_okf_rubric_pilot.py --generated-at 2026-06-19T00:00:00+08:00
```

- [x] Confirm output counts:
  - `cases=1`
  - `rubrics=5`
  - `scoring_points=15`
  - `official_score_allowed=false`
  - `runtime_consumable=false`

## Task 3: Script Tests

**Files:**
- Create: `tests/scripts/test_okf_rubric_pilot.py`

**Interfaces:**
- Consumes: `build_okf_rubric_pilot.py`.
- Produces: pytest coverage for generation and authority guardrails.

**Steps:**

- [x] Use `tmp_path` to generate into temporary `okf_pilot/rubric_v0` and `extractions/okf_rubric_pilot_v0` directories.
- [x] Assert manifest counts and selected ids.
- [x] Assert compiled artifacts preserve `authority=training_org_analysis_yousen`.
- [x] Assert every generated record has `official_score_allowed is False`.
- [x] Assert Markdown concept docs include `type`, `canonical_id`, `authority`, `not_official`, and `source_ref`.
- [x] Assert dangerous path, source-in-output, and overlapping output-root cases fail before reset.
- [x] Assert compiled cross references resolve and compound list points expose `acceptable_items`, `partial_credit_rule=unknown_from_source`, and `max_per_group`.

## Task 4: Index Updates

**Files:**
- Modify: `docs/原始数据/数据盘点/INDEX.md`
- Modify: `docs/plan/INDEX.md`

**Interfaces:**
- Consumes: generated pilot paths.
- Produces: discoverable plan and data inventory routing.

**Steps:**

- [x] Add a row to the data inventory index.
- [x] Add this plan to the knowledge compilation section.
- [x] Keep the current dirty worktree changes intact; do not stage or commit.

## Verification

Run:

```bash
python3 docs/原始数据/数据盘点/scripts/build_okf_rubric_pilot.py --generated-at 2026-06-19T00:00:00+08:00
python3 -m pytest tests/scripts/test_okf_rubric_pilot.py -q
git diff --check -- docs/plan/知识编译与检索/2026-06-19-luban-okf-like-rubric-pilot-implementation-plan.md docs/原始数据/数据盘点 tests/scripts/test_okf_rubric_pilot.py docs/plan/INDEX.md
```

Expected:

- Script prints the generated counts and output directories.
- Pytest passes.
- `git diff --check` reports no whitespace errors.

## Explicit Non-goals

- No official score claim.
- No runtime default or production published registry.
- No `CaseGradingSkillKernel` behavior change.
- No LearnerState or GBrain write.
- No graph viewer.
- No full conversion of `docs/原始数据/数据盘点`.
