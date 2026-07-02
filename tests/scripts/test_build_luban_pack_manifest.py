from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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
