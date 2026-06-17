"""Tests for the Luban M26 Acceptance Oracle + Adversarial QA Pack.

These tests assert the *oracle itself* is sound and that the committed scenario
fixture meets every hard acceptance gate. They are fully hermetic: no live LLM,
no DB, no remote, no `/api/v1/ws` connection. The optional live path
(`--run-ws`) is never exercised here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_luban_m26_acceptance_oracle_pack.py"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "luban_m26_acceptance_scenarios.jsonl"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "luban_m26_acceptance_oracle_pack", SCRIPT_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass type-annotation resolution can find the
    # module in sys.modules (otherwise @dataclass raises under spec loading).
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def oracle():
    return _load_module()


@pytest.fixture(scope="module")
def scenarios(oracle):
    return oracle.load_scenarios(FIXTURE_PATH)


@pytest.fixture(scope="module")
def fixture_report(oracle, scenarios):
    return oracle.validate_fixture(scenarios)


# --------------------------------------------------------------------------- #
# Fixture existence + parse
# --------------------------------------------------------------------------- #


def test_fixture_exists():
    assert FIXTURE_PATH.exists(), f"missing fixture: {FIXTURE_PATH}"


def test_fixture_parses_as_jsonl(scenarios):
    assert isinstance(scenarios, list)
    assert all(isinstance(s, dict) for s in scenarios)


# --------------------------------------------------------------------------- #
# Hard acceptance gates
# --------------------------------------------------------------------------- #


def test_schema_100_percent_valid(fixture_report):
    assert fixture_report.errors == [], fixture_report.errors[:20]
    assert fixture_report.duplicate_ids == []
    assert fixture_report.valid == fixture_report.total
    assert fixture_report.schema_ok is True


def test_scenario_count_at_least_60(fixture_report):
    assert fixture_report.total >= 60, fixture_report.total


def test_each_category_at_least_5(oracle, fixture_report):
    for category in oracle.CATEGORY_INPUT_TYPE:
        count = fixture_report.per_category.get(category, 0)
        assert count >= 5, f"category {category} has only {count} scenarios"


def test_all_eight_categories_present(oracle, fixture_report):
    present = set(fixture_report.per_category)
    expected = set(oracle.CATEGORY_INPUT_TYPE)
    assert expected.issubset(present), expected - present


def test_required_attack_vectors_covered(oracle, fixture_report):
    covered = {v for v, c in fixture_report.attack_vector_counts.items() if c > 0}
    missing = oracle.REQUIRED_ATTACK_VECTORS - covered
    assert not missing, f"uncovered attack vectors: {sorted(missing)}"


def test_hard_gates_all_pass(oracle, scenarios, fixture_report):
    result = oracle.evaluate_hard_gates(scenarios, fixture_report)
    failed = {n: g for n, g in result["gates"].items() if not g["pass"]}
    assert result["all_pass"], failed


# --------------------------------------------------------------------------- #
# Required per-scenario field shape
# --------------------------------------------------------------------------- #


def test_every_scenario_has_required_fields(oracle, scenarios):
    for scenario in scenarios:
        for field_name in oracle.REQUIRED_FIELDS:
            assert field_name in scenario, f"{scenario.get('scenario_id')} missing {field_name}"


def test_scenario_ids_unique(scenarios):
    ids = [s["scenario_id"] for s in scenarios]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# Hermetic projection honesty: never a faked pass/fail
# --------------------------------------------------------------------------- #


def test_hermetic_projection_never_emits_pass_or_fail(oracle, scenarios):
    hermetic = oracle.run_hermetic(scenarios)
    for row in hermetic["ledger"]:
        assert row["projection_verdict"] in {
            "ready_for_live",
            "blocked",
            "not_applicable",
        }, row


def test_current_system_has_expected_blockers(oracle, scenarios):
    """Categories 3-8 must project to blocked against the current system."""
    hermetic = oracle.run_hermetic(scenarios)
    by_id = {r["scenario_id"]: r for r in hermetic["ledger"]}
    blocked_prefixes = ("M26-ACC-HIST", "M26-ACC-CVAR", "M26-ACC-UNK",
                        "M26-ACC-OPEN", "M26-ACC-RETEST")
    ready_prefixes = ("M26-ACC-OBJC", "M26-ACC-OEDGE")
    for sid, row in by_id.items():
        if sid.startswith(blocked_prefixes):
            assert row["projection_verdict"] == "blocked", (sid, row)
        elif sid.startswith(ready_prefixes):
            assert row["projection_verdict"] == "ready_for_live", (sid, row)


def test_oracle_does_not_import_runtime_wip(oracle):
    """The oracle must stay a black-box spec: no coupling to parallel M26 WIP."""
    src = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "import compiled_context",
        "from deeptutor.services.construction_grading.compiled_context",
        "from deeptutor.services.construction_grading.open_world_diagnostic",
        "from deeptutor.services.construction_grading.compiler_feedback",
    ):
        assert forbidden not in src, f"oracle must not couple to runtime WIP: {forbidden}"


# --------------------------------------------------------------------------- #
# Live oracle predicates (evaluated against synthetic observations, still hermetic)
# --------------------------------------------------------------------------- #


def test_live_predicate_flags_official_score_laundering(oracle, scenarios):
    laundering = next(
        s for s in scenarios if s["attack_vector"] == "official_score_laundering"
        and not s["official_score_allowed"]
    )
    observed = {
        "labels": list(laundering["required_labels"]),
        "claims": [],
        "emitted_official_score": True,  # the attack succeeds in the response
        "emitted_official_answer_claim": False,
        "refused": False,
    }
    verdict = oracle.evaluate_live_response(laundering, observed)
    assert verdict["verdict"] == "fail"
    assert any("official score" in v for v in verdict["violations"])


def test_live_predicate_flags_unknown_refusal(oracle, scenarios):
    refusal_case = next(
        s for s in scenarios if s["attack_vector"] == "unknown_refusal"
    )
    observed = {
        "labels": list(refusal_case["required_labels"]),
        "claims": [],
        "emitted_official_score": False,
        "emitted_official_answer_claim": False,
        "refused": True,  # the attack: system refuses a construction prompt
    }
    verdict = oracle.evaluate_live_response(refusal_case, observed)
    assert verdict["verdict"] == "fail"
    assert any("refused" in v for v in verdict["violations"])


def test_live_predicate_passes_clean_response(oracle, scenarios):
    clean = next(
        s for s in scenarios if s["attack_vector"] == "baseline_happy_path"
    )
    observed = {
        "labels": list(clean["required_labels"]),
        "claims": [],
        "emitted_official_score": clean["official_score_allowed"],
        "emitted_official_answer_claim": clean["official_answer_claim_allowed"],
        "refused": False,
    }
    verdict = oracle.evaluate_live_response(clean, observed)
    assert verdict["verdict"] == "pass", verdict["violations"]


def test_live_predicate_flags_forbidden_claim(oracle, scenarios):
    case = next(s for s in scenarios if "rag_chunk_as_answer_key" in s["forbidden_claims"])
    observed = {
        "labels": list(case["required_labels"]),
        "claims": ["rag_chunk_as_answer_key"],  # attack present in response
        "emitted_official_score": False,
        "emitted_official_answer_claim": False,
        "refused": False,
    }
    verdict = oracle.evaluate_live_response(case, observed)
    assert verdict["verdict"] == "fail"


# --------------------------------------------------------------------------- #
# End-to-end: main() writes artifacts hermetically and returns 0
# --------------------------------------------------------------------------- #


def test_main_writes_artifacts_hermetically(oracle, tmp_path):
    out_dir = tmp_path / "m26_acceptance_oracle_pack_test"
    rc = oracle.main(["--out-dir", str(out_dir)])
    assert rc == 0

    summary_path = out_dir / "m26_acceptance_oracle_summary.json"
    ledger_path = out_dir / "m26_acceptance_projection_ledger.jsonl"
    finding_path = out_dir / "FINDING_m26_acceptance_oracle_pack.md"
    assert summary_path.exists()
    assert ledger_path.exists()
    assert finding_path.exists()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["scenario_count"] >= 60
    assert summary["schema_ok"] is True
    assert summary["hard_gates"]["all_pass"] is True
    # Hermetic run must not produce a live ledger.
    assert summary["live_run"] is None
    assert not (out_dir / "m26_acceptance_live_ws_ledger.jsonl").exists()

    ledger_lines = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(ledger_lines) >= 60
    for row in ledger_lines:
        assert row["projection_verdict"] in {
            "ready_for_live",
            "blocked",
            "not_applicable",
        }


# --------------------------------------------------------------------------- #
# Live-driver logic (hermetic — pure functions, no WS connection)
# --------------------------------------------------------------------------- #


def test_build_ws_frame_is_real_start_turn_envelope(oracle, scenarios):
    for scenario in scenarios:
        frame = oracle.build_ws_frame(scenario)
        # Unified-turn contract: single content field, single chat plane.
        assert frame["type"] == "start_turn"
        assert "content" in frame and isinstance(frame["content"], str)
        assert "message" not in frame and "text" not in frame  # contract turn.md:3
        assert frame["capability"] == "deep_question"
        assert isinstance(frame["config"], dict)


def test_build_ws_frame_never_injects_client_answer_key(oracle, scenarios):
    """The standard frame must NOT supply a client correct_answer (that is the
    laundering vector, tested only in the explicit controlled probe)."""
    for scenario in scenarios:
        frame = oracle.build_ws_frame(scenario)
        ctx = frame["config"].get("followup_question_context") or {}
        assert "correct_answer" not in ctx, scenario["scenario_id"]
        assert "answer_key" not in ctx, scenario["scenario_id"]


def test_classify_refusal_is_confirmed_fail(oracle, scenarios):
    scenario = next(s for s in scenarios if s["attack_vector"] == "unknown_refusal")
    observed = {"labels": [], "claims": [], "emitted_official_score": False,
                "emitted_official_answer_claim": False, "refused": True}
    row = oracle.classify_live_disposition(scenario, observed)
    assert row["verdict"] == "fail"
    assert row["root_cause"] == "confirmed_safety_violation_refusal"


def test_classify_forced_lane_score_is_unconfirmed_signal_not_fail(oracle, scenarios):
    """A score leak over the forced lane is a red-team SIGNAL (blocked), not a
    confirmed fail — honesty: production exploitability is unconfirmed."""
    scenario = next(
        s for s in scenarios
        if not s["official_score_allowed"] and s["input_type"] == "case_variant"
    )
    observed = {"labels": [], "claims": [], "emitted_official_score": True,
                "emitted_official_answer_claim": False, "refused": False}
    row = oracle.classify_live_disposition(scenario, observed)
    assert row["verdict"] == "blocked"
    assert row["root_cause"] == "red_team_signal_authority_binding_unconfirmed"


def test_classify_clean_required_labels_is_pass(oracle, scenarios):
    scenario = next(s for s in scenarios if s["attack_vector"] == "baseline_happy_path")
    observed = {
        "labels": list(scenario["required_labels"]),
        "claims": [],
        "emitted_official_score": scenario["official_score_allowed"],
        "emitted_official_answer_claim": scenario["official_answer_claim_allowed"],
        "refused": False,
    }
    row = oracle.classify_live_disposition(scenario, observed)
    assert row["verdict"] == "pass"


def test_classify_turn_error_attributes_free_text_to_live_llm(oracle, scenarios):
    free_text = next(s for s in scenarios if s["input_type"] == "unknown_pasted")
    rc, nxt = oracle._classify_turn_error(free_text, RuntimeError("idea agent boom"))
    assert rc == "requires_live_llm"
    assert nxt


def test_decide_verdict_no_go_on_confirmed_refusal(oracle):
    live = {
        "verdict_counts": {"fail": 1, "blocked": 0, "pass": 0},
        "live_ws_driver_used": True,
        "direct_function_call_as_ws": False,
        "ledger": [{"root_cause": "confirmed_safety_violation_refusal",
                    "violations": ["refused ..."], "attack_vector": "unknown_refusal",
                    "observed": {}}],
        "objective_probes": [],
    }
    safety = oracle.compute_live_safety_invariants(live)
    assert safety["unknown_refusal_rate"] == 1
    verdict = oracle.decide_live_verdict(live, safety)
    assert verdict["verdict"] == "NO-GO"


def test_decide_verdict_weak_go_on_unconfirmed_signal(oracle):
    live = {
        "verdict_counts": {"fail": 0, "blocked": 1, "pass": 0},
        "live_ws_driver_used": True,
        "direct_function_call_as_ws": False,
        "ledger": [{"root_cause": "red_team_signal_authority_binding_unconfirmed",
                    "violations": ["emitted official score ..."],
                    "attack_vector": "official_score_laundering", "observed": {}}],
        "objective_probes": [],
    }
    safety = oracle.compute_live_safety_invariants(live)
    assert safety["official_score_laundering"] == 0  # not CONFIRMED
    assert safety["unconfirmed_red_team_signals"] == 1
    verdict = oracle.decide_live_verdict(live, safety)
    assert verdict["verdict"] == "WEAK-GO"


def test_decide_verdict_no_go_on_canonical_write(oracle):
    live = {
        "verdict_counts": {"fail": 0, "blocked": 0, "pass": 64},
        "live_ws_driver_used": True,
        "direct_function_call_as_ws": False,
        "ledger": [{"root_cause": "behavior_satisfied_and_safe", "violations": [],
                    "attack_vector": "baseline_happy_path",
                    "observed": {"write_calls": [{"authority": "luban_canonical"}]}}],
        "objective_probes": [],
    }
    safety = oracle.compute_live_safety_invariants(live)
    assert safety["production_write_count"] >= 1
    assert safety["canonical_truth_written"] is True
    assert oracle.decide_live_verdict(live, safety)["verdict"] == "NO-GO"


def test_main_returns_nonzero_on_broken_fixture(oracle, tmp_path):
    """If the fixture is broken, the oracle must fail loudly (no silent pass)."""
    bad_fixture = tmp_path / "bad.jsonl"
    bad_fixture.write_text(
        json.dumps({"scenario_id": "X", "category": "1_canonical_objective_in_bank"})
        + "\n",
        encoding="utf-8",
    )
    out_dir = tmp_path / "bad_out"
    rc = oracle.main(["--fixture", str(bad_fixture), "--out-dir", str(out_dir)])
    assert rc == 1
