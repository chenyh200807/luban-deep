from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "docs" / "原始数据" / "数据盘点" / "scripts" / "profile_raw_data_assets.py"


def _load_profiler():
    spec = importlib.util.spec_from_file_location("profile_raw_data_assets", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_bank(path: Path, cards: list[dict], *, declared_count: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "luban-concept-card-bank",
                "status": "signed",
                "card_count": len(cards) if declared_count is None else declared_count,
                "cards": cards,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_summarize_cards_uses_finished_concept_card_banks(tmp_path, monkeypatch) -> None:
    profiler = _load_profiler()
    monkeypatch.setattr(profiler, "ROOT", tmp_path)
    finished = tmp_path / "考点原料" / "成品"
    _write_bank(finished / "_A01_concept_card_bank.v0.json", [{"id": "a"}, {"id": "b"}])
    _write_bank(finished / "_S05_concept_card_bank.v0.json", [{"id": "c"}])

    summary = profiler.summarize_cards()

    assert summary["authority"] == "finished_concept_card_banks"
    assert summary["bank_files"] == 2
    assert summary["card_count"] == 3
    assert summary["invalid_banks"] == []
    assert summary["declared_count_mismatches"] == []
    assert summary["legacy_path_exists"] is False


def test_summarize_cards_reports_invalid_and_count_mismatch(tmp_path, monkeypatch) -> None:
    profiler = _load_profiler()
    monkeypatch.setattr(profiler, "ROOT", tmp_path)
    finished = tmp_path / "考点原料" / "成品"
    _write_bank(finished / "_A01_concept_card_bank.v0.json", [{"id": "a"}], declared_count=2)
    invalid = finished / "_BAD_concept_card_bank.v0.json"
    invalid.write_text("not-json", encoding="utf-8")

    summary = profiler.summarize_cards()

    assert summary["bank_files"] == 1
    assert summary["card_count"] == 1
    assert len(summary["invalid_banks"]) == 1
    assert summary["declared_count_mismatches"] == [
        {
            "path": "考点原料/成品/_A01_concept_card_bank.v0.json",
            "declared": 2,
            "actual": 1,
        }
    ]
