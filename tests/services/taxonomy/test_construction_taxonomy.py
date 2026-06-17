from __future__ import annotations

from pathlib import Path

from deeptutor.services.taxonomy.construction_taxonomy import (
    chapter_prefix_labels,
    display_taxonomy_label,
    taxonomy_label,
    taxonomy_source_metadata,
    taxonomy_tree_stats,
)


def test_construction_taxonomy_labels_known_codes() -> None:
    assert taxonomy_label("1A432000") == "工程招标投标与合同管理"
    assert taxonomy_label("1A432011") == "招标方式与程序"
    assert taxonomy_label("1A412030") == "建筑功能材料"
    # book-derived leaf with uppercase segment (2026 rebuild)
    assert taxonomy_label("1A412010-B103") == "石材"


def test_construction_taxonomy_falls_back_to_nearest_parent() -> None:
    assert taxonomy_label("1A432019") == "工程招标投标"
    assert taxonomy_label("1A438999") == "施工资源管理"


def test_display_taxonomy_label_can_hide_machine_code() -> None:
    assert display_taxonomy_label("1A432000") == "工程招标投标与合同管理"
    assert display_taxonomy_label("1A432000", with_code=True) == "工程招标投标与合同管理（1A432000）"


def test_construction_taxonomy_reads_compiled_final_cleaned_authority() -> None:
    source = taxonomy_source_metadata()

    # single-authority: A recompiled from the canonical 2026 source (identical (code,name) content to
    # the legacy docs/ copy — verified), now projecting concept_registry deprecations.
    # taxonomy-frozen-v1.1-20260613: canonical sha is pinned by the freeze declaration
    # (TAXONOMY_FREEZE.md); changes only through the freeze change policy.
    # v1.1 = first weekly-window coverage expansion (+78 E-suffixed exam-axis leaves).
    assert source["sha256"] == "26dbb542b31601d6b3255d53463d0007c0c7eaea5a24ad9c338b3742baa976c8"
    assert source["path"].endswith("FINAL_CLEANED_TAXONOMY2026.json")


def test_construction_taxonomy_tree_stats_preserve_original_outline_counts() -> None:
    stats = taxonomy_tree_stats()

    # taxonomy-frozen-v1.1-20260613 (first weekly-window coverage expansion: +78 E-suffixed
    # exam-axis leaves derived from the 2021-2025 real-exam node prefix gap, 77 textbook +
    # 1 lecture lane, 1 unfilled work order): codes unique
    assert stats["total_nodes"] == 2116
    assert stats["leaf_nodes"] == 1976
    assert stats["coded_nodes"] == 2116
    assert stats["unique_codes"] == 2116
    assert stats["duplicate_code_rows"] == 0


def test_wechat_taxonomy_shadow_is_derived_from_backend_prefix_labels() -> None:
    repo = Path(__file__).parents[3]
    expected = chapter_prefix_labels()

    for relative_path in (
        "wx_miniprogram/utils/taxonomy.js",
        "yousenwebview/packageDeeptutor/utils/taxonomy.js",
    ):
        source = (repo / relative_path).read_text(encoding="utf-8")
        for code in ("1A411", "1A412", "1A413", "1A438"):
            assert f'"{code}": "{expected[code]}"' in source


def test_student_taxonomy_label_never_leaks_code():
    # SINGLE AUTHORITY for student-facing display: canonical Chinese name, or '' on miss — NEVER a code.
    from deeptutor.services.taxonomy.taxonomy_authority import student_taxonomy_label

    assert student_taxonomy_label("1A432000") == "工程招标投标与合同管理"   # resolvable -> Chinese
    # unresolvable / non-concept codes -> '' (caller hides), NEVER the raw code shown to a learner
    for code in ["1A420000", "E02", "M03", "1B411000", "EXAM_1A432000_P0016_02::E0::Q1-1"]:
        out = student_taxonomy_label(code)
        assert out == "" or "工程" in out or "建筑" in out  # Chinese-or-empty
        assert code not in out                                # the literal code must never appear


def test_student_facing_label_cjk_heuristic_never_leaks_ascii_code():
    from deeptutor.services.taxonomy.taxonomy_authority import student_facing_label

    assert student_facing_label("1A432000") == "工程招标投标与合同管理"   # resolvable code -> Chinese
    assert student_facing_label("地基基础承载力") == "地基基础承载力"        # Chinese passes through
    # any ASCII-only machine code/id -> Chinese or '' (generic) — NEVER the raw string
    for code in ["12A412000", "knowledge_node_7f3a9b2c-1", "Q1-1", "R12", "1B412000",
                 "EXAM_1A432000_P0016_02::E0::Q1-1", "abc123", "E02"]:
        out = student_facing_label(code, generic="相关考点")
        assert code not in out


def test_scrub_codes_for_student_handles_cjk_adjacent_codes():
    from deeptutor.services.taxonomy.taxonomy_authority import scrub_codes_for_student

    # the code is wedged directly against Chinese (no ASCII boundary) — must still be scrubbed
    assert "1A412000" not in scrub_codes_for_student("项目1A412000管理")
    assert "1B412000" not in scrub_codes_for_student("考点1A412000和1B412000")
    assert scrub_codes_for_student("纯中文没有代码") == "纯中文没有代码"


def test_object_display_never_dangling_colon_or_raw_code():
    from deeptutor.services.learner_state.learning_brain_read_model import _object_display

    for oid, ot in [("1A420000", "concept"), ("EXAM_x::abcdef", "rubric_item"), ("weird_obj_id", "")]:
        title = _object_display(oid, ot)["display_title"]
        assert not title.endswith("：")          # no dangling colon
        assert oid not in title                   # no raw code/id in the learner-facing title


def test_is_non_topic_label_rejects_non_textbook_front_back_matter_and_marketing():
    # Front/back-matter + marketing noise from textbook OCR must NEVER surface as a learner topic.
    from deeptutor.services.taxonomy.textbook_directory import is_non_topic_label

    for noise in ["讲义封底免费听课资源", "扫码领取课程资料", "关注公众号免费试听",
                  "讲义封面", "版权页", "增值服务二维码", "直播回放入口", "押题密卷领取"]:
        assert is_non_topic_label(noise) is True, noise
    # real 一建 knowledge points (some contain 资源/管理/技术) must be KEPT
    for topic in ["建设工程项目资源管理", "施工现场临时用电", "工程招标投标与合同管理",
                  "施工技术资料管理", "人力资源与劳务管理"]:
        assert is_non_topic_label(topic) is False, topic


def test_canonical_topic_options_and_exact_resolution():
    from deeptutor.services.taxonomy.textbook_directory import (
        canonical_topic_options,
        resolve_canonical_option,
    )

    opts = canonical_topic_options()
    assert len(opts) >= 13 and all(o.get("name") and o.get("code") for o in opts)
    # exact chapter/section/alias resolution; non-option -> None (no fuzzy)
    assert resolve_canonical_option("工程招标投标与合同管理")["code"] == "1A432"
    assert resolve_canonical_option("屋面与防水工程施工")["kind"] == "section"
    assert resolve_canonical_option("建筑设计与构造")  # chapter alias
    assert resolve_canonical_option("专家论证程序") is None
    assert resolve_canonical_option("讲义封底免费听课资源") is None
