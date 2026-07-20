"""luban_lesson 域测试：投影门 fail-closed 是本模块唯一的存在理由。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeptutor.services.luban_lesson import (
    LessonNotAvailable,
    build_lesson_viewmodel,
    list_green_lessons,
    list_lesson_catalog,
    list_teaching_points,
)
from deeptutor.services.luban_lesson.practice_html import load_compiled_practice


def _write_manifest(tmp_path: Path, packs, green) -> Path:
    p = tmp_path / "_pack_manifest.json"
    p.write_text(
        json.dumps({"projection_green": green, "packs": packs}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "_variant_blocklist.json").write_text(
        json.dumps({"variants": []}),
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
    assert vm["practice_url"] == ""
    assert vm["evidence_channels"] == {
        "practice_completion": "luban_retest_completion.v1",
        "full_answer": "case_grading",
    }


def test_custom_manifest_without_compiled_capability_cannot_guess_practice_url(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    f16 = dict(_S05, pack_id="F16", title="屋面防水起鼓割补")
    mp = _write_manifest(tmp_path, [f16], ["F16"])

    vm = build_lesson_viewmodel("F16", manifest_path=mp)

    assert vm["card_url"] == "https://cdn.example.com/luban/f16/lesson.html"
    assert vm["practice_url"] == ""


def test_pending_compiled_pack_hides_practice_consumer_url(monkeypatch, pendingize_pack):
    """合成 pending 世界态(2026-07-20 全语料签发后 F16 已签,夹具重置 review):
    未签发 pack 的讲解卡照常可达,但练习消费 URL 必须隐藏(fail-closed)。"""
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    authority = pendingize_pack("F16")
    vm = build_lesson_viewmodel("F16")
    assert authority is not None
    assert vm["card_url"] == (
        "https://cdn.example.com/luban/f16/lesson.html?v="
        + authority["published_lesson_sha256"]
    )
    assert authority["surfaces"][0]["eligible_variant_ids"] == []
    assert vm["practice_url"] == ""
    assert authority["published_lesson_sha256"] != authority["source_bundle_sha256"]


def test_unhosted_green_pack_gets_no_card_url(tmp_path, monkeypatch):
    """card_hosted 缺失/False 的绿灯站不发 card_url——防 web-view 打开 404
    (2026-07-05 部署探针实证: base 一配, 28 绿灯站里 22 站无托管卡)。"""
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    unhosted = dict(_S05, pack_id="G03", title="桩基", card_hosted=False)
    mp = _write_manifest(tmp_path, [unhosted], ["G03"])
    vm = build_lesson_viewmodel("g03", manifest_path=mp)
    assert vm["card_url"] == ""
    assert vm["practice_url"] == ""


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
    assert rows[0]["card_hosted"] is True


def test_green_listing_keeps_unhosted_truth_for_learning_home(tmp_path):
    unhosted = dict(_S05, pack_id="B02", card_hosted=False)
    mp = _write_manifest(tmp_path, [unhosted], ["B02"])
    rows = list_green_lessons(manifest_path=mp)
    assert len(rows) == 1
    assert rows[0]["pack_id"] == "B02"
    assert rows[0]["title"] == "临时用电三级配电"
    assert rows[0]["content_sha256"] == "abc123"
    assert rows[0]["card_hosted"] is False
    assert rows[0]["retest_available"] is False


def test_teaching_points_project_contiguous_published_episodes(monkeypatch, tmp_path):
    """74 集只从发布页投影；缺集不猜，不能把 pack 生命周期拆成 episode。"""
    import deeptutor.services.luban_lesson.read_model as read_model

    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    public_root = tmp_path / "luban-preview"
    station_root = public_root / "s05"
    station_root.mkdir(parents=True)
    (station_root / "lesson.html").write_text("lesson one", encoding="utf-8")
    (station_root / "lesson2.html").write_text("lesson two", encoding="utf-8")
    monkeypatch.setattr(read_model, "_PUBLIC_PREVIEW_ROOT", public_root)
    manifest = _write_manifest(tmp_path, [_S05], ["S05"])

    # 临时 manifest 不允许借用主仓发布目录；生产投影使用唯一 published root。
    assert list_teaching_points(manifest_path=manifest) == []

    # 直接钉住页级 projection helper，避免测试为了目录注入而伪造第二个 registry。
    lesson = {
        "pack_id": "S05",
        "title": _S05["title"],
        "card_hosted": True,
    }
    points = read_model._teaching_points_for_lesson(lesson)
    assert [(point["episode_index"], point["episode_label"]) for point in points] == [
        (1, "上集"),
        (2, "下集"),
    ]
    assert [point["lesson_file"] for point in points] == ["lesson.html", "lesson2.html"]
    assert all(point["card_url"].startswith("https://cdn.example.com/luban/s05/") for point in points)

    # 有 lesson3 而缺 lesson2 时整套 fail-closed，不让用户进入错序视频。
    (station_root / "lesson2.html").unlink()
    (station_root / "lesson3.html").write_text("lesson three", encoding="utf-8")
    assert read_model._teaching_points_for_lesson(lesson) == []


def test_real_published_catalog_has_40_topics_and_74_teaching_points(monkeypatch):
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    points = list_teaching_points()
    assert len(points) == 74
    assert len({point["pack_id"] for point in points}) == 40
    d14 = [point for point in points if point["pack_id"] == "D14"]
    assert [(point["episode_index"], point["episode_label"]) for point in d14] == [
        (1, "上集"), (2, "中集"), (3, "下集")
    ]
    assert all(point["card_url"] for point in points)


def test_combined_catalog_scans_each_green_pack_and_hosted_page_set_once(monkeypatch):
    import deeptutor.services.luban_lesson.read_model as read_model

    meta_calls = 0
    page_calls = 0
    original_meta = read_model._compiled_practice_meta
    original_pages = read_model._published_lesson_pages

    def counted_meta(pack_id):
        nonlocal meta_calls
        meta_calls += 1
        return original_meta(pack_id)

    def counted_pages(pack_id):
        nonlocal page_calls
        page_calls += 1
        return original_pages(pack_id)

    monkeypatch.setattr(read_model, "_compiled_practice_meta", counted_meta)
    monkeypatch.setattr(read_model, "_published_lesson_pages", counted_pages)

    lessons, points = list_lesson_catalog()

    assert len(lessons) == 41
    assert len(points) == 74
    assert meta_calls == 40  # E01 无 compiled authority，不伪造 meta 或覆盖 signed-only 路径。
    assert page_calls == 40


def test_episode_detail_selects_the_exact_published_page(monkeypatch):
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    vm = build_lesson_viewmodel("D14", episode_index=2)
    assert vm["teaching_episode"] == {"index": 2, "total": 3, "label": "中集"}
    assert "/d14/lesson2.html?v=" in vm["card_url"]
    with pytest.raises(LessonNotAvailable):
        build_lesson_viewmodel("D14", episode_index=4)


@pytest.mark.parametrize(
    ("pack_id", "episode_index", "expected_file"),
    [
        ("B02", 2, "practice2.html"),
        ("S01", 3, "practice3.html"),
        # A01 只有一份通用随堂练，两集都明确复用同一份成品练习。
        ("A01", 2, "practice.html"),
    ],
)
def test_pending_episode_practice_surfaces_remain_hidden(
    monkeypatch, pendingize_pack, pack_id, episode_index, expected_file
):
    """合成 pending 世界态:未签发 pack 的任何教学集都不得暴露练习入口。"""
    monkeypatch.setenv("LUBAN_LESSON_CARD_BASE", "https://cdn.example.com/luban")
    pendingize_pack(pack_id)

    vm = build_lesson_viewmodel(pack_id, episode_index=episode_index)

    assert expected_file
    assert vm["practice_url"] == ""


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


@pytest.mark.parametrize("blocklist_state", ["missing", "corrupt"])
def test_variant_revocation_authority_failure_fails_closed(
    tmp_path,
    blocklist_state,
):
    from deeptutor.services.luban_lesson import build_retest_items
    from deeptutor.services.luban_lesson.read_model import (
        retest_pool_meta,
        retest_supply_identity,
    )

    mp = _write_manifest(tmp_path, [_S05], ["S05"])
    (tmp_path / "_S05_variant_bank.v0.json").write_text(
        json.dumps({
            "status": "signed",
            "source_pack_sha256": "abc123",
            "variants": [
                {
                    "variant_id": "S05-B-000",
                    "rule_group": "B",
                    "surface": "s1",
                    "expected_ok": True,
                    "correct_statement": "c1",
                    "anchor": "kc:X:1",
                }
            ],
        }),
        encoding="utf-8",
    )
    blocklist = tmp_path / "_variant_blocklist.json"
    if blocklist_state == "missing":
        blocklist.unlink()
    else:
        blocklist.write_text("{not-json", encoding="utf-8")

    vm = build_lesson_viewmodel("S05", manifest_path=mp)

    assert vm["variant_retest"] == {"available": False, "count": 0}
    assert build_retest_items(
        "S05", user_id="u", day_index=1, manifest_path=mp
    ) == []
    assert retest_supply_identity(
        "S05", manifest_path=mp
    ) == {"kind": "", "digest": ""}
    assert retest_pool_meta("S05", manifest_path=mp) == {
        "core_total": 0,
        "rule_groups_total": 0,
    }


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


@pytest.mark.parametrize("pack_id", ["A01", "X01", "G03"])
def test_pending_v3_pack_never_advertises_light_practice_or_retest(
    pack_id: str, pendingize_pack
) -> None:
    """合成 pending 世界态:v3 未签发 pack 绝不对外宣传轻练/复测供给。"""
    pendingize_pack(pack_id)
    rows = {row["pack_id"]: row for row in list_green_lessons()}
    vm = build_lesson_viewmodel(pack_id)

    assert rows[pack_id]["retest_available"] is False
    assert vm["practice_surface"]["available"] is False
    assert vm["variant_retest"] == {
        "available": False,
        "count": 0,
        "bank_status": "compiled_v3",
        "source_pack_sha256": vm["content_sha256"],
    }


def test_real_manifest_has_mandatory_variant_revocation_authority():
    import deeptutor.services.luban_lesson.read_model as read_model

    assert read_model._variant_blocklist(
        read_model._MANIFEST_PATH.parent
    ) is not None


@pytest.mark.parametrize("pack_id", ["A01", "X01", "G03"])
def test_pending_candidate_pack_never_falls_back_to_signed_bank(
    pack_id: str, pendingize_pack
) -> None:
    """合成 pending 世界态:candidate 供给不得回退到任何 signed bank。"""
    from deeptutor.services.luban_lesson import build_retest_items

    pendingize_pack(pack_id)

    for mode in ("forward", "review"):
        assert build_retest_items(
            pack_id,
            user_id=f"qa_eval_{pack_id.lower()}_pending",
            day_index=2026194,
            limit=5,
            mode=mode,
        ) == []


@pytest.mark.parametrize("pack_id", ["A01", "X01", "G03"])
def test_compiled_artifact_is_same_supply_identity_for_forward_and_review(
    pack_id: str, pendingize_pack
) -> None:
    """合成 pending 世界态:forward/review 共用同一 compiled supply identity,
    未签发时两种 mode 同形拒发(空题集),identity 仍指向同一 artifact。"""
    from deeptutor.services.luban_lesson import (
        build_retest_items,
        resolve_retest_items,
        retest_supply_identity,
    )

    pendingize_pack(pack_id)
    assert build_retest_items(
        pack_id,
        user_id=f"qa_eval_{pack_id.lower()}_exact_selection",
        day_index=2026194,
        mode="forward",
    ) == []
    assert resolve_retest_items(pack_id, variant_ids=["not-eligible"], mode="review") == []
    forward = retest_supply_identity(pack_id, mode="forward")
    review = retest_supply_identity(pack_id, mode="review")
    assert forward["kind"] == "compiled_html" and len(forward["digest"]) == 64
    assert review == forward


def test_custom_manifest_without_compiled_capability_uses_its_signed_bank(
    tmp_path: Path,
) -> None:
    from deeptutor.services.luban_lesson import build_retest_items

    pack = dict(_S05, pack_id="F16", title="F16", content_sha256="stale-pack-sha")
    mp = _write_manifest(tmp_path, [pack], ["F16"])
    (tmp_path / "_F16_variant_bank.v0.json").write_text(
        json.dumps(
            {
                "status": "signed",
                "source_pack_sha256": "stale-pack-sha",
                "variants": [
                    {
                        "variant_id": "F16-legacy",
                        "rule_group": "legacy",
                        "surface": "旧题",
                        "expected_ok": True,
                        "correct_statement": "旧答案",
                        "anchor": "kc:F16",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    items = build_retest_items(
        "F16", user_id="qa_eval_f16_sha_drift", day_index=1,
        mode="forward", manifest_path=mp,
    )
    assert [item["variant_id"] for item in items] == ["F16-legacy"]


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
    vm = build_lesson_viewmodel("S05", manifest_path=mp)
    assert vm["variant_retest"]["count"] == 5
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


def test_retest_receipt_path_resolves_through_single_receipt_authority(monkeypatch):
    """receipt 桥接经唯一 builder 委托 resolve_projection_receipt(带 surface+sha 双锚)。"""
    import deeptutor.services.luban_lesson.read_model as read_model

    monkeypatch.setattr(
        read_model,
        "build_lesson_viewmodel",
        lambda pack_id, manifest_path=None: {
            "pack_id": "F16",
            "content_sha256": "1" * 64,
            "variant_retest": {"available": False},
        },
    )
    monkeypatch.setattr(read_model, "is_compiled_practice_pack", lambda pack_id: True)
    rows = [{"variant_id": f"F16-html-q{index}"} for index in range(5)]
    captured = {}

    def _resolve(pack_id, receipt, *, surface_id="", expected_pack_sha256=""):
        captured.update(
            pack_id=pack_id,
            receipt=receipt,
            surface_id=surface_id,
            expected_pack_sha256=expected_pack_sha256,
        )
        return rows

    monkeypatch.setattr(read_model, "resolve_projection_receipt", _resolve)

    items = read_model.build_retest_items(
        "f16",
        user_id="u",
        day_index=1,
        mode="forward",
        practice_surface="practice.html",
        projection_receipt="receipt-token",
    )

    assert items is rows
    assert captured == {
        "pack_id": "F16",
        "receipt": "receipt-token",
        "surface_id": "practice.html",
        "expected_pack_sha256": "1" * 64,
    }


def test_retest_receipt_outside_compiled_forward_fails_closed(monkeypatch):
    """receipt 只对 compiled forward 生效;review 模式/非编译包一律 fail-close 重取。"""
    from deeptutor.services.luban_lesson.practice_html import PracticeHtmlInvalid
    import deeptutor.services.luban_lesson.read_model as read_model

    monkeypatch.setattr(
        read_model,
        "build_lesson_viewmodel",
        lambda pack_id, manifest_path=None: {
            "pack_id": "F16",
            "content_sha256": "1" * 64,
            "variant_retest": {"available": False},
        },
    )

    monkeypatch.setattr(read_model, "is_compiled_practice_pack", lambda pack_id: True)
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        read_model.build_retest_items(
            "F16",
            user_id="u",
            day_index=1,
            mode="review",
            projection_receipt="receipt-token",
        )

    monkeypatch.setattr(read_model, "is_compiled_practice_pack", lambda pack_id: False)
    with pytest.raises(PracticeHtmlInvalid, match="content_updated_retake"):
        read_model.build_retest_items(
            "F16",
            user_id="u",
            day_index=1,
            mode="forward",
            projection_receipt="receipt-token",
        )


def test_signed_first_batch_pack_advertises_retest_supply() -> None:
    """N01 首批签发后,读模型必须点亮同一签发供给(不回退 signed bank)。"""
    rows = {row["pack_id"]: row for row in list_green_lessons()}
    assert rows["N01"]["retest_available"] is True
    vm = build_lesson_viewmodel("N01")
    assert vm["practice_surface"]["available"] is True
    assert vm["variant_retest"]["available"] is True
    assert vm["variant_retest"]["bank_status"] == "compiled_v3"
