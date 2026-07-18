from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "prefill_practice_review_anchors.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("prefill_practice_review_anchors", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def fixture_base(tmp_path: Path) -> Path:
    """Minimal 考点原料 layout for a fake pack T01."""
    base = tmp_path / "考点原料"
    packets = base / "成品" / "_practice_review_packets"
    packets.mkdir(parents=True)

    (base / "_T01_compiled_source.json").write_text(
        json.dumps(
            {
                "考点": "T01 测试考点",
                "units": [
                    {
                        "leaf_id": "1A000000-B001",
                        "source_ref": {"chunk_id": "1A000000_001_0001"},
                        "note": "本体判据",
                        "scoring_points": [
                            {
                                "point_id": "kc:1A000000_001_0001:0",
                                "statement": "关键工作是总时差最小的工作，关键线路工期等于计算工期。",
                                "quote": "关键工作是总时差最小的工作，关键线路工期等于计算工期。",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (base / "_T01_exam_evidence.json").write_text(
        json.dumps(
            {
                "考点": "T01",
                "evidence": [
                    {
                        "year": "2015",
                        "题号": "案例1",
                        "type": "case_study",
                        "stem": "网络图中关键线路有两条，总工期为25个月。",
                        "correct_answer": "关键线路判定依据总时差最小。",
                        "analysis": "",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    packet = {
        "schema": "luban_practice_review_packet.v1",
        "pack_id": "T01",
        "human_gate": {"required_roles": ["teaching", "scoring"], "machine_must_not_sign": True},
        "items": [
            {
                "variant_id": "T01-q1",
                "stem": "如何判定关键工作与关键线路？",
                "options": [
                    {"text": "关键工作是总时差最小的工作，关键线路工期等于计算工期。", "is_correct": True},
                    {"text": "持续时间最长的工作就是关键线路。", "is_correct": False},
                ],
                "model_answer": "关键工作是总时差最小的工作；关键线路工期等于计算工期。",
                "decision": {"source_anchor": "", "source_sha256": "", "review": {"status": "pending"}},
            }
        ],
    }
    (packets / "t01.practice.review.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return base


def test_generates_candidates_without_touching_packet(fixture_base: Path):
    mod = _load_module()
    packet_path = fixture_base / "成品" / "_practice_review_packets" / "t01.practice.review.json"
    packet_bytes_before = packet_path.read_bytes()

    rc = mod.main(["--base-dir", str(fixture_base), "T01"])
    assert rc == 0

    # 1) candidates file created, marked machine-only, packet untouched
    out_path = fixture_base / "成品" / "_practice_review_packets" / "t01.anchor.candidates.json"
    assert out_path.exists()
    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert out["machine_candidates_only"] is True
    assert "generated_at" in out
    assert packet_path.read_bytes() == packet_bytes_before

    # 2) decision fields still empty (never signed / filled by machine)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["items"][0]["decision"]["source_anchor"] == ""
    assert packet["items"][0]["decision"]["source_sha256"] == ""

    # 3) the matching question got real candidates with required fields
    item = out["items"][0]
    assert item["variant_id"] == "T01-q1"
    assert len(item["candidates"]) >= 1
    top = item["candidates"][0]
    assert top["source_anchor"] == "kc:1A000000_001_0001:0"
    assert 0 < top["match_score"] <= 1
    assert len(top["quote"]) <= 200
    assert len(top["source_sha256"]) == 64
    assert out["coverage"]["total_items"] == 1
    assert out["coverage"]["items_with_candidates"] == 1


def test_degrades_when_exam_evidence_missing(fixture_base: Path):
    (fixture_base / "_T01_exam_evidence.json").unlink()
    mod = _load_module()
    rc = mod.main(["--base-dir", str(fixture_base), "T01"])
    assert rc == 0
    out = json.loads(
        (fixture_base / "成品" / "_practice_review_packets" / "t01.anchor.candidates.json").read_text(
            encoding="utf-8"
        )
    )
    assert out["machine_candidates_only"] is True
    assert any("exam_evidence" in w for w in out["warnings"])
    # textbook anchor still found
    assert out["items"][0]["candidates"][0]["source_anchor"].startswith("kc:")
