"""M25-A: objective answer-key compiler — determinism, signing, tamper/fail-closed, seed-only."""
from __future__ import annotations

import copy

from deeptutor.services.construction_grading import objective_answer_key_compiler as C


def _seed():
    return [
        {"question_id": "q2", "question_type": "multiple_choice",
         "stem": "s2", "options": ["A. a", "B. b", "C. c"], "official_answer": "CAB",
         "source_refs": [{"ref": "x"}], "provenance": "synthetic_seed"},
        {"question_id": "q1", "question_type": "single_choice",
         "stem": "s1", "options": ["A. a", "B. b"], "official_answer": "a",
         "source_refs": [], "provenance": "synthetic_seed"},
        {"question_id": "q3", "question_type": "true_false",
         "stem": "s3", "options": ["对", "错"], "official_answer": "错"},
    ]


def test_compile_is_deterministic():
    b1 = C.compile_objective_answer_keys(_seed())
    b2 = C.compile_objective_answer_keys(_seed())
    assert b1["manifest"]["content_hash"] == b2["manifest"]["content_hash"]
    assert b1["manifest"]["signature"] == b2["manifest"]["signature"]


def test_multi_select_answer_key_is_order_independent():
    b = C.compile_objective_answer_keys(_seed())
    rec = {r["question_id"]: r for r in b["records"]}
    # "CAB" -> sorted unique letters "ABC"
    assert rec["q2"]["answer_key"] == "ABC"
    # single "a" -> "A"
    assert rec["q1"]["answer_key"] == "A"
    # true_false "错" -> "F"
    assert rec["q3"]["answer_key"] == "F"


def test_bundle_verifies_clean():
    b = C.compile_objective_answer_keys(_seed())
    assert C.verify_objective_bundle(b) is True


def test_tampered_answer_key_fails_closed():
    b = C.compile_objective_answer_keys(_seed())
    tampered = copy.deepcopy(b)
    tampered["records"][0]["answer_key"] = "ZZZ"  # flip authority
    assert C.verify_objective_bundle(tampered) is False


def test_tampered_manifest_signature_fails_closed():
    b = C.compile_objective_answer_keys(_seed())
    tampered = copy.deepcopy(b)
    tampered["manifest"]["signature"] = "0" * 64
    assert C.verify_objective_bundle(tampered) is False


def test_official_answer_is_seed_only_never_release():
    b = C.compile_objective_answer_keys(_seed())
    assert b["manifest"]["status"] == "candidate"
    assert b["manifest"]["release_authority"] is None
    assert b["manifest"]["official_answer_role"] == "seed_only"
    for rec in b["records"]:
        assert rec["status"] == "candidate"


def test_namespace_separate_from_case_registry():
    b = C.compile_objective_answer_keys(_seed())
    assert b["manifest"]["namespace"] == "objective_answer_key"
    assert b["manifest"]["separate_from_case_registry"] is True


def test_clean_checkout_tracked_seed_loads_and_compiles():
    # Must NOT depend on gitignored artifacts — reads the tracked synthetic seed.
    rows = C.load_objective_seed()
    assert len(rows) >= 3
    b = C.compile_objective_answer_keys(rows)
    assert C.verify_objective_bundle(b) is True
    assert all(r["synthetic_example"] for r in b["records"])  # tracked seed is clearly synthetic


def test_no_llm_dependency_in_module():
    import inspect
    src = inspect.getsource(C)
    for banned in ("anthropic", "openai", "dashscope", "deepseek", "qwen", "httpx.post", "requests.post"):
        assert banned not in src.lower()
