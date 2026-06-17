from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _duplicate_top_level_yaml_keys(path: Path) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        if not key:
            continue
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def test_contract_indexes_do_not_redeclare_top_level_keys() -> None:
    for path in (
        ROOT / "contracts" / "index.yaml",
        ROOT / "deeptutor" / "contracts" / "index.yaml",
    ):
        duplicates = _duplicate_top_level_yaml_keys(path)
        assert duplicates == [], f"{path.relative_to(ROOT)} duplicate top-level keys: {duplicates}"


def test_repo_and_package_contract_indexes_match() -> None:
    repo_index = _load_yaml(ROOT / "contracts" / "index.yaml")
    package_index = _load_yaml(ROOT / "deeptutor" / "contracts" / "index.yaml")

    assert repo_index == package_index


def test_learning_report_contract_surface_registered() -> None:
    index = _load_yaml(ROOT / "contracts" / "index.yaml")
    turn = index["domains"]["turn"]

    assert "contracts/learning-report.md" in turn["contract_files"]
    assert "contracts/learning-report.md" in turn["schema_files"]
    assert "deeptutor/services/learner_state/attempt_refs.py" in turn["protected_patterns"]
    assert "deeptutor/services/learner_state/attempt_detail_read_model.py" in turn["protected_patterns"]
    assert "deeptutor/services/learner_state/mistake_book.py" in turn["protected_patterns"]
    assert "deeptutor/services/learner_state/training_intent.py" in turn["protected_patterns"]
    assert "deeptutor/services/learner_state/home_personalization.py" in turn["protected_patterns"]


def test_learning_report_contract_keeps_conversation_evidence_inside_learning_evidence() -> None:
    contract = (ROOT / "contracts" / "learning-report.md").read_text(encoding="utf-8")

    assert 'event_type="learning_evidence"' in contract
    assert 'memory_kind="learning_evidence"' in contract
    assert 'payload.evidence_source="conversation_synthesis"' in contract
    assert "`conversation_learning_evidence`" in contract
    for signal_type in (
        "answer_explanation",
        "concept_explain",
        "mistake_explain",
        "still_confused",
        "home_prompt_clicked",
    ):
        assert f"`{signal_type}`" in contract


def test_learning_state_inference_surface_registered_in_index_yaml() -> None:
    """Batch A Task 1: register learning_state_inference surface (top-level
    YAML block recording authority, allowed event types, projections, and
    explicit forbidden anti-patterns)."""
    index = _load_yaml(ROOT / "contracts" / "index.yaml")
    block = index.get("learning_state_inference")

    assert isinstance(block, dict), "learning_state_inference top-level block must exist"
    assert (
        "learner_memory_events.learning_evidence" in block["authority"]
        and "learning_synthesis" in block["authority"]
        and "learning_report_read_model" in block["authority"]
    ), block["authority"]
    assert block["allowed_event_type"] == "learning_evidence"

    sources = set(block["allowed_evidence_sources"])
    assert {"construction_grading", "conversation_synthesis"}.issubset(sources)

    projections = set(block["projections"])
    assert {
        "knowledge_state",
        "ability_state",
        "behavior_state",
        "prescription",
        "scoring_point_map",
    }.issubset(projections)

    forbidden = " | ".join(block["forbidden"])
    assert "second learner memory" in forbidden.lower()
    assert "frontend mastery derivation" in forbidden.lower()
    assert "recommendation authority" in forbidden.lower()


def test_learning_state_inference_md_registered_in_learner_state_domain() -> None:
    """The narrative contract doc must be registered so the contract guard
    fails when learner_state code changes without updating it."""
    index = _load_yaml(ROOT / "contracts" / "index.yaml")
    learner_state = index["domains"]["learner_state"]

    assert "docs/contracts/learning-state-inference.md" in learner_state["contract_files"]


def test_learning_state_inference_md_exists_and_names_required_sections() -> None:
    contract = (ROOT / "docs" / "contracts" / "learning-state-inference.md").read_text(encoding="utf-8")

    # Hard product gates that this contract pins.
    assert "learner_memory_events.learning_evidence" in contract
    assert "training_intent" in contract
    assert "scoring_point_map" in contract
    assert "rubric_pending" in contract
    # Explicit forbidden patterns must appear so future agents can grep.
    assert "second learner memory" in contract.lower()
    assert "frontend mastery derivation" in contract.lower()
