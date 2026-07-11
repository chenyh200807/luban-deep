"""变体引擎单元测试（工单②：18 builder 收敛）。

覆盖: spec 健康检查(退化单极拒绝)/对偶强制成对/双推互证抓破坏/X02 试点全等。
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.luban_variant_engine.gate import run_gate  # noqa: E402
from scripts.luban_variant_engine.generators import generate  # noqa: E402
from scripts.luban_variant_engine.spec import SpecError, validate_spec  # noqa: E402


def _min_spec(**overrides):
    spec = {
        "pack_id": "T99",
        "pack_file": "x.md",
        "schema_version": "t",
        "site_skins": ["某工地"],
        "rule_groups": [{
            "id": "A-t", "kind": "threshold", "verdict_op": "<=",
            "param_key": "n", "thr": 16, "values": [12, 18],
            "surface": "{skin}住 {value} 人",
            "correct_statement": "c", "anchor": "kc:x",
        }],
    }
    spec.update(overrides)
    return spec


def test_threshold_straddle_health_check_rejects_degenerate():
    """取值域不横跨阈值=退化单极(答案泄露温床)——spec 层直接拒绝。"""
    bad = _min_spec()
    bad["rule_groups"][0]["values"] = [1, 2, 3]  # 全部 <=16 → 全妥
    with pytest.raises(SpecError, match="退化单极"):
        validate_spec(bad)


def test_dual_membership_forced_pairing():
    """对偶引擎化: 每 item 必出 正+反 两条, 句式壳与答案相关性归零。"""
    spec = _min_spec()
    spec["rule_groups"] = [{
        "id": "D-t", "kind": "dual_membership", "param_key": "item",
        "enum": ["甲", "乙"],
        "surface_pos": "{skin}将「{value}」列入方案", "surface_neg": "{skin}认为「{value}」无需列入",
        "correct_statement": "c", "anchor": "kc:x",
    }]
    validate_spec(spec)
    variants = generate(spec)
    assert len(variants) == 4  # 2 item × 正/反
    by_item = {}
    for v in variants:
        by_item.setdefault(v["params"]["item"], []).append(v["expected_ok"])
    assert all(sorted(oks) == [False, True] for oks in by_item.values())
    # "认为"句不再恒错: 含"认为"的都是 False, 含"列入"的都是 True——但每 item 成对,
    # 风格审计尺的组合口诀对该组命中率=50%(无信息量)
    gate = run_gate(spec, variants)
    assert gate["passed"] == gate["total"] == 4


def test_mutual_check_catches_generator_sabotage():
    """双推互证: 篡改 expected_ok 必被 gate 抓 mismatch。"""
    spec = _min_spec()
    validate_spec(spec)
    variants = generate(spec)
    variants[0]["expected_ok"] = not variants[0]["expected_ok"]
    gate = run_gate(spec, variants)
    assert variants[0]["variant_id"] in gate["verdict_mismatches"]


def test_out_of_domain_param_rejected():
    """封闭取值域外的 params 判 None → mismatch(fail-closed)。"""
    spec = _min_spec()
    validate_spec(spec)
    variants = generate(spec)
    variants[0]["params"]["n"] = 999
    gate = run_gate(spec, variants)
    assert variants[0]["variant_id"] in gate["verdict_mismatches"]


def test_x02_pilot_field_equal_with_signed_bank():
    """试点过闸判据: 引擎产物与现有 signed bank 的 variants 逐字段全等。"""
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.luban_variant_engine.build", "--pack", "X02", "--diff"],
        capture_output=True, text=True, timeout=120, cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DIFF-EQUAL" in proc.stdout
