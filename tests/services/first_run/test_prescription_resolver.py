from __future__ import annotations

from deeptutor.services.first_run.prescription_resolver import (
    resolve_first_run_prescription,
)


def test_resolver_selects_only_source_backed_green_pack_with_signed_retest_supply() -> None:
    resolved = resolve_first_run_prescription([
        {"question_id": "first_run.v1:qigu_gebu", "is_correct": False},
        {"question_id": "first_run.v1:zhiliang_jihua", "is_correct": False},
    ])

    assert resolved["target_pack_id"] == "F16"
    assert resolved["supply_verified"] is True
    assert resolved["mapping_refs"]


def test_resolver_falls_back_honestly_when_missed_item_has_no_pack_mapping() -> None:
    resolved = resolve_first_run_prescription([
        {"question_id": "first_run.v1:zhiliang_jihua", "is_correct": False},
        {"question_id": "first_run.v1:tianchongqiang_fangbie", "is_correct": True},
    ])

    assert resolved["target_pack_id"] == ""
    assert resolved["focus_item"]["question_id"] == "first_run.v1:zhiliang_jihua"
