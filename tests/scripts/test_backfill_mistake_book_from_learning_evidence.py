from __future__ import annotations

import subprocess
import sys

import pytest

from scripts import backfill_mistake_book_from_learning_evidence as backfill_module
from scripts.backfill_mistake_book_from_learning_evidence import build_mistake_book_payload, backfill_rows


def _wrong_row(event_id: str, *, user_id: str = "u1") -> dict:
    return {
        "event_id": event_id,
        "user_id": user_id,
        "source_bot_id": "construction-exam",
        "payload_json": {
            "question_id": f"q-{event_id}",
            "question_stem": f"Stem {event_id}",
            "score_awarded": 0,
            "max_score": 1,
            "error_events": [
                {
                    "concept_tag": "boundary",
                    "diagnosis": "mixed conditions",
                }
            ],
            "next_training_signal": {
                "concept": "approval conditions",
            },
            "explanation": {
                "summary": "Needs review.",
            },
            "question_type": "mcq",
        },
    }


def _correct_row(event_id: str, *, user_id: str = "u1") -> dict:
    return {
        "event_id": event_id,
        "user_id": user_id,
        "source_bot_id": "construction-exam",
        "payload_json": {
            "question_id": f"q-{event_id}",
            "score_awarded": 1,
            "max_score": 1,
        },
    }


class _FakeStore:
    def __init__(self, rows: dict[tuple[str, str], dict] | None = None) -> None:
        self._rows = dict(rows or {})

    def get_item(self, user_id: str, event_id: str) -> dict | None:
        row = self._rows.get((user_id, event_id))
        return dict(row) if row else None


class _FakeService:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    def save_item(self, **kwargs) -> dict:
        self.saved.append(dict(kwargs))
        return dict(kwargs)


class _FakeResponse:
    def __init__(self, payload: list[dict]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return list(self._payload)


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[dict] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args) -> None:
        return None

    def get(self, url: str, *, headers: dict, params: dict) -> _FakeResponse:
        self.calls.append(dict(params))
        offset = int(params.get("offset") or 0)
        pages = {
            0: [{"event_id": "evt_other", "user_id": "other"}],
            1: [{"event_id": "evt_target", "user_id": "target"}],
        }
        return _FakeResponse(pages.get(offset, []))


def test_build_mistake_book_payload_uses_learning_evidence_fields() -> None:
    payload, status = build_mistake_book_payload(_wrong_row("evt1"))

    assert status == "candidate"
    assert payload is not None
    assert payload["user_id"] == "u1"
    assert payload["event_id"] == "evt1"
    assert payload["subject_id"] == "construction_exam_1"
    assert payload["bot_id"] == "construction-exam"
    assert payload["title"] == "Stem evt1"
    assert payload["concept_label"] == "approval conditions"
    assert payload["error_label"] == "mixed conditions"
    assert payload["note"] == "Needs review."
    assert payload["tags"] == ["mcq"]
    assert payload["attempt_ref"]


def test_fetch_learning_evidence_rows_does_not_stop_after_filtered_empty_page(monkeypatch) -> None:
    monkeypatch.setattr(backfill_module.httpx, "Client", _FakeClient)

    rows = backfill_module.fetch_learning_evidence_rows(
        base_url="https://example.supabase.co",
        service_key="secret",
        user_ids={"target", "another"},
        limit=1,
        page_size=1,
    )

    assert rows == [{"event_id": "evt_target", "user_id": "target"}]


def test_backfill_dry_run_skips_correct_existing_and_archived_rows() -> None:
    store = _FakeStore(
        {
            ("u1", "evt_existing"): {"event_id": "evt_existing", "archived_at": None},
            ("u1", "evt_archived"): {"event_id": "evt_archived", "archived_at": "2026-05-01T00:00:00+08:00"},
        }
    )
    service = _FakeService()

    result = backfill_rows(
        [
            _wrong_row("evt_new"),
            _correct_row("evt_correct"),
            _wrong_row("evt_existing"),
            _wrong_row("evt_archived"),
        ],
        store=store,
        service=service,
        apply=False,
        restore_archived=False,
    )

    assert result["ok"] is True
    assert result["summary"]["seen"] == 4
    assert result["summary"]["would_insert"] == 1
    assert result["summary"]["skipped_not_wrong_attempt"] == 1
    assert result["summary"]["existing_active_skipped"] == 1
    assert result["summary"]["existing_archived_skipped"] == 1
    assert service.saved == []


def test_backfill_apply_writes_only_missing_rows_by_default() -> None:
    store = _FakeStore(
        {
            ("u1", "evt_existing"): {"event_id": "evt_existing", "archived_at": None},
            ("u1", "evt_archived"): {"event_id": "evt_archived", "archived_at": "2026-05-01T00:00:00+08:00"},
        }
    )
    service = _FakeService()

    result = backfill_rows(
        [
            _wrong_row("evt_new"),
            _wrong_row("evt_existing"),
            _wrong_row("evt_archived"),
        ],
        store=store,
        service=service,
        apply=True,
        restore_archived=False,
    )

    assert result["ok"] is True
    assert result["summary"]["inserted"] == 1
    assert result["summary"]["existing_active_skipped"] == 1
    assert result["summary"]["existing_archived_skipped"] == 1
    assert len(service.saved) == 1
    assert service.saved[0]["title"] == "Stem evt_new"
    assert service.saved[0]["subject_id"] == "construction_exam_1"


def test_backfill_can_restore_archived_rows_when_explicitly_requested() -> None:
    store = _FakeStore(
        {
            ("u1", "evt_archived"): {"event_id": "evt_archived", "archived_at": "2026-05-01T00:00:00+08:00"},
        }
    )
    service = _FakeService()

    result = backfill_rows(
        [_wrong_row("evt_archived")],
        store=store,
        service=service,
        apply=True,
        restore_archived=True,
    )

    assert result["ok"] is True
    assert result["summary"]["inserted"] == 1
    assert len(service.saved) == 1


def test_main_rejects_all_users_with_user_filter(monkeypatch) -> None:
    monkeypatch.setattr(
        backfill_module.argparse.ArgumentParser,
        "parse_args",
        lambda self: type(
            "Args",
            (),
            {
                "user_id": ["u1"],
                "all_users": True,
                "apply": False,
                "restore_archived": False,
                "limit": None,
                "page_size": 500,
                "env_file": ".env",
            },
        )(),
    )

    with pytest.raises(SystemExit, match="either --all-users or --user-id"):
        backfill_module.main()


def test_script_can_run_directly_from_repo_root_without_import_error() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/backfill_mistake_book_from_learning_evidence.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "No module named" not in result.stderr
    assert "Provide --user-id" in result.stderr
