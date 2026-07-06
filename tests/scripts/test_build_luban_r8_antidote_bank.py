"""R8 解药 bank 编译器域测试——确定性派生 + fail-closed + gate 100%。

对真实签发 pack 跑真实派生（block 体例 A01 + 表体例 Codex-镜头批）：
1. 确定性重建：同输入重跑逐字段一致（禁 LLM/时钟/随机泄入内容面）；
2. fail-closed：三色门（🔴待验证/无绿锚）、码 ∉ registry、码待核验、锚不 resolve
   一律丢（dropped_rows 留痕）；
3. gate：code ∈ ERROR_CODE_REGISTRY + kc 锚 resolve + 禁审视词，100% 通过；
4. bank 恒 candidate（签发唯一入口 = promote_variant_bank.py --kind antidote）；
5. 磁盘已产 bank 与重建一致。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILDER = REPO / "scripts" / "build_luban_r8_antidote_bank.py"
_spec = importlib.util.spec_from_file_location("build_luban_r8_antidote_bank", BUILDER)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["build_luban_r8_antidote_bank"] = _mod
_spec.loader.exec_module(_mod)

from deeptutor.contracts.error_codes import ERROR_CODE_REGISTRY

# block 体例(A01) + 表体例(C01/E01/F16/S05/X03) 混样
TARGET_PACKS = ("A01", "C01", "E01", "F16", "S05", "X03")
# pack 明示「错因码待注册表核准」→ 全表 fail-closed 抽象（诚实空）
ABSTAIN_PACKS = ("N02", "K01")


@pytest.mark.parametrize("pack_id", TARGET_PACKS)
def test_deterministic_rebuild(pack_id):
    a1, k1, d1, s1 = _mod.derive_antidotes(pack_id)
    a2, k2, d2, s2 = _mod.derive_antidotes(pack_id)
    assert a1 == a2 and k1 == k2 and d1 == d2 and s1 == s2
    assert k1, "目标站都必须至少产出 1 条解药"


@pytest.mark.parametrize("pack_id", TARGET_PACKS)
def test_gate_100_and_codes_registered_and_anchor_resolves(pack_id):
    antidotes, kept, _, _ = _mod.derive_antidotes(pack_id)
    gate = _mod.run_gate(pack_id, kept)
    assert gate["passed"] == gate["total"] == len(kept)
    assert gate["code_unregistered"] == []
    assert gate["anchor_unresolved"] == []
    assert gate["forbidden_words"] == []
    # 独立于 run_gate 再核一遍（防 gate 自证）：每条码 ∈ registry、锚 ∈ compiled_source
    points = _mod._point_ids(pack_id)
    for row in kept:
        assert row["error_codes"]
        for code in row["error_codes"]:
            assert code in ERROR_CODE_REGISTRY
        assert row["textbook_ref"] in points
        assert row["mental_model"]
    # 键 = error_code，投影形状 = {mental_model, textbook_ref}
    for code, rows in antidotes.items():
        assert code in ERROR_CODE_REGISTRY
        for r in rows:
            assert r["mental_model"] and r["textbook_ref"].startswith("kc:")


def test_a01_matches_plan_example_and_drops_r8_1_amber_red():
    """A01 block 体例：R8-1（🟡锚 + 🔴待验证）三色门挡掉；E07=R8-4 逐字。"""
    antidotes, kept, dropped, _ = _mod.derive_antidotes("A01")
    assert {d["r8_id"] for d in dropped if d["reason"] == "antidote_amber_red"} == {
        "A01:R8-1"
    }
    e07 = antidotes["E07"][0]
    assert e07["r8_id"] == "A01:R8-4"
    assert e07["textbook_ref"] == "kc:1A434020_085_0136:1"
    assert "监理单位组织" in e07["mental_model"]


@pytest.mark.parametrize("pack_id", ABSTAIN_PACKS)
def test_abstain_packs_fail_closed_empty(pack_id):
    """pack 明示错因码待注册表核准 → 派生 0（fail-closed，禁把待核验码当已验证采信）。"""
    with pytest.raises(_mod.BankBuildError):
        _mod.build_payload(pack_id)
    _, kept, dropped, _ = _mod.derive_antidotes(pack_id)
    assert kept == []
    assert dropped and all(d["reason"] == "code_unverified" for d in dropped)


def test_c04_non_registry_codes_fail_closed():
    """C04 §6 用自造码（ERR_*）+ 省略锚 → 无一成解药（诚实源缺口）。"""
    _, kept, _, _ = _mod.derive_antidotes("C04")
    assert kept == []


def test_forbidden_words_gate_catches():
    """禁审视词落在 authored 文（解药/现象/心智）必须挡下。"""
    bad = [{
        "r8_id": "A01:R8-X", "error_codes": ["E07"],
        "mental_model": "一眼看穿考生软肋", "textbook_ref": "kc:1A434020_085_0136:1",
        "phenomenon": "", "wrong_model": "",
    }]
    gate = _mod.run_gate("A01", bad)
    assert gate["forbidden_words"] == ["A01:R8-X"]
    assert gate["passed"] == 0


def test_unregistered_code_gate_catches():
    bad = [{
        "r8_id": "A01:R8-Y", "error_codes": ["E99"],
        "mental_model": "x", "textbook_ref": "kc:1A434020_085_0136:1",
        "phenomenon": "", "wrong_model": "",
    }]
    gate = _mod.run_gate("A01", bad)
    assert "A01:R8-Y:E99" in gate["code_unregistered"]
    assert gate["passed"] == 0


def test_on_disk_bank_matches_rebuild_and_is_candidate():
    bank_path = (
        REPO / "docs" / "原始数据" / "考点原料" / "成品"
        / _mod.BANK_TEMPLATE.format(pack_id="A01")
    )
    assert bank_path.exists()
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    payload = _mod.build_payload("A01")
    assert _mod._stable_view(bank) == _mod._stable_view(payload)
    assert bank["status"] in ("candidate", "signed")
    assert bank["schema_version"] == "luban-antidote-bank"
    assert bank["gate"]["passed"] == bank["gate"]["total"] > 0


def test_builder_never_writes_signed():
    body = BUILDER.read_text(encoding="utf-8")
    assert '"status": "candidate"' in body
    assert '"status": "signed"' not in body
