from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "build_luban_pack_manifest", REPO / "scripts" / "build_luban_pack_manifest.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["build_luban_pack_manifest"] = _mod
_spec.loader.exec_module(_mod)


def test_manifest_scans_real_packs_and_never_self_publishes() -> None:
    """manifest 覆盖全部主 Pack; published 只能来自人工 overrides, 脚本恒 False。"""
    manifest = _mod.build_manifest()
    assert manifest["schema"] == "luban_deep_pack_manifest.v0"
    assert manifest["pack_count"] >= 40
    ids = [p["pack_id"] for p in manifest["packs"]]
    assert "A01" in ids and "S07" in ids
    assert len(ids) == len(set(ids)), "pack_id 必须唯一"
    if not _mod.OVERRIDES_PATH.exists():
        assert all(p["published"] is False for p in manifest["packs"])
        assert manifest["projection_green"] == []


def test_s07_coarse_review_is_barred_from_default_entry() -> None:
    """S07 自标 coarse_review + 不进默认入口——确定性提取必须如实登记(Codex 对抗采信)。"""
    manifest = _mod.build_manifest()
    s07 = next(p for p in manifest["packs"] if p["pack_id"] == "S07")
    assert s07["review_level"] == "coarse_review"
    assert s07["explicitly_barred_default_entry"] is True
    assert s07["needs_leaf_review"] is True


def test_entry_shape_has_projection_gate_fields() -> None:
    """投影门消费的字段必须齐: published/jury_clean/barred/sha256。"""
    manifest = _mod.build_manifest()
    required = {
        "pack_id", "content_sha256", "published", "jury_clean",
        "explicitly_barred_default_entry", "red_marker_count",
        "has_compiled_source", "has_exam_evidence",
    }
    for pack in manifest["packs"]:
        assert required <= set(pack), f"{pack['pack_id']} 缺字段: {required - set(pack)}"


def test_jury_clean_counts_only_unresolved_high_confidence() -> None:
    """jury_clean = 无未解决高可信 issue: 有 resolution.status=fixed 的不再挡门,
    无 resolution 的高可信 issue 仍 fail-closed 挡门(S05 签发样板实证)。"""
    manifest = _mod.build_manifest()
    s05 = next(p for p in manifest["packs"] if p["pack_id"] == "S05")
    # S05: 3 条高可信全部登记 resolution.status=fixed → clean
    assert s05["jury_high_confidence"] == 3
    assert s05["jury_high_confidence_unresolved"] == 0
    assert s05["jury_clean"] is True
    # 但未签发时仍不得进绿灯(published 恒 False, 除非 overrides 人工置 true)
    if not _mod.OVERRIDES_PATH.exists():
        assert "S05" not in manifest["projection_green"]
    # 对照组: 仍有未解决高可信 issue 的 pack 必须保持 jury_clean=False
    dirty = [p for p in manifest["packs"] if p["jury_high_confidence_unresolved"] > 0]
    assert dirty, "应存在未收口 pack(否则本断言失效需更新)"
    assert all(p["jury_clean"] is False for p in dirty)


def test_is_resolved_fail_closed_shapes() -> None:
    """resolution 形状不合法一律计为未解决(fail-closed)。"""
    assert _mod._is_resolved({"resolution": {"status": "fixed"}}) is True
    assert _mod._is_resolved({"resolution": {"status": "not_applicable"}}) is True
    assert _mod._is_resolved({}) is False
    assert _mod._is_resolved({"resolution": "fixed"}) is False
    assert _mod._is_resolved({"resolution": {"status": "wip"}}) is False


def test_companion_files_found_in_parent_mining_dir() -> None:
    """配套件在上级挖矿目录也算存在(S05 的 compiled_source/exam_evidence 实存于上级)。"""
    manifest = _mod.build_manifest()
    s05 = next(p for p in manifest["packs"] if p["pack_id"] == "S05")
    assert s05["has_compiled_source"] is True
    assert s05["has_exam_evidence"] is True


def test_published_only_from_overrides_and_green_closure() -> None:
    """published 只能来自 overrides 人工置位; 绿灯 = published∧jury_clean∧非barred 的精确闭包。"""
    manifest = _mod.build_manifest()
    published = {p["pack_id"] for p in manifest["packs"] if p["published"]}
    if _mod.OVERRIDES_PATH.exists():
        import json as _json
        overrides = _json.loads(_mod.OVERRIDES_PATH.read_text(encoding="utf-8"))
        allowed = {k for k, v in overrides.items() if v.get("published")}
        assert published == allowed, "published 集合必须与 overrides 人工置位完全一致"
    else:
        assert published == set()
    expected_green = sorted(
        p["pack_id"] for p in manifest["packs"]
        if p["published"] and p["jury_clean"] and not p["explicitly_barred_default_entry"]
    )
    assert sorted(manifest["projection_green"]) == expected_green
