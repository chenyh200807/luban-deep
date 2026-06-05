from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_luban_policy_queue import build_policy_queue
from scripts.build_luban_qwen_fewshot import build as build_fewshot

REPO = Path(__file__).resolve().parents[2]
PQ_DIR = REPO / "artifacts/luban_consensus_gold/policy_queue_20260603"


def _fixtures(tmp: Path):
    packet = tmp / "packet.json"
    packet.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "case_id": "QX", "student_id": "S1", "point_id": "P1",
                        "stem": "题干", "official_answer": "甲、乙、丙",
                        "student_answer": "我写了甲和乙",
                        "scoring_point": {"label": "列举型:甲/乙/丙"},
                        "model_judgments": {
                            "gpt": {"hit": "hit", "score": 1}, "opus": {"hit": "hit", "score": 1},
                            "deepseek": {"hit": "hit", "score": 1}, "qwen37": {"hit": "partial", "score": 0.66},
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    unresolved = tmp / "unresolved.csv"
    with unresolved.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "student_id", "point_id", "policy_type", "dissent_reason"])
        w.writerow(["QX", "S1", "P1", "list_rule", "majority hit vs stricter qwen37=partial"])
    return unresolved, packet


def test_policy_queue_maps_unresolved_back_to_packet_context(tmp_path: Path) -> None:
    unresolved, packet = _fixtures(tmp_path)
    cases = build_policy_queue(unresolved_csv=unresolved, packet_path=packet, qwen_disagree_csv=None, deepseek_disagree_csv=None)
    assert len(cases) == 1
    c = cases[0]
    assert c["scoring_point"] == "列举型:甲/乙/丙"
    assert c["student_answer"] == "我写了甲和乙"
    assert c["conflict_axis"] == "list_rule_denominator"
    assert "model_judgments" in c and "qwen37" in c["model_judgments"]


def test_policy_queue_stops_on_packet_mismatch(tmp_path: Path) -> None:
    _, packet = _fixtures(tmp_path)
    bad = tmp_path / "bad.csv"
    with bad.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "student_id", "point_id", "policy_type", "dissent_reason"])
        w.writerow(["NOPE", "S9", "P9", "list_rule", "x"])
    with pytest.raises(SystemExit):
        build_policy_queue(unresolved_csv=bad, packet_path=packet, qwen_disagree_csv=None, deepseek_disagree_csv=None)


def test_policy_queue_does_not_read_human_or_ledger_or_artifact(tmp_path: Path) -> None:
    unresolved, packet = _fixtures(tmp_path)
    cases = build_policy_queue(unresolved_csv=unresolved, packet_path=packet, qwen_disagree_csv=None, deepseek_disagree_csv=None)
    blob = json.dumps(cases, ensure_ascii=False)
    for forbidden in ("human_hit", "human_score", "human_note", "ground_truth_ledger", "ledger_point_rows", "artifact_first", "blind_grade"):
        assert forbidden not in blob


def test_fewshot_examples_never_fabricate_gold(tmp_path: Path) -> None:
    cases = [{"case_id": "QX", "student_id": "S1", "point_id": "P1", "conflict_axis": "list_rule_denominator", "scoring_point": "x", "student_answer": "y"}]
    ex = build_fewshot(cases)
    assert ex and all(e["correct_decision"] == "needs_policy_review" for e in ex)


@pytest.mark.skipif(not (PQ_DIR / "typed_policy_rules.json").exists(), reason="policy queue artifacts not generated")
def test_typed_policy_rules_schema() -> None:
    rules = json.loads((PQ_DIR / "typed_policy_rules.json").read_text(encoding="utf-8"))["rules"]
    assert len(rules) >= 5
    for r in rules:
        for field in ("rule_id", "policy_type", "decision_rule", "examples"):
            assert field in r
        assert r["runtime_status"] == "shadow_only"


@pytest.mark.skipif(not (PQ_DIR / "qwen_fewshot_policy_prompt.md").exists(), reason="prompt not generated")
def test_qwen_prompt_has_review_output_fields() -> None:
    prompt = (PQ_DIR / "qwen_fewshot_policy_prompt.md").read_text(encoding="utf-8")
    assert "high_risk" in prompt and "needs_policy_review" in prompt
