"""F16 变体池生成器域测试（双轮 §8 红线：编译期预生成、禁运行时现编）。

守三件事：
1. 一致性门——生成/校验双路互证零失配，产量按封闭域自然枚举（核心 ≥40）。
2. 争议层零泄漏——🔵推理层(jury HI#2 成因/诊断)与🔴编造层(C2 蓄水/淋水)禁入池；
   区分锚 🔵 的防混答变体必须 extension=true 且核心变体全部挂 🟢 锚。
3. 题面唯一 + 产物锚定——artifact 与生成器同步、source_pack_sha256 对得上当前 pack。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "build_luban_f16_variant_bank.py"
_spec = importlib.util.spec_from_file_location("build_luban_f16_variant_bank", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["build_luban_f16_variant_bank"] = _mod
_spec.loader.exec_module(_mod)

_GREEN_ANCHOR_MARKS = ("kc:1A434000_076_0119:0", "kc:1A434000_068_0104:0", "{2017,案例二}")


def test_consistency_gate_zero_defects_and_closed_domain_counts() -> None:
    """一致性门零失配/零泄漏/零重复；产量=封闭域自然枚举（不凑数不注水）。"""
    variants = _mod.build_variants()
    gate = _mod.run_gate(variants)
    assert gate["verdict_mismatches"] == []
    assert gate["contested_leaks"] == []
    assert gate["duplicate_surfaces"] == []
    assert gate["passed"] == gate["total"] == len(variants)
    # 封闭域自然产量: A 分档 6直径×2法=12 + 不分档政策2; B 工序 2皮×(1全+4点名漏步+1点名顺序)=12;
    # C 检查项 9项×2极性=18; 外延 X 防混答 3
    per_group = {g: sum(1 for v in variants if v["rule_group"] == g)
                 for g in {v["rule_group"] for v in variants}}
    assert per_group == {"A-diameter": 12, "A-policy": 2, "B-seq": 12,
                         "C-check": 18, "X-mix": 3}
    core = [v for v in variants if not v["extension"]]
    assert len(core) == 44 >= 40
    assert len(variants) == 47


def test_contested_and_inference_layer_zero_leak() -> None:
    """🔴编造(蓄水/淋水)与🔵推理(成因/根因/复发/诊断/养护)零泄漏；
    核心变体锚必须含 🟢 锚定层；区分锚🔵 的防混答变体必须全部 extension=true。"""
    variants = _mod.build_variants()
    for v in variants:
        for token in _mod._CONTESTED_TOKENS:
            assert token not in v["surface"], (v["variant_id"], token)
            assert token not in v["correct_statement"], (v["variant_id"], token)
    for v in variants:
        if not v["extension"]:
            assert any(m in v["anchor"] for m in _GREEN_ANCHOR_MARKS), v["variant_id"]
            # 核心变体锚不得引用 🔵 区分/相邻锚（流淌/搭接）
            assert "1A434000_076_0118" not in v["anchor"], v["variant_id"]
            assert "1A413030" not in v["anchor"], v["variant_id"]
    # 组 D 防混答（区分锚 🔵）整组外延，核心复测不发
    assert all(v["extension"] for v in variants if v["rule_group"] == "X-mix")


def test_independent_verdict_covers_every_variant() -> None:
    """校验器对每个变体都能独立推导判定（无 None 盲区），且与生成侧互证一致。"""
    variants = _mod.build_variants()
    for v in variants:
        iv = _mod._independent_verdict(v)
        assert iv is not None, v["variant_id"]
        assert iv == v["expected_ok"], v["variant_id"]


def test_surfaces_unique_and_shape_complete() -> None:
    """题面唯一；每个变体带 runtime 抽取所需完整字段（read_model 消费面）。"""
    variants = _mod.build_variants()
    surfaces = [v["surface"] for v in variants]
    assert len(surfaces) == len(set(surfaces))
    required = {"variant_id", "rule_group", "surface", "params", "expected_ok",
                "correct_statement", "anchor", "extension"}
    for v in variants:
        assert required <= set(v), v.get("variant_id")
        assert isinstance(v["expected_ok"], bool)


def test_check_mode_exits_zero() -> None:
    """--check CI 模式退出码 0（可挂门）。"""
    proc = subprocess.run([sys.executable, str(SCRIPT), "--check"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_artifact_in_sync_with_generator_and_pack() -> None:
    """已提交产物 = 生成器当前输出（防漂移）；sha 锚定当前 pack；status 诚实为 candidate。"""
    assert _mod.OUT_PATH.exists(), "产物缺失: 先跑 python3 scripts/build_luban_f16_variant_bank.py"
    bank = json.loads(_mod.OUT_PATH.read_text(encoding="utf-8"))
    assert bank["schema_version"] == "luban-f16-variant-bank"
    assert bank["pack_id"] == "F16"
    assert bank["status"] == "candidate"
    assert bank["source_pack_sha256"] == hashlib.sha256(_mod.PACK_PATH.read_bytes()).hexdigest()
    assert bank["variants"] == _mod.build_variants()
    assert bank["gate"]["verdict_mismatches"] == []
    assert bank["gate"]["contested_leaks"] == []
    assert bank["gate"]["duplicate_surfaces"] == []


def test_rebuild_preserves_baked_decisions_by_id_and_content(tmp_path, monkeypatch):
    """重建保留合并：bake 进 bank 的 decision 块在 builder 重跑后原位保留；
    --check 零写入。（镜像 practice publisher `_load_practice_review_records`
    的 build-time 人审保留模式。）"""
    from deeptutor.services.luban_lesson.variant_eligibility import (
        decision_identity_sha256,
        review_signature_envelope_sha256,
        variant_content_sha256,
    )

    out_path = tmp_path / "_F16_variant_bank.v0.json"
    monkeypatch.setattr(_mod, "OUT_PATH", out_path)
    monkeypatch.setattr(_mod, "REPO", tmp_path)  # 只影响收尾 relative_to 打印
    monkeypatch.setattr(sys, "argv", ["build_luban_f16_variant_bank.py"])
    assert _mod.main() == 0
    bank = json.loads(out_path.read_text(encoding="utf-8"))

    # 给第一个变体 bake 一条已签 decision（identity 用真实 sha 链）
    variant = bank["variants"][0]
    temptation, loss_reason = "诱错点", "丢分原因"
    decision = {
        "schema": "luban_variant_decision.v1",
        "fact_id": "f16-fact-demo",
        "skeleton_id": "f16-vskel-demo-ok",
        "probe_role": "immediate_confirm",
        "temptation": temptation,
        "loss_reason": loss_reason,
        "source_anchor": str(variant["anchor"]),
        "source_sha256": bank["source_pack_sha256"],
        "content_sha256": variant_content_sha256(
            variant, temptation=temptation, loss_reason=loss_reason
        ),
    }
    decision["decision_identity_sha256"] = decision_identity_sha256(decision)
    decision["review"] = {
        "status": "signed",
        "verdict": "approved",
        "reviewed_content_sha256": decision["content_sha256"],
        "reviewed_decision_sha256": decision["decision_identity_sha256"],
        "signatures": [
            {"role": "teaching", "reviewer_id": "r", "signed_at": "t"},
            {"role": "scoring", "reviewer_id": "r", "signed_at": "t"},
        ],
        "checks": {
            "source_verified": True,
            "answer_verified": True,
            "diagnosis_verified": True,
            "longest_option_checked": True,
            "template_leakage_checked": True,
        },
    }
    decision["review"]["signature_envelope_sha256"] = (
        review_signature_envelope_sha256(decision)
    )
    variant["decision"] = decision
    out_path.write_text(
        json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    # --check 零写入
    before = out_path.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["build_luban_f16_variant_bank.py", "--check"])
    assert _mod.main() == 0
    assert out_path.read_text(encoding="utf-8") == before

    # 重建：decision 原位保留（variant_id + content_sha256 比中），其余变体不受扰
    monkeypatch.setattr(sys, "argv", ["build_luban_f16_variant_bank.py"])
    assert _mod.main() == 0
    rebuilt = json.loads(out_path.read_text(encoding="utf-8"))
    assert rebuilt["variants"][0]["decision"] == decision
    assert all("decision" not in v for v in rebuilt["variants"][1:])
