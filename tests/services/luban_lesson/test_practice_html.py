from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path

import pytest

import deeptutor.services.luban_lesson.practice_html as practice_html
from deeptutor.services.luban_lesson.practice_html import (
    PracticeHtmlInvalid,
    _array_after,
    _top_level_objects,
    load_compiled_practice,
    project_compiled_practice,
    resolve_compiled_practice_items,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
PUBLIC = ROOT / "web" / "public" / "luban-preview"


def _compiled_pack_ids() -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        row["pack_id"]
        for row in manifest["packs"]
        if (row.get("practice") or {}).get("status") == "compiled"
    ]


def test_all_registered_finished_practices_compile_to_private_five_question_surfaces() -> None:
    pack_ids = _compiled_pack_ids()
    authorities = [load_compiled_practice(pack_id) for pack_id in pack_ids]

    assert len(pack_ids) == 40
    assert all(authority is not None for authority in authorities)
    assert sum(len(authority["surfaces"]) for authority in authorities if authority) == 43
    assert sum(len(authority["items"]) for authority in authorities if authority) == 215
    for authority in authorities:
        assert authority is not None
        assert len({item["variant_id"] for item in authority["items"]}) == len(
            authority["items"]
        )
        assert all(
            sum(option["is_correct"] for option in item["options"]) == 1
            for item in authority["items"]
        )
        for surface in authority["surfaces"]:
            source = ROOT / surface["source_path"]
            assert source.is_file()
            assert hashlib.sha256(source.read_bytes()).hexdigest() == surface[
                "source_html_sha256"
            ]


def test_compiled_and_unavailable_pack_sets_are_exact() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    compiled = {
        row["pack_id"]
        for row in manifest["packs"]
        if (row.get("practice") or {}).get("status") == "compiled"
    }
    unavailable = {
        row["pack_id"]
        for row in manifest["packs"]
        if (row.get("practice") or {}).get("status") == "unavailable"
    }
    assert len(compiled) == 40
    assert unavailable == {"E01"}


def test_f16_projects_curated_five_without_answer_leakage() -> None:
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
    assert all("is_correct" not in option for item in projected for option in item["options"])
    assert all("model_answer" not in item for item in projected)


def test_public_projection_contains_only_compiled_questions_and_server_bridge() -> None:
    for pack_id in _compiled_pack_ids():
        authority = load_compiled_practice(pack_id)
        assert authority is not None
        for surface in authority["surfaces"]:
            html = (PUBLIC / pack_id.lower() / surface["surface_id"]).read_text(
                encoding="utf-8"
            )
            marker = surface["array_marker"]
            if marker:
                assert len(_top_level_objects(_array_after(html, marker))) == 5
            assert "__dtRedirectEvidence" in html
            assert "this.optPerm(i)" in html
            assert "Number(permutation[selected])" in html
            assert f'encodeURIComponent("{pack_id}")' in html
            assert f'encodeURIComponent("{surface["surface_id"]}")' in html
            assert "网页预览作答仅供即时反馈" in html
            assert "满分手" not in html
            assert '"稳了"' not in html
            assert "采分点都拿到了" not in html
            assert "满分——采分点抓得稳" not in html


def test_format_adapters_and_multi_surface_resolution_are_data_driven() -> None:
    a02 = load_compiled_practice("A02")
    s07 = load_compiled_practice("S07")
    s01 = load_compiled_practice("S01")
    assert a02 and a02["surfaces"][0]["format_kind"] == "bank_drawn"
    assert s07 and s07["surfaces"][0]["format_kind"] == "pool_deck"
    assert s01 and [surface["surface_id"] for surface in s01["surfaces"]] == [
        "practice.html",
        "practice2.html",
        "practice3.html",
    ]
    second = resolve_compiled_practice_items("S01", surface_id="practice2.html")
    assert second and [item["surface_id"] for item in second] == ["practice2.html"] * 5
    assert resolve_compiled_practice_items(
        "S01", variant_ids=[item["variant_id"] for item in second]
    ) == second


def test_authority_sidecar_answer_tamper_fails_closed(tmp_path: Path) -> None:
    canonical = load_compiled_practice("F16")
    assert canonical is not None
    for option in canonical["items"][0]["options"]:
        option["is_correct"] = False
    path = tmp_path / "practice.authority.json"
    path.write_text(json.dumps(canonical, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PracticeHtmlInvalid, match="answer_invalid"):
        load_compiled_practice("F16", authority_path=path)


def test_authority_sidecar_rejects_practice_surface_gaps(tmp_path: Path) -> None:
    canonical = load_compiled_practice("B02")
    assert canonical is not None
    tampered = copy.deepcopy(canonical)
    tampered["surfaces"][1]["surface_id"] = "practice3.html"
    for item in tampered["items"]:
        if item["surface_id"] == "practice2.html":
            item["surface_id"] = "practice3.html"
    path = tmp_path / "practice.authority.json"
    path.write_text(json.dumps(tampered, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(PracticeHtmlInvalid, match="surface_set_invalid"):
        load_compiled_practice("B02", authority_path=path)


def test_manifest_digest_rejects_shape_valid_answer_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = ROOT / "deeptutor/services/luban_lesson/compiled/f16.practice.authority.json"
    original = source_path.read_bytes()
    tampered = json.loads(original)
    first_options = tampered["items"][0]["options"]
    correct_index = next(
        index for index, option in enumerate(first_options) if option["is_correct"]
    )
    replacement = 1 if correct_index == 0 else 0
    first_options[correct_index]["is_correct"] = False
    first_options[replacement]["is_correct"] = True

    compiled = tmp_path / "compiled"
    compiled.mkdir()
    (compiled / "f16.practice.authority.json").write_text(
        json.dumps(tampered, ensure_ascii=False), encoding="utf-8"
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "packs": [
                    {
                        "pack_id": "F16",
                        "practice": {
                            "status": "compiled",
                            "authority_path": "f16.practice.authority.json",
                            "authority_sha256": hashlib.sha256(original).hexdigest(),
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(practice_html, "_COMPILED_DIR", compiled)
    monkeypatch.setattr(practice_html, "_MANIFEST_PATH", manifest)

    with pytest.raises(PracticeHtmlInvalid, match="digest_mismatch"):
        load_compiled_practice("F16")


def test_unregistered_or_wrong_surface_never_falls_back_to_another_question_set() -> None:
    b02 = load_compiled_practice("B02")
    assert b02 is not None
    assert [surface["surface_id"] for surface in b02["surfaces"]] == [
        "practice.html", "practice2.html"
    ]
    assert load_compiled_practice("E01") is None
    with pytest.raises(PracticeHtmlInvalid, match="surface_not_found"):
        resolve_compiled_practice_items("B02", surface_id="practice3.html")
    with pytest.raises(PracticeHtmlInvalid, match="surface_not_found"):
        resolve_compiled_practice_items("S01", surface_id="practice4.html")
