"""§6-3/§6-4 数据守护：animation IR 的 taxonomy_alignment 必须与 60-slot
注册表一致；`_pack_taxonomy_registry.v0.json` 是 taxonomy_code→pack 反查的
唯一机器可读编译产物（primary 全部 provisional，待教研复核）。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
IR_DIR = REPO_ROOT / "artifacts/luban_case_family_assets/diagram_microlesson"
REGISTRY_MD = REPO_ROOT / "docs/plan/鲁班移动端提分闭环/2026-06-19-luban-animation-pack-taxonomy-alignment-registry.md"
COMPILED_REGISTRY = REPO_ROOT / "docs/原始数据/考点原料/成品/_pack_taxonomy_registry.v0.json"


def _load_checker_module():
    spec = importlib.util.spec_from_file_location(
        "check_luban_animation_taxonomy_alignment",
        REPO_ROOT / "scripts/check_luban_animation_taxonomy_alignment.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _registry_rows_by_pack() -> dict[str, object]:
    checker = _load_checker_module()
    return {row.pack_id: row for row in checker.parse_registry(REGISTRY_MD)}


def _ir_alignment_blocks() -> dict[str, dict]:
    blocks: dict[str, dict] = {}
    for path in sorted(IR_DIR.glob("P40_*.animation_ir.v0.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        alignment = payload.get("taxonomy_alignment")
        if isinstance(alignment, dict):
            blocks[path.name] = alignment
    return blocks


def test_every_p40_ir_has_taxonomy_alignment_block() -> None:
    ir_files = sorted(IR_DIR.glob("P40_*.animation_ir.v0.json"))
    assert ir_files, "no animation IR files found"
    missing = [
        path.name
        for path in ir_files
        if not isinstance(json.loads(path.read_text(encoding="utf-8")).get("taxonomy_alignment"), dict)
    ]
    assert missing == [], f"IR missing taxonomy_alignment block: {missing}"


def test_ir_alignment_status_and_refs_match_60_slot_registry() -> None:
    rows = _registry_rows_by_pack()
    valid_statuses = {"direct", "composite", "coarse_review", "merged_child", "conditional_split"}
    problems: list[str] = []
    for name, alignment in _ir_alignment_blocks().items():
        pack_id = str(alignment.get("pack_id") or "").strip()
        row = rows.get(pack_id)
        if row is None:
            problems.append(f"{name}: pack {pack_id!r} not in 60-slot registry")
            continue
        status = str(alignment.get("status") or "").strip()
        if status not in valid_statuses:
            problems.append(f"{name}: invalid status {status!r}")
        elif status != row.alignment_status:
            problems.append(f"{name}: status {status!r} != registry {row.alignment_status!r}")
        refs = [str(item).strip() for item in list(alignment.get("canonical_taxonomy_refs") or [])]
        if not refs:
            problems.append(f"{name}: missing canonical_taxonomy_refs")
            continue
        drift = [ref for ref in refs if ref not in row.taxonomy_refs]
        if drift:
            problems.append(f"{name}: refs {drift} not registered for pack {pack_id}")
    assert problems == [], "\n".join(problems)


def test_compiled_pack_taxonomy_registry_matches_md_registry() -> None:
    assert COMPILED_REGISTRY.exists(), (
        "run scripts/compile_luban_pack_taxonomy_registry.py to build the compiled registry"
    )
    compiled = json.loads(COMPILED_REGISTRY.read_text(encoding="utf-8"))
    assert compiled.get("schema") == "luban_pack_taxonomy_registry.v0"
    packs = compiled.get("packs") or {}
    rows = _registry_rows_by_pack()
    assert set(packs) == set(rows), "compiled registry must cover exactly the 60-slot registry rows"
    for pack_id, row in rows.items():
        entry = packs[pack_id]
        assert entry["primary_taxonomy_ref"] == (row.taxonomy_refs[0] if row.taxonomy_refs else ""), pack_id
        # 机械取首 ref：绝不当判分 authority,一律标 provisional 待教研复核。
        assert entry["primary_taxonomy_ref_provisional"] is True, pack_id
        assert tuple(entry["supporting_taxonomy_refs"]) == tuple(row.taxonomy_refs[1:]), pack_id
        assert entry["alignment_status"] == row.alignment_status, pack_id


def test_compiled_registry_is_deterministic_rebuild() -> None:
    spec = importlib.util.spec_from_file_location(
        "compile_luban_pack_taxonomy_registry",
        REPO_ROOT / "scripts/compile_luban_pack_taxonomy_registry.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rebuilt = module.compile_registry()
    on_disk = json.loads(COMPILED_REGISTRY.read_text(encoding="utf-8"))
    assert rebuilt == on_disk, "compiled registry drifted from md registry — rerun the compile script"
