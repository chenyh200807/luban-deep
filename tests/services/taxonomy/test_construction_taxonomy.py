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
    assert taxonomy_label("1A411011-02-d") == "建筑高度计算方法"


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
    assert source["sha256"] == "38249e82e4d7a38c5b50341bb0c75ef12e599850381a11160121a8dbbbd09e81"
    assert source["path"].endswith("FINAL_CLEANED_TAXONOMY2026.json")


def test_construction_taxonomy_tree_stats_preserve_original_outline_counts() -> None:
    stats = taxonomy_tree_stats()

    assert stats["total_nodes"] == 3735
    assert stats["leaf_nodes"] == 2786
    assert stats["coded_nodes"] == 3733
    assert stats["unique_codes"] == 1284
    assert stats["duplicate_code_rows"] == 2449


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
