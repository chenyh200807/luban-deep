from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = (
    ROOT
    / "artifacts/luban_case_family_assets/diagram_microlesson/"
    "build_card_bundle_manifest.py"
)

spec = importlib.util.spec_from_file_location("build_card_bundle_manifest", BUILDER)
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def write_bundle_fixture(tmp_path: Path) -> tuple[Path, Path]:
    lesson = tmp_path / "card.lesson.json"
    lesson.write_text('{"schema_version":"luban_teaching_animation.v0","teach":{"beats":[{"id":"intro"}]}}\n', encoding="utf-8")
    timing = tmp_path / "card.lesson.timing.json"
    timing.write_text('{"audio":"card.mp3","totalSec":10,"segments":[]}\n', encoding="utf-8")
    audio = tmp_path / "card.mp3"
    audio.write_bytes(b"fake mp3")
    master = tmp_path / "card.master.json"
    master.write_text(
        json.dumps(
            {
                "schema_version": "luban_case_family.master.sample.v0",
                "master_id": "card",
                "teaching_lesson_ref": lesson.name,
            }
        ),
        encoding="utf-8",
    )
    rendered = tmp_path / "card.journey.html"
    rendered.write_text("<!doctype html><html></html>\n", encoding="utf-8")
    return master, rendered


def test_bundle_manifest_records_assets_without_runtime_authority(tmp_path: Path) -> None:
    master, rendered = write_bundle_fixture(tmp_path)

    manifest = builder.build_manifest(master, rendered_path=rendered)

    assert manifest["schema_version"] == "luban_card_bundle_manifest.v0"
    assert manifest["official_score_allowed"] is False
    assert manifest["runtime_canonical"] is False
    assert manifest["grading_authority"] is False
    assert manifest["learner_state_write_allowed"] is False
    assert manifest["blocking_failures"] == []
    roles = {asset["role"]: asset for asset in manifest["assets"]}
    assert roles["master"]["status"] == "ok"
    assert roles["lesson"]["status"] == "ok"
    assert roles["timing"]["status"] == "ok"
    assert roles["rendered_html"]["sha256"]
    assert roles["audio"]["status"] == "ok"
    assert roles["audio"]["path"] == "card.mp3"
    assert not Path(roles["master"]["path"]).is_absolute()
    assert roles["practice_html"]["status"] == "pending_m4"
    assert roles["practice_html"]["required"] is False


def test_bundle_manifest_can_make_practice_blocking(tmp_path: Path) -> None:
    master, rendered = write_bundle_fixture(tmp_path)

    manifest = builder.build_manifest(master, rendered_path=rendered, require_practice=True)

    assert "practice_html:missing_required" in manifest["blocking_failures"]


def test_bundle_manifest_makes_timing_audio_blocking(tmp_path: Path) -> None:
    master, rendered = write_bundle_fixture(tmp_path)
    (tmp_path / "card.mp3").unlink()

    manifest = builder.build_manifest(master, rendered_path=rendered)

    assert "audio:missing_required" in manifest["blocking_failures"]
