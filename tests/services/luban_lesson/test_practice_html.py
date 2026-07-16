from __future__ import annotations

import copy
import base64
import hashlib
import json
from pathlib import Path

import pytest

import deeptutor.services.luban_lesson.practice_html as practice_html
from deeptutor.services.luban_lesson.practice_html import (
    PracticeHtmlInvalid,
    _array_after,
    _top_level_objects,
    build_practice_authority,
    compile_practice_surface,
    compiled_practice_eligibility_summary,
    decode_projection_receipt,
    load_compiled_practice,
    project_compiled_practice,
    resolve_projection_receipt,
    resolve_compiled_practice_items,
)

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs" / "原始数据" / "考点原料" / "成品" / "_pack_manifest.json"
PUBLIC = ROOT / "web" / "public" / "luban-preview"


def _compiled_n01_surface() -> dict[str, object]:
    source = (
        ROOT
        / "artifacts/luban_case_family_assets/diagram_microlesson/finished/P40_N01/P40_N01.practice.dc.html"
    )
    raw = source.read_text(encoding="utf-8")
    return compile_practice_surface(
        "N01",
        surface_id="practice.html",
        html=raw,
        source_path=str(source.relative_to(ROOT)),
        source_html_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def _signed_review(
    item: dict[str, object],
    index: int,
    *,
    fact_id: str = "",
    probe_role: str = "anchor",
) -> dict[str, object]:
    return {
        "fact_id": fact_id or f"N01-fact-{index + 1}",
        "skeleton_id": f"N01-skeleton-{index + 1}",
        "probe_role": probe_role,
        "source_anchor": f"textbook:N01#fact-{index + 1}",
        "source_sha256": "a" * 64,
        "review": {
            "status": "signed",
            "verdict": "approved",
            "reviewed_content_sha256": item["content_sha256"],
            "signatures": [
                {
                    "role": "teaching",
                    "reviewer_id": "teacher-reviewer",
                    "signed_at": "2026-07-16T00:00:00Z",
                },
                {
                    "role": "scoring",
                    "reviewer_id": "scoring-owner",
                    "signed_at": "2026-07-16T00:00:00Z",
                },
            ],
            "checks": {
                "source_verified": True,
                "answer_verified": True,
                "diagnosis_verified": True,
                "longest_option_checked": True,
                "template_leakage_checked": True,
            },
        },
        "revoked": False,
        "revocation_refs": [],
    }


def test_v3_compiler_emits_item_governance_and_defaults_to_ineligible() -> None:
    compiled = _compiled_n01_surface()
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
    )

    assert authority["schema_version"] == "luban_compiled_practice.v3"
    assert all(item["fact_id"] == "" for item in authority["items"])
    assert all(item["skeleton_id"] == "" for item in authority["items"])
    assert all(item["review"]["status"] == "pending" for item in authority["items"])
    assert all(item["eligible"] is False for item in authority["items"])
    assert all(item["revoked"] is False for item in authority["items"])
    assert authority["surfaces"][0]["eligible_variant_ids"] == []

    receipt = decode_projection_receipt(
        authority["surfaces"][0]["projection_receipt"]
    )
    assert receipt["pack_id"] == "N01"
    assert receipt["ordered_variant_ids"] == authority["surfaces"][0]["variant_ids"]
    assert len(receipt["source_digest"]) == 64
    assert len(receipt["projection_digest"]) == 64


def test_projection_receipt_resolves_only_exact_signed_non_revoked_set(
    tmp_path: Path,
) -> None:
    compiled = _compiled_n01_surface()
    compiled["surface"]["published_practice_sha256"] = "4" * 64
    selected_ids = set(compiled["surface"]["variant_ids"])
    reviews = {}
    selected = [
        (index, item)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] in selected_ids
    ]
    for selected_index, (index, item) in enumerate(selected):
        reviews[item["variant_id"]] = _signed_review(
            item,
            index,
            fact_id="N01-fact-triad" if selected_index == 0 else "",
        )
    extras = [
        (index, item)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] not in selected_ids
    ][:2]
    for role, (index, item) in zip(("immediate_confirm", "d1_probe"), extras):
        reviews[item["variant_id"]] = _signed_review(
            item, index, fact_id="N01-fact-triad", probe_role=role
        )
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
        review_records=reviews,
    )
    authority["published_lesson_sha256"] = "3" * 64
    path = tmp_path / "n01.practice.authority.json"
    path.write_text(json.dumps(authority, ensure_ascii=False), encoding="utf-8")

    receipt = authority["surfaces"][0]["projection_receipt"]
    resolved = resolve_projection_receipt("N01", receipt, authority_path=path)
    assert [item["variant_id"] for item in resolved] == authority["surfaces"][0][
        "variant_ids"
    ]

    reordered = decode_projection_receipt(receipt)
    reordered["ordered_variant_ids"] = list(reversed(reordered["ordered_variant_ids"]))
    reordered_receipt = base64.urlsafe_b64encode(
        json.dumps(
            reordered, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).decode("ascii").rstrip("=")
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        resolve_projection_receipt("N01", reordered_receipt, authority_path=path)

    stale = copy.deepcopy(authority)
    stale["items"][0]["revoked"] = True
    stale["items"][0]["eligible"] = False
    stale["items"][0]["revocation_refs"] = ["content-review:N01:withdrawn"]
    path.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        resolve_projection_receipt("N01", receipt, authority_path=path)


def test_five_signed_anchors_do_not_bypass_seven_question_fact_triad_gate() -> None:
    compiled = _compiled_n01_surface()
    selected_ids = set(compiled["surface"]["variant_ids"])
    reviews = {
        item["variant_id"]: _signed_review(item, index)
        for index, item in enumerate(compiled["items"])
        if item["variant_id"] in selected_ids
    }
    authority = build_practice_authority(
        "N01",
        source_pack_sha256="1" * 64,
        source_bundle_sha256="2" * 64,
        compiled_surfaces=[compiled],
        review_records=reviews,
    )

    summary = compiled_practice_eligibility_summary(authority)
    assert summary["eligible_question_count"] == 5
    assert summary["anchors_ready"] is True
    assert summary["complete_fact_count"] == 0
    assert summary["supply_ready"] is False


def test_projection_receipt_rejects_legacy_identity() -> None:
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        decode_projection_receipt("1,0,1,0,1")


def _compiled_pack_ids() -> list[str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [
        row["pack_id"]
        for row in manifest["packs"]
        if (row.get("practice") or {}).get("status") == "compiled"
    ]


def test_all_registered_finished_practices_compile_full_private_pools_and_five_question_projections() -> None:
    pack_ids = _compiled_pack_ids()
    authorities = [load_compiled_practice(pack_id) for pack_id in pack_ids]

    assert len(pack_ids) == 40
    assert all(authority is not None for authority in authorities)
    assert sum(len(authority["surfaces"]) for authority in authorities if authority) == 43
    assert sum(len(authority["items"]) for authority in authorities if authority) == 633
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
            assert len(surface["variant_ids"]) == 5
            assert set(surface["variant_ids"]).issubset(
                {item["variant_id"] for item in authority["items"]}
            )
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


@pytest.mark.parametrize("pack_id", ["N01", "S05", "X01"])
def test_candidate_packs_remain_default_denied_until_exact_human_signatures(
    pack_id: str,
) -> None:
    canonical = load_compiled_practice(pack_id)
    assert canonical is not None
    assert canonical["schema_version"] == "luban_compiled_practice.v3"
    assert all(item["eligible"] is False for item in canonical["items"])
    assert all(item["review"]["status"] == "pending" for item in canonical["items"])
    with pytest.raises(PracticeHtmlInvalid, match="selection_insufficient"):
        project_compiled_practice(pack_id, selection_key="qa_eval_candidate:2026196:forward")


def test_every_pending_compiled_surface_fails_closed_instead_of_falling_back() -> None:
    for pack_id in _compiled_pack_ids():
        authority = load_compiled_practice(pack_id)
        assert authority is not None
        for surface in authority["surfaces"]:
            surface_id = surface["surface_id"]
            assert surface["eligible_variant_ids"] == []
            with pytest.raises(PracticeHtmlInvalid, match="selection_insufficient"):
                project_compiled_practice(
                    pack_id,
                    surface_id=surface_id,
                    selection_key=f"qa_eval_all_surfaces:2026196:{surface_id}",
                )


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
            assert "projection_receipt=" in html
            assert "&answers=" in html
            assert "answer_indexes" not in html
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
    second_ids = s01["surfaces"][1]["variant_ids"]
    assert len(second_ids) == 5
    assert all(
        next(item for item in s01["items"] if item["variant_id"] == variant_id)["surface_id"]
        == "practice2.html"
        for variant_id in second_ids
    )
    with pytest.raises(PracticeHtmlInvalid, match="selection_insufficient"):
        resolve_compiled_practice_items("S01", surface_id="practice2.html")


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
