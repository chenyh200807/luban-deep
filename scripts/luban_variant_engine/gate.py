"""三门 gate（verdict_mismatch / contested_leak / duplicate_surface）——
18 个旧 builder 中 17 个逐字节相同的 run_gate 收敛为唯一实现。"""
from __future__ import annotations

from typing import Any

from .verdict import independent_verdict


def run_gate(spec: dict[str, Any], variants: list[dict[str, Any]]) -> dict[str, Any]:
    contested_tokens = tuple(spec.get("contested_tokens") or ())
    mismatches, contested, dup = [], [], []
    seen: set[str] = set()
    for v in variants:
        iv = independent_verdict(spec, v)
        if iv is None or iv != v["expected_ok"]:
            mismatches.append(v["variant_id"])
        if any(t in v["surface"] or t in v["correct_statement"] for t in contested_tokens):
            contested.append(v["variant_id"])
        key = v["surface"]
        if key in seen:
            dup.append(v["variant_id"])
        seen.add(key)
    total = len(variants)
    passed = total - len(set(mismatches + contested + dup))
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "verdict_mismatches": mismatches,
        "contested_leaks": contested,
        "duplicate_surfaces": dup,
    }
