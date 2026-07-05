"""考点卡 bank 编译器域测试——确定性派生 + fail-closed + gate 100%。

对真实签发 pack（S05/A01/F16/J01/N01 五个绿灯站）跑真实派生：
1. 确定性重建：同输入重跑逐字段一致（禁 LLM/时钟/随机泄入内容面）；
2. fail-closed：无 quote 锚不成卡、非🟢行不成卡（dropped_rows 留痕）；
3. gate：quote 逐字命中 compiled_source + front 去重 + 禁审视词，100% 通过；
4. bank 恒 candidate（签发唯一入口 = promote_variant_bank.py --kind concept_cards）；
5. 磁盘已产 bank 与重建一致（防 pack/builder 改动后 bank 落后）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILDER = REPO / "scripts" / "build_luban_concept_card_bank.py"
_spec = importlib.util.spec_from_file_location("build_luban_concept_card_bank", BUILDER)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["build_luban_concept_card_bank"] = _mod
_spec.loader.exec_module(_mod)

TARGET_PACKS = ("S05", "A01", "F16", "J01", "N01")


@pytest.mark.parametrize("pack_id", TARGET_PACKS)
def test_deterministic_rebuild(pack_id):
    first_cards, first_dropped, first_sha = _mod.derive_cards(pack_id)
    second_cards, second_dropped, second_sha = _mod.derive_cards(pack_id)
    assert first_cards == second_cards
    assert first_dropped == second_dropped
    assert first_sha == second_sha
    assert first_cards, "五个目标站都必须至少产出 1 卡"


@pytest.mark.parametrize("pack_id", TARGET_PACKS)
def test_gate_100_percent_and_quote_verbatim(pack_id):
    cards, _, _ = _mod.derive_cards(pack_id)
    gate = _mod.run_gate(pack_id, cards)
    assert gate["passed"] == gate["total"] == len(cards)
    assert gate["quote_mismatches"] == []
    assert gate["duplicate_cards"] == []
    assert gate["forbidden_words"] == []
    # quote 逐字命中 compiled_source（独立于 run_gate 再核一遍，防 gate 自证）
    points = _mod._point_index(pack_id)
    for card in cards:
        assert card["quote"] == points[card["point_id"]]["quote"]
        assert card["front"]
        assert card["point_id"].startswith("kc:")


@pytest.mark.parametrize("pack_id", TARGET_PACKS)
def test_fail_closed_drops_are_honest(pack_id):
    """掉卡必须留痕且只许三种原因（无 quote / 非🟢 / point 重复）。"""
    _, dropped, _ = _mod.derive_cards(pack_id)
    allowed = {"not_green", "no_verbatim_quote", "duplicate_point_id"}
    assert {d["reason"] for d in dropped} <= allowed


@pytest.mark.parametrize("pack_id", TARGET_PACKS)
def test_on_disk_bank_matches_rebuild_and_is_candidate(pack_id):
    """已产 bank 必须与确定性重建一致，且未经签发恒 candidate。"""
    bank_path = (
        REPO / "docs" / "原始数据" / "考点原料" / "成品"
        / _mod.BANK_TEMPLATE.format(pack_id=pack_id)
    )
    assert bank_path.exists(), f"{pack_id} 卡池尚未产出"
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    payload = _mod.build_payload(pack_id)
    assert _mod._stable_view(bank) == _mod._stable_view(payload)
    assert bank["status"] in ("candidate", "signed")
    assert bank["schema_version"] == "luban-concept-card-bank"
    assert bank["gate"]["passed"] == bank["gate"]["total"] > 0


def test_forbidden_words_gate_catches():
    """禁审视词（看穿/识破/揭穿/露馅）落在模板侧字段必须挡下。"""
    bad = [{
        "card_id": "S05:kc:x:0", "front": "一眼看穿送电顺序",
        "key_gist": "x", "quote": "y", "point_id": "kc:x:0", "source_ref": {},
    }]
    gate = _mod.run_gate("S05", bad)
    assert gate["forbidden_words"] == ["S05:kc:x:0"]
    assert gate["passed"] == 0


def test_builder_never_writes_signed():
    """builder 源码不得出现签发字面量赋值（status 恒 candidate，人闸独占翻牌）。"""
    body = BUILDER.read_text(encoding="utf-8")
    assert '"status": "candidate"' in body
    assert '"status": "signed"' not in body
