from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson.practice_html import (
    F16_FINISHED_PRACTICE_SHA256,
    PracticeHtmlInvalid,
    _array_after,
    load_compiled_practice,
    project_compiled_practice,
)


def test_f16_compiled_html_projects_fixed_five_without_answer_leakage() -> None:
    canonical = load_compiled_practice("F16")
    projected = project_compiled_practice("F16")

    assert canonical is not None and projected is not None
    assert [item["source_index"] for item in canonical["items"]] == [0, 1, 2, 3, 5]
    assert [item["rule_group"] for item in canonical["items"]] == [
        "分档·条件维",
        "割补工序·程序维",
        "判断纠错·三段式",
        "检验清单·记录维",
        "采分诊断·末题",
    ]
    assert len({item["variant_id"] for item in canonical["items"]}) == 5
    assert all(sum(option["is_correct"] for option in item["options"]) == 1 for item in canonical["items"])
    assert all("is_correct" not in option for item in projected for option in item["options"])
    assert all("model_answer" not in item for item in projected)
    assert canonical["source_html_sha256"]
    source_pack = (
        Path(__file__).resolve().parents[3]
        / "docs" / "原始数据" / "考点原料" / "成品" / "F16_屋面防水起鼓割补.md"
    )
    assert canonical["source_pack_sha256"] == hashlib.sha256(
        source_pack.read_bytes()
    ).hexdigest()


def test_consumer_question_block_matches_tracked_compiled_source() -> None:
    root = Path(__file__).resolve().parents[3]
    consumer = (root / "web/public/luban-preview/f16/practice.html").read_text(
        encoding="utf-8"
    )
    compiled = (
        root
        / "artifacts/luban_case_family_assets/diagram_microlesson/finished"
        / "P40_F16/P40_F16.practice.dc.html"
    ).read_text(encoding="utf-8")

    assert _array_after(consumer, r"\bQ\s*=") == _array_after(compiled, r"\bQ\s*=")


def test_finished_preview_does_not_claim_mastery_or_persisted_evidence() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (
        root
        / "artifacts/luban_case_family_assets/diagram_microlesson/finished"
        / "P40_F16/P40_F16.practice.dc.html"
    ).read_text(encoding="utf-8")

    assert "满分手" not in source
    assert '"稳了"' not in source
    assert "采分点都拿到了" not in source
    assert "是否形成学习记录以小程序正式收据为准" in source


def test_five_question_policy_is_anchored_to_current_finished_sha() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "artifacts/luban_case_family_assets/diagram_microlesson/finished"
        / "P40_F16/P40_F16.practice.dc.html"
    )

    assert hashlib.sha256(source.read_bytes()).hexdigest() == F16_FINISHED_PRACTICE_SHA256


def test_authority_sidecar_answer_tamper_fails_closed(tmp_path: Path) -> None:
    canonical = load_compiled_practice("F16")
    assert canonical is not None
    for option in canonical["items"][0]["options"]:
        option["is_correct"] = False
    path = tmp_path / "practice.authority.json"
    import json

    path.write_text(json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PracticeHtmlInvalid, match="answer_invalid"):
        load_compiled_practice("F16", authority_path=path)
