"""R6 精确挖空 bank 编译器域测试——确定性派生 + fail-closed + gate 100%。

对真实签发 pack（A01：唯一有 required_terms 列 + 逐行 kc 锚的 R5 表）跑真实派生：
1. 确定性重建：同输入重跑逐字段一致；
2. 挖空 = 纯确定性字符串操作（required_terms 首命中→末命中跨度替 blank）；
3. fail-closed：锚不 resolve / required_terms 字面对不上 statement 一律丢（留痕，不 LLM 补）；
4. gate：锚 resolve + 被挖词回填命中 + 禁审视词，100% 通过；
5. bank 恒 candidate（签发入口 = promote_variant_bank.py --kind cloze）；
6. 源缺 required_terms 列的 pack fail-closed 抛错（诚实源缺口，禁 LLM 造）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILDER = REPO / "scripts" / "build_luban_r6_cloze_bank.py"
_spec = importlib.util.spec_from_file_location("build_luban_r6_cloze_bank", BUILDER)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["build_luban_r6_cloze_bank"] = _mod
_spec.loader.exec_module(_mod)


def test_deterministic_rebuild_a01():
    s1, d1, sha1 = _mod.derive_cloze("A01")
    s2, d2, sha2 = _mod.derive_cloze("A01")
    assert s1 == s2 and d1 == d2 and sha1 == sha2
    assert s1, "A01 必须至少产出 1 句挖空"


def test_gate_100_and_anchor_resolves_and_terms_in_sentence():
    sentences, _, _ = _mod.derive_cloze("A01")
    gate = _mod.run_gate("A01", sentences)
    assert gate["passed"] == gate["total"] == len(sentences)
    assert gate["anchor_unresolved"] == []
    assert gate["term_not_in_sentence"] == []
    assert gate["forbidden_words"] == []
    points = _mod._point_ids("A01")
    for s in sentences:
        assert s["point_id"] in points  # 锚 resolve 到 compiled_source
        # 被挖词必须能从残句 + hint 拼回（挖空可复现，无凭空 blank）
        blank_terms = [t.strip() for t in s["blank_hint"].split("/") if t.strip()]
        rejoined = s["text_before"] + s["blank_hint"] + s["text_after"]
        assert blank_terms and all(t in rejoined for t in blank_terms)


def test_c4_1_matches_plan_example():
    """挖空派生 = 把 required_terms 首命中→末命中跨度替 blank（与计划 §2.2 例逐字一致）。"""
    sentences, _, _ = _mod.derive_cloze("A01")
    c41 = next(s for s in sentences if s["cloze_id"] == "A01:C4-1")
    assert c41["point_id"] == "kc:1A434020_085_0136:0"
    assert c41["text_before"] == "实体检验四内容："
    assert c41["blank_hint"] == "混凝土强度 / 钢筋保护层 / 尺寸偏差"
    assert c41["text_after"] == "、合同约定项目"


def test_fail_closed_drops_are_honest():
    """掉句只许四种原因（锚不 resolve / 词对不上句 / 无关键词 / 去重）。"""
    _, dropped, _ = _mod.derive_cloze("A01")
    allowed = {
        "anchor_unresolved", "term_not_in_sentence",
        "no_required_terms", "duplicate_cloze_id",
    }
    assert dropped, "A01 应有 fail-closed 掉句留痕"
    assert {d["reason"] for d in dropped} <= allowed


def test_pack_without_required_terms_column_fail_closed():
    """无 required_terms 列的 pack = 精确挖空源缺失，fail-closed 抛错（禁 LLM 造）。"""
    with pytest.raises(_mod.BankBuildError, match="required_terms"):
        _mod.derive_cloze("C01")


def test_carve_helper_first_to_last_span():
    carved = _mod._carve("四内容：甲、乙、丙、丁", ["甲", "丙"])
    assert carved["text_before"] == "四内容："
    assert carved["blank_hint"] == "甲 / 丙"
    assert carved["text_after"] == "、丁"
    assert _mod._carve("完全不含关键词", ["甲"]) is None


def test_forbidden_words_gate_catches():
    bad = [{
        "cloze_id": "A01:CX", "point_id": "kc:x:0",
        "text_before": "一眼看穿", "blank_hint": "甲", "text_after": "",
    }]
    gate = _mod.run_gate("A01", bad)
    assert gate["forbidden_words"] == ["A01:CX"]
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
    assert bank["schema_version"] == "luban-cloze-bank"
    assert bank["recall_prompt"] == _mod.RECALL_PROMPT
    assert bank["gate"]["passed"] == bank["gate"]["total"] > 0


def test_builder_never_writes_signed():
    body = BUILDER.read_text(encoding="utf-8")
    assert '"status": "candidate"' in body
    assert '"status": "signed"' not in body
