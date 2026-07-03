"""§6-4 primary_taxonomy_ref 机器可读化（确定性编译，可重跑零漂移）。

从 60-slot 注册表 md（唯一权威）机械编译出
``docs/原始数据/考点原料/成品/_pack_taxonomy_registry.v0.json``：
taxonomy_code→pack 反查的唯一机器可读源。primary_taxonomy_ref = 注册表
refs 首项（机械取，不做语义判断），一律标 ``primary_taxonomy_ref_provisional:
true`` —— 只用于反查消歧，绝不当判分 authority。

同时产出「待教研复核清单」：primary 全量 + IR↔注册表漂移项。

用法::

    python scripts/compile_luban_pack_taxonomy_registry.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_MD = (
    REPO_ROOT
    / "docs/plan/鲁班移动端提分闭环/2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md"
)
IR_DIR = REPO_ROOT / "artifacts/luban_case_family_assets/diagram_microlesson"
OUTPUT_JSON = REPO_ROOT / "docs/原始数据/考点原料/成品/_pack_taxonomy_registry.v0.json"
REVIEW_MD = REPO_ROOT / "docs/原始数据/考点原料/待教研复核-primary_taxonomy_ref.md"


def _load_checker_module():
    spec = importlib.util.spec_from_file_location(
        "check_luban_animation_taxonomy_alignment",
        REPO_ROOT / "scripts/check_luban_animation_taxonomy_alignment.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compile_registry() -> dict:
    checker = _load_checker_module()
    rows = checker.parse_registry(REGISTRY_MD)
    packs: dict[str, dict] = {}
    for row in rows:
        refs = list(row.taxonomy_refs)
        packs[row.pack_id] = {
            "slot": row.slot,
            "student_title": row.student_title,
            "alignment_status": row.alignment_status,
            "primary_taxonomy_ref": refs[0] if refs else "",
            "primary_taxonomy_ref_provisional": True,
            "supporting_taxonomy_refs": refs[1:],
            "note": row.note,
        }
    return {
        "schema": "luban_pack_taxonomy_registry.v0",
        "source_registry": REGISTRY_MD.relative_to(REPO_ROOT).as_posix(),
        "source_registry_sha256": hashlib.sha256(REGISTRY_MD.read_bytes()).hexdigest(),
        "authority_note": (
            "primary_taxonomy_ref 为注册表 refs 首项机械取值（provisional，待教研复核），"
            "只用于 taxonomy_code→pack 反查消歧，不充判分 authority；"
            "判分归 signed grading artifact。"
        ),
        "packs": packs,
    }


def _ir_drift_report(compiled: dict) -> list[str]:
    lines: list[str] = []
    packs = compiled["packs"]
    seen_ir_packs: set[str] = set()
    for path in sorted(IR_DIR.glob("P40_*.animation_ir.v0.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        alignment = payload.get("taxonomy_alignment")
        if not isinstance(alignment, dict):
            lines.append(f"- `{path.name}`：缺 taxonomy_alignment 块")
            continue
        pack_id = str(alignment.get("pack_id") or "").strip()
        seen_ir_packs.add(pack_id)
        entry = packs.get(pack_id)
        if entry is None:
            lines.append(f"- `{path.name}`：pack `{pack_id}` 不在 60-slot 注册表")
            continue
        registered = {entry["primary_taxonomy_ref"], *entry["supporting_taxonomy_refs"]}
        ir_refs = [str(item).strip() for item in list(alignment.get("canonical_taxonomy_refs") or [])]
        drift = [ref for ref in ir_refs if ref and ref not in registered]
        if drift:
            lines.append(f"- `{path.name}`：refs 漂移 {drift}（注册表未登记）")
        status = str(alignment.get("status") or "").strip()
        if status and status != entry["alignment_status"]:
            lines.append(
                f"- `{path.name}`：status `{status}` ≠ 注册表 `{entry['alignment_status']}`"
            )
    no_ir = sorted(pack for pack in packs if pack not in seen_ir_packs)
    if no_ir:
        lines.append(f"- 注册表登记但无 animation IR 的 slot：{'、'.join(no_ir)}")
    return lines


def _write_review_md(compiled: dict, drift_lines: list[str]) -> None:
    packs = compiled["packs"]
    rows = [
        f"| {entry['slot']} | {pack_id} | `{entry['primary_taxonomy_ref'] or '（空）'}` | {entry['alignment_status']} | 待复核 |"
        for pack_id, entry in sorted(packs.items(), key=lambda kv: int(str(kv[1]["slot"]).split("/")[0]) if str(kv[1]["slot"]).isdigit() else 999)
    ]
    body = "\n".join(
        [
            "# 待教研复核 — primary_taxonomy_ref（机械取值，provisional）",
            "",
            "> 来源：`scripts/compile_luban_pack_taxonomy_registry.py` 从 60-slot 注册表机械取 refs 首项。",
            "> **全部条目 provisional**：只用于 taxonomy_code→pack 反查消歧，不充判分 authority。",
            "> 教研确认某 pack 主锚后，请在注册表 md 调整该行 refs 首项并重跑编译脚本。",
            "",
            "## 1. primary_taxonomy_ref 全量（60 slot）",
            "",
            "| Slot | Pack | primary_taxonomy_ref（机械首项） | 对齐状态 | 教研复核 |",
            "|---:|---|---|---|---|",
            *rows,
            "",
            "## 2. IR↔注册表漂移项（需教研裁决）",
            "",
            *(drift_lines or ["- 无漂移"]),
            "",
        ]
    )
    REVIEW_MD.write_text(body, encoding="utf-8")


def main() -> int:
    compiled = compile_registry()
    OUTPUT_JSON.write_text(
        json.dumps(compiled, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    drift_lines = _ir_drift_report(compiled)
    _write_review_md(compiled, drift_lines)
    print(f"compiled {len(compiled['packs'])} packs -> {OUTPUT_JSON.relative_to(REPO_ROOT)}")
    print(f"review checklist -> {REVIEW_MD.relative_to(REPO_ROOT)} (drift items: {len(drift_lines)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
