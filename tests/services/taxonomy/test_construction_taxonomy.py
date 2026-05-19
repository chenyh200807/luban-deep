from __future__ import annotations

from deeptutor.services.taxonomy.construction_taxonomy import display_taxonomy_label, taxonomy_label


def test_construction_taxonomy_labels_known_codes() -> None:
    assert taxonomy_label("1A432000") == "工程招标投标与合同管理"
    assert taxonomy_label("1A432011") == "招标方式与程序"
    assert taxonomy_label("1A412030") == "建筑功能材料"


def test_construction_taxonomy_falls_back_to_nearest_parent() -> None:
    assert taxonomy_label("1A432019") == "工程招标投标"
    assert taxonomy_label("1A438999") == "施工资源管理"


def test_display_taxonomy_label_can_hide_machine_code() -> None:
    assert display_taxonomy_label("1A432000") == "工程招标投标与合同管理"
    assert display_taxonomy_label("1A432000", with_code=True) == "工程招标投标与合同管理（1A432000）"
