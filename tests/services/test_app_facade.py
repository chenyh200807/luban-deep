"""Tests for the public DeepTutor application facade."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deeptutor.app import DeepTutorApp
from deeptutor.contracts import get_contract_index_candidates, get_contract_index_path, load_contract_index


class _FakeNotebookManager:
    def __init__(self) -> None:
        self.add_calls = []
        self.update_calls = []
        self.record = {
            "id": "rec-1",
            "type": "co_writer",
            "title": "Old",
            "output": "Old body",
            "metadata": {"source": "co_writer"},
        }

    def add_record(self, **kwargs):  # noqa: ANN003
        self.add_calls.append(kwargs)
        return {"record": {"id": "rec-new", **kwargs}, "added_to_notebooks": kwargs["notebook_ids"]}

    def get_record(self, notebook_id: str, record_id: str):  # noqa: ANN001
        if notebook_id == "nb1" and record_id == "rec-1":
            return dict(self.record)
        return None

    def update_record(self, notebook_id: str, record_id: str, **kwargs):  # noqa: ANN003
        self.update_calls.append((notebook_id, record_id, kwargs))
        return {"id": record_id, **kwargs}


def test_import_markdown_into_notebook_uses_co_writer_semantics(tmp_path: Path) -> None:
    markdown = tmp_path / "lesson.md"
    markdown.write_text("# Vectors\n\nSome content.", encoding="utf-8")

    app = DeepTutorApp()
    fake_manager = _FakeNotebookManager()
    app.notebooks = fake_manager

    result = app.import_markdown_into_notebook("nb1", markdown)

    assert result["record"]["id"] == "rec-new"
    add_call = fake_manager.add_calls[0]
    assert add_call["record_type"] == "co_writer"
    assert add_call["title"] == "Vectors"
    assert add_call["user_query"] == "Vectors"
    assert add_call["output"] == "# Vectors\n\nSome content."
    assert add_call["metadata"]["saved_via"] == "cli"
    assert add_call["metadata"]["source_path"] == str(markdown.resolve())


def test_replace_markdown_record_updates_existing_co_writer_record(tmp_path: Path) -> None:
    markdown = tmp_path / "updated.md"
    markdown.write_text("# Matrices\n\nUpdated body.", encoding="utf-8")

    app = DeepTutorApp()
    fake_manager = _FakeNotebookManager()
    app.notebooks = fake_manager

    result = app.replace_markdown_record("nb1", "rec-1", markdown)

    assert result["id"] == "rec-1"
    notebook_id, record_id, update_call = fake_manager.update_calls[0]
    assert notebook_id == "nb1"
    assert record_id == "rec-1"
    assert update_call["title"] == "Matrices"
    assert update_call["user_query"] == "Matrices"
    assert update_call["output"] == "# Matrices\n\nUpdated body."
    assert update_call["metadata"]["saved_via"] == "cli"


def test_app_facade_contract_self_check_reports_ok() -> None:
    app = DeepTutorApp()

    assert app.contract_self_check.ok is True
    assert app.contract_self_check.entrypoint == "CONTRACT.md"
    assert app.contract_self_check.transport == "/api/v1/ws"
    assert "turn" in app.contract_self_check.domains
    assert "capability" in app.contract_self_check.domains
    assert "learner_state" in app.contract_self_check.domains


def test_app_facade_strict_contract_check_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "deeptutor.app.facade.load_contract_index",
        lambda: {"entrypoint": "CONTRACT.md", "domains": {"turn": {}}},
    )
    monkeypatch.setenv("DEEPTUTOR_STRICT_CONTRACT_CHECK", "true")

    with pytest.raises(RuntimeError, match="contract self-check failed"):
        DeepTutorApp()


def test_packaged_contract_index_matches_repo_contract_index() -> None:
    payload = load_contract_index()
    resolved_path = get_contract_index_path()
    candidates = get_contract_index_candidates()

    assert payload["entrypoint"] == "CONTRACT.md"
    assert "turn" in payload["domains"]
    assert resolved_path.name == "index.yaml"
    assert len(candidates) >= 2
    repo_payload = yaml.safe_load(candidates[0].read_text(encoding="utf-8"))
    package_payload = yaml.safe_load(candidates[1].read_text(encoding="utf-8"))
    assert repo_payload == package_payload
