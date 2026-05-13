# Luban Case Grading Error Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first shippable loop for 建筑实务案例题 AI 阅卷 + 错因图谱 + 个性化下一题推荐, while reusing Supabase `questions_bank`, `deep_question`, `LearnerStateService`, and assessment policy foundations.

**Architecture:** Add a narrow `case_grading` internal service that owns subjective case grading only. It reads case assets from `questions_bank`, builds runtime Rubric projections, matches learner answer spans to rubric items, aggregates score deterministically, emits error events, and hands next-task signals back to existing learner state and assessment teaching policy. It does not create a second question bank, a second learner state system, or a new chat WebSocket.

**Tech Stack:** Python dataclasses, existing DeepTutor service layout, Supabase PostgREST read-only access, existing LLM `complete` seam, existing `deep_question` capability, existing `LearnerStateService`, pytest, Node tests for mini-program smoke when UI work begins.

---

## 0. Scope And Stop Rules

This implementation plan covers P0 and the minimum P1 bridge:

1. Case rubric readiness audit.
2. 20-question L2 rubric golden set support.
3. `CaseGradingService` internal kernel.
4. Error event writeback through existing learner state.
5. Next-task recommendation that prefers existing `questions_bank`.
6. `deep_question` grading route integration for written/case submissions.

This plan does not implement:

1. Teacher workspace.
2. OCR / photo upload.
3. Full generated variant publishing.
4. New Supabase schema migrations.
5. New `/api/v1/ws` route or any case-specific chat WebSocket.
6. Full B2B SaaS classroom backend.

Stop rules:

1. If the readiness audit cannot find 20 viable L2 case candidates, stop product integration and curate 5 concepts x 3-4 questions first.
2. If AI-human score agreement misses the PRD target, expose "AI 初评区间 + 漏点诊断" and do not present a hard final score.
3. If generated variants fail validator quality, keep next-task recommendation retrieval-only.

## 1. Current Authority Map

| Business fact | Existing authority to reuse | New code must not replace |
| --- | --- | --- |
| Question asset | Supabase `questions_bank` | No new rubric question bank |
| Chat entry | Unified `/api/v1/ws` through existing capability routing | No dedicated case grading WebSocket |
| Practice continuity | `deep_question` + `question_followup` + active object | No parallel practice transaction |
| Learner long-term state | `LearnerStateService` | No separate error-map database |
| Teaching action | `assessment.teaching_policy` plus Teaching Methods Matrix | No second teaching policy engine |
| Knowledge grounding | Existing RAG / `questions_bank` provenance | No new grounded mode |

Contract-sensitive files in later tasks:

- `deeptutor/capabilities/deep_question.py`
- `deeptutor/services/learner_state/service.py` only if a small wrapper method is added
- `contracts/index.yaml` only if stable external contract surface changes

The preferred P0 path avoids changing contract files by keeping new structures internal and reusing existing result metadata.

## 2. File Structure

Create:

- `deeptutor/services/case_grading/__init__.py`
- `deeptutor/services/case_grading/schema.py`
- `deeptutor/services/case_grading/assets.py`
- `deeptutor/services/case_grading/readiness.py`
- `deeptutor/services/case_grading/rubric_normalizer.py`
- `deeptutor/services/case_grading/error_taxonomy.py`
- `deeptutor/services/case_grading/matcher.py`
- `deeptutor/services/case_grading/score_aggregator.py`
- `deeptutor/services/case_grading/feedback.py`
- `deeptutor/services/case_grading/service.py`
- `deeptutor/services/case_grading/learner_writeback.py`
- `deeptutor/services/case_grading/recommendation.py`
- `scripts/audit_case_rubric_readiness.py`
- `tests/fixtures/case_grading/sample_questions_bank_rows.json`
- `tests/fixtures/case_grading/sample_submissions.json`
- `tests/services/case_grading/test_schema.py`
- `tests/services/case_grading/test_assets.py`
- `tests/services/case_grading/test_readiness.py`
- `tests/services/case_grading/test_rubric_normalizer.py`
- `tests/services/case_grading/test_error_taxonomy.py`
- `tests/services/case_grading/test_matcher.py`
- `tests/services/case_grading/test_score_aggregator.py`
- `tests/services/case_grading/test_service.py`
- `tests/services/case_grading/test_learner_writeback.py`
- `tests/services/case_grading/test_recommendation.py`

Modify:

- `deeptutor/capabilities/deep_question.py`
- `tests/core/test_deep_question_submission_grading.py`
- `docs/plan/INDEX.md`
- `docs/plan/2026-05-13-luban-case-grading-error-map-prd.md` only if implementation evidence is appended after completion

Do not touch unrelated dirty files, especially current observability edits:

- `deeptutor/services/observability/aae_composite.py`
- `tests/services/observability/test_aae_composite.py`

## 3. Task Sequence

### Task 1: Create Case Grading Schemas

**Files:**

- Create: `deeptutor/services/case_grading/__init__.py`
- Create: `deeptutor/services/case_grading/schema.py`
- Test: `tests/services/case_grading/test_schema.py`

- [ ] **Step 1: Write the failing schema tests**

```python
# tests/services/case_grading/test_schema.py
from deeptutor.services.case_grading.schema import (
    CaseQuestionAsset,
    CaseRubricItem,
    CaseRubricProjection,
    RubricMatchResult,
    CaseGradingResult,
)


def test_case_rubric_projection_keeps_questions_bank_authority() -> None:
    asset = CaseQuestionAsset(
        question_id="123",
        question_type="case_study",
        stem="背景资料",
        question_text="指出不妥之处。",
        correct_answer="应编制专项施工方案并组织专家论证。",
        analysis="危大工程专项方案流程。",
        total_score=6.0,
        source_type="REAL_EXAM",
        exam_year=2024,
        node_code="1A424000",
        source_meta={"paper": "2024"},
    )
    projection = CaseRubricProjection(
        question_id=asset.question_id,
        source_question_id=asset.question_id,
        rubric_version="projection_v1",
        rubric_level="L2",
        total_score=6.0,
        items=[
            CaseRubricItem(
                item_id="r1",
                criterion="应组织专家论证",
                required_meaning="表达超过一定规模危大工程专项方案需专家论证",
                score=1.0,
                keywords=("专家论证",),
                acceptable_expressions=("组织专家论证",),
                non_credit_expressions=("加强管理",),
                concept_tags=("危大工程",),
                error_tags=("E02", "E03"),
                source_ref={"question_id": "123"},
            )
        ],
    )

    assert projection.source_question_id == "123"
    assert projection.items[0].score == 1.0
    assert projection.items[0].source_ref["question_id"] == "123"


def test_case_grading_result_total_score_is_data_not_markdown() -> None:
    result = CaseGradingResult(
        grading_run_id="run_1",
        question_id="123",
        submission_text="施工单位未编制专项方案。",
        total_score=0.5,
        max_score=1.0,
        confidence=0.8,
        status="ai_final",
        rubric_results=[
            RubricMatchResult(
                rubric_item_id="r1",
                criterion="应组织专家论证",
                max_score=1.0,
                awarded_score=0.5,
                status="partial",
                evidence_text="施工单位未编制专项方案",
                missing_meaning="未写出专家论证",
                reason="识别到专项方案问题，但漏专家论证",
                error_tags=("E02", "E03"),
                confidence=0.8,
            )
        ],
        major_problems=("漏程序性采分点",),
        rewrite_answer="应编制专项施工方案并组织专家论证。",
        next_training_suggestion={"focus_concepts": ["危大工程"]},
    )

    assert result.total_score == 0.5
    assert result.rubric_results[0].evidence_text
    assert result.status == "ai_final"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
pytest tests/services/case_grading/test_schema.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.case_grading'
```

- [ ] **Step 3: Add the schema implementation**

```python
# deeptutor/services/case_grading/schema.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RubricLevel = Literal["L0", "L1", "L2", "L3"]
RubricMatchStatus = Literal["full", "partial", "miss", "wrong", "irrelevant"]
GradingStatus = Literal["ai_draft", "ai_final", "needs_review", "teacher_corrected", "discarded"]


@dataclass(frozen=True)
class CaseQuestionAsset:
    question_id: str
    question_type: str
    stem: str
    question_text: str
    correct_answer: str
    analysis: str = ""
    total_score: float = 0.0
    source_type: str = ""
    exam_year: int | None = None
    node_code: str = ""
    grading_keywords: tuple[str, ...] = ()
    grading_rubric: Any = None
    tags: tuple[str, ...] = ()
    source_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseRubricItem:
    item_id: str
    criterion: str
    required_meaning: str
    score: float
    keywords: tuple[str, ...] = ()
    acceptable_expressions: tuple[str, ...] = ()
    non_credit_expressions: tuple[str, ...] = ()
    concept_tags: tuple[str, ...] = ()
    error_tags: tuple[str, ...] = ()
    source_ref: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseRubricProjection:
    question_id: str
    source_question_id: str
    rubric_version: str
    rubric_level: RubricLevel
    total_score: float
    items: list[CaseRubricItem]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnswerSpan:
    span_id: str
    text: str
    possible_concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RubricMatchResult:
    rubric_item_id: str
    criterion: str
    max_score: float
    awarded_score: float
    status: RubricMatchStatus
    evidence_text: str | None
    missing_meaning: str | None
    reason: str
    error_tags: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class CaseErrorEventPayload:
    question_id: str
    rubric_item_id: str
    concept_tag: str
    error_code: str
    severity: float
    evidence: str
    diagnosis: str


@dataclass(frozen=True)
class CaseGradingResult:
    grading_run_id: str
    question_id: str
    submission_text: str
    total_score: float
    max_score: float
    confidence: float
    status: GradingStatus
    rubric_results: list[RubricMatchResult]
    major_problems: tuple[str, ...] = ()
    rewrite_answer: str = ""
    next_training_suggestion: dict[str, Any] = field(default_factory=dict)
```

```python
# deeptutor/services/case_grading/__init__.py
from deeptutor.services.case_grading.schema import (
    AnswerSpan,
    CaseErrorEventPayload,
    CaseGradingResult,
    CaseQuestionAsset,
    CaseRubricItem,
    CaseRubricProjection,
    RubricMatchResult,
)

__all__ = [
    "AnswerSpan",
    "CaseErrorEventPayload",
    "CaseGradingResult",
    "CaseQuestionAsset",
    "CaseRubricItem",
    "CaseRubricProjection",
    "RubricMatchResult",
]
```

- [ ] **Step 4: Run the schema tests**

Run:

```bash
pytest tests/services/case_grading/test_schema.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 2: Add Case Asset Adapter And Fixture Rows

**Files:**

- Create: `deeptutor/services/case_grading/assets.py`
- Create: `tests/fixtures/case_grading/sample_questions_bank_rows.json`
- Test: `tests/services/case_grading/test_assets.py`

- [ ] **Step 1: Create the fixture**

```json
[
  {
    "id": "case_001",
    "question_type": "case_study",
    "question_stem": "某工程模板支撑高度较大，施工单位仅由项目经理审批后实施。",
    "stem": "",
    "question_text": "指出事件中的不妥之处，并说明正确做法。",
    "correct_answer": "施工单位应编制专项施工方案，按规定审核审批；超过一定规模的危大工程应组织专家论证；实施前应进行安全技术交底。",
    "analysis": "本题考查危大工程专项施工方案流程。",
    "score": 6,
    "source_type": "REAL_EXAM",
    "exam_year": 2024,
    "node_code": "1A424000",
    "grading_keywords": ["专项施工方案", "审核审批", "专家论证", "安全技术交底"],
    "grading_rubric": null,
    "tags": ["危大工程", "安全管理"],
    "source_meta": {"paper": "2024建筑实务"}
  },
  {
    "id": "case_002",
    "question_type": "single_choice",
    "question_stem": "流水步距反映什么？",
    "correct_answer": "B",
    "options": {"A": "工期", "B": "相邻专业队投入间隔"}
  }
]
```

- [ ] **Step 2: Write the failing adapter tests**

```python
# tests/services/case_grading/test_assets.py
import json
from pathlib import Path

from deeptutor.services.case_grading.assets import (
    is_case_question_row,
    row_to_case_question_asset,
)


FIXTURE = Path("tests/fixtures/case_grading/sample_questions_bank_rows.json")


def test_row_to_case_question_asset_preserves_questions_bank_id() -> None:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    asset = row_to_case_question_asset(rows[0])

    assert asset is not None
    assert asset.question_id == "case_001"
    assert asset.question_type == "case_study"
    assert asset.total_score == 6.0
    assert asset.grading_keywords == ("专项施工方案", "审核审批", "专家论证", "安全技术交底")
    assert asset.source_meta["paper"] == "2024建筑实务"


def test_non_case_question_row_is_not_case_asset() -> None:
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))

    assert is_case_question_row(rows[1]) is False
    assert row_to_case_question_asset(rows[1]) is None
```

- [ ] **Step 3: Run the test and confirm it fails**

Run:

```bash
pytest tests/services/case_grading/test_assets.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.case_grading.assets'
```

- [ ] **Step 4: Implement the adapter**

```python
# deeptutor/services/case_grading/assets.py
from __future__ import annotations

from typing import Any

from deeptutor.services.case_grading.schema import CaseQuestionAsset

_CASE_TYPES = {"case_study", "written", "short_answer", "essay"}


def is_case_question_row(row: dict[str, Any]) -> bool:
    question_type = str(row.get("question_type") or "").strip().lower()
    return question_type in _CASE_TYPES


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        return tuple(part.strip() for part in value.replace("，", ",").split(",") if part.strip())
    return ()


def _float_value(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def row_to_case_question_asset(row: dict[str, Any]) -> CaseQuestionAsset | None:
    if not isinstance(row, dict) or not is_case_question_row(row):
        return None
    question_id = str(row.get("id") or row.get("question_id") or "").strip()
    stem = str(row.get("question_stem") or row.get("stem") or "").strip()
    correct_answer = str(row.get("correct_answer") or row.get("answer") or "").strip()
    if not question_id or not stem or not correct_answer:
        return None
    source_meta = row.get("source_meta") if isinstance(row.get("source_meta"), dict) else {}
    return CaseQuestionAsset(
        question_id=question_id,
        question_type=str(row.get("question_type") or "case_study").strip(),
        stem=stem,
        question_text=str(row.get("question_text") or row.get("question") or "").strip(),
        correct_answer=correct_answer,
        analysis=str(row.get("analysis") or row.get("explanation") or "").strip(),
        total_score=_float_value(row.get("score") or row.get("total_score")),
        source_type=str(row.get("source_type") or "").strip(),
        exam_year=_int_or_none(row.get("exam_year") or source_meta.get("exam_year")),
        node_code=str(row.get("node_code") or "").strip(),
        grading_keywords=_string_tuple(row.get("grading_keywords")),
        grading_rubric=row.get("grading_rubric"),
        tags=_string_tuple(row.get("tags")),
        source_meta=dict(source_meta),
    )
```

- [ ] **Step 5: Run the adapter tests**

Run:

```bash
pytest tests/services/case_grading/test_assets.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 3: Build Case Rubric Readiness Audit

**Files:**

- Create: `deeptutor/services/case_grading/readiness.py`
- Create: `scripts/audit_case_rubric_readiness.py`
- Test: `tests/services/case_grading/test_readiness.py`

- [ ] **Step 1: Write the readiness tests**

```python
# tests/services/case_grading/test_readiness.py
import json
from pathlib import Path

from deeptutor.services.case_grading.assets import row_to_case_question_asset
from deeptutor.services.case_grading.readiness import evaluate_case_rubric_readiness


def test_readiness_classifies_case_assets_by_rubric_strength() -> None:
    rows = json.loads(Path("tests/fixtures/case_grading/sample_questions_bank_rows.json").read_text(encoding="utf-8"))
    assets = [row_to_case_question_asset(rows[0])]
    report = evaluate_case_rubric_readiness([asset for asset in assets if asset is not None])

    assert report["total_case_assets"] == 1
    assert report["ready_counts"]["needs_ai_split"] == 1
    assert report["items"][0]["question_id"] == "case_001"
    assert report["items"][0]["signals"]["has_keywords"] is True
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```bash
pytest tests/services/case_grading/test_readiness.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.case_grading.readiness'
```

- [ ] **Step 3: Implement the readiness evaluator**

```python
# deeptutor/services/case_grading/readiness.py
from __future__ import annotations

from collections import Counter
from typing import Any

from deeptutor.services.case_grading.schema import CaseQuestionAsset


def _has_structured_rubric(asset: CaseQuestionAsset) -> bool:
    rubric = asset.grading_rubric
    if isinstance(rubric, list):
        return len(rubric) >= 2
    if isinstance(rubric, dict):
        items = rubric.get("items") or rubric.get("rubric_items")
        return isinstance(items, list) and len(items) >= 2
    return False


def _answer_has_split_markers(answer: str) -> bool:
    text = str(answer or "")
    markers = ("1.", "1、", "（1）", "(1)", "；", ";", "\n")
    return any(marker in text for marker in markers)


def classify_case_asset_readiness(asset: CaseQuestionAsset) -> str:
    if _has_structured_rubric(asset):
        return "ready_structured"
    if asset.grading_keywords and asset.correct_answer:
        return "needs_ai_split"
    if _answer_has_split_markers(asset.correct_answer):
        return "needs_ai_split"
    if asset.correct_answer and asset.analysis:
        return "needs_human_review"
    return "not_ready"


def evaluate_case_rubric_readiness(assets: list[CaseQuestionAsset]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    for asset in assets:
        status = classify_case_asset_readiness(asset)
        counter[status] += 1
        items.append(
            {
                "question_id": asset.question_id,
                "status": status,
                "question_type": asset.question_type,
                "total_score": asset.total_score,
                "source_type": asset.source_type,
                "exam_year": asset.exam_year,
                "node_code": asset.node_code,
                "signals": {
                    "has_structured_rubric": _has_structured_rubric(asset),
                    "has_keywords": bool(asset.grading_keywords),
                    "has_answer": bool(asset.correct_answer),
                    "has_analysis": bool(asset.analysis),
                    "has_total_score": asset.total_score > 0,
                },
            }
        )
    return {
        "status": "pass" if counter["ready_structured"] + counter["needs_ai_split"] >= 20 else "warn",
        "total_case_assets": len(assets),
        "ready_counts": dict(counter),
        "items": items,
    }
```

- [ ] **Step 4: Add the audit script**

```python
# scripts/audit_case_rubric_readiness.py
#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib import parse, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deeptutor.services.case_grading.assets import row_to_case_question_asset
from deeptutor.services.case_grading.readiness import evaluate_case_rubric_readiness


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _config(env_file: Path) -> tuple[str, str]:
    values = _read_env_file(env_file)
    url = (os.getenv("SUPABASE_URL") or values.get("SUPABASE_URL") or values.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or values.get("SUPABASE_SERVICE_ROLE_KEY") or values.get("SUPABASE_ANON_KEY") or ""
    if not url or not key:
        raise RuntimeError("Missing Supabase config for case rubric readiness audit")
    return url, key


def _fetch_rows(env_file: Path, limit: int) -> list[dict]:
    base_url, api_key = _config(env_file)
    query = {
        "select": "id,question_type,question_stem,stem,question_text,correct_answer,analysis,score,total_score,source_type,exam_year,node_code,grading_keywords,grading_rubric,tags,source_meta",
        "question_type": "in.(case_study,written,short_answer,essay)",
        "limit": str(limit),
        "order": "id.asc",
    }
    req = request.Request(
        f"{base_url}/rest/v1/questions_bank?{parse.urlencode(query)}",
        headers={"apikey": api_key, "Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    with request.urlopen(req, timeout=30) as response:
        return list(json.loads(response.read().decode("utf-8") or "[]"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit case rubric readiness from questions_bank.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--fixture", help="Offline questions_bank rows JSON.")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--output", default="tmp/case_rubric_readiness_report.json")
    args = parser.parse_args(argv)

    if args.fixture:
        rows = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    else:
        rows = _fetch_rows(Path(args.env_file), args.limit)
    assets = [asset for row in rows if (asset := row_to_case_question_asset(row)) is not None]
    report = evaluate_case_rubric_readiness(assets)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(str(output))
    return 0 if report["total_case_assets"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests and offline audit**

Run:

```bash
pytest tests/services/case_grading/test_readiness.py -q
python scripts/audit_case_rubric_readiness.py \
  --fixture tests/fixtures/case_grading/sample_questions_bank_rows.json \
  --output tmp/case_rubric_readiness_fixture_report.json
```

Expected:

```text
1 passed
tmp/case_rubric_readiness_fixture_report.json
```

- [ ] **Step 6: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 4: Implement Rubric Normalizer

**Files:**

- Create: `deeptutor/services/case_grading/rubric_normalizer.py`
- Test: `tests/services/case_grading/test_rubric_normalizer.py`

- [ ] **Step 1: Write the failing normalizer tests**

```python
# tests/services/case_grading/test_rubric_normalizer.py
import json
from pathlib import Path

from deeptutor.services.case_grading.assets import row_to_case_question_asset
from deeptutor.services.case_grading.rubric_normalizer import build_rubric_projection


def test_build_rubric_projection_from_keywords_and_answer() -> None:
    row = json.loads(Path("tests/fixtures/case_grading/sample_questions_bank_rows.json").read_text(encoding="utf-8"))[0]
    asset = row_to_case_question_asset(row)
    assert asset is not None

    projection = build_rubric_projection(asset)

    assert projection.question_id == "case_001"
    assert projection.source_question_id == "case_001"
    assert projection.rubric_level == "L1"
    assert projection.total_score == 6.0
    assert len(projection.items) >= 3
    assert any("专家论证" in item.keywords for item in projection.items)
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
pytest tests/services/case_grading/test_rubric_normalizer.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'deeptutor.services.case_grading.rubric_normalizer'
```

- [ ] **Step 3: Implement normalizer**

Use deterministic extraction first. Keep AI extraction out of this task.

```python
# deeptutor/services/case_grading/rubric_normalizer.py
from __future__ import annotations

import re
from typing import Any

from deeptutor.services.case_grading.schema import (
    CaseQuestionAsset,
    CaseRubricItem,
    CaseRubricProjection,
)

_SPLIT_RE = re.compile(r"(?:\n+|；|;|(?<=。)|(?<=；)|\d+[.、]|[（(]\d+[）)])")


def _as_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _items_from_structured_rubric(asset: CaseQuestionAsset) -> list[CaseRubricItem]:
    rubric = asset.grading_rubric
    raw_items = []
    if isinstance(rubric, dict):
        raw_items = rubric.get("items") or rubric.get("rubric_items") or []
    elif isinstance(rubric, list):
        raw_items = rubric
    if not isinstance(raw_items, list):
        return []
    items: list[CaseRubricItem] = []
    fallback_score = asset.total_score / max(len(raw_items), 1) if asset.total_score else 1.0
    for index, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict):
            continue
        criterion = str(raw.get("criterion") or raw.get("name") or raw.get("text") or "").strip()
        meaning = str(raw.get("required_meaning") or raw.get("meaning") or criterion).strip()
        if not criterion:
            continue
        items.append(
            CaseRubricItem(
                item_id=f"r{index}",
                criterion=criterion,
                required_meaning=meaning,
                score=_as_float(raw.get("score"), fallback_score),
                keywords=tuple(str(item).strip() for item in raw.get("keywords", []) if str(item).strip()) if isinstance(raw.get("keywords"), list) else (),
                acceptable_expressions=tuple(str(item).strip() for item in raw.get("acceptable_expressions", []) if str(item).strip()) if isinstance(raw.get("acceptable_expressions"), list) else (),
                non_credit_expressions=("加强管理", "严格检查", "注意安全"),
                concept_tags=asset.tags,
                error_tags=("E02", "E03"),
                source_ref={"question_id": asset.question_id, "source_type": asset.source_type, "exam_year": asset.exam_year},
            )
        )
    return items


def _items_from_keywords(asset: CaseQuestionAsset) -> list[CaseRubricItem]:
    keywords = list(asset.grading_keywords)
    if not keywords:
        return []
    per_item_score = asset.total_score / len(keywords) if asset.total_score else 1.0
    return [
        CaseRubricItem(
            item_id=f"r{index}",
            criterion=f"写出“{keyword}”相关采分点",
            required_meaning=f"答案必须表达与“{keyword}”相关的核心含义",
            score=per_item_score,
            keywords=(keyword,),
            acceptable_expressions=(keyword,),
            non_credit_expressions=("加强管理", "严格检查", "注意安全"),
            concept_tags=asset.tags,
            error_tags=("E02", "E03"),
            source_ref={"question_id": asset.question_id, "source_type": asset.source_type, "exam_year": asset.exam_year},
        )
        for index, keyword in enumerate(keywords, 1)
    ]


def _items_from_answer(asset: CaseQuestionAsset) -> list[CaseRubricItem]:
    parts = [part.strip(" 。；;\n\t") for part in _SPLIT_RE.split(asset.correct_answer) if part.strip(" 。；;\n\t")]
    if len(parts) < 2:
        return []
    per_item_score = asset.total_score / len(parts) if asset.total_score else 1.0
    return [
        CaseRubricItem(
            item_id=f"r{index}",
            criterion=part[:80],
            required_meaning=part,
            score=per_item_score,
            keywords=tuple(keyword for keyword in asset.grading_keywords if keyword in part),
            acceptable_expressions=(part,),
            non_credit_expressions=("加强管理", "严格检查", "注意安全"),
            concept_tags=asset.tags,
            error_tags=("E02", "E03"),
            source_ref={"question_id": asset.question_id, "source_type": asset.source_type, "exam_year": asset.exam_year},
        )
        for index, part in enumerate(parts, 1)
    ]


def build_rubric_projection(asset: CaseQuestionAsset) -> CaseRubricProjection:
    structured = _items_from_structured_rubric(asset)
    if structured:
        return CaseRubricProjection(
            question_id=asset.question_id,
            source_question_id=asset.question_id,
            rubric_version="projection_v1",
            rubric_level="L2",
            total_score=asset.total_score or sum(item.score for item in structured),
            items=structured,
        )
    keyword_items = _items_from_keywords(asset)
    if keyword_items:
        return CaseRubricProjection(
            question_id=asset.question_id,
            source_question_id=asset.question_id,
            rubric_version="projection_v1",
            rubric_level="L1",
            total_score=asset.total_score or sum(item.score for item in keyword_items),
            items=keyword_items,
            warnings=("keyword_generated_rubric_requires_review",),
        )
    answer_items = _items_from_answer(asset)
    if answer_items:
        return CaseRubricProjection(
            question_id=asset.question_id,
            source_question_id=asset.question_id,
            rubric_version="projection_v1",
            rubric_level="L1",
            total_score=asset.total_score or sum(item.score for item in answer_items),
            items=answer_items,
            warnings=("answer_split_rubric_requires_review",),
        )
    return CaseRubricProjection(
        question_id=asset.question_id,
        source_question_id=asset.question_id,
        rubric_version="projection_v1",
        rubric_level="L0",
        total_score=asset.total_score,
        items=[],
        warnings=("rubric_not_ready",),
    )
```

- [ ] **Step 4: Run normalizer tests**

Run:

```bash
pytest tests/services/case_grading/test_rubric_normalizer.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 5: Implement Error Taxonomy And Score Aggregation

**Files:**

- Create: `deeptutor/services/case_grading/error_taxonomy.py`
- Create: `deeptutor/services/case_grading/score_aggregator.py`
- Test: `tests/services/case_grading/test_error_taxonomy.py`
- Test: `tests/services/case_grading/test_score_aggregator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/services/case_grading/test_error_taxonomy.py
from deeptutor.services.case_grading.error_taxonomy import (
    DEFAULT_ERROR_LABELS,
    map_existing_diagnosis_to_error_codes,
)


def test_error_taxonomy_contains_case_expression_errors() -> None:
    assert DEFAULT_ERROR_LABELS["E03"] == "关键词缺失"
    assert DEFAULT_ERROR_LABELS["E04"] == "口号化表达"


def test_existing_grading_diagnosis_maps_to_case_error_codes() -> None:
    assert map_existing_diagnosis_to_error_codes("OVERSIGHT") == ("E05",)
    assert map_existing_diagnosis_to_error_codes("PARTIAL") == ("E02",)
```

```python
# tests/services/case_grading/test_score_aggregator.py
from deeptutor.services.case_grading.schema import RubricMatchResult
from deeptutor.services.case_grading.score_aggregator import aggregate_score


def test_aggregate_score_clamps_scores_and_requires_evidence_for_full() -> None:
    result = aggregate_score(
        question_id="case_001",
        submission_text="加强管理。",
        matches=[
            RubricMatchResult(
                rubric_item_id="r1",
                criterion="应组织专家论证",
                max_score=1.0,
                awarded_score=1.0,
                status="full",
                evidence_text=None,
                missing_meaning=None,
                reason="模型误给满分",
                error_tags=("E03",),
                confidence=0.9,
            )
        ],
        max_score=1.0,
    )

    assert result.total_score == 0.0
    assert result.status == "needs_review"
    assert result.rubric_results[0].awarded_score == 0.0
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
pytest tests/services/case_grading/test_error_taxonomy.py \
  tests/services/case_grading/test_score_aggregator.py -q
```

Expected:

```text
ModuleNotFoundError
```

- [ ] **Step 3: Implement taxonomy and aggregation**

```python
# deeptutor/services/case_grading/error_taxonomy.py
from __future__ import annotations

DEFAULT_ERROR_LABELS = {
    "E01": "知识点缺失",
    "E02": "采分点遗漏",
    "E03": "关键词缺失",
    "E04": "口号化表达",
    "E05": "审题错误",
    "E06": "程序顺序错误",
    "E07": "概念混淆",
    "E08": "背景信息提取失败",
    "E09": "计算错误",
    "E10": "规范适用错误",
    "E11": "迁移失败",
    "E12": "表达冗余",
}

_EXISTING_DIAGNOSIS_MAP = {
    "CORRECT": (),
    "PARTIAL": ("E02",),
    "CONFUSION": ("E01", "E07"),
    "OVERSIGHT": ("E05",),
    "MEMORY_DECAY": ("E01", "E03"),
    "SLIP": (),
    "INVALID": (),
}


def map_existing_diagnosis_to_error_codes(diagnosis: str) -> tuple[str, ...]:
    return _EXISTING_DIAGNOSIS_MAP.get(str(diagnosis or "").strip().upper(), ())
```

```python
# deeptutor/services/case_grading/score_aggregator.py
from __future__ import annotations

import uuid

from deeptutor.services.case_grading.schema import CaseGradingResult, RubricMatchResult


def _clamp_score(value: float, *, max_score: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(score, float(max_score or 0.0)))


def _normalize_match(match: RubricMatchResult) -> RubricMatchResult:
    awarded = _clamp_score(match.awarded_score, max_score=match.max_score)
    status = match.status
    evidence = str(match.evidence_text or "").strip()
    if status == "full" and not evidence:
        awarded = 0.0
        status = "miss"
    return RubricMatchResult(
        rubric_item_id=match.rubric_item_id,
        criterion=match.criterion,
        max_score=match.max_score,
        awarded_score=awarded,
        status=status,
        evidence_text=evidence or None,
        missing_meaning=match.missing_meaning,
        reason=match.reason,
        error_tags=match.error_tags,
        confidence=max(0.0, min(float(match.confidence or 0.0), 1.0)),
    )


def aggregate_score(
    *,
    question_id: str,
    submission_text: str,
    matches: list[RubricMatchResult],
    max_score: float,
) -> CaseGradingResult:
    normalized = [_normalize_match(match) for match in matches]
    total = min(sum(match.awarded_score for match in normalized), float(max_score or 0.0))
    confidence = min((match.confidence for match in normalized), default=0.0)
    status = "ai_final" if confidence >= 0.75 and all(
        match.status != "full" or match.evidence_text for match in normalized
    ) else "needs_review"
    major_problems = tuple(
        match.reason for match in normalized if match.status in {"miss", "partial", "wrong"} and match.reason
    )[:3]
    return CaseGradingResult(
        grading_run_id=f"case_grade_{uuid.uuid4().hex[:12]}",
        question_id=question_id,
        submission_text=submission_text,
        total_score=round(total, 2),
        max_score=float(max_score or 0.0),
        confidence=round(confidence, 3),
        status=status,
        rubric_results=normalized,
        major_problems=major_problems,
    )
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/services/case_grading/test_error_taxonomy.py \
  tests/services/case_grading/test_score_aggregator.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 6: Add Matcher With Deterministic Test Seam

**Files:**

- Create: `deeptutor/services/case_grading/matcher.py`
- Test: `tests/services/case_grading/test_matcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/services/case_grading/test_matcher.py
from deeptutor.services.case_grading.matcher import deterministic_keyword_match
from deeptutor.services.case_grading.schema import CaseRubricItem


def test_deterministic_keyword_match_marks_partial_when_keyword_family_is_incomplete() -> None:
    item = CaseRubricItem(
        item_id="r1",
        criterion="应组织专家论证",
        required_meaning="超过一定规模危大工程专项方案应组织专家论证",
        score=1.0,
        keywords=("专家论证", "专项施工方案"),
        acceptable_expressions=("组织专家论证",),
        non_credit_expressions=("加强管理",),
        concept_tags=("危大工程",),
        error_tags=("E02", "E03"),
        source_ref={"question_id": "case_001"},
    )

    match = deterministic_keyword_match(item, "施工单位未编制专项施工方案，应加强管理。")

    assert match.status == "partial"
    assert match.awarded_score == 0.5
    assert match.evidence_text == "施工单位未编制专项施工方案，应加强管理。"
    assert "E03" in match.error_tags
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
pytest tests/services/case_grading/test_matcher.py -q
```

Expected:

```text
ModuleNotFoundError
```

- [ ] **Step 3: Implement deterministic matcher**

```python
# deeptutor/services/case_grading/matcher.py
from __future__ import annotations

from deeptutor.services.case_grading.schema import CaseRubricItem, RubricMatchResult


def deterministic_keyword_match(item: CaseRubricItem, submission_text: str) -> RubricMatchResult:
    answer = str(submission_text or "").strip()
    keywords = tuple(keyword for keyword in item.keywords if keyword)
    hit_keywords = tuple(keyword for keyword in keywords if keyword in answer)
    has_non_credit = any(expr and expr in answer for expr in item.non_credit_expressions)

    if keywords and len(hit_keywords) == len(keywords):
        return RubricMatchResult(
            rubric_item_id=item.item_id,
            criterion=item.criterion,
            max_score=item.score,
            awarded_score=item.score,
            status="full",
            evidence_text=answer,
            missing_meaning=None,
            reason="命中全部关键词",
            error_tags=(),
            confidence=0.8,
        )
    if hit_keywords:
        return RubricMatchResult(
            rubric_item_id=item.item_id,
            criterion=item.criterion,
            max_score=item.score,
            awarded_score=round(item.score * 0.5, 2),
            status="partial",
            evidence_text=answer,
            missing_meaning="缺少：" + "、".join(keyword for keyword in keywords if keyword not in hit_keywords),
            reason="只命中部分关键词",
            error_tags=tuple(dict.fromkeys((*item.error_tags, "E03"))),
            confidence=0.72,
        )
    return RubricMatchResult(
        rubric_item_id=item.item_id,
        criterion=item.criterion,
        max_score=item.score,
        awarded_score=0.0,
        status="miss",
        evidence_text=answer if has_non_credit else None,
        missing_meaning=item.required_meaning,
        reason="未找到可给分证据" + ("，且出现口号化表达" if has_non_credit else ""),
        error_tags=tuple(dict.fromkeys((*item.error_tags, "E04" if has_non_credit else "E02"))),
        confidence=0.7,
    )


def match_rubric_items_deterministic(
    *,
    items: list[CaseRubricItem],
    submission_text: str,
) -> list[RubricMatchResult]:
    return [deterministic_keyword_match(item, submission_text) for item in items]
```

- [ ] **Step 4: Run matcher tests**

Run:

```bash
pytest tests/services/case_grading/test_matcher.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 7: Compose CaseGradingService And Feedback

**Files:**

- Create: `deeptutor/services/case_grading/feedback.py`
- Create: `deeptutor/services/case_grading/service.py`
- Test: `tests/services/case_grading/test_service.py`

- [ ] **Step 1: Write failing service test**

```python
# tests/services/case_grading/test_service.py
import json
from pathlib import Path

from deeptutor.services.case_grading.assets import row_to_case_question_asset
from deeptutor.services.case_grading.service import CaseGradingService


def test_case_grading_service_returns_structured_score_and_feedback() -> None:
    row = json.loads(Path("tests/fixtures/case_grading/sample_questions_bank_rows.json").read_text(encoding="utf-8"))[0]
    asset = row_to_case_question_asset(row)
    assert asset is not None

    service = CaseGradingService()
    result = service.grade(asset=asset, submission_text="施工单位未编制专项施工方案，应加强管理。")

    assert result.question_id == "case_001"
    assert result.max_score == 6.0
    assert result.total_score > 0
    assert result.rewrite_answer
    assert result.next_training_suggestion["focus_concepts"]
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
pytest tests/services/case_grading/test_service.py -q
```

Expected:

```text
ModuleNotFoundError
```

- [ ] **Step 3: Implement feedback builder**

```python
# deeptutor/services/case_grading/feedback.py
from __future__ import annotations

from deeptutor.services.case_grading.schema import CaseGradingResult, CaseRubricProjection


def build_rewrite_answer(projection: CaseRubricProjection) -> str:
    if not projection.items:
        return ""
    parts = [item.required_meaning.rstrip("。") for item in projection.items[:6] if item.required_meaning]
    return "；".join(parts) + "。"


def build_next_training_suggestion(result: CaseGradingResult) -> dict[str, object]:
    concepts: list[str] = []
    error_tags: list[str] = []
    for match in result.rubric_results:
        for tag in match.error_tags:
            if tag and tag not in error_tags:
                error_tags.append(tag)
    for problem in result.major_problems:
        if problem and problem not in concepts:
            concepts.append(problem[:40])
    return {
        "focus_concepts": concepts[:3] or ["案例题得分表达"],
        "error_tags": error_tags[:5],
        "suggested_question_types": ["case_study"],
        "reason": "根据本次漏分点优先推荐同考点案例小题。",
    }
```

- [ ] **Step 4: Implement service**

```python
# deeptutor/services/case_grading/service.py
from __future__ import annotations

from deeptutor.services.case_grading.feedback import (
    build_next_training_suggestion,
    build_rewrite_answer,
)
from deeptutor.services.case_grading.matcher import match_rubric_items_deterministic
from deeptutor.services.case_grading.rubric_normalizer import build_rubric_projection
from deeptutor.services.case_grading.schema import CaseGradingResult, CaseQuestionAsset
from deeptutor.services.case_grading.score_aggregator import aggregate_score


class CaseGradingService:
    def grade(self, *, asset: CaseQuestionAsset, submission_text: str) -> CaseGradingResult:
        projection = build_rubric_projection(asset)
        matches = match_rubric_items_deterministic(
            items=projection.items,
            submission_text=submission_text,
        )
        result = aggregate_score(
            question_id=asset.question_id,
            submission_text=submission_text,
            matches=matches,
            max_score=projection.total_score,
        )
        return CaseGradingResult(
            grading_run_id=result.grading_run_id,
            question_id=result.question_id,
            submission_text=result.submission_text,
            total_score=result.total_score,
            max_score=result.max_score,
            confidence=result.confidence,
            status=result.status if projection.rubric_level in {"L2", "L3"} else "ai_draft",
            rubric_results=result.rubric_results,
            major_problems=result.major_problems,
            rewrite_answer=build_rewrite_answer(projection),
            next_training_suggestion=build_next_training_suggestion(result),
        )
```

- [ ] **Step 5: Run service tests**

Run:

```bash
pytest tests/services/case_grading/test_service.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 8: Write Error Events Through LearnerStateService

**Files:**

- Create: `deeptutor/services/case_grading/learner_writeback.py`
- Test: `tests/services/case_grading/test_learner_writeback.py`

- [ ] **Step 1: Write failing writeback test**

```python
# tests/services/case_grading/test_learner_writeback.py
from deeptutor.services.case_grading.learner_writeback import write_case_grading_events
from deeptutor.services.case_grading.schema import CaseGradingResult, RubricMatchResult


class FakeLearnerStateService:
    def __init__(self) -> None:
        self.events = []

    def append_memory_event(self, user_id: str, **kwargs):
        self.events.append((user_id, kwargs))
        return kwargs


def test_write_case_grading_events_uses_existing_learner_state_service() -> None:
    fake = FakeLearnerStateService()
    result = CaseGradingResult(
        grading_run_id="run_1",
        question_id="case_001",
        submission_text="加强管理",
        total_score=0.0,
        max_score=6.0,
        confidence=0.7,
        status="ai_draft",
        rubric_results=[
            RubricMatchResult(
                rubric_item_id="r1",
                criterion="应组织专家论证",
                max_score=1.0,
                awarded_score=0.0,
                status="miss",
                evidence_text="加强管理",
                missing_meaning="专家论证",
                reason="口号化表达",
                error_tags=("E04",),
                confidence=0.7,
            )
        ],
    )

    write_case_grading_events(
        learner_state_service=fake,
        user_id="u1",
        result=result,
        source_bot_id="construction_exam_default",
    )

    assert fake.events[0][0] == "u1"
    assert fake.events[0][1]["memory_kind"] == "case_grading_result"
    assert fake.events[0][1]["payload_json"]["question_id"] == "case_001"
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
pytest tests/services/case_grading/test_learner_writeback.py -q
```

Expected:

```text
ModuleNotFoundError
```

- [ ] **Step 3: Implement learner writeback**

```python
# deeptutor/services/case_grading/learner_writeback.py
from __future__ import annotations

from typing import Any

from deeptutor.services.case_grading.schema import CaseGradingResult


def _rubric_result_payload(result: CaseGradingResult) -> list[dict[str, Any]]:
    return [
        {
            "rubric_item_id": item.rubric_item_id,
            "criterion": item.criterion,
            "status": item.status,
            "awarded_score": item.awarded_score,
            "max_score": item.max_score,
            "evidence_text": item.evidence_text,
            "missing_meaning": item.missing_meaning,
            "error_tags": list(item.error_tags),
            "confidence": item.confidence,
        }
        for item in result.rubric_results
    ]


def write_case_grading_events(
    *,
    learner_state_service: Any,
    user_id: str,
    result: CaseGradingResult,
    source_bot_id: str | None = None,
) -> None:
    if not user_id or result.status == "discarded":
        return
    learner_state_service.append_memory_event(
        user_id,
        source_feature="case_grading",
        source_id=result.grading_run_id,
        source_bot_id=source_bot_id,
        memory_kind="case_grading_result",
        payload_json={
            "grading_run_id": result.grading_run_id,
            "question_id": result.question_id,
            "total_score": result.total_score,
            "max_score": result.max_score,
            "confidence": result.confidence,
            "status": result.status,
            "rubric_results": _rubric_result_payload(result),
            "major_problems": list(result.major_problems),
            "next_training_suggestion": result.next_training_suggestion,
        },
    )
```

- [ ] **Step 4: Run writeback tests**

Run:

```bash
pytest tests/services/case_grading/test_learner_writeback.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Run learner-state adjacent tests**

Run:

```bash
pytest tests/services/learner_state/test_service.py \
  tests/services/learner_state/test_outbox.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 9: Add Questions Bank First Recommendation

**Files:**

- Create: `deeptutor/services/case_grading/recommendation.py`
- Test: `tests/services/case_grading/test_recommendation.py`

- [ ] **Step 1: Write failing recommendation test**

```python
# tests/services/case_grading/test_recommendation.py
from deeptutor.services.case_grading.recommendation import select_next_case_question


def test_select_next_case_question_prefers_existing_questions_bank_match() -> None:
    result = select_next_case_question(
        focus_concepts=["危大工程"],
        candidates=[
            {"id": "q1", "question_type": "case_study", "tags": ["混凝土"], "node_code": "1A415000"},
            {"id": "q2", "question_type": "case_study", "tags": ["危大工程", "安全管理"], "node_code": "1A424000"},
        ],
    )

    assert result["question_id"] == "q2"
    assert result["source"] == "questions_bank"
```

- [ ] **Step 2: Run and confirm failure**

Run:

```bash
pytest tests/services/case_grading/test_recommendation.py -q
```

Expected:

```text
ModuleNotFoundError
```

- [ ] **Step 3: Implement recommendation selector**

```python
# deeptutor/services/case_grading/recommendation.py
from __future__ import annotations

from typing import Any


def _text_blob(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("id"),
        candidate.get("question_type"),
        candidate.get("node_code"),
        *(candidate.get("tags") or [] if isinstance(candidate.get("tags"), list) else []),
        str(candidate.get("question_stem") or candidate.get("stem") or ""),
    ]
    return " ".join(str(part or "") for part in parts)


def select_next_case_question(
    *,
    focus_concepts: list[str],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    concepts = [str(item).strip() for item in focus_concepts if str(item).strip()]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for candidate in candidates:
        if str(candidate.get("question_type") or "").strip().lower() not in {"case_study", "written", "short_answer", "essay"}:
            continue
        blob = _text_blob(candidate)
        score = sum(1 for concept in concepts if concept and concept in blob)
        ranked.append((score, candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] <= 0:
        return {
            "source": "none",
            "question_id": "",
            "reason": "没有找到匹配当前错因的现有案例题。",
        }
    selected = ranked[0][1]
    return {
        "source": "questions_bank",
        "question_id": str(selected.get("id") or selected.get("question_id") or ""),
        "reason": "优先推荐现有题库中与当前错因概念匹配的案例题。",
    }
```

- [ ] **Step 4: Run recommendation tests**

Run:

```bash
pytest tests/services/case_grading/test_recommendation.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 10: Preserve Case Metadata And Integrate Case Grading Into `deep_question`

**Files:**

- Modify: `deeptutor/services/question_followup.py`
- Modify: `deeptutor/capabilities/deep_question.py`
- Modify: `tests/services/test_question_followup.py`
- Modify: `tests/core/test_deep_question_submission_grading.py`

- [ ] **Step 1: Write failing metadata preservation test**

Append or adapt this test in `tests/services/test_question_followup.py`:

```python
def test_normalize_question_followup_context_preserves_case_grading_metadata() -> None:
    context = {
        "question_id": "case_001",
        "question": "指出模板支撑工程专项方案管理的不妥之处。",
        "question_type": "case_study",
        "correct_answer": "应编制专项施工方案并组织专家论证。",
        "explanation": "危大工程专项方案流程。",
        "score": 6,
        "source_type": "REAL_EXAM",
        "exam_year": 2025,
        "node_code": "建筑实务.安全.危大工程",
        "grading_keywords": ["专项施工方案", "专家论证"],
        "grading_rubric": [{"criterion": "应组织专家论证", "score": 1}],
        "tags": ["危大工程"],
        "source_meta": {"paper": "2025 一建建筑实务"},
    }

    normalized = normalize_question_followup_context(context)

    assert normalized is not None
    assert normalized["score"] == 6
    assert normalized["source_type"] == "REAL_EXAM"
    assert normalized["exam_year"] == 2025
    assert normalized["node_code"] == "建筑实务.安全.危大工程"
    assert normalized["grading_keywords"] == ["专项施工方案", "专家论证"]
    assert normalized["grading_rubric"] == [{"criterion": "应组织专家论证", "score": 1}]
    assert normalized["tags"] == ["危大工程"]
    assert normalized["source_meta"] == {"paper": "2025 一建建筑实务"}
```

- [ ] **Step 2: Run and confirm metadata test failure**

Run:

```bash
pytest tests/services/test_question_followup.py::test_normalize_question_followup_context_preserves_case_grading_metadata -q
```

Expected:

```text
FAIL
```

The failure proves the existing context normalizer drops case-grading metadata. Do not work around this in `deep_question`; preserve the existing context once at its authority boundary.

- [ ] **Step 3: Preserve case grading metadata in `question_followup`**

In `deeptutor/services/question_followup.py`, extend `normalize_question_followup_context` with a narrow allowlist:

```python
_CASE_GRADING_CONTEXT_KEYS = (
    "score",
    "source_type",
    "exam_year",
    "node_code",
    "grading_keywords",
    "grading_rubric",
    "tags",
    "source_meta",
)
```

When the source context contains these keys, copy them into the normalized context without renaming them. This is not a second schema; it is only context preservation so the existing `questions_bank` row metadata can reach `CaseGradingService`.

Then run:

```bash
pytest tests/services/test_question_followup.py::test_normalize_question_followup_context_preserves_case_grading_metadata -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Write failing integration test**

Append this test to `tests/core/test_deep_question_submission_grading.py`:

```python
@pytest.mark.asyncio
async def test_deep_question_routes_written_case_submission_to_case_grading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeCaseGradingService:
        def grade(self, *, asset, submission_text: str):
            captured["asset"] = asset
            captured["submission_text"] = submission_text
            from deeptutor.services.case_grading.schema import CaseGradingResult

            return CaseGradingResult(
                grading_run_id="run_case",
                question_id=asset.question_id,
                submission_text=submission_text,
                total_score=3.0,
                max_score=6.0,
                confidence=0.82,
                status="ai_final",
                rubric_results=[],
                major_problems=("漏专家论证",),
                rewrite_answer="应编制专项施工方案并组织专家论证。",
                next_training_suggestion={"focus_concepts": ["危大工程"]},
            )

    monkeypatch.setattr(
        "deeptutor.services.case_grading.service.CaseGradingService",
        FakeCaseGradingService,
    )

    context = UnifiedContext(
        user_message="施工单位未编制专项方案，应加强管理。",
        language="zh",
        metadata={
            "turn_semantic_decision": {"next_action": "route_to_grading"},
            "question_followup_action": {
                "intent": "answer_questions",
                "answer": "施工单位未编制专项方案，应加强管理。",
            },
            "question_followup_context": {
                "question_id": "case_001",
                "question": "某工程模板支撑高度较大，施工单位仅由项目经理审批后实施。指出不妥之处。",
                "question_type": "case_study",
                "correct_answer": "应编制专项施工方案并组织专家论证。",
                "explanation": "危大工程专项方案流程。",
                "score": 6,
                "source_type": "REAL_EXAM",
                "exam_year": 2025,
                "node_code": "建筑实务.安全.危大工程",
                "grading_keywords": ["专项施工方案", "专家论证"],
                "tags": ["危大工程"],
            },
        },
    )

    capability = DeepQuestionCapability()
    events = await _collect_events(lambda bus: capability.run(context, bus))

    result_event = next(event for event in events if event.type == StreamEventType.RESULT)
    assert result_event.metadata["mode"] == "case_grading"
    assert result_event.metadata["case_grading_result"]["total_score"] == 3.0
    assert "应编制专项施工方案" in result_event.metadata["response"]
```

- [ ] **Step 5: Run and confirm integration test failure**

Run:

```bash
pytest tests/core/test_deep_question_submission_grading.py::test_deep_question_routes_written_case_submission_to_case_grading -q
```

Expected:

```text
FAIL
```

The failure should show that written/case submissions still route through the generic `SubmissionGraderAgent` path.

- [ ] **Step 6: Add a case grading helper inside `deep_question.py`**

Near existing helper functions, add:

```python
def _is_case_grading_context(question_context: dict[str, Any] | None) -> bool:
    normalized = normalize_question_followup_context(question_context) or {}
    question_type = str(normalized.get("question_type") or "").strip().lower()
    return question_type in {"case_study", "written", "short_answer", "essay"}
```

Add an import inside the case branch instead of a top-level import:

```python
from deeptutor.services.case_grading.assets import row_to_case_question_asset
from deeptutor.services.case_grading.service import CaseGradingService
```

Inside the existing `next_action == "route_to_grading"` branch, before constructing `SubmissionGraderAgent`, add:

```python
if _is_case_grading_context(action_context):
    asset = row_to_case_question_asset(
        {
            "id": action_context.get("question_id"),
            "question_type": action_context.get("question_type"),
            "question_stem": action_context.get("question"),
            "question_text": action_context.get("question_text", ""),
            "correct_answer": action_context.get("correct_answer"),
            "analysis": action_context.get("explanation"),
            "score": action_context.get("score"),
            "source_type": action_context.get("source_type", ""),
            "exam_year": action_context.get("exam_year"),
            "node_code": action_context.get("node_code", ""),
            "grading_keywords": action_context.get("grading_keywords", []),
            "grading_rubric": action_context.get("grading_rubric"),
            "tags": action_context.get("tags", []),
            "source_meta": action_context.get("source_meta", {}),
        }
    )
    if asset is not None:
        case_result = CaseGradingService().grade(
            asset=asset,
            submission_text=str(action_context.get("user_answer") or context.user_message or "").strip(),
        )
        answer = (
            "## 阅卷结论\n"
            f"预计得分：{case_result.total_score:g}/{case_result.max_score:g}\n\n"
            "## 主要问题\n"
            + "\n".join(f"- {item}" for item in case_result.major_problems)
            + "\n\n## 得分表达改写\n"
            + case_result.rewrite_answer
        ).strip()
        await stream.content(answer, source=self.name, stage="generation")
        await stream.result(
            {
                "response": answer,
                "mode": "case_grading",
                "question_id": case_result.question_id,
                "user_answer": case_result.submission_text,
                "is_correct": None,
                "case_grading_result": {
                    "grading_run_id": case_result.grading_run_id,
                    "question_id": case_result.question_id,
                    "total_score": case_result.total_score,
                    "max_score": case_result.max_score,
                    "confidence": case_result.confidence,
                    "status": case_result.status,
                    "major_problems": list(case_result.major_problems),
                    "rewrite_answer": case_result.rewrite_answer,
                    "next_training_suggestion": case_result.next_training_suggestion,
                },
                "question_followup_context": normalize_question_followup_context(action_context) or {},
                "active_object": build_active_object_from_question_context(
                    action_context,
                    source_turn_id=turn_id,
                    previous_active_object=active_object,
                )
                or {},
                "suspended_object_stack": suspended_object_stack,
                "turn_semantic_decision": turn_semantic_decision
                or self._default_turn_semantic_decision(
                    next_action="route_to_grading",
                    active_object=active_object,
                    question_context=action_context,
                    user_message=context.user_message,
                ),
            },
            source=self.name,
        )
        return
```

Keep the service import inside the case branch unless a test proves module-level import is needed. Do not add a new route.

- [ ] **Step 7: Run focused integration test**

Run:

```bash
pytest tests/core/test_deep_question_submission_grading.py::test_deep_question_routes_written_case_submission_to_case_grading -q
```

Expected:

```text
1 passed
```

- [ ] **Step 8: Run existing grading tests**

Run:

```bash
pytest tests/core/test_deep_question_submission_grading.py \
  tests/services/test_question_followup.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Run contract-adjacent tests**

Run:

```bash
pytest tests/api/test_unified_ws_turn_runtime.py::test_turn_runtime_routes_question_followup_to_grading \
  tests/core/test_deep_question_submission_grading.py -q
```

If the named unified WS test does not exist in the current checkout, run:

```bash
pytest tests/api/test_unified_ws_turn_runtime.py tests/core/test_deep_question_submission_grading.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 11: Add Golden Evaluation Harness

**Files:**

- Create: `tests/fixtures/case_grading/sample_submissions.json`
- Create: `tests/services/case_grading/test_golden_eval.py`

- [ ] **Step 1: Add sample submissions**

```json
[
  {
    "question_id": "case_001",
    "submission_text": "施工单位未编制专项施工方案，应加强管理。",
    "expected_min_score": 0.5,
    "expected_error_tags": ["E03"]
  },
  {
    "question_id": "case_001",
    "submission_text": "应编制专项施工方案并按规定审批，超过一定规模的危大工程应组织专家论证，实施前进行安全技术交底。",
    "expected_min_score": 3.0,
    "expected_error_tags": []
  }
]
```

- [ ] **Step 2: Write golden eval test**

```python
# tests/services/case_grading/test_golden_eval.py
import json
from pathlib import Path

from deeptutor.services.case_grading.assets import row_to_case_question_asset
from deeptutor.services.case_grading.service import CaseGradingService


def test_case_grading_golden_samples_meet_minimum_scores() -> None:
    rows = json.loads(Path("tests/fixtures/case_grading/sample_questions_bank_rows.json").read_text(encoding="utf-8"))
    submissions = json.loads(Path("tests/fixtures/case_grading/sample_submissions.json").read_text(encoding="utf-8"))
    assets = {
        asset.question_id: asset
        for row in rows
        if (asset := row_to_case_question_asset(row)) is not None
    }
    service = CaseGradingService()

    for sample in submissions:
        result = service.grade(
            asset=assets[sample["question_id"]],
            submission_text=sample["submission_text"],
        )
        assert result.total_score >= sample["expected_min_score"]
        tags = {tag for item in result.rubric_results for tag in item.error_tags}
        for expected_tag in sample["expected_error_tags"]:
            assert expected_tag in tags
```

- [ ] **Step 3: Run golden eval**

Run:

```bash
pytest tests/services/case_grading/test_golden_eval.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Checkpoint scope**

Do not commit automatically. Record changed files and verification output; commit only if the user explicitly asks, and then stage only the files from this task.

### Task 12: Run Full P0 Verification

**Files:**

- No new files unless failures require fixes.

- [ ] **Step 1: Run the case grading suite**

```bash
pytest tests/services/case_grading -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run practice and grading continuity tests**

```bash
pytest tests/core/test_deep_question_submission_grading.py \
  tests/services/test_question_followup.py \
  tests/agents/question/test_submission_grader_agent.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Run learner state writeback tests**

```bash
pytest tests/services/learner_state/test_service.py \
  tests/services/learner_state/test_outbox.py \
  tests/services/learner_state/test_supabase_writer.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Run contract guard**

```bash
python scripts/check_contract_guard.py
```

Expected:

```text
no contract violations
```

If the guard reports that `deep_question.py` is not indexed under a contract domain, record the result in the final implementation note. If it reports a protected-domain violation, add the exact required test or contract-surface update before proceeding.

- [ ] **Step 5: Run offline readiness report**

```bash
python scripts/audit_case_rubric_readiness.py \
  --fixture tests/fixtures/case_grading/sample_questions_bank_rows.json \
  --output tmp/case_rubric_readiness_fixture_report.json
```

Expected:

```text
tmp/case_rubric_readiness_fixture_report.json
```

- [ ] **Step 6: Run live Supabase readiness report when credentials are present**

```bash
python scripts/audit_case_rubric_readiness.py \
  --env-file .env \
  --limit 200 \
  --output tmp/case_rubric_readiness_report.json
```

Expected when credentials exist:

```text
tmp/case_rubric_readiness_report.json
```

Expected when credentials are missing:

```text
RuntimeError: Missing Supabase config for case rubric readiness audit
```

The missing credentials result is not a code failure. It means live readiness must be run in the configured environment.

- [ ] **Step 7: Record verification docs only if new evidence is appended**

If appending implementation evidence to the PRD, update the PRD and `docs/plan/INDEX.md` if status changes. Do not commit automatically; commit only if the user explicitly asks.

## 4. Release Gate

P0 can be called implemented locally only when all are true:

1. `pytest tests/services/case_grading -q` passes.
2. `pytest tests/core/test_deep_question_submission_grading.py tests/services/test_question_followup.py -q` passes.
3. `python scripts/audit_case_rubric_readiness.py --fixture ...` writes a report.
4. Live Supabase readiness has either run successfully or is explicitly blocked by missing local credentials.
5. No new route was added.
6. No new Supabase schema migration was added.
7. `CaseGradingService` is the only score authority for written/case submissions.
8. Learner writeback goes through `LearnerStateService`, not a new store.

P1 can start only after P0 gate passes and at least 20 L2 rubric candidates are identified.

## 5. Follow-up Plans After P0

Create separate plans after P0 evidence exists:

1. `teacher-calibration-workbench-implementation-plan`
   - Rubric review, teacher correction, class heatmap.
2. `case-variant-validator-implementation-plan`
   - Generated variants, validator, approval queue.
3. `mini-program-case-practice-ui-implementation-plan`
   - Mobile case answer input, report UI, optional OCR.

Do not merge those into this P0 plan.
