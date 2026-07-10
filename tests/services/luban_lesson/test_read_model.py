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
        "published": True, "jury_clean": True, "explicitly_barred_default_entry": False,
        "card_hosted": True}
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


def test_unhosted_green_pack_gets_no_card_url(tmp_path, monkeypatch):
    """card_hosted 缺失/False 的绿灯站不发 card_url——防 web-view 打开 404
    (2026-07-05 部署探针实证: base 一配, 28 绿灯站里 22 站无托管卡)。"""
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    unhosted = dict(_S05, pack_id="G03", title="桩基", card_hosted=False)
    mp = _write_manifest(tmp_path, [unhosted], ["G03"])
    vm = build_lesson_viewmodel("g03", manifest_path=mp)
    assert vm["card_url"] == ""


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


def _concept_bank(tmp_path, *, status="signed", sha="abc123", front="临时用电三大系统"):
    (tmp_path / "_S05_concept_card_bank.v0.json").write_text(json.dumps({
        "status": status, "source_pack_sha256": sha,
        "cards": [{"card_id": "S05:kc:0", "front": front, "key_gist": "g", "quote": "q"}],
    }, ensure_ascii=False), encoding="utf-8")


def test_summary_from_signed_concept_bank_first_front(tmp_path):
    """路线卡副标题 = 签发考点卡首卡 front 逐字（真源，零生成）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _concept_bank(tmp_path)
    rows = list_green_lessons(manifest_path=mp)
    assert rows[0]["summary"] == "临时用电三大系统"


def test_summary_fail_closed_when_no_bank(tmp_path):
    """无考点卡的绿灯站：summary=""（前端据此留空,不造词）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    rows = list_green_lessons(manifest_path=mp)
    assert rows[0]["summary"] == ""


def test_summary_fail_closed_on_candidate_or_sha_drift(tmp_path):
    """考点卡池走同一签发闸：candidate/未签发、sha 漂移 → summary=""（与缺失同形）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _concept_bank(tmp_path, status="candidate")
    assert list_green_lessons(manifest_path=mp)[0]["summary"] == ""
    _concept_bank(tmp_path, status="signed", sha="stale-old-sha")
    assert list_green_lessons(manifest_path=mp)[0]["summary"] == ""


def test_variant_summary_signed_sha_match_passes(tmp_path):
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "signed", "source_pack_sha256": "abc123",
        "variants": [{"variant_id": "S05-B-000"}, {"variant_id": "S05-B-001"}],
    }), encoding="utf-8")
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    assert vm["variant_retest"]["available"] is True
    assert vm["variant_retest"]["count"] == 2
    assert vm["variant_retest"]["bank_status"] == "signed"
    assert vm["variant_retest"]["source_pack_sha256"] == "abc123"


def test_variant_bank_candidate_rejected_same_as_missing(tmp_path):
    """签发闸①：candidate（未签发）bank 与缺失同形——不直通真实考生。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "candidate", "source_pack_sha256": "abc123",
        "variants": [{"variant_id": "S05-B-000"}],
    }), encoding="utf-8")
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    assert vm["variant_retest"] == {"available": False, "count": 0}
    assert build_retest_items("S05", user_id="u", day_index=1, manifest_path=mp) == []


def test_variant_bank_sha_drift_rejected_same_as_missing(tmp_path):
    """签发闸②：pack 正文修订后（sha 漂移）旧签发变体失效——与缺失同形。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "signed", "source_pack_sha256": "stale-old-sha",
        "variants": [{"variant_id": "S05-B-000"}],
    }), encoding="utf-8")
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    assert vm["variant_retest"] == {"available": False, "count": 0}
    assert build_retest_items("S05", user_id="u", day_index=1, manifest_path=mp) == []


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
        json.dumps({"status": "signed", "source_pack_sha256": "abc123",
                    "variants": variants}), encoding="utf-8")


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


# ── 复习模块三层母题集投影（双轮 v3 §6.2/§5.2/§6.4）───────────────────────────
# 三层全部走 variant_retest 同一签发闸（signed + sha 双 fail-closed）：
# 概念卡池已签发 → 逐字投影；挖空/解药池尚未签发（main 上不存在）→ fail-closed。

def _concept_bank_multi(tmp_path, *, status="signed", sha="abc123"):
    """两张考点卡的签发池——投影须逐字透传 §6.2 字段（front/key_gist/quote/出处）。"""
    (tmp_path / "_S05_concept_card_bank.v0.json").write_text(json.dumps({
        "status": status, "source_pack_sha256": sha,
        "cards": [
            {"card_id": "S05:kc:1", "front": "三级配电", "key_gist": "总-分-开关箱",
             "quote": "施工现场临时用电应采用三级配电系统",
             "point_id": "kc:1", "source_ref": {"chunk_id": "", "page_num": None},
             "leaf_name_path": "安全 > 临时用电", "grade_weight": 5},
            {"card_id": "S05:kc:2", "front": "两级保护", "key_gist": "总配+开关箱漏保",
             "quote": "应设置两级漏电保护", "point_id": "kc:2",
             "source_ref": {"chunk_id": "", "page_num": None},
             "leaf_name_path": "安全 > 临时用电"},
        ],
    }, ensure_ascii=False), encoding="utf-8")


def test_review_concept_cards_verbatim_projection_from_signed_bank(tmp_path):
    """签发考点卡池 → 逐字投影 §6.2 字段列表（front/key_gist/quote/point/出处）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _concept_bank_multi(tmp_path)
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    cards = vm["review_concept_cards"]
    assert len(cards) == 2
    assert cards[0]["front"] == "三级配电"          # 考点，逐字
    assert cards[0]["key_gist"] == "总-分-开关箱"     # 关键词颗粒，逐字
    assert cards[0]["quote"] == "施工现场临时用电应采用三级配电系统"  # 教材原文，逐字
    assert cards[0]["point_id"] == "kc:1"             # 出处
    assert cards[0]["leaf_name_path"] == "安全 > 临时用电"
    # 不在 §6.2 投影字段清单里的 bank 字段不出现（不新造、也不顺手带出）：
    assert "grade_weight" not in cards[0]
    assert cards[1]["front"] == "两级保护"


def test_review_concept_cards_fail_closed_when_no_bank(tmp_path):
    """无考点卡池的绿灯站 → 空列表（fail-closed，绝不现编考点卡）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    assert vm["review_concept_cards"] == []


def test_review_concept_cards_fail_closed_on_candidate_or_sha_drift(tmp_path):
    """考点卡池走同一签发闸：candidate/未签发、sha 漂移 → 空列表（与缺失同形）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _concept_bank_multi(tmp_path, status="candidate")
    assert build_lesson_viewmodel("S05", manifest_path=mp)["review_concept_cards"] == []
    _concept_bank_multi(tmp_path, status="signed", sha="stale-old-sha")
    assert build_lesson_viewmodel("S05", manifest_path=mp)["review_concept_cards"] == []


def _cloze_bank(tmp_path, *, status="signed", sha="abc123"):
    (tmp_path / "_S05_r6_cloze_bank.v0.json").write_text(json.dumps({
        "status": status, "source_pack_sha256": sha,
        "items": [
            {"cloze_id": "S05:cz:1", "skeleton": "临时用电应采用____配电系统",
             "answer": "三级"},
            {"cloze_id": "S05:cz:2", "skeleton": "应设置____级漏电保护", "answer": "两"},
        ],
    }, ensure_ascii=False), encoding="utf-8")


def test_cloze_fill_verbatim_projection_from_signed_bank(tmp_path):
    """签发挖空池 → available:true + items 逐字透传（§5.2 关键词填空）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _cloze_bank(tmp_path)
    cf = build_lesson_viewmodel("S05", manifest_path=mp)["cloze_fill"]
    assert cf["available"] is True
    assert len(cf["items"]) == 2
    assert cf["items"][0]["skeleton"] == "临时用电应采用____配电系统"
    assert cf["items"][0]["answer"] == "三级"


def test_cloze_fill_fail_closed_when_no_bank(tmp_path):
    """无挖空池 → available:false（fail-closed；main 上挖空池尚未签发即此形）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    cf = build_lesson_viewmodel("S05", manifest_path=mp)["cloze_fill"]
    assert cf == {"available": False, "items": []}


def test_cloze_fill_fail_closed_on_candidate_or_sha_drift(tmp_path):
    """挖空池走同一签发闸：candidate/未签发、sha 漂移 → available:false（同缺失）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _cloze_bank(tmp_path, status="candidate")
    assert build_lesson_viewmodel("S05", manifest_path=mp)["cloze_fill"] == {
        "available": False, "items": []}
    _cloze_bank(tmp_path, status="signed", sha="stale-old-sha")
    assert build_lesson_viewmodel("S05", manifest_path=mp)["cloze_fill"] == {
        "available": False, "items": []}


def _antidote_bank(tmp_path, *, status="signed", sha="abc123"):
    (tmp_path / "_S05_r8_antidote_bank.v0.json").write_text(json.dumps({
        "status": status, "source_pack_sha256": sha,
        "antidotes": [
            {"antidote_id": "S05:ad:1", "error_code": "E02",
             "scoring_point": "三级配电", "antidote": "记忆口诀:总-分-开关箱"},
            {"antidote_id": "S05:ad:2", "error_code": "E02",
             "scoring_point": "开关箱一机一闸", "antidote": "一机一闸一漏一箱"},
            {"antidote_id": "S05:ad:3", "error_code": "E07",
             "scoring_point": "两级保护", "antidote": "总配+开关箱各一级漏保"},
            {"antidote_id": "S05:ad:bad", "scoring_point": "无错因码"},  # 缺 error_code
        ],
    }, ensure_ascii=False), encoding="utf-8")


def test_antidotes_grouped_by_error_code_verbatim(tmp_path):
    """签发解药池 → 按 error_code 归组逐字投影（§6.4 同错因聚焦）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _antidote_bank(tmp_path)
    ad = build_lesson_viewmodel("S05", manifest_path=mp)["antidotes"]
    assert set(ad.keys()) == {"E02", "E07"}
    assert len(ad["E02"]) == 2 and len(ad["E07"]) == 1
    assert ad["E02"][0]["antidote"] == "记忆口诀:总-分-开关箱"
    # 缺 error_code 的条目不投影（fail-closed:不虚构错因码归因）：
    assert all("bad" not in a["antidote_id"] for codes in ad.values() for a in codes)


def test_antidotes_fail_closed_when_no_bank(tmp_path):
    """无解药池 → {}（fail-closed；main 上解药池尚未签发即此形）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    assert build_lesson_viewmodel("S05", manifest_path=mp)["antidotes"] == {}


def test_antidotes_fail_closed_on_candidate_or_sha_drift(tmp_path):
    """解药池走同一签发闸：candidate/未签发、sha 漂移 → {}（与缺失同形）。"""
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _antidote_bank(tmp_path, status="candidate")
    assert build_lesson_viewmodel("S05", manifest_path=mp)["antidotes"] == {}
    _antidote_bank(tmp_path, status="signed", sha="stale-old-sha")
    assert build_lesson_viewmodel("S05", manifest_path=mp)["antidotes"] == {}


def test_real_manifest_spike_packs_project_concept_cards():
    """活体断言：A01/F16/J01/N01 签发考点卡真投影出来（10/2/6/5）;
    挖空/解药池 main 上尚未签发 → 两层 fail-closed（空/false）。"""
    expected = {"A01": 10, "F16": 2, "J01": 6, "N01": 5}
    for pack_id, n in expected.items():
        vm = build_lesson_viewmodel(pack_id)
        assert len(vm["review_concept_cards"]) == n, f"{pack_id} 考点卡投影计数"
        # 挖空/解药池未签发 → fail-closed（投影不生成铁律）：
        assert vm["cloze_fill"] == {"available": False, "items": []}
        assert vm["antidotes"] == {}


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
