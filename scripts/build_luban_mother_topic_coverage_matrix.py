#!/usr/bin/env python3
"""Build the Luban mother-topic capability coverage audit.

The audit is governance-only.  It joins the 60-slot planning registry to the
current pack manifest, taxonomy source, compiled source summaries, and per-pack
exam evidence.  It does not write runtime supply or learner state.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO / "docs" / "原始数据" / "考点原料"
PACK_DIR = PACK_ROOT / "成品"
REGISTRY = PACK_DIR / "_pack_taxonomy_registry.v0.json"
MANIFEST = PACK_DIR / "_pack_manifest.json"
TAXONOMY = REPO / "docs" / "原始数据" / "2026_副本" / "taxonomy" / "FINAL_CLEANED_TAXONOMY2026.json"
DEFAULT_OUT = PACK_ROOT / "母题覆盖审计_v1"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _taxonomy_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def walk(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            code = str(node.get("code") or node.get("canonical_code") or "")
            if code:
                result[code] = node
            walk(node.get("children") or [])

    walk(payload.get("outline_structure") or [])
    return result


def _pack_evidence(pack_id: str) -> tuple[int | None, int | None, int | None]:
    exam_path = PACK_ROOT / f"_{pack_id}_exam_evidence.json"
    source_path = PACK_ROOT / f"_{pack_id}_compiled_source.json"
    exam_hits: int | None = None
    source_units: int | None = None
    scoring_points: int | None = None
    if exam_path.is_file():
        value = _read_json(exam_path).get("真题命中")
        exam_hits = int(value) if isinstance(value, (int, float)) else None
    if source_path.is_file():
        source = _read_json(source_path)
        units = source.get("命中单元")
        points = source.get("去重采分点")
        source_units = int(units) if isinstance(units, (int, float)) else None
        scoring_points = int(points) if isinstance(points, (int, float)) else None
    return exam_hits, source_units, scoring_points


def _coverage_strength(
    *, exists: bool, alignment: str, manifest_pack: dict[str, Any] | None, exam_hits: int | None
) -> tuple[str, int]:
    if not exists:
        return "missing", 0
    if alignment == "coarse_review" or bool((manifest_pack or {}).get("needs_leaf_review")):
        return "coarse_boundary", 1
    if alignment == "composite":
        return "broad_composite", 2
    if exam_hits is None:
        return "source_grounded_exam_unmeasured", 2
    if exam_hits == 0:
        return "source_grounded_exam_zero", 2
    if (
        alignment == "direct"
        and bool((manifest_pack or {}).get("has_compiled_source"))
        and bool((manifest_pack or {}).get("jury_clean"))
    ):
        return "strong_direct", 4
    return "supported", 3


def _expansion_decision(
    *, pack_id: str, exists: bool, alignment: str, overlap_ratio: float, note: str
) -> tuple[str, str, str]:
    if exists:
        if alignment == "coarse_review":
            return "no", "refine_existing_boundary", "已有母题；先补精确 leaf/source 边界"
        if alignment == "composite":
            return "no", "refine_existing_composite", "已有组合母题；先收窄主辅能力边界"
        return "no", "retain_existing", "已有独立母题，不新增同义包"

    if alignment == "merged_child":
        if pack_id == "K02":
            return "no", "merge_into_planned_parent", note
        return "no", "merge_into_existing", note
    if alignment == "conditional_split":
        return "conditional", "split_only_with_evidence", note
    if pack_id == "E04":
        return (
            "yes_candidate",
            "add_after_exam_evidence",
            "存在独立竣工结算能力；先与 E03/K04 划界，再补真题与 source 证据",
        )
    if pack_id == "K04":
        return "conditional", "hold_until_parent_boundary", note
    if alignment == "coarse_review":
        return "conditional", "evidence_first", note
    if overlap_ratio >= 0.5 or "迁移包" in note or "联动" in note:
        return "no", "enrich_existing_instead", "与现有母题共享多数 taxonomy refs；先补现有包"
    if alignment == "composite":
        return "conditional", "candidate_after_boundary_review", "有独立能力残差，但需先证明组合边界"
    return "conditional", "candidate_after_exam_evidence", "taxonomy 可解析；需补真题与独立性证据"


def build_matrix() -> dict[str, Any]:
    registry_payload = _read_json(REGISTRY)
    manifest_payload = _read_json(MANIFEST)
    taxonomy_payload = _read_json(TAXONOMY)
    registry = registry_payload["packs"]
    manifest = {row["pack_id"]: row for row in manifest_payload["packs"]}
    taxonomy = _taxonomy_index(taxonomy_payload)

    refs_by_pack = {
        pack_id: [row["primary_taxonomy_ref"], *(row.get("supporting_taxonomy_refs") or [])]
        for pack_id, row in registry.items()
    }
    unresolved = sorted({ref for refs in refs_by_pack.values() for ref in refs if ref not in taxonomy})
    if unresolved:
        raise ValueError(f"unresolved taxonomy refs: {unresolved}")

    existing_ref_owners: dict[str, list[str]] = defaultdict(list)
    all_ref_owners: dict[str, list[str]] = defaultdict(list)
    for pack_id, refs in refs_by_pack.items():
        for ref in refs:
            all_ref_owners[ref].append(pack_id)
            if pack_id in manifest:
                existing_ref_owners[ref].append(pack_id)

    rows: list[dict[str, Any]] = []
    for pack_id, planned in sorted(registry.items(), key=lambda item: int(item[1]["slot"])):
        refs = refs_by_pack[pack_id]
        existing = pack_id in manifest
        current = manifest.get(pack_id)
        exam_hits, source_units, scoring_points = _pack_evidence(pack_id)
        overlap_refs = sorted(ref for ref in refs if existing_ref_owners.get(ref))
        overlap_packs = sorted(
            {
                owner
                for ref in overlap_refs
                for owner in existing_ref_owners[ref]
                if owner != pack_id
            }
        )
        registry_overlap_refs = sorted(
            ref for ref in refs if any(owner != pack_id for owner in all_ref_owners[ref])
        )
        registry_overlap_packs = sorted(
            {
                owner
                for ref in registry_overlap_refs
                for owner in all_ref_owners[ref]
                if owner != pack_id
            }
        )
        overlap_ratio = len(overlap_refs) / len(refs) if refs else 0.0
        unique_refs = [ref for ref in refs if not existing_ref_owners.get(ref)] if not existing else []
        strength, strength_score = _coverage_strength(
            exists=existing,
            alignment=str(planned["alignment_status"]),
            manifest_pack=current,
            exam_hits=exam_hits,
        )
        worth, action, rationale = _expansion_decision(
            pack_id=pack_id,
            exists=existing,
            alignment=str(planned["alignment_status"]),
            overlap_ratio=overlap_ratio,
            note=str(planned.get("note") or ""),
        )
        rows.append(
            {
                "slot": int(planned["slot"]),
                "capability_id": pack_id,
                "capability_title": planned["student_title"],
                "primary_taxonomy_ref": planned["primary_taxonomy_ref"],
                "primary_taxonomy_name": taxonomy[planned["primary_taxonomy_ref"]].get("name", ""),
                "supporting_taxonomy_refs": planned.get("supporting_taxonomy_refs") or [],
                "alignment_status": planned["alignment_status"],
                "existing_mother_topics": [pack_id] if existing else [],
                "coverage_strength": strength,
                "coverage_strength_score": strength_score,
                "exam_evidence_hits_candidate": exam_hits,
                "compiled_source_units": source_units,
                "compiled_scoring_points": scoring_points,
                "overlap_existing_mother_topics": overlap_packs,
                "shared_existing_taxonomy_refs": overlap_refs,
                "overlap_existing_ratio": round(overlap_ratio, 4),
                "overlap_registry_capabilities": registry_overlap_packs,
                "shared_registry_taxonomy_refs": registry_overlap_refs,
                "missing_capability_refs": unique_refs,
                "missing_capability_names": [taxonomy[ref].get("name", "") for ref in unique_refs],
                "worth_adding": worth,
                "recommended_action": action,
                "decision_rationale": rationale,
                "registry_note": planned.get("note") or "",
            }
        )

    return {
        "schema": "luban_mother_topic_coverage_audit.v1",
        "authority_status": "governance_audit_only",
        "scope": "60-slot mother-topic capability registry; not full textbook taxonomy coverage",
        "boundaries": [
            "exam evidence hit counts are candidate retrieval evidence, not official exam frequency",
            "absence of an exam evidence file does not prove the capability was never examined",
            "taxonomy refs are routing anchors, not scoring authority",
            "this artifact does not authorize runtime supply, learner-state writes, or production release",
        ],
        "source_paths": {
            "registry": str(REGISTRY.relative_to(REPO)),
            "manifest": str(MANIFEST.relative_to(REPO)),
            "taxonomy": str(TAXONOMY.relative_to(REPO)),
        },
        "source_sha256": {
            "registry": _sha256(REGISTRY),
            "manifest": _sha256(MANIFEST),
            "taxonomy": _sha256(TAXONOMY),
        },
        "counts": {
            "capability_slots": len(rows),
            "existing_mother_topics": sum(bool(row["existing_mother_topics"]) for row in rows),
            "missing_slots": sum(not row["existing_mother_topics"] for row in rows),
            "coverage_strength": dict(Counter(row["coverage_strength"] for row in rows)),
            "worth_adding": dict(Counter(row["worth_adding"] for row in rows)),
            "recommended_action": dict(Counter(row["recommended_action"] for row in rows)),
            "shared_taxonomy_refs": sum(1 for owners in all_ref_owners.values() if len(owners) > 1),
        },
        "rows": rows,
    }


def _csv_text(rows: list[dict[str, Any]]) -> str:
    fields = [
        "slot",
        "capability_id",
        "capability_title",
        "primary_taxonomy_ref",
        "primary_taxonomy_name",
        "existing_mother_topics",
        "coverage_strength",
        "exam_evidence_hits_candidate",
        "overlap_existing_mother_topics",
        "overlap_registry_capabilities",
        "missing_capability_names",
        "worth_adding",
        "recommended_action",
        "decision_rationale",
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        csv_row = dict(row)
        for field in (
            "existing_mother_topics",
            "overlap_existing_mother_topics",
            "overlap_registry_capabilities",
            "missing_capability_names",
        ):
            csv_row[field] = "；".join(csv_row[field])
        writer.writerow(csv_row)
    return buffer.getvalue()


def _summary_markdown(audit: dict[str, Any]) -> str:
    rows = audit["rows"]
    missing = [row for row in rows if not row["existing_mother_topics"]]
    lines = [
        "# 鲁班母题能力覆盖审计 v1",
        "",
        "> 口径：60-slot 母题能力注册表，不是 2116 个 taxonomy 节点的教材全覆盖。",
        "> 真题命中为候选检索证据，不是官方考频；taxonomy ref 不是判分 authority。",
        "",
        "## 总览",
        "",
        f"- 能力槽：**{audit['counts']['capability_slots']}**",
        f"- 已有母题：**{audit['counts']['existing_mother_topics']}**",
        f"- 未建能力槽：**{audit['counts']['missing_slots']}**",
        f"- 注册表内共享 taxonomy ref：**{audit['counts']['shared_taxonomy_refs']}**",
        "",
        "## 未建能力裁决",
        "",
        "| Slot | 能力点 | 覆盖强度 | 重叠能力槽（已有/规划） | 缺失能力 | 是否值得新增 | 动作 |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in missing:
        existing_overlap = "/".join(row["overlap_existing_mother_topics"]) or "—"
        planned_only = sorted(
            set(row["overlap_registry_capabilities"])
            - set(row["overlap_existing_mother_topics"])
        )
        overlap = f"{existing_overlap} / {'/'.join(planned_only) or '—'}"
        gaps = "；".join(row["missing_capability_names"]) or "—"
        lines.append(
            f"| {row['slot']} | {row['capability_id']} {row['capability_title']} | {row['coverage_strength']} | "
            f"{overlap} | {gaps} | {row['worth_adding']} | {row['recommended_action']} |"
        )
    lines.extend(
        [
            "",
            "## 当前裁决",
            "",
            "1. **不把 19 个空槽等同于 19 个应新增母题。**",
            "2. **E04 是当前唯一 `yes_candidate`**：独立残差是竣工结算申请/支付与结算确定/调整；补真题证据后再立项。",
            "3. E02、G05、K05、R04、N04 与现有母题共享多数能力锚，优先扩充现有包，不新造平行母题。",
            "4. F06、D17、X04 并入现有母题；K02 并入规划中的 K06，不独立新增；R05、X05、D15、D16 仅保留条件拆分。",
            "5. E03、K03、R02/R03 先补精确 leaf/source；K06 先完成责任事件边界审查；K04 等 E04/K05 边界稳定。",
            "",
            "## 全量矩阵",
            "",
            "详见 `matrix.csv`（便于筛选）与 `matrix.json`（保留全部 refs、计数和 source SHA）。",
            "",
        ]
    )
    return "\n".join(lines)


def _manifest_payload(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "luban_mother_topic_coverage_audit_manifest.v1",
        "authority_status": audit["authority_status"],
        "source_paths": audit["source_paths"],
        "source_sha256": audit["source_sha256"],
        "outputs": ["matrix.json", "matrix.csv", "summary.md"],
        "counts": audit["counts"],
    }


def write_outputs(audit: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "matrix.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "matrix.csv").write_text(_csv_text(audit["rows"]), encoding="utf-8")
    (out_dir / "summary.md").write_text(_summary_markdown(audit), encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(_manifest_payload(audit), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit = build_matrix()
    if args.check:
        expected = {
            "matrix.json": json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
            "matrix.csv": _csv_text(audit["rows"]),
            "summary.md": _summary_markdown(audit),
            "manifest.json": json.dumps(
                _manifest_payload(audit), ensure_ascii=False, indent=2
            )
            + "\n",
        }
        for name, content in expected.items():
            path = args.out / name
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"stale output: {path}")
        print("mother-topic coverage matrix: check passed")
        return 0
    write_outputs(audit, args.out)
    print(json.dumps(audit["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
