from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DATA_ID_GATE = ROOT / "artifacts/luban_case_family_assets/diagram_microlesson/validate_data_id_targets.mjs"
TIMING_GATE = ROOT / "artifacts/luban_case_family_assets/diagram_microlesson/validate_timing_sync.mjs"


def run_node(script: Path, *args: Path | str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for diagram microlesson gate tests")
    return subprocess.run(
        [node, str(script), *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def write_lesson(tmp_path: Path) -> Path:
    lesson = tmp_path / "card.lesson.json"
    lesson.write_text(
        """{
          "schema_version": "luban_teaching_animation.v0",
          "card_id": "card",
          "teach": {"beats": [
            {"id": "intro", "animation_action": [
              {"type": "camera", "target": "data-id:stage.intro"},
              {"type": "keycard", "target": "data-id:keycard.intro"}
            ]}
          ]}
        }""",
        encoding="utf-8",
    )
    return lesson


def write_rendered(tmp_path: Path, *, include_keycard: bool = True) -> Path:
    keycard = '<div data-visual-node-id="keycard.intro"></div>' if include_keycard else ""
    rendered = tmp_path / "card.lesson.view.html"
    rendered.write_text(
        f"""<!doctype html><html><body>
        <main data-card-id="card" data-stage-shell="test">
          <section data-stage-shell="visual-stage">
            <div data-beat-id="intro"></div>
            <div data-action-id="intro.camera.0"></div>
            <div data-visual-node-id="stage.intro"></div>
            {keycard}
            <div data-practice-id="q1"></div>
          </section>
        </main>
        <script>window.__LUBAN_LESSON_MANIFEST__={{}};</script>
        </body></html>""",
        encoding="utf-8",
    )
    return rendered


def write_rendered_with_plain_id_only(tmp_path: Path) -> Path:
    rendered = tmp_path / "card.lesson.view.html"
    rendered.write_text(
        """<!doctype html><html><body>
        <main data-card-id="card" data-stage-shell="test">
          <section data-stage-shell="visual-stage">
            <div data-beat-id="intro"></div>
            <div data-action-id="intro.camera.0"></div>
            <div data-visual-node-id="stage.intro"></div>
            <div id="keycard.intro"></div>
            <div data-practice-id="q1"></div>
          </section>
        </main>
        <script>window.__LUBAN_LESSON_MANIFEST__={};</script>
        </body></html>""",
        encoding="utf-8",
    )
    return rendered


def test_data_id_gate_passes_when_targets_resolve(tmp_path: Path) -> None:
    result = run_node(DATA_ID_GATE, write_lesson(tmp_path), write_rendered(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "data-id target gate: PASS" in result.stdout


def test_data_id_gate_fails_when_target_is_missing(tmp_path: Path) -> None:
    result = run_node(DATA_ID_GATE, write_lesson(tmp_path), write_rendered(tmp_path, include_keycard=False))

    assert result.returncode == 1
    assert "keycard.intro" in result.stderr
    assert "data-id target gate: FAIL" in result.stderr


def test_data_id_gate_rejects_plain_id_false_positive(tmp_path: Path) -> None:
    result = run_node(DATA_ID_GATE, write_lesson(tmp_path), write_rendered_with_plain_id_only(tmp_path))

    assert result.returncode == 1
    assert "keycard.intro" in result.stderr
    assert "data-id target gate: FAIL" in result.stderr


def write_timing_pair(tmp_path: Path, *, keyword: str = "关键判据") -> Path:
    lesson = tmp_path / "sync.lesson.json"
    lesson.write_text(
        f"""{{
          "schema_version": "luban_teaching_animation.v0",
          "card_id": "sync",
          "teach": {{"beats": [
            {{"id": "intro", "claim": true, "sync_keyword": "{keyword}", "animation_action": [
              {{"type": "highlight", "target": "data-id:stage.intro"}}
            ]}}
          ]}},
          "qa": [
            {{"q": {{"speaker": "S", "claim": false, "text": "问"}},
             "a": {{"speaker": "T", "claim": true, "sync_keyword": "{keyword}", "text": "答"}}}}
          ]
        }}""",
        encoding="utf-8",
    )
    timing = tmp_path / "sync.lesson.timing.json"
    timing.write_text(
        """{
          "audio": "sync.lesson.mp3",
          "totalSec": 20,
          "teachEndSec": 8,
          "segments": [
            {"idx": 0, "kind": "teach", "state": "intro", "claim": true, "text": "这里讲关键判据", "startSec": 0, "durSec": 8},
            {"idx": 1, "kind": "a", "qaIndex": 0, "state": "intro", "claim": true, "text": "老师继续讲关键判据", "startSec": 8, "durSec": 6}
          ]
        }""",
        encoding="utf-8",
    )
    return timing


def test_timing_gate_fails_when_sync_keyword_does_not_hit_segment_text(tmp_path: Path) -> None:
    timing = write_timing_pair(tmp_path, keyword="不存在的关键词")

    result = run_node(TIMING_GATE, timing)

    assert result.returncode == 1
    assert "未命中对应旁白" in result.stdout


def test_timing_gate_passes_when_sync_keyword_hits_segment_text(tmp_path: Path) -> None:
    timing = write_timing_pair(tmp_path)

    result = run_node(TIMING_GATE, timing)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "且命中对应 timing 文本" in result.stdout
