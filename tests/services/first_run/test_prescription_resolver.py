"""处方源头必须对齐供给真值(契约 first-run §7:question→pack 映射由
source-backed resolver 与当前 green+signed-retest supply 共同验证)。

供给用 stub 控制(disk-agnostic):2026-07-16 QA 死证 = F16/X03 停发后
硬编码单 pack 映射恒产空 target,新用户首跑处方永不可执行。
"""

from __future__ import annotations

import pytest

from deeptutor.services.first_run import prescription_resolver


def _stub_supply(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, object]]) -> None:
    monkeypatch.setattr(prescription_resolver, "list_green_lessons", lambda: rows)


def test_resolver_prefers_first_supply_ready_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 恢复回归:F16 供给恢复后仍按候选序优先 F16(原行为不变)。
    _stub_supply(monkeypatch, [
        {"pack_id": "F16", "retest_available": True},
        {"pack_id": "N01", "retest_available": True},
    ])

    resolved = prescription_resolver.resolve_first_run_prescription([
        {"question_id": "first_run.v1:qigu_gebu", "is_correct": False},
        {"question_id": "first_run.v1:zhiliang_jihua", "is_correct": False},
    ])

    assert resolved["target_pack_id"] == "F16"
    assert resolved["supply_verified"] is True
    assert resolved["mapping_refs"]


def test_resolver_falls_through_to_next_candidate_when_head_pack_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 红测试②:F16/X03 停发(retest_available=False)时处方不产空 target——
    # 按能力真值过滤候选序列,落到下一个 supply-ready 候选。
    _stub_supply(monkeypatch, [
        {"pack_id": "F16", "retest_available": False},
        {"pack_id": "X03", "retest_available": False},
        {"pack_id": "N01", "retest_available": True},
    ])

    resolved = prescription_resolver.resolve_first_run_prescription([
        {"question_id": "first_run.v1:qigu_gebu", "is_correct": False},
        {"question_id": "first_run.v1:zhuangpeishi_laji", "is_correct": False},
    ])

    assert resolved["target_pack_id"] == "N01"
    assert resolved["supply_verified"] is True
    assert resolved["mapping_refs"]


def test_resolver_produces_no_pack_binding_when_no_candidate_is_supply_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 全候选不可用 → 诚实无 pack 绑定(不臆造、不硬编码字面特权)。
    _stub_supply(monkeypatch, [
        {"pack_id": "F16", "retest_available": False},
        {"pack_id": "X03", "retest_available": False},
        {"pack_id": "N01", "retest_available": False},
    ])

    resolved = prescription_resolver.resolve_first_run_prescription([
        {"question_id": "first_run.v1:qigu_gebu", "is_correct": False},
    ])

    assert resolved["target_pack_id"] == ""
    assert resolved["supply_verified"] is False
    assert resolved["mapping_refs"] == []
    assert resolved["focus_item"]["question_id"] == "first_run.v1:qigu_gebu"


def test_resolver_falls_back_honestly_when_missed_item_has_no_pack_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_supply(monkeypatch, [
        {"pack_id": "F16", "retest_available": True},
        {"pack_id": "N01", "retest_available": True},
    ])

    resolved = prescription_resolver.resolve_first_run_prescription([
        {"question_id": "first_run.v1:zhiliang_jihua", "is_correct": False},
        {"question_id": "first_run.v1:tianchongqiang_fangbie", "is_correct": True},
    ])

    assert resolved["target_pack_id"] == ""
    assert resolved["focus_item"]["question_id"] == "first_run.v1:zhiliang_jihua"
