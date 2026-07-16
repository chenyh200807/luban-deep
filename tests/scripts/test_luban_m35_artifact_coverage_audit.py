import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/audit_luban_m35_artifact_coverage.py"


def _write_fixture(root: Path, *, questions: list[dict], answers: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"fixture_id": "unit_fixture", "questions": questions}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "student_answers.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in answers) + "\n",
        encoding="utf-8",
    )


def _run_audit(tmp_path: Path, fixture: Path) -> dict:
    out = tmp_path / "coverage.json"
    subprocess.run(
        ["python", str(SCRIPT), "--fixture", str(fixture), "--output", str(out)],
        check=True,
        cwd=REPO_ROOT,
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_missing_fastapi_case_artifacts_create_compiler_work_orders(tmp_path):
    fixture = tmp_path / "fixture"
    _write_fixture(
        fixture,
        questions=[
            {"question_id": "Q1-NA", "stem": "既有 golden artifact 覆盖题"},
            {"question_id": "Q2023-02__P01", "stem": "FastAPI 案例子题"},
        ],
        answers=[
            {"answer_id": "A1", "question_id": "Q1-NA", "student_answer": "专家论证"},
            {"answer_id": "A2", "question_id": "Q2023-02__P01", "student_answer": "项目经理处理"},
        ],
    )

    payload = _run_audit(tmp_path, fixture)

    assert payload["question_count"] == 2
    assert payload["missing_artifact_count"] == 1
    assert payload["compiled_artifact_count"] == 1
    assert payload["verdict"] == "NO_GO_ARTIFACT_COVERAGE"
    assert payload["quality_claim_allowed"] is False
    assert payload["production_write_count"] == 0
    assert payload["canonical_truth_written"] is False
    assert payload["official_score_allowed"] is False
    assert payload["compiler_ledger"]["candidate_used_as_release_truth"] == 0

    work_orders = payload["compiler_work_orders"]
    assert len(work_orders) == 1
    assert work_orders[0]["namespace"] == "luban_compiler_candidate"
    assert work_orders[0]["kind"] == "work_order"
    assert work_orders[0]["origin"] == "m35_artifact_coverage_audit"
    assert work_orders[0]["promote_to_release"] is False
    assert work_orders[0]["is_release_truth"] is False
    assert work_orders[0]["payload"]["work_order_type"] == "compile_missing_scoring_artifact"
    assert work_orders[0]["payload"]["question_id"] == "Q2023-02__P01"
    assert work_orders[0]["payload"]["runtime_usable_as_truth"] is False


def test_current_fastapi_case_fixture_is_no_go_until_artifacts_are_compiled(tmp_path):
    payload = _run_audit(
        tmp_path,
        REPO_ROOT / "tests/fixtures/luban_m35_fastapi_case_subquestions_20q_100a",
    )

    assert payload["question_count"] >= 20
    assert payload["missing_artifact_count"] == payload["question_count"]
    assert payload["compiled_artifact_count"] == 0
    assert payload["verdict"] == "NO_GO_ARTIFACT_COVERAGE"
    assert payload["quality_claim_allowed"] is False
    assert payload["compiler_ledger"]["by_kind"] == {"work_order": payload["question_count"]}
