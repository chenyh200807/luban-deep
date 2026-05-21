from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


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
