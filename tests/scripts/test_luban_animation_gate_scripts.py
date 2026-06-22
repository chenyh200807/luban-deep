from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DATA_ID_GATE = ROOT / "artifacts/luban_case_family_assets/diagram_microlesson/validate_data_id_targets.mjs"
TIMING_GATE = ROOT / "artifacts/luban_case_family_assets/diagram_microlesson/validate_timing_sync.mjs"
CONTRACT_GATE = ROOT / "artifacts/luban_case_family_assets/diagram_microlesson/validate_animation_ir_contract.mjs"


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


def write_animation_ir_contract_fixture(
    tmp_path: Path,
    *,
    visual_kind: str,
    required: list[str] | None,
    renderer_handles: list[str] | None = None,
    html_handles: list[str] | None = None,
) -> Path:
    src = tmp_path / "remotion_demo" / "src"
    src.mkdir(parents=True)
    ir_path = tmp_path / "card.animation_ir.v0.json"
    wrapper = src / "CardAnimationIrPreview.tsx"
    wrapper.write_text(
        """import React from "react";
import ir from "../../card.animation_ir.v0.json";
import {AnimationIrRenderer} from "./AnimationIrRenderer";
export const CardAnimationIrPreview: React.FC = () => <AnimationIrRenderer ir={ir as any} />;
""",
        encoding="utf-8",
    )
    handled = renderer_handles or [visual_kind]
    branches = "\n".join(f'if (node.kind === "{kind}") return null;' for kind in handled)
    (src / "AnimationIrRenderer.tsx").write_text(
        f"""export const AnimationIrRenderer = () => null;
function Primitive(node: {{kind: string}}) {{
  {branches}
  return null;
}}
""",
        encoding="utf-8",
    )
    html_branches = "\n".join(f'    if kind == "{kind}":\n        return ""' for kind in (html_handles or [visual_kind]))
    (tmp_path / "render_animation_ir_preview.py").write_text(
        f"""def _primitive_svg(node):
    kind = node.get("kind")
{html_branches}
    raise ValueError(kind)
""",
        encoding="utf-8",
    )
    scenes = []
    visual_library = {}
    for index, scene_id in enumerate(["hook", "map", "rule", "trap", "score", "closing_challenge"]):
        start = index * 10
        node_id = f"{scene_id}_visual"
        scenes.append(
            {
                "id": scene_id,
                "label": scene_id,
                "start_sec": start,
                "end_sec": start + 10,
                "scene": f"calculation_structure_{scene_id}",
                "focus": node_id,
                "enter": ["scene.fade_in"],
                "hold": [f"{node_id}.spotlight"],
                "exit": ["scene.fade_out"],
                "layout": {"portrait": "centered_board"},
                "camera": {"verb": "push-in", "target": node_id, "duration_sec": 0.4},
                "visible_nodes": [node_id],
                "actions": [
                    {"kind": "camera", "target": node_id, "start": 0, "end": 0.2},
                    {"kind": "reveal", "target": node_id, "start": 0.1, "end": 0.3},
                ],
                "keycard": "看图",
                "coach": "按图推演",
            }
        )
        visual_library[scene_id] = {
            "board": "warm_grid",
            "nodes": [{"id": node_id, "kind": visual_kind, "text": "图示", "x": 40, "y": 40, "w": 260, "h": 160}],
        }
    render_contract = {
        "html_preview": "card.animation_ir_preview.html",
        "remotion_renderer": "remotion_demo/src/CardAnimationIrPreview.tsx",
        "remotion_composition": "CardAnimationIrPreview",
        "max_visible_nodes": 4,
        "challenge_unlock_sec": 40,
    }
    if required is not None:
        render_contract["archetype_visual_required"] = required
    ir_path.write_text(
        __import__("json").dumps(
            {
                "schema_version": "luban_animation_ir.v0",
                "ir_id": "card",
                "card_id": "card",
                "display": {"title": "测试卡"},
                "main_exam_action": "把图写成采分句",
                "teaching_spine": {"archetype": "calculation_structure"},
                "render_contract": render_contract,
                "chapters": [{"id": scene["id"], "label": scene["label"], "start_sec": scene["start_sec"]} for scene in scenes],
                "scenes": scenes,
                "visual_library": visual_library,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return ir_path


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


def test_animation_ir_contract_rejects_text_only_archetype_visual(tmp_path: Path) -> None:
    ir_path = write_animation_ir_contract_fixture(tmp_path, visual_kind="pill", required=None)

    result = run_node(CONTRACT_GATE, ir_path)

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "archetype_visual_required_canonical" in output
    assert "archetype_not_text_only" in output


def test_animation_ir_contract_rejects_missing_remotion_primitive_branch(tmp_path: Path) -> None:
    ir_path = write_animation_ir_contract_fixture(
        tmp_path,
        visual_kind="network_graph",
        required=["network_graph", "formula_chain"],
        renderer_handles=["pill"],
    )

    result = run_node(CONTRACT_GATE, ir_path)

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "remotion_primitive_coverage" in output
    assert "network_graph" in output


def test_animation_ir_contract_rejects_missing_html_primitive_branch(tmp_path: Path) -> None:
    ir_path = write_animation_ir_contract_fixture(
        tmp_path,
        visual_kind="network_graph",
        required=["network_graph", "formula_chain"],
        renderer_handles=["network_graph"],
        html_handles=["pill"],
    )

    result = run_node(CONTRACT_GATE, ir_path)

    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert "html_primitive_coverage" in output
    assert "network_graph" in output
