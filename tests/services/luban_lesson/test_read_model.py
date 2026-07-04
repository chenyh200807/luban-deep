"""luban_lesson 域测试：投影门 fail-closed 是本模块唯一的存在理由。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_lesson_viewmodel,
    list_green_lessons,
)


def _write_manifest(tmp_path: Path, packs, green) -> Path:
    p = tmp_path / "_pack_manifest.json"
    p.write_text(
        json.dumps({"projection_green": green, "packs": packs}, ensure_ascii=False),
        encoding="utf-8",
    )
    return p


_S05 = {"pack_id": "S05", "title": "临时用电三级配电", "content_sha256": "abc123",
        "published": True, "jury_clean": True, "explicitly_barred_default_entry": False}
_X99 = {"pack_id": "X99", "title": "未签发包", "content_sha256": "def456",
        "published": False, "jury_clean": False, "explicitly_barred_default_entry": False}


def test_green_pack_projects_viewmodel(tmp_path, monkeypatch):
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    mp = _write_manifest(tmp_path, [_S05, _X99], ["S05"])
    vm = build_lesson_viewmodel("s05", manifest_path=mp)
    assert vm["pack_id"] == "S05"
    assert vm["content_sha256"] == "abc123"
    assert vm["card_url"] == "https://cdn.example.com/luban/s05/lesson.html"
    assert vm["evidence_channels"] == {
        "light_practice": "learner_signal", "full_answer": "case_grading",
    }


def test_unpublished_pack_fail_closed_same_as_missing(tmp_path):
    mp = _write_manifest(tmp_path, [_S05, _X99], ["S05"])
    with pytest.raises(LessonNotAvailable):
        build_lesson_viewmodel("X99", manifest_path=mp)  # 存在但未签发
    with pytest.raises(LessonNotAvailable):
        build_lesson_viewmodel("Z00", manifest_path=mp)  # 不存在


def test_missing_or_corrupt_manifest_fail_closed(tmp_path):
    with pytest.raises(LessonNotAvailable):
        build_lesson_viewmodel("S05", manifest_path=tmp_path / "nope.json")
    bad = tmp_path / "_pack_manifest.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(LessonNotAvailable):
        build_lesson_viewmodel("S05", manifest_path=bad)


def test_green_only_in_listing(tmp_path):
    mp = _write_manifest(tmp_path, [_S05, _X99], ["S05"])
    rows = list_green_lessons(manifest_path=mp)
    assert [r["pack_id"] for r in rows] == ["S05"]


def test_variant_summary_from_bank_sidecar(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "candidate", "source_pack_sha256": "abc123",
        "variants": [{"variant_id": "S05-B-000"}, {"variant_id": "S05-B-001"}],
    }), encoding="utf-8")
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    assert vm["variant_retest"]["available"] is True
    assert vm["variant_retest"]["count"] == 2
    assert vm["variant_retest"]["bank_status"] == "candidate"


def test_no_card_base_env_degrades_to_empty_url(tmp_path, monkeypatch):
    monkeypatch.delenv("LUBAN_LESSON_CARD_BASE", raising=False)
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    assert vm["card_url"] == ""


def test_real_manifest_green_packs_all_project():
    """对真 manifest 的活体断言：绿灯集合里的每个包都能出 viewmodel。"""
    rows = list_green_lessons()
    assert rows, "main 上已有 5 个绿灯包, 列表不应为空"
    for row in rows:
        vm = build_lesson_viewmodel(row["pack_id"])
        assert vm["content_sha256"]


def _bank(tmp_path, n_core=6, n_ext=2):
    variants = [{"variant_id": f"S05-X-{i:03d}", "rule_group": "C-voltage",
                 "surface": f"表面{i}", "expected_ok": i % 2 == 0,
                 "correct_statement": "s", "anchor": "kc:x", "extension": False}
                for i in range(n_core)]
    variants += [{"variant_id": f"S05-E-{i}", "rule_group": "X-distance",
                  "surface": f"外延{i}", "expected_ok": True,
                  "correct_statement": "s", "anchor": "{2017,第2题}", "extension": True}
                 for i in range(n_ext)]
    (tmp_path / "_S05_variant_bank.v0.json").write_text(
        json.dumps({"status": "candidate", "variants": variants}), encoding="utf-8")


def test_retest_items_deterministic_and_core_only(tmp_path):
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _bank(tmp_path)
    a = build_retest_items("S05", user_id="u1", day_index=738000, limit=3, manifest_path=mp)
    b = build_retest_items("S05", user_id="u1", day_index=738000, limit=3, manifest_path=mp)
    assert a == b and len(a) == 3, "同用户同日必须幂等(§9-D3)"
    c = build_retest_items("S05", user_id="u1", day_index=738001, limit=3, manifest_path=mp)
    assert a != c, "跨天轮换"
    assert all(not i["variant_id"].startswith("S05-E") for i in a + c), "外延变体禁入复测"


def test_retest_items_gate_and_empty_bank(tmp_path):
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05, _X99], ["S05"])
    with pytest.raises(LessonNotAvailable):
        build_retest_items("X99", user_id="u", day_index=1, manifest_path=mp)
    assert build_retest_items("S05", user_id="u", day_index=1, manifest_path=mp) == []


def test_retest_pool_wraps_when_exhausted(tmp_path):
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _bank(tmp_path, n_core=2)
    items = build_retest_items("S05", user_id="u", day_index=99, limit=5, manifest_path=mp)
    assert len(items) == 2, "池小于 limit 时只发池内不重复项(复用旧变体, 绝不现编)"


def test_manifest_cache_hits_by_stat_and_invalidates_on_change(tmp_path, monkeypatch):
    # 病B-3（事件循环纪律）：manifest 每请求全量重读+重解析曾是纯浪费；
    # (mtime_ns,size) 键缓存命中零解析，产物更新自动失效，失败不缓存。
    import deeptutor.services.luban_lesson.read_model as rm

    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    rm._MANIFEST_CACHE.clear()
    parses = {"n": 0}
    original_loads = json.loads

    def counting_loads(*args, **kwargs):
        parses["n"] += 1
        return original_loads(*args, **kwargs)

    monkeypatch.setattr(rm.json, "loads", counting_loads)

    assert rm.list_all_pack_ids(manifest_path=mp) == ["S05"]
    first = parses["n"]
    assert rm.list_all_pack_ids(manifest_path=mp) == ["S05"]
    assert parses["n"] == first  # 第二次命中缓存，零解析

    # 产物更新（内容变 → stat 键变）自动失效
    _write_manifest(tmp_path, [_S05, _X99], ["S05"])
    assert rm.list_all_pack_ids(manifest_path=mp) == ["S05", "X99"]
    assert parses["n"] > first

    # 损坏文件 fail-closed 且不落缓存：修好后同进程恢复
    mp.write_text("{broken", encoding="utf-8")
    assert rm.list_all_pack_ids(manifest_path=mp) == []
    _write_manifest(tmp_path, [_S05], ["S05"])
    assert rm.list_all_pack_ids(manifest_path=mp) == ["S05"]
    rm._MANIFEST_CACHE.clear()
