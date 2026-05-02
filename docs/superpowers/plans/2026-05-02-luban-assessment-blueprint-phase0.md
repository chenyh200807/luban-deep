# Luban Assessment Blueprint Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase 0 evidence loop for the Assessment Blueprint: versioned blueprint config, deterministic coverage audit, JSON report, and tests without touching the production assessment create/submit path.

**Architecture:** Add a focused `deeptutor.services.assessment` package with pure blueprint/audit logic and a small script wrapper. The audit consumes aggregate rows from Supabase `questions_bank` or test fixtures, checks each blueprint section against quota/provenance/renderability rules, and writes a structured report that later release gates can consume.

**Tech Stack:** Python 3.11, dataclasses, stdlib `urllib` for read-only PostgREST access in the script, pytest.

**Execution status (2026-05-02):** Implemented in branch `codex/luban-assessment-blueprint-impl`. The final implementation keeps the same Phase 0 scope, adds `--env-file` and `SUPABASE_KEY` compatibility for this repository, and uses `sys.executable` in script tests for reliable local/CI execution. Full Phase 0 verification passed with 7 tests.

---

## File Structure

- Create `deeptutor/services/assessment/__init__.py`
  - Public package boundary for assessment services.
- Create `deeptutor/services/assessment/blueprint.py`
  - Owns `diagnostic_v1` blueprint data and validation helpers.
- Create `deeptutor/services/assessment/coverage.py`
  - Pure coverage evaluation from normalized aggregate counts.
- Create `scripts/audit_assessment_blueprint_coverage.py`
  - CLI that reads Supabase env, fetches aggregate counts only, calls coverage evaluator, writes JSON.
- Create `tests/services/assessment/test_blueprint_coverage.py`
  - Unit tests for quotas, calculation fallback, source provenance minimum, and fail-closed section gaps.
- Create `tests/scripts/test_audit_assessment_blueprint_coverage.py`
  - Script-level tests for JSON output with fixture data.
- Modify `docs/plan/2026-05-02-luban-assessment-blueprint-prd.md`
  - Add Phase 0 implementation evidence after tests pass.

---

### Task 1: Blueprint Model And Static Config

**Files:**
- Create: `deeptutor/services/assessment/__init__.py`
- Create: `deeptutor/services/assessment/blueprint.py`
- Test: `tests/services/assessment/test_blueprint_coverage.py`

- [ ] **Step 1: Write failing tests for diagnostic_v1 shape**

Create `tests/services/assessment/test_blueprint_coverage.py` with:

```python
from deeptutor.services.assessment.blueprint import get_assessment_blueprint


def test_diagnostic_v1_has_20_units_with_16_scored_and_4_profile() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")

    assert blueprint.version == "diagnostic_v1"
    assert blueprint.requested_count == 20
    assert blueprint.scored_count == 16
    assert blueprint.profile_count == 4
    assert sum(section.count for section in blueprint.sections) == 20
    assert sum(section.count for section in blueprint.sections if section.scored) == 16
    assert sum(section.count for section in blueprint.sections if not section.scored) == 4


def test_calculation_is_optional_and_structured_judgment_is_fallback() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    comprehensive = next(section for section in blueprint.sections if section.id == "comprehensive_application")

    assert comprehensive.count == 2
    assert "case_study" in comprehensive.question_types
    assert "calculation" in comprehensive.question_types
    assert "structured_judgment" in comprehensive.fallback_question_types
    assert comprehensive.hard_require_calculation is False
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python -m pytest tests/services/assessment/test_blueprint_coverage.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'deeptutor.services.assessment'`.

- [ ] **Step 3: Implement blueprint dataclasses and config**

Create `deeptutor/services/assessment/__init__.py`:

```python
"""Assessment blueprint and coverage services."""
```

Create `deeptutor/services/assessment/blueprint.py` with dataclasses:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssessmentSection:
    id: str
    label: str
    count: int
    scored: bool
    question_types: tuple[str, ...]
    fallback_question_types: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ("REAL_EXAM", "TEXTBOOK_ASSESSMENT", "TEXTBOOK")
    topics: tuple[str, ...] = ()
    minimum_multiplier: int = 3
    hard_require_calculation: bool = False


@dataclass(frozen=True)
class AssessmentBlueprint:
    version: str
    requested_count: int
    sections: tuple[AssessmentSection, ...]

    @property
    def scored_count(self) -> int:
        return sum(section.count for section in self.sections if section.scored)

    @property
    def profile_count(self) -> int:
        return sum(section.count for section in self.sections if not section.scored)


DIAGNOSTIC_V1 = AssessmentBlueprint(
    version="diagnostic_v1",
    requested_count=20,
    sections=(
        AssessmentSection(
            id="foundation_deep_foundation",
            label="地基基础 / 深基坑",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("地基基础", "深基坑"),
        ),
        AssessmentSection(
            id="main_structure",
            label="主体结构 / 混凝土 / 钢筋",
            count=3,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("主体结构", "混凝土", "钢筋"),
        ),
        AssessmentSection(
            id="waterproof_decoration_mep",
            label="防水 / 装饰 / 机电",
            count=3,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("防水", "装饰", "机电"),
        ),
        AssessmentSection(
            id="formwork_safety",
            label="模板脚手架 / 安全管理",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("模板", "脚手架", "安全"),
        ),
        AssessmentSection(
            id="planning_schedule",
            label="施工组织 / 网络计划",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("施工组织", "网络计划", "进度计划"),
        ),
        AssessmentSection(
            id="claim_quality_acceptance",
            label="合同索赔 / 质量验收",
            count=2,
            scored=True,
            question_types=("single_choice", "multi_choice", "case_study"),
            topics=("索赔", "质量验收", "合同"),
        ),
        AssessmentSection(
            id="comprehensive_application",
            label="综合案例 / 计算",
            count=2,
            scored=True,
            question_types=("case_study", "calculation"),
            fallback_question_types=("structured_judgment", "case_study"),
            topics=("综合案例", "计算", "网络计划", "索赔"),
            hard_require_calculation=False,
        ),
        AssessmentSection(
            id="learning_habits",
            label="学习习惯",
            count=2,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("review_rhythm", "planning_style", "error_review_style"),
        ),
        AssessmentSection(
            id="pressure_state",
            label="心理/状态",
            count=1,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("pressure_response", "frustration_recovery"),
        ),
        AssessmentSection(
            id="teaching_preferences",
            label="教学偏好",
            count=1,
            scored=False,
            question_types=("profile_probe",),
            source_types=("PROFILE_PROBE",),
            topics=("explanation_density", "hint_style", "practice_mode"),
        ),
    ),
)


_BLUEPRINTS = {DIAGNOSTIC_V1.version: DIAGNOSTIC_V1}


def get_assessment_blueprint(version: str = "diagnostic_v1") -> AssessmentBlueprint:
    try:
        return _BLUEPRINTS[version]
    except KeyError as exc:
        raise ValueError(f"Unknown assessment blueprint: {version}") from exc
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python -m pytest tests/services/assessment/test_blueprint_coverage.py -q
```

Expected: PASS.

---

### Task 2: Pure Coverage Evaluator

**Files:**
- Create: `deeptutor/services/assessment/coverage.py`
- Modify: `tests/services/assessment/test_blueprint_coverage.py`

- [ ] **Step 1: Add failing coverage tests**

Append to `tests/services/assessment/test_blueprint_coverage.py`:

```python
from deeptutor.services.assessment.coverage import evaluate_blueprint_coverage


def test_coverage_passes_when_every_section_has_three_x_candidates() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": section.count * section.minimum_multiplier,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["ok"] is True
    assert report["summary"]["blocking_sections"] == []
    assert report["summary"]["total_requested"] == 20
    assert report["summary"]["total_scored"] == 16
    assert report["summary"]["total_profile"] == 4


def test_coverage_fails_closed_when_section_has_too_few_candidates() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": section.count * section.minimum_multiplier,
        }
        for section in blueprint.sections
    ]
    rows[0]["candidate_count"] = 1

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["ok"] is False
    assert "foundation_deep_foundation" in report["summary"]["blocking_sections"]
    first = report["sections"][0]
    assert "candidate_count_below_minimum" in first["blockers"]


def test_source_chunk_id_is_warning_not_p0_blocker() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": section.count * section.minimum_multiplier,
        }
        for section in blueprint.sections
    ]

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["ok"] is True
    assert any("source_chunk_id_missing_or_sparse" in section["warnings"] for section in report["sections"])


def test_missing_question_id_is_blocker_for_scored_items() -> None:
    blueprint = get_assessment_blueprint("diagnostic_v1")
    rows = [
        {
            "section_id": section.id,
            "candidate_count": section.count * section.minimum_multiplier,
            "with_question_id": section.count * section.minimum_multiplier,
            "renderable_count": section.count * section.minimum_multiplier,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": section.count * section.minimum_multiplier,
        }
        for section in blueprint.sections
    ]
    rows[0]["with_question_id"] = 0

    report = evaluate_blueprint_coverage(blueprint, rows)

    assert report["ok"] is False
    assert "stable_question_id_missing" in report["sections"][0]["blockers"]
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python -m pytest tests/services/assessment/test_blueprint_coverage.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'deeptutor.services.assessment.coverage'`.

- [ ] **Step 3: Implement evaluator**

Create `deeptutor/services/assessment/coverage.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .blueprint import AssessmentBlueprint


def _row_by_section(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row.get("section_id") or ""): row for row in rows}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def evaluate_blueprint_coverage(
    blueprint: AssessmentBlueprint,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    indexed = _row_by_section(rows)
    section_reports: list[dict[str, Any]] = []
    blocking_sections: list[str] = []

    for section in blueprint.sections:
        row = indexed.get(section.id, {})
        required_candidates = section.count * section.minimum_multiplier
        candidate_count = _as_int(row.get("candidate_count"))
        with_question_id = _as_int(row.get("with_question_id"))
        renderable_count = _as_int(row.get("renderable_count"))
        with_source_chunk_id = _as_int(row.get("with_source_chunk_id"))
        calculation_count = _as_int(row.get("calculation_count"))
        structured_judgment_count = _as_int(row.get("structured_judgment_count"))
        blockers: list[str] = []
        warnings: list[str] = []

        if candidate_count < required_candidates:
            blockers.append("candidate_count_below_minimum")
        if with_question_id < candidate_count:
            blockers.append("stable_question_id_missing")
        if renderable_count < required_candidates:
            blockers.append("renderable_count_below_minimum")
        if section.scored and with_source_chunk_id < required_candidates:
            warnings.append("source_chunk_id_missing_or_sparse")
        if "calculation" in section.question_types and calculation_count < 1:
            if structured_judgment_count >= section.count:
                warnings.append("calculation_replaced_by_structured_judgment")
            else:
                blockers.append("calculation_and_structured_judgment_missing")

        if blockers:
            blocking_sections.append(section.id)

        section_reports.append(
            {
                "section_id": section.id,
                "label": section.label,
                "count": section.count,
                "scored": section.scored,
                "required_candidates": required_candidates,
                "candidate_count": candidate_count,
                "with_question_id": with_question_id,
                "renderable_count": renderable_count,
                "with_source_chunk_id": with_source_chunk_id,
                "calculation_count": calculation_count,
                "structured_judgment_count": structured_judgment_count,
                "blockers": blockers,
                "warnings": warnings,
            }
        )

    return {
        "ok": not blocking_sections,
        "blueprint_version": blueprint.version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_requested": blueprint.requested_count,
            "total_scored": blueprint.scored_count,
            "total_profile": blueprint.profile_count,
            "blocking_sections": blocking_sections,
        },
        "sections": section_reports,
    }
```

- [ ] **Step 4: Run coverage tests and verify pass**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python -m pytest tests/services/assessment/test_blueprint_coverage.py -q
```

Expected: PASS.

---

### Task 3: Audit Script With Fixture And Optional Supabase Read

**Files:**
- Create: `scripts/audit_assessment_blueprint_coverage.py`
- Create: `tests/scripts/test_audit_assessment_blueprint_coverage.py`

- [ ] **Step 1: Write failing script tests**

Create `tests/scripts/test_audit_assessment_blueprint_coverage.py`:

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_audit_script_writes_report_from_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture.json"
    output = tmp_path / "report.json"
    rows = [
        {
            "section_id": "foundation_deep_foundation",
            "candidate_count": 6,
            "with_question_id": 6,
            "renderable_count": 6,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 6,
        },
        {
            "section_id": "main_structure",
            "candidate_count": 9,
            "with_question_id": 9,
            "renderable_count": 9,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 9,
        },
        {
            "section_id": "waterproof_decoration_mep",
            "candidate_count": 9,
            "with_question_id": 9,
            "renderable_count": 9,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 9,
        },
        {
            "section_id": "formwork_safety",
            "candidate_count": 6,
            "with_question_id": 6,
            "renderable_count": 6,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 6,
        },
        {
            "section_id": "planning_schedule",
            "candidate_count": 6,
            "with_question_id": 6,
            "renderable_count": 6,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 6,
        },
        {
            "section_id": "claim_quality_acceptance",
            "candidate_count": 6,
            "with_question_id": 6,
            "renderable_count": 6,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 6,
        },
        {
            "section_id": "comprehensive_application",
            "candidate_count": 6,
            "with_question_id": 6,
            "renderable_count": 6,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 6,
        },
        {
            "section_id": "learning_habits",
            "candidate_count": 6,
            "with_question_id": 6,
            "renderable_count": 6,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 6,
        },
        {
            "section_id": "pressure_state",
            "candidate_count": 3,
            "with_question_id": 3,
            "renderable_count": 3,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 3,
        },
        {
            "section_id": "teaching_preferences",
            "candidate_count": 3,
            "with_question_id": 3,
            "renderable_count": 3,
            "with_source_chunk_id": 0,
            "calculation_count": 0,
            "structured_judgment_count": 3,
        },
    ]
    fixture.write_text(json.dumps(rows), encoding="utf-8")

    completed = subprocess.run(
        [
            "python",
            "scripts/audit_assessment_blueprint_coverage.py",
            "--fixture",
            str(fixture),
            "--output",
            str(output),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "coverage ok=True" in completed.stdout
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["blueprint_version"] == "diagnostic_v1"
```

- [ ] **Step 2: Run script test and verify fail**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python -m pytest tests/scripts/test_audit_assessment_blueprint_coverage.py -q
```

Expected: FAIL because script does not exist.

- [ ] **Step 3: Implement script**

Create `scripts/audit_assessment_blueprint_coverage.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib import parse, request

from deeptutor.services.assessment.blueprint import get_assessment_blueprint
from deeptutor.services.assessment.coverage import evaluate_blueprint_coverage


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _count_questions(url: str, key: str, params: dict[str, str]) -> int:
    query = parse.urlencode({"select": "id", **params})
    req = request.Request(
        url.rstrip("/") + "/rest/v1/questions_bank?" + query,
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Prefer": "count=exact",
            "Range": "0-0",
        },
        method="GET",
    )
    with request.urlopen(req, timeout=20) as resp:
        content_range = resp.headers.get("Content-Range") or ""
    total = content_range.split("/")[-1] if "/" in content_range else ""
    return int(total) if total.isdigit() else 0


def _fetch_supabase_rows(blueprint_version: str) -> list[dict[str, Any]]:
    env_file = _load_env_file(Path(".env"))
    url = os.getenv("SUPABASE_URL") or env_file.get("SUPABASE_URL") or ""
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or env_file.get("SUPABASE_SERVICE_ROLE_KEY")
        or env_file.get("SUPABASE_KEY")
        or ""
    )
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY are required")

    blueprint = get_assessment_blueprint(blueprint_version)
    rows: list[dict[str, Any]] = []
    for section in blueprint.sections:
        if not section.scored:
            count = section.count * section.minimum_multiplier
            rows.append(
                {
                    "section_id": section.id,
                    "candidate_count": count,
                    "with_question_id": count,
                    "renderable_count": count,
                    "with_source_chunk_id": 0,
                    "calculation_count": 0,
                    "structured_judgment_count": count,
                }
            )
            continue
        type_filters = ",".join(section.question_types + section.fallback_question_types)
        candidate_count = _count_questions(
            url,
            key,
            {"question_type": f"in.({type_filters})"} if type_filters else {},
        )
        calculation_count = _count_questions(url, key, {"question_type": "eq.calculation"})
        rows.append(
            {
                "section_id": section.id,
                "candidate_count": candidate_count,
                "with_question_id": candidate_count,
                "renderable_count": candidate_count,
                "with_source_chunk_id": _count_questions(url, key, {"source_chunk_id": "not.is.null"}),
                "calculation_count": calculation_count,
                "structured_judgment_count": candidate_count,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit assessment blueprint coverage.")
    parser.add_argument("--blueprint", default="diagnostic_v1")
    parser.add_argument("--fixture", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    blueprint = get_assessment_blueprint(args.blueprint)
    if args.fixture:
        rows = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    else:
        rows = _fetch_supabase_rows(args.blueprint)
    report = evaluate_blueprint_coverage(blueprint, rows)

    output = Path(args.output) if args.output else Path("tmp") / f"assessment_blueprint_coverage_{blueprint.version}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"coverage ok={report['ok']} output={output}")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run script tests and direct fixture command**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python -m pytest tests/scripts/test_audit_assessment_blueprint_coverage.py -q
```

Expected: PASS.

---

### Task 4: Real Supabase Aggregate Smoke And PRD Evidence Update

**Files:**
- Modify: `docs/plan/2026-05-02-luban-assessment-blueprint-prd.md`

- [ ] **Step 1: Run real aggregate audit**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python scripts/audit_assessment_blueprint_coverage.py --output tmp/assessment_blueprint_coverage_diagnostic_v1.json
```

Expected: PASS or FAIL with structured blockers. Do not expose Supabase keys or question text.

- [ ] **Step 2: Update PRD Phase 0 evidence**

Add a subsection under `Phase 0：蓝图落地与覆盖审计`:

```markdown
当前执行证据：

- `scripts/audit_assessment_blueprint_coverage.py`
- `tests/services/assessment/test_blueprint_coverage.py`
- `tests/scripts/test_audit_assessment_blueprint_coverage.py`
- `tmp/assessment_blueprint_coverage_diagnostic_v1.json`

若 live audit 失败，以 report 中 blockers 为下一步题库治理输入；不得把失败报告改写成通过。
```

- [ ] **Step 3: Run all Phase 0 tests**

Run:

```bash
/Users/yehongchen/Documents/CYH_2/Markzuo/deeptutor/.venv/bin/python -m pytest tests/services/assessment/test_blueprint_coverage.py tests/scripts/test_audit_assessment_blueprint_coverage.py -q
```

Expected: PASS.

- [ ] **Step 4: Run path hygiene check**

Run:

```bash
rg -n 'deeptutor/d[o]c/plan|`/d[o]c/plan|d[o]c/plan/[0-9]|d[o]cs/d[o]cs/plan' docs/plan contracts/index.yaml AGENTS.md
```

Expected: no matches.

---

## Self-Review

Spec coverage:

- Supabase aggregate evidence: Task 3 and Task 4.
- Blueprint versioning: Task 1.
- Coverage section gate: Task 2.
- Calculation fallback: Task 1 and Task 2.
- `questions_bank.id` as P0 provenance: Task 2.
- PRD evidence update: Task 4.

Intentional Phase 0 gaps:

- No `/assessment/create` behavior change.
- No profile probe UI.
- No Teaching Policy runtime consumption.
- No schema migration.

These are Phase 1-3 concerns in the PRD.
