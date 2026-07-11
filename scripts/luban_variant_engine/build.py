"""引擎 CLI：python3 -m scripts.luban_variant_engine.build --pack X02 [--check] [--diff]

payload 形状与旧 builder 逐字段兼容（schema_version/pack_id/status=candidate/
source_pack_sha256/generation_ms/gate/per_group_counts/variants）；
--diff 对比现有 bank 的 variants 逐字段全等（迁移过闸判据）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from .gate import run_gate
from .generators import generate
from .spec import REPO, SpecError, load_spec

PACK_DIR = REPO / "docs" / "原始数据" / "考点原料" / "成品"


def build_payload(pack_id: str) -> dict:
    spec = load_spec(pack_id)
    pack_path = PACK_DIR / str(spec["pack_file"])
    if not pack_path.exists():
        raise SpecError(f"pack 正文不存在: {pack_path}")
    t0 = time.perf_counter()
    variants = generate(spec)
    gen_ms = (time.perf_counter() - t0) * 1000
    gate = run_gate(spec, variants)
    return {
        "schema_version": str(spec["schema_version"]),
        "pack_id": spec["pack_id"],
        "status": "candidate",  # 签发唯一入口 = promote_variant_bank.py(人闸)
        "source_pack_sha256": hashlib.sha256(pack_path.read_bytes()).hexdigest(),
        "generation_ms": round(gen_ms, 2),
        "gate": gate,
        "per_group_counts": {
            g: sum(1 for v in variants if v["rule_group"] == g)
            for g in sorted({v["rule_group"] for v in variants})
        },
        "variants": variants,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", required=True)
    parser.add_argument("--check", action="store_true", help="只跑 gate 不写文件")
    parser.add_argument("--diff", action="store_true",
                        help="与现有 bank 的 variants 逐字段比对(迁移过闸判据)")
    args = parser.parse_args()

    try:
        payload = build_payload(args.pack)
    except SpecError as exc:
        print(f"luban-variant-engine: FAIL — {exc}", file=sys.stderr)
        return 1
    gate = payload["gate"]
    clean = not (gate["verdict_mismatches"] or gate["contested_leaks"] or gate["duplicate_surfaces"])
    core = sum(1 for v in payload["variants"] if not v["extension"])
    print(f"variants={gate['total']} (core={core}) gate_pass={gate['passed']} "
          f"rate={gate['pass_rate']:.2%} -> {'PASS' if clean else 'FAIL'}")
    if not clean:
        print(json.dumps({k: gate[k] for k in
                          ("verdict_mismatches", "contested_leaks", "duplicate_surfaces")},
                         ensure_ascii=False), file=sys.stderr)
        return 1

    out_path = PACK_DIR / f"_{payload['pack_id']}_variant_bank.v0.json"
    if args.diff:
        if not out_path.exists():
            print("luban-variant-engine: 无现有 bank 可比", file=sys.stderr)
            return 1
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        old_variants = existing.get("variants") or []
        new_variants = payload["variants"]
        if old_variants == new_variants:
            print(f"DIFF-EQUAL ✓ {len(new_variants)} 个变体与现有 bank 逐字段全等")
            return 0
        print(f"DIFF-MISMATCH: 现有 {len(old_variants)} vs 引擎 {len(new_variants)}",
              file=sys.stderr)
        for i, (a, b) in enumerate(zip(old_variants, new_variants)):
            if a != b:
                print(f"  首个差异@{i}:\n    旧 {json.dumps(a, ensure_ascii=False)[:160]}"
                      f"\n    新 {json.dumps(b, ensure_ascii=False)[:160]}", file=sys.stderr)
                break
        return 1
    if args.check:
        return 0
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(f"written {out_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
