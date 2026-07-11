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
def test_retest_items_textbook_join_same_pack_signed_cards(tmp_path):
    """textbook = 同 pack 签发考点卡按 anchor==point_id 精确 join(fail-closed)。

    命中 → {quote, label, page_num} 逐字透传; 不命中/卡池 candidate → 字段缺省。
    """
    from deeptutor.services.luban_lesson.read_model import build_retest_items

    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "signed", "source_pack_sha256": "abc123",
        "variants": [
            {"variant_id": "S05-B-000", "rule_group": "B", "surface": "s1",
             "expected_ok": True, "correct_statement": "c1", "anchor": "kc:X:1"},
            {"variant_id": "S05-B-001", "rule_group": "B", "surface": "s2",
             "expected_ok": False, "correct_statement": "c2", "anchor": "kc:X:9"},
        ],
    }), encoding="utf-8")
    # 卡池 candidate → 全部无 textbook(签发闸 fail-closed)
    card_bank = {
        "status": "candidate", "source_pack_sha256": "abc123",
        "cards": [{"point_id": "kc:X:1", "front": "三级配电", "quote": "教材原文逐字",
                   "source_ref": {"page_num": 208}}],
    }
    (tmp_path / "_S05_concept_card_bank.v0.json").write_text(
        json.dumps(card_bank), encoding="utf-8")
    items = build_retest_items("S05", user_id="u", day_index=0, limit=5, manifest_path=mp)
    assert all("textbook" not in it for it in items)
    # 签发后 → anchor 命中的那题带 textbook, 不命中的缺省
    card_bank["status"] = "signed"
    (tmp_path / "_S05_concept_card_bank.v0.json").write_text(
        json.dumps(card_bank), encoding="utf-8")
    items = build_retest_items("S05", user_id="u", day_index=0, limit=5, manifest_path=mp)
    by_id = {it["variant_id"]: it for it in items}
    assert by_id["S05-B-000"]["textbook"] == {
        "quote": "教材原文逐字", "label": "三级配电", "page_num": 208}
    assert "textbook" not in by_id["S05-B-001"]


def test_listing_retest_available_follows_signed_bank(tmp_path):
    """retest_available = signed 变体池真值(单一闸复用)——头牌轻练按供给路由的依据。

    无 bank → False(保守降级); signed+sha 匹配 → True; candidate 未签发 → False。
    """
    mp = _write_manifest(tmp_path, [_S05, _X99], ["S05", "X99"])
    # 无 bank 文件 → False
    rows = {r["pack_id"]: r for r in list_green_lessons(manifest_path=mp)}
    assert rows["S05"]["retest_available"] is False
    assert rows["X99"]["retest_available"] is False
    # S05 signed + sha 匹配 → True
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "signed", "source_pack_sha256": "abc123",
        "variants": [{"variant_id": "S05-B-000"}],
    }), encoding="utf-8")
    # X99 candidate(未过人闸) → 仍 False(与 _load_signed_bank 同一 fail-closed)
    (tmp_path / "_X99_variant_bank.v0.json").write_text(json.dumps({
        "status": "candidate", "source_pack_sha256": _X99["content_sha256"],
        "variants": [{"variant_id": "X99-B-000"}],
    }), encoding="utf-8")
    rows = {r["pack_id"]: r for r in list_green_lessons(manifest_path=mp)}
    assert rows["S05"]["retest_available"] is True
    assert rows["X99"]["retest_available"] is False


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
    """活体断言：A01/F16/J01/N01 签发考点卡真投影出来（8/1/3/5，
    2026-07-11 考点卡质量治本 141 卡重签 + §1 blocklist 后的计数）;
    挖空/解药池 main 上尚未签发 → 两层 fail-closed（空/false）。"""
    expected = {"A01": 8, "F16": 1, "J01": 3, "N01": 5}
    for pack_id, n in expected.items():
        vm = build_lesson_viewmodel(pack_id)
        assert len(vm["review_concept_cards"]) == n, f"{pack_id} 考点卡投影计数"
        # 挖空/解药池未签发 → fail-closed（投影不生成铁律）：
        assert vm["cloze_fill"] == {"available": False, "items": []}
        assert vm["antidotes"] == {}
_SIGNED_ITEM_FIELDS = {
    "variant_id", "rule_group", "surface", "expected_ok", "correct_statement", "anchor",
}


def test_items_project_only_signed_fields_no_fabrication(tmp_path):
    """红线(投影不生成):对外题卡只投影签发字段,绝不派生 scoring_point 文本 /
    exam_refs(真题)/ chapter(章节)——变体池无此供给。两模式同守。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _bank(tmp_path)
    for mode in ("review", "forward"):
        items = build_retest_items(
            "S05", user_id="u1", day_index=738000, limit=3, mode=mode, manifest_path=mp
        )
        assert items, mode
        for item in items:
            assert set(item.keys()) == _SIGNED_ITEM_FIELDS, (
                f"{mode} 模式题卡出现未签发派生字段: {set(item.keys()) - _SIGNED_ITEM_FIELDS}"
            )


def _multi_group_bank(tmp_path):
    """核心变体分布在 3 个 rule_group(A×3 / B×2 / C×1),验证 forward 广度覆盖。"""
    variants = []
    for grp, n in (("A-order", 3), ("B-scope", 2), ("C-voltage", 1)):
        for i in range(n):
            variants.append({
                "variant_id": f"S05-{grp}-{i:03d}", "rule_group": grp,
                "surface": f"{grp}表面{i}", "expected_ok": i % 2 == 0,
                "correct_statement": "s", "anchor": "kc:x", "extension": False,
            })
    variants.append({"variant_id": "S05-E-0", "rule_group": "A-order", "surface": "外延",
                     "expected_ok": True, "correct_statement": "s", "anchor": "kc:x",
                     "extension": True})
    (tmp_path / "_S05_variant_bank.v0.json").write_text(
        json.dumps({"status": "signed", "source_pack_sha256": "abc123",
                    "variants": variants}), encoding="utf-8")


def test_forward_mode_covers_distinct_rule_groups(tmp_path):
    """forward 广度优先:limit ≤ 组数时,取到的题必落在不同 rule_group(先广后深)。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _multi_group_bank(tmp_path)
    items = build_retest_items(
        "S05", user_id="u1", day_index=738000, limit=3, mode="forward", manifest_path=mp
    )
    assert len(items) == 3
    assert len({i["rule_group"] for i in items}) == 3, "前 3 题应覆盖 3 个不同考法"
    assert all(not i["variant_id"].startswith("S05-E") for i in items), "外延变体禁入"


def test_retest_session_never_uniform_answer_key(tmp_path):
    """防答案模式泄露: 池含两类时, 任一 (user,day,mode) 送出的 session 不得全同答案。

    owner 实测抓到"整场点不妥当全对"——选题层收口为防全同+顺序洗牌(§9-D3 幂等保持)。
    """
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _multi_group_bank(tmp_path)
    for mode in ("forward", "review"):
        for uid in ("u1", "u2", "attacker", "f16demo"):
            for day in (738000, 738001, 738002):
                items = build_retest_items(
                    "S05", user_id=uid, day_index=day, limit=3,
                    mode=mode, manifest_path=mp)
                keys = {i["expected_ok"] for i in items}
                assert len(keys) == 2, f"{mode}/{uid}/{day} 全同答案: {items}"


def test_retest_session_skeleton_diversity(tmp_path):
    """同场次句式骨架去重: 池够多样时一场内不得出现"同句换词"两题。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    variants = []
    # 8个同骨架换词题 + 4个异骨架题
    for i in range(8):
        variants.append({"variant_id": f"S05-A-{i:03d}", "rule_group": "A",
            "surface": f"项目部将「实体{i}」列为划分依据", "expected_ok": i % 2 == 0,
            "correct_statement": "c", "anchor": "kc:x", "extension": False})
    distinct = [
        "某住宅楼验收按检验批→分项→分部顺序推进",
        "监理要求复验进场钢筋的出厂合格证",
        "雨后基坑侧壁出现渗水项目部继续开挖",
        "冬期浇筑的混凝土采用蓄热法养护",
    ]
    for i, surf in enumerate(distinct):
        variants.append({"variant_id": f"S05-B-{i:03d}", "rule_group": "B",
            "surface": surf, "expected_ok": i % 2 == 0,
            "correct_statement": "c", "anchor": "kc:x", "extension": False})
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "signed", "source_pack_sha256": "abc123", "variants": variants,
    }), encoding="utf-8")
    from deeptutor.services.luban_lesson.read_model import _surface_skeleton
    # 池共 5 种骨架(同句换词的8题算1种+4种各异) → 5题场次应零重复
    for uid in ("u1", "u2"):
        items = build_retest_items("S05", user_id=uid, day_index=738000, limit=5, manifest_path=mp)
        sks = [_surface_skeleton(i["surface"]) for i in items]
        assert len(set(sks)) == len(sks), f"场内出现同骨架: {sks}"
    # 小池优雅回填: 骨架不足时仍发满题数(不空窗), 唯一骨架数=池骨架数
    items3 = build_retest_items("S05", user_id="u1", day_index=738000, limit=8, manifest_path=mp)
    sks3 = [_surface_skeleton(i["surface"]) for i in items3]
    assert len(items3) == 8 and len(set(sks3)) == 5


def test_retest_pool_meta_counts(tmp_path):
    from deeptutor.services.luban_lesson.read_model import retest_pool_meta
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _multi_group_bank(tmp_path)
    meta = retest_pool_meta("S05", manifest_path=mp)
    assert meta == {"core_total": 6, "rule_groups_total": 3}


def test_retest_blocklisted_variants_never_served(tmp_path):
    """对抗面板 A 级停发清单: serve 侧过滤, 被停发变体绝不出现在任何 session。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _multi_group_bank(tmp_path)
    (tmp_path / "_variant_blocklist.json").write_text(json.dumps({
        "variants": [{"variant_id": "S05-A-order-000", "reason": "面板A级"}]
    }), encoding="utf-8")
    for uid in ("u1", "u2", "u3"):
        for day in (738000, 738001):
            items = build_retest_items("S05", user_id=uid, day_index=day,
                                       limit=6, manifest_path=mp)
            assert all(i["variant_id"] != "S05-A-order-000" for i in items)


def test_retest_uniform_pool_served_honestly(tmp_path):
    """单类池(全 False)如实全送不臆造对偶——防全同只在对偶存在时生效。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    variants = [{"variant_id": f"S05-F-{i}", "rule_group": "A", "surface": f"s{i}",
                 "expected_ok": False, "correct_statement": "c", "anchor": "kc:x",
                 "extension": False} for i in range(4)]
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "signed", "source_pack_sha256": "abc123", "variants": variants,
    }), encoding="utf-8")
    items = build_retest_items("S05", user_id="u1", day_index=738000, limit=3, manifest_path=mp)
    assert len(items) == 3 and all(i["expected_ok"] is False for i in items)


def test_forward_mode_deterministic(tmp_path):
    """forward 同用户同日幂等(多端一致,§9-D3)。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _multi_group_bank(tmp_path)
    a = build_retest_items("S05", user_id="u1", day_index=738000, limit=4, mode="forward", manifest_path=mp)
    b = build_retest_items("S05", user_id="u1", day_index=738000, limit=4, mode="forward", manifest_path=mp)
    assert a == b and len(a) == 4


def test_forward_and_review_are_same_builder_same_pool(tmp_path):
    """forward 不是第二 builder:同一 build_retest_items、同一签发池,仅选序不同。
    未识别 mode 归一为 review 行为。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    _multi_group_bank(tmp_path)
    review = build_retest_items("S05", user_id="u1", day_index=738000, limit=6, mode="review", manifest_path=mp)
    forward = build_retest_items("S05", user_id="u1", day_index=738000, limit=6, mode="forward", manifest_path=mp)
    # 同池:取满时(limit≥核心数)两模式是同一集合的重排
    assert {i["variant_id"] for i in review} == {i["variant_id"] for i in forward}
    unknown = build_retest_items("S05", user_id="u1", day_index=738000, limit=6, mode="banana", manifest_path=mp)
    assert unknown == review, "未识别 mode 归一 review"


def test_forward_mode_fail_closed_on_unsigned(tmp_path):
    """forward 与 review 同一签发闸:candidate/未签发 → 空(不伪造轻练题)。"""
    from deeptutor.services.luban_lesson import build_retest_items
    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    (tmp_path / "_S05_variant_bank.v0.json").write_text(json.dumps({
        "status": "candidate", "source_pack_sha256": "abc123",
        "variants": [{"variant_id": "S05-A-000", "rule_group": "A", "surface": "s",
                      "expected_ok": True, "correct_statement": "s", "anchor": "kc:x",
                      "extension": False}],
    }), encoding="utf-8")
    assert build_retest_items("S05", user_id="u", day_index=1, mode="forward", manifest_path=mp) == []


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
