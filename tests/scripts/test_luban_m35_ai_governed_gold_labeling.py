"""R2 AI-governed gold labeling pipeline skeleton tests (hermetic, no live LLM).

Every output row claiming ``ai_governed_gold`` must pass the canonical
``validate_ai_governed_gold_protocol`` and the row-level contract enforced by
``scripts/audit_luban_m35_label_authority.audit``. Sample-volume gates
(``NO_GO_LABEL_VOLUME``) are expected on a small slice and are not failures.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from deeptutor.services.construction_grading.m35_ai_governed_gold import (
    validate_ai_governed_gold_protocol,
)
from scripts.audit_luban_m35_label_authority import audit

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/run_luban_m35_ai_governed_gold_labeling.py"
FIXTURE_DIR = REPO / "tests/fixtures/luban_m35_fastapi_case_subquestions_20q_100a"
SLICE_QUESTION_IDS = ("Q2023-01__P01", "Q2023-01__P02", "Q2023-01__P03")
# Terms chosen so the hard-coded deterministic mutation rules in the script
# never create or destroy them (mutation-stable happy path).
DEFAULT_POINT_SPECS = {
    "Q2023-01__P01": [(["见证记录"], 2.0), (["取样"], 1.0)],
    "Q2023-01__P02": [(["质量缺陷"], 2.0)],
    "Q2023-01__P03": [(["防水"], 2.0)],
}
BUCKET_CYCLE = ("hit", "partial", "miss", "wrong_content", "calculation", "stem_fact")


def _scoring_point(question_id: str, index: int, terms: list[str], max_score: float) -> dict:
    return {
        "point_id": f"{question_id}::SP{index:02d}",
        "criterion": f"作答需覆盖：{'、'.join(terms)}",
        "max_score": max_score,
        "policy_type": "standard",
        "required_terms": terms,
        "negative_evidence": [],
        "source_refs": [
            {
                "source_type": "exam_reference_answer",
                "source_id": f"EXAM-{question_id}-SP{index:02d}",
                "quote_hash": f"sha256:{'0' * 16}",
                "verified": True,
            }
        ],
    }


def _build_slice(
    tmp_path: Path,
    *,
    question_ids: tuple[str, ...] = SLICE_QUESTION_IDS,
    per_question: int = 2,
    point_specs: dict | None = None,
    answer_text: str | None = None,
) -> tuple[Path, Path, list[dict]]:
    source_rows = [
        json.loads(line)
        for line in (FIXTURE_DIR / "student_answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected: list[dict] = []
    for question_id in question_ids:
        matching = [row for row in source_rows if row["question_id"] == question_id]
        selected.extend(matching[:per_question])
    assert selected, "fixture slice must not be empty"
    rows = [
        {
            **row,
            "student_answer": answer_text if answer_text is not None else row["student_answer"],
            "sample_bucket": BUCKET_CYCLE[index % len(BUCKET_CYCLE)],
        }
        for index, row in enumerate(selected)
    ]

    specs = point_specs or DEFAULT_POINT_SPECS
    source_manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    questions = [
        {
            **question,
            "scoring_points": [
                _scoring_point(question["question_id"], index + 1, terms, max_score)
                for index, (terms, max_score) in enumerate(specs[question["question_id"]])
            ],
        }
        for question in source_manifest["questions"]
        if question["question_id"] in question_ids
    ]
    manifest = {**source_manifest, "questions": questions}

    answers_path = tmp_path / "input_student_answers.jsonl"
    answers_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "input_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return answers_path, manifest_path, rows


def _term_judge(point: dict, student_answer: str, official_anchor: dict) -> dict:
    terms = point.get("required_terms") or []
    found = [term for term in terms if term in student_answer]
    if terms and len(found) == len(terms):
        verdict = "hit"
    elif found:
        verdict = "partial"
    else:
        verdict = "miss"
    return {
        "verdict": verdict,
        "evidence_span": found[0] if found else "",
        "confidence": 0.9,
    }


def _verdict_judge(verdict: str):
    def judge(point: dict, student_answer: str, official_anchor: dict) -> dict:
        return {
            "verdict": verdict,
            "evidence_span": student_answer[:8],
            "confidence": 0.8,
        }

    return judge


def _stub_judges() -> dict:
    # Sorted ids -> blind panel: 1..3, arbiter: 4, adversarial prosecutor: 5.
    return {f"stub-judge-{index}": _term_judge for index in range(1, 6)}


def _run(tmp_path: Path, judge_fns: dict, **slice_kwargs):
    from scripts.run_luban_m35_ai_governed_gold_labeling import run_labeling

    answers_path, manifest_path, input_rows = _build_slice(tmp_path, **slice_kwargs)
    output_dir = tmp_path / "out"
    result = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns=judge_fns,
        output_dir=output_dir,
    )
    rows = [
        json.loads(line)
        for line in (output_dir / "student_answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    return result, rows, manifest, output_dir, input_rows


def test_gold_slice_rows_validate_and_pass_row_level_audit(tmp_path):
    _, rows, manifest, output_dir, input_rows = _run(tmp_path, _stub_judges())

    assert len(rows) == len(input_rows) >= 3
    for row in rows:
        assert row["label_authority"] == "ai_governed_gold"
        assert row["label_scope"] == "point_and_score"
        assert row["directionality_flag"] == "ai_governed_gold"
        assert row["sample_bucket"]
        assert row["gold_point_matches"]
        assert validate_ai_governed_gold_protocol(row["ai_governed_gold"])["valid"] is True

    # Deterministic score sum from artifact point values: 2.0 (hit) + 1.0 (hit).
    by_id = {row["answer_id"]: row for row in rows}
    assert by_id["Q2023-01__P01__S01"]["gold_score"] == 3.0

    payload = audit(output_dir / "student_answers.jsonl")
    assert payload["missing_contract_answer_ids"] == []
    # Volume gate is the expected ceiling on a small slice; contract must be clean.
    assert payload["verdict_ceiling"] == "NO_GO_LABEL_VOLUME"
    assert payload["label_authority_counts"] == {"ai_governed_gold": len(rows)}

    assert manifest["fleiss_kappa"] == 1.0
    assert manifest["mutation_pass_rate"] == 1.0
    assert manifest["stop_condition_triggered"] is False
    assert manifest["gold_row_count"] == len(rows)
    assert manifest["model_roles"]["blind_panel"] == [
        "stub-judge-1",
        "stub-judge-2",
        "stub-judge-3",
    ]
    assert manifest["model_roles"]["arbiter"] == "stub-judge-4"
    assert manifest["model_roles"]["adversarial_prosecutor"] == "stub-judge-5"


def test_split_votes_route_to_arbitration_and_cannot_claim_gold(tmp_path):
    judges = {
        "stub-judge-1": _verdict_judge("hit"),
        "stub-judge-2": _verdict_judge("partial"),
        "stub-judge-3": _verdict_judge("miss"),
        "stub-judge-4": _verdict_judge("partial"),
        "stub-judge-5": _term_judge,
    }
    _, rows, manifest, output_dir, _ = _run(tmp_path, judges)

    for row in rows:
        assert row["label_authority"] == "ai_council_directional"
        assert row["directionality_flag"] == "ai_council_directional"
        assert "ai_governed_gold" not in row
        assert "insufficient_independent_blind_accepts" in row["downgrade_reasons"]
        for provenance in row["point_label_provenance"]:
            assert provenance["route"] == "arbitration"
            assert provenance["arbiter_model_id"] == "stub-judge-4"
            assert provenance["arbiter_verdict"] == "partial"
            assert provenance["consolidated_verdict"] == "partial"
            assert provenance["authority"] == "ai_council_directional"

    # Downgraded rows must still satisfy the row-level label contract.
    payload = audit(output_dir / "student_answers.jsonl")
    assert payload["missing_contract_answer_ids"] == []
    assert manifest["gold_row_count"] == 0


def test_majority_votes_are_reviewed_and_confirmed_by_arbiter(tmp_path):
    judges = {
        "stub-judge-1": _verdict_judge("hit"),
        "stub-judge-2": _verdict_judge("hit"),
        "stub-judge-3": _verdict_judge("partial"),
        "stub-judge-4": _verdict_judge("hit"),
        "stub-judge-5": _verdict_judge("hit"),
    }
    _, rows, _, _, _ = _run(tmp_path, judges)

    for row in rows:
        assert row["label_authority"] == "ai_governed_gold"
        protocol = row["ai_governed_gold"]
        assert validate_ai_governed_gold_protocol(protocol)["valid"] is True
        votes = {vote["model_id"]: vote["verdict"] for vote in protocol["blind_model_votes"]}
        assert votes["stub-judge-1"] == "accept"
        assert votes["stub-judge-2"] == "accept"
        assert votes["stub-judge-3"] == "dissent"
        assert votes["stub-judge-4"] == "accept"
        for provenance in row["point_label_provenance"]:
            assert provenance["route"] == "majority_review_confirmed"


def test_unresolved_prosecutor_objection_downgrades_entire_row(tmp_path):
    judges = {
        "stub-judge-1": _verdict_judge("hit"),
        "stub-judge-2": _verdict_judge("hit"),
        "stub-judge-3": _verdict_judge("hit"),
        "stub-judge-4": _verdict_judge("hit"),
        # Prosecutor demands miss against a consolidated hit: a two-level
        # disagreement cannot be auto-resolved -> unresolved objection.
        "stub-judge-5": _verdict_judge("miss"),
    }
    _, rows, manifest, output_dir, _ = _run(tmp_path, judges)

    for row in rows:
        assert row["label_authority"] == "ai_council_directional"
        assert "ai_governed_gold" not in row
        assert "unresolved_adversarial_objection" in row["downgrade_reasons"]
        assert row["adversarial_review"]["role"] == "adversarial_prosecutor"
        assert row["adversarial_review"]["unresolved_objection_count"] >= 1

    payload = audit(output_dir / "student_answers.jsonl")
    assert payload["missing_contract_answer_ids"] == []
    assert manifest["gold_row_count"] == 0


def test_one_level_prosecutor_objection_is_resolved_by_blind_supermajority(tmp_path):
    judges = {
        "stub-judge-1": _verdict_judge("hit"),
        "stub-judge-2": _verdict_judge("hit"),
        "stub-judge-3": _verdict_judge("hit"),
        "stub-judge-4": _verdict_judge("hit"),
        "stub-judge-5": _verdict_judge("partial"),
    }
    _, rows, _, _, _ = _run(tmp_path, judges)

    for row in rows:
        assert row["label_authority"] == "ai_governed_gold"
        adversarial = row["ai_governed_gold"]["adversarial_review"]
        assert adversarial["role"] == "adversarial_prosecutor"
        assert adversarial["objection_count"] >= 1
        assert adversarial["unresolved_objection_count"] == 0
        assert validate_ai_governed_gold_protocol(row["ai_governed_gold"])["valid"] is True


def test_mutation_instability_downgrades_and_triggers_stop_condition(tmp_path):
    # Meaning-preserving mutations must remain stable. Here exact marker terms
    # are destroyed by synonym_swap and punctuation_normalize -> 4/6 accepted.
    _, rows, manifest, _, _ = _run(
        tmp_path,
        _stub_judges(),
        question_ids=("Q2023-01__P01",),
        per_question=1,
        answer_text="不妥；试验员制作见证记录。",
        point_specs={"Q2023-01__P01": [(["不妥", "；"], 2.0)]},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["label_authority"] == "ai_council_directional"
    assert "mutation_test_failed" in row["downgrade_reasons"]
    assert row["mutation_test"]["passed"] is False
    assert row["mutation_test"]["case_count"] >= 5

    assert manifest["fleiss_kappa"] == 1.0
    assert manifest["mutation_pass_rate"] == pytest.approx(4 / 6, abs=1e-6)
    assert manifest["stop_condition_triggered"] is True
    assert "mutation_pass_rate_below_threshold" in manifest["stop_condition"]["reasons"]


def test_invalid_positive_evidence_span_downgrades_row(tmp_path):
    def invalid_span_judge(point: dict, student_answer: str, official_anchor: dict) -> dict:
        return {
            "verdict": "hit",
            "evidence_span": "这段证据不在学生作答中",
            "confidence": 0.9,
        }

    _, rows, manifest, _, _ = _run(
        tmp_path,
        {f"stub-judge-{index}": invalid_span_judge for index in range(1, 6)},
        question_ids=("Q2023-01__P01",),
        per_question=1,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["label_authority"] == "ai_council_directional"
    assert "ai_governed_gold" not in row
    assert "evidence_span_audit_failed" in row["downgrade_reasons"]
    assert row["evidence_span_audit"]["passed"] is False
    assert row["evidence_span_audit"]["violations"][0]["reason"] == "positive_span_not_in_answer"
    assert manifest["gold_row_count"] == 0


def test_evidence_span_auditor_repairs_unique_whitespace_collapsed_span(tmp_path):
    def collapsed_span_judge(point: dict, student_answer: str, official_anchor: dict) -> dict:
        return {
            "verdict": "hit",
            "evidence_span": "作答：问题1：不妥之处：试验员如实记录",
            "confidence": 0.9,
        }

    _, rows, manifest, _, _ = _run(
        tmp_path,
        {f"stub-judge-{index}": collapsed_span_judge for index in range(1, 6)},
        question_ids=("Q2023-01__P01",),
        per_question=1,
        answer_text="作答：\n问题1：不妥之处：试验员如实记录。",
        point_specs={"Q2023-01__P01": [(["试验员"], 2.0)]},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["label_authority"] == "ai_governed_gold"
    assert row["evidence_span_audit"]["passed"] is True
    assert row["evidence_span_audit"]["repair_count"] == 1
    assert row["gold_point_matches"][0]["evidence_span"] == "作答：\n问题1：不妥之处：试验员如实记录"
    assert manifest["gold_row_count"] == 1


def test_bucket_taxonomist_derives_answer_bucket_from_point_verdicts(tmp_path):
    _, rows, _, output_dir, _ = _run(
        tmp_path,
        _stub_judges(),
        question_ids=("Q2023-01__P01",),
        per_question=1,
        answer_text="这里只写了见证记录，没有覆盖另一个采分点。",
        point_specs={"Q2023-01__P01": [(["见证记录"], 1.0), (["取样"], 1.0)]},
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["sample_bucket"] == "list_incomplete"
    assert row["sample_bucket_provenance"]["basis"] == "point_verdicts"
    assert row["sample_bucket_provenance"]["status_counts"] == {"hit": 1, "miss": 1}

    payload = audit(output_dir / "student_answers.jsonl")
    assert payload["sample_bucket_counts"] == {"list_incomplete": 1}
    assert payload["missing_contract_answer_ids"] == []


def test_point_checkpoint_resume_skips_completed_point_after_interruption(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import run_labeling

    answers_path, manifest_path, _ = _build_slice(
        tmp_path,
        question_ids=("Q2023-01__P01",),
        per_question=1,
        point_specs={"Q2023-01__P01": [(["见证记录"], 1.0), (["取样"], 1.0)]},
    )
    output_dir = tmp_path / "out"
    original_answer = json.loads(answers_path.read_text(encoding="utf-8").splitlines()[0])[
        "student_answer"
    ]

    def fail_on_second_point(point, student_answer, official_anchor):
        if str(point.get("point_id")).endswith("SP02"):
            raise RuntimeError("simulated interruption after first point")
        return _term_judge(point, student_answer, official_anchor)

    with pytest.raises(RuntimeError, match="simulated interruption"):
        run_labeling(
            answers_path=answers_path,
            manifest_path=manifest_path,
            judge_fns={f"stub-judge-{i}": fail_on_second_point for i in range(1, 6)},
            output_dir=output_dir,
        )

    point_checkpoint = output_dir / "point_checkpoint.jsonl"
    assert point_checkpoint.read_text(encoding="utf-8").strip()

    original_first_point_calls = {"n": 0}

    def resume_blind_judge(point, student_answer, official_anchor):
        if (
            str(point.get("point_id")).endswith("SP01")
            and student_answer == original_answer
        ):
            original_first_point_calls["n"] += 1
        return _term_judge(point, student_answer, official_anchor)

    result = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns={
            "stub-judge-1": resume_blind_judge,
            "stub-judge-2": resume_blind_judge,
            "stub-judge-3": resume_blind_judge,
            "stub-judge-4": _term_judge,
            # Force an adversarial downgrade before mutation replay. The test
            # is about point-reconcile checkpointing, not mutation calls.
            "stub-judge-5": _verdict_judge("miss"),
        },
        output_dir=output_dir,
    )

    assert result["manifest"]["row_count"] == 1
    assert original_first_point_calls["n"] == 0


def test_adversarial_mutation_downgrade_is_accepted(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import _mutation_test

    point = _scoring_point("Q2023-01__P01", 1, ["试验员"], 2.0)
    result = _mutation_test(
        [
            {
                "point": point,
                "consolidated_verdict": "hit",
            }
        ],
        "试验员制作见证记录。",
        {"question_id": "Q2023-01__P01"},
        _stub_judges(),
        {"blind_panel": ["stub-judge-1", "stub-judge-2", "stub-judge-3"]},
    )
    subject_swap = next(case for case in result["cases"] if case["mutation_id"] == "subject_swap")
    assert subject_swap["stable"] is False
    assert subject_swap["accepted"] is True
    assert result["passed"] is True


def test_low_fleiss_kappa_triggers_stop_condition(tmp_path):
    judges = {
        "stub-judge-1": _verdict_judge("hit"),
        "stub-judge-2": _verdict_judge("partial"),
        "stub-judge-3": _verdict_judge("miss"),
        "stub-judge-4": _verdict_judge("partial"),
        "stub-judge-5": _verdict_judge("hit"),
    }
    _, _, manifest, _, _ = _run(tmp_path, judges)

    assert manifest["fleiss_kappa"] == -0.5
    assert manifest["stop_condition_triggered"] is True
    assert "fleiss_kappa_below_threshold" in manifest["stop_condition"]["reasons"]


def test_fewer_than_five_judge_models_is_rejected(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import run_labeling

    answers_path, manifest_path, _ = _build_slice(tmp_path)
    with pytest.raises(ValueError, match=">=5"):
        run_labeling(
            answers_path=answers_path,
            manifest_path=manifest_path,
            judge_fns={f"stub-judge-{index}": _term_judge for index in range(1, 5)},
            output_dir=tmp_path / "out",
        )


def test_explicit_live_roles_pin_the_user_mandated_panel(tmp_path):
    """2026-06-11 multipart-fix panel: production-aligned blind + cross-vendor CLI.

    Both weak Qwen variants (qwen-max / qwen-turbo) are dropped — they are not
    the production grading models and were the noisy raters. Blind is the three
    reliable HTTP judges; Opus arbitrates; Codex/GPT prosecutes (per-point, so
    its abstention is monitored via adversarial_prosecutor_abstained).
    """
    from scripts.run_luban_m35_ai_governed_gold_labeling import (
        LIVE_MODEL_ROLES,
        run_labeling,
    )

    live_ids = [*LIVE_MODEL_ROLES["blind_panel"], LIVE_MODEL_ROLES["arbiter"],
                LIVE_MODEL_ROLES["adversarial_prosecutor"]]
    assert sorted(live_ids) == [
        "claude-opus-4-8",
        "deepseek-chat",
        "deepseek-reasoner",
        "gpt-codex",
        "qwen-plus",
    ]
    judge_fns = {model_id: _term_judge for model_id in live_ids}
    answers_path, manifest_path, _ = _build_slice(tmp_path)
    result = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns=judge_fns,
        output_dir=tmp_path / "out-live-roles",
        explicit_roles=LIVE_MODEL_ROLES,
    )
    roles = result["manifest"]["model_roles"]
    assert sorted(roles["blind_panel"]) == ["deepseek-chat", "deepseek-reasoner", "qwen-plus"]
    assert roles["arbiter"] == "claude-opus-4-8"
    assert roles["adversarial_prosecutor"] == "gpt-codex"
    # Both weak Qwen variants dropped from every role.
    assert "qwen-max" not in json.dumps(roles)
    assert "qwen-turbo" not in json.dumps(roles)


def test_explicit_roles_must_cover_exactly_the_judge_set(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import assign_roles

    judge_fns = {f"stub-judge-{index}": _term_judge for index in range(1, 6)}
    with pytest.raises(ValueError, match="cover exactly"):
        assign_roles(
            judge_fns,
            explicit_roles={
                "blind_panel": ["stub-judge-1", "stub-judge-2", "stub-judge-3"],
                "arbiter": "stub-judge-4",
                "adversarial_prosecutor": "not-a-judge",
            },
        )
    with pytest.raises(ValueError, match="reuse"):
        assign_roles(
            judge_fns,
            explicit_roles={
                "blind_panel": ["stub-judge-1", "stub-judge-2", "stub-judge-3"],
                "arbiter": "stub-judge-3",
                "adversarial_prosecutor": "stub-judge-5",
            },
        )


def test_live_adapter_factory_keeps_double_opt_in_and_demands_prerequisites():
    from scripts.run_luban_m35_ai_governed_gold_labeling import build_live_judge_fns

    with pytest.raises(PermissionError):
        build_live_judge_fns(cli_live_flag=False, env={"LUBAN_M35_GOLD_LABELING_LIVE": "1"})
    with pytest.raises(PermissionError):
        build_live_judge_fns(cli_live_flag=True, env={})
    # Explicit env is the complete environment (no os.environ / .env leakage):
    # a missing DASHSCOPE_API_KEY must abort regardless of local key files.
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        build_live_judge_fns(
            cli_live_flag=True,
            env={"LUBAN_M35_GOLD_LABELING_LIVE": "1", "DEEPSEEK_API_KEY": "test-key-not-real"},
        )


def test_cli_blocks_without_double_opt_in_and_never_labels(tmp_path):
    answers_path, manifest_path, _ = _build_slice(tmp_path)
    output_dir = tmp_path / "cli-out"
    env = {key: value for key, value in os.environ.items() if key != "LUBAN_M35_GOLD_LABELING_LIVE"}

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--answers",
            str(answers_path),
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--live",
        ],
        check=True,
        cwd=REPO,
        env=env,
    )

    report = json.loads((output_dir / "live_gate_report.json").read_text(encoding="utf-8"))
    assert report["labeling_run"] is False
    assert report["live"]["status"] == "blocked_live_double_opt_in_required"
    assert not (output_dir / "student_answers.jsonl").exists()


def test_cli_with_double_opt_in_but_missing_prerequisites_blocks_loudly(tmp_path):
    answers_path, manifest_path, _ = _build_slice(tmp_path)
    output_dir = tmp_path / "cli-out-live"
    env = {
        **os.environ,
        "LUBAN_M35_GOLD_LABELING_LIVE": "1",
        # Empty keys override any .env fallback; a bare PATH hides the CLI
        # judges, so prerequisites fail and no provider is ever called.
        "DEEPSEEK_API_KEY": "",
        "DASHSCOPE_API_KEY": "",
        "PATH": "/usr/bin:/bin",
    }

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--answers",
            str(answers_path),
            "--manifest",
            str(manifest_path),
            "--output-dir",
            str(output_dir),
            "--live",
        ],
        check=False,
        cwd=REPO,
        env=env,
    )

    assert proc.returncode == 2
    report = json.loads((output_dir / "live_gate_report.json").read_text(encoding="utf-8"))
    assert report["labeling_run"] is False
    assert report["live"]["status"] == "blocked_live_prerequisites_missing"
    assert not (output_dir / "student_answers.jsonl").exists()


def _abstain_judge(point: dict, student_answer: str, official_anchor: dict) -> dict:
    return {
        "verdict": "abstain",
        "evidence_span": "",
        "confidence": 0.0,
        "abstain_reason": "stub_timeout",
    }


def test_single_panel_abstention_is_recorded_and_never_counts_as_accept(tmp_path):
    judges = {
        "stub-judge-1": _term_judge,
        "stub-judge-2": _abstain_judge,
        "stub-judge-3": _term_judge,
        "stub-judge-4": _term_judge,
        "stub-judge-5": _term_judge,
    }
    _, rows, manifest, _, _ = _run(tmp_path, judges)

    for row in rows:
        # Remaining 2 panel votes + arbiter = 3 independent accepts -> still gold.
        assert row["label_authority"] == "ai_governed_gold"
        votes = {vote["model_id"]: vote["verdict"] for vote in row["ai_governed_gold"]["blind_model_votes"]}
        assert votes["stub-judge-2"] == "abstain"
        accepts = [model for model, verdict in votes.items() if verdict == "accept"]
        assert sorted(accepts) == ["stub-judge-1", "stub-judge-3", "stub-judge-4"]
        assert validate_ai_governed_gold_protocol(row["ai_governed_gold"])["valid"] is True
    # Abstaining points carry incomplete panels and are excluded from kappa.
    assert manifest["fleiss_kappa"] is None
    assert manifest["kappa_item_count"] == 0
    assert manifest["kappa_items_excluded_for_abstention"] > 0


def test_all_panel_abstain_leaves_arbiter_alone_and_downgrades(tmp_path):
    judges = {
        "stub-judge-1": _abstain_judge,
        "stub-judge-2": _abstain_judge,
        "stub-judge-3": _abstain_judge,
        "stub-judge-4": _term_judge,
        "stub-judge-5": _term_judge,
    }
    _, rows, manifest, _, _ = _run(tmp_path, judges)

    for row in rows:
        assert row["label_authority"] == "ai_council_directional"
        assert "insufficient_independent_blind_accepts" in row["downgrade_reasons"]
        for provenance in row["point_label_provenance"]:
            assert provenance["route"] == "arbitration"
    assert manifest["gold_row_count"] == 0


def test_arbiter_abstention_on_split_yields_unadjudicated_downgrade(tmp_path):
    judges = {
        "stub-judge-1": _verdict_judge("hit"),
        "stub-judge-2": _verdict_judge("partial"),
        "stub-judge-3": _verdict_judge("miss"),
        "stub-judge-4": _abstain_judge,
        "stub-judge-5": _term_judge,
    }
    _, rows, manifest, _, _ = _run(tmp_path, judges)

    for row in rows:
        assert row["label_authority"] == "ai_council_directional"
        assert "unadjudicated_point_due_to_abstention" in row["downgrade_reasons"]
        for provenance in row["point_label_provenance"]:
            assert provenance["route"] == "arbitration_unresolved"
            assert provenance["consolidated_verdict"] == "unadjudicated"
        for match in row["gold_point_matches"]:
            assert match["status"] == "unadjudicated"
            assert match["awarded_score"] == 0.0
    assert manifest["gold_row_count"] == 0


def test_prosecutor_abstention_downgrades_row(tmp_path):
    judges = {
        "stub-judge-1": _term_judge,
        "stub-judge-2": _term_judge,
        "stub-judge-3": _term_judge,
        "stub-judge-4": _term_judge,
        "stub-judge-5": _abstain_judge,
    }
    _, rows, manifest, _, _ = _run(tmp_path, judges)

    for row in rows:
        assert row["label_authority"] == "ai_council_directional"
        assert "adversarial_prosecutor_abstained" in row["downgrade_reasons"]
        assert row["adversarial_review"]["abstained_point_count"] >= 1
    assert manifest["gold_row_count"] == 0


def test_manifest_provider_call_patch_uses_uncached_judge_calls():
    from scripts.run_luban_m35_ai_governed_gold_labeling import (
        _patch_manifest_provider_calls,
    )

    manifest = {"safety": {"db_write_count": 0, "remote_write_count": 0, "provider_call_count": 0}}
    snapshot = {
        "deepseek-chat": {"calls": 10, "cached_hits": 4},
        "gpt-codex": {"calls": 5, "cached_hits": 0},
    }
    patched = _patch_manifest_provider_calls(manifest, snapshot)
    assert patched["safety"]["provider_call_count"] == 11
    # Immutability: the input manifest is never mutated.
    assert manifest["safety"]["provider_call_count"] == 0


def test_question_ids_filter_and_row_workers_parallelism(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import run_labeling

    answers_path, manifest_path, _ = _build_slice(tmp_path, per_question=2)
    result = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns=_stub_judges(),
        output_dir=tmp_path / "out-filtered",
        question_ids=("Q2023-01__P02",),
        row_workers=3,
    )
    rows = result["rows"]
    assert len(rows) == 2
    assert {row["question_id"] for row in rows} == {"Q2023-01__P02"}
    assert result["manifest"]["gold_row_count"] == 2


def test_pipeline_source_has_no_network_imports():
    source = SCRIPT.read_text(encoding="utf-8")
    for banned in ("requests", "httpx", "urllib", "aiohttp", "websocket", "http.client", "socket"):
        assert banned not in source, f"network-capable token {banned!r} found in pipeline source"


def test_checkpoint_resume_skips_completed_rows(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import run_labeling

    answers_path, manifest_path, _ = _build_slice(tmp_path)
    output_dir = tmp_path / "out"

    calls = {"n": 0}

    def counting_judge(point, student_answer, official_anchor):
        calls["n"] += 1
        return _term_judge(point, student_answer, official_anchor)

    first = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns={f"stub-judge-{i}": counting_judge for i in range(1, 6)},
        output_dir=output_dir,
    )
    assert calls["n"] > 0
    assert (output_dir / "row_checkpoint.jsonl").read_text(encoding="utf-8").strip()

    # Identical config -> every row resumes from the checkpoint, so a judge that
    # would explode is never invoked, and the manifest is reproduced.
    def exploding_judge(point, student_answer, official_anchor):
        raise AssertionError("resume must not re-judge a checkpointed row")

    second = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns={f"stub-judge-{i}": exploding_judge for i in range(1, 6)},
        output_dir=output_dir,
    )
    assert second["manifest"]["row_count"] == first["manifest"]["row_count"]
    assert second["manifest"]["gold_row_count"] == first["manifest"]["gold_row_count"]


def test_checkpoint_config_change_does_not_resume_stale_rows(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import run_labeling

    answers_path, manifest_path, _ = _build_slice(tmp_path)
    output_dir = tmp_path / "out"

    run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns=_stub_judges(),
        output_dir=output_dir,
    )

    # A different panel (new model ids) changes the fingerprint; the stale
    # checkpoint must be ignored so incompatible rows are never silently reused.
    calls = {"n": 0}

    def counting_judge(point, student_answer, official_anchor):
        calls["n"] += 1
        return _term_judge(point, student_answer, official_anchor)

    run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns={f"other-judge-{i}": counting_judge for i in range(1, 6)},
        output_dir=output_dir,
    )
    assert calls["n"] > 0


def test_checkpoint_tolerates_torn_final_line(tmp_path):
    from scripts.run_luban_m35_ai_governed_gold_labeling import run_labeling

    answers_path, manifest_path, _ = _build_slice(tmp_path)
    output_dir = tmp_path / "out"

    first = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns=_stub_judges(),
        output_dir=output_dir,
    )
    checkpoint = output_dir / "row_checkpoint.jsonl"
    checkpoint.write_text(
        checkpoint.read_text(encoding="utf-8") + '{"answer_id": "x", "outcome": {tru',
        encoding="utf-8",
    )

    def exploding_judge(point, student_answer, official_anchor):
        raise AssertionError("intact checkpointed rows must still resume")

    second = run_labeling(
        answers_path=answers_path,
        manifest_path=manifest_path,
        judge_fns={f"stub-judge-{i}": exploding_judge for i in range(1, 6)},
        output_dir=output_dir,
    )
    assert second["manifest"]["row_count"] == first["manifest"]["row_count"]
